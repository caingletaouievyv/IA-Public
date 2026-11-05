# IA/backend/scripts/test/test_activity_postgres.py
# Live PostgreSQL activity checks. Skipped unless IA_TEST_DATABASE_URL points at a disposable database.
# These tests refuse Neon hosts and never read DATABASE_URL as their target.

import datetime
import os
import sys
import threading
import time
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.activity import manager
from app.activity import repository
from app.activity.models import ActivityEvent
from app.activity.repository import ActivityStoreError
from app.auth import repository as auth_repository
from app.memories import manager as memories_manager
from app.db import DatabaseConnectionError, install_engine, reset_engine
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
        raise RuntimeError("Refusing to run activity tests against a Neon host.")
    if parsed.drivername not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise RuntimeError("IA_TEST_DATABASE_URL must be a PostgreSQL URL.")
    return url


class PostgresActivityTests(unittest.TestCase):
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
            connection.execute(text("DELETE FROM activity_events"))
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

    def test_activity_catalog(self):
        with self.engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            self.assertEqual(version, "c9a1e4f72b36")
            occurred_type = connection.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'activity_events' "
                    "AND column_name = 'occurred_at'"
                )
            ).scalar()
            self.assertEqual(occurred_type, "timestamp with time zone")
            constraints = {
                name: definition
                for name, definition in connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conrelid = 'public.activity_events'::regclass"
                    )
                )
            }
            self.assertIn(
                "FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE",
                constraints["activity_events_user_id_fkey"],
            )
            self.assertIn("note.created", constraints["activity_events_type_known"])
            index_sql = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = 'activity_events_user_recent'"
                )
            ).scalar()
            self.assertIn("user_id", index_sql)
            self.assertIn("occurred_at", index_sql)

    def test_order_isolation_limit_and_equal_timestamps(self):
        first = manager.record_activity(self.user, "note.created")
        second = manager.record_activity(self.user, "flashcard_deck.created")
        manager.record_activity(self.other, "note.deleted")
        self.assertEqual(
            [event["event_type"] for event in manager.list_activity(self.user)],
            ["flashcard_deck.created", "note.created"],
        )
        self.assertEqual(manager.list_activity(self.user, 1)[0]["event_id"], second["event_id"])
        self.assertEqual(len(manager.list_activity(self.other)), 1)
        moment = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        left = {
            "event_id": "same-time-left",
            "event_type": "note.updated",
            "description": "Note updated",
            "timestamp": moment,
        }
        right = {
            "event_id": "same-time-right",
            "event_type": "note.deleted",
            "description": "Note deleted",
            "timestamp": moment,
        }
        with repository.activity_session() as session:
            repository.insert_event(session, self.user, left, manager.MAX_STORED_EVENTS)
        with repository.activity_session() as session:
            repository.insert_event(session, self.user, right, manager.MAX_STORED_EVENTS)
        newest = manager.list_activity(self.user, 2)
        self.assertEqual([event["event_id"] for event in newest], ["same-time-right", "same-time-left"])
        self.assertEqual(newest[0]["timestamp"], newest[1]["timestamp"])
        self.assertNotIn(first["description"], "private note body")

    def test_retention_rollback_and_concurrent_inserts(self):
        with patch.object(manager, "MAX_STORED_EVENTS", 2):
            manager.record_activity(self.user, "note.created")
            manager.record_activity(self.user, "note.updated")
            manager.record_activity(self.user, "note.deleted")
        self.assertEqual(len(manager.list_activity(self.user, 100)), 2)
        real_insert = repository.insert_event

        def fail_after_insert(session, user_id, event, max_stored):
            real_insert(session, user_id, event, max_stored)
            raise RuntimeError("forced activity failure")

        before = self._count(self.user)
        with patch("app.activity.repository.insert_event", fail_after_insert):
            with self.assertRaisesRegex(RuntimeError, "forced activity failure"):
                manager.record_activity(self.user, "note.created")
        self.assertEqual(self._count(self.user), before)

        errors = []

        def record():
            try:
                manager.record_activity(self.other, "note.updated")
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=record) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(8)
        self.assertEqual(errors, [])
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(self._count(self.other), 12)

    def test_invalid_type_is_rejected_and_files_stay_closed(self):
        with self.assertRaisesRegex(ValueError, "Unsupported activity event type"):
            manager.record_activity(self.user, "settings.changed")
        with patch("builtins.open", side_effect=AssertionError("activity opened a file")):
            stored = manager.record_activity(self.user, "note.created")
        self.assertEqual(manager.list_activity(self.user)[0]["event_id"], stored["event_id"])
        self.assertEqual(self._count(self.user), 1)

    def test_database_errors_omit_connection_details(self):
        bad = create_engine(
            "postgresql+psycopg://activity:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((ActivityStoreError, DatabaseConnectionError)) as caught:
                manager.list_activity(self.user)
        finally:
            install_engine(self.engine)
            bad.dispose()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)

    def _count(self, user_id: str) -> int:
        with repository.activity_session() as session:
            return session.scalar(
                select(func.count()).select_from(ActivityEvent).where(ActivityEvent.user_id == user_id)
            )


