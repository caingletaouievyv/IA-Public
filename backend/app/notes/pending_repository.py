# IA/backend/app/notes/pending_repository.py
# One Ask create confirmation and one delete confirmation per user.
# Consumption deletes the row under a PostgreSQL row lock and commits before note changes.

import datetime
import threading
from contextlib import contextmanager, nullcontext

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.db import DatabaseConfigError, DatabaseConnectionError, get_engine, session_scope
from app.notes.models import AskPendingConfirmation

# SQLite has one writer. This lock is in-process only and is not the PostgreSQL guarantee.
_SQLITE_LOCK = threading.RLock()
KIND_CREATE = "create"
KIND_DELETE = "delete"


class PendingStoreError(RuntimeError):
    """Pending confirmation storage failed. The message must not include connection details."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


@contextmanager
def pending_session():
    """Commit one pending-confirmation transaction. Storage failures stay generic."""
    write_lock = _SQLITE_LOCK if get_engine().dialect.name == "sqlite" else nullcontext()
    with write_lock:
        try:
            with session_scope() as session:
                yield session
        except (DatabaseConfigError, DatabaseConnectionError, PendingStoreError, ValueError):
            raise
        except (IntegrityError, OperationalError, SQLAlchemyError):
            raise PendingStoreError("Could not access pending confirmations.") from None


def save_create(
    session,
    user_id: str,
    *,
    need_title: bool,
    need_content: bool,
    title: str | None,
    category: str,
    ttl_seconds: int,
    created_at: datetime.datetime | None = None,
    expires_at: datetime.datetime | None = None,
) -> dict:
    now = _now()
    created = created_at or now
    expires = expires_at or (now + datetime.timedelta(seconds=ttl_seconds))
    _upsert(
        session,
        {
            "user_id": user_id,
            "kind": KIND_CREATE,
            "created_at": created,
            "expires_at": expires,
            "need_title": bool(need_title),
            "need_content": bool(need_content),
            "title": title,
            "category": category,
            "note_id": None,
            "expected_title": None,
        },
    )
    return _create_view(user_id, need_title, need_content, title, category, created, expires)


def save_delete(
    session,
    user_id: str,
    *,
    note_id: str,
    expected_title: str,
    ttl_seconds: int,
) -> dict:
    now = _now()
    expires = now + datetime.timedelta(seconds=ttl_seconds)
    _upsert(
        session,
        {
            "user_id": user_id,
            "kind": KIND_DELETE,
            "created_at": now,
            "expires_at": expires,
            "need_title": None,
            "need_content": None,
            "title": None,
            "category": None,
            "note_id": note_id,
            "expected_title": expected_title,
        },
    )
    return _delete_view(note_id, expected_title, now, expires)


def load_pending(session, user_id: str, kind: str) -> dict | None:
    row = _locked(session, user_id, kind)
    if row is None:
        return None
    if _expired(row):
        session.delete(row)
        session.flush()
        return None
    return _view(row)


def clear_pending(session, user_id: str, kind: str) -> None:
    session.execute(
        delete(AskPendingConfirmation).where(
            AskPendingConfirmation.user_id == user_id,
            AskPendingConfirmation.kind == kind,
        )
    )


def consume_pending(session, user_id: str, kind: str, *, match_title: str | None = None) -> dict | None:
    """Delete one live confirmation. A second consumer in another transaction gets nothing."""
    row = _locked(session, user_id, kind)
    if row is None:
        return None
    if _expired(row):
        session.delete(row)
        session.flush()
        return None
    if match_title is not None and (row.expected_title or "") != match_title:
        return None
    payload = _view(row)
    session.delete(row)
    session.flush()
    return payload


def _upsert(session, values: dict) -> None:
    statement = _insert(session).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=["user_id", "kind"],
        set_={key: values[key] for key in values if key not in {"user_id", "kind"}},
    )
    session.execute(statement)


def _insert(session):
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        return pg_insert(AskPendingConfirmation)
    return sqlite_insert(AskPendingConfirmation)


def _locked(session, user_id: str, kind: str):
    statement = select(AskPendingConfirmation).where(
        AskPendingConfirmation.user_id == user_id,
        AskPendingConfirmation.kind == kind,
    )
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    return session.scalar(statement)


def _expired(row: AskPendingConfirmation) -> bool:
    return _now() > _as_utc(row.expires_at)


def _view(row: AskPendingConfirmation) -> dict:
    if row.kind == KIND_CREATE:
        return _create_view(
            row.user_id,
            bool(row.need_title),
            bool(row.need_content),
            row.title,
            row.category or "general",
            _as_utc(row.created_at),
            _as_utc(row.expires_at),
        )
    return _delete_view(
        row.note_id or "",
        row.expected_title or "",
        _as_utc(row.created_at),
        _as_utc(row.expires_at),
    )


def _create_view(user_id, need_title, need_content, title, category, created, expires) -> dict:
    del user_id
    return {
        "need_title": bool(need_title),
        "need_content": bool(need_content),
        "title": title,
        "category": category or "general",
        "created_at": created.timestamp(),
        "expires_at": expires.timestamp(),
    }


def _delete_view(note_id, expected_title, created, expires) -> dict:
    return {
        "note_id": note_id,
        "expected_title": expected_title,
        "created_at": created.timestamp(),
        "expires_at": expires.timestamp(),
    }


def _as_utc(value) -> datetime.datetime:
    if isinstance(value, str):
        value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)
