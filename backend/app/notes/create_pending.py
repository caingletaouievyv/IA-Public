# IA/backend/app/notes/create_pending.py
# Per-user pending note creation (follow-up after Ask clarification).

import hashlib
import json
import os
import threading
import time

from app.notes import manager as notes_manager

_STORE_LOCK = threading.RLock()
TTL_SECONDS = 900


def _pending_path(user_id: str) -> str:
    user_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return os.path.join(notes_manager.DATA_DIR, f"notes_create_pending_{user_key}.json")


def set_pending_create(
    user_id: str,
    *,
    need_title: bool,
    need_content: bool,
    title: str | None = None,
    category: str | None = None,
) -> dict:
    if not user_id:
        raise ValueError("Pending create requires user_id")
    payload = {
        "need_title": bool(need_title),
        "need_content": bool(need_content),
        "title": (title or "").strip() or None,
        "category": (category or "").strip() or "general",
        "created_at": time.time(),
        "expires_at": time.time() + TTL_SECONDS,
    }
    with _STORE_LOCK:
        os.makedirs(notes_manager.DATA_DIR, exist_ok=True)
        with open(_pending_path(user_id), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    return payload


def get_pending_create(user_id: str) -> dict | None:
    if not user_id:
        return None
    with _STORE_LOCK:
        path = _pending_path(user_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if time.time() > float(payload.get("expires_at") or 0):
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        return payload


def clear_pending_create(user_id: str) -> None:
    if not user_id:
        return
    with _STORE_LOCK:
        path = _pending_path(user_id)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
