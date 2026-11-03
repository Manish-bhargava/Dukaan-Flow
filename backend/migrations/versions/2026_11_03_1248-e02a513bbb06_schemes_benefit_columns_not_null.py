"""schemes benefit columns not null

DATABASE_DESIGN.MD defines schemes.free_quantity and schemes.discount_percentage as
non-nullable NUMERIC columns. The benefit a scheme type does not use is stored as 0.

Revision ID: e02a513bbb06
Revises: 7e83f062af14
Create Date: 2026-11-03 12:48:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e02a513bbb06"
down_revision: Union[str, Sequence[str], None] = "7e83f062af14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECK_NAME = "ck_schemes_benefit_matches_type"

NEW_CHECK = (
    "(scheme_type = 'FREE_GOODS' AND free_quantity > 0 AND discount_percentage = 0)"
    " OR (scheme_type = 'SLAB_DISCOUNT' AND discount_percentage > 0"
    " AND discount_percentage <= 100 AND free_quantity = 0)"
)
OLD_CHECK = (
    "(scheme_type = 'FREE_GOODS' AND free_quantity > 0 AND discount_percentage IS NULL)"
    " OR (scheme_type = 'SLAB_DISCOUNT' AND discount_percentage > 0"
    " AND discount_percentage <= 100 AND free_quantity IS NULL)"
)


def upgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "schemes", type_="check")
    op.execute("UPDATE schemes SET free_quantity = 0 WHERE free_quantity IS NULL")
    op.execute("UPDATE schemes SET discount_percentage = 0 WHERE discount_percentage IS NULL")
    op.alter_column(
        "schemes", "free_quantity", existing_type=sa.Numeric(12, 3),
        nullable=False, server_default="0",
    )
    op.alter_column(
        "schemes", "discount_percentage", existing_type=sa.Numeric(5, 2),
        nullable=False, server_default="0",
    )
    op.create_check_constraint(op.f(CHECK_NAME), "schemes", NEW_CHECK)


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "schemes", type_="check")
    op.alter_column(
        "schemes", "free_quantity", existing_type=sa.Numeric(12, 3),
        nullable=True, server_default=None,
    )
    op.alter_column(
        "schemes", "discount_percentage", existing_type=sa.Numeric(5, 2),
        nullable=True, server_default=None,
    )
    op.execute("UPDATE schemes SET free_quantity = NULL WHERE scheme_type = 'SLAB_DISCOUNT'")
    op.execute("UPDATE schemes SET discount_percentage = NULL WHERE scheme_type = 'FREE_GOODS'")
    op.create_check_constraint(op.f(CHECK_NAME), "schemes", OLD_CHECK)
