# IA/backend/scripts/test/test_semantic_retrieval.py
# Semantic note search with stubbed vectors. This does not download a model or call an API.

import os
import sys
import unittest
from unittest.mock import patch

import numpy as np

from app.memory import embeddings, manager
from app.memory.embeddings import get_relevant_notes_subset
from app.notes.manager import HISTORY_CATEGORY

_PICKLE_NAMES = ("faiss_index.pkl", "note_map.pkl", "faiss_fingerprint.txt")


def note(note_id, title="", category="general", tags=None, content=""):
    return {
        "id": note_id,
        "title": title,
        "category": category,
        "tags": tags or [],
        "content": content,
    }


def stub_encode(texts):
    """Map marker text to a fixed 384-dimensional vector. Ranking stays in FAISS."""
    vectors = np.zeros((len(texts), embeddings.DIM), dtype=np.float32)
    for index, text in enumerate(texts):
        if "high-marker" in text or "score-high" in text or "alpha-marker" in text:
            vectors[index, 0] = 1.0
        elif "score-mid" in text:
            vectors[index, 0] = 0.5
        elif "low-marker" in text:
            vectors[index, 0] = 0.25
        elif "score-low" in text:
            vectors[index, 0] = 0.2
        elif "beta-marker" in text:
            vectors[index, 1] = 1.0
        else:
            vectors[index, 2] = 1.0
    return vectors


