# IA/backend/app/settings/models.py
# One preferences document per user. Missing rows mean an empty document.

from sqlalchemy import ForeignKey, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base


class UserSettings(Base):
    __tablename__ = "settings"

    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("users.user_id", ondelete="CASCADE", name="settings_user_id_fkey"),
        primary_key=True,
    )
    preferences: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
