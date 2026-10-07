import unittest

from app.ai.engine import _build_system_content, _context_items_from_notes


class AIResponseStyleTests(unittest.TestCase):
    def test_empty_context_forbids_note_source_labels(self):
        system_content = _build_system_content(_context_items_from_notes({"context": ""}))

        self.assertIn("No note context is available", system_content)
        self.assertIn("Do not mention or imply", system_content)
        self.assertIn("[From your notes]", system_content)
        self.assertIn("Respond normally and conversationally", system_content)

    def test_note_context_keeps_note_specific_instructions(self):
        context_items = _context_items_from_notes({
            "context": "Biology: Cell structure",
            "note_titles": ["Biology"],
        })
        system_content = _build_system_content(context_items)

        self.assertEqual(len(context_items), 1)
        self.assertEqual(context_items[0].source, "notes")
        self.assertEqual(context_items[0].content, "Biology: Cell structure")
        self.assertEqual(context_items[0].metadata, {"note_titles": ["Biology"]})
        self.assertIn("context is from the user's notes", system_content)
        self.assertIn("topic: Biology", system_content)
        self.assertIn("grounded in the provided note content", system_content)
        self.assertNotIn("No note context is available", system_content)

    def test_empty_note_context_is_not_emitted_as_an_item(self):
        self.assertEqual(_context_items_from_notes(None), [])


if __name__ == "__main__":
    unittest.main()