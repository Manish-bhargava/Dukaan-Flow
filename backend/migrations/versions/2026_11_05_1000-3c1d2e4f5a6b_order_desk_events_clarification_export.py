"""order desk: order history, clarification status, Tally export marker

Revision ID: 3c1d2e4f5a6b
Revises: 768fa02aea51
Create Date: 2026-11-05 10:00:00

Existing orders get their history backfilled from the columns that already record it
(created, approved, rejected, corrections), so every order has a history from the start.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "3c1d2e4f5a6b"
down_revision: Union[str, Sequence[str], None] = "768fa02aea51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_STATUSES = "'PENDING', 'CREDIT_HOLD', 'ON_HOLD', 'APPROVED', 'REJECTED'"
NEW_STATUSES = "'PENDING', 'CREDIT_HOLD', 'ON_HOLD', 'CLARIFICATION_REQUIRED', 'APPROVED', 'REJECTED'"
ACTIONS = ("'RECEIVED', 'CONFIRMED', 'CREDIT_HOLD', 'PUT_ON_HOLD', 'CLARIFICATION_REQUESTED', "
           "'CORRECTED', 'REJECTED', 'EXPORTED'")


def upgrade() -> None:
    op.drop_constraint(op.f("ck_orders_status_valid"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_status_valid"), "orders", f"status IN ({NEW_STATUSES})")
    op.add_column("orders", sa.Column("clarification_message", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("tally_exported_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "order_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"action IN ({ACTIONS})", name=op.f("ck_order_events_action_valid")),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name=op.f("fk_order_events_actor_id_users")),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_order_events_order_id_orders")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_events")),
    )
    op.create_index("ix_order_events_order_id_created_at", "order_events", ["order_id", "created_at"], unique=False)

    # Backfill history for orders created before this revision.
    op.execute("""
        INSERT INTO order_events (order_id, action, actor_id, details, created_at)
        SELECT id, 'RECEIVED', created_by,
               jsonb_build_object('source', source, 'created_offline', created_offline, 'backfilled', true),
               created_at
        FROM orders
    """)
    op.execute("""
        INSERT INTO order_events (order_id, action, actor_id, message, details, created_at)
        SELECT i.order_id, 'CORRECTED', c.corrected_by, c.reason,
               jsonb_build_object('old_product_id', c.old_product_id, 'new_product_id', c.new_product_id,
                                  'old_quantity', c.old_quantity, 'new_quantity', c.new_quantity, 'backfilled', true),
               c.created_at
        FROM order_corrections c JOIN order_items i ON i.id = c.order_item_id
    """)
    op.execute("""
        INSERT INTO order_events (order_id, action, actor_id, details, created_at)
        SELECT id, 'CONFIRMED', approved_by, jsonb_build_object('backfilled', true), approved_at
        FROM orders WHERE status = 'APPROVED' AND approved_at IS NOT NULL
    """)
    op.execute("""
        INSERT INTO order_events (order_id, action, actor_id, message, details, created_at)
        SELECT id, 'REJECTED', NULL, rejection_reason, jsonb_build_object('backfilled', true), updated_at
        FROM orders WHERE status = 'REJECTED'
    """)
    op.execute("""
        INSERT INTO order_events (order_id, action, actor_id, message, details, created_at)
        SELECT id, 'PUT_ON_HOLD', NULL, hold_reason, jsonb_build_object('backfilled', true), updated_at
        FROM orders WHERE status = 'ON_HOLD'
    """)


def downgrade() -> None:
    op.drop_index("ix_order_events_order_id_created_at", table_name="order_events")
    op.drop_table("order_events")
    op.drop_column("orders", "tally_exported_at")
    # CLARIFICATION_REQUIRED does not exist before this revision: keep those orders open as ON_HOLD.
    op.execute("UPDATE orders SET status = 'ON_HOLD', hold_reason = COALESCE(clarification_message, hold_reason) "
               "WHERE status = 'CLARIFICATION_REQUIRED'")
    op.drop_column("orders", "clarification_message")
    op.drop_constraint(op.f("ck_orders_status_valid"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_status_valid"), "orders", f"status IN ({OLD_STATUSES})")
