# IA/backend/scripts/test/test_pending_postgres.py
# Live PostgreSQL Ask confirmation checks. Skipped unless IA_TEST_DATABASE_URL points at a disposable database.
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

from app.auth import repository as auth_repository
from app.db import DatabaseConnectionError, install_engine, reset_engine
from app.notes import create_pending, delete_pending
from app.notes import pending_repository as repository
from app.notes.models import AskPendingConfirmation
from app.notes.pending_repository import PendingStoreError
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
        raise RuntimeError("Refusing to run pending confirmation tests against a Neon host.")
    if parsed.drivername not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise RuntimeError("IA_TEST_DATABASE_URL must be a PostgreSQL URL.")
    return url


class PostgresPendingTests(unittest.TestCase):
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
            connection.execute(text("DELETE FROM ask_pending_confirmations"))
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

    def test_pending_catalog(self):
        with self.engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            self.assertEqual(version, "c9a1e4f72b36")
            expires_type = connection.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'ask_pending_confirmations' "
                    "AND column_name = 'expires_at'"
                )
            ).scalar()
            self.assertEqual(expires_type, "timestamp with time zone")
            constraints = {
                name: definition
                for name, definition in connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conrelid = 'public.ask_pending_confirmations'::regclass"
                    )
                )
            }
            self.assertIn(
                "FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE",
                constraints["ask_pending_confirmations_user_id_fkey"],
            )
            self.assertIn("PRIMARY KEY (user_id, kind)", constraints["ask_pending_confirmations_pkey"])
            self.assertIn("create", constraints["ask_pending_confirmations_kind_known"])
            index_sql = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = 'ask_pending_confirmations_expires'"
                )
            ).scalar()
            self.assertIn("expires_at", index_sql)

    def test_isolation_expiry_and_one_consume(self):
        create_pending.set_pending_create(self.user, need_title=True, need_content=False, title="Mine")
        delete_pending.set_pending_delete(self.user, "note-1", "Mine")
        delete_pending.set_pending_delete(self.other, "note-2", "Theirs")
        self.assertEqual(create_pending.get_pending_create(self.user)["title"], "Mine")
        self.assertEqual(delete_pending.get_pending_delete(self.user)["note_id"], "note-1")
        self.assertEqual(delete_pending.get_pending_delete(self.other)["note_id"], "note-2")
        self.assertIsNone(delete_pending.consume_pending_delete(self.user, match_title="mine"))
        consumed = delete_pending.consume_pending_delete(self.user, match_title="Mine")
        self.assertEqual(consumed["note_id"], "note-1")
        self.assertIsNone(delete_pending.consume_pending_delete(self.user, match_title="Mine"))
        self.assertEqual(delete_pending.get_pending_delete(self.other)["expected_title"], "Theirs")
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=create_pending.TTL_SECONDS + 5)
        with patch("app.notes.pending_repository._now", return_value=future):
            self.assertIsNone(create_pending.get_pending_create(self.user))
        self.assertEqual(self._count(self.user, repository.KIND_CREATE), 0)

    def test_database_errors_omit_connection_details(self):
        bad = create_engine(
            "postgresql+psycopg://pending:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((PendingStoreError, DatabaseConnectionError)) as caught:
                delete_pending.get_pending_delete(self.user)
        finally:
            install_engine(self.engine)
            bad.dispose()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)

    def _count(self, user_id: str, kind: str | None = None) -> int:
        with repository.pending_session() as session:
            statement = select(func.count()).select_from(AskPendingConfirmation).where(
                AskPendingConfirmation.user_id == user_id
            )
            if kind is not None:
                statement = statement.where(AskPendingConfirmation.kind == kind)
            return session.scalar(statement)


