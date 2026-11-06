"""Row-level locking under truly concurrent transactions.

Each test starts several threads, each with its own database connection and transaction,
and releases them at the same moment with a barrier. Row locks only matter across
transactions, so these tests commit for real; the `world` fixture records the state before
the test and restores it afterwards.
"""

import threading
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy import Engine, delete, select, text, update
from sqlalchemy.orm import Session

from app.core.constants import OrderSource
from app.exceptions.base import AppException
from app.models import (
    CreditAccount,
    CreditLedger,
    Inventory,
    Order,
    OrderCorrection,
    OrderEvent,
    OrderItem,
    StockMovement,
    User,
)
from app.modules.orders import service as orders
from app.modules.orders.schemas import CorrectOrderItemInput, OrderItemInput
from seed.run_seed import seed_id
from tests.test_seed import assert_books_balance

BS075, DB150, DT1KG, DW500 = (seed_id("product", s) for s in ("SKU-BS-075", "SKU-DB-150", "SKU-DT-1KG", "SKU-DW-500"))
SHARMA, GUPTA, JAIN = (seed_id("retailer", k) for k in ("sharma", "gupta", "jain"))
# Orders are placed by the retailers' salesman as AI-captured orders, so they wait for the
# Order Desk (catalogue orders are confirmed at placement and never reach these races).
ORDERING_USER = {SHARMA: "salesman_sunil", GUPTA: "salesman_sunil", JAIN: "salesman_sunil"}


class World:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.order_ids: list = []

    def order(self, retailer_id, *lines: tuple) -> object:
        """Create and commit an order; lines are (product_id, cases)."""
        with Session(self.engine) as s:
            user = s.get(User, seed_id("user", ORDERING_USER[retailer_id]))
            retailer = orders.resolve_ordering_retailer(s, user, retailer_id)
            order = orders.build_order(
                s, user, retailer,
                [OrderItemInput(product_id=p, quantity=Decimal(q), unit="case") for p, q in lines],
                source=OrderSource.AI,
            )
            s.commit()
            self.order_ids.append(order.id)
            return order.id

    def stock(self, product_id) -> Decimal:
        with Session(self.engine) as s:
            return s.scalar(select(Inventory.stock_cases).where(Inventory.product_id == product_id))

    def outstanding(self, retailer_id) -> Decimal:
        with Session(self.engine) as s:
            return s.scalar(select(CreditAccount.current_outstanding).where(CreditAccount.retailer_id == retailer_id))

    def status(self, order_id) -> str:
        with Session(self.engine) as s:
            return s.get(Order, order_id).status

    def assert_books_balance(self):
        with Session(self.engine) as s:
            assert_books_balance(s)
            assert s.scalar(select(Inventory).where(Inventory.stock_cases < 0)) is None


@pytest.fixture
def world(test_engine, seed_runs):
    with Session(test_engine) as s:
        stock_before = dict(s.execute(select(Inventory.product_id, Inventory.stock_cases)).all())
        credit_before = dict(s.execute(select(CreditAccount.retailer_id, CreditAccount.current_outstanding)).all())
    w = World(test_engine)
    yield w
    with Session(test_engine) as s:
        ids = w.order_ids
        item_ids = select(OrderItem.id).where(OrderItem.order_id.in_(ids))
        s.execute(delete(OrderCorrection).where(OrderCorrection.order_item_id.in_(item_ids)))
        s.execute(delete(StockMovement).where(StockMovement.order_id.in_(ids)))
        s.execute(delete(CreditLedger).where(CreditLedger.order_id.in_(ids)))
        s.execute(delete(OrderEvent).where(OrderEvent.order_id.in_(ids)))
        s.execute(delete(OrderItem).where(OrderItem.order_id.in_(ids)))
        s.execute(delete(Order).where(Order.id.in_(ids)))
        for product_id, stock in stock_before.items():
            s.execute(update(Inventory).where(Inventory.product_id == product_id).values(stock_cases=stock))
        for retailer_id, outstanding in credit_before.items():
            s.execute(update(CreditAccount).where(CreditAccount.retailer_id == retailer_id)
                      .values(current_outstanding=outstanding))
        s.commit()


