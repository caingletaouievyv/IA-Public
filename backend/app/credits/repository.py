# IA/backend/app/credits/repository.py
# Credit balance and idempotency changes. Callers commit through credits_session().
# Each change locks the account row, commits, and returns before any AI provider call.

import datetime
import json
import threading
import time
import uuid
from contextlib import contextmanager, nullcontext

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.credits.models import CreditAccount, CreditLedgerEntry, CreditOperation
from app.db import DatabaseConfigError, DatabaseConnectionError, get_engine, session_scope

# SQLite has one writer. This lock is in-process only and is not the PostgreSQL guarantee.
_SQLITE_LOCK = threading.RLock()


class CreditStoreError(RuntimeError):
    """Credit storage failed. The message must not include connection details."""


class InsufficientCreditsError(Exception):
    """Raised when a user cannot reserve the requested AI Credits."""

    def __init__(self, balance: int, required: int):
        self.balance = balance
        self.required = required
        super().__init__("Insufficient AI Credits")


@contextmanager
def credits_session():
    """Commit one credit transaction. Storage failures stay generic."""
    write_lock = _SQLITE_LOCK if get_engine().dialect.name == "sqlite" else nullcontext()
    with write_lock:
        try:
            with session_scope() as session:
                yield session
        except (DatabaseConfigError, DatabaseConnectionError, CreditStoreError, InsufficientCreditsError, ValueError):
            raise
        except (IntegrityError, OperationalError, SQLAlchemyError):
            raise CreditStoreError("Could not access credits.") from None


@contextmanager
def locked_credits(user_id: str, initial_balance: int):
    """Create the account if needed, lock that row, and hold the lock until commit."""
    with credits_session() as session:
        _ensure_and_lock(session, user_id, initial_balance)
        yield session


def account_row_exists(session, user_id: str) -> bool:
    return session.get(CreditAccount, user_id) is not None


def account_view(session, user_id: str) -> dict:
    """Return the account document. Internal sequence numbers stay out of it."""
    session.flush()
    session.expire_all()
    row = session.get(CreditAccount, user_id)
    entries = session.scalars(
        select(CreditLedgerEntry)
        .where(CreditLedgerEntry.user_id == user_id)
        .order_by(CreditLedgerEntry.seq)
    ).all()
    operations = session.scalars(
        select(CreditOperation)
        .where(CreditOperation.user_id == user_id)
        .order_by(CreditOperation.operation_id)
    ).all()
    return {
        "user_id": user_id,
        "credit_balance": int(row.credit_balance),
        "ledger": [_entry_view(entry) for entry in entries],
        "operations": {item.operation_id: _operation_view(item) for item in operations},
    }


def apply_claim(session, user_id: str, operation_id: str, pending_ttl_seconds: int) -> dict:
    """Claim a missing or expired operation, or report the current one."""
    row = _operation(session, user_id, operation_id)
    if row is not None and row.status == "completed":
        return {"status": "completed", "result": _copy(row.result or {})}
    if row is not None and row.status == "failed":
        return {"status": "failed", "result": _copy(row.result or {})}
    if row is not None and row.status == "pending":
        started = float(row.started_at or 0)
        if time.time() - started < pending_ttl_seconds:
            return {"status": "pending", "result": _copy(row.result or {})}
        if not _is_flashcard_generation_result(row.result):
            row.status = "pending"
            row.started_at = time.time()
            row.result = None
            session.flush()
            return {"status": "claimed"}
        return {"status": "pending", "result": _copy(row.result or {}), "expired": True}
    now = time.time()
    if row is None:
        session.add(
            CreditOperation(
                user_id=user_id,
                operation_id=operation_id,
                status="pending",
                started_at=now,
                result=None,
            )
        )
    else:
        row.status = "pending"
        row.started_at = now
        row.result = None
    session.flush()
    return {"status": "claimed"}