class PostgresActivityConcurrencyTests(PostgresActivityTests):
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

    def _advisory_locks(self) -> int:
        with self.engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT count(*) FROM pg_locks AS lock "
                    "JOIN pg_stat_activity AS activity ON activity.pid = lock.pid "
                    "WHERE lock.locktype = 'advisory' "
                    "AND activity.datname = current_database()"
                )
            ).scalar()

    def _backend_pid(self, session) -> int:
        return session.execute(text("SELECT pg_backend_pid()")).scalar()

    def _visible_count(self, user_id: str) -> int:
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT count(*) FROM activity_events WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).scalar()

    def test_concurrent_inserts_keep_the_cap_on_separate_connections(self):
        cap = 4
        total = 12
        base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        errors = []
        pids = []
        peaks = []
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                peaks.append(self._visible_count(self.user))
                time.sleep(0.005)

        def insert(index: int):
            event = {
                "event_id": f"event-{index:02d}",
                "event_type": "note.created",
                "description": "Note created",
                "timestamp": base + datetime.timedelta(seconds=index),
            }
            try:
                with repository.activity_session() as session:
                    pids.append(self._backend_pid(session))
                    repository.insert_event(session, self.user, event, cap)
            except Exception as error:
                errors.append(error)

        watcher = threading.Thread(target=watch)
        watcher.start()
        threads = [threading.Thread(target=insert, args=(index,)) for index in range(total)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(15)
        stop.set()
        watcher.join(2)
        self.assertEqual(errors, [])
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(len(set(pids)), total)
        self.assertGreaterEqual(len(peaks), 1)
        self.assertLessEqual(max(peaks), cap)
        kept = manager.list_activity(self.user, 100)
        self.assertEqual(
            [event["event_id"] for event in kept],
            [f"event-{index:02d}" for index in range(total - 1, total - cap - 1, -1)],
        )
        self.assertEqual(self._count(self.user), cap)

    def test_different_users_insert_while_one_lock_is_held(self):
        hold = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        errors = []
        pids = []

        def hold_owner():
            try:
                with repository.activity_session() as session:
                    pids.append(self._backend_pid(session))
                    repository._lock_user_activity(session, self.user)
                    hold.set()
                    if not release.wait(8):
                        raise TimeoutError("activity lock holder was not released")
            except Exception as error:
                errors.append(error)

        def other_owner():
            try:
                with repository.activity_session() as session:
                    pids.append(self._backend_pid(session))
                    repository.insert_event(
                        session,
                        self.other,
                        {
                            "event_id": "other-user-event",
                            "event_type": "note.created",
                            "description": "Note created",
                            "timestamp": datetime.datetime.now(datetime.timezone.utc),
                        },
                        manager.MAX_STORED_EVENTS,
                    )
            except Exception as error:
                errors.append(error)
            finished.set()

        holder = threading.Thread(target=hold_owner)
        other = threading.Thread(target=other_owner)
        holder.start()
        self.assertTrue(hold.wait(8))
        other.start()
        try:
            self.assertTrue(finished.wait(5), "a different user waited on this user's activity lock")
            self.assertEqual(self._advisory_waiters(), 0)
        finally:
            release.set()
        holder.join(8)
        other.join(8)
        self.assertFalse(holder.is_alive())
        self.assertFalse(other.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(set(pids)), 2)
        self.assertEqual(self._count(self.other), 1)
        self.assertEqual(self._advisory_locks(), 0)

    def test_activity_lock_does_not_block_the_same_users_memories(self):
        hold = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        errors = []

        def hold_activity():
            try:
                with repository.activity_session() as session:
                    repository._lock_user_activity(session, self.user)
                    hold.set()
                    if not release.wait(8):
                        raise TimeoutError("activity lock holder was not released")
            except Exception as error:
                errors.append(error)

        def write_memory():
            try:
                memories_manager.add_or_update_memories(
                    self.user,
                    [{"text": "The user likes rain.", "explicit_remember": True}],
                )
            except Exception as error:
                errors.append(error)
            finished.set()

        holder = threading.Thread(target=hold_activity)
        writer = threading.Thread(target=write_memory)
        holder.start()
        self.assertTrue(hold.wait(8))
        writer.start()
        try:
            self.assertTrue(finished.wait(5), "a memory write waited on the activity lock")
        finally:
            release.set()
        holder.join(8)
        writer.join(8)
        self.assertFalse(holder.is_alive())
        self.assertFalse(writer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(memories_manager.load_memories(self.user)), 1)

    def test_failed_trim_rolls_back_and_releases_the_lock(self):
        hold = threading.Event()
        release = threading.Event()
        errors = []
        real_insert = repository.insert_event
        failed_id = "fail-trim"

        def fail_after_trim(session, user_id, event, max_stored):
            stored = real_insert(session, user_id, event, max_stored)
            if event["event_id"] != failed_id:
                return stored
            hold.set()
            if not release.wait(8):
                raise TimeoutError("activity lock holder was not released")
            raise RuntimeError("forced trim failure")

        def fail():
            try:
                with repository.activity_session() as session:
                    repository.insert_event(
                        session,
                        self.user,
                        {
                            "event_id": failed_id,
                            "event_type": "note.created",
                            "description": "Note created",
                            "timestamp": datetime.datetime.now(datetime.timezone.utc),
                        },
                        manager.MAX_STORED_EVENTS,
                    )
            except Exception as error:
                errors.append(error)

        def later():
            try:
                manager.record_activity(self.user, "note.updated")
            except Exception as error:
                errors.append(error)

        with patch("app.activity.repository.insert_event", fail_after_trim):
            first = threading.Thread(target=fail)
            second = threading.Thread(target=later)
            first.start()
            self.assertTrue(hold.wait(8))
            second.start()
            try:
                self._wait_until(lambda: self._advisory_waiters() >= 1, "later insert did not wait for the user lock")
            finally:
                release.set()
            first.join(8)
            second.join(8)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(str(errors[0]), "forced trim failure")
        self.assertEqual(self._count(self.user), 1)
        self.assertNotIn(failed_id, [event["event_id"] for event in manager.list_activity(self.user, 10)])
        self.assertEqual(self._advisory_waiters(), 0)
        self.assertEqual(self._advisory_locks(), 0)
        manager.record_activity(self.user, "note.deleted")
        self.assertEqual(self._count(self.user), 2)


if __name__ == "__main__":
    unittest.main()
