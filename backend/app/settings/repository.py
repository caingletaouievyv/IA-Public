# IA/backend/app/settings/repository.py
# Settings reads and merges. Callers commit through settings_session().

import json
import threading
from contextlib import contextmanager, nullcontext

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.db import DatabaseConfigError, DatabaseConnectionError, get_engine, session_scope
from app.settings.models import UserSettings

# SQLite has one writer. This lock is in-process only and is not the PostgreSQL guarantee.
_SQLITE_LOCK = threading.RLock()


class SettingsStoreError(RuntimeError):
    """Settings storage failed. The message must not include connection details."""


@contextmanager
def settings_session():
    """Commit one settings transaction. Storage failures stay generic."""
    write_lock = _SQLITE_LOCK if get_engine().dialect.name == "sqlite" else nullcontext()
    with write_lock:
        try:
            with session_scope() as session:
                yield session
        except (DatabaseConfigError, DatabaseConnectionError, SettingsStoreError):
            raise
        except (IntegrityError, OperationalError, SQLAlchemyError):
            raise SettingsStoreError("Could not access settings.") from None


@contextmanager
def locked_settings(user_id: str):
    """Lock this user's settings before the merge, until commit or rollback."""
    with settings_session() as session:
        _lock_user_settings(session, user_id)
        yield session


def read_settings(session, user_id: str) -> dict:
    row = session.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    if row is None or not isinstance(row.preferences, dict):
        return {}
    return _copy(row.preferences)


def merge_settings(session, user_id: str, data: dict) -> dict:
    """Shallow-merge data into this user's document and return the full document."""
    _lock_user_settings(session, user_id)
    current = read_settings(session, user_id)
    merged = _copy({**current, **data})
    row = session.get(UserSettings, user_id)
    if row is None:
        session.add(UserSettings(user_id=user_id, preferences=merged))
    else:
        row.preferences = merged
    session.flush()
    return merged


def _lock_user_settings(session, user_id: str) -> None:
    """Serialize one user's settings writes. The keys do not share the memories lock."""
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    session.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            "hashtext('settings'), hashtext(CAST(:user_id AS text))"
            ")"
        ),
        {"user_id": user_id},
    )


def _copy(value: dict) -> dict:
    return json.loads(json.dumps(value))
