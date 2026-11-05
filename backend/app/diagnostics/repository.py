# IA/backend/app/diagnostics/repository.py
# Diagnostic events. Callers commit through diagnostics_session().
# Insert, duplicate feedback, and retention trim share one transaction lock.

import datetime
import threading
from contextlib import contextmanager, nullcontext

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.db import DatabaseConfigError, DatabaseConnectionError, get_engine, session_scope
from app.diagnostics.models import DiagnosticEvent

# SQLite has one writer. This lock is in-process only and is not the PostgreSQL guarantee.
_SQLITE_LOCK = threading.RLock()
_OPTIONAL_FIELDS = (
    "feedback_reason",
    "provider",
    "model",
    "ai_mode",
    "operation_id",
    "memory_status",
    "note_context_mode",
    "memory_enabled",
)


class DiagnosticsStoreError(RuntimeError):
    """Diagnostics storage failed. The message must not include connection details."""


@contextmanager
def diagnostics_session():
    """Commit one diagnostics transaction. Storage failures stay generic."""
    write_lock = _SQLITE_LOCK if get_engine().dialect.name == "sqlite" else nullcontext()
    with write_lock:
        try:
            with session_scope() as session:
                yield session
        except (DatabaseConfigError, DatabaseConnectionError, DiagnosticsStoreError, ValueError):
            raise
        except (IntegrityError, OperationalError, SQLAlchemyError):
            raise DiagnosticsStoreError("Could not access diagnostics.") from None


def insert_event(session, user_id: str, event: dict, max_stored: int, retention_days: int) -> dict:
    """Lock this user, keep one report per operation, and drop rows past the cap."""
    # Held until this transaction commits or rolls back. Listing does not take it.
    _lock_user_diagnostics(session, user_id)
    cutoff = _cutoff(retention_days)
    operation_id = event.get("operation_id")
    if event["kind"] == "user_report" and operation_id:
        existing = _matching_report(session, user_id, operation_id, cutoff)
        if existing is not None:
            return _view(existing)
    if cutoff is not None:
        session.execute(
            delete(DiagnosticEvent).where(
                DiagnosticEvent.user_id == user_id,
                DiagnosticEvent.occurred_at < cutoff,
            )
        )
    row = DiagnosticEvent(
        event_id=event["event_id"],
        user_id=user_id,
        occurred_at=_require_timestamp(event.get("timestamp")),
        kind=event["kind"],
        feature=event["feature"],
        code=event["code"],
        category=event["category"],
        fallback=event["fallback"],
        error_type=event["error_type"],
        user_key_prefix=event["user_key_prefix"],
        feedback_reason=event.get("feedback_reason"),
        provider=event.get("provider"),
        model=event.get("model"),
        ai_mode=event.get("ai_mode"),
        operation_id=operation_id,
        memory_status=event.get("memory_status"),
        note_context_mode=event.get("note_context_mode"),
        memory_enabled=event.get("memory_enabled"),
    )
    session.add(row)
    session.flush()
    stale_ids = session.scalars(
        select(DiagnosticEvent.id)
        .where(DiagnosticEvent.user_id == user_id)
        .order_by(DiagnosticEvent.occurred_at.desc(), DiagnosticEvent.id.desc())
        .offset(max_stored)
    ).all()
    if stale_ids:
        session.execute(delete(DiagnosticEvent).where(DiagnosticEvent.id.in_(stale_ids)))
        session.flush()
    return _view(row)


def list_user_events(session, user_id: str, limit: int, retention_days: int) -> list[dict]:
    rows = session.scalars(_recent(limit, retention_days, user_id)).all()
    return [_view(row) for row in rows]


def list_admin_events(session, limit: int, retention_days: int) -> list[dict]:
    rows = session.scalars(_recent(limit, retention_days)).all()
    return [_view(row) for row in rows]


def _lock_user_diagnostics(session, user_id: str) -> None:
    """Serialize one user's insert and trim. The keys do not share the activity lock."""
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    session.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            "hashtext('diagnostics'), hashtext(CAST(:user_id AS text))"
            ")"
        ),
        {"user_id": user_id},
    )


def _matching_report(session, user_id: str, operation_id: str, cutoff):
    statement = select(DiagnosticEvent).where(
        DiagnosticEvent.user_id == user_id,
        DiagnosticEvent.kind == "user_report",
        DiagnosticEvent.operation_id == operation_id,
    )
    if cutoff is not None:
        statement = statement.where(DiagnosticEvent.occurred_at >= cutoff)
    return session.scalars(
        statement.order_by(DiagnosticEvent.occurred_at.desc(), DiagnosticEvent.id.desc())
    ).first()


def _recent(limit: int, retention_days: int, user_id: str | None = None):
    statement = select(DiagnosticEvent)
    if user_id is not None:
        statement = statement.where(DiagnosticEvent.user_id == user_id)
    cutoff = _cutoff(retention_days)
    if cutoff is not None:
        statement = statement.where(DiagnosticEvent.occurred_at >= cutoff)
    return statement.order_by(DiagnosticEvent.occurred_at.desc(), DiagnosticEvent.id.desc()).limit(limit)


def _cutoff(retention_days: int):
    if retention_days <= 0:
        return None
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=retention_days)


def _require_timestamp(value) -> datetime.datetime:
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise ValueError("Diagnostic event timestamp is invalid")
    return parsed


def _parse_timestamp(value):
    if isinstance(value, datetime.datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _view(row: DiagnosticEvent) -> dict:
    event = {
        "event_id": row.event_id,
        "timestamp": _timestamp_text(row.occurred_at),
        "kind": row.kind,
        "feature": row.feature,
        "code": row.code,
        "category": row.category,
        "fallback": row.fallback,
        "error_type": row.error_type,
        "user_key_prefix": row.user_key_prefix,
    }
    for key in _OPTIONAL_FIELDS:
        value = getattr(row, key)
        if value is not None:
            event[key] = value
    return event


def _timestamp_text(value) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise ValueError("Diagnostic event timestamp is invalid")
    return parsed.isoformat()
