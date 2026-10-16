"""Per-user persistent memory records and relevance retrieval."""

import datetime
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid

from app.memory.text_retrieval import normalize_query
from app.memory.utils import estimate_tokens

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
MAX_MEMORY_LENGTH = 500
MAX_MEMORIES = 100
MAX_RETRIEVED_MEMORIES = 8
MEMORY_TOKEN_BUDGET = 180

_STORE_LOCK = threading.RLock()
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}", re.IGNORECASE),
    re.compile(r"\b(?:password|passwd|passcode|api[_ -]?key|access[_ -]?token|secret)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)
_SENSITIVE_TERMS = re.compile(
    r"\b(?:diagnos(?:is|ed)|medical condition|prescription|mental health|"
    r"political affiliation|religion|sexual orientation|bank account|credit card|"
    r"social security number|ssn)\b",
    re.IGNORECASE,
)
def _memory_path(user_id: str) -> str:
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("user_id required for memory storage")
    user_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return os.path.join(DATA_DIR, f"memories_{user_key}.json")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split()).strip(" .,!?:;")


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def sensitive_personal_terms(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _SENSITIVE_TERMS.finditer(text)}


def validate_memory_text(value: object, *, explicit_remember: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("Memory text must be a string")
    text = value.strip()
    if not text or len(text) > MAX_MEMORY_LENGTH:
        raise ValueError(f"Memory text must be between 1 and {MAX_MEMORY_LENGTH} characters")
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise ValueError("Memory text contains unsupported control characters")
    if contains_secret(text):
        raise ValueError("Memory cannot contain passwords, credentials, tokens, or private keys")
    if sensitive_personal_terms(text) and not explicit_remember:
        raise ValueError("Sensitive personal information requires an explicit remember request")
    return text


def load_memories(user_id: str) -> list[dict]:
    path = _memory_path(user_id)
    with _STORE_LOCK:
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as handle:
            memories = json.load(handle)
    if not isinstance(memories, list):
        raise ValueError("Stored memory data is invalid")
    return [item for item in memories if isinstance(item, dict)]


def _save_memories(user_id: str, memories: list[dict]) -> None:
    path = _memory_path(user_id)
    os.makedirs(DATA_DIR, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DATA_DIR,
            prefix=".memories-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            json.dump(memories, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def list_memories(user_id: str) -> list[dict]:
    return sorted(load_memories(user_id), key=lambda item: item.get("created_at", ""))


def add_or_update_memories(
    user_id: str,
    candidates: list[dict],
    delete_ids: list[str] | None = None,
) -> dict[str, int]:
    with _STORE_LOCK:
        memories = load_memories(user_id)
        existing_by_id = {item.get("id"): item for item in memories if item.get("id")}
        deleted = set(delete_ids or ())
        kept = []
        by_normalized = {}
        for item in memories:
            if item.get("id") in deleted:
                continue
            normalized = _normalize(item.get("text", ""))
            if not normalized or normalized in by_normalized:
                continue
            kept.append(item)
            by_normalized[normalized] = item
        added_count = 0
        updated_count = 0
        now = _now()

        for candidate in candidates[:10]:
            text = candidate.get("text")
            try:
                text = validate_memory_text(
                    text,
                    explicit_remember=bool(candidate.get("explicit_remember")),
                )
            except ValueError:
                continue
            normalized = _normalize(text)
            if not normalized:
                continue

            requested_id = candidate.get("id")
            existing = existing_by_id.get(requested_id) if requested_id else None
            if existing and existing not in kept:
                existing = None
            if requested_id and existing is None:
                continue
            existing = existing or by_normalized.get(normalized)
            if existing:
                if existing.get("text") != text:
                    duplicate = by_normalized.get(normalized)
                    if duplicate is not None and duplicate is not existing:
                        kept.remove(duplicate)
                        by_normalized.pop(normalized, None)
                    previous_key = _normalize(existing.get("text", ""))
                    by_normalized.pop(previous_key, None)
                    existing["text"] = text
                    existing["updated_at"] = now
                    by_normalized[normalized] = existing
                    updated_count += 1
                continue
            if len(kept) >= MAX_MEMORIES:
                continue
            record = {
                "id": str(uuid.uuid4()),
                "text": text,
                "created_at": now,
                "updated_at": now,
            }
            kept.append(record)
            existing_by_id[record["id"]] = record
            by_normalized[normalized] = record
            added_count += 1

        removed_count = len(memories) - len(kept)
        if added_count or updated_count or removed_count:
            _save_memories(user_id, kept)
        return {"added": added_count, "updated": updated_count, "removed": removed_count}


def update_memory(user_id: str, memory_id: str, value: object) -> dict | None:
    text = validate_memory_text(value, explicit_remember=True)
    normalized = _normalize(text)
    with _STORE_LOCK:
        memories = load_memories(user_id)
        target = next((item for item in memories if item.get("id") == memory_id), None)
        if target is None:
            return None
        duplicate = next(
            (
                item for item in memories
                if item is not target and _normalize(item.get("text", "")) == normalized
            ),
            None,
        )
        if duplicate:
            raise ValueError("Memory duplicates another existing record")
        target["text"] = text
        target["updated_at"] = _now()
        _save_memories(user_id, memories)
        return target


def delete_memory(user_id: str, memory_id: str) -> bool:
    with _STORE_LOCK:
        memories = load_memories(user_id)
        kept = [item for item in memories if item.get("id") != memory_id]
        if len(kept) == len(memories):
            return False
        _save_memories(user_id, kept)
        return True


def clear_memories(user_id: str) -> int:
    with _STORE_LOCK:
        memories = load_memories(user_id)
        if memories:
            _save_memories(user_id, [])
        return len(memories)


def retrieve_memories(user_id: str, query: str) -> list[dict]:
    query_tokens = set(normalize_query(query).split())
    if not query_tokens:
        return []

    ranked = []
    seen = set()
    for memory in load_memories(user_id):
        text = memory.get("text", "")
        normalized = _normalize(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        content_tokens = set(normalize_query(text).split())
        overlap = len(query_tokens & content_tokens)
        if not overlap:
            continue
        score = overlap / len(query_tokens)
        ranked.append((score, memory))

    ranked.sort(key=lambda item: (-item[0], item[1].get("created_at", "")))
    selected = []
    used_tokens = 0
    for _, memory in ranked[:MAX_RETRIEVED_MEMORIES]:
        tokens = estimate_tokens(memory.get("text", ""))
        if used_tokens + tokens > MEMORY_TOKEN_BUDGET:
            continue
        selected.append(memory)
        used_tokens += tokens
    return selected
