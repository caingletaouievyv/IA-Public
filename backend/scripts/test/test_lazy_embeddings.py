# IA/scripts/test/test_lazy_embeddings.py
# Verify application startup does not load the embedding model.

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class LazyEmbeddingTests(unittest.TestCase):
    def test_importing_run_does_not_initialize_sentence_transformer(self):
        with patch("sentence_transformers.SentenceTransformer") as model_constructor:
            import run
            from app.memory import embeddings

            model_constructor.assert_not_called()
            self.assertIsNone(embeddings.model)
            self.assertEqual(run.app.test_client().get("/health").status_code, 200)

            with patch.object(embeddings, "SentenceTransformer", return_value=object()) as lazy_constructor:
                first_model = embeddings._get_model()
                second_model = embeddings._get_model()

            self.assertIs(first_model, second_model)
            lazy_constructor.assert_called_once_with("sentence-transformers/all-MiniLM-L6-v2")


if __name__ == "__main__":
    unittest.main()