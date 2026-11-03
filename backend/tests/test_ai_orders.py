"""AI extraction records stay separate from orders until a human confirms them."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.exceptions.base import AppException
from app.models import AiExtraction, Order, RetailerAlias
from app.modules.ai_orders import service as ai_orders
from app.modules.ai_orders.schemas import (
    ConfirmedItemInput,
    ConfirmExtractionInput,
    ExtractedItemInput,
    RecordExtractionInput,
)
from app.modules.orders import service as orders
from app.modules.orders.schemas import CorrectOrderItemInput
from seed.run_seed import seed_id
from tests.conftest import seed_user

BS075, BS150, DT1KG, TE250 = (
    seed_id("product", s) for s in ("SKU-BS-075", "SKU-BS-150", "SKU-DT-1KG", "SKU-TE-250")
)
MESSAGE = "bhaiya 5 peti biscuit chhota, 2 peti washing powder, 5 biscuit bhej dena"


def record(tx, user_key="retailer_sharma"):
    return ai_orders.record_extraction(tx, seed_user(tx, user_key), RecordExtractionInput(
        original_message=MESSAGE,
        model_name="test-model",
        raw_response={"items": 3},
        items=[
            ExtractedItemInput(original_text="5 peti biscuit chhota", extracted_name="biscuit chhota",
                               quantity=Decimal(5), unit="case", matched_product_id=BS075,
                               confidence=Decimal("0.94")),
            ExtractedItemInput(original_text="2 peti washing powder", extracted_name="washing powder",
                               quantity=Decimal(2), unit="case", matched_product_id=DT1KG,
                               confidence=Decimal("0.90"),
                               alternatives=[{"product_id": str(seed_id("product", "SKU-DT-500")), "confidence": 0.7}]),
            # unit not stated: cases or packets? -> must not be guessed
            ExtractedItemInput(original_text="5 biscuit bhej dena", extracted_name="biscuit",
                               quantity=Decimal(5), unit=None, matched_product_id=BS075,
                               confidence=Decimal("0.55")),
        ],
    ))


def confirm(tx, extraction, choices, user_key="retailer_sharma"):
    items = [
        ConfirmedItemInput(extraction_item_id=extraction.items[index].id, product_id=product,
                           quantity=Decimal(qty), unit=unit)
        for index, product, qty, unit in choices
    ]
    return ai_orders.confirm_extraction(tx, seed_user(tx, user_key), extraction.id,
                                        ConfirmExtractionInput(items=items))


def code(callable_, *args):
    with pytest.raises(AppException) as exc:
        callable_(*args)
    return exc.value.error_code


def test_extraction_is_stored_without_creating_an_order(tx):
    extraction = record(tx)
    assert extraction.extraction_status == "PENDING"
    assert extraction.original_message == MESSAGE
    assert extraction.user_id == seed_id("user", "retailer_sharma")
    assert [i.original_text for i in extraction.items][0] == "5 peti biscuit chhota"
    assert extraction.items[1].alternatives[0]["confidence"] == 0.7
    assert tx.scalar(select(func.count()).select_from(Order)) == 0


def test_unclear_unit_is_stored_as_unknown_and_flagged(tx):
    unclear = record(tx).items[2]
    assert unclear.unit is None
    assert unclear.requires_clarification is True


def test_confirmation_creates_ai_order_from_reviewed_items(tx):
    extraction = record(tx)
    # The user resolves the unclear line by stating 5 *cases* explicitly; line 2 is removed.
    order = confirm(tx, extraction, [(0, BS075, 5, "case"), (2, BS150, 1, "case")])
    assert (order.source, order.ai_extraction_id, order.status) == ("AI", extraction.id, "PENDING")
    assert sorted(i.sku for i in order.items) == ["SKU-BS-075", "SKU-BS-150"]
    assert extraction.extraction_status == "CONFIRMED"
    # The extraction keeps the AI's original output for traceability.
    assert extraction.items[2].unit is None


def test_confirmed_ai_order_still_needs_order_desk_approval(tx):
    order = confirm(tx, record(tx), [(0, BS075, 5, "case")])
    assert order.status == "PENDING" and order.approved_by is None
    orders.approve_order(tx, seed_user(tx, "order_desk"), order.id)
    assert order.status == "APPROVED"


def test_extraction_cannot_be_confirmed_twice(tx):
    extraction = record(tx)
    confirm(tx, extraction, [(0, BS075, 5, "case")])
    assert code(confirm, tx, extraction, [(0, BS075, 5, "case")]) == "INVALID_EXTRACTION_STATUS"


def test_confirmation_must_use_items_of_that_extraction(tx):
    first, second = record(tx), record(tx)
    with pytest.raises(AppException) as exc:
        ai_orders.confirm_extraction(tx, seed_user(tx, "retailer_sharma"), first.id, ConfirmExtractionInput(
            items=[ConfirmedItemInput(extraction_item_id=second.items[0].id, product_id=BS075,
                                      quantity=Decimal(1), unit="case")]))
    assert exc.value.error_code == "VALIDATION_ERROR"


def test_confirmation_refuses_a_guessed_unit(tx):
    assert code(confirm, tx, record(tx), [(2, BS075, 5, "packet")]) == "VALIDATION_ERROR"


def test_failed_confirmation_leaves_extraction_pending_and_creates_no_order(tx):
    extraction = record(tx)
    assert code(confirm, tx, extraction, [(0, TE250, 1, "case")]) == "INSUFFICIENT_STOCK"
    tx.refresh(extraction)
    assert extraction.extraction_status == "PENDING"
    assert tx.scalar(select(func.count()).select_from(Order)) == 0


def test_other_retailer_cannot_confirm_or_record_for_someone_else(tx):
    extraction = record(tx)
    assert code(confirm, tx, extraction, [(0, BS075, 5, "case")], "retailer_gupta") == "FORBIDDEN"
    with pytest.raises(AppException) as exc:
        ai_orders.record_extraction(tx, seed_user(tx, "retailer_gupta"), RecordExtractionInput(
            retailer_id=seed_id("retailer", "sharma"), original_message="x", items=[]))
    assert exc.value.error_code == "FORBIDDEN"


def test_assigned_salesman_can_confirm_for_the_retailer(tx):
    order = confirm(tx, record(tx), [(0, BS075, 5, "case")], user_key="salesman_sunil")
    assert order.created_by == seed_id("user", "salesman_sunil") and order.source == "AI"


def test_order_desk_does_not_confirm_extractions(tx):
    assert code(confirm, tx, record(tx), [(0, BS075, 5, "case")], "order_desk") == "FORBIDDEN"


def test_order_desk_correction_of_ai_order_teaches_retailer_alias(tx):
    order = confirm(tx, record(tx), [(0, BS075, 5, "case")])
    orders.correct_order_item(
        tx, seed_user(tx, "order_desk"), order.id, order.items[0].id,
        CorrectOrderItemInput(new_product_id=BS150, reason="Retailer meant 150g",
                              save_alias="biscuit chhota"),
    )
    # Sharma's existing alias "chhota biscuit" is untouched; the new wording now points to 150g.
    alias = tx.scalar(select(RetailerAlias).where(
        RetailerAlias.retailer_id == seed_id("retailer", "sharma"),
        RetailerAlias.normalized_alias == "biscuit chhota",
    ))
    assert alias.product_id == BS150
    assert tx.get(AiExtraction, order.ai_extraction_id).extraction_status == "CONFIRMED"