class PostgresPendingConcurrencyTests(PostgresPendingTests):
    def _wait_until(self, predicate, message: str, timeout: float = 5) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.fail(message)

    def test_only_one_concurrent_consumer_succeeds(self):
        delete_pending.set_pending_delete(self.user, "note-1", "Once")
        errors = []
        results = []
        pids = []
        barrier = threading.Barrier(2)

        def consume():
            try:
                barrier.wait(5)
                with repository.pending_session() as session:
                    pids.append(session.execute(text("SELECT pg_backend_pid()")).scalar())
                    results.append(
                        repository.consume_pending(session, self.user, repository.KIND_DELETE, match_title="Once")
                    )
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=consume) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(8)
        self.assertEqual(errors, [])
        self.assertEqual(len(set(pids)), 2)
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(self._count(self.user), 0)

    def test_different_user_consumes_while_one_row_is_locked(self):
        delete_pending.set_pending_delete(self.user, "note-1", "Held")
        delete_pending.set_pending_delete(self.other, "note-2", "Free")
        hold = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        errors = []
        real_lock = repository._locked
        state = {"n": 0}

        def pause_first(session, user_id, kind):
            row = real_lock(session, user_id, kind)
            if user_id != self.user or kind != repository.KIND_DELETE:
                return row
            state["n"] += 1
            if state["n"] != 1:
                return row
            hold.set()
            if not release.wait(8):
                raise TimeoutError("pending lock holder was not released")
            return row

        def hold_owner():
            try:
                delete_pending.consume_pending_delete(self.user, match_title="Held")
            except Exception as error:
                errors.append(error)

        def other_owner():
            try:
                consumed = delete_pending.consume_pending_delete(self.other, match_title="Free")
                if consumed is None:
                    raise RuntimeError("other user did not consume")
            except Exception as error:
                errors.append(error)
            finished.set()

        holder = threading.Thread(target=hold_owner)
        other = threading.Thread(target=other_owner)
        with patch("app.notes.pending_repository._locked", pause_first):
            holder.start()
            self.assertTrue(hold.wait(8))
            other.start()
            try:
                self.assertTrue(finished.wait(5), "a different user waited on this confirmation")
            finally:
                release.set()
            holder.join(8)
            other.join(8)
        self.assertEqual(errors, [])
        self.assertEqual(self._count(self.user), 0)
        self.assertEqual(self._count(self.other), 0)

    def test_failed_consume_rolls_back_and_releases_the_lock(self):
        delete_pending.set_pending_delete(self.user, "note-1", "Rollback")
        hold = threading.Event()
        release = threading.Event()
        errors = []
        real_lock = repository._locked
        state = {"n": 0}

        def fail_while_locked(session, user_id, kind):
            row = real_lock(session, user_id, kind)
            if user_id != self.user:
                return row
            state["n"] += 1
            if state["n"] != 1:
                return row
            hold.set()
            if not release.wait(8):
                raise TimeoutError("pending lock holder was not released")
            raise RuntimeError("forced consume failure")

        def fail():
            try:
                delete_pending.consume_pending_delete(self.user, match_title="Rollback")
            except Exception as error:
                errors.append(error)

        def later():
            try:
                return delete_pending.consume_pending_delete(self.user, match_title="Rollback")
            except Exception as error:
                errors.append(error)
                return None

        first = threading.Thread(target=fail)
        second_result = []

        def later_thread():
            second_result.append(later())

        second = threading.Thread(target=later_thread)
        with patch("app.notes.pending_repository._locked", fail_while_locked):
            first.start()
            self.assertTrue(hold.wait(8))
            second.start()
            self._wait_until(lambda: self._row_lock_waiters() >= 1, "later consume did not wait for the row lock")
            release.set()
            first.join(8)
            second.join(8)
        self.assertEqual([str(error) for error in errors], ["forced consume failure"])
        self.assertEqual(len(second_result), 1)
        self.assertIsNotNone(second_result[0])
        self.assertEqual(self._count(self.user), 0)
        with auth_repository.auth_session() as session:
            session.execute(text("DELETE FROM users WHERE user_id = :user_id"), {"user_id": self.other})
        create_pending.set_pending_create(self.user, need_title=True, need_content=True)
        with auth_repository.auth_session() as session:
            session.execute(text("DELETE FROM users WHERE user_id = :user_id"), {"user_id": self.user})
        self.assertEqual(self._count(self.user), 0)

    def _row_lock_waiters(self) -> int:
        with self.engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid() "
                    "AND wait_event_type = 'Lock' "
                    "AND wait_event IN ('tuple', 'transactionid')"
                )
            ).scalar()


if __name__ == "__main__":
    unittest.main()
