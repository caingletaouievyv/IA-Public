# IA/backend/alembic/versions/d1e6a4c93b20_memories.py
# Memories belong to a user. seq preserves stored order and is not an API field.

"""memories

Revision ID: d1e6a4c93b20
Revises: c8a4e2b71d09
Create Date: 2026-11-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e6a4c93b20"
down_revision: Union[str, Sequence[str], None] = "c8a4e2b71d09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE", name="memories_user_id_fkey"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("memory_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(text) > 0 AND length(text) <= 500", name="memories_text_bounds"),
        sa.CheckConstraint(
            "memory_key IS NULL OR memory_key = 'assistant.name'",
            name="memories_key_known",
        ),
        sa.UniqueConstraint("user_id", "seq", name="memories_user_seq"),
    )
    op.create_index("memories_user_key", "memories", ["user_id", "memory_key"])


def downgrade() -> None:
    op.drop_index("memories_user_key", table_name="memories")
    op.drop_table("memories")
