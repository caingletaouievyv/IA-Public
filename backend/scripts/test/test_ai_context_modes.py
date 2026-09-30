import unittest
from unittest.mock import patch

from app.ai.routes import _parse_note_context_mode
from app.memory import manager


def note(note_id, title, content):
    return {
        "id": note_id,
        "title": title,
        "category": "",
        "tags": [],
        "content": content,
    }


class AIContextModeTests(unittest.TestCase):
    def setUp(self):
        manager.intent_cache.cache.clear()
        self.notes = [
            note("first", "First", "target in first note"),
            note("second", "Second", "target in second note"),
        ]

    def build_context(self, note_ids=None, mode="automatic"):
        with (
            patch.object(manager, "load_notes", return_value=self.notes),
            patch.object(manager, "MEMORY_RETRIEVAL", "text"),
        ):
            return manager.build_context(
                "target",
                note_ids=note_ids,
                user_id="user-1",
                note_context_mode=mode,
            )

    def test_automatic_without_ids_retrieves_relevant_user_notes(self):
        result = self.build_context()

        self.assertIn("First:", result["context"])
        self.assertIn("Second:", result["context"])

    def test_focused_without_ids_returns_empty_without_loading_notes(self):
        with (
            patch.object(manager, "load_notes") as load_notes,
            patch.object(manager, "_get_relevant_notes_subset") as retrieve,
        ):
            result = manager.build_context(
                "target",
                note_ids=[],
                user_id="user-1",
                note_context_mode="focused",
            )

        self.assertEqual(result["context"], "")
        load_notes.assert_not_called()
        retrieve.assert_not_called()

    def test_off_ignores_selected_ids_without_loading_notes(self):
        with (
            patch.object(manager, "load_notes") as load_notes,
            patch.object(manager, "_get_relevant_notes_subset") as retrieve,
        ):
            result = manager.build_context(
                "target",
                note_ids=["first"],
                user_id="user-1",
                note_context_mode="off",
            )

        self.assertEqual(result["context"], "")
        load_notes.assert_not_called()
        retrieve.assert_not_called()

    def test_automatic_with_ids_uses_only_selected_notes(self):
        result = self.build_context(note_ids=["first"])

        self.assertIn("First:", result["context"])
        self.assertNotIn("Second:", result["context"])

    def test_focused_with_ids_uses_only_selected_notes(self):
        result = self.build_context(note_ids=["first"], mode="focused")

        self.assertIn("First:", result["context"])
        self.assertNotIn("Second:", result["context"])

    def test_missing_mode_defaults_to_automatic(self):
        self.assertEqual(_parse_note_context_mode({}), "automatic")

    def test_off_is_a_valid_mode(self):
        self.assertEqual(_parse_note_context_mode({"note_context_mode": "off"}), "off")

    def test_invalid_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "note_context_mode"):
            _parse_note_context_mode({"note_context_mode": "all"})


if __name__ == "__main__":
    unittest.main()