class SemanticRetrievalTests(unittest.TestCase):
    def setUp(self):
        manager.intent_cache.cache.clear()
        self.model = patch("sentence_transformers.SentenceTransformer").start()
        self.addCleanup(patch.stopall)

    def test_sentence_transformer_is_not_loaded(self):
        notes = [note("alpha", content="alpha-marker"), note("beta", content="beta-marker")]
        with patch("app.memory.embeddings.encode_texts", stub_encode):
            results = get_relevant_notes_subset("alpha-marker", notes)

        self.model.assert_not_called()
        self.assertEqual([item[1]["id"] for item in results], ["alpha", "beta"])

    def test_empty_input_returns_empty_without_encoding(self):
        with patch("app.memory.embeddings.encode_texts", side_effect=AssertionError("encoded")):
            self.assertEqual(get_relevant_notes_subset("algebra", []), [])
            self.assertEqual(get_relevant_notes_subset("algebra", [note("blank", content="")]), [])
            self.assertEqual(get_relevant_notes_subset("algebra", [note("blank", content="   ")]), [])
        self.model.assert_not_called()

    def test_only_supplied_notes_are_searched(self):
        notes = [note("alpha", content="alpha-marker"), note("beta", content="beta-marker")]
        with patch("app.memory.embeddings.encode_texts", stub_encode):
            results = get_relevant_notes_subset("alpha-marker", notes, top_n=5)

        self.assertEqual([item[1]["id"] for item in results], ["alpha", "beta"])
        self.assertAlmostEqual(results[0][0], 1.0, places=5)
        self.assertAlmostEqual(results[1][0], 0.0, places=5)

    def test_best_chunk_score_wins(self):
        words = ["low-marker"] + ["filler"] * 119 + ["high-marker"]
        notes = [note("chunked", content=" ".join(words))]
        with patch("app.memory.embeddings.encode_texts", stub_encode):
            results = get_relevant_notes_subset("high-marker", notes)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1]["id"], "chunked")
        self.assertAlmostEqual(results[0][0], 1.0, places=5)

    def test_top_n_limits_results(self):
        notes = [
            note("high", content="score-high"),
            note("mid", content="score-mid"),
            note("low", content="score-low"),
        ]
        with patch("app.memory.embeddings.encode_texts", stub_encode):
            first = get_relevant_notes_subset("score-high", notes, top_n=1)
            first_two = get_relevant_notes_subset("score-high", notes, top_n=2)

        self.assertEqual([item[1]["id"] for item in first], ["high"])
        self.assertEqual([item[1]["id"] for item in first_two], ["high", "mid"])

    def test_query_normalization(self):
        seen = []

        def record(texts):
            seen.append(list(texts))
            return np.zeros((len(texts), embeddings.DIM), dtype=np.float32)

        notes = [note("one", content="placeholder")]
        with patch("app.memory.embeddings.encode_texts", record):
            get_relevant_notes_subset("Find the algebra 42", notes)
            get_relevant_notes_subset("Find the algebra 42", notes, preserve_numbers=True)

        self.assertEqual(seen[1], ["algebra"])
        self.assertEqual(seen[3], ["algebra 42"])
        self.model.assert_not_called()

    def test_no_faiss_pickle_files_are_opened(self):
        opened = []

        def audit(event, args):
            if event != "open" or not args or not isinstance(args[0], (str, os.PathLike)):
                return
            opened.append(os.fspath(args[0]))

        sys.addaudithook(audit)
        notes = [note("alpha", content="alpha-marker")]
        with patch("app.memory.embeddings.encode_texts", stub_encode):
            get_relevant_notes_subset("alpha-marker", notes)

        self.assertFalse(any(any(name in path for name in _PICKLE_NAMES) for path in opened))

    def test_manager_semantic_wiring_excludes_history(self):
        notes = [
            note("keep", title="Keep", content="alpha-marker"),
            note("hist", title="Secret History", category=HISTORY_CATEGORY, content="alpha-marker"),
        ]
        seen = []
        real = embeddings.get_relevant_notes_subset

        def spy(query, candidates, top_n=5, preserve_numbers=False):
            seen.append([item["id"] for item in candidates])
            return real(query, candidates, top_n=top_n, preserve_numbers=preserve_numbers)

        with (
            patch.object(manager, "load_notes", return_value=notes) as load_notes,
            patch.object(manager, "MEMORY_RETRIEVAL", "semantic"),
            patch("app.memory.manager.log_memory_event"),
            patch("app.memory.embeddings.encode_texts", stub_encode),
            patch("app.memory.embeddings.get_relevant_notes_subset", spy),
        ):
            result = manager.build_context(
                "alpha-marker",
                user_id="user-1",
                note_context_mode="automatic",
                memory_context_mode="off",
            )

        load_notes.assert_called_once_with("user-1")
        self.assertEqual(seen, [["keep"]])
        self.assertIn("Keep:", result["context"])
        self.assertNotIn("Secret History", result["context"])
        self.model.assert_not_called()

    def test_semantic_threshold_boundaries(self):
        # FAISS returns float32, so the next lower value falls below each threshold.
        boundaries = (
            ("boundary topic", 0.649, "Exploratory"),
            ("lookup boundary", 0.54, "Lookup"),
        )
        for query, threshold, label in boundaries:
            at_score = np.float32(threshold)
            below_score = np.nextafter(at_score, np.float32(0))
            qualifying = note(f"{label}-at", title=f"At {label}", content=f"at-{label}")
            rejected = note(f"{label}-below", title=f"Below {label}", content=f"below-{label}")
            scores = {qualifying["content"]: at_score, rejected["content"]: below_score}

            both = self._semantic_context([qualifying, rejected], query, scores)
            self.assertEqual(both["note_titles"], [qualifying["title"]])
            self.assertNotIn(rejected["title"], both["context"])
            self.assertAlmostEqual(both["best_score"], threshold, places=5)

            manager.intent_cache.cache.clear()
            only_below = self._semantic_context([rejected], query, scores)
            self.assertEqual(only_below["context"], "")
            self.assertEqual(only_below["note_titles"], [])
            self.assertAlmostEqual(only_below["best_score"], float(below_score), places=5)
            manager.intent_cache.cache.clear()
        self.model.assert_not_called()

    def test_faiss_top_n_times_three_window(self):
        filler = note("filler", title="Filler", content=" ".join(["filler-marker"] * 451))
        hidden = note("hidden", title="Hidden", content="hidden-marker")
        scores = {"filler-marker": np.float32(0.8), "hidden-marker": np.float32(0.4)}
        with patch("app.memory.embeddings.encode_texts", self._score_encode(scores)):
            narrow = get_relevant_notes_subset("window query", [filler, hidden], top_n=2)
            wide = get_relevant_notes_subset("window query", [filler, hidden], top_n=3)

        self.assertEqual([item[1]["id"] for item in narrow], ["filler"])
        self.assertAlmostEqual(narrow[0][0], 0.8, places=5)
        self.assertEqual([item[1]["id"] for item in wide], ["filler", "hidden"])
        self.assertAlmostEqual(wide[0][0], 0.8, places=5)
        self.assertAlmostEqual(wide[1][0], 0.4, places=5)
        self.model.assert_not_called()

    def test_manager_preserve_numbers(self):
        notes = [note("kept", title="Kept", content="threshold-note")]
        scores = {"threshold-note": np.float32(0.60)}
        encoded = []
        flags = []
        real = embeddings.get_relevant_notes_subset

        def spy(query, candidates, top_n=5, preserve_numbers=False):
            flags.append(preserve_numbers)
            return real(query, candidates, top_n=top_n, preserve_numbers=preserve_numbers)

        def record(texts):
            encoded.append(list(texts))
            return self._score_encode(scores)(texts)

        queries = (
            ("stress level 42", True, "stress level 42", ["Kept"]),
            ("Find the algebra 42", True, "algebra 42", ["Kept"]),
            ("algebra level 42", False, "algebra level", []),
        )
        with (
            patch.object(manager, "load_notes", return_value=notes),
            patch.object(manager, "MEMORY_RETRIEVAL", "semantic"),
            patch("app.memory.manager.log_memory_event"),
            patch("app.memory.embeddings.encode_texts", record),
            patch("app.memory.embeddings.get_relevant_notes_subset", spy),
        ):
            results = []
            for query, _flag, _text, _titles in queries:
                manager.intent_cache.cache.clear()
                results.append(manager.build_context(
                    query,
                    user_id="user-1",
                    note_context_mode="automatic",
                    memory_context_mode="off",
                ))

        self.assertEqual(flags, [True, True, False])
        self.assertEqual([encoded[1], encoded[3], encoded[5]], [
            ["stress level 42"],
            ["algebra 42"],
            ["algebra level"],
        ])
        for result, (_query, _flag, _text, titles) in zip(results, queries):
            self.assertEqual(result["note_titles"], titles)
            self.assertAlmostEqual(result["best_score"], 0.60, places=5)
        self.assertEqual(results[2]["context"], "")
        self.model.assert_not_called()

    def _semantic_context(self, notes, query, scores):
        with (
            patch.object(manager, "load_notes", return_value=notes),
            patch.object(manager, "MEMORY_RETRIEVAL", "semantic"),
            patch("app.memory.manager.log_memory_event"),
            patch("app.memory.embeddings.encode_texts", self._score_encode(scores)),
        ):
            return manager.build_context(
                query,
                user_id="user-1",
                note_context_mode="automatic",
                memory_context_mode="off",
            )

    def _score_encode(self, scores):
        def encode(texts):
            vectors = np.zeros((len(texts), embeddings.DIM), dtype=np.float32)
            for index, text in enumerate(texts):
                vectors[index, 0] = np.float32(1.0)
                for marker, score in scores.items():
                    if marker in text:
                        vectors[index, 0] = score
                        break
            return vectors
        return encode


if __name__ == "__main__":
    unittest.main()
