# IA/backend/app/memories/repository.py
# Memory reads and writes. Callers commit through memories_session().

import threading
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.db import DatabaseConfigError, DatabaseConnectionError, get_engine, session_scope
from app.memories.models import Memory

# SQLite has one writer. This lock is in-process only and is not the PostgreSQL guarantee.
_SQLITE_LOCK = threading.RLock()
_ASSISTANT_NAME_KEY = "assistant.name"


class MemoryStoreError(RuntimeError):
    """Memory storage failed. The message must not include connection details."""


@contextmanager
def memories_session():
    """Commit one memory transaction. Storage failures stay generic."""
    write_lock = _SQLITE_LOCK if get_engine().dialect.name == "sqlite" else nullcontext()
    with write_lock:
        try:
            with session_scope() as session:
                yield session
        except (DatabaseConfigError, DatabaseConnectionError, MemoryStoreError):
            raise
        except (IntegrityError, OperationalError, SQLAlchemyError):
            raise MemoryStoreError("Could not access memories.") from None


@contextmanager
def locked_memories(user_id: str):
    """Lock this user before a read, and keep that lock until commit or rollback."""
    with memories_session() as session:
        _lock_user_memories(session, user_id)
        yield session


def list_memories(session, user_id: str) -> list[dict]:
    rows = session.scalars(
        select(Memory).where(Memory.user_id == user_id).order_by(Memory.seq, Memory.id)
    ).all()
    return [_record(row) for row in rows]


def replace_memories(session, user_id: str, memories: list[dict]) -> None:
    """Replace one user's memories, keeping the given order, ids, and timestamps."""
    # Same transaction lock as locked_memories(); a second request returns immediately.
    _lock_user_memories(session, user_id)
    session.execute(delete(Memory).where(Memory.user_id == user_id))
    session.flush()
    now = _now()
    for seq, item in enumerate(memories, start=1):
        created = _parse_stamp(item.get("created_at")) if item.get("created_at") else now
        updated = _parse_stamp(item.get("updated_at")) if item.get("updated_at") else created
        key = item.get("key")
        session.add(
            Memory(
                id=str(item.get("id") or uuid.uuid4()),
                user_id=user_id,
                text=item.get("text") or "",
                memory_key=key if key == _ASSISTANT_NAME_KEY else None,
                created_at=created,
                updated_at=updated,
                seq=seq,
            )
        )
    session.flush()


def _lock_user_memories(session, user_id: str) -> None:
    """Serialize one user's memory writes on PostgreSQL. The id is a bound parameter."""
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(CAST(:user_id AS text)))"),
        {"user_id": user_id},
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_stamp(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text_value = str(value).strip()
    if text_value.endswith("Z"):
        text_value = text_value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text_value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _record(row: Memory) -> dict:
    record = {
        "id": row.id,
        "text": row.text,
        "created_at": _format_stamp(row.created_at),
        "updated_at": _format_stamp(row.updated_at),
    }
    if row.memory_key:
        record["key"] = row.memory_key
    return record


def _format_stamp(value) -> str:
    if isinstance(value, str):
        text_value = value.strip().replace(" ", "T", 1)
        if text_value.endswith("Z"):
            return text_value[:-1] + "+00:00"
        if "+" not in text_value and "-" not in text_value[10:]:
            return text_value + "+00:00"
        return text_value
    if not isinstance(value, datetime):
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()
