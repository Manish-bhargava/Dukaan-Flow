"""add users email

Retailers sign in with an email OTP. Email is optional (existing users have none), unique,
and stored normalized (trimmed, lower case), enforced by a CHECK constraint.

Revision ID: 6011b61e50cc
Revises: e02a513bbb06
Create Date: 2026-11-03 15:23:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6011b61e50cc"
down_revision: Union[str, Sequence[str], None] = "e02a513bbb06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])
    op.create_check_constraint(
        op.f("ck_users_email_normalized"), "users", "email IS NULL OR email = lower(btrim(email))"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_email_normalized"), "users", type_="check")
    op.drop_constraint(op.f("uq_users_email"), "users", type_="unique")
    op.drop_column("users", "email")
