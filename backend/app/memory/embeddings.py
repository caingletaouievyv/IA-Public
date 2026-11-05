# IA/backend/app/memory/embeddings.py
"""Semantic note recall. Each search builds a temporary FAISS index and discards it."""

import faiss
import numpy as np
import re
from app.memory.chunker import chunk_text

model = None
DIM = 384
STOPWORDS = {"the", "a", "an", "of", "to", "is", "about", "me", "tell", "find", "show", "number"}


def _get_model():
    global model
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return model


def encode_texts(texts: list):
    """Encode to vectors; L2-normalize for cosine similarity."""
    emb = np.array(_get_model().encode(texts), dtype="float32")
    return emb / np.linalg.norm(emb, axis=1, keepdims=True)


def get_relevant_notes_subset(query: str, notes: list, top_n: int = 5, preserve_numbers=False):
    """Search only the given notes with a temporary index. Return the best score per note."""
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
