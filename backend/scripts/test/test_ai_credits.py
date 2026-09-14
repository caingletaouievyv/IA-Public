# IA/backend/scripts/test/test_ai_credits.py
# Focused AI Credit foundation tests. Run from backend/: python scripts/test/test_ai_credits.py

import datetime
import os
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import jwt

from app import create_app, limiter
from app import config
from app.ai import routes as ai_routes
from app.credits import manager as credit_manager


class AICreditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.data_dir_patch = patch.object(credit_manager, "DATA_DIR", cls.temp_dir.name)
        cls.data_dir_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.data_dir_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        limiter.reset()

    def user_id(self):
        return str(uuid.uuid4())

    def headers(self, user_id):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}"}

    def ask(self, user_id, operation_id):
        return self.client.post(
            "/ai/ask",
            json={"question": "hello"},
            headers={**self.headers(user_id), "Idempotency-Key": operation_id},
        )

    def test_new_user_gets_configured_initial_balance(self):
        account = credit_manager.get_credit_account(self.user_id())
        self.assertEqual(account["credit_balance"], max(0, config.AI_CREDIT_INITIAL_BALANCE))
        self.assertEqual(account["ledger"][0]["reason"], "initial_balance")

    def test_balances_are_isolated_and_grants_are_ledgered(self):
        first = self.user_id()
        second = self.user_id()
        credit_manager.grant_credits(first, 10, "rewarded_ad", "reward-1")
        first_account = credit_manager.get_credit_account(first)
        second_account = credit_manager.get_credit_account(second)
        self.assertEqual(first_account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE + 10)
        self.assertEqual(second_account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)
        self.assertEqual(first_account["ledger"][-1]["amount"], 10)
        self.assertEqual(first_account["ledger"][-1]["reason"], "rewarded_ad")

    def test_grant_requires_operation_id(self):
        with self.assertRaisesRegex(ValueError, "operation_id required"):
            credit_manager.grant_credits(self.user_id(), 10, "rewarded_ad", "")

    def test_grant_with_same_operation_id_is_idempotent(self):
        user_id = self.user_id()
        credit_manager.grant_credits(user_id, 10, "rewarded_ad", "reward-1")
        account = credit_manager.grant_credits(user_id, 10, "rewarded_ad", "reward-1")
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE + 10)
        self.assertEqual(len(account["ledger"]), 2)

    def test_grant_rejects_same_operation_id_with_different_amount(self):
        user_id = self.user_id()
        credit_manager.grant_credits(user_id, 10, "rewarded_ad", "reward-1")
        with self.assertRaisesRegex(ValueError, "different grant"):
            credit_manager.grant_credits(user_id, 20, "rewarded_ad", "reward-1")

    def test_grant_rejects_same_operation_id_with_different_reason(self):
        user_id = self.user_id()
        credit_manager.grant_credits(user_id, 10, "rewarded_ad", "reward-1")
        with self.assertRaisesRegex(ValueError, "different grant"):
            credit_manager.grant_credits(user_id, 10, "referral", "reward-1")

    def test_different_grant_operation_ids_are_independent(self):
        user_id = self.user_id()
        account = credit_manager.grant_credits(user_id, 10, "rewarded_ad", "reward-1")
        account = credit_manager.grant_credits(user_id, 20, "referral", "reward-2")
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE + 30)
        self.assertEqual(len(account["ledger"]), 3)

    def test_successful_ask_consumes_one_credit_and_is_retry_safe(self):
        user_id = self.user_id()
        operation_id = "ask-success"
        with patch.object(ai_routes, "ask", return_value=("answer", 3)) as ask_mock:
            response = self.ask(user_id, operation_id)
            retry = self.ask(user_id, operation_id)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(retry.status_code, 200, retry.get_data(as_text=True))
        self.assertEqual(ask_mock.call_count, 2)
        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - config.AI_ASK_CREDIT_COST)
        self.assertEqual(account["ledger"][-1]["reason"], "ai_ask")
        self.assertEqual(account["ledger"][-1]["amount"], -config.AI_ASK_CREDIT_COST)

    def test_insufficient_credits_rejects_before_provider_call(self):
        user_id = self.user_id()
        for index in range(config.AI_CREDIT_INITIAL_BALANCE):
            credit_manager.reserve_credits(user_id, config.AI_ASK_CREDIT_COST, "ai_ask", f"used-{index}")
        with patch.object(ai_routes, "ask") as ask_mock:
            response = self.ask(user_id, "ask-rejected")
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.get_json()["error"], "insufficient_ai_credits")
        ask_mock.assert_not_called()

    def test_failed_ask_refunds_and_records_ledger_entry(self):
        user_id = self.user_id()
        with patch.object(ai_routes, "ask", side_effect=RuntimeError("provider failed")):
            response = self.ask(user_id, "ask-failed")
        self.assertEqual(response.status_code, 500)
        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)
        self.assertEqual(account["ledger"][-2]["reason"], "ai_ask")
        self.assertEqual(account["ledger"][-1]["reason"], "ai_ask_refund")
        self.assertEqual(account["ledger"][-1]["amount"], config.AI_ASK_CREDIT_COST)

    def test_existing_authentication_still_works(self):
        response = self.client.get(f"/notes/auth-check", headers=self.headers(self.user_id()))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["auth_ok"])

    def test_existing_ip_rate_limit_remains_intact(self):
        user_id = self.user_id()
        credit_manager.grant_credits(user_id, 40, "test_setup", "rate-limit-credits")
        limiter.reset()
        with patch.object(ai_routes, "ask", return_value=("answer", 1)):
            responses = [self.ask(user_id, f"rate-limit-{index}") for index in range(31)]
        self.assertEqual(responses[-1].status_code, 429)


if __name__ == "__main__":
    unittest.main()