# IA/backend/app/auth/manager.py
# User store: data/users.json. Password hashing via werkzeug (Flask dep). No API secret.

import json
import os
import threading
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

from app.auth.roles import KNOWN_ROLES, ROLE_ADMIN, ROLE_MAIN_ADMIN, ROLE_USER, normalize_role

_USERS_LOCK = threading.RLock()

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
    if not user:
        return ROLE_USER
    return normalize_role(user.get("role"))


def set_user_role(user_id: str, role: str) -> None:
    """Persist a known role for one account. Used by operator bootstrap tooling."""
    normalized = normalize_role(role)
    if normalized not in KNOWN_ROLES:
        raise ValueError("Unsupported role")
    with _USERS_LOCK:
        users = _load_users()
        for user in users:
            if user.get("user_id") == user_id:
                user["role"] = normalized
                _save_users(users)
                return
    raise ValueError("User not found")


def list_user_summaries() -> list[dict]:
    """Return public account metadata for Main Admin user management."""
    with _USERS_LOCK:
        users = _load_users()
        return [
            {
                "user_id": user.get("user_id"),
                "username": user.get("username"),
                "role": normalize_role(user.get("role")),
            }
            for user in users
            if user.get("user_id")
        ]


def promote_user_to_admin(target_user_id: str) -> dict:
    """Promote a normal user to admin. Main Admin ownership cannot change here."""
    if not target_user_id:
        raise ValueError("user_id required")
    with _USERS_LOCK:
        users = _load_users()
        target = next((user for user in users if user.get("user_id") == target_user_id), None)
        if not target:
            raise LookupError("User not found")
        current_role = normalize_role(target.get("role"))
        if current_role == ROLE_MAIN_ADMIN:
            raise ValueError("Main Admin ownership cannot be changed through promotion")
        if current_role != ROLE_USER:
            raise ValueError("Only user accounts can be promoted to admin")
        target["role"] = ROLE_ADMIN
        _save_users(users)
        return {
            "user_id": target_user_id,
            "username": target.get("username"),
            "role": ROLE_ADMIN,
        }


def verify_password(user: dict, password: str) -> bool:
    """True if password matches user's stored hash."""
    return bool(user and check_password_hash(user.get("password_hash") or "", password or ""))


def create_initial_main_admin(username: str, password: str) -> dict:
    """Create the first account as Main Admin when the user store is empty."""
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        raise ValueError("username and password required")
    with _USERS_LOCK:
        users = _load_users()
        if users:
            raise ValueError("User store is not empty")
        user_id = str(uuid.uuid4())
        user = {
            "user_id": user_id,
            "username": username,
            "password_hash": generate_password_hash(password),
            "role": ROLE_MAIN_ADMIN,
        }
        users.append(user)
        _save_users(users)
        return {"user_id": user_id, "username": username}


def create_user(username: str, password: str) -> dict | None:
    """Register user if username not taken. Return user dict or None."""
    username = (username or "").strip()
    password = password or ""
    if not username or len(password) < 1:
        return None
    with _USERS_LOCK:
        users = _load_users()
        for existing in users:
            if (existing.get("username") or "").strip() == username:
                return None
        user_id = str(uuid.uuid4())
        user = {
            "user_id": user_id,
            "username": username,
            "password_hash": generate_password_hash(password),
            "role": ROLE_USER,
        }
        users.append(user)
        _save_users(users)
        return {"user_id": user_id, "username": user["username"]}
