# IA/backend/scripts/test/test_memories_postgres.py
# Live PostgreSQL memory checks. Skipped unless IA_TEST_DATABASE_URL points at a disposable database.
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
from app.memories import extraction, manager
from app.memories import repository
from app.memories.repository import MemoryStoreError
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
        raise RuntimeError("Refusing to run memory tests against a Neon host.")
    if parsed.drivername not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise RuntimeError("IA_TEST_DATABASE_URL must be a PostgreSQL URL.")
    return url


class PostgresMemoryTests(unittest.TestCase):
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
            connection.execute(text("DELETE FROM memories"))
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

    def test_memories_catalog(self):
        with self.engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            self.assertEqual(version, "c9a1e4f72b36")
            constraints = {
                name: definition
                for name, definition in connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conrelid = 'public.memories'::regclass"
                    )
                )
            }
            self.assertIn(
                "FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE",
                constraints["memories_user_id_fkey"],
            )
            self.assertIn("length(text)", constraints["memories_text_bounds"])
            self.assertIn("assistant.name", constraints["memories_key_known"])
            self.assertIn("UNIQUE (user_id, seq)", constraints["memories_user_seq"])
            index_sql = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = 'memories_user_key'"
                )
            ).scalar()
            self.assertIn("(user_id, memory_key)", index_sql)

    def test_crud_dedup_ranking_extraction_and_isolation(self):
        created = manager.add_or_update_memories(
            self.user,
            [{"text": "The user prefers concise answers about Python.", "explicit_remember": True}],
        )
        self.assertEqual(created["added"], 1)
        duplicate = manager.add_or_update_memories(
            self.user,
            [{"text": "The user prefers concise answers about Python.", "explicit_remember": True}],
        )
        self.assertEqual(duplicate["added"], 0)
        self.assertEqual(len(manager.list_memories(self.user)), 1)

        status = extraction.extract_and_save(self.user, "From now on, call yourself Atlas.")
        self.assertEqual(status, "saved")
        owned = manager.list_memories(self.user)
        self.assertEqual(len(owned), 2)
        name = next(item for item in owned if item.get("key") == "assistant.name")
        self.assertIn("Atlas", name["text"])
        self.assertIsNone(manager.update_memory(self.other, name["id"], "The user lives in Rome."))
        self.assertEqual(manager.list_memories(self.other), [])

        with patch("app.ai.client.call_ai", return_value='{"memory_key": null}'):
            ranked = manager.retrieve_memories(self.user, "How should you answer my Python question?")
        self.assertEqual(
            [item["text"] for item in ranked],
            ["The user prefers concise answers about Python."],
        )
        self.assertTrue(manager.delete_memory(self.user, name["id"]))
        self.assertEqual(manager.clear_memories(self.user), 1)
        self.assertEqual(manager.load_memories(self.user), [])

    def test_database_errors_omit_connection_details(self):
        with self.assertRaises(MemoryStoreError) as caught:
            manager._save_memories(self.user, [{
                "id": str(uuid.uuid4()),
                "text": "",
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            }])
        self.assertEqual(str(caught.exception), "Could not access memories.")
        self.assertNotIn("://", repr(caught.exception))

        bad = create_engine(
            "postgresql+psycopg://memories:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((MemoryStoreError, DatabaseConnectionError)) as caught:
                manager.load_memories(self.user)
        finally:
            install_engine(self.engine)
            bad.dispose()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)

    def test_memories_do_not_open_files(self):
        with patch("builtins.open", side_effect=AssertionError("memories opened a file")):
            manager.add_or_update_memories(
                self.user,
                [{"text": "The user likes rain.", "explicit_remember": True}],
            )
            self.assertEqual(len(manager.load_memories(self.user)), 1)