def apply_complete(session, user_id: str, operation_id: str, result: dict) -> bool:
    """Mark pending as completed. Returns True only when the transition occurred."""
    stored = _copy(result)
    row = _operation(session, user_id, operation_id)
    if row is None or row.status != "pending":
        return False
    row.status = "completed"
    row.started_at = None
    row.result = stored
    session.flush()
    return True


def apply_release(session, user_id: str, operation_id: str) -> None:
    row = _operation(session, user_id, operation_id)
    if row is not None and row.status == "pending":
        session.delete(row)
        session.flush()


def apply_fail(session, user_id: str, operation_id: str, result: dict) -> bool:
    """Mark pending as failed. Returns True only when the transition occurred."""
    row = _operation(session, user_id, operation_id)
    if row is None or row.status != "pending":
        return False
    row.status = "failed"
    row.started_at = None
    row.result = _copy(result)
    session.flush()
    return True


def apply_update_pending_result(session, user_id: str, operation_id: str, result: dict) -> bool:
    row = _operation(session, user_id, operation_id)
    if row is None or row.status != "pending":
        return False
    stored = _copy(result)
    stored["last_activity_at"] = time.time()
    row.result = stored
    session.flush()
    return True


def flashcard_last_activity_at(row: CreditOperation) -> float:
    """Return the latest progress timestamp without extending total job lifetime."""
    result = row.result if isinstance(row.result, dict) else {}
    activity = result.get("last_activity_at")
    if activity is not None:
        return float(activity)
    return float(row.started_at or 0)


def list_pending_flashcard_operations(session) -> list[tuple[str, str]]:
    rows = session.scalars(select(CreditOperation).where(CreditOperation.status == "pending")).all()
    pending = []
    for row in rows:
        if _is_flashcard_generation_result(row.result):
            pending.append((row.user_id, row.operation_id))
    return pending


def read_operation(session, user_id: str, operation_id: str) -> dict | None:
    row = _operation(session, user_id, operation_id)
    if row is None:
        return None
    payload = {"status": row.status, "result": _copy(row.result or {})}
    if row.started_at is not None:
        payload["started_at"] = float(row.started_at)
    return payload


def operation_completed(session, user_id: str, operation_id: str) -> bool:
    row = _operation(session, user_id, operation_id)
    return row is not None and row.status == "completed"


def apply_grant(session, user_id: str, amount: int, reason: str, operation_id: str) -> dict:
    """Grant once per operation. A different amount or reason for that id is rejected."""
    for entry in _ledger(session, user_id):
        if entry.get("operation_id") != operation_id:
            continue
        if entry.get("amount") == amount and entry.get("reason") == reason and not entry.get("related_entry_id"):
            return account_view(session, user_id)
        raise ValueError("operation_id already used for a different grant")
    _add_balance(session, user_id, amount)
    _append_entry(session, user_id, amount, reason, operation_id)
    return account_view(session, user_id)


def apply_reserve(session, user_id: str, amount: int, reason: str, operation_id: str) -> dict:
    """Debit once. An existing unrefunded debit for this operation is not charged again."""
    ledger = _ledger(session, user_id)
    if _unrefunded_debit(ledger, operation_id, amount) is not None:
        return {"account": account_view(session, user_id), "charged": False}
    row = session.get(CreditAccount, user_id)
    balance = int(row.credit_balance)
    if balance < amount:
        raise InsufficientCreditsError(balance, amount)
    # The balance predicate is the backstop if two deductions pass the read.
    session.execute(
        update(CreditAccount)
        .where(CreditAccount.user_id == user_id)
        .where(CreditAccount.credit_balance >= amount)
        .values(credit_balance=CreditAccount.credit_balance - amount)
    )
    session.expire(row)
    session.refresh(row)
    if int(row.credit_balance) != balance - amount:
        raise InsufficientCreditsError(int(row.credit_balance), amount)
    _append_entry(session, user_id, -amount, reason, operation_id)
    return {"account": account_view(session, user_id), "charged": True}


