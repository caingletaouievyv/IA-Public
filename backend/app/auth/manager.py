# IA/backend/app/auth/manager.py
# User store: data/users.json. Password hashing via werkzeug (Flask dep). No API secret.

import json
import os
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")


def _load_users():
    """Return list of user dicts; [] if file missing."""
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_users(users: list):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def find_user_by_username(username: str) -> dict | None:
    """First user with matching username (case-sensitive), or None."""
    users = _load_users()
    u = (username or "").strip()
    for user in users:
        if (user.get("username") or "").strip() == u:
            return user
    return None


def find_user_by_id(user_id: str) -> dict | None:
    """First user with matching user_id, or None."""
    for user in _load_users():
        if user.get("user_id") == user_id:
            return user
    return None


def get_user_role(user_id: str) -> str:
    """Return the persisted role; users without one remain normal users."""
    user = find_user_by_id(user_id)
    return (user.get("role") or "user") if user else "user"


def verify_password(user: dict, password: str) -> bool:
    """True if password matches user's stored hash."""
    return bool(user and check_password_hash(user.get("password_hash") or "", password or ""))


def create_user(username: str, password: str) -> dict | None:
    """Register user if username not taken. Return user dict or None."""
    username = (username or "").strip()
    password = password or ""
    if not username or len(password) < 1:
        return None
    if find_user_by_username(username):
        return None
    user_id = str(uuid.uuid4())
    user = {
        "user_id": user_id,
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": "user",
    }
    users = _load_users()
    users.append(user)
    _save_users(users)
    return {"user_id": user_id, "username": user["username"]}