class PostgresMemoryConcurrencyTests(PostgresMemoryTests):
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

    def _pause_first_lock(self, user_id: str, hold: threading.Event, release: threading.Event, *, fail: bool = False):
        real_lock = repository._lock_user_memories
        state = {"n": 0}

        def wrapped(session, locked_user_id):
            real_lock(session, locked_user_id)
            if locked_user_id != user_id:
                return
            state["n"] += 1
            if state["n"] != 1:
                return
            hold.set()
            if not release.wait(8):
                raise TimeoutError("memory lock holder was not released")
            if fail:
                raise RuntimeError("forced memory failure")

        return patch("app.memories.repository._lock_user_memories", wrapped)

    def test_concurrent_adds_keep_both_memories(self):
        hold = threading.Event()
        release = threading.Event()
        reads = []
        errors = []
        real_list = manager.list_memory_rows
        first = "The user likes rain."
        second = "The user likes tea."

        def listed(session, user_id):
            rows = real_list(session, user_id)
            if user_id != self.user:
                return rows
            reads.append([item["text"] for item in rows])
            if len(reads) == 1:
                hold.set()
                if not release.wait(8):
                    raise TimeoutError("memory lock holder was not released")
            return rows

        def add(text):
            try:
                manager.add_or_update_memories(
                    self.user,
                    [{"text": text, "explicit_remember": True}],
                )
            except Exception as error:
                errors.append(error)

        with patch("app.memories.manager.list_memory_rows", listed):
            first_thread = threading.Thread(target=add, args=(first,))
            second_thread = threading.Thread(target=add, args=(second,))
            first_thread.start()
            self.assertTrue(hold.wait(8))
            second_thread.start()
            try:
                self._wait_until(lambda: self._advisory_waiters() >= 1, "second add did not wait for the user lock")
                self.assertEqual(reads, [[]])
            finally:
                release.set()
            first_thread.join(8)
            second_thread.join(8)
        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(reads[1], [first])
        self.assertEqual(
            {item["text"] for item in manager.load_memories(self.user)},
            {first, second},
        )

    def test_concurrent_replacements_stay_consistent(self):
        hold = threading.Event()
        release = threading.Event()
        errors = []
        stamp = "2024-01-01T00:00:00+00:00"

        def row(memory_id: str, text: str) -> dict:
            return {"id": memory_id, "text": text, "created_at": stamp, "updated_at": stamp}

        first_rows = [row("alpha-id", "The user likes alpha."), row("beta-id", "The user likes beta.")]
        second_rows = [row("gamma-id", "The user likes gamma.")]

        def replace(rows):
            try:
                manager._save_memories(self.user, rows)
            except Exception as error:
                errors.append(error)

        with self._pause_first_lock(self.user, hold, release):
            first_thread = threading.Thread(target=replace, args=(first_rows,))
            second_thread = threading.Thread(target=replace, args=(second_rows,))
            first_thread.start()
            self.assertTrue(hold.wait(8))
            second_thread.start()
            try:
                self._wait_until(
                    lambda: self._advisory_waiters() >= 1,
                    "second replacement did not wait for the user lock",
                )
            finally:
                release.set()
            first_thread.join(8)
            second_thread.join(8)
        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(errors, [])
        stored = manager.load_memories(self.user)
        self.assertEqual([item["id"] for item in stored], ["gamma-id"])
        self.assertEqual([item["text"] for item in stored], ["The user likes gamma."])

    def test_different_users_do_not_block_each_other(self):
        hold = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        errors = []

        def hold_owner():
            try:
                manager.add_or_update_memories(
                    self.user,
                    [{"text": "The user likes rain.", "explicit_remember": True}],
                )
            except Exception as error:
                errors.append(error)

        def other_owner():
            try:
                manager.add_or_update_memories(
                    self.other,
                    [{"text": "The user likes tea.", "explicit_remember": True}],
                )
            except Exception as error:
                errors.append(error)
            finished.set()

        with self._pause_first_lock(self.user, hold, release):
            holder = threading.Thread(target=hold_owner)
            other = threading.Thread(target=other_owner)
            holder.start()
            self.assertTrue(hold.wait(8))
            other.start()
            try:
                self.assertTrue(finished.wait(5), "a different user waited on this user's memory lock")
            finally:
                release.set()
            holder.join(8)
            other.join(8)
        self.assertFalse(holder.is_alive())
        self.assertFalse(other.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(manager.load_memories(self.user)), 1)
        self.assertEqual(len(manager.load_memories(self.other)), 1)

    def test_failed_operation_rolls_back_and_next_write_succeeds(self):
        hold = threading.Event()
        release = threading.Event()
        errors = []
        failed_text = "The user likes rain."
        later_text = "The user likes tea."

        def fail_add():
            try:
                manager.add_or_update_memories(
                    self.user,
                    [{"text": failed_text, "explicit_remember": True}],
                )
            except Exception as error:
                errors.append(error)

        def later_add():
            try:
                manager.add_or_update_memories(
                    self.user,
                    [{"text": later_text, "explicit_remember": True}],
                )
            except Exception as error:
                errors.append(error)

        with self._pause_first_lock(self.user, hold, release, fail=True):
            first_thread = threading.Thread(target=fail_add)
            second_thread = threading.Thread(target=later_add)
            first_thread.start()
            self.assertTrue(hold.wait(8))
            second_thread.start()
            try:
                self._wait_until(lambda: self._advisory_waiters() >= 1, "later add did not wait for the user lock")
            finally:
                release.set()
            first_thread.join(8)
            second_thread.join(8)
        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(str(errors[0]), "forced memory failure")
        self.assertEqual(
            [item["text"] for item in manager.load_memories(self.user)],
            [later_text],
        )


if __name__ == "__main__":
    unittest.main()
