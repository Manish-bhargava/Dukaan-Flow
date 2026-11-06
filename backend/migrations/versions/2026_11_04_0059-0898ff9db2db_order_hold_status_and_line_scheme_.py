"""order hold status and line scheme snapshot

Revision ID: 0898ff9db2db
Revises: 6011b61e50cc
Create Date: 2026-11-04 00:59:58.063888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0898ff9db2db'
down_revision: Union[str, Sequence[str], None] = '6011b61e50cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_STATUSES = "'PENDING', 'CREDIT_HOLD', 'APPROVED', 'REJECTED'"
NEW_STATUSES = "'PENDING', 'CREDIT_HOLD', 'ON_HOLD', 'APPROVED', 'REJECTED'"


def upgrade() -> None:
    # Orders: Order Desk can put an order ON_HOLD with a reason.
    op.add_column("orders", sa.Column("hold_reason", sa.Text(), nullable=True))
    op.drop_constraint(op.f("ck_orders_status_valid"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_status_valid"), "orders", f"status IN ({NEW_STATUSES})")

    # Order items: GST treatment and applied-scheme snapshots.
    op.add_column("order_items", sa.Column("tax_inclusive", sa.Boolean(), nullable=True))
    op.add_column("order_items", sa.Column("scheme_id", sa.Uuid(), nullable=True))
    op.add_column("order_items", sa.Column("scheme_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key(
        op.f("fk_order_items_scheme_id_schemes"), "order_items", "schemes", ["scheme_id"], ["id"]
    )

    # Backfill existing lines from the price/scheme that was effective when the order was
    # placed, only where it matches the stored snapshot exactly; anything else stays NULL.
    op.execute("""
        UPDATE order_items oi SET tax_inclusive = rp.tax_inclusive
        FROM orders o, retailer_prices rp
        WHERE oi.order_id = o.id AND rp.retailer_id = o.retailer_id AND rp.product_id = oi.product_id
          AND rp.effective_from <= o.created_at
          AND (rp.effective_to IS NULL OR rp.effective_to > o.created_at)
          AND rp.dealer_price = oi.unit_price AND rp.price_basis = oi.price_basis
    """)
    op.execute("""
        UPDATE order_items oi SET
          scheme_id = s.id,
          scheme_snapshot = jsonb_build_object(
            'scheme_id', s.id::text, 'scheme_type', s.scheme_type,
            'min_quantity', s.min_quantity::text,
            'free_quantity', oi.free_quantity::text,
            'discount_percentage', s.discount_percentage::text,
            'description', CASE s.scheme_type
              WHEN 'FREE_GOODS' THEN 'Buy ' || trim_scale(s.min_quantity) || ' get '
                                     || trim_scale(s.free_quantity) || ' free'
              ELSE trim_scale(s.discount_percentage) || '% off on ' || trim_scale(s.min_quantity) || '+'
            END)
        FROM orders o, schemes s
        WHERE oi.order_id = o.id AND s.product_id = oi.product_id
          AND s.starts_at <= o.created_at AND (s.ends_at IS NULL OR s.ends_at > o.created_at)
          AND ((s.scheme_type = 'FREE_GOODS' AND oi.free_quantity > 0)
               OR (s.scheme_type = 'SLAB_DISCOUNT' AND oi.discount_percentage > 0
                   AND oi.discount_percentage = s.discount_percentage))
    """)


def downgrade() -> None:
    op.drop_constraint(op.f("fk_order_items_scheme_id_schemes"), "order_items", type_="foreignkey")
    op.drop_column("order_items", "scheme_snapshot")
    op.drop_column("order_items", "scheme_id")
    op.drop_column("order_items", "tax_inclusive")
    # ON_HOLD does not exist before this revision: such orders go back to PENDING (open,
    # awaiting the Order Desk), which is what they were before being held.
    op.execute("UPDATE orders SET status = 'PENDING' WHERE status = 'ON_HOLD'")
    op.drop_constraint(op.f("ck_orders_status_valid"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_status_valid"), "orders", f"status IN ({OLD_STATUSES})")
    op.drop_column("orders", "hold_reason")
