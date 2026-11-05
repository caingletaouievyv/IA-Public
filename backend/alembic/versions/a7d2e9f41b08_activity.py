# IA/backend/alembic/versions/a7d2e9f41b08_activity.py
# Append-only per-user activity events. The id orders events that share a timestamp.

"""activity

Revision ID: a7d2e9f41b08
Revises: f5c9d3e72a16
Create Date: 2026-11-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7d2e9f41b08"
down_revision: Union[str, Sequence[str], None] = "f5c9d3e72a16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_events",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("event_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE", name="activity_events_user_id_fkey"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ("
            "'note.created', 'note.updated', 'note.deleted', "
            "'flashcard_deck.created', 'flashcard_deck.updated', 'flashcard_deck.deleted'"
            ")",
            name="activity_events_type_known",
        ),
    )
    op.create_index(
        "activity_events_user_recent",
        "activity_events",
        ["user_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("activity_events_user_recent", table_name="activity_events")
    op.drop_table("activity_events")
