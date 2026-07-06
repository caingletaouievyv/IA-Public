# IA/backend/app/memory/manager.py
"""Build optimized AI context: semantic filter (top-k), summarization, token cap."""

from app.notes.manager import load_notes
from app.memory.embeddings import get_relevant_notes_subset, normalize_query
from app.memory.summarizer import summarize_text
from app.memory.utils import estimate_tokens
from app.memory.intent_cache import IntentLRUCache
from app.config import (
    MAX_CONTEXT_TOKENS,
    INTENT_CACHE_MAX_SIZE,
    INTENT_CACHE_TTL,
    FAISS_THRESHOLD_LOOKUP,
    FAISS_THRESHOLD_EXPLORATORY,
    MAX_FAISS_RESULTS,
    LOG_DROPPED_NOTES,
)
from app.memory.analytics import log_memory_event
import logging

logger = logging.getLogger(__name__)
SUMMARY_WORD_LIMIT = 150
intent_cache = IntentLRUCache(max_size=INTENT_CACHE_MAX_SIZE, ttl=INTENT_CACHE_TTL)

def build_context(query: str, max_tokens: int = 2000, note_ids: list | None = None, user_id: str = None):
    """Build AI context from user's notes (user_id required). Semantic search via temp FAISS subset (no global cache per user)."""
    if not user_id:
        raise ValueError("user_id required for build_context (Phase 8)")
    notes = load_notes(user_id)
    if note_ids:
        note_ids_set = set(note_ids)
        notes = [n for n in notes if n.get("id") in note_ids_set]
        if not notes:
            return {"context": "", "tokens": 0, "best_score": None, "dropped_notes": [], "note_titles": []}
        preserve_numbers = any(k in query.lower() for k in ["stress", "find"])
        matches = get_relevant_notes_subset(query, notes, top_n=MAX_FAISS_RESULTS, preserve_numbers=preserve_numbers)
        cache_key = None
    else:
        preserve_numbers = any(k in query.lower() for k in ["stress", "find"])
        intent = classify_intent(query)
        cache_key = f"{user_id}:{intent}:{normalize_query(query, preserve_numbers=preserve_numbers)}"
        cached = intent_cache.get(cache_key)
        if cached:
            return cached
        matches = get_relevant_notes_subset(query, notes, top_n=MAX_FAISS_RESULTS, preserve_numbers=preserve_numbers)
    if not matches:
        result = {"context": "", "tokens": 0, "best_score": None, "dropped_notes": [], "note_titles": []}
        if cache_key is not None:
            intent_cache.set(cache_key, result)
        return result
    intent = classify_intent(query) if not note_ids else "lookup"
    threshold = FAISS_THRESHOLD_LOOKUP if intent == "lookup" else FAISS_THRESHOLD_EXPLORATORY
    best_score = float(matches[0][0])
    if best_score < threshold:
        result = {"context": "", "tokens": 0, "best_score": best_score, "dropped_notes": [], "note_titles": []}
        if cache_key is not None:
            intent_cache.set(cache_key, result)
        return result
    # 3.3 Score-weighted packing: process in score desc so token cap fills with best matches first.
    matches = sorted(matches, key=lambda x: x[0], reverse=True)
    seen = set()
    processed = []
    token_est = 0
    dropped = []
    for score, note in matches:
        if score < threshold:
            break
        note_id = note["id"]
        if note_id in seen:
            continue
        seen.add(note_id)
        content = note["content"]
        if len(content.split()) > SUMMARY_WORD_LIMIT:
            content = summarize_text(content)
        block = f"{note['title']}: {content}"
        block_tokens = estimate_tokens(block)
        if token_est + block_tokens > MAX_CONTEXT_TOKENS:
            dropped.append(note["title"])
            continue
        processed.append(block)
        token_est += block_tokens
    context = "\n".join(processed)
    if dropped and LOG_DROPPED_NOTES:
        logger.debug(f"Dropped notes due to token cap: {dropped}")
    note_titles = [b.split(":", 1)[0].strip() for b in processed]
    result = {"context": context, "tokens": int(token_est), "best_score": float(best_score), "dropped_notes": dropped, "note_titles": note_titles}
    log_memory_event(query=query, intent=intent, best_score=float(best_score), context_tokens=int(token_est), included_notes=[b.split(":")[0] for b in processed], dropped_notes=dropped)
    if cache_key is not None:
        intent_cache.set(cache_key, result)
    return result

def classify_intent(query: str) -> str:
    """lookup if find/lookup/note/stress in query; else exploratory."""
    if any(k in query.lower() for k in ["find", "lookup", "note", "stress"]):
        return "lookup"
    return "exploratory"
