# IA/backend/alembic/versions/c9a1e4f72b36_ask_pending.py
# One create confirmation and one delete confirmation per user.

"""ask pending confirmations

Revision ID: c9a1e4f72b36
Revises: b8e3c1a94d27
Create Date: 2026-11-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9a1e4f72b36"
down_revision: Union[str, Sequence[str], None] = "b8e3c1a94d27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ask_pending_confirmations",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("need_title", sa.Boolean(), nullable=True),
        sa.Column("need_content", sa.Boolean(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("note_id", sa.Text(), nullable=True),
        sa.Column("expected_title", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="ask_pending_confirmations_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "kind", name="ask_pending_confirmations_pkey"),
        sa.CheckConstraint(
            "kind IN ('create', 'delete')",
            name="ask_pending_confirmations_kind_known",
        ),
        sa.CheckConstraint(
            "kind <> 'create' OR (need_title IS NOT NULL AND need_content IS NOT NULL AND category IS NOT NULL)",
            name="ask_pending_confirmations_create_fields",
        ),
        sa.CheckConstraint(
            "kind <> 'delete' OR (note_id IS NOT NULL AND expected_title IS NOT NULL)",
            name="ask_pending_confirmations_delete_fields",
        ),
    )
    op.create_index(
        "ask_pending_confirmations_expires",
        "ask_pending_confirmations",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ask_pending_confirmations_expires", table_name="ask_pending_confirmations")
    op.drop_table("ask_pending_confirmations")
