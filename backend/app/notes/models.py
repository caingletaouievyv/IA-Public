# IA/backend/app/notes/models.py
# Note rows. seq keeps append order and is not part of the API.

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint("length(title) > 0", name="notes_title_present"),
        CheckConstraint("length(category) > 0", name="notes_category_present"),
        UniqueConstraint("user_id", "seq", name="notes_user_seq"),
        Index("notes_user_category", "user_id", "category"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("users.user_id", ondelete="CASCADE", name="notes_user_id_fkey"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)


class AskPendingConfirmation(Base):
    __tablename__ = "ask_pending_confirmations"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('create', 'delete')",
            name="ask_pending_confirmations_kind_known",
        ),
        CheckConstraint(
            "kind <> 'create' OR (need_title IS NOT NULL AND need_content IS NOT NULL AND category IS NOT NULL)",
            name="ask_pending_confirmations_create_fields",
        ),
        CheckConstraint(
            "kind <> 'delete' OR (note_id IS NOT NULL AND expected_title IS NOT NULL)",
            name="ask_pending_confirmations_delete_fields",
        ),
        Index("ask_pending_confirmations_expires", "expires_at"),
    )

    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("users.user_id", ondelete="CASCADE", name="ask_pending_confirmations_user_id_fkey"),
        primary_key=True,
    )
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    need_title: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    need_content: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_title: Mapped[str | None] = mapped_column(Text, nullable=True)
