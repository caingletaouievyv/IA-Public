# IA/backend/alembic/versions/e4b8c2d61f05_settings.py
# One settings document per user. There is no global settings row.

"""settings

Revision ID: e4b8c2d61f05
Revises: d1e6a4c93b20
Create Date: 2026-11-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4b8c2d61f05"
down_revision: Union[str, Sequence[str], None] = "d1e6a4c93b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE", name="settings_user_id_fkey"),
            primary_key=True,
        ),
        sa.Column("preferences", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("settings")
