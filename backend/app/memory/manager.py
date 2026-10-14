# IA/backend/app/memory/manager.py
"""Build AI context: retrieval filter (top-k), summarization, and token cap."""

from app.notes.manager import HISTORY_CATEGORY, load_notes
from app.memory.text_retrieval import get_relevant_notes_subset, normalize_query
from app.memory.summarizer import summarize_text
from app.memory.utils import estimate_tokens
from app.memory.intent_cache import IntentLRUCache
from app.config import (
    MAX_CONTEXT_TOKENS,
    INTENT_CACHE_MAX_SIZE,
    INTENT_CACHE_TTL,
    FAISS_THRESHOLD_LOOKUP,
    FAISS_THRESHOLD_EXPLORATORY,
    MEMORY_RETRIEVAL,
    TEXT_RETRIEVAL_THRESHOLD_LOOKUP,
    TEXT_RETRIEVAL_THRESHOLD_EXPLORATORY,
    MAX_FAISS_RESULTS,
    LOG_DROPPED_NOTES,
)
from app.memory.analytics import log_memory_event
import logging

logger = logging.getLogger(__name__)
SUMMARY_WORD_LIMIT = 150
intent_cache = IntentLRUCache(max_size=INTENT_CACHE_MAX_SIZE, ttl=INTENT_CACHE_TTL)


def _get_relevant_notes_subset(query: str, notes: list, top_n: int, preserve_numbers: bool):
    """Use lightweight retrieval by default; load semantic retrieval only when selected."""
    if MEMORY_RETRIEVAL == "semantic":
        from app.memory.embeddings import get_relevant_notes_subset as semantic_retrieval
        return semantic_retrieval(query, notes, top_n=top_n, preserve_numbers=preserve_numbers)
    return get_relevant_notes_subset(query, notes, top_n=top_n, preserve_numbers=preserve_numbers)

def _empty_context():
    return {"context": "", "tokens": 0, "best_score": None, "dropped_notes": [], "note_titles": []}


def _retrieval_threshold(intent: str) -> float:
    if MEMORY_RETRIEVAL == "semantic":
        return FAISS_THRESHOLD_LOOKUP if intent == "lookup" else FAISS_THRESHOLD_EXPLORATORY
    return TEXT_RETRIEVAL_THRESHOLD_LOOKUP if intent == "lookup" else TEXT_RETRIEVAL_THRESHOLD_EXPLORATORY


def build_context(
    query: str,
    max_tokens: int = 2000,
    note_ids: list | None = None,
    user_id: str = None,
    note_context_mode: str = "automatic",
    memory_context_mode: str = "off",
):
    """Build deduplicated context from a user's notes (user_id required)."""
    if not user_id:
        raise ValueError("user_id required for build_context (Phase 8)")
    if note_context_mode not in ("off", "automatic", "focused"):
        raise ValueError("note_context_mode must be 'off', 'automatic', or 'focused'")
    if memory_context_mode not in ("off", "automatic", "focused"):
        raise ValueError("memory_context_mode must be 'off', 'automatic', or 'focused'")
    note_ids_set = set(note_ids or [])
    notes_enabled = note_context_mode != "off"
    memory_enabled = memory_context_mode != "off"
    if not notes_enabled and not memory_enabled:
        return _empty_context()
    selected_enabled = note_context_mode == "focused" or memory_context_mode == "focused"
    automatic_enabled = note_context_mode == "automatic" or memory_context_mode == "automatic"
    if not automatic_enabled and selected_enabled and not note_ids_set:
        return _empty_context()

    notes = [
        note for note in load_notes(user_id)
        if note.get("category") != HISTORY_CATEGORY
    ]
    selected_notes = [
        note for note in notes
        if selected_enabled and note.get("id") in note_ids_set
    ]
    matches_by_id = {note["id"]: (1.0, note) for note in selected_notes}
    best_retrieval_score = None
    cache_key = None

    if automatic_enabled:
        preserve_numbers = any(k in query.lower() for k in ["stress", "find"])
        automatic_searches = []
        if memory_context_mode == "automatic":
            automatic_searches.append((notes, classify_intent(query), False))
        if note_context_mode == "automatic":
            note_candidates = [note for note in notes if note.get("id") in note_ids_set] if note_ids_set else notes
            note_intent = "lookup" if note_ids_set else classify_intent(query)
            if not any(candidates is note_candidates and intent == note_intent for candidates, intent, _ in automatic_searches):
                automatic_searches.append((note_candidates, note_intent, bool(note_ids_set)))

        if (
            len(automatic_searches) == 1
            and automatic_searches[0][0] is notes
            and not note_ids_set
            and not selected_enabled
        ):
            cache_key = (
                f"{user_id}:{automatic_searches[0][1]}:"
                f"{normalize_query(query, preserve_numbers=preserve_numbers)}"
            )
            cached = intent_cache.get(cache_key)
            if cached:
                return cached

        for candidates, intent, include_selected_on_no_match in automatic_searches:
            matches = _get_relevant_notes_subset(
                query,
                candidates,
                top_n=MAX_FAISS_RESULTS,
                preserve_numbers=preserve_numbers,
            )
            if matches:
                search_best_score = float(matches[0][0])
                if best_retrieval_score is None or search_best_score > best_retrieval_score:
                    best_retrieval_score = search_best_score
            if include_selected_on_no_match and (not matches or matches[0][0] <= 0):
                matches = [(1.0, note) for note in candidates]
            threshold = _retrieval_threshold(intent)
            for score, note in matches:
                if score >= threshold:
                    current = matches_by_id.get(note["id"])
                    if current is None or score > current[0]:
                        matches_by_id[note["id"]] = (score, note)

    if not matches_by_id:
        result = _empty_context()
        result["best_score"] = best_retrieval_score
        if cache_key is not None:
            intent_cache.set(cache_key, result)
        return result

    matches = sorted(matches_by_id.values(), key=lambda match: match[0], reverse=True)
    best_score = float(matches[0][0])
    processed = []
    token_est = 0
    dropped = []
    for score, note in matches:
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
    log_memory_event(
        query=query,
        intent=classify_intent(query),
        best_score=float(best_score),
        context_tokens=int(token_est),
        included_notes=[b.split(":")[0] for b in processed],
        dropped_notes=dropped,
    )
    if cache_key is not None:
        intent_cache.set(cache_key, result)
    return result

def classify_intent(query: str) -> str:
    """lookup if find/lookup/note/stress in query; else exploratory."""
    if any(k in query.lower() for k in ["find", "lookup", "note", "stress"]):
        return "lookup"
    return "exploratory"
