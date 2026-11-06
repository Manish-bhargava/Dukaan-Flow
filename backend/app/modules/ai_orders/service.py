"""AI order capture records and their human confirmation.

An extraction is never an order. Only confirm_extraction() creates an order, from items the
retailer (or their assigned salesman) has reviewed, and the order then goes through the
normal Order Desk workflow (review, correction, approval or rejection).
"""

import base64
import uuid

from sqlalchemy.orm import Session

from app.core.constants import AiInputType, ErrorCode, ExtractionStatus, OrderSource
from app.core.permissions import ensure_can_access_retailer
from app.exceptions.base import AppException
from app.models import AiExtraction, AiExtractionItem, Order, User
from app.modules.ai_orders import graph, llm, matcher, repository
from app.modules.ai_orders.schemas import ConfirmExtractionInput, ExtractOrderInput, RecordExtractionInput
from app.modules.orders import service as orders_service
from app.modules.orders.schemas import OrderItemInput

CONFIRMABLE_STATUSES = (ExtractionStatus.PENDING, ExtractionStatus.REVIEWED)


def record_extraction(db: Session, actor: User, data: RecordExtractionInput) -> AiExtraction:
    """Store the original message and extracted lines. Creates no order."""
    try:
        retailer = orders_service.resolve_ordering_retailer(db, actor, data.retailer_id)
        extraction = AiExtraction(
            retailer_id=retailer.id,
            user_id=actor.id,
            original_message=data.original_message,
            input_type=data.input_type,
            extraction_status=ExtractionStatus.PENDING,
            model_name=data.model_name,
            raw_response=data.raw_response,
        )
        for line_no, item in enumerate(data.items, start=1):
            unclear = item.quantity is None or item.unit is None or item.matched_product_id is None
            extraction.items.append(AiExtractionItem(
                line_no=line_no,
                original_text=item.original_text,
                extracted_name=item.extracted_name,
                quantity=item.quantity,
                unit=item.unit,
                matched_product_id=item.matched_product_id,
                confidence=item.confidence,
                alternatives=item.alternatives,
                evidence=item.evidence,
                clarification_reason=item.clarification_reason,
                requires_clarification=item.requires_clarification or unclear,
            ))
        db.add(extraction)
        db.commit()
        return extraction
    except Exception:
        db.rollback()
        raise


def extract_order(db: Session, actor: User, data: ExtractOrderInput) -> AiExtraction:
    """Text message -> draft (see app/modules/ai_orders/graph.py). Never creates an order."""
    retailer = orders_service.resolve_ordering_retailer(db, actor, data.retailer_id)
    return graph.run(db, actor, retailer, input_type=AiInputType.TEXT, text=data.message)


IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mpeg", "audio/mp3", "audio/mp4", "audio/m4a", "audio/x-m4a",
               "audio/wav", "audio/x-wav", "audio/aac", "video/webm"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_AUDIO_BYTES = 10 * 1024 * 1024


def extract_from_media(db: Session, actor: User, *, kind: str, content: bytes, content_type: str | None,
                       filename: str | None, retailer_id: uuid.UUID | None) -> AiExtraction:
    """A photo of an order list (read by the vision model) or a voice note (transcribed
    first, then read like a message) -> draft. Never creates an order."""
    retailer = orders_service.resolve_ordering_retailer(db, actor, retailer_id)
    content_type = (content_type or "").split(";")[0].strip().lower()
    if kind == "image":
        if content_type not in IMAGE_TYPES:
            raise AppException("Send a JPEG, PNG or WebP photo", ErrorCode.VALIDATION_ERROR, 422)
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise AppException("The photo must be at most 5 MB", ErrorCode.VALIDATION_ERROR, 422)
        data_url = f"data:{content_type};base64,{base64.b64encode(content).decode()}"
        return graph.run(db, actor, retailer, input_type=AiInputType.IMAGE, text="", image_data_url=data_url)
    if kind == "voice":
        if content_type not in AUDIO_TYPES:
            raise AppException("Send the voice note as webm, ogg, mp3, m4a or wav", ErrorCode.VALIDATION_ERROR, 422)
        if not content or len(content) > MAX_AUDIO_BYTES:
            raise AppException("The voice note must be at most 10 MB", ErrorCode.VALIDATION_ERROR, 422)
        db.commit()  # no transaction open during the transcription call
        transcript = llm.transcribe(content, filename or "voice-note.webm", content_type)
        return graph.run(db, actor, retailer, input_type=AiInputType.VOICE, text=transcript[:2000])
    raise AppException("kind must be image or voice", ErrorCode.VALIDATION_ERROR, 422)


