import unittest

from app.ai.engine import _build_system_content


class AIResponseStyleTests(unittest.TestCase):
    def test_empty_context_forbids_note_source_labels(self):
        system_content = _build_system_content("", [])

        self.assertIn("No note context is available", system_content)
        self.assertIn("Do not mention or imply", system_content)
        self.assertIn("[From your notes]", system_content)
        self.assertIn("Respond normally and conversationally", system_content)

    def test_note_context_keeps_note_specific_instructions(self):
        system_content = _build_system_content("Biology: Cell structure", ["Biology"])

        self.assertIn("context is from the user's notes", system_content)
        self.assertIn("topic: Biology", system_content)
        self.assertIn("grounded in the provided note content", system_content)
        self.assertNotIn("No note context is available", system_content)


if __name__ == "__main__":
    unittest.main()