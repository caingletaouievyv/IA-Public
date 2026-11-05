# IA/backend/scripts/test/test_credits_postgres.py
# Live PostgreSQL credit and idempotency checks. Skipped unless IA_TEST_DATABASE_URL points at a disposable database.
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from app import config
from app.auth import repository as auth_repository
from app.auth.manager import get_user_role
from app.auth.permissions import has_unlimited_credits
from app.credits import manager
from app.credits import repository
from app.credits.repository import CreditStoreError, InsufficientCreditsError
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
        raise RuntimeError("Refusing to run credit tests against a Neon host.")
    if parsed.drivername not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise RuntimeError("IA_TEST_DATABASE_URL must be a PostgreSQL URL.")
    return url


class PostgresCreditTests(unittest.TestCase):
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
            connection.execute(text("DELETE FROM credit_operations"))
            connection.execute(text("DELETE FROM credit_ledger"))
            connection.execute(text("DELETE FROM credit_accounts"))
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

    def _row_lock_waiters(self) -> int:
        with self.engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid() "
                    "AND wait_event_type = 'Lock'"
                )
            ).scalar()

    def test_credit_catalog(self):
        with self.engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            self.assertEqual(version, "c9a1e4f72b36")
            balance_type = connection.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'credit_accounts' "
                    "AND column_name = 'credit_balance'"
                )
            ).scalar()
            amount_type = connection.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'credit_ledger' "
                    "AND column_name = 'amount'"
                )
            ).scalar()
            self.assertEqual(balance_type, "integer")
            self.assertEqual(amount_type, "integer")
            constraints = {
                name: definition
                for name, definition in connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conrelid IN ("
                        "'public.credit_accounts'::regclass, "
                        "'public.credit_ledger'::regclass, "
                        "'public.credit_operations'::regclass)"
                    )
                )
            }
            self.assertIn(
                "FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE",
                constraints["credit_accounts_user_id_fkey"],
            )
            self.assertIn("credit_balance >= 0", constraints["credit_accounts_balance_nonnegative"])
            self.assertIn("UNIQUE (user_id, seq)", constraints["credit_ledger_user_seq"])
            self.assertIn("PRIMARY KEY (user_id, operation_id)", constraints["credit_operations_pkey"])
            index_sql = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = 'credit_ledger_user_operation'"
                )
            ).scalar()
            self.assertIn("user_id", index_sql)
            self.assertIn("operation_id", index_sql)

    def test_deduction_refund_duplicate_and_unlimited_role(self):
        account = manager.get_credit_account(self.user)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)
        reserved = manager.reserve_credits(self.user, 3, "ai_ask", "ask-1")
        self.assertTrue(reserved["charged"])
        self.assertFalse(manager.reserve_credits(self.user, 3, "ai_ask", "ask-1")["charged"])
        with self.assertRaises(InsufficientCreditsError):
            manager.reserve_credits(self.user, config.AI_CREDIT_INITIAL_BALANCE, "ai_ask", "too-much")
        self.assertEqual(
            manager.get_credit_account(self.user)["credit_balance"],
            config.AI_CREDIT_INITIAL_BALANCE - 3,
        )
        manager.claim_operation(self.user, "ask-1")
        manager.complete_operation(self.user, "ask-1", {"answer": "saved"})
        self.assertEqual(manager.claim_operation(self.user, "ask-1")["result"]["answer"], "saved")
        refunded = manager.refund_credits(self.user, 3, "ai_ask_refund", "ask-1")
        self.assertEqual(refunded["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)
        for index in range(config.AI_CREDIT_INITIAL_BALANCE):
            manager.reserve_credits(self.user, 1, "ai_ask", f"drain-{index}")
        with auth_repository.auth_session() as session:
            auth_repository.set_role(session, self.user, "admin")
        self.assertTrue(has_unlimited_credits(get_user_role(self.user)))
        manager.claim_operation(self.user, "unlimited-ask")
        manager.complete_operation(self.user, "unlimited-ask", {"answer": "ok"})
        stored = manager.get_credit_account(self.user)
        self.assertEqual(stored["credit_balance"], 0)
        self.assertFalse(any(entry.get("operation_id") == "unlimited-ask" for entry in stored["ledger"]))

    def test_negative_balance_is_rejected_and_user_delete_cascades(self):
        manager.get_credit_account(self.user)
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text("UPDATE credit_accounts SET credit_balance = -1 WHERE user_id = :user_id"),
                    {"user_id": self.user},
                )
        self.assertGreaterEqual(manager.get_credit_account(self.user)["credit_balance"], 0)
        with auth_repository.auth_session() as session:
            session.execute(text("DELETE FROM users WHERE user_id = :user_id"), {"user_id": self.user})
        self.assertFalse(manager.account_exists(self.user))

    def test_concurrent_deductions_do_not_lose_updates_or_go_negative(self):
        self._overlap_reserves("spend-a", "spend-b", 4, 4)
        account = manager.get_credit_account(self.user)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - 8)
        self.assertGreaterEqual(account["credit_balance"], 0)
        debits = [entry for entry in account["ledger"] if entry.get("reason") == "test_spend"]
        self.assertEqual(len(debits), 2)

        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM credit_ledger WHERE user_id = :user_id"), {"user_id": self.user})
            connection.execute(
                text("UPDATE credit_accounts SET credit_balance = 5 WHERE user_id = :user_id"),
                {"user_id": self.user},
            )
        errors = self._overlap_reserves("tight-a", "tight-b", 4, 4)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], InsufficientCreditsError)
        tight = manager.get_credit_account(self.user)
        self.assertEqual(tight["credit_balance"], 1)
        self.assertGreaterEqual(tight["credit_balance"], 0)

    def test_concurrent_same_key_claims_and_reserves_once(self):
        claims = self._overlap_calls(
            repository.apply_claim,
            "app.credits.repository.apply_claim",
            lambda real, session, user_id, operation_id, pending_ttl: real(
                session, user_id, operation_id, pending_ttl
            ),
            lambda: manager.claim_operation(self.user, "same-claim"),
            lambda: manager.claim_operation(self.user, "same-claim"),
        )
        statuses = sorted(item["status"] for item in claims)
        self.assertEqual(statuses, ["claimed", "pending"])
        results = self._overlap_calls(
            repository.apply_reserve,
            "app.credits.repository.apply_reserve",
            lambda real, session, user_id, amount, reason, operation_id: real(
                session, user_id, amount, reason, operation_id
            ),
            lambda: manager.reserve_credits(self.user, 3, "ai_ask", "same-reserve"),
            lambda: manager.reserve_credits(self.user, 3, "ai_ask", "same-reserve"),
        )
        charged = sorted(item["charged"] for item in results)
        self.assertEqual(charged, [False, True])
        self.assertEqual(
            manager.get_credit_account(self.user)["credit_balance"],
            config.AI_CREDIT_INITIAL_BALANCE - 3,
        )

    def test_same_key_for_another_user_is_not_blocked(self):
        hold = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        errors = []
        real_reserve = repository.apply_reserve

        def paused(session, user_id, amount, reason, operation_id):
            if user_id == self.user:
                hold.set()
                if not release.wait(8):
                    raise TimeoutError("credit lock holder was not released")
            return real_reserve(session, user_id, amount, reason, operation_id)

        def reserve(user_id):
            try:
                manager.reserve_credits(user_id, 3, "ai_ask", "shared-key")
            except Exception as error:
                errors.append(error)
            finally:
                if user_id == self.other:
                    finished.set()

        with patch("app.credits.repository.apply_reserve", paused):
            first = threading.Thread(target=reserve, args=(self.user,))
            second = threading.Thread(target=reserve, args=(self.other,))
            first.start()
            self.assertTrue(hold.wait(8))
            second.start()
            try:
                self.assertTrue(finished.wait(3), "other user was blocked by this user's credit lock")
            finally:
                release.set()
            first.join(8)
            second.join(8)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(
            manager.get_credit_account(self.user)["credit_balance"],
            config.AI_CREDIT_INITIAL_BALANCE - 3,
        )
        self.assertEqual(
            manager.get_credit_account(self.other)["credit_balance"],
            config.AI_CREDIT_INITIAL_BALANCE - 3,
        )

    def test_failed_reserve_rolls_back_and_releases_the_lock(self):
        hold = threading.Event()
        release = threading.Event()
        errors = []
        real_reserve = repository.apply_reserve

        def fail_once(session, user_id, amount, reason, operation_id):
            if operation_id == "fail":
                real_reserve(session, user_id, amount, reason, operation_id)
                hold.set()
                if not release.wait(8):
                    raise TimeoutError("credit lock holder was not released")
                raise RuntimeError("forced credit failure")
            return real_reserve(session, user_id, amount, reason, operation_id)

        def reserve(operation_id):
            try:
                manager.reserve_credits(self.user, 4, "ai_ask", operation_id)
            except Exception as error:
                errors.append(error)

        with patch("app.credits.repository.apply_reserve", fail_once):
            first = threading.Thread(target=reserve, args=("fail",))
            second = threading.Thread(target=reserve, args=("later",))
            first.start()
            self.assertTrue(hold.wait(8))
            second.start()
            try:
                self._wait_until(
                    lambda: self._row_lock_waiters() >= 1,
                    "later credit update did not wait for the account lock",
                )
            finally:
                release.set()
            first.join(8)
            second.join(8)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(str(errors[0]), "forced credit failure")
        account = manager.get_credit_account(self.user)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - 4)
        self.assertFalse(any(entry.get("operation_id") == "fail" for entry in account["ledger"]))
        self.assertTrue(any(entry.get("operation_id") == "later" for entry in account["ledger"]))

    def test_provider_failure_restores_balance(self):
        operation_id = "provider-failed"
        manager.claim_operation(self.user, operation_id)
        self.assertTrue(manager.reserve_credits(self.user, 1, "ai_ask", operation_id)["charged"])
        manager.refund_credits(self.user, 1, "ai_ask_refund", operation_id)
        manager.release_operation(self.user, operation_id)
        account = manager.get_credit_account(self.user)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)
        self.assertEqual(account["ledger"][-1]["reason"], "ai_ask_refund")
        self.assertNotIn(operation_id, account["operations"])

    def test_credit_paths_do_not_open_files(self):
        with patch("builtins.open", side_effect=AssertionError("credits opened a file")):
            self.assertEqual(
                manager.get_credit_account(self.user)["credit_balance"],
                config.AI_CREDIT_INITIAL_BALANCE,
            )

    def test_database_errors_omit_connection_details(self):
        bad = create_engine(
            "postgresql+psycopg://credits:secret-password@127.0.0.1:1/none",
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
        install_engine(bad)
        try:
            with self.assertRaises((CreditStoreError, DatabaseConnectionError)) as caught:
                manager.get_credit_account(self.user)
        finally:
            install_engine(self.engine)
            bad.dispose()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)

    def _overlap_reserves(self, first_id: str, second_id: str, first_amount: int, second_amount: int):
        results = self._overlap_calls(
            repository.apply_reserve,
            "app.credits.repository.apply_reserve",
            lambda real, session, user_id, amount, reason, operation_id: real(
                session, user_id, amount, reason, operation_id
            ),
            lambda: manager.reserve_credits(self.user, first_amount, "test_spend", first_id),
            lambda: manager.reserve_credits(self.user, second_amount, "test_spend", second_id),
        )
        return [item for item in results if isinstance(item, Exception)]

    def _overlap_calls(self, real, patch_path, invoke, first_call, second_call):
        hold = threading.Event()
        release = threading.Event()
        results = []
        paused = {"done": False}

        def wrapped(*args, **kwargs):
            if not paused["done"]:
                paused["done"] = True
                hold.set()
                if not release.wait(8):
                    raise TimeoutError("credit lock holder was not released")
            return invoke(real, *args, **kwargs)

        def run(call):
            try:
                results.append(call())
            except Exception as error:
                results.append(error)

        with patch(patch_path, wrapped):
            first = threading.Thread(target=run, args=(first_call,))
            second = threading.Thread(target=run, args=(second_call,))
            first.start()
            self.assertTrue(hold.wait(8))
            second.start()
            try:
                self._wait_until(
                    lambda: self._row_lock_waiters() >= 1,
                    "second credit request did not wait for the account lock",
                )
            finally:
                release.set()
            first.join(8)
            second.join(8)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        return results


if __name__ == "__main__":
    unittest.main()
