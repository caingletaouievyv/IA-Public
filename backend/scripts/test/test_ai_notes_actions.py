# IA/backend/scripts/test/test_ai_notes_actions.py
# Notes feature awareness and AI-assisted Notes actions via Ask.

import datetime
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import jwt

from app import config, create_app, limiter
from app.ai.engine import ask
from app.ai.notes_actions import attempt_notes_action
from app.notes import create_pending, delete_pending
from app.notes import manager as notes_manager


class AINotesActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.notes_patch = patch.object(notes_manager, "DATA_DIR", cls.temp_dir.name)
        cls.notes_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.notes_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        limiter.reset()

    def user_id(self):
        return str(uuid.uuid4())

    def headers(self, user_id, operation_id="notes-action"):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}", "Idempotency-Key": operation_id}

    def seed_note(self, user_id, title="Study", category="school", content="Body"):
        return notes_manager.add_note(
            {"title": title, "category": category, "content": content, "tags": []},
            user_id,
        )

    def test_feature_question_without_notes_interpreter(self):
        user_id = self.user_id()
        with patch("app.ai.notes_actions.interpret_notes_plan") as interpret:
            answer, _, status, notes_action = ask("What can you help me with?", user_id=user_id)
        interpret.assert_not_called()
        self.assertEqual(status, "disabled")
        self.assertEqual(notes_action["status"], "answered")
        self.assertIn("Notes", answer)

    def test_create_note_executes_via_interpreter(self):
        user_id = self.user_id()
        plan = {
            "kind": "create_note",
            "title": "Todo",
            "category": "tasks",
            "content": "Finish report",
        }
        with patch("app.ai.notes_actions.interpret_notes_plan", return_value=plan):
            answer, _, _, notes_action = ask("Create a note titled Todo", user_id=user_id)
        self.assertEqual(notes_action["status"], "executed")
        self.assertEqual(notes_action["action"], "create_note")
        self.assertIn("Created note", answer)
        stored = notes_manager.load_notes(user_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["title"], "Todo")

    def test_update_note_append(self):
        user_id = self.user_id()
        self.seed_note(user_id, title="Budget", content="Rent 500")
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={
                "kind": "update_note",
                "match_title": "Budget",
                "append_content": "\nUtilities 80",
            },
        ):
            _, _, _, notes_action = ask("Append utilities to Budget note", user_id=user_id)
        self.assertEqual(notes_action["status"], "executed")
        updated = notes_manager.get_note(notes_action["note"]["id"], user_id)
        self.assertIn("Utilities 80", updated["content"])

    def test_read_plan_defers_to_normal_ask_without_notes_action(self):
        user_id = self.user_id()
        self.seed_note(user_id, title="Project Ideas", content="Secret body")
        with (
            patch(
                "app.ai.notes_actions.interpret_notes_plan",
                return_value={"kind": "read_note", "match_title": "Project Ideas"},
            ),
            patch("app.ai.engine.call_ai", return_value="Model answer"),
        ):
            answer, _, _, notes_action = ask(
                "Show me my Project Ideas note",
                user_id=user_id,
                note_context_mode="off",
            )
        self.assertIsNone(notes_action)
        self.assertEqual(answer, "Model answer")
        self.assertNotIn("Secret body", answer)

    def test_search_plan_defers_without_notes_action(self):
        user_id = self.user_id()
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={"kind": "search_notes", "search_query": "budget"},
        ):
            self.assertIsNone(attempt_notes_action(user_id, "Show my notes"))

    def test_find_notes_phrasing_defers_without_search_action(self):
        user_id = self.user_id()
        self.seed_note(user_id, title="Budget", content="Rent 500")
        with (
            patch(
                "app.ai.notes_actions.interpret_notes_plan",
                return_value={"kind": "search_notes", "search_query": "budget"},
            ),
            patch("app.ai.engine.call_ai", return_value="Model answer"),
        ):
            answer, _, _, notes_action = ask(
                "Find notes about budget",
                user_id=user_id,
                note_context_mode="off",
            )
        self.assertIsNone(notes_action)
        self.assertEqual(answer, "Model answer")
        self.assertNotIn("Rent 500", answer)

    def test_ambiguous_update_requests_clarification(self):
        user_id = self.user_id()
        self.seed_note(user_id, title="Alpha")
        self.seed_note(user_id, title="Alphabet")
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={"kind": "update_note", "match_title": "Al"},
        ):
            answer, _, _, notes_action = ask("Update note Al", user_id=user_id)
        self.assertEqual(notes_action["status"], "clarify")
        self.assertIn("Multiple notes", answer)

    def test_delete_requires_exact_title_confirmation(self):
        user_id = self.user_id()
        note = self.seed_note(user_id, title="Temp")
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={"kind": "delete_note", "match_title": "Temp"},
        ):
            _, _, _, notes_action = ask("Delete note Temp", user_id=user_id)
        self.assertEqual(notes_action["status"], "confirm_required")
        self.assertIn("Type the exact title", notes_action["message"])
        self.assertIsNotNone(notes_manager.get_note(note["id"], user_id))

        with patch("app.ai.notes_actions.interpret_notes_plan") as interpret:
            _, _, _, notes_action = ask("Temp", user_id=user_id)
        interpret.assert_not_called()
        self.assertEqual(notes_action["status"], "executed")
        self.assertIsNone(notes_manager.get_note(note["id"], user_id))

    def test_wrong_confirmation_title_does_not_delete(self):
        user_id = self.user_id()
        note = self.seed_note(user_id, title="Temp")
        delete_pending.set_pending_delete(user_id, note["id"], "Temp")
        with patch("app.ai.notes_actions.interpret_notes_plan") as interpret:
            _, _, _, notes_action = ask("temp", user_id=user_id)
        interpret.assert_not_called()
        self.assertEqual(notes_action["status"], "confirm_failed")
        self.assertIsNotNone(notes_manager.get_note(note["id"], user_id))

    def test_cancel_pending_deletion(self):
        user_id = self.user_id()
        note = self.seed_note(user_id, title="Keep Me")
        delete_pending.set_pending_delete(user_id, note["id"], "Keep Me")
        _, _, _, notes_action = ask("Cancel deletion", user_id=user_id)
        self.assertEqual(notes_action["status"], "cancelled")
        self.assertIsNotNone(notes_manager.get_note(note["id"], user_id))
        self.assertIsNone(delete_pending.get_pending_delete(user_id))

    def test_confirmation_without_pending_does_not_delete(self):
        user_id = self.user_id()
        note = self.seed_note(user_id, title="Temp")
        with (
            patch("app.ai.notes_actions.interpret_notes_plan") as interpret,
            patch("app.ai.engine.call_ai", return_value="Unrelated answer"),
        ):
            _, _, _, notes_action = ask("Temp", user_id=user_id)
        interpret.assert_not_called()
        self.assertIsNone(notes_action)
        self.assertIsNotNone(notes_manager.get_note(note["id"], user_id))

    def test_cross_user_cannot_confirm_another_users_pending(self):
        owner = self.user_id()
        other = self.user_id()
        note = self.seed_note(owner, title="Private")
        delete_pending.set_pending_delete(owner, note["id"], "Private")
        with (
            patch("app.ai.notes_actions.interpret_notes_plan") as interpret,
            patch("app.ai.engine.call_ai", return_value="Unrelated answer"),
        ):
            _, _, _, notes_action = ask("Private", user_id=other)
        interpret.assert_not_called()
        self.assertIsNone(notes_action)
        self.assertIsNotNone(notes_manager.get_note(note["id"], owner))

    def test_pending_cleared_when_note_title_changes(self):
        user_id = self.user_id()
        note = self.seed_note(user_id, title="Original")
        delete_pending.set_pending_delete(user_id, note["id"], "Original")
        notes_manager.update_note(note["id"], {"title": "Renamed"}, user_id)
        with patch("app.ai.notes_actions.interpret_notes_plan") as interpret:
            _, _, _, notes_action = ask("Original", user_id=user_id)
        interpret.assert_not_called()
        self.assertEqual(notes_action["status"], "failed")
        self.assertIsNotNone(notes_manager.get_note(note["id"], user_id))

    def test_expired_pending_does_not_delete(self):
        user_id = self.user_id()
        note = self.seed_note(user_id, title="Expire")
        delete_pending.set_pending_delete(user_id, note["id"], "Expire")
        pending = delete_pending.get_pending_delete(user_id)
        pending["expires_at"] = 1
        path = delete_pending._pending_path(user_id)
        import json
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(pending, handle)
        with (
            patch("app.ai.notes_actions.interpret_notes_plan") as interpret,
            patch("app.ai.engine.call_ai", return_value="Unrelated answer"),
        ):
            _, _, _, notes_action = ask("Expire", user_id=user_id)
        interpret.assert_not_called()
        self.assertIsNone(notes_action)
        self.assertIsNotNone(notes_manager.get_note(note["id"], user_id))

    def test_cross_user_delete_request_does_not_remove_owner_note(self):
        owner = self.user_id()
        other = self.user_id()
        note = self.seed_note(owner, title="Private")
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={"kind": "delete_note", "match_title": "Private"},
        ):
            _, _, _, notes_action = ask("Delete note Private", user_id=other)
        self.assertEqual(notes_action["status"], "clarify")
        self.assertIsNotNone(notes_manager.get_note(note["id"], owner))

    def test_ask_route_returns_notes_action_payload(self):
        user_id = self.user_id()
        with (
            patch("app.ai.routes.ask", return_value=("Done", 3, "disabled", {
                "status": "executed",
                "action": "list_notes",
                "message": "Saved notes:\n- A (general)",
            })),
            patch("app.ai.routes.reserve_credits", return_value={"charged": True}),
        ):
            response = self.client.post(
                "/ai/ask",
                json={"question": "List my notes"},
                headers=self.headers(user_id),
            )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["notes_action"]["action"], "list_notes")

    def test_create_without_content_asks_for_clarification(self):
        user_id = self.user_id()
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={"kind": "create_note", "title": "Project Ideas"},
        ):
            _, _, _, notes_action = ask("Create a note called Project Ideas", user_id=user_id)
        self.assertEqual(notes_action["status"], "clarify")
        self.assertEqual(notes_action["action"], "create_note")
        self.assertIn("suggestions", notes_action)
        self.assertGreaterEqual(len(notes_action["suggestions"]), 1)
        self.assertIn("PDF", notes_action["message"])
        self.assertIsNotNone(create_pending.get_pending_create(user_id))
        self.assertEqual(notes_manager.load_notes(user_id), [])

    def test_ap_pdf_later_conversation_persists_blank_note(self):
        user_id = self.user_id()
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={
                "kind": "none",
                "clarification_needed": "What should the note be called?",
            },
        ):
            _, _, _, notes_action = ask(
                "Create a note for me. I want to upload a PDF later.",
                user_id=user_id,
            )
        self.assertEqual(notes_action["status"], "clarify")
        self.assertEqual(notes_action["action"], "create_note")
        self.assertIsNotNone(create_pending.get_pending_create(user_id))

        with patch("app.ai.engine.call_ai", return_value="I created your note."):
            _, _, _, notes_action = ask(
                "Title is A.P. Leave the content blank.",
                user_id=user_id,
            )
        self.assertEqual(notes_action["status"], "executed")
        self.assertEqual(notes_action["action"], "create_note")
        self.assertIn("note", notes_action)
        self.assertTrue(notes_action["note"]["id"])
        stored = notes_manager.load_notes(user_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["title"], "A.P")
        self.assertEqual(stored[0]["content"], "")
        self.assertEqual(stored[0]["id"], notes_action["note"]["id"])
        self.assertIsNone(create_pending.get_pending_create(user_id))

    def test_create_blank_note_after_clarification_followup(self):
        user_id = self.user_id()
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={"kind": "create_note"},
        ):
            _, _, _, notes_action = ask(
                "hey create a note for me make it note thru pdf",
                user_id=user_id,
            )
        self.assertEqual(notes_action["status"], "clarify")

        with patch("app.ai.engine.call_ai", return_value="I created your note."):
            _, _, _, notes_action = ask(
                "title would be A.P the content leave it blank imma upload it on my own",
                user_id=user_id,
            )
        self.assertEqual(notes_action["status"], "executed")
        self.assertEqual(notes_action["action"], "create_note")
        stored = notes_manager.load_notes(user_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["title"], "A.P")
        self.assertEqual(stored[0]["content"], "")

    def test_create_blank_note_in_one_step_when_intent_is_clear(self):
        user_id = self.user_id()
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={
                "kind": "create_note",
                "title": "A.P",
                "content_intentionally_empty": True,
            },
        ):
            _, _, _, notes_action = ask(
                "Create note A.P with blank body for PDF upload",
                user_id=user_id,
            )
        self.assertEqual(notes_action["status"], "executed")
        stored = notes_manager.load_notes(user_id)
        self.assertEqual(stored[0]["title"], "A.P")
        self.assertEqual(stored[0]["content"], "")

    def test_replace_content_and_rename(self):
        user_id = self.user_id()
        note = self.seed_note(user_id, title="Project Ideas", content="Old body")
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={
                "kind": "update_note",
                "match_title": "Project Ideas",
                "title": "App Ideas",
                "content": "New body",
                "replace_content": True,
            },
        ):
            _, _, _, notes_action = ask(
                "Rename note Project Ideas to App Ideas and replace the content",
                user_id=user_id,
            )
        self.assertEqual(notes_action["status"], "executed")
        updated = notes_manager.get_note(note["id"], user_id)
        self.assertEqual(updated["title"], "App Ideas")
        self.assertEqual(updated["content"], "New body")

    def test_update_failure_when_storage_returns_none(self):
        user_id = self.user_id()
        self.seed_note(user_id, title="Budget", content="Rent")
        with (
            patch(
                "app.ai.notes_actions.interpret_notes_plan",
                return_value={"kind": "update_note", "match_title": "Budget", "append_content": " more"},
            ),
            patch("app.ai.notes_actions.update_note", return_value=None),
        ):
            _, _, _, notes_action = ask("Append to Budget", user_id=user_id)
        self.assertEqual(notes_action["status"], "failed")

    def test_invalid_create_plan_fails_without_storage(self):
        user_id = self.user_id()
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={"kind": "create_note", "title": "x" * 101, "category": "general", "content": "ok"},
        ):
            _, _, _, notes_action = ask("Create a note", user_id=user_id)
        self.assertEqual(notes_action["status"], "failed")
        self.assertEqual(notes_manager.load_notes(user_id), [])

    def test_list_notes(self):
        user_id = self.user_id()
        self.seed_note(user_id, title="Alpha", content="One")
        self.seed_note(user_id, title="Beta", content="Two")
        with patch(
            "app.ai.notes_actions.interpret_notes_plan",
            return_value={"kind": "list_notes"},
        ):
            answer, _, _, notes_action = ask("Show my notes", user_id=user_id)
        self.assertEqual(notes_action["status"], "executed")
        self.assertEqual(notes_action["action"], "list_notes")
        self.assertIn("Alpha", answer)
        self.assertIn("Beta", answer)

    def test_create_failure_when_storage_returns_none(self):
        user_id = self.user_id()
        with (
            patch(
                "app.ai.notes_actions.interpret_notes_plan",
                return_value={
                    "kind": "create_note",
                    "title": "Todo",
                    "category": "general",
                    "content": "Body",
                },
            ),
            patch("app.ai.notes_actions.add_note", return_value=None),
        ):
            _, _, _, notes_action = ask("Create a note titled Todo", user_id=user_id)
        self.assertEqual(notes_action["status"], "failed")
        self.assertEqual(notes_manager.load_notes(user_id), [])


if __name__ == "__main__":
    unittest.main()
