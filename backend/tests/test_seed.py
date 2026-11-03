from decimal import Decimal

from sqlalchemy import func, select

from app.models import (
    CreditAccount,
    CreditLedger,
    Inventory,
    Product,
    Retailer,
    RetailerPrice,
    StockMovement,
    User,
)
from seed.run_seed import seed_id

EXPECTED_TOTALS = {
    "users": 6,
    "retailers": 5,
    "categories": 4,
    "products": 10,
    "retailer_prices": 51,
    "schemes": 3,
    "inventory": 10,
    "stock_movements": 9,
    "credit_accounts": 5,
    "credit_ledger": 4,
    "retailer_aliases": 6,
}


def test_first_seed_run_inserts_all_records(seed_runs):
    first, _ = seed_runs
    assert {table: inserted for table, (inserted, _) in first.items()} == EXPECTED_TOTALS


def test_second_seed_run_creates_no_duplicates(seed_runs):
    _, second = seed_runs
    assert all(inserted == 0 for inserted, _ in second.values())
    assert {table: total for table, (_, total) in second.items()} == EXPECTED_TOTALS


def test_retailer_user_is_linked_to_its_retailer(db_session):
    user = db_session.scalar(select(User).where(User.phone == "9000000101"))
    assert user.role == "RETAILER"
    assert user.retailer.shop_name == "Sharma Kirana Store"
    assert user in user.retailer.users


def test_assigned_salesmen_have_salesman_role(db_session):
    retailers = db_session.scalars(select(Retailer)).all()
    assigned = [r for r in retailers if r.assigned_salesman is not None]
    assert len(assigned) == 4
    assert all(r.assigned_salesman.role == "SALESMAN" for r in assigned)
    assert db_session.get(Retailer, seed_id("retailer", "agrawal")).assigned_salesman is None


def test_every_retailer_has_a_credit_account_and_price_for_every_product(db_session):
    product_count = db_session.scalar(select(func.count()).select_from(Product))
    for retailer in db_session.scalars(select(Retailer)):
        assert retailer.credit_account is not None
        current = [p for p in retailer.prices if p.effective_to is None]
        assert len(current) == product_count


def test_credit_ledger_explains_outstanding_balance(db_session):
    for account in db_session.scalars(select(CreditAccount)):
        ledger_total = db_session.scalar(
            select(func.coalesce(func.sum(CreditLedger.amount), 0)).where(
                CreditLedger.retailer_id == account.retailer_id
            )
        )
        assert ledger_total == account.current_outstanding


def test_stock_movements_explain_inventory(db_session):
    for inventory in db_session.scalars(select(Inventory)):
        movement_total = db_session.scalar(
            select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
                StockMovement.product_id == inventory.product_id
            )
        )
        assert movement_total == inventory.stock_cases


def test_sample_products_match_assignment_data(db_session):
    expected = {
        "SKU-BS-075": (Decimal("96"), Decimal("8.10"), Decimal("340")),
        "SKU-DT-1KG": (Decimal("20"), Decimal("101.50"), Decimal("85")),
        "SKU-TE-250": (Decimal("40"), Decimal("118.00"), Decimal("0")),
    }
    sharma = seed_id("retailer", "sharma")
    for sku, (per_case, price, stock) in expected.items():
        product = db_session.scalar(select(Product).where(Product.sku == sku))
        current_price = db_session.scalar(
            select(RetailerPrice.dealer_price).where(
                RetailerPrice.retailer_id == sharma,
                RetailerPrice.product_id == product.id,
                RetailerPrice.effective_to.is_(None),
            )
        )
        assert (product.units_per_case, current_price, product.inventory.stock_cases) == (
            per_case,
            price,
            stock,
        )


# ---------------------------------------------------------------- demo activity


def assert_books_balance(session):
    """Business invariants that must hold after any sequence of operations."""
    from sqlalchemy import text

    unbalanced_credit = session.execute(text(
        "SELECT a.retailer_id FROM credit_accounts a LEFT JOIN credit_ledger l ON l.retailer_id = a.retailer_id"
        " GROUP BY a.retailer_id, a.current_outstanding HAVING COALESCE(SUM(l.amount), 0) <> a.current_outstanding"
    )).all()
    unbalanced_stock = session.execute(text(
        "SELECT i.product_id FROM inventory i LEFT JOIN stock_movements m ON m.product_id = i.product_id"
        " GROUP BY i.product_id, i.stock_cases HAVING COALESCE(SUM(m.quantity), 0) <> i.stock_cases"
    )).all()
    wrong_totals = session.execute(text(
        "SELECT o.order_number FROM orders o JOIN order_items i ON i.order_id = o.id GROUP BY o.id"
        " HAVING SUM(i.line_total) <> o.grand_total OR SUM(i.taxable_amount) <> o.taxable_amount"
        " OR SUM(i.gst_amount) <> o.gst_amount OR SUM(i.discount_amount) <> o.discount_total"
    )).all()
    assert (unbalanced_credit, unbalanced_stock, wrong_totals) == ([], [], [])


def test_demo_activity_covers_every_status_and_keeps_books_balanced(tx):
    from app.models import AiExtraction, Order, OrderCorrection
    from seed.demo_activity import run_demo_activity

    assert run_demo_activity(tx) == {
        "DF-DEMO-0001": "APPROVED",
        "DF-DEMO-0002": "PENDING",
        "DF-DEMO-0003": "CREDIT_HOLD",
        "DF-DEMO-0004": "REJECTED",
    }
    assert {o.source for o in tx.scalars(select(Order))} == {"MANUAL", "AI", "SALESMAN"}
    assert sorted(e.extraction_status for e in tx.scalars(select(AiExtraction))) == ["CONFIRMED", "PENDING"]
    assert tx.scalar(select(func.count()).select_from(OrderCorrection)) == 1
    assert_books_balance(tx)

    # A second run creates nothing.
    orders_before = tx.scalar(select(func.count()).select_from(Order))
    assert run_demo_activity(tx) is None
    assert tx.scalar(select(func.count()).select_from(Order)) == orders_before


def test_master_seed_books_balance(db_session):
    assert_books_balance(db_session)
