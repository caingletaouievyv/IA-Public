# IA/backend/app/auth/models.py
# Account tables. Usernames stay case-sensitive. One Main Admin is a database constraint.

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, literal_column, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared metadata for accounts, notes, memories, settings, credits, activity, and diagnostics."""


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(trim(username)) > 0", name="users_username_present"),
        CheckConstraint("length(password_hash) > 0", name="users_password_hash_present"),
        CheckConstraint(
            "role IN ('user', 'admin', 'main_admin')",
            name="users_role_known",
        ),
        Index(
            "users_one_main_admin",
            literal_column("(true)"),
            unique=True,
            postgresql_where=literal_column("role = 'main_admin'"),
            sqlite_where=literal_column("role = 'main_admin'"),
        ),
    )

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'user'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MainAdminMarker(Base):
    __tablename__ = "main_admin_marker"
    __table_args__ = (
        CheckConstraint("singleton = 1", name="main_admin_marker_one_row"),
    )

    singleton: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.user_id"),
        unique=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DemoSeedMarker(Base):
    __tablename__ = "demo_seed_marker"
    __table_args__ = (
        CheckConstraint("singleton = 1", name="demo_seed_marker_one_row"),
    )

    singleton: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.user_id"),
        unique=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