def apply_refund(session, user_id: str, amount: int, reason: str, operation_id: str) -> dict:
    """Refund the newest matching debit once. A second refund of that debit does nothing."""
    ledger = _ledger(session, user_id)
    debit = _unrefunded_debit(ledger, operation_id, amount)
    if debit is None:
        return account_view(session, user_id)
    _add_balance(session, user_id, amount)
    _append_entry(session, user_id, amount, reason, operation_id, debit["entry_id"])
    return account_view(session, user_id)


def _ensure_and_lock(session, user_id: str, initial_balance: int) -> CreditAccount:
    """Insert the account once, then lock it so later balance changes cannot overlap."""
    inserted = session.execute(
        _insert_account(session).values(user_id=user_id, credit_balance=initial_balance)
        .on_conflict_do_nothing(index_elements=["user_id"])
        .returning(CreditAccount.user_id)
    ).scalar_one_or_none()
    if inserted is not None:
        _append_entry(session, user_id, initial_balance, "initial_balance")
    statement = select(CreditAccount).where(CreditAccount.user_id == user_id)
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = session.scalar(statement)
    if row is None:
        raise CreditStoreError("Could not access credits.")
    return row


def _insert_account(session):
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        return pg_insert(CreditAccount)
    return sqlite_insert(CreditAccount)


def _add_balance(session, user_id: str, amount: int) -> None:
    session.execute(
        update(CreditAccount)
        .where(CreditAccount.user_id == user_id)
        .values(credit_balance=CreditAccount.credit_balance + amount)
    )


def _append_entry(
    session,
    user_id: str,
    amount: int,
    reason: str,
    operation_id: str | None = None,
    related_entry_id: str | None = None,
) -> None:
    current = session.scalar(
        select(CreditLedgerEntry.seq)
        .where(CreditLedgerEntry.user_id == user_id)
        .order_by(CreditLedgerEntry.seq.desc())
        .limit(1)
    )
    session.add(
        CreditLedgerEntry(
            entry_id=str(uuid.uuid4()),
            user_id=user_id,
            seq=(current or 0) + 1,
            amount=amount,
            reason=reason,
            operation_id=operation_id or None,
            related_entry_id=related_entry_id or None,
            created_at=_timestamp(),
        )
    )
    session.flush()


def _ledger(session, user_id: str) -> list[dict]:
    rows = session.scalars(
        select(CreditLedgerEntry)
        .where(CreditLedgerEntry.user_id == user_id)
        .order_by(CreditLedgerEntry.seq)
    ).all()
    return [_entry_view(row) for row in rows]


def _unrefunded_debit(ledger: list[dict], operation_id: str, amount: int) -> dict | None:
    for entry in reversed(ledger):
        if entry.get("operation_id") != operation_id or entry.get("amount") != -amount:
            continue
        if not any(item.get("related_entry_id") == entry.get("entry_id") for item in ledger):
            return entry
    return None


def _operation(session, user_id: str, operation_id: str) -> CreditOperation | None:
    return session.scalar(
        select(CreditOperation).where(
            CreditOperation.user_id == user_id,
            CreditOperation.operation_id == operation_id,
        )
    )


def _entry_view(entry: CreditLedgerEntry) -> dict:
    view = {
        "entry_id": entry.entry_id,
        "user_id": entry.user_id,
        "amount": int(entry.amount),
        "reason": entry.reason,
        "created_at": entry.created_at,
    }
    if entry.operation_id:
        view["operation_id"] = entry.operation_id
    if entry.related_entry_id:
        view["related_entry_id"] = entry.related_entry_id
    return view


def _operation_view(row: CreditOperation) -> dict:
    if row.status == "completed":
        return {"status": "completed", "result": _copy(row.result or {})}
    if row.status == "failed":
        return {"status": "failed", "result": _copy(row.result or {})}
    view = {"status": "pending", "started_at": float(row.started_at or 0)}
    if row.result:
        view["result"] = _copy(row.result)
    return view


def _is_flashcard_generation_result(result) -> bool:
    return isinstance(result, dict) and result.get("kind") == "flashcards_generation"


def _copy(value):
    return json.loads(json.dumps(value))


def _timestamp() -> str:
    current = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return current.isoformat() + "Z"
