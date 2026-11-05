# IA/backend/app/memories/models.py
# Memory rows. seq keeps stored order and is not part of the API.

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint("length(text) > 0 AND length(text) <= 500", name="memories_text_bounds"),
        CheckConstraint(
            "memory_key IS NULL OR memory_key = 'assistant.name'",
            name="memories_key_known",
        ),
        UniqueConstraint("user_id", "seq", name="memories_user_seq"),
        Index("memories_user_key", "user_id", "memory_key"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("users.user_id", ondelete="CASCADE", name="memories_user_id_fkey"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    memory_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
