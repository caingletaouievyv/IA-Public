"""Bounded, per-user suggestion event context stored in local JSON files."""

import datetime
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
DEFAULT_ACTIVITY_LIMIT = 50
MAX_ACTIVITY_LIMIT = 100
MAX_STORED_EVENTS = 500
_REPLACE_MAX_ATTEMPTS = 5
_REPLACE_RETRY_DELAY_SECONDS = 0.01

_STORE_LOCK = threading.RLock()
_EVENT_DESCRIPTIONS = {
    "note.created": "Note created",
    "note.updated": "Note updated",
    "note.deleted": "Note deleted",
    "flashcard_deck.created": "Flashcard deck created",
    "flashcard_deck.updated": "Flashcard deck updated",
    "flashcard_deck.deleted": "Flashcard deck deleted",
}


def _activity_path(user_id: str) -> str:
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("user_id required for activity storage")
    user_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return os.path.join(DATA_DIR, f"activity_{user_key}.json")


def _load_activity(user_id: str) -> list[dict]:
    path = _activity_path(user_id)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        events = json.load(handle)
    expected_fields = {"event_id", "event_type", "description", "timestamp"}
    if (
        not isinstance(events, list)
        or any(
            not isinstance(event, dict)
            or set(event) != expected_fields
            or any(not isinstance(event.get(field), str) or not event[field] for field in expected_fields)
            for event in events
        )
    ):
        raise ValueError("Stored activity data is invalid")
    if any(
        event["event_type"] not in _EVENT_DESCRIPTIONS
        or event["description"] != _EVENT_DESCRIPTIONS[event["event_type"]]
        for event in events
    ):
        raise ValueError("Stored activity data is invalid")
    return events


def _save_activity(user_id: str, events: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = _activity_path(user_id)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DATA_DIR,
            prefix=".activity-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            json.dump(events, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(_REPLACE_MAX_ATTEMPTS):
            try:
                os.replace(temp_path, path)
                break
            except PermissionError:
                if attempt + 1 == _REPLACE_MAX_ATTEMPTS:
                    raise
                time.sleep(_REPLACE_RETRY_DELAY_SECONDS * (2**attempt))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def record_activity(user_id: str, event_type: str) -> dict:
    """Persist a fixed, non-sensitive event for the authenticated user's action."""
    description = _EVENT_DESCRIPTIONS.get(event_type)
    if description is None:
        raise ValueError("Unsupported activity event type")

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "description": description,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with _STORE_LOCK:
        events = _load_activity(user_id)
        events.insert(0, event)
        events.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        _save_activity(user_id, events[:MAX_STORED_EVENTS])
    return event


def list_activity(user_id: str, limit: int = DEFAULT_ACTIVITY_LIMIT) -> list[dict]:
    """Return the newest activity events for one user, up to the API maximum."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    bounded_limit = min(limit, MAX_ACTIVITY_LIMIT)
    with _STORE_LOCK:
        events = _load_activity(user_id)
    return sorted(events, key=lambda item: item.get("timestamp", ""), reverse=True)[:bounded_limit]
