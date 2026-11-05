# IA/backend/app/activity/models.py
# One append-only activity event per row. The internal id is only a tie-breaker.

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'note.created', 'note.updated', 'note.deleted', "
            "'flashcard_deck.created', 'flashcard_deck.updated', 'flashcard_deck.deleted'"
            ")",
            name="activity_events_type_known",
        ),
        Index("activity_events_user_recent", "user_id", "occurred_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    event_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("users.user_id", ondelete="CASCADE", name="activity_events_user_id_fkey"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
