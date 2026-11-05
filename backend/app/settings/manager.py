# IA/backend/app/settings/manager.py
# Per-user settings in PostgreSQL. Settings JSON files are not read or written.

import os

from app.settings.repository import locked_settings, merge_settings, read_settings, settings_session

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Kept so existing patches still bind. Settings rows do not use this directory.
DATA_DIR = os.path.join(_BACKEND_DIR, "data")


def _require_user(user_id: str) -> None:
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("user_id required for settings storage")


def get_settings(user_id: str) -> dict:
    """Return this user's stored settings. A user with no row gets an empty document."""
    _require_user(user_id)
    with settings_session() as session:
        return read_settings(session, user_id)


def save_settings(user_id: str, data: dict) -> dict:
    """Merge data into this user's settings and return the full stored document."""
    _require_user(user_id)
    with locked_settings(user_id) as session:
        return merge_settings(session, user_id, data)
