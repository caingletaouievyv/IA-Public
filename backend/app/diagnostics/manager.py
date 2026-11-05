# IA/backend/app/diagnostics/manager.py
# Diagnostic events live in PostgreSQL. Diagnostics JSON files are not read or written.
# Each insert commits on its own. Duplicate feedback and retention share that transaction.

import datetime
import hashlib
import os
import uuid

from app.config import (
    DIAGNOSTICS_ENABLED,
    DIAGNOSTICS_MAX_EVENTS_PER_USER,
    DIAGNOSTICS_RETENTION_DAYS,
)
from app.diagnostics import repository

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Kept so existing patches still bind. Diagnostic rows do not use this directory.
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
DEFAULT_ADMIN_LIMIT = 50
MAX_ADMIN_LIMIT = 200
_AUTOMATIC_FIELDS = {
    "event_id",
    "timestamp",
    "kind",
    "feature",
    "code",
    "category",
    "fallback",
    "error_type",
    "provider",
    "model",
    "ai_mode",
    "operation_id",
    "memory_status",
    "note_context_mode",
    "memory_enabled",
    "user_key_prefix",
}
_USER_REPORT_FIELDS = _AUTOMATIC_FIELDS | {"feedback_reason"}
_KINDS = {"automatic", "user_report"}


def user_key_prefix(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:8]


def _require_user(user_id: str) -> None:
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("user_id required for diagnostics storage")


def _validate_event(event: dict, kind: str) -> None:
    allowed = _USER_REPORT_FIELDS if kind == "user_report" else _AUTOMATIC_FIELDS
    if set(event) - allowed:
        raise ValueError("Diagnostic event contains unsupported fields")
    required = {"event_id", "timestamp", "kind", "feature", "code", "category", "fallback", "error_type", "user_key_prefix"}
    if kind == "user_report":
        required.add("feedback_reason")
    if not required.issubset(event):
        raise ValueError("Diagnostic event is missing required fields")
    if kind not in _KINDS:
        raise ValueError("Stored diagnostics data is invalid")


def _bounded_limit(limit: int) -> int:
    return max(1, min(limit, MAX_ADMIN_LIMIT))


def record_event(user_id: str, event: dict) -> dict | None:
    """Append one validated diagnostic event for the authenticated user."""
    if not DIAGNOSTICS_ENABLED:
        return None
    _require_user(user_id)
    kind = event.get("kind")
    _validate_event(event, kind)
    with repository.diagnostics_session() as session:
        return repository.insert_event(
            session,
            user_id,
            event,
            DIAGNOSTICS_MAX_EVENTS_PER_USER,
            DIAGNOSTICS_RETENTION_DAYS,
        )


def build_automatic_event(
    user_id: str,
    *,
    code: str,
    feature: str,
    category: str,
    fallback: str,
    error_type: str,
    metadata: dict | None = None,
) -> dict:
    event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "kind": "automatic",
        "feature": feature,
        "code": code,
        "category": category,
        "fallback": fallback,
        "error_type": error_type,
        "user_key_prefix": user_key_prefix(user_id),
    }
    for key, value in (metadata or {}).items():
        if key in _AUTOMATIC_FIELDS and key not in event and value is not None:
            event[key] = value
    _validate_event(event, "automatic")
    return event


def build_user_report_event(
    user_id: str,
    *,
    code: str,
    feature: str,
    category: str,
    fallback: str,
    feedback_reason: str,
    operation_id: str,
    metadata: dict | None = None,
) -> dict:
    event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "kind": "user_report",
        "feature": feature,
        "code": code,
        "category": category,
        "fallback": fallback,
        "error_type": "none",
        "feedback_reason": feedback_reason,
        "operation_id": operation_id,
        "user_key_prefix": user_key_prefix(user_id),
    }
    for key, value in (metadata or {}).items():
        if key in _USER_REPORT_FIELDS and key not in event and value is not None:
            event[key] = value
    _validate_event(event, "user_report")
    return event


def list_events_for_user(user_id: str, limit: int = DEFAULT_ADMIN_LIMIT) -> list[dict]:
    _require_user(user_id)
    with repository.diagnostics_session() as session:
        return repository.list_user_events(
            session,
            user_id,
            _bounded_limit(limit),
            DIAGNOSTICS_RETENTION_DAYS,
        )


def list_events_admin(limit: int = DEFAULT_ADMIN_LIMIT) -> list[dict]:
    with repository.diagnostics_session() as session:
        return repository.list_admin_events(
            session,
            _bounded_limit(limit),
            DIAGNOSTICS_RETENTION_DAYS,
        )
