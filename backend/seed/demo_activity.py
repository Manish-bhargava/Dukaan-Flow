"""Demo order activity on top of the master seed data.

Everything goes through the real services (pricing, schemes, stock/credit checks, row
locks, audit records), so the data obeys the same rules as the application:

  DF-DEMO-0001  Gupta, MANUAL           -> APPROVED at placement (3 days ago; catalogue orders need
                                           no desk review): stock deducted, movements + ORDER_DEBIT
  DF-DEMO-0002  Sharma, AI (Hinglish)    -> confirmed by retailer, then corrected by Order Desk
                                           (order_corrections row), awaiting review: PENDING
  DF-DEMO-0003  Patel via salesman       -> over available credit: CREDIT_HOLD
  DF-DEMO-0004  Jain, AI via salesman    -> REJECTED by Order Desk with reason (20 days ago; Jain is
                                           now inactive)
  Gupta AI extraction                    -> not confirmed yet: PENDING, one unclear line, no order
  Gupta payment ₹10,000                  -> PAYMENT_CREDIT ledger entry, outstanding reduced
  Detergent Powder 500g restock +40      -> RESTOCK stock movement, inventory increased

otp_verifications stays empty: OTP hashing is part of authentication (Milestone 2 Part 2).
Agrawal Traders has no user and no orders (an inactive, unassigned retailer).

Runs once: if DF-DEMO-0001 already exists, nothing is done.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import CreditAccount, CreditLedger, Inventory, Order, OrderEvent, StockMovement, User
from app.modules.ai_orders import service as ai_orders
from app.modules.ai_orders.schemas import (
    ConfirmedItemInput,
    ConfirmExtractionInput,
    ExtractedItemInput,
    RecordExtractionInput,
)
from app.modules.orders import service as orders
from app.modules.orders.schemas import CorrectOrderItemInput, CreateOrderInput, OrderItemInput
from seed.run_seed import seed_id

FIRST_DEMO_ORDER = "DF-DEMO-0001"


def _user(session: Session, key: str) -> User:
    return session.get(User, seed_id("user", key))


def _product(sku: str):
    return seed_id("product", sku)


def _cases(sku: str, quantity: int | str) -> OrderItemInput:
    return OrderItemInput(product_id=_product(sku), quantity=Decimal(quantity), unit="case")


def _number(session: Session, order: Order, n: int) -> Order:
    """Give demo orders stable, easy-to-query numbers."""
    order.order_number = f"DF-DEMO-{n:04d}"
    session.commit()
    return order


def _backdate(session: Session, order: Order, days: int, approved_after: timedelta | None = None) -> None:
    created = datetime.now(UTC) - timedelta(days=days)
    values = {"created_at": created, "updated_at": created}
    # Its history moves with it (confirmation at approved_at).
    session.execute(update(OrderEvent).where(OrderEvent.order_id == order.id)
                    .values(created_at=OrderEvent.created_at + (created - order.created_at)))
    if approved_after is not None:
        values["approved_at"] = created + approved_after
        for model in (StockMovement, CreditLedger):
            session.execute(
                update(model).where(model.order_id == order.id).values(created_at=values["approved_at"])
            )
        session.execute(update(OrderEvent).where(OrderEvent.order_id == order.id, OrderEvent.action == "CONFIRMED")
                        .values(created_at=values["approved_at"]))
    session.execute(update(Order).where(Order.id == order.id).values(**values))


def run_demo_activity(session: Session) -> dict[str, str] | None:
    """Create the demo activity. Returns {order_number: status}, or None if already present."""
    if session.scalar(select(Order.id).where(Order.order_number == FIRST_DEMO_ORDER)):
        return None

    desk = _user(session, "order_desk")
    admin = _user(session, "admin")
    sunil = _user(session, "salesman_sunil")
    deepak = _user(session, "salesman_deepak")
    sharma = _user(session, "retailer_sharma")
    gupta = _user(session, "retailer_gupta")

    # 1. Manual catalogue order, accepted by the Order Desk.
    o1 = orders.create_order(session, gupta, CreateOrderInput(
        items=[_cases("SKU-BS-075", 10), _cases("SKU-DB-150", 5)],
        remarks="Deliver before 10 am",
    ))
    _number(session, o1, 1)
    orders.approve_order(session, desk, o1.id)
    _backdate(session, o1, days=3, approved_after=timedelta(seconds=1))

    # 2. AI order: extraction -> retailer confirmation -> Order Desk correction.
    extraction = ai_orders.record_extraction(session, sharma, RecordExtractionInput(
        original_message="bhaiya 5 peti biscuit chhota, 2 peti washing powder 1 kilo, chai patti 250 wala 1 peti",
        model_name="demo-seed (no LLM call)",
        raw_response={"note": "illustrative extraction output for demo data"},
        items=[
            ExtractedItemInput(
                original_text="5 peti biscuit chhota", extracted_name="biscuit chhota",
                quantity=Decimal(5), unit="case", matched_product_id=_product("SKU-BS-075"),
                confidence=Decimal("0.950"),
                alternatives=[{"product_id": str(_product("SKU-BS-150")), "sku": "SKU-BS-150", "confidence": 0.41}],
            ),
            ExtractedItemInput(
                original_text="2 peti washing powder 1 kilo", extracted_name="washing powder 1 kilo",
                quantity=Decimal(2), unit="case", matched_product_id=_product("SKU-DT-1KG"),
                confidence=Decimal("0.910"),
                alternatives=[{"product_id": str(_product("SKU-DT-500")), "sku": "SKU-DT-500", "confidence": 0.62}],
            ),
            ExtractedItemInput(
                original_text="chai patti 250 wala 1 peti", extracted_name="chai patti 250",
                quantity=Decimal(1), unit="case", matched_product_id=_product("SKU-TE-250"),
                confidence=Decimal("0.930"),
            ),
        ],
    ))
    by_text = {item.extracted_name: item.id for item in extraction.items}
    o2 = ai_orders.confirm_extraction(session, sharma, extraction.id, ConfirmExtractionInput(
        items=[
            ConfirmedItemInput(extraction_item_id=by_text["biscuit chhota"], product_id=_product("SKU-BS-075"),
                               quantity=Decimal(5), unit="case"),
            ConfirmedItemInput(extraction_item_id=by_text["washing powder 1 kilo"],
                               product_id=_product("SKU-DT-1KG"), quantity=Decimal(2), unit="case"),
        ],
        remarks="Tea removed by retailer: out of stock",
    ))
    _number(session, o2, 2)
    detergent_line = next(i for i in o2.items if i.sku == "SKU-DT-1KG")
    orders.correct_order_item(session, desk, o2.id, detergent_line.id, CorrectOrderItemInput(
        new_quantity=Decimal(3), reason="Retailer phoned to increase washing powder to 3 cases",
    ))

    # 3. Salesman order over the retailer's available credit -> CREDIT_HOLD.
    o3 = orders.create_order(session, deepak, CreateOrderInput(
        retailer_id=seed_id("retailer", "patel"), items=[_cases("SKU-BS-150", 3)],
    ))
    _number(session, o3, 3)

    # 4. AI order captured by the salesman for Jain, rejected by Order Desk, 20 days ago.
    jain_extraction = ai_orders.record_extraction(session, sunil, RecordExtractionInput(
        retailer_id=seed_id("retailer", "jain"),
        original_message="Jain ji ke liye 20 peti noodles",
        model_name="demo-seed (no LLM call)",
        items=[ExtractedItemInput(
            original_text="20 peti noodles", extracted_name="instant noodles 70g", quantity=Decimal(20),
            unit="case", matched_product_id=_product("SKU-NS-070"), confidence=Decimal("0.900"),
        )],
    ))
    o4 = ai_orders.confirm_extraction(session, sunil, jain_extraction.id, ConfirmExtractionInput(
        items=[ConfirmedItemInput(extraction_item_id=jain_extraction.items[0].id,
                                  product_id=_product("SKU-NS-070"), quantity=Decimal(20), unit="case")],
    ))
    _number(session, o4, 4)
    orders.reject_order(session, desk, o4.id, "Duplicate of the order already taken by phone")
    _backdate(session, o4, days=20)

    # 5. AI extraction still awaiting the retailer's review (unit not stated -> clarification).
    ai_orders.record_extraction(session, gupta, RecordExtractionInput(
        original_message="5 biscuit bhej dena aur 2 peti chai patti 500",
        model_name="demo-seed (no LLM call)",
        items=[
            ExtractedItemInput(
                original_text="5 biscuit bhej dena", extracted_name="biscuit",
                quantity=Decimal(5), unit=None, matched_product_id=_product("SKU-BS-075"),
                confidence=Decimal("0.480"),
                alternatives=[
                    {"product_id": str(_product("SKU-BS-150")), "sku": "SKU-BS-150", "confidence": 0.45},
                    {"product_id": str(_product("SKU-CB-100")), "sku": "SKU-CB-100", "confidence": 0.30},
                ],
                requires_clarification=True,
            ),
            ExtractedItemInput(
                original_text="2 peti chai patti 500", extracted_name="chai patti 500",
                quantity=Decimal(2), unit="case", matched_product_id=_product("SKU-TE-500"),
                confidence=Decimal("0.920"),
            ),
        ],
    ))

    # 6. A payment received from Gupta (recorded by the admin; no payment gateway in V1).
    account = session.scalar(
        select(CreditAccount).where(CreditAccount.retailer_id == seed_id("retailer", "gupta"))
    )
    account.current_outstanding -= Decimal("10000.00")
    session.add(CreditLedger(
        retailer_id=account.retailer_id, transaction_type="PAYMENT_CREDIT", amount=Decimal("-10000.00"),
        description="Cash payment received (demo)", created_by=admin.id,
        created_at=datetime.now(UTC) - timedelta(days=1),
    ))

    # 7. Restock of a low-stock product.
    inventory = session.scalar(select(Inventory).where(Inventory.product_id == _product("SKU-DT-500")))
    inventory.stock_cases += Decimal(40)
    session.add(StockMovement(
        product_id=inventory.product_id, movement_type="RESTOCK", quantity=Decimal(40),
        reference="Purchase from Dhavala Home Care (demo)", created_by=admin.id,
    ))
    session.commit()

    return {o.order_number: o.status for o in (o1, o2, o3, o4)}
