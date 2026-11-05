# IA/scripts/test/test_lazy_embeddings.py
# Verify application startup does not load the embedding model or the persistent FAISS cache.

import importlib
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_PICKLE_NAMES = ("faiss_index.pkl", "note_map.pkl", "faiss_fingerprint.txt")


class LazyEmbeddingTests(unittest.TestCase):
    def test_importing_run_does_not_initialize_sentence_transformer(self):
        with patch("sentence_transformers.SentenceTransformer") as model_constructor:
            import run
            embeddings = self._import_embeddings()

            model_constructor.assert_not_called()
            self.assertIsNone(embeddings.model)
            self.assertEqual(run.app.test_client().get("/health").status_code, 200)

            with patch("sentence_transformers.SentenceTransformer", return_value=object()) as lazy_constructor:
                first_model = embeddings._get_model()
                second_model = embeddings._get_model()

            self.assertIs(first_model, second_model)
            lazy_constructor.assert_called_once_with("sentence-transformers/all-MiniLM-L6-v2")

    def test_importing_embeddings_does_not_load_the_persistent_cache(self):
        opened = []

        def audit(event, args):
            if event != "open" or not args or not isinstance(args[0], (str, os.PathLike)):
                return
            opened.append(os.fspath(args[0]))

        sys.addaudithook(audit)
        embeddings = self._import_embeddings()

        self.assertNotIn("app.memory.cache", sys.modules)
        self.assertFalse(hasattr(embeddings, "vector_cache"))
        self.assertFalse(any(any(name in path for name in _PICKLE_NAMES) for path in opened))

    def _import_embeddings(self):
        sys.modules.pop("app.memory.embeddings", None)
        sys.modules.pop("app.memory.cache", None)
        return importlib.import_module("app.memory.embeddings")


if __name__ == "__main__":
    unittest.main()
