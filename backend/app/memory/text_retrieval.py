"""Deterministic lexical note retrieval for the default memory path."""

import re

from app.memory.chunker import chunk_text

STOPWORDS = {"the", "a", "an", "of", "to", "is", "about", "me", "tell", "find", "show", "number"}
_TITLE_WEIGHT = 4
_METADATA_WEIGHT = 3
_BODY_WEIGHT = 1
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")


def normalize_query(text: str, preserve_numbers: bool = False) -> str:
    """Match the existing query normalization used by semantic retrieval."""
    text = text.casefold()
    if not preserve_numbers:
        text = re.sub(r"\d+", "", text)
    return " ".join(token for token in _TOKEN_RE.findall(text) if token not in STOPWORDS)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.casefold()))


def _chunk_score(query_tokens: set[str], note: dict, content_chunk: str) -> float:
    title_tokens = _tokens(str(note.get("title") or ""))
    category_tokens = _tokens(str(note.get("category") or ""))
    tag_tokens = _tokens(" ".join(str(tag) for tag in note.get("tags") or []))
    body_tokens = _tokens(content_chunk)

    score = 0
    for token in query_tokens:
        if token in title_tokens:
            score += _TITLE_WEIGHT
        elif token in category_tokens or token in tag_tokens:
            score += _METADATA_WEIGHT
        elif token in body_tokens:
            score += _BODY_WEIGHT
    return score / (len(query_tokens) * _TITLE_WEIGHT)


def get_relevant_notes_subset(
    query: str,
    notes: list,
    top_n: int = 5,
    preserve_numbers: bool = False,
):
    """Return deterministic ``(0..1 score, note)`` matches using chunk-level lexical overlap.

    Each note is represented by its title, category, tags, and each 120-word content
    chunk with the existing 30-word overlap. Metadata matches outweigh body matches.
    Candidate chunks are limited to ``top_n * 3`` before selecting the best chunk per
    note, matching the current retrieval contract.
    """
    normalized_query = normalize_query(query, preserve_numbers=preserve_numbers)
    query_tokens = set(normalized_query.split())
    if not query_tokens or not notes or top_n <= 0:
        return []

    scored_chunks = []
    for note_index, note in enumerate(notes):
        for chunk_index, content_chunk in enumerate(chunk_text(str(note.get("content") or ""))):
            score = _chunk_score(query_tokens, note, content_chunk)
            scored_chunks.append((-score, note_index, chunk_index, score, note))

    if not scored_chunks:
        return []

    scored_chunks.sort(key=lambda item: item[:3])
    candidates = scored_chunks[: top_n * 3]
    best_per_note = {}
    for _, note_index, chunk_index, score, note in candidates:
        current = best_per_note.get(note_index)
        if current is None or (-score, chunk_index) < (-current[0], current[1]):
            best_per_note[note_index] = (score, chunk_index, note)

    ranked = sorted(
        ((score, note_index, chunk_index, note) for note_index, (score, chunk_index, note) in best_per_note.items()),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    return [(score, note) for score, _, _, note in ranked[:top_n]]
