# IA/backend/app/activity/repository.py
# Append-only activity events. Callers commit through activity_session().
# Insert and trim share one transaction lock. The identity column orders equal timestamps.

import datetime
import threading
from contextlib import contextmanager, nullcontext

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.activity.models import ActivityEvent
from app.db import DatabaseConfigError, DatabaseConnectionError, get_engine, session_scope

# SQLite has one writer. This lock is in-process only and is not the PostgreSQL guarantee.
_SQLITE_LOCK = threading.RLock()


class ActivityStoreError(RuntimeError):
    """Activity storage failed. The message must not include connection details."""


@contextmanager
def activity_session():
    """Commit one activity transaction. Storage failures stay generic."""
    write_lock = _SQLITE_LOCK if get_engine().dialect.name == "sqlite" else nullcontext()
    with write_lock:
        try:
            with session_scope() as session:
                yield session
        except (DatabaseConfigError, DatabaseConnectionError, ActivityStoreError, ValueError):
            raise
        except (IntegrityError, OperationalError, SQLAlchemyError):
            raise ActivityStoreError("Could not access activity.") from None


def insert_event(session, user_id: str, event: dict, max_stored: int) -> dict:
    """Lock this user, insert one event, and drop rows beyond the retention cap."""
    # Held until this transaction commits or rolls back. Listing does not take it.
    _lock_user_activity(session, user_id)
    row = ActivityEvent(
        event_id=event["event_id"],
        user_id=user_id,
        event_type=event["event_type"],
        description=event["description"],
        occurred_at=event["timestamp"],
    )
    session.add(row)
    session.flush()
    stale_ids = session.scalars(
        select(ActivityEvent.id)
        .where(ActivityEvent.user_id == user_id)
        .order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc())
        .offset(max_stored)
    ).all()
    if stale_ids:
        session.execute(delete(ActivityEvent).where(ActivityEvent.id.in_(stale_ids)))
        session.flush()
    return _view(row)


def _lock_user_activity(session, user_id: str) -> None:
    """Serialize one user's insert and trim. The keys do not share the memories lock."""
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    session.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            "hashtext('activity'), hashtext(CAST(:user_id AS text))"
            ")"
        ),
        {"user_id": user_id},
    )


def list_events(session, user_id: str, limit: int) -> list[dict]:
    rows = session.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.user_id == user_id)
        .order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc())
        .limit(limit)
    ).all()
    return [_view(row) for row in rows]


def _view(row: ActivityEvent) -> dict:
    return {
        "event_id": row.event_id,
        "event_type": row.event_type,
        "description": row.description,
        "timestamp": _timestamp_text(row.occurred_at),
    }


def _timestamp_text(value) -> str:
    if isinstance(value, str):
        value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    else:
        value = value.astimezone(datetime.timezone.utc)
    return value.isoformat()
