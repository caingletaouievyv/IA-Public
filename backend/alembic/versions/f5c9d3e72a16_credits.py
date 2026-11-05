# IA/backend/alembic/versions/f5c9d3e72a16_credits.py
# Credit accounts, ledger rows, and per-user idempotency records.

"""credits

Revision ID: f5c9d3e72a16
Revises: e4b8c2d61f05
Create Date: 2026-11-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f5c9d3e72a16"
down_revision: Union[str, Sequence[str], None] = "e4b8c2d61f05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_accounts",
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE", name="credit_accounts_user_id_fkey"),
            primary_key=True,
        ),
        sa.Column("credit_balance", sa.Integer(), nullable=False),
        sa.CheckConstraint("credit_balance >= 0", name="credit_accounts_balance_nonnegative"),
    )
    op.create_table(
        "credit_ledger",
        sa.Column("entry_id", sa.Text(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE", name="credit_ledger_user_id_fkey"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("operation_id", sa.Text(), nullable=True),
        sa.Column("related_entry_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("user_id", "seq", name="credit_ledger_user_seq"),
    )
    op.create_index(
        "credit_ledger_user_operation",
        "credit_ledger",
        ["user_id", "operation_id"],
    )
    op.create_table(
        "credit_operations",
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE", name="credit_operations_user_id_fkey"),
            nullable=False,
        ),
        sa.Column("operation_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("user_id", "operation_id", name="credit_operations_pkey"),
        sa.CheckConstraint(
            "status IN ('pending', 'completed')",
            name="credit_operations_status_known",
        ),
    )


def downgrade() -> None:
    op.drop_table("credit_operations")
    op.drop_index("credit_ledger_user_operation", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_table("credit_accounts")
