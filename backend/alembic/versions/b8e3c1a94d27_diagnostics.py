# IA/backend/alembic/versions/b8e3c1a94d27_diagnostics.py
# Per-user diagnostic events. The id orders events that share a timestamp.

"""diagnostics

Revision ID: b8e3c1a94d27
Revises: a7d2e9f41b08
Create Date: 2026-11-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8e3c1a94d27"
down_revision: Union[str, Sequence[str], None] = "a7d2e9f41b08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_events",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("event_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE", name="diagnostic_events_user_id_fkey"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("feature", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("fallback", sa.Text(), nullable=False),
        sa.Column("error_type", sa.Text(), nullable=False),
        sa.Column("user_key_prefix", sa.Text(), nullable=False),
        sa.Column("feedback_reason", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("ai_mode", sa.Text(), nullable=True),
        sa.Column("operation_id", sa.Text(), nullable=True),
        sa.Column("memory_status", sa.Text(), nullable=True),
        sa.Column("note_context_mode", sa.Text(), nullable=True),
        sa.Column("memory_enabled", sa.Boolean(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('automatic', 'user_report')",
            name="diagnostic_events_kind_known",
        ),
        sa.CheckConstraint(
            "kind <> 'user_report' OR feedback_reason IS NOT NULL",
            name="diagnostic_events_report_reason",
        ),
    )
    op.create_index(
        "diagnostic_events_user_recent",
        "diagnostic_events",
        ["user_id", "occurred_at", "id"],
    )
    op.create_index(
        "diagnostic_events_recent",
        "diagnostic_events",
        ["occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("diagnostic_events_recent", table_name="diagnostic_events")
    op.drop_index("diagnostic_events_user_recent", table_name="diagnostic_events")
    op.drop_table("diagnostic_events")
