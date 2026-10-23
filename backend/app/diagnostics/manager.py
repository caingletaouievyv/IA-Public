# IA/backend/app/diagnostics/manager.py
"""Bounded, per-user AI diagnostic events stored in local JSON files."""

import datetime
import glob
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid

from app.config import (
    DIAGNOSTICS_ENABLED,
    DIAGNOSTICS_MAX_EVENTS_PER_USER,
    DIAGNOSTICS_RETENTION_DAYS,
)

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
DEFAULT_ADMIN_LIMIT = 50
MAX_ADMIN_LIMIT = 200
_REPLACE_MAX_ATTEMPTS = 5
_REPLACE_RETRY_DELAY_SECONDS = 0.01

_STORE_LOCK = threading.RLock()
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


def _diagnostics_path(user_id: str) -> str:
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("user_id required for diagnostics storage")
    user_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return os.path.join(DATA_DIR, f"diagnostics_{user_key}.json")


def user_key_prefix(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:8]


def _parse_timestamp(value: str) -> datetime.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _within_retention(event: dict) -> bool:
    if DIAGNOSTICS_RETENTION_DAYS <= 0:
        return True
    parsed = _parse_timestamp(event.get("timestamp", ""))
    if parsed is None:
        return False
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=DIAGNOSTICS_RETENTION_DAYS)
    return parsed >= cutoff


def _validate_event(event: dict, kind: str) -> None:
    allowed = _USER_REPORT_FIELDS if kind == "user_report" else _AUTOMATIC_FIELDS
    if set(event) - allowed:
        raise ValueError("Diagnostic event contains unsupported fields")
    required = {"event_id", "timestamp", "kind", "feature", "code", "category", "fallback", "error_type", "user_key_prefix"}
    if kind == "user_report":
        required.add("feedback_reason")
    if not required.issubset(event):
        raise ValueError("Diagnostic event is missing required fields")


def _load_events(user_id: str) -> list[dict]:
    path = _diagnostics_path(user_id)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        events = json.load(handle)
    if not isinstance(events, list):
        raise ValueError("Stored diagnostics data is invalid")
    validated = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Stored diagnostics data is invalid")
        kind = event.get("kind")
        if kind not in ("automatic", "user_report"):
            raise ValueError("Stored diagnostics data is invalid")
        _validate_event(event, kind)
        if _within_retention(event):
            validated.append(event)
    return validated


def _save_events(user_id: str, events: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = _diagnostics_path(user_id)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DATA_DIR,
            prefix=".diagnostics-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            json.dump(events[:DIAGNOSTICS_MAX_EVENTS_PER_USER], handle, ensure_ascii=False, indent=2)
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


def record_event(user_id: str, event: dict) -> dict | None:
    """Append one validated diagnostic event for the authenticated user."""
    if not DIAGNOSTICS_ENABLED:
        return None
    kind = event.get("kind")
    _validate_event(event, kind)
    with _STORE_LOCK:
        events = _load_events(user_id)
        if kind == "user_report":
            operation_id = event.get("operation_id")
            if operation_id:
                for item in events:
                    if item.get("kind") == "user_report" and item.get("operation_id") == operation_id:
                        return item
        events.insert(0, event)
        events.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        _save_events(user_id, events)
    return event


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
    bounded_limit = max(1, min(limit, MAX_ADMIN_LIMIT))
    with _STORE_LOCK:
        events = _load_events(user_id)
    return sorted(events, key=lambda item: item.get("timestamp", ""), reverse=True)[:bounded_limit]


def list_events_admin(limit: int = DEFAULT_ADMIN_LIMIT) -> list[dict]:
    bounded_limit = max(1, min(limit, MAX_ADMIN_LIMIT))
    combined: list[dict] = []
    pattern = os.path.join(DATA_DIR, "diagnostics_*.json")
    with _STORE_LOCK:
        for path in glob.glob(pattern):
            user_key = os.path.basename(path)[len("diagnostics_"):-len(".json")]
            try:
                with open(path, encoding="utf-8") as handle:
                    events = json.load(handle)
            except (OSError, ValueError, TypeError):
                continue
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict) or not _within_retention(event):
                    continue
                try:
                    kind = event.get("kind")
                    if kind not in ("automatic", "user_report"):
                        continue
                    _validate_event(event, kind)
                except ValueError:
                    continue
                if event.get("user_key_prefix") != user_key[:8]:
                    event = dict(event)
                    event["user_key_prefix"] = user_key[:8]
                combined.append(event)
    combined.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return combined[:bounded_limit]