def race(engine: Engine, *actions: Callable[[Session], object]) -> list[str]:
    """Run each action in its own thread/transaction, all released at once.
    Returns "OK" or the AppException error code per action, in order."""
    barrier = threading.Barrier(len(actions))
    results: list[str] = [""] * len(actions)

    def run(index: int, action) -> None:
        with Session(engine) as session:
            barrier.wait()
            try:
                action(session)
                results[index] = "OK"
            except AppException as exc:
                results[index] = exc.error_code
            except Exception as exc:  # e.g. a deadlock would surface here
                results[index] = f"{type(exc).__name__}: {exc}"

    threads = [threading.Thread(target=run, args=(i, a)) for i, a in enumerate(actions)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a transaction never finished"
    return results


def approve(order_id, reason=None):
    def action(s: Session):
        orders.approve_order(s, s.get(User, seed_id("user", "order_desk")), order_id, reason)
    return action


def reject(order_id):
    def action(s: Session):
        orders.reject_order(s, s.get(User, seed_id("user", "order_desk")), order_id, "Race test")
    return action


# ---------------------------------------------------------------- stock


def test_two_orders_competing_for_the_same_stock(world):
    a = world.order(GUPTA, (DW500, 5))
    b = world.order(JAIN, (DW500, 5))  # 5 + 5 > 8 in stock; each alone fits

    assert sorted(race(world.engine, approve(a), approve(b))) == ["INSUFFICIENT_STOCK", "OK"]
    assert world.stock(DW500) == 3
    world.assert_books_balance()


def test_many_concurrent_approvals_never_oversell(world):
    ids = [world.order(r, (DW500, 2)) for r in (GUPTA, GUPTA, GUPTA, JAIN, JAIN)]  # 10 cases wanted, 8 in stock

    results = race(world.engine, *(approve(i) for i in ids))

    assert sorted(results) == ["INSUFFICIENT_STOCK", "OK", "OK", "OK", "OK"]
    assert world.stock(DW500) == 0
    assert [world.status(i) for i in ids].count("APPROVED") == 4
    world.assert_books_balance()


# ---------------------------------------------------------------- credit


def test_concurrent_approvals_cannot_overspend_credit(world):
    # Sharma has 15,000 available. Each order fits alone, both together do not, and they
    # use different products, so only the credit-account lock can serialise them.
    a = world.order(SHARMA, (DT1KG, 4))   # 9,581.60
    b = world.order(SHARMA, (BS075, 7))   # 5,715.36

    results = race(world.engine, approve(a), approve(b))

    assert sorted(results) == ["CREDIT_LIMIT_EXCEEDED", "OK"]
    refused = a if results[0] != "OK" else b
    assert world.status(refused) == "CREDIT_HOLD"
    assert world.outstanding(SHARMA) <= Decimal("50000.00")  # never above the limit
    world.assert_books_balance()


# ---------------------------------------------------------------- same order


def test_same_order_approved_twice_at_once(world):
    order_id = world.order(GUPTA, (DW500, 2))

    assert sorted(race(world.engine, approve(order_id), approve(order_id))) == ["INVALID_ORDER_STATUS", "OK"]
    assert world.stock(DW500) == 6
    world.assert_books_balance()


def test_approve_and_reject_race_has_one_winner(world):
    order_id = world.order(GUPTA, (DW500, 2))

    results = race(world.engine, approve(order_id), reject(order_id))

    assert sorted(results) == ["INVALID_ORDER_STATUS", "OK"]
    if results[0] == "OK":
        assert world.status(order_id) == "APPROVED" and world.stock(DW500) == 6
    else:
        assert world.status(order_id) == "REJECTED" and world.stock(DW500) == 8
    world.assert_books_balance()


def test_correction_and_approval_race_stays_consistent(world):
    order_id = world.order(GUPTA, (BS075, 10))

    def correct(s: Session):
        order = s.get(Order, order_id)
        orders.correct_order_item(s, s.get(User, seed_id("user", "order_desk")), order_id,
                                  order.items[0].id, CorrectOrderItemInput(new_quantity=Decimal(20), reason="Race test"))

    results = race(world.engine, approve(order_id), correct)

    # Either the approval won (correction refused), or the correction ran first and the
    # approval deducted the corrected quantity. Never a mix of the two.
    assert results[0] == "OK"
    deducted = Decimal(340) - world.stock(BS075)
    assert deducted == (Decimal(22) if results[1] == "OK" else Decimal(11))
    if results[1] != "OK":
        assert results[1] == "INVALID_ORDER_STATUS"
    world.assert_books_balance()


# ---------------------------------------------------------------- deadlocks and waiting


def test_opposite_product_order_does_not_deadlock(world):
    # Items listed in opposite order: without a fixed lock order these could deadlock.
    for _ in range(5):
        a = world.order(GUPTA, (BS075, 1), (DB150, 1))
        b = world.order(JAIN, (DB150, 1), (BS075, 1))
        assert race(world.engine, approve(a), approve(b)) == ["OK", "OK"]
    world.assert_books_balance()


def test_approval_waits_for_a_locked_inventory_row(world):
    order_id = world.order(GUPTA, (DW500, 5))
    result: list[str] = []

    with world.engine.connect() as holder:
        # Another transaction locks the stock row and changes it, without committing yet.
        holder.execute(text("SELECT 1 FROM inventory WHERE product_id = :p FOR UPDATE"), {"p": DW500})
        holder.execute(update(Inventory).where(Inventory.product_id == DW500).values(stock_cases=1))

        thread = threading.Thread(target=lambda: result.extend(race(world.engine, approve(order_id))))
        thread.start()
        thread.join(timeout=1.0)
        assert thread.is_alive(), "approval should be blocked by the row lock"

        waiting = holder.execute(text(
            "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND datname = current_database()"
        )).scalar()
        assert waiting == 1

        holder.commit()  # release the lock with stock = 1

    thread.join(timeout=10)
    # The approval resumed and saw the committed value, not a stale one.
    assert result == ["INSUFFICIENT_STOCK"]
    assert world.status(order_id) == "PENDING"
