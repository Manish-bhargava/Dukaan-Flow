import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.database.base import Base
from app.models import Category, Inventory, Product, RetailerAlias, RetailerPrice, Scheme, User
from seed.run_seed import seed_id

EXPECTED_TABLES = {
    "users", "otp_verifications", "retailers", "categories", "products", "retailer_prices",
    "schemes", "retailer_aliases", "ai_extractions", "ai_extraction_items", "orders",
    "order_items", "order_corrections", "inventory", "stock_movements", "credit_accounts",
    "credit_ledger",
}


def test_migration_creates_all_expected_tables(test_engine):
    tables = set(inspect(test_engine).get_table_names())
    assert EXPECTED_TABLES <= tables
    assert tables - EXPECTED_TABLES == {"alembic_version"}


def test_migrated_schema_matches_models(test_engine):
    with test_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def _assert_rejected(session: Session, obj) -> None:
    session.add(obj)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_negative_stock_is_rejected(db_session):
    db_session.get(Inventory, seed_id("inventory", "SKU-BS-075")).stock_cases = Decimal("-1")
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_duplicate_sku_is_rejected(db_session):
    _assert_rejected(db_session, Product(
        sku="SKU-BS-075", name="Duplicate", brand="X",
        category_id=seed_id("category", "Biscuits"), pack_size="75g",
        units_per_case=Decimal(96), base_unit="piece", order_unit="case", gst_rate=Decimal(5),
    ))


def test_duplicate_normalized_alias_for_same_retailer_is_rejected(db_session):
    _assert_rejected(db_session, RetailerAlias(
        retailer_id=seed_id("retailer", "sharma"), product_id=seed_id("product", "SKU-BS-150"),
        alias="Chhota Biscuit", normalized_alias="chhota biscuit",
    ))


def test_retailer_user_must_be_linked_to_a_retailer(db_session):
    _assert_rejected(db_session, User(name="No Shop", phone="9111111111", role="RETAILER"))


def test_invalid_role_is_rejected(db_session):
    _assert_rejected(db_session, User(name="Ghost", phone="9111111112", role="SUPERUSER"))


def test_scheme_benefit_must_match_scheme_type(db_session):
    _assert_rejected(db_session, Scheme(
        product_id=seed_id("product", "SKU-TE-500"), scheme_type="FREE_GOODS",
        min_quantity=Decimal(5), discount_percentage=Decimal(3),
        starts_at=datetime.now(UTC),
    ))


def test_price_for_unknown_retailer_violates_foreign_key(db_session):
    _assert_rejected(db_session, RetailerPrice(
        retailer_id=uuid.uuid4(), product_id=seed_id("product", "SKU-BS-075"),
        dealer_price=Decimal("8.00"), price_basis="PIECE", tax_inclusive=False,
        effective_from=datetime.now(UTC),
    ))


def test_duplicate_category_name_is_rejected(db_session):
    _assert_rejected(db_session, Category(name="Biscuits"))


def test_user_email_must_be_unique(db_session):
    _assert_rejected(db_session, User(
        name="Copy", phone="9111111113", role="ADMIN", email="sharma.kirana@example.com"
    ))


def test_user_email_must_be_stored_normalized(db_session):
    _assert_rejected(db_session, User(name="Caps", phone="9111111114", role="ADMIN", email="Caps@Example.com"))


def test_user_email_is_optional(db_session):
    db_session.add(User(name="No Email", phone="9111111115", role="ADMIN"))
    db_session.flush()
    db_session.rollback()