def list_drafts(db: Session, actor: User, retailer_id: uuid.UUID | None = None, limit: int = 20) -> list[AiExtraction]:
    """AI drafts not yet placed as an order (newest first). A draft is never an order: it
    only becomes one when the user confirms it, and then the Order Desk accepts or rejects it."""
    retailer = orders_service.resolve_ordering_retailer(db, actor, retailer_id)
    drafts = repository.list_open_extractions(db, retailer.id, list(CONFIRMABLE_STATUSES), limit)
    return [d for d in drafts if d.items]  # messages where nothing was recognised are not drafts


def get_extraction(db: Session, actor: User, extraction_id: uuid.UUID) -> AiExtraction:
    extraction = repository.get_extraction(db, extraction_id)
    if extraction is None:
        raise AppException("AI extraction not found", ErrorCode.RESOURCE_NOT_FOUND, 404, {"id": str(extraction_id)})
    orders_service.resolve_ordering_retailer(db, actor, extraction.retailer_id)
    return extraction


def confirm_extraction(
    db: Session, actor: User, extraction_id: uuid.UUID, data: ConfirmExtractionInput
) -> Order:
    """Turn reviewed extraction lines into an order (source AI) in one transaction.

    The confirmed product, quantity and unit come from the user's review, so items that
    required clarification are resolved by what the user states, never by a guess. Prices,
    schemes, stock and credit are evaluated exactly as for a manual order.
    """
    try:
        extraction = repository.get_extraction(db, extraction_id, lock=True)
        if extraction is None:
            raise AppException(
                "AI extraction not found", ErrorCode.RESOURCE_NOT_FOUND, 404, {"id": str(extraction_id)}
            )
        retailer = orders_service.resolve_ordering_retailer(db, actor, extraction.retailer_id)
        ensure_can_access_retailer(actor, retailer)
        if extraction.extraction_status not in CONFIRMABLE_STATUSES:
            raise AppException(
                f"Extraction is {extraction.extraction_status} and cannot be confirmed",
                ErrorCode.INVALID_EXTRACTION_STATUS,
                409,
            )

        items_by_id = {item.id: item for item in extraction.items}
        item_ids = set(items_by_id)
        confirmed_ids = [i.extraction_item_id for i in data.items if i.extraction_item_id is not None]
        unknown = [str(i) for i in confirmed_ids if i not in item_ids]
        if unknown or len(set(confirmed_ids)) != len(confirmed_ids):
            raise AppException(
                "Confirmed items must be distinct items of this extraction",
                ErrorCode.VALIDATION_ERROR,
                422,
                {"unknown_item_ids": unknown},
            )

        order = orders_service.build_order(
            db,
            actor,
            retailer,
            [OrderItemInput(product_id=i.product_id, quantity=i.quantity, unit=i.unit) for i in data.items],
            source=OrderSource.AI,
            remarks=data.remarks,
            ai_extraction_id=extraction.id,
        )
        extraction.extraction_status = ExtractionStatus.CONFIRMED
        # Link each AI line to the order line it became: its product (after any Order Desk
        # correction) is what the retailer meant, and future matching learns from it.
        lines_by_product = {line.product_id: line for line in order.items}
        for confirmed in data.items:
            source = items_by_id.get(confirmed.extraction_item_id)
            if source is not None and confirmed.product_id in lines_by_product:
                source.order_item_id = lines_by_product[confirmed.product_id].id

        # Learn the retailer's wording when they chose a different product than the match,
        # so the same words match directly next time (retailer-specific only).
        for confirmed in data.items:
            source = items_by_id.get(confirmed.extraction_item_id)
            if source is not None and confirmed.product_id != source.matched_product_id:
                wording = matcher.wording_for_alias(source.original_text, source.quantity)
                if wording:
                    repository.save_alias(db, retailer.id, confirmed.product_id, wording)
        db.commit()
        return order
    except Exception:
        db.rollback()
        raise
