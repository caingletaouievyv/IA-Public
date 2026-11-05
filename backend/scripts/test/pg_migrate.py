# IA/backend/scripts/test/pg_migrate.py
# Run Alembic revisions on a connection the caller already opened.

from pathlib import Path

from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory

import app.diagnostics.models  # noqa: F401  # diagnostics revisions share this metadata
import app.activity.models  # noqa: F401  # activity revisions share this metadata
import app.credits.models  # noqa: F401  # credit revisions share this metadata
import app.memories.models  # noqa: F401  # memory revisions share this metadata
import app.settings.models  # noqa: F401  # settings revisions share this metadata
import app.notes.models  # noqa: F401  # notes revisions share this metadata
from app.auth.models import Base

_BACKEND = Path(__file__).resolve().parents[2]


def run_auth_migrations(connection, *, downgrade: bool = False, fail_after_upgrade: bool = False) -> None:
    """Upgrade to head, or downgrade to base, inside one transactional DDL transaction."""
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    script = ScriptDirectory.from_config(config)
    destination = "base" if downgrade else "head"
    # A connection that already executed SQL is in a transaction. Commit it so
    # Alembic's BEGIN is the root transaction and close() cannot roll the revision back.
    if connection.in_transaction():
        connection.commit()

    def _steps(revision, _context):
        if downgrade:
            steps = list(script._downgrade_revs(destination, revision))
        else:
            steps = list(script._upgrade_revs(destination, revision))
        if fail_after_upgrade:
            for step in steps:
                original = step.migration_fn

                def _fail(fn=original, **kwargs):
                    fn(**kwargs)
                    raise RuntimeError("forced migration failure")

                step.migration_fn = _fail
        return steps

    with EnvironmentContext(
        config,
        script,
        fn=_steps,
        as_sql=False,
        destination_rev=destination,
    ) as env:
        env.configure(connection=connection, target_metadata=Base.metadata)
        with env.begin_transaction():
            env.run_migrations()
    if connection.in_transaction():
        connection.commit()

