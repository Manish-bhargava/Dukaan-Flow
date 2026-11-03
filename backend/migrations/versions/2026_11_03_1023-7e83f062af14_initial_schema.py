"""initial schema

Revision ID: 7e83f062af14
Revises: 
Create Date: 2026-11-03 10:23:15.291281

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7e83f062af14'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('categories',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories')),
    sa.UniqueConstraint('name', name=op.f('uq_categories_name'))
    )
    op.create_table('otp_verifications',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('phone', sa.String(length=15), nullable=False),
    sa.Column('otp_hash', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('attempts >= 0', name=op.f('ck_otp_verifications_attempts_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_otp_verifications'))
    )
    op.create_index(op.f('ix_otp_verifications_phone'), 'otp_verifications', ['phone'], unique=False)
    op.create_table('retailers',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('shop_name', sa.String(length=200), nullable=False),
    sa.Column('owner_name', sa.String(length=150), nullable=False),
    sa.Column('phone', sa.String(length=15), nullable=False),
    sa.Column('address', sa.Text(), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('gstin', sa.String(length=20), nullable=True),
    sa.Column('assigned_salesman_id', sa.Uuid(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_retailers'))
    )
    op.create_index(op.f('ix_retailers_assigned_salesman_id'), 'retailers', ['assigned_salesman_id'], unique=False)
    op.create_table('credit_accounts',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('retailer_id', sa.Uuid(), nullable=False),
    sa.Column('credit_limit', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('current_outstanding', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('credit_limit >= 0', name=op.f('ck_credit_accounts_credit_limit_non_negative')),
    sa.ForeignKeyConstraint(['retailer_id'], ['retailers.id'], name=op.f('fk_credit_accounts_retailer_id_retailers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_credit_accounts')),
    sa.UniqueConstraint('retailer_id', name=op.f('uq_credit_accounts_retailer_id'))
    )
    op.create_table('products',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('sku', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('brand', sa.String(length=100), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=False),
    sa.Column('pack_size', sa.String(length=100), nullable=False),
    sa.Column('units_per_case', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('base_unit', sa.String(length=30), nullable=False),
    sa.Column('order_unit', sa.String(length=30), nullable=False),
    sa.Column('gst_rate', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('image_url', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('gst_rate >= 0 AND gst_rate <= 100', name=op.f('ck_products_gst_rate_range')),
    sa.CheckConstraint('units_per_case > 0', name=op.f('ck_products_units_per_case_positive')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_products_category_id_categories')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_products')),
    sa.UniqueConstraint('sku', name=op.f('uq_products_sku'))
    )
    op.create_index(op.f('ix_products_category_id'), 'products', ['category_id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('phone', sa.String(length=15), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('role', sa.String(length=30), nullable=False),
    sa.Column('retailer_id', sa.Uuid(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role <> 'RETAILER' OR retailer_id IS NOT NULL", name=op.f('ck_users_retailer_link')),
    sa.CheckConstraint("role IN ('RETAILER', 'SALESMAN', 'ORDER_DESK', 'ADMIN')", name=op.f('ck_users_role_valid')),
    sa.ForeignKeyConstraint(['retailer_id'], ['retailers.id'], name=op.f('fk_users_retailer_id_retailers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('phone', name=op.f('uq_users_phone'))
    )
    op.create_index(op.f('ix_users_retailer_id'), 'users', ['retailer_id'], unique=False)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)
    # retailers.assigned_salesman_id -> users.id is added after both tables exist
    # (users.retailer_id -> retailers.id makes the two tables reference each other).
    op.create_foreign_key(op.f('fk_retailers_assigned_salesman_id_users'), 'retailers', 'users', ['assigned_salesman_id'], ['id'])
    op.create_table('ai_extractions',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('retailer_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('original_message', sa.Text(), nullable=False),
    sa.Column('extraction_status', sa.String(length=30), server_default='PENDING', nullable=False),
    sa.Column('model_name', sa.String(length=100), nullable=True),
    sa.Column('raw_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("extraction_status IN ('PENDING', 'REVIEWED', 'CONFIRMED', 'FAILED')", name=op.f('ck_ai_extractions_status_valid')),
    sa.ForeignKeyConstraint(['retailer_id'], ['retailers.id'], name=op.f('fk_ai_extractions_retailer_id_retailers')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ai_extractions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_extractions'))
    )
    op.create_index(op.f('ix_ai_extractions_retailer_id'), 'ai_extractions', ['retailer_id'], unique=False)
    op.create_table('inventory',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('stock_cases', sa.Numeric(precision=12, scale=3), server_default='0', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('stock_cases >= 0', name=op.f('ck_inventory_stock_non_negative')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_inventory_product_id_products')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory')),
    sa.UniqueConstraint('product_id', name=op.f('uq_inventory_product_id'))
    )
    op.create_table('retailer_aliases',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('retailer_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('alias', sa.String(length=200), nullable=False),
    sa.Column('normalized_alias', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_retailer_aliases_product_id_products')),
    sa.ForeignKeyConstraint(['retailer_id'], ['retailers.id'], name=op.f('fk_retailer_aliases_retailer_id_retailers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_retailer_aliases')),
    sa.UniqueConstraint('retailer_id', 'normalized_alias', name=op.f('uq_retailer_aliases_retailer_id_normalized_alias'))
    )
    op.create_table('retailer_prices',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('retailer_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('dealer_price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('price_basis', sa.String(length=20), nullable=False),
    sa.Column('tax_inclusive', sa.Boolean(), nullable=False),
    sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("price_basis IN ('CASE', 'PIECE')", name=op.f('ck_retailer_prices_price_basis_valid')),
    sa.CheckConstraint('dealer_price >= 0', name=op.f('ck_retailer_prices_dealer_price_non_negative')),
    sa.CheckConstraint('effective_to IS NULL OR effective_to > effective_from', name=op.f('ck_retailer_prices_effective_range')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_retailer_prices_product_id_products')),
    sa.ForeignKeyConstraint(['retailer_id'], ['retailers.id'], name=op.f('fk_retailer_prices_retailer_id_retailers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_retailer_prices'))
    )
    op.create_index('ix_retailer_prices_retailer_id_product_id', 'retailer_prices', ['retailer_id', 'product_id'], unique=False)
    op.create_table('schemes',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('scheme_type', sa.String(length=30), nullable=False),
    sa.Column('min_quantity', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('free_quantity', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('discount_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(scheme_type = 'FREE_GOODS' AND free_quantity > 0 AND discount_percentage IS NULL) OR (scheme_type = 'SLAB_DISCOUNT' AND discount_percentage > 0 AND discount_percentage <= 100 AND free_quantity IS NULL)", name=op.f('ck_schemes_benefit_matches_type')),
    sa.CheckConstraint("scheme_type IN ('FREE_GOODS', 'SLAB_DISCOUNT')", name=op.f('ck_schemes_scheme_type_valid')),
    sa.CheckConstraint('ends_at IS NULL OR ends_at > starts_at', name=op.f('ck_schemes_date_range')),
    sa.CheckConstraint('min_quantity > 0', name=op.f('ck_schemes_min_quantity_positive')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_schemes_product_id_products')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_schemes'))
    )
    op.create_index('ix_schemes_product_id_is_active', 'schemes', ['product_id', 'is_active'], unique=False)
    op.create_table('ai_extraction_items',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('extraction_id', sa.Uuid(), nullable=False),
    sa.Column('original_text', sa.Text(), nullable=False),
    sa.Column('extracted_name', sa.String(length=200), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('unit', sa.String(length=30), nullable=True),
    sa.Column('matched_product_id', sa.Uuid(), nullable=True),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), server_default='0', nullable=False),
    sa.Column('alternatives', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('requires_clarification', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('confidence >= 0 AND confidence <= 1', name=op.f('ck_ai_extraction_items_confidence_range')),
    sa.CheckConstraint('quantity IS NULL OR quantity > 0', name=op.f('ck_ai_extraction_items_quantity_positive')),
    sa.ForeignKeyConstraint(['extraction_id'], ['ai_extractions.id'], name=op.f('fk_ai_extraction_items_extraction_id_ai_extractions')),
    sa.ForeignKeyConstraint(['matched_product_id'], ['products.id'], name=op.f('fk_ai_extraction_items_matched_product_id_products')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_extraction_items'))
    )
    op.create_index(op.f('ix_ai_extraction_items_extraction_id'), 'ai_extraction_items', ['extraction_id'], unique=False)
    op.create_table('orders',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('order_number', sa.String(length=50), nullable=False),
    sa.Column('retailer_id', sa.Uuid(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('ai_extraction_id', sa.Uuid(), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=30), server_default='PENDING', nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
    sa.Column('discount_total', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
    sa.Column('taxable_amount', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
    sa.Column('gst_amount', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
    sa.Column('grand_total', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('approved_by', sa.Uuid(), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('MANUAL', 'AI', 'SALESMAN')", name=op.f('ck_orders_source_valid')),
    sa.CheckConstraint("status IN ('PENDING', 'CREDIT_HOLD', 'APPROVED', 'REJECTED')", name=op.f('ck_orders_status_valid')),
    sa.CheckConstraint('subtotal >= 0 AND discount_total >= 0 AND taxable_amount >= 0 AND gst_amount >= 0 AND grand_total >= 0', name=op.f('ck_orders_amounts_non_negative')),
    sa.ForeignKeyConstraint(['ai_extraction_id'], ['ai_extractions.id'], name=op.f('fk_orders_ai_extraction_id_ai_extractions')),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], name=op.f('fk_orders_approved_by_users')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_orders_created_by_users')),
    sa.ForeignKeyConstraint(['retailer_id'], ['retailers.id'], name=op.f('fk_orders_retailer_id_retailers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_orders')),
    sa.UniqueConstraint('order_number', name=op.f('uq_orders_order_number'))
    )
    op.create_index('ix_orders_retailer_id_created_at', 'orders', ['retailer_id', 'created_at'], unique=False)
    op.create_index('ix_orders_status_created_at', 'orders', ['status', 'created_at'], unique=False)
    op.create_table('credit_ledger',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('retailer_id', sa.Uuid(), nullable=False),
    sa.Column('order_id', sa.Uuid(), nullable=True),
    sa.Column('transaction_type', sa.String(length=30), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("transaction_type IN ('ORDER_DEBIT', 'PAYMENT_CREDIT', 'ADJUSTMENT')", name=op.f('ck_credit_ledger_type_valid')),
    sa.CheckConstraint('amount <> 0', name=op.f('ck_credit_ledger_amount_non_zero')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_credit_ledger_created_by_users')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_credit_ledger_order_id_orders')),
    sa.ForeignKeyConstraint(['retailer_id'], ['retailers.id'], name=op.f('fk_credit_ledger_retailer_id_retailers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_credit_ledger'))
    )
    op.create_index(op.f('ix_credit_ledger_retailer_id'), 'credit_ledger', ['retailer_id'], unique=False)
    op.create_table('order_items',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('order_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('product_name', sa.String(length=200), nullable=False),
    sa.Column('sku', sa.String(length=50), nullable=False),
    sa.Column('paid_quantity', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('free_quantity', sa.Numeric(precision=12, scale=3), server_default='0', nullable=False),
    sa.Column('price_basis', sa.String(length=20), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('discount_percentage', sa.Numeric(precision=5, scale=2), server_default='0', nullable=False),
    sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
    sa.Column('gst_rate', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('taxable_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('gst_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('line_total', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.CheckConstraint("price_basis IN ('CASE', 'PIECE')", name=op.f('ck_order_items_price_basis_valid')),
    sa.CheckConstraint('discount_amount >= 0 AND taxable_amount >= 0 AND gst_amount >= 0 AND line_total >= 0', name=op.f('ck_order_items_amounts_non_negative')),
    sa.CheckConstraint('discount_percentage >= 0 AND discount_percentage <= 100', name=op.f('ck_order_items_discount_range')),
    sa.CheckConstraint('free_quantity >= 0', name=op.f('ck_order_items_free_quantity_non_negative')),
    sa.CheckConstraint('gst_rate >= 0 AND gst_rate <= 100', name=op.f('ck_order_items_gst_rate_range')),
    sa.CheckConstraint('paid_quantity > 0', name=op.f('ck_order_items_paid_quantity_positive')),
    sa.CheckConstraint('unit_price >= 0', name=op.f('ck_order_items_unit_price_non_negative')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_items_order_id_orders')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_order_items_product_id_products')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_items'))
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_table('stock_movements',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('order_id', sa.Uuid(), nullable=True),
    sa.Column('movement_type', sa.String(length=30), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('reference', sa.String(length=200), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("movement_type IN ('ORDER_DEDUCTION', 'RESTOCK', 'ADJUSTMENT')", name=op.f('ck_stock_movements_type_valid')),
    sa.CheckConstraint('quantity <> 0', name=op.f('ck_stock_movements_quantity_non_zero')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_stock_movements_created_by_users')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_stock_movements_order_id_orders')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_stock_movements_product_id_products')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_movements'))
    )
    op.create_index(op.f('ix_stock_movements_product_id'), 'stock_movements', ['product_id'], unique=False)
    op.create_table('order_corrections',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('order_item_id', sa.Uuid(), nullable=False),
    sa.Column('old_product_id', sa.Uuid(), nullable=True),
    sa.Column('new_product_id', sa.Uuid(), nullable=False),
    sa.Column('old_quantity', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('new_quantity', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('corrected_by', sa.Uuid(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('new_quantity > 0', name=op.f('ck_order_corrections_new_quantity_positive')),
    sa.CheckConstraint('old_quantity >= 0', name=op.f('ck_order_corrections_old_quantity_non_negative')),
    sa.ForeignKeyConstraint(['corrected_by'], ['users.id'], name=op.f('fk_order_corrections_corrected_by_users')),
    sa.ForeignKeyConstraint(['new_product_id'], ['products.id'], name=op.f('fk_order_corrections_new_product_id_products')),
    sa.ForeignKeyConstraint(['old_product_id'], ['products.id'], name=op.f('fk_order_corrections_old_product_id_products')),
    sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id'], name=op.f('fk_order_corrections_order_item_id_order_items')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_corrections'))
    )
    op.create_index(op.f('ix_order_corrections_order_item_id'), 'order_corrections', ['order_item_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_order_corrections_order_item_id'), table_name='order_corrections')
    op.drop_table('order_corrections')
    op.drop_index(op.f('ix_stock_movements_product_id'), table_name='stock_movements')
    op.drop_table('stock_movements')
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_index(op.f('ix_credit_ledger_retailer_id'), table_name='credit_ledger')
    op.drop_table('credit_ledger')
    op.drop_index('ix_orders_status_created_at', table_name='orders')
    op.drop_index('ix_orders_retailer_id_created_at', table_name='orders')
    op.drop_table('orders')
    op.drop_index(op.f('ix_ai_extraction_items_extraction_id'), table_name='ai_extraction_items')
    op.drop_table('ai_extraction_items')
    op.drop_index('ix_schemes_product_id_is_active', table_name='schemes')
    op.drop_table('schemes')
    op.drop_index('ix_retailer_prices_retailer_id_product_id', table_name='retailer_prices')
    op.drop_table('retailer_prices')
    op.drop_table('retailer_aliases')
    op.drop_table('inventory')
    op.drop_index(op.f('ix_ai_extractions_retailer_id'), table_name='ai_extractions')
    op.drop_table('ai_extractions')
    op.drop_constraint(op.f('fk_retailers_assigned_salesman_id_users'), 'retailers', type_='foreignkey')
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_index(op.f('ix_users_retailer_id'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_products_category_id'), table_name='products')
    op.drop_table('products')
    op.drop_table('credit_accounts')
    op.drop_index(op.f('ix_retailers_assigned_salesman_id'), table_name='retailers')
    op.drop_table('retailers')
    op.drop_index(op.f('ix_otp_verifications_phone'), table_name='otp_verifications')
    op.drop_table('otp_verifications')
    op.drop_table('categories')
