# IA/backend/app/settings/manager.py
# Per-user settings: load/save to data/settings_{user_id}.json (Phase 8).

import json
import os

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BACKEND_DIR, "data")

def _settings_path(user_id: str):
    return os.path.join(DATA_DIR, f"settings_{user_id}.json")

def get_settings(user_id: str) -> dict:
    """Return user settings dict; {} if file missing."""
    path = _settings_path(user_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(user_id: str, data: dict) -> dict:
    """Merge data into user settings, save, return full settings."""
    current = get_settings(user_id)
    current.update(data)
    path = _settings_path(user_id)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return current
