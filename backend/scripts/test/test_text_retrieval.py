import unittest
from unittest.mock import patch

from app.memory import manager
from app.memory.text_retrieval import get_relevant_notes_subset


def note(note_id, title="", category="", tags=None, content=""):
    return {
        "id": note_id,
        "title": title,
        "category": category,
        "tags": tags or [],
        "content": content,
    }


class TextRetrievalTests(unittest.TestCase):
    def setUp(self):
        manager.intent_cache.cache.clear()

    def test_title_category_tag_and_content_matching(self):
        notes = [
            note("title", title="Algebra Review", content="unrelated words"),
            note("category", category="Algebra", content="unrelated words"),
            note("tag", tags=["algebra"], content="unrelated words"),
            note("content", content="Algebra appears in the body"),
        ]

        results = get_relevant_notes_subset("algebra", notes, top_n=4)

        self.assertEqual([item[1]["id"] for item in results], ["title", "category", "tag", "content"])
        self.assertTrue(all(0 <= score <= 1 for score, _ in results))

    def test_deterministic_tie_ordering(self):
        notes = [note("first", content="shared term"), note("second", content="shared term")]

        results = get_relevant_notes_subset("shared", notes, top_n=2)

        self.assertEqual([item[1]["id"] for item in results], ["first", "second"])

    def test_chunk_level_matching_and_best_chunk_per_note(self):
        content = " ".join(f"word{i}" for i in range(210))
        content = f"{content} distinctive target"
        notes = [note("chunked", content=content), note("other", content="target")]

        results = get_relevant_notes_subset("target", notes, top_n=2)

        self.assertEqual(results[0][1]["id"], "chunked")
        self.assertEqual(len(results), 2)
        self.assertEqual(len({item[1]["id"] for item in results}), 2)

    def test_candidate_and_top_k_limiting(self):
        notes = [note(str(index), content="same term") for index in range(8)]

        results = get_relevant_notes_subset("same", notes, top_n=2)

        self.assertEqual(len(results), 2)
        self.assertEqual([item[1]["id"] for item in results], ["0", "1"])

    def test_empty_query_and_notes(self):
        self.assertEqual(get_relevant_notes_subset("", [note("one", content="text")]), [])
        self.assertEqual(get_relevant_notes_subset("text", []), [])

    def test_note_ids_filtering_and_unmatched_ids(self):
        notes = [
            note("selected", title="Selected", content="target"),
            note("other", title="Other", content="target"),
        ]
        with patch.object(manager, "load_notes", return_value=notes), patch.object(manager, "MEMORY_RETRIEVAL", "text"):
            selected = manager.build_context("target", note_ids=["selected"], user_id="user")
            unmatched = manager.build_context("target", note_ids=["missing"], user_id="user")

        self.assertIn("Selected:", selected["context"])
        self.assertNotIn("Other:", selected["context"])
        self.assertEqual(unmatched["context"], "")

    def test_lexical_threshold(self):
        notes = [note("body", content="target")]
        with patch.object(manager, "load_notes", return_value=notes), patch.object(manager, "MEMORY_RETRIEVAL", "text"), patch.object(manager, "TEXT_RETRIEVAL_THRESHOLD_EXPLORATORY", 0.5):
            result = manager.build_context("target", user_id="user")

        self.assertEqual(result["context"], "")
        self.assertEqual(result["best_score"], 0.25)

    def test_existing_context_token_packing(self):
        notes = [
            note("first", title="First", content="target first content"),
            note("second", title="Second", content="target second content"),
        ]
        with (
            patch.object(manager, "load_notes", return_value=notes),
            patch.object(manager, "MEMORY_RETRIEVAL", "text"),
            patch.object(manager, "MAX_CONTEXT_TOKENS", 4),
            patch.object(manager, "estimate_tokens", side_effect=lambda text: len(text.split())),
        ):
            result = manager.build_context("target", user_id="user")

        self.assertLessEqual(result["tokens"], 4)
        self.assertIn("First:", result["context"])
        self.assertTrue(result["dropped_notes"])


if __name__ == "__main__":
    unittest.main()
