# IA/backend/alembic/versions/b7e1a2c4d5f6_auth_accounts.py
# First revision: accounts, one Main Admin, and the demo seed marker.

"""auth accounts

Revision ID: b7e1a2c4d5f6
Revises:
Create Date: 2026-11-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1a2c4d5f6"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'user'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("length(trim(username)) > 0", name="users_username_present"),
        sa.CheckConstraint("length(password_hash) > 0", name="users_password_hash_present"),
        sa.CheckConstraint(
            "role IN ('user', 'admin', 'main_admin')",
            name="users_role_known",
        ),
        sa.UniqueConstraint("username", name="users_username_key"),
    )
    op.execute(
        "CREATE UNIQUE INDEX users_one_main_admin ON users ((true)) WHERE role = 'main_admin'"
    )
    op.create_table(
        "main_admin_marker",
        sa.Column("singleton", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("singleton = 1", name="main_admin_marker_one_row"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="main_admin_marker_user_id_fkey"),
        sa.UniqueConstraint("user_id", name="main_admin_marker_user_id_key"),
    )
    op.create_table(
        "demo_seed_marker",
        sa.Column("singleton", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("singleton = 1", name="demo_seed_marker_one_row"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="demo_seed_marker_user_id_fkey"),
        sa.UniqueConstraint("user_id", name="demo_seed_marker_user_id_key"),
    )


def downgrade() -> None:
    op.drop_table("demo_seed_marker")
    op.drop_table("main_admin_marker")
    op.execute("DROP INDEX IF EXISTS users_one_main_admin")
    op.drop_table("users")
