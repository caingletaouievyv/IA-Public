# IA/backend/app/notes/repository.py
# Note reads and writes. Callers commit through notes_session().

import threading
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.db import DatabaseConfigError, DatabaseConnectionError, get_engine, session_scope
from app.notes.models import Note

# SQLite has one writer. This lock is in-process only and is not the PostgreSQL guarantee.
_SQLITE_LOCK = threading.RLock()


class NoteStoreError(RuntimeError):
    """Note storage failed. The message must not include connection details."""


@contextmanager
def notes_session():
    """Commit one notes transaction. Storage failures stay generic."""
    write_lock = _SQLITE_LOCK if get_engine().dialect.name == "sqlite" else nullcontext()
    with write_lock:
        try:
            with session_scope() as session:
                yield session
        except (DatabaseConfigError, DatabaseConnectionError, NoteStoreError):
            raise
        except (IntegrityError, OperationalError, SQLAlchemyError):
            raise NoteStoreError("Could not access notes.") from None


def list_notes(session, user_id: str) -> list[dict]:
    rows = session.scalars(
        select(Note).where(Note.user_id == user_id).order_by(Note.seq, Note.id)
    ).all()
    return [_record(row) for row in rows]


def find_note(session, user_id: str, note_id: str) -> dict | None:
    row = session.scalar(select(Note).where(Note.user_id == user_id, Note.id == note_id))
    return _record(row) if row is not None else None


def insert_note(session, user_id: str, note_data: dict) -> dict:
    """Append one note. The stored id is always newly generated."""
    _lock_user_notes(session, user_id)
    now = _now()
    row = Note(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=note_data.get("title") or "",
        category=note_data.get("category") or "",
        content=note_data.get("content") or "",
        tags=_tags(note_data.get("tags")),
        created_at=now,
        updated_at=now,
        seq=_next_seq(session, user_id),
    )
    session.add(row)
    session.flush()
    return _record(row)


def update_note(session, user_id: str, note_id: str, updated_data: dict) -> dict | None:
    row = session.scalar(select(Note).where(Note.user_id == user_id, Note.id == note_id))
    if row is None:
        return None
    if "title" in updated_data:
        row.title = updated_data.get("title") or ""
    if "category" in updated_data:
        row.category = updated_data.get("category") or ""
    if "content" in updated_data:
        row.content = updated_data.get("content") or ""
    if "tags" in updated_data:
        row.tags = _tags(updated_data.get("tags"))
    row.updated_at = _now()
    session.flush()
    return _record(row)


def delete_note(session, user_id: str, note_id: str) -> bool:
    result = session.execute(delete(Note).where(Note.user_id == user_id, Note.id == note_id))
    return result.rowcount == 1


def replace_notes(session, user_id: str, notes: list) -> None:
    """Replace one user's notes, keeping the given order, ids, and timestamps."""
    _lock_user_notes(session, user_id)
    session.execute(delete(Note).where(Note.user_id == user_id))
    session.flush()
    now = _now()
    for seq, item in enumerate(notes, start=1):
        created = _parse_stamp(item.get("created_at")) if item.get("created_at") else now
        updated = _parse_stamp(item.get("updated_at")) if item.get("updated_at") else created
        session.add(
            Note(
                id=str(item.get("id") or uuid.uuid4()),
                user_id=user_id,
                title=item.get("title") or "",
                category=item.get("category") or "",
                content=item.get("content") or "",
                tags=_tags(item.get("tags")),
                created_at=created,
                updated_at=updated,
                seq=seq,
            )
        )
    session.flush()


def _lock_user_notes(session, user_id: str) -> None:
    """Serialize one user's note writes on PostgreSQL. The id is a bound parameter."""
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(CAST(:user_id AS text)))"),
        {"user_id": user_id},
    )


def _next_seq(session, user_id: str) -> int:
    current = session.scalar(select(func.max(Note.seq)).where(Note.user_id == user_id))
    return int(current or 0) + 1


def _tags(value) -> list:
    if not isinstance(value, list):
        return []
    return list(value)


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


def _record(row: Note) -> dict:
    tags = row.tags if isinstance(row.tags, list) else []
    return {
        "id": row.id,
        "title": row.title,
        "category": row.category,
        "content": row.content or "",
        "tags": list(tags),
        "created_at": _format_stamp(row.created_at),
        "updated_at": _format_stamp(row.updated_at),
    }


def _format_stamp(value) -> str:
    if isinstance(value, str):
        text_value = value.strip().replace(" ", "T")
        if text_value.endswith("+00:00"):
            return text_value[:-6] + "Z"
        if text_value.endswith("Z"):
            return text_value
        return text_value + "Z"
    if not isinstance(value, datetime):
        return ""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat() + "Z"
