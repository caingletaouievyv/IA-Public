# IA/backend/scripts/test/test_remember_command.py
# Regression tests for the Ask !remember command (no AI provider, no Ask credits).

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
from app.credits import manager as credit_manager
from app.memories import manager as memory_manager
from app.memories.remember_command import parse_remember_command
from app.settings import manager as settings_manager
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


class RememberCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.memory_patch = patch.object(memory_manager, "DATA_DIR", cls.temp_dir.name)
        cls.settings_patch = patch.object(settings_manager, "DATA_DIR", cls.temp_dir.name)
        cls.credits_patch = patch.object(credit_manager, "DATA_DIR", cls.temp_dir.name)
        cls.memory_patch.start()
        cls.settings_patch.start()
        cls.credits_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.credits_patch.stop()
        cls.settings_patch.stop()
        cls.memory_patch.stop()
        close_notes_database()
        cls.temp_dir.cleanup()

    def setUp(self):
        limiter.reset()

    def user_id(self):
        return ensure_note_owner(str(uuid.uuid4()))

    def headers(self, user_id, operation_id):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}", "Idempotency-Key": operation_id}

    def remember_ask(self, user_id, operation_id, question, **payload):
        return self.client.post(
            "/ai/ask",
            json={"question": question, **payload},
            headers=self.headers(user_id, operation_id),
        )

    def enable_memory(self, user_id):
        settings_manager.save_settings(
            user_id,
            {"memory_enabled": True, "remember_command_enabled": True},
        )

    def test_parse_remember_command(self):
        self.assertIsNone(parse_remember_command("hello"))
        self.assertEqual(parse_remember_command("!remember my fact"), "my fact")
        self.assertEqual(parse_remember_command("  !REMEMBER   Spaced  "), "Spaced  ")
        self.assertEqual(parse_remember_command("!Remember"), "")

    def test_remember_saves_without_ai_or_credits(self):
        user_id = self.user_id()
        self.enable_memory(user_id)
        starting = credit_manager.get_credit_account(user_id)["credit_balance"]
        with patch.object(ai_routes, "ask") as ask_mock:
            response = self.remember_ask(user_id, "remember-save", "!remember Favorite color is blue")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["remember_command"])
        self.assertEqual(payload["remember_status"], "saved")
        self.assertEqual(payload["message"], "Saved to Memory.")
        self.assertIn("operation_id", payload)
        ask_mock.assert_not_called()
        stored = memory_manager.load_memories(user_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["text"], "Favorite color is blue")
        self.assertEqual(credit_manager.get_credit_account(user_id)["credit_balance"], starting)

    def test_remember_preserves_typed_text_casing(self):
        user_id = self.user_id()
        self.enable_memory(user_id)
        text = "!Remember   My Custom Fact"
        with patch.object(ai_routes, "ask") as ask_mock:
            response = self.remember_ask(user_id, "remember-case", text)
        ask_mock.assert_not_called()
        self.assertEqual(response.status_code, 200)
        stored = memory_manager.load_memories(user_id)
        self.assertEqual(stored[0]["text"], "My Custom Fact")

    def test_remember_requires_memory_master_setting(self):
        user_id = self.user_id()
        settings_manager.save_settings(user_id, {"remember_command_enabled": True})
        response = self.remember_ask(user_id, "remember-no-memory", "!remember fact")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Memory is disabled", response.get_json()["error"])

    def test_remember_rejects_when_command_disabled(self):
        user_id = self.user_id()
        settings_manager.save_settings(
            user_id,
            {"memory_enabled": True, "remember_command_enabled": False},
        )
        response = self.remember_ask(user_id, "remember-disabled", "!remember fact")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Remember command is disabled", response.get_json()["error"])

    def test_remember_validation_failures(self):
        user_id = self.user_id()
        self.enable_memory(user_id)
        cases = [
            ("!remember", "Provide text after !remember."),
            ("!remember " + ("x" * 501), "between 1 and 500"),
            ("!remember password=secret123", "credentials"),
        ]
        for operation_id, case in enumerate(cases):
            question, expected = case
            with self.subTest(question=question[:40]):
                response = self.remember_ask(user_id, f"remember-bad-{operation_id}", question)
                self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
                self.assertIn(expected, response.get_json()["error"])

    def test_remember_duplicate_and_update(self):
        user_id = self.user_id()
        self.enable_memory(user_id)
        first = self.remember_ask(user_id, "remember-dup-1", "!remember Same Fact")
        self.assertEqual(first.get_json()["remember_status"], "saved")
        second = self.remember_ask(user_id, "remember-dup-2", "!remember Same Fact")
        self.assertEqual(second.get_json()["remember_status"], "unchanged")
        third = self.remember_ask(user_id, "remember-dup-3", "!remember same fact")
        self.assertEqual(third.get_json()["remember_status"], "updated")
        stored = memory_manager.load_memories(user_id)
        self.assertEqual(stored[0]["text"], "same fact")

    def test_remember_idempotent_retry(self):
        user_id = self.user_id()
        self.enable_memory(user_id)
        with patch.object(ai_routes, "ask") as ask_mock:
            first = self.remember_ask(user_id, "remember-idem", "!remember Stable fact")
            second = self.remember_ask(user_id, "remember-idem", "!remember Stable fact")
        ask_mock.assert_not_called()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.get_json(), second.get_json())
        self.assertEqual(len(memory_manager.load_memories(user_id)), 1)

    def test_remember_memory_limit(self):
        user_id = self.user_id()
        self.enable_memory(user_id)
        for batch in range(10):
            memory_manager.add_or_update_memories(
                user_id,
                [
                    {"text": f"record {batch}-{index}", "explicit_remember": True}
                    for index in range(10)
                ],
            )
        self.assertEqual(len(memory_manager.load_memories(user_id)), memory_manager.MAX_MEMORIES)
        response = self.remember_ask(user_id, "remember-cap", "!remember brand new fact")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Memory limit reached", response.get_json()["error"])
        texts = {item["text"] for item in memory_manager.load_memories(user_id)}
        self.assertNotIn("brand new fact", texts)

    def test_settings_default_remember_command_enabled(self):
        user_id = self.user_id()
        response = self.client.get("/settings/", headers=self.headers(user_id, "settings-get"))
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.get_json()["remember_command_enabled"], True)

    def test_failed_operation_id_does_not_run_remember(self):
        user_id = self.user_id()
        operation_id = "remember-failed-op"
        from app.credits import repository

        self.enable_memory(user_id)
        credit_manager.claim_operation(user_id, operation_id)
        with repository.locked_credits(user_id, config.AI_CREDIT_INITIAL_BALANCE) as session:
            repository.apply_fail(session, user_id, operation_id, {"error": "prior failure"})
        with patch("app.ai.routes.execute_remember_command") as remember_mock:
            response = self.remember_ask(user_id, operation_id, "!remember keep this fact")
        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertEqual(payload["error"], "operation_failed")
        remember_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
