# IA/backend/app/credits/models.py
# One credit account per user, an append-only ledger, and per-user operation records.

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, JSON, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base


class CreditAccount(Base):
    __tablename__ = "credit_accounts"
    __table_args__ = (
        CheckConstraint("credit_balance >= 0", name="credit_accounts_balance_nonnegative"),
    )

    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("users.user_id", ondelete="CASCADE", name="credit_accounts_user_id_fkey"),
        primary_key=True,
    )
    credit_balance: Mapped[int] = mapped_column(Integer, nullable=False)


class CreditLedgerEntry(Base):
    __tablename__ = "credit_ledger"
    __table_args__ = (
        UniqueConstraint("user_id", "seq", name="credit_ledger_user_seq"),
        Index("credit_ledger_user_operation", "user_id", "operation_id"),
    )

    entry_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("users.user_id", ondelete="CASCADE", name="credit_ledger_user_id_fkey"),
        nullable=False,
    )
    # Append order for this user. Omitted from the account document.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    operation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Refunds point at the debit entry_id. A debit and its refund share operation_id.
    related_entry_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class CreditOperation(Base):
    __tablename__ = "credit_operations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="credit_operations_status_known",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("users.user_id", ondelete="CASCADE", name="credit_operations_user_id_fkey"),
        primary_key=True,
    )
    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
