# IA/backend/scripts/test/test_diagnostics_postgres.py
# Live PostgreSQL diagnostics checks. Skipped unless IA_TEST_DATABASE_URL points at a disposable database.
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

from app.activity import manager as activity_manager
from app.auth import repository as auth_repository
from app.db import DatabaseConnectionError, install_engine, reset_engine
from app.diagnostics import manager
from app.diagnostics import repository
from app.diagnostics.models import DiagnosticEvent
from app.diagnostics.repository import DiagnosticsStoreError
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
        raise RuntimeError("Refusing to run diagnostics tests against a Neon host.")
    if parsed.drivername not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise RuntimeError("IA_TEST_DATABASE_URL must be a PostgreSQL URL.")
    return url


def _event(user_id: str, *, kind: str = "automatic", operation_id: str | None = None, timestamp=None, **extra):
    event = {
        "event_id": extra.pop("event_id", str(uuid.uuid4())),
        "timestamp": timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "kind": kind,
        "feature": "ask",
        "code": "ask.operation_failed",
        "category": "provider_failure",
        "fallback": "generic_error",
        "error_type": "RuntimeError",
        "user_key_prefix": manager.user_key_prefix(user_id),
    }
    if kind == "user_report":
        event["feedback_reason"] = extra.pop("feedback_reason", "wrong")
        event["operation_id"] = operation_id or "op-1"
        event["code"] = "ask.feedback.reported"
        event["error_type"] = "none"
    event.update(extra)
    return event


class PostgresDiagnosticsTests(unittest.TestCase):
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
            connection.execute(text("DELETE FROM diagnostic_events"))
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

    def test_diagnostics_catalog(self):
        with self.engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            self.assertEqual(version, "c9a1e4f72b36")
            occurred_type = connection.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'diagnostic_events' "
                    "AND column_name = 'occurred_at'"
                )
            ).scalar()
            self.assertEqual(occurred_type, "timestamp with time zone")
            constraints = {
                name: definition
                for name, definition in connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conrelid = 'public.diagnostic_events'::regclass"
                    )
                )
            }
            self.assertIn(
                "FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE",
                constraints["diagnostic_events_user_id_fkey"],
            )
            self.assertIn("user_report", constraints["diagnostic_events_kind_known"])
            self.assertIn("feedback_reason", constraints["diagnostic_events_report_reason"])
            for index_name in ("diagnostic_events_user_recent", "diagnostic_events_recent"):
                index_sql = connection.execute(
                    text(
                        "SELECT indexdef FROM pg_indexes "
                        "WHERE schemaname = 'public' AND indexname = :index_name"
                    ),
                    {"index_name": index_name},
                ).scalar()
                self.assertIn("occurred_at", index_sql)

    def test_order_isolation_duplicate_and_payload(self):
        base = datetime.datetime.now(datetime.timezone.utc)
        first = _event(self.user, timestamp=base.isoformat(), provider="groq", memory_enabled=False)
        second = _event(
            self.user,
            timestamp=(base + datetime.timedelta(seconds=1)).isoformat(),
            memory_enabled=True,
        )
        manager.record_event(self.user, first)
        manager.record_event(self.user, second)
        manager.record_event(self.other, _event(self.other))
        listed = manager.list_events_for_user(self.user, 10)
        self.assertEqual([event["event_id"] for event in listed], [second["event_id"], first["event_id"]])
        self.assertEqual(listed[0]["memory_enabled"], True)
        self.assertEqual(listed[1]["provider"], "groq")
        self.assertEqual(listed[1]["memory_enabled"], False)
        self.assertEqual(len(manager.list_events_admin(limit=1)), 1)
        report = _event(self.user, kind="user_report", operation_id="shared-op")
        repeat = _event(self.user, kind="user_report", operation_id="shared-op", feedback_reason="other")
        stored = manager.record_event(self.user, report)
        again = manager.record_event(self.user, repeat)
        self.assertEqual(again["event_id"], stored["event_id"])
        self.assertEqual(self._count(self.user, kind="user_report"), 1)
        manager.record_event(self.other, _event(self.other, kind="user_report", operation_id="shared-op"))
        self.assertEqual(self._count(self.other, kind="user_report"), 1)

    def test_equal_timestamps_retention_and_cap(self):
        moment = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
        left = _event(self.user, timestamp=moment, event_id="same-time-left")
        right = _event(self.user, timestamp=moment, event_id="same-time-right")
        manager.record_event(self.user, left)
        manager.record_event(self.user, right)
        newest = manager.list_events_for_user(self.user, 2)
        self.assertEqual([event["event_id"] for event in newest], ["same-time-right", "same-time-left"])
        self.assertEqual(newest[0]["timestamp"], newest[1]["timestamp"])
        aged = self._owner()
        old = _event(
            aged,
            timestamp=(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10)).isoformat(),
        )
        with patch.object(manager, "DIAGNOSTICS_RETENTION_DAYS", 1):
            manager.record_event(aged, old)
            self.assertEqual(manager.list_events_for_user(aged, 10), [])
            fresh = _event(aged)
            manager.record_event(aged, fresh)
        self.assertEqual(self._count(aged), 1)
        with patch.object(manager, "DIAGNOSTICS_MAX_EVENTS_PER_USER", 2):
            manager.record_event(self.other, _event(self.other))
            manager.record_event(self.other, _event(self.other))
            manager.record_event(self.other, _event(self.other))
        self.assertEqual(self._count(self.other), 2)

    def test_invalid_input_and_files_stay_closed(self):
        broken = _event(self.user)
        broken["kind"] = "other"
        with self.assertRaisesRegex(ValueError, "invalid"):
            manager.record_event(self.user, broken)
        with patch("builtins.open", side_effect=AssertionError("diagnostics opened a file")):
            stored = manager.record_event(self.user, _event(self.user))
        self.assertEqual(manager.list_events_for_user(self.user)[0]["event_id"], stored["event_id"])

    def test_database_errors_omit_connection_details(self):
        bad = create_engine(
            "postgresql+psycopg://diagnostics:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((DiagnosticsStoreError, DatabaseConnectionError)) as caught:
                manager.list_events_admin()
        finally:
            install_engine(self.engine)
            bad.dispose()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)

    def _count(self, user_id: str, kind: str | None = None) -> int:
        with repository.diagnostics_session() as session:
            statement = select(func.count()).select_from(DiagnosticEvent).where(DiagnosticEvent.user_id == user_id)
            if kind is not None:
                statement = statement.where(DiagnosticEvent.kind == kind)
            return session.scalar(statement)


