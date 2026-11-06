import uuid

from sqlalchemy.orm import Session

from app.models import AiExtraction, User
from app.modules.ai_orders import matcher, service
from app.modules.ai_orders.schemas import (
    ConfirmExtractionInput,
    DraftSummaryOut,
    ExtractionItemOut,
    ExtractionOut,
    ExtractOrderInput,
    ProductChoiceOut,
)
from app.modules.orders.controller import order_out
from app.modules.orders.repository import get_products
from app.utils.responses import success_response


def extraction_out(db: Session, extraction: AiExtraction) -> ExtractionOut:
    products = get_products(db, [i.matched_product_id for i in extraction.items if i.matched_product_id])
    items = []
    for item in extraction.items:
        product = products.get(item.matched_product_id)
        items.append(ExtractionItemOut(
            id=item.id, original_text=item.original_text, extracted_name=item.extracted_name,
            quantity=item.quantity, unit=item.unit,
            product=ProductChoiceOut(product_id=product.id, sku=product.sku, name=product.name,
                                     pack_size=product.pack_size, order_unit=product.order_unit) if product else None,
            confidence=item.confidence, alternatives=item.alternatives or [],
            requires_clarification=item.requires_clarification,
            clarification=matcher.clarification_reason(item, product.order_unit if product else None),
            evidence=item.evidence or [],
        ))
    return ExtractionOut(
        extraction_id=extraction.id, status=extraction.extraction_status, input_type=extraction.input_type,
        original_message=extraction.original_message, model_name=extraction.model_name, items=items,
    )


def list_drafts(db: Session, user: User, retailer_id: uuid.UUID | None) -> dict:
    drafts = service.list_drafts(db, user, retailer_id)
    return success_response("Drafts fetched", [
        DraftSummaryOut(
            extraction_id=d.id, created_at=d.created_at, original_message=d.original_message,
            item_count=len(d.items), needs_clarification=any(i.requires_clarification for i in d.items),
        )
        for d in drafts
    ])


def extract(db: Session, user: User, data: ExtractOrderInput) -> dict:
    extraction = service.extract_order(db, user, data)
    message = "Order read from your message. Please review it." if extraction.items else "No products found in the message."
    return success_response(message, extraction_out(db, extraction))


def extract_media(db: Session, user: User, *, kind, content, content_type, filename, retailer_id) -> dict:
    extraction = service.extract_from_media(db, user, kind=kind, content=content, content_type=content_type,
                                            filename=filename, retailer_id=retailer_id)
    source = "photo" if kind == "image" else "voice note"
    message = f"Order read from your {source}. Please review it." if extraction.items else f"No products found in the {source}."
    return success_response(message, extraction_out(db, extraction))


def get(db: Session, user: User, extraction_id: uuid.UUID) -> dict:
    return success_response("Extraction fetched", extraction_out(db, service.get_extraction(db, user, extraction_id)))


def confirm(db: Session, user: User, extraction_id: uuid.UUID, data: ConfirmExtractionInput) -> dict:
    order = service.confirm_extraction(db, user, extraction_id, data)
    return success_response("Order placed", order_out(order))
