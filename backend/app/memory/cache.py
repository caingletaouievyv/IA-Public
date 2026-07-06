# IA/backend/app/memory/cache.py
"""Persistent FAISS index + note_map; load on init; dimension-checked."""

import faiss
import numpy as np
import os
import pickle
import logging
import hashlib

logger = logging.getLogger(__name__)
CACHE_FILE = "data/faiss_index.pkl"
NOTE_MAP_FILE = "data/note_map.pkl"
FINGERPRINT_FILE = "data/faiss_fingerprint.txt"

class VectorCache:
    def __init__(self, dim=384):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.note_map = []
        self._load_cache()

    def _load_cache(self):
        """Load index + note_map from disk; rebuild empty if missing or dim mismatch."""
        if not (os.path.exists(CACHE_FILE) and os.path.exists(NOTE_MAP_FILE)):
            logger.info("FAISS cache missing → starting fresh")
            return
        try:
            with open(CACHE_FILE, "rb") as f:
                idx = pickle.load(f)
            if idx.d != self.dim:
                logger.warning(f"FAISS dim mismatch {idx.d} != {self.dim} → rebuilding")
                return
            self.index = idx
            with open(NOTE_MAP_FILE, "rb") as f:
                self.note_map = pickle.load(f)
            logger.info(f"FAISS loaded: {self.index.ntotal} vectors")
        except Exception as e:
            logger.error(f"FAISS load failed: {e}")
            self.index = faiss.IndexFlatL2(self.dim)
            self.note_map = []

    def _save_cache(self, fingerprint: str | None = None):
        """Persist index, note_map, optional fingerprint."""
        os.makedirs("data", exist_ok=True)
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(self.index, f)
        with open(NOTE_MAP_FILE, "wb") as f:
            pickle.dump(self.note_map, f)
        if fingerprint:
            self._save_fingerprint(fingerprint)
        logger.info("FAISS cache saved")

    def add_embeddings(self, embeddings: np.ndarray, notes: list):
        """Append vectors + note metadata; save."""
        if embeddings.ndim != 2 or embeddings.shape[1] != self.dim:
            raise ValueError(f"Bad shape {embeddings.shape}, expected (?, {self.dim})")
        self.index.add(embeddings)
        self.note_map.extend(notes)
        self._save_cache()

    def search(self, query_embedding: np.ndarray, top_n: int = 5):
        """Return list of (distance, note) for top_n nearest."""
        if self.index.ntotal == 0:
            return []
        distances, indices = self.index.search(query_embedding, top_n)
        return [(d, self.note_map[i]) for d, i in zip(distances[0], indices[0]) if 0 <= i < len(self.note_map)]

    def clear(self):
        """Reset index and note_map; remove fingerprint file."""
        self.index.reset()
        self.note_map = []
        if os.path.exists(FINGERPRINT_FILE):
            os.remove(FINGERPRINT_FILE)
        logger.info("FAISS cache cleared")

    def _load_fingerprint(self):
        if not os.path.exists(FINGERPRINT_FILE):
            return None
        with open(FINGERPRINT_FILE) as f:
            return f.read().strip()

    def _save_fingerprint(self, fp: str):
        with open(FINGERPRINT_FILE, "w") as f:
            f.write(fp)

vector_cache = VectorCache()
