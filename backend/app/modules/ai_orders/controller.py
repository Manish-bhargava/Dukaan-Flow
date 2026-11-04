import uuid

from sqlalchemy.orm import Session

from app.models import AiExtraction, User
from app.modules.ai_orders import matcher, service
from app.modules.ai_orders.schemas import (
    ConfirmExtractionInput,
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
        ))
    return ExtractionOut(
        extraction_id=extraction.id, status=extraction.extraction_status,
        original_message=extraction.original_message, model_name=extraction.model_name, items=items,
    )


def extract(db: Session, user: User, data: ExtractOrderInput) -> dict:
    extraction = service.extract_order(db, user, data)
    message = "Order read from your message. Please review it." if extraction.items else "No products found in the message."
    return success_response(message, extraction_out(db, extraction))


def get(db: Session, user: User, extraction_id: uuid.UUID) -> dict:
    return success_response("Extraction fetched", extraction_out(db, service.get_extraction(db, user, extraction_id)))


def confirm(db: Session, user: User, extraction_id: uuid.UUID, data: ConfirmExtractionInput) -> dict:
    order = service.confirm_extraction(db, user, extraction_id, data)
    return success_response("Order placed", order_out(order))
