# IA/backend/app/activity/manager.py
# Activity events live in PostgreSQL. Activity JSON files are not read or written.
# Each insert commits on its own. A note save does not share that transaction.

import datetime
import os
import uuid

from app.activity import repository

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Kept so existing patches still bind. Activity rows do not use this directory.
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
DEFAULT_ACTIVITY_LIMIT = 50
MAX_ACTIVITY_LIMIT = 100
MAX_STORED_EVENTS = 500
_EVENT_DESCRIPTIONS = {
    "note.created": "Note created",
    "note.updated": "Note updated",
    "note.deleted": "Note deleted",
    "flashcard_deck.created": "Flashcard deck created",
    "flashcard_deck.updated": "Flashcard deck updated",
    "flashcard_deck.deleted": "Flashcard deck deleted",
}


def _require_user(user_id: str) -> None:
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("user_id required for activity storage")


def record_activity(user_id: str, event_type: str) -> dict:
    """Persist a fixed, non-sensitive event for the authenticated user's action."""
    _require_user(user_id)
    description = _EVENT_DESCRIPTIONS.get(event_type)
    if description is None:
        raise ValueError("Unsupported activity event type")
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "description": description,
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
    }
    with repository.activity_session() as session:
        return repository.insert_event(session, user_id, event, MAX_STORED_EVENTS)


def list_activity(user_id: str, limit: int = DEFAULT_ACTIVITY_LIMIT) -> list[dict]:
    """Return the newest activity events for one user, up to the API maximum."""
    _require_user(user_id)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    bounded_limit = min(limit, MAX_ACTIVITY_LIMIT)
    with repository.activity_session() as session:
        return repository.list_events(session, user_id, bounded_limit)
