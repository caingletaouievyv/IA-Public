# IA/backend/scripts/test/test_credits_repository.py
# Credit and idempotency checks on SQLite. These do not open a PostgreSQL connection.

import os
import sys
import time
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, delete, select
from sqlalchemy.pool import NullPool

from app import config
from app.auth import repository as auth_repository
from app.auth.manager import get_user_role
from app.auth.models import User
from app.auth.permissions import has_unlimited_credits
from app.credits import manager
from app.credits import repository
from app.credits.models import CreditOperation
from app.credits.repository import CreditStoreError, InsufficientCreditsError
from app.db import DatabaseConnectionError, install_engine
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


class CreditRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()

    @classmethod
    def tearDownClass(cls):
        close_notes_database()

    def setUp(self):
        self.user = ensure_note_owner(str(uuid.uuid4()))
        self.other = ensure_note_owner(str(uuid.uuid4()))

    def test_new_account_uses_initial_balance_once(self):
        self.assertFalse(manager.account_exists(self.user))
        account = manager.get_credit_account(self.user)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)
        self.assertEqual(account["ledger"][0]["reason"], "initial_balance")
        self.assertEqual(account["ledger"][0]["amount"], config.AI_CREDIT_INITIAL_BALANCE)
        self.assertNotIn("operation_id", account["ledger"][0])
        self.assertEqual(account["operations"], {})
        self.assertEqual(manager.get_credit_account(self.user), account)
        self.assertEqual(manager.get_credit_account(self.other)["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)

    def test_deduction_insufficient_balance_and_refund(self):
        reserved = manager.reserve_credits(self.user, 4, "ai_ask", "spend-1")
        self.assertTrue(reserved["charged"])
        self.assertEqual(reserved["account"]["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - 4)
        self.assertEqual(reserved["account"]["ledger"][-1]["amount"], -4)
        self.assertEqual(reserved["account"]["ledger"][-1]["reason"], "ai_ask")
        again = manager.reserve_credits(self.user, 4, "ai_ask", "spend-1")
        self.assertFalse(again["charged"])
        self.assertEqual(again["account"]["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - 4)
        with self.assertRaises(InsufficientCreditsError) as caught:
            manager.reserve_credits(self.user, config.AI_CREDIT_INITIAL_BALANCE, "ai_ask", "too-much")
        self.assertEqual(caught.exception.balance, config.AI_CREDIT_INITIAL_BALANCE - 4)
        self.assertEqual(manager.get_credit_account(self.user)["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - 4)
        refunded = manager.refund_credits(self.user, 4, "ai_ask_refund", "spend-1")
        self.assertEqual(refunded["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)
        self.assertEqual(refunded["ledger"][-1]["reason"], "ai_ask_refund")
        self.assertEqual(refunded["ledger"][-1]["related_entry_id"], reserved["account"]["ledger"][-1]["entry_id"])
        second_refund = manager.refund_credits(self.user, 4, "ai_ask_refund", "spend-1")
        self.assertEqual(second_refund["ledger"], refunded["ledger"])
        retried = manager.reserve_credits(self.user, 4, "ai_ask", "spend-1")
        self.assertTrue(retried["charged"])
        self.assertEqual(retried["account"]["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - 4)

    def test_duplicate_operation_returns_the_original_result(self):
        claimed = manager.claim_operation(self.user, "ask-1")
        self.assertEqual(claimed["status"], "claimed")
        self.assertEqual(manager.claim_operation(self.user, "ask-1")["status"], "pending")
        manager.reserve_credits(self.user, 1, "ai_ask", "ask-1")
        manager.complete_operation(self.user, "ask-1", {"answer": "saved", "operation_id": "ask-1"})
        completed = manager.claim_operation(self.user, "ask-1")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["result"]["answer"], "saved")
        self.assertFalse(manager.reserve_credits(self.user, 1, "ai_ask", "ask-1")["charged"])
        self.assertEqual(
            manager.get_credit_account(self.user)["credit_balance"],
            config.AI_CREDIT_INITIAL_BALANCE - 1,
        )
        self.assertTrue(manager.has_completed_operation(self.user, "ask-1"))
        self.assertFalse(manager.has_completed_operation(self.other, "ask-1"))

    def test_same_key_is_independent_for_each_user(self):
        self.assertEqual(manager.claim_operation(self.user, "shared")["status"], "claimed")
        self.assertEqual(manager.claim_operation(self.other, "shared")["status"], "claimed")
        self.assertTrue(manager.reserve_credits(self.user, 2, "ai_ask", "shared")["charged"])
        self.assertTrue(manager.reserve_credits(self.other, 2, "ai_ask", "shared")["charged"])
        self.assertEqual(
            manager.get_credit_account(self.user)["credit_balance"],
            config.AI_CREDIT_INITIAL_BALANCE - 2,
        )
        self.assertEqual(
            manager.get_credit_account(self.other)["credit_balance"],
            config.AI_CREDIT_INITIAL_BALANCE - 2,
        )

    def test_provider_failure_refunds_and_releases_the_claim(self):
        operation_id = "provider-failed"
        self.assertEqual(manager.claim_operation(self.user, operation_id)["status"], "claimed")
        reservation = manager.reserve_credits(self.user, 1, "ai_ask", operation_id)
        self.assertTrue(reservation["charged"])
        manager.refund_credits(self.user, 1, "ai_ask_refund", operation_id)
        manager.release_operation(self.user, operation_id)
        account = manager.get_credit_account(self.user)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)
        self.assertEqual([entry["reason"] for entry in account["ledger"][-2:]], ["ai_ask", "ai_ask_refund"])
        self.assertNotIn(operation_id, account["operations"])
        self.assertEqual(manager.claim_operation(self.user, operation_id)["status"], "claimed")

    def test_expired_pending_operation_can_be_claimed_again(self):
        manager.claim_operation(self.user, "stale")
        with repository.credits_session() as session:
            row = session.scalar(
                select(CreditOperation).where(
                    CreditOperation.user_id == self.user,
                    CreditOperation.operation_id == "stale",
                )
            )
            row.started_at = time.time() - 301
        self.assertEqual(manager.claim_operation(self.user, "stale")["status"], "claimed")

    def test_rollback_drops_the_debit_and_a_later_reserve_succeeds(self):
        real_reserve = repository.apply_reserve

        def fail_after_reserve(session, user_id, amount, reason, operation_id):
            real_reserve(session, user_id, amount, reason, operation_id)
            raise RuntimeError("forced credit failure")

        with patch("app.credits.repository.apply_reserve", fail_after_reserve):
            with self.assertRaisesRegex(RuntimeError, "forced credit failure"):
                manager.reserve_credits(self.user, 6, "ai_ask", "rolled-back")
        account = manager.get_credit_account(self.user)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)
        self.assertFalse(any(entry.get("operation_id") == "rolled-back" for entry in account["ledger"]))
        later = manager.reserve_credits(self.user, 6, "ai_ask", "after-rollback")
        self.assertTrue(later["charged"])
        self.assertEqual(later["account"]["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - 6)

    def test_unlimited_role_keeps_a_zero_balance(self):
        for index in range(config.AI_CREDIT_INITIAL_BALANCE):
            manager.reserve_credits(self.user, 1, "ai_ask", f"drain-{index}")
        with auth_repository.auth_session() as session:
            auth_repository.set_role(session, self.user, "admin")
        self.assertTrue(has_unlimited_credits(get_user_role(self.user)))
        manager.claim_operation(self.user, "unlimited-ask")
        manager.complete_operation(self.user, "unlimited-ask", {"answer": "ok"})
        account = manager.get_credit_account(self.user)
        self.assertEqual(account["credit_balance"], 0)
        self.assertFalse(any(entry.get("operation_id") == "unlimited-ask" for entry in account["ledger"]))

    def test_user_delete_removes_credit_rows(self):
        manager.reserve_credits(self.user, 1, "ai_ask", "gone")
        with auth_repository.auth_session() as session:
            session.execute(delete(User).where(User.user_id == self.user))
        self.assertFalse(manager.account_exists(self.user))

    def test_credit_paths_do_not_open_files(self):
        with patch("builtins.open", side_effect=AssertionError("credits opened a file")):
            manager.get_credit_account(self.user)
            manager.reserve_credits(self.user, 1, "ai_ask", "no-file")

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
            bad.dispose()
            close_notes_database()
            install_notes_database()
        message = f"{caught.exception} {caught.exception!r}"
        self.assertNotIn("secret-password", message)
        self.assertNotIn("127.0.0.1", message)
        self.assertNotIn("://", message)
        self.assertIn(str(caught.exception), {"Could not access credits.", "Database connection failed"})


if __name__ == "__main__":
    unittest.main()
