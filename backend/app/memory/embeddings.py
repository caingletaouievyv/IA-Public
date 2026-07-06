# IA/backend/app/memory/embeddings.py
"""Embedding-based semantic recall. All-note path uses get_relevant_notes_subset (temp index per request); get_relevant_notes + vector_cache reserved for optional single-user persistent cache."""

import faiss
import numpy as np
import hashlib
import re
import logging
from sentence_transformers import SentenceTransformer
from app.memory.cache import vector_cache
from app.config import FAISS_LOG_SCORES, FAISS_SCORE_LOG_PATH
from datetime import datetime
from app.memory.chunker import chunk_text

logger = logging.getLogger(__name__)
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
DIM = 384
STOPWORDS = {"the", "a", "an", "of", "to", "is", "about", "me", "tell", "find", "show", "number"}

def encode_texts(texts: list):
    """Encode to vectors; L2-normalize for cosine similarity."""
    emb = np.array(model.encode(texts), dtype="float32")
    return emb / np.linalg.norm(emb, axis=1, keepdims=True)

def store_note_embeddings(notes: list):
    """Chunk each note; encode; append to FAISS index + note_map."""
    if not notes:
        return
    texts = []
    meta = []
    for n in notes:
        for chunk in chunk_text(n["content"]):
            text = f"{n['title']} {n.get('category','')} {' '.join(n.get('tags', []))} {chunk}"
            texts.append(text)
            meta.append(n)
    embeddings = encode_texts(texts)
    vector_cache.add_embeddings(embeddings, meta)

def compute_notes_fingerprint(notes):
    """Stable hash from id+updated_at; change invalidates FAISS cache."""
    base = "|".join(f"{n['id']}:{n['updated_at']}" for n in notes)
    return hashlib.md5(base.encode()).hexdigest()

def get_relevant_notes(query: str, notes: list, top_n: int = 5, preserve_numbers=False):
    """Persistent FAISS cache (single fingerprint). Unused in current multi-user flow; manager uses get_relevant_notes_subset for both all-notes and subset."""
    if not notes:
        return []
    new_fp = compute_notes_fingerprint(notes)
    old_fp = vector_cache._load_fingerprint()
    if new_fp != old_fp:
        vector_cache.clear()
        store_note_embeddings(notes)
        vector_cache._save_cache(fingerprint=new_fp)
    query = normalize_query(query, preserve_numbers=preserve_numbers)
    query_emb = encode_texts([query])
    logger.debug(f"FAISS index size: {vector_cache.index.ntotal}")
    results = vector_cache.search(query_emb, top_n)
    results = sorted(results, key=lambda x: x[0], reverse=True)
    best_score = results[0][0] if results else None
    if best_score is not None:
        log_faiss_score(query, best_score, len(results))
    return results

def get_relevant_notes_subset(query: str, notes: list, top_n: int = 5, preserve_numbers=False):
    """Search only within given notes using a temporary FAISS index; do not touch global cache. Return (score, note) list, one per note (best score per note)."""
    if not notes:
        return []
    texts = []
    meta = []
    for n in notes:
        for chunk in chunk_text(n["content"]):
            text = f"{n['title']} {n.get('category','')} {' '.join(n.get('tags', []))} {chunk}"
            texts.append(text)
            meta.append(n)
    if not texts:
        return []
    embeddings = encode_texts(texts)
    index = faiss.IndexFlatIP(DIM)
    index.add(embeddings.astype("float32"))
    query_norm = normalize_query(query, preserve_numbers=preserve_numbers)
    query_emb = encode_texts([query_norm])
    k = min(top_n * 3, index.ntotal)
    distances, indices = index.search(query_emb, k)
    best_per_note = {}
    for d, i in zip(distances[0], indices[0]):
        if 0 <= i < len(meta):
            note = meta[i]
            nid = note["id"]
            if nid not in best_per_note or d > best_per_note[nid][0]:
                best_per_note[nid] = (d, note)
    results = sorted(best_per_note.values(), key=lambda x: x[0], reverse=True)[:top_n]
    return results

def normalize_query(text: str, preserve_numbers=False) -> str:
    """Lowercase; optionally strip digits; remove stopwords."""
    text = text.lower()
    if not preserve_numbers:
        text = re.sub(r"\d+", "", text)
    words = [w for w in text.split() if w not in STOPWORDS]
    return " ".join(words)

def log_faiss_score(query, best_dist, returned_count):
    """Append one line to FAISS score log if enabled."""
    if not FAISS_LOG_SCORES:
        return
    with open(FAISS_SCORE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow().isoformat()},{best_dist:.4f},{returned_count},\"{query}\"\n")

