# IA/backend/alembic/versions/c8a4e2b71d09_notes.py
# Notes belong to a user. seq preserves append order and is not an API field.

"""notes

Revision ID: c8a4e2b71d09
Revises: b7e1a2c4d5f6
Create Date: 2026-11-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8a4e2b71d09"
down_revision: Union[str, Sequence[str], None] = "b7e1a2c4d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE", name="notes_user_id_fkey"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(title) > 0", name="notes_title_present"),
        sa.CheckConstraint("length(category) > 0", name="notes_category_present"),
        sa.UniqueConstraint("user_id", "seq", name="notes_user_seq"),
    )
    op.create_index("notes_user_category", "notes", ["user_id", "category"])


def downgrade() -> None:
    op.drop_index("notes_user_category", table_name="notes")
    op.drop_table("notes")
