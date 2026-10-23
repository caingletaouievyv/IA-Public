"""Authenticated flashcard-generation route regressions."""

import datetime
import json
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import jwt

from app import create_app, config
from app.credits import manager as credit_manager
from app.notes import manager as notes_manager


class FlashcardRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.notes_data_patch = patch.object(notes_manager, "DATA_DIR", cls.temp_dir.name)
        cls.credits_data_patch = patch.object(credit_manager, "DATA_DIR", cls.temp_dir.name)
        cls.notes_data_patch.start()
        cls.credits_data_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        cls.client = cls.app.test_client()
        cls.role_patch = patch("app.ai.routes.get_user_role", return_value="user")
        cls.role_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.role_patch.stop()
        cls.credits_data_patch.stop()
        cls.notes_data_patch.stop()
        cls.temp_dir.cleanup()

    def user_id(self):
        return str(uuid.uuid4())

    def headers(self, user_id):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}"}

    def add_note(self, user_id, title, content, category="study"):
        return notes_manager.add_note(
            {"title": title, "category": category, "content": content, "tags": []},
            user_id,
        )

    def request_data(self, note_id, **overrides):
        return {
            "note_ids": [note_id],
            "card_count": 2,
            "difficulty": "Mixed",
            "question_style": "Understanding",
            "language": "Same as notes",
            "additional_instructions": "",
            "request_id": str(uuid.uuid4()),
            **overrides,
        }

    def test_generation_uses_only_selected_owned_notes_and_validates_cards(self):
        user_id = self.user_id()
        selected = self.add_note(user_id, "Biology", "Plants use light to make sugars.")
        self.add_note(user_id, "Other", "This material must not be sent.")
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]
        provider_output = json.dumps({
            "cards": [
                {"question": "What do plants make?", "answer": "Sugars."},
                {"question": "What energy source is used?", "answer": "Light."},
            ],
        })

        with patch("app.ai.flashcards.call_ai", return_value=provider_output) as provider:
            response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(selected["id"]),
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["cards"], json.loads(provider_output)["cards"])
        self.assertEqual(
            credit_manager.get_credit_account(user_id)["credit_balance"],
            initial_balance - config.AI_ASK_CREDIT_COST,
        )
        provider.assert_called_once()
        messages = provider.call_args.kwargs["messages"]
        self.assertIn("untrusted user data", messages[0]["content"])
        source_payload = json.loads(messages[1]["content"])
        self.assertEqual(source_payload["source_notes"], [
            {"title": "Biology", "content": "Plants use light to make sugars."},
        ])

    def test_language_defaults_to_same_as_notes_when_omitted(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Biology", "Plants use light to make sugars.")
        request_data = self.request_data(note["id"])
        request_data.pop("language")
        provider_output = json.dumps({
            "cards": [
                {"question": "What do plants make?", "answer": "Sugars."},
                {"question": "What energy source is used?", "answer": "Light."},
            ],
        })

        with patch("app.ai.flashcards.call_ai", return_value=provider_output) as provider:
            response = self.client.post(
                "/ai/flashcards/generate",
                json=request_data,
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        provider.assert_called_once()
        source_payload = json.loads(provider.call_args.kwargs["messages"][1]["content"])
        self.assertEqual(source_payload["language"], "Same as notes")

    def test_authentication_and_note_ownership_are_required(self):
        user_id, other_user = self.user_id(), self.user_id()
        foreign_note = self.add_note(other_user, "Private", "Private source.")

        unauthenticated = self.client.post(
            "/ai/flashcards/generate",
            json=self.request_data(foreign_note["id"]),
        )
        self.assertEqual(unauthenticated.status_code, 401)

        with patch("app.ai.flashcards.call_ai") as provider:
            response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(foreign_note["id"]),
                headers=self.headers(user_id),
            )
        self.assertEqual(response.status_code, 400)
        provider.assert_not_called()

    def test_invalid_request_and_history_note_are_rejected_before_provider_call(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "A source.")
        history = self.add_note(user_id, "History", "[]", category="_history")

        with patch("app.ai.flashcards.call_ai") as provider:
            invalid_count = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(note["id"], card_count=True),
                headers=self.headers(user_id),
            )
            invalid_style = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(note["id"], question_style="Unknown"),
                headers=self.headers(user_id),
            )
            history_response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(history["id"]),
                headers=self.headers(user_id),
            )

        self.assertEqual(invalid_count.status_code, 400)
        self.assertEqual(invalid_style.status_code, 400)
        self.assertEqual(history_response.status_code, 400)
        provider.assert_not_called()

    def test_malformed_provider_response_fails_and_refunds_reserved_credit(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "A source.")
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]

        with (
            self.assertLogs("ia.understanding", level="WARNING") as captured,
            patch(
                "app.ai.flashcards.call_ai",
                return_value="PRIVATE_PROVIDER_OUTPUT_SENTINEL",
            ),
        ):
            response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(note["id"]),
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 502)
        self.assertIn("code=flashcards.generation_failed", captured.output[0])
        self.assertNotIn("PRIVATE_PROVIDER_OUTPUT_SENTINEL", captured.output[0])
        self.assertEqual(
            credit_manager.get_credit_account(user_id)["credit_balance"],
            initial_balance,
        )


if __name__ == "__main__":
    unittest.main()