class PostgresDiagnosticsConcurrencyTests(PostgresDiagnosticsTests):
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

    def _visible_count(self, user_id: str) -> int:
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT count(*) FROM diagnostic_events WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).scalar()

    def test_concurrent_inserts_keep_the_cap_on_separate_connections(self):
        cap = 4
        total = 12
        base = datetime.datetime.now(datetime.timezone.utc)
        errors = []
        pids = []
        peaks = []
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                peaks.append(self._visible_count(self.user))
                time.sleep(0.005)

        def insert(index: int):
            event = _event(
                self.user,
                event_id=f"event-{index:02d}",
                timestamp=(base + datetime.timedelta(seconds=index)).isoformat(),
            )
            try:
                with repository.diagnostics_session() as session:
                    pids.append(session.execute(text("SELECT pg_backend_pid()")).scalar())
                    repository.insert_event(session, self.user, event, cap, 0)
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
        self.assertLessEqual(max(peaks), cap)
        kept = manager.list_events_for_user(self.user, 100)
        self.assertEqual(
            [event["event_id"] for event in kept],
            [f"event-{index:02d}" for index in range(total - 1, total - cap - 1, -1)],
        )

    def test_concurrent_feedback_keeps_one_event(self):
        errors = []
        stored = []

        def record(index: int):
            try:
                stored.append(
                    manager.record_event(
                        self.user,
                        _event(self.user, kind="user_report", operation_id="same-op", event_id=f"report-{index}"),
                    )
                )
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=record, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(8)
        self.assertEqual(errors, [])
        self.assertEqual(len({event["event_id"] for event in stored}), 1)
        self.assertEqual(self._count(self.user), 1)

    def test_different_users_insert_while_one_lock_is_held(self):
        hold = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        errors = []

        def hold_owner():
            try:
                with repository.diagnostics_session() as session:
                    repository._lock_user_diagnostics(session, self.user)
                    hold.set()
                    if not release.wait(8):
                        raise TimeoutError("diagnostics lock holder was not released")
            except Exception as error:
                errors.append(error)

        def other_owner():
            try:
                manager.record_event(self.other, _event(self.other))
                activity_manager.record_activity(self.user, "note.created")
            except Exception as error:
                errors.append(error)
            finished.set()

        holder = threading.Thread(target=hold_owner)
        other = threading.Thread(target=other_owner)
        holder.start()
        self.assertTrue(hold.wait(8))
        other.start()
        try:
            self.assertTrue(finished.wait(5), "another write waited on this user's diagnostics lock")
        finally:
            release.set()
        holder.join(8)
        other.join(8)
        self.assertEqual(errors, [])
        self.assertEqual(self._count(self.other), 1)
        self.assertEqual(self._advisory_locks(), 0)

    def test_failed_write_rolls_back_and_releases_the_lock(self):
        hold = threading.Event()
        release = threading.Event()
        errors = []
        real_insert = repository.insert_event

        def fail_after_insert(session, user_id, event, max_stored, retention_days):
            stored = real_insert(session, user_id, event, max_stored, retention_days)
            if event["event_id"] != "fail-trim":
                return stored
            hold.set()
            if not release.wait(8):
                raise TimeoutError("diagnostics lock holder was not released")
            raise RuntimeError("forced trim failure")

        def fail():
            try:
                with repository.diagnostics_session() as session:
                    repository.insert_event(
                        session,
                        self.user,
                        _event(self.user, event_id="fail-trim"),
                        manager.DIAGNOSTICS_MAX_EVENTS_PER_USER,
                        manager.DIAGNOSTICS_RETENTION_DAYS,
                    )
            except Exception as error:
                errors.append(error)

        def later():
            try:
                manager.record_event(self.user, _event(self.user, event_id="after-failure"))
            except Exception as error:
                errors.append(error)

        with patch("app.diagnostics.repository.insert_event", fail_after_insert):
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
        self.assertEqual([str(error) for error in errors], ["forced trim failure"])
        self.assertEqual(self._count(self.user), 1)
        self.assertEqual(manager.list_events_for_user(self.user, 10)[0]["event_id"], "after-failure")
        self.assertEqual(self._advisory_waiters(), 0)
        self.assertEqual(self._advisory_locks(), 0)
        with auth_repository.auth_session() as session:
            session.execute(text("DELETE FROM users WHERE user_id = :user_id"), {"user_id": self.user})
        self.assertEqual(self._count(self.user), 0)


if __name__ == "__main__":
    unittest.main()
