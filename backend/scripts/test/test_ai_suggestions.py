"""AI suggestion selection, privacy, authentication, and per-user regressions."""

import datetime
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import jwt

from app import config, create_app
from app.activity import manager as activity_manager
from app.settings import manager as settings_manager


class AISuggestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.activity_dir_patch = patch.object(activity_manager, "DATA_DIR", cls.temp_dir.name)
        cls.settings_dir_patch = patch.object(settings_manager, "DATA_DIR", cls.temp_dir.name)
        cls.activity_dir_patch.start()
        cls.settings_dir_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.settings_dir_patch.stop()
        cls.activity_dir_patch.stop()
        cls.temp_dir.cleanup()

    def headers(self, user_id):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": "Bearer " + token}

    def user_id(self):
        return str(uuid.uuid4())

    def add_recent_events(self, user_id, *event_types):
        for event_type in event_types:
            activity_manager.record_activity(user_id, event_type)

    def test_suggestion_requires_auth_and_setting_off_prevents_generation(self):
        user_id = self.user_id()
        self.add_recent_events(user_id, "note.created", "note.updated")
        self.assertEqual(self.client.post("/ai/suggestions").status_code, 401)

        settings_manager.save_settings(user_id, {"ai_suggestions_enabled": False})
        with patch("app.ai.suggestions.call_ai") as call_ai:
            response = self.client.post("/ai/suggestions", headers=self.headers(user_id))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["suggestion"])
        call_ai.assert_not_called()

    def test_ai_receives_only_recent_event_type_counts_and_returns_allowed_action(self):
        user_id = self.user_id()
        self.add_recent_events(user_id, "note.created", "note.updated")
        captured = {}

        def fake_call_ai(prompt, messages):
            captured["messages"] = messages
            return '{"action":"open_flashcards"}'

        with patch("app.ai.suggestions.call_ai", side_effect=fake_call_ai):
            response = self.client.post("/ai/suggestions", headers=self.headers(user_id))

        self.assertEqual(response.status_code, 200)
        suggestion = response.get_json()["suggestion"]
        self.assertEqual(suggestion["action"], "open_flashcards")
        self.assertEqual(
            suggestion["text"],
            "Turn your recent note activity into a focused flashcard session.",
        )
        self.assertEqual(set(suggestion), {"suggestion_id", "action", "text"})
        serialized_prompt = str(captured["messages"])
        self.assertIn("note.created", serialized_prompt)
        self.assertIn("note.updated", serialized_prompt)
        self.assertNotIn("Private note", serialized_prompt)
        self.assertNotIn("password", serialized_prompt)

    def test_suggestion_context_is_isolated_and_requires_multiple_recent_events(self):
        first_user, second_user = self.user_id(), self.user_id()
        self.add_recent_events(first_user, "note.created", "note.updated")
        self.add_recent_events(second_user, "note.created")

        with patch("app.ai.suggestions.call_ai", return_value='{"action":"prepare_ask"}') as call_ai:
            first = self.client.post("/ai/suggestions", headers=self.headers(first_user))
            second = self.client.post("/ai/suggestions", headers=self.headers(second_user))

        self.assertEqual(first.status_code, 200)
        self.assertIsNotNone(first.get_json()["suggestion"])
        self.assertEqual(second.status_code, 200)
        self.assertIsNone(second.get_json()["suggestion"])
        call_ai.assert_called_once()

    def test_provider_failure_uses_a_fixed_rule_fallback(self):
        user_id = self.user_id()
        self.add_recent_events(user_id, "note.created", "note.updated")

        with patch("app.ai.suggestions.call_ai", side_effect=RuntimeError("provider unavailable")):
            suggestion = self.client.post(
                "/ai/suggestions",
                headers=self.headers(user_id),
            ).get_json()["suggestion"]

        self.assertEqual(suggestion["action"], "prepare_ask")
        self.assertEqual(
            suggestion["text"],
            "Want to ask IA to summarize your recent note changes and suggest next steps?",
        )


if __name__ == "__main__":
    unittest.main()
