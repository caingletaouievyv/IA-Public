# IA/backend/scripts/test/auth_db.py
# SQLite account database for auth tests. This does not verify PostgreSQL concurrency.

import uuid

from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool

import app.diagnostics.models  # noqa: F401  # create diagnostics tables with the auth metadata
import app.activity.models  # noqa: F401  # create activity tables with the auth metadata
import app.credits.models  # noqa: F401  # create credit tables with the auth metadata
import app.memories.models  # noqa: F401  # create memory tables with the auth metadata
import app.settings.models  # noqa: F401  # create settings tables with the auth metadata
import app.notes.models  # noqa: F401  # create notes tables with the auth metadata
from app.auth.models import Base
from app.db import install_engine, reset_engine

_keeper = None


def install_sqlite_auth_database():
    """Install a shared in-memory SQLite engine and create the account and note tables."""
    global _keeper
    name = uuid.uuid4().hex
    engine = create_engine(
        f"sqlite:///file:{name}?mode=memory&cache=shared&uri=true",
        poolclass=NullPool,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Shared memory disappears when the last connection closes. Hold one open.
    _keeper = engine.connect()
    install_engine(engine)
    Base.metadata.create_all(engine)
    return engine


def close_sqlite_auth_database() -> None:
    global _keeper
    keeper = _keeper
    _keeper = None
    if keeper is not None:
        keeper.close()
    reset_engine()
