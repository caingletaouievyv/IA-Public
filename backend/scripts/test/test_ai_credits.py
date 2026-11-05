# IA/backend/scripts/test/test_ai_credits.py
# Focused AI Credit foundation tests. Run from backend/: python scripts/test/test_ai_credits.py

import datetime
import os
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import jwt

from app import create_app, limiter
from app import config
from app.ai import routes as ai_routes
from app.auth import manager as auth_manager
from app.auth.roles import ROLE_ADMIN
from app.credits import manager as credit_manager
from app.credits import routes as credit_routes
from app.settings import manager as settings_manager
from scripts.test.notes_db import ensure_note_owner
from scripts.test.auth_db import close_sqlite_auth_database, install_sqlite_auth_database


class AICreditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        install_sqlite_auth_database()
        cls.data_dir_patch = patch.object(credit_manager, "DATA_DIR", cls.temp_dir.name)
        cls.data_dir_patch.start()
        cls.settings_dir_patch = patch.object(settings_manager, "DATA_DIR", cls.temp_dir.name)
        cls.settings_dir_patch.start()
        cls.reward_env_patch = patch.object(credit_routes, "APP_ENV", "test")
        cls.reward_env_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.reward_env_patch.stop()
        cls.settings_dir_patch.stop()
        close_sqlite_auth_database()
        cls.data_dir_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        limiter.reset()

    def user_id(self):
        return ensure_note_owner(str(uuid.uuid4()))

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

    def ask(self, user_id, operation_id, **payload):
        return self.client.post(
            "/ai/ask",
            json={"question": "hello", **payload},
            headers={**self.headers(user_id), "Idempotency-Key": operation_id},
        )

    def rewarded_ad(self, user_id, reward_id, **payload):
        return self.client.post(
            "/credits/rewarded-ad",
            json={"reward_id": reward_id, **payload},
            headers=self.headers(user_id),
        )

    def test_new_user_gets_configured_initial_balance(self):
        account = credit_manager.get_credit_account(self.user_id())
        self.assertEqual(account["credit_balance"], max(0, config.AI_CREDIT_INITIAL_BALANCE))
        self.assertEqual(account["ledger"][0]["reason"], "initial_balance")

    def test_registration_defers_credit_initialization_until_first_credit_access(self):
        username = f"new-{uuid.uuid4()}"
        response = self.client.post(
            "/auth/register",
            json={"username": username, "password": "test-password"},
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))

        user_id = response.get_json()["user_id"]
        self.assertFalse(credit_manager.account_exists(user_id))

        account = credit_manager.get_credit_account(user_id)
        self.assertTrue(credit_manager.account_exists(user_id))
        self.assertEqual(account["credit_balance"], max(0, config.AI_CREDIT_INITIAL_BALANCE))
        self.assertEqual(account["ledger"][0]["reason"], "initial_balance")

    def test_registration_succeeds_when_credit_store_initialization_would_fail(self):
        username = f"credit-store-failure-{uuid.uuid4()}"
        with patch(
            "app.credits.repository.locked_credits",
            side_effect=OSError("credit store unavailable"),
        ):
            response = self.client.post(
                "/auth/register",
                json={"username": username, "password": "test-password"},
            )

        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        user_id = response.get_json()["user_id"]
        self.assertFalse(credit_manager.account_exists(user_id))
        self.assertIsNotNone(auth_manager.find_user_by_id(user_id))

        login = self.client.post(
            "/auth/login",
            json={"username": username, "password": "test-password"},
        )
        self.assertEqual(login.status_code, 200, login.get_data(as_text=True))

        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["credit_balance"], max(0, config.AI_CREDIT_INITIAL_BALANCE))

    def test_configured_initial_balance_applies_to_uninitialized_accounts(self):
        user_id = self.user_id()
        with patch.object(credit_manager, "AI_CREDIT_INITIAL_BALANCE", 137):
            account = credit_manager.get_credit_account(user_id)

        self.assertEqual(account["credit_balance"], 137)
        self.assertEqual(account["ledger"][0]["amount"], 137)

    def test_existing_credit_account_is_not_changed_by_initial_balance_setting(self):
        user_id = self.user_id()
        with patch.object(credit_manager, "AI_CREDIT_INITIAL_BALANCE", 41):
            credit_manager.get_credit_account(user_id)
        credit_manager.reserve_credits(user_id, 7, "test_spend", "existing-account")
        before = credit_manager.get_credit_account(user_id)

        with patch.object(credit_manager, "AI_CREDIT_INITIAL_BALANCE", 100):
            after = credit_manager.get_credit_account(user_id)

        self.assertEqual(after, before)
        self.assertEqual(after["credit_balance"], 34)

    def test_app_startup_rejects_missing_or_unsafe_jwt_secret(self):
        for secret in ("", "change-me-in-production", "a" * 32):
            with self.subTest(secret_length=len(secret)):
                with patch.object(config, "JWT_SECRET", secret):
                    with self.assertRaisesRegex(RuntimeError, "JWT_SECRET"):
                        create_app()

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

    def test_authenticated_reward_grants_configured_amount(self):
        user_id = self.user_id()
        response = self.rewarded_ad(user_id, "ad-reward-1")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["credits_granted"], config.REWARDED_AD_CREDIT_AMOUNT)
        self.assertEqual(
            response.get_json()["credit_balance"],
            config.AI_CREDIT_INITIAL_BALANCE + config.REWARDED_AD_CREDIT_AMOUNT,
        )

    def test_unverified_reward_is_disabled_outside_development_and_test(self):
        user_id = self.user_id()
        before = credit_manager.get_credit_account(user_id)
        with patch.object(credit_routes, "APP_ENV", "production"):
            response = self.rewarded_ad(user_id, "unverified-reward")
        after = credit_manager.get_credit_account(user_id)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "rewarded_ad_disabled")
        self.assertEqual(after["credit_balance"], before["credit_balance"])
        self.assertEqual(after["ledger"], before["ledger"])

    def test_reward_requires_non_empty_reward_id(self):
        for reward_id in (None, "", "   "):
            with self.subTest(reward_id=reward_id):
                response = self.rewarded_ad(self.user_id(), reward_id)
                self.assertEqual(response.status_code, 400)

    def test_duplicate_reward_id_is_idempotent(self):
        user_id = self.user_id()
        first = self.rewarded_ad(user_id, "ad-reward-duplicate")
        second = self.rewarded_ad(user_id, "ad-reward-duplicate")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first.get_json()["idempotent"])
        self.assertTrue(second.get_json()["idempotent"])
        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE + config.REWARDED_AD_CREDIT_AMOUNT)
        self.assertEqual(len([entry for entry in account["ledger"] if entry.get("reason") == "rewarded_ad"]), 1)

    def test_different_reward_ids_grant_independently(self):
        user_id = self.user_id()
        self.assertEqual(self.rewarded_ad(user_id, "ad-reward-a").status_code, 200)
        self.assertEqual(self.rewarded_ad(user_id, "ad-reward-b").status_code, 200)
        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE + (2 * config.REWARDED_AD_CREDIT_AMOUNT))

    def test_reward_requires_authentication(self):
        response = self.client.post("/credits/rewarded-ad", json={"reward_id": "unauthenticated"})
        self.assertEqual(response.status_code, 401)

    def test_reward_amount_cannot_be_overridden_by_client(self):
        user_id = self.user_id()
        response = self.rewarded_ad(user_id, "ad-reward-fixed", amount=999999)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["credits_granted"], config.REWARDED_AD_CREDIT_AMOUNT)

    def test_reward_ledger_records_reason_and_reward_id(self):
        user_id = self.user_id()
        self.assertEqual(self.rewarded_ad(user_id, "ad-reward-ledger").status_code, 200)
        account = credit_manager.get_credit_account(user_id)
        reward_entries = [entry for entry in account["ledger"] if entry.get("reason") == "rewarded_ad"]
        self.assertEqual(len(reward_entries), 1)
        self.assertEqual(reward_entries[0]["operation_id"], "ad-reward-ledger")

    def test_successful_ask_consumes_one_credit_and_is_retry_safe(self):
        user_id = self.user_id()
        operation_id = "ask-success"
        with patch.object(ai_routes, "ask", return_value=("answer", 3, "disabled", None)) as ask_mock:
            response = self.ask(user_id, operation_id)
            retry = self.ask(user_id, operation_id)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(retry.status_code, 200, retry.get_data(as_text=True))
        self.assertEqual(response.get_json(), retry.get_json())
        self.assertEqual(ask_mock.call_count, 1)
        self.assertEqual(ask_mock.call_args.kwargs["note_context_mode"], "automatic")
        self.assertFalse(ask_mock.call_args.kwargs["memory_enabled"])
        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - config.AI_ASK_CREDIT_COST)
        self.assertEqual(account["ledger"][-1]["reason"], "ai_ask")
        self.assertEqual(account["ledger"][-1]["amount"], -config.AI_ASK_CREDIT_COST)

    def test_ask_passes_context_modes_and_authenticated_user_to_engine(self):
        user_id = self.user_id()
        with patch.object(ai_routes, "ask", return_value=("answer", 3, "disabled", None)) as ask_mock:
            response = self.ask(
                user_id,
                "memory-context",
                note_context_mode="focused",
                memory_context_mode="selected",
                note_ids=["owned-note"],
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(ask_mock.call_args.kwargs["user_id"], user_id)
        self.assertEqual(ask_mock.call_args.kwargs["note_context_mode"], "focused")
        self.assertFalse(ask_mock.call_args.kwargs["memory_enabled"])
        self.assertEqual(ask_mock.call_args.kwargs["note_ids"], ["owned-note"])

    def test_ask_uses_persisted_memory_setting_and_only_charges_one_credit(self):
        user_id = self.user_id()
        settings_manager.save_settings(user_id, {"memory_enabled": True})

        with patch.object(ai_routes, "ask", return_value=("answer", 3, "saved", None)) as ask_mock:
            response = self.ask(user_id, "memory-enabled", memory_enabled=False)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["memory_status"], "saved")
        self.assertTrue(ask_mock.call_args.kwargs["memory_enabled"])
        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - config.AI_ASK_CREDIT_COST)

    def test_malformed_context_payloads_are_rejected_before_credit_charge(self):
        user_id = self.user_id()
        malformed_payloads = [
            {"memory_context_mode": "focused"},
            {"memory_context_mode": []},
            {"note_ids": "owned-note"},
            {"note_ids": [""]},
            {"note_ids": [None]},
        ]
        with patch.object(ai_routes, "ask") as ask_mock:
            for index, payload in enumerate(malformed_payloads):
                with self.subTest(payload=payload):
                    response = self.ask(user_id, f"malformed-{index}", **payload)
                    self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
            response = self.client.post(
                "/ai/ask",
                json=["not", "an", "object"],
                headers={**self.headers(user_id), "Idempotency-Key": "malformed-object"},
            )

        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        ask_mock.assert_not_called()
        self.assertEqual(credit_manager.get_credit_account(user_id)["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE)

    def test_different_idempotency_keys_are_independent_operations(self):
        user_id = self.user_id()
        with patch.object(ai_routes, "ask", side_effect=[("first", 3, "disabled", None), ("second", 4, "disabled", None)]) as ask_mock:
            first = self.ask(user_id, "ask-first")
            second = self.ask(user_id, "ask-second")
        self.assertEqual(first.get_json()["answer"], "first")
        self.assertEqual(second.get_json()["answer"], "second")
        self.assertEqual(ask_mock.call_count, 2)
        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - 2 * config.AI_ASK_CREDIT_COST)

    def test_idempotency_records_are_isolated_by_user(self):
        first_user = self.user_id()
        second_user = self.user_id()
        with patch.object(ai_routes, "ask", side_effect=[("first", 3, "disabled", None), ("second", 4, "disabled", None)]) as ask_mock:
            first = self.ask(first_user, "shared-key")
            second = self.ask(second_user, "shared-key")
        self.assertEqual(first.get_json()["answer"], "first")
        self.assertEqual(second.get_json()["answer"], "second")
        self.assertEqual(ask_mock.call_count, 2)
        self.assertEqual(credit_manager.get_credit_account(first_user)["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - config.AI_ASK_CREDIT_COST)
        self.assertEqual(credit_manager.get_credit_account(second_user)["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - config.AI_ASK_CREDIT_COST)

    def test_normal_user_still_pays_credits(self):
        user_id = self.user_id()
        with patch.object(ai_routes, "ask", return_value=("answer", 3, "disabled", None)):
            response = self.ask(user_id, "normal-user-pays")
        self.assertEqual(response.status_code, 200)
        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["credit_balance"], config.AI_CREDIT_INITIAL_BALANCE - config.AI_ASK_CREDIT_COST)
        self.assertEqual(account["ledger"][-1]["amount"], -config.AI_ASK_CREDIT_COST)

    def test_unlimited_role_can_ask_with_zero_credits_without_debit(self):
        user_id = self.user_id()
        auth_manager._save_users([{
            "user_id": user_id,
            "username": "credit-admin",
            "password_hash": "test-hash",
            "role": ROLE_ADMIN,
        }])
        for index in range(config.AI_CREDIT_INITIAL_BALANCE):
            credit_manager.reserve_credits(user_id, config.AI_ASK_CREDIT_COST, "ai_ask", f"zero-{index}")
        with patch.object(ai_routes, "ask", return_value=("answer", 3, "disabled", None)):
            response = self.ask(user_id, "unlimited-ask")
        self.assertEqual(response.status_code, 200)
        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["credit_balance"], 0)
        self.assertFalse(any(entry.get("operation_id") == "unlimited-ask" for entry in account["ledger"]))

    def test_request_payload_cannot_activate_unlimited_mode(self):
        user_id = self.user_id()
        with patch.object(ai_routes, "ask", return_value=("answer", 3, "disabled", None)):
            response = self.client.post(
                "/ai/ask",
                json={"question": "hello", "unlimited": True, "role": config.AI_UNLIMITED_ROLE},
                headers={**self.headers(user_id), "Idempotency-Key": "payload-role"},
            )
        self.assertEqual(response.status_code, 200)
        account = credit_manager.get_credit_account(user_id)
        self.assertEqual(account["ledger"][-1]["amount"], -config.AI_ASK_CREDIT_COST)

    def test_unauthenticated_ai_request_remains_rejected(self):
        response = self.client.post("/ai/ask", json={"question": "hello"})
        self.assertEqual(response.status_code, 401)

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
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"], "AI request failed")
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
        with patch.object(ai_routes, "ask", return_value=("answer", 1, "disabled", None)):
            responses = [self.ask(user_id, f"rate-limit-{index}") for index in range(31)]
        self.assertEqual(responses[-1].status_code, 429)

    def test_failed_operation_id_does_not_call_ask_provider(self):
        user_id = self.user_id()
        operation_id = "ask-failed-op"
        from app.credits import repository

        credit_manager.claim_operation(user_id, operation_id)
        with repository.locked_credits(user_id, config.AI_CREDIT_INITIAL_BALANCE) as session:
            repository.apply_fail(session, user_id, operation_id, {"error": "prior failure"})
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]
        with patch.object(ai_routes, "ask") as ask_mock:
            response = self.ask(user_id, operation_id)
        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertEqual(payload["error"], "operation_failed")
        self.assertEqual(payload["operation_id"], operation_id)
        ask_mock.assert_not_called()
        self.assertEqual(credit_manager.get_credit_account(user_id)["credit_balance"], initial_balance)


if __name__ == "__main__":
    unittest.main()