# IA/backend/scripts/test/test_settings_postgres.py
# Live PostgreSQL settings checks. Skipped unless IA_TEST_DATABASE_URL points at a disposable database.
# These tests refuse Neon hosts and never read DATABASE_URL as their target.

import os
import sys
import threading
import time
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.auth import repository as auth_repository
from app.db import DatabaseConnectionError, install_engine, reset_engine
from app.settings import manager
from app.settings import repository
from app.settings.repository import SettingsStoreError
from scripts.test.pg_migrate import run_auth_migrations

_TEST_URL_ENV = "IA_TEST_DATABASE_URL"


def _disposable_postgres_url() -> str | None:
    url = (os.getenv(_TEST_URL_ENV) or "").strip()
    if not url:
        return None
    if url == (os.getenv("DATABASE_URL") or "").strip():
        raise RuntimeError("Refusing to use DATABASE_URL as the PostgreSQL test target.")
    parsed = make_url(url)
    host = (parsed.host or "").lower()
    if "neon.tech" in host or "neon.tech" in url.lower():
        raise RuntimeError("Refusing to run settings tests against a Neon host.")
    if parsed.drivername not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise RuntimeError("IA_TEST_DATABASE_URL must be a PostgreSQL URL.")
    return url


class PostgresSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = _disposable_postgres_url()
        if url is None:
            raise unittest.SkipTest("IA_TEST_DATABASE_URL is not set")
        cls.engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True)
        install_engine(cls.engine)
        with cls.engine.connect() as connection:
            run_auth_migrations(connection)

    @classmethod
    def tearDownClass(cls):
        reset_engine()
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM settings"))
        self.user = self._owner()
        self.other = self._owner()

    def _owner(self) -> str:
        user_id = str(uuid.uuid4())
        with auth_repository.auth_session() as session:
            auth_repository.insert_user(
                session,
                user_id=user_id,
                username=user_id,
                password_hash="test-hash",
                role="user",
            )
        return user_id

    def _wait_until(self, predicate, message: str, timeout: float = 5) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.fail(message)

    def _advisory_waiters(self) -> int:
        with self.engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid() "
                    "AND wait_event_type = 'Lock' "
                    "AND wait_event = 'advisory'"
                )
            ).scalar()

    def test_settings_catalog(self):
        with self.engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            self.assertEqual(version, "c9a1e4f72b36")
            constraints = {
                name: definition
                for name, definition in connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conrelid = 'public.settings'::regclass"
                    )
                )
            }
            self.assertIn(
                "FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE",
                constraints["settings_user_id_fkey"],
            )
            column_type = connection.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'settings' "
                    "AND column_name = 'preferences'"
                )
            ).scalar()
            self.assertEqual(column_type, "jsonb")

    def test_merge_types_isolation_and_no_files(self):
        saved = manager.save_settings(
            self.user,
            {
                "theme": "dark",
                "limit": 3,
                "memory_enabled": False,
                "ask_context_modes": {"notes": "automatic"},
            },
        )
        self.assertEqual(saved["limit"], 3)
        self.assertIs(saved["memory_enabled"], False)
        again = manager.save_settings(self.user, {"remember_command_enabled": True})
        self.assertEqual(again["theme"], "dark")
        self.assertEqual(again["ask_context_modes"], {"notes": "automatic"})
        self.assertIs(again["remember_command_enabled"], True)
        self.assertEqual(manager.get_settings(self.other), {})
        with patch("builtins.open", side_effect=AssertionError("settings opened a file")):
            self.assertEqual(manager.get_settings(self.user)["theme"], "dark")

    def test_concurrent_key_updates_keep_both_values(self):
        hold = threading.Event()
        release = threading.Event()
        errors = []
        real_merge = repository.merge_settings

        def paused(session, user_id, data):
            if "theme" in data:
                hold.set()
                if not release.wait(8):
                    raise TimeoutError("settings lock holder was not released")
            return real_merge(session, user_id, data)

        def save(data):
            try:
                manager.save_settings(self.user, data)
            except Exception as error:
                errors.append(error)

        with patch("app.settings.manager.merge_settings", paused):
            first = threading.Thread(target=save, args=({"theme": "dark"},))
            second = threading.Thread(target=save, args=({"limit": 2},))
            first.start()
            self.assertTrue(hold.wait(8))
            second.start()
            try:
                self._wait_until(
                    lambda: self._advisory_waiters() >= 1,
                    "second settings update did not wait for the user lock",
                )
            finally:
                release.set()
            first.join(8)
            second.join(8)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        stored = manager.get_settings(self.user)
        self.assertEqual(stored["theme"], "dark")
        self.assertEqual(stored["limit"], 2)

    def test_failed_update_rolls_back_and_releases_the_lock(self):
        manager.save_settings(self.user, {"theme": "dark"})
        hold = threading.Event()
        release = threading.Event()
        errors = []
        real_merge = repository.merge_settings

        def fail_once(session, user_id, data):
            if data.get("limit") == 9:
                merged = real_merge(session, user_id, data)
                hold.set()
                if not release.wait(8):
                    raise TimeoutError("settings lock holder was not released")
                raise RuntimeError("forced settings failure")
            return real_merge(session, user_id, data)

        def fail_update():
            try:
                manager.save_settings(self.user, {"limit": 9})
            except Exception as error:
                errors.append(error)

        def later_update():
            try:
                manager.save_settings(self.user, {"show_context_source_labels": False})
            except Exception as error:
                errors.append(error)

        with patch("app.settings.manager.merge_settings", fail_once):
            first = threading.Thread(target=fail_update)
            second = threading.Thread(target=later_update)
            first.start()
            self.assertTrue(hold.wait(8))
            second.start()
            try:
                self._wait_until(
                    lambda: self._advisory_waiters() >= 1,
                    "later settings update did not wait for the user lock",
                )
            finally:
                release.set()
            first.join(8)
            second.join(8)
        self.assertEqual(len(errors), 1)
        self.assertEqual(str(errors[0]), "forced settings failure")
        stored = manager.get_settings(self.user)
        self.assertEqual(stored["theme"], "dark")
        self.assertNotIn("limit", stored)
        self.assertIs(stored["show_context_source_labels"], False)

    def test_database_errors_omit_connection_details(self):
        bad = create_engine(
            "postgresql+psycopg://settings:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((SettingsStoreError, DatabaseConnectionError)) as caught:
                manager.get_settings(self.user)
        finally:
            install_engine(self.engine)
            bad.dispose()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)


if __name__ == "__main__":
    unittest.main()
