# IA/backend/alembic/env.py
# Migration runtime. Reads DATABASE_URL and does not print it.

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

load_dotenv(_REPO / ".env")
load_dotenv()

import app.diagnostics.models  # noqa: F401  # register diagnostics on the shared metadata
import app.activity.models  # noqa: F401  # register activity on the shared metadata
import app.credits.models  # noqa: F401  # register credits on the shared metadata
import app.memories.models  # noqa: F401  # register memories on the shared metadata
import app.settings.models  # noqa: F401  # register settings on the shared metadata
import app.notes.models  # noqa: F401  # register notes on the shared metadata
from app.auth.models import Base
from app.db import migration_connection, require_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=require_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with migration_connection() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
