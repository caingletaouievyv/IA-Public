# IA/backend/app/diagnostics/models.py
# One diagnostic event per row. The internal id is only a tie-breaker.

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base


class DiagnosticEvent(Base):
    __tablename__ = "diagnostic_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('automatic', 'user_report')",
            name="diagnostic_events_kind_known",
        ),
        CheckConstraint(
            "kind <> 'user_report' OR feedback_reason IS NOT NULL",
            name="diagnostic_events_report_reason",
        ),
        Index("diagnostic_events_user_recent", "user_id", "occurred_at", "id"),
        Index("diagnostic_events_recent", "occurred_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    event_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("users.user_id", ondelete="CASCADE", name="diagnostic_events_user_id_fkey"),
        nullable=False,
    )
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    fallback: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    user_key_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_context_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
