"""AI order capture records and their human confirmation.

An extraction is never an order. Only confirm_extraction() creates an order, from items the
retailer (or their assigned salesman) has reviewed, and the order then goes through the
normal Order Desk workflow (review, correction, approval or rejection).
"""

import uuid

from sqlalchemy.orm import Session

from app.core.constants import ErrorCode, ExtractionStatus, OrderSource
from app.core.permissions import ensure_can_access_retailer
from app.exceptions.base import AppException
from app.models import AiExtraction, AiExtractionItem, Order, User
from app.modules.ai_orders import repository
from app.modules.ai_orders.schemas import ConfirmExtractionInput, RecordExtractionInput
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
            extraction_status=ExtractionStatus.PENDING,
            model_name=data.model_name,
            raw_response=data.raw_response,
        )
        for item in data.items:
            unclear = item.quantity is None or item.unit is None or item.matched_product_id is None
            extraction.items.append(AiExtractionItem(
                original_text=item.original_text,
                extracted_name=item.extracted_name,
                quantity=item.quantity,
                unit=item.unit,
                matched_product_id=item.matched_product_id,
                confidence=item.confidence,
                alternatives=item.alternatives,
                requires_clarification=item.requires_clarification or unclear,
            ))
        db.add(extraction)
        db.commit()
        return extraction
    except Exception:
        db.rollback()
        raise


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

        item_ids = {item.id for item in extraction.items}
        confirmed_ids = [item.extraction_item_id for item in data.items]
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
        db.commit()
        return order
    except Exception:
        db.rollback()
        raise
