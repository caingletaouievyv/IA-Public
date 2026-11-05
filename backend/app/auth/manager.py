# IA/backend/app/auth/manager.py
# Accounts live in PostgreSQL. Password hashing via werkzeug. Legacy users.json is not read.

import os
import uuid

from werkzeug.security import check_password_hash, generate_password_hash

from app.auth import repository
from app.auth.repository import AccountConflict, AccountStoreError
from app.auth.roles import KNOWN_ROLES, ROLE_ADMIN, ROLE_MAIN_ADMIN, ROLE_USER, normalize_role

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
# Legacy JSON path. Left in place so existing data is not deleted. Auth does not read or write it.
USERS_FILE = os.path.join(DATA_DIR, "users.json")


def _load_users() -> list[dict]:
    """Return account rows. Tests and the bootstrap CLI use this shape."""
    with repository.auth_session() as session:
        return [repository.user_record(user) for user in repository.list_users(session)]


def _save_users(users: list) -> None:
    """Replace account rows. Password hashes are stored exactly as given."""
    try:
        with repository.auth_session() as session:
            repository.replace_users(session, users)
    except AccountConflict:
        raise ValueError("Could not replace accounts.") from None
    except AccountStoreError:
        raise


def store_is_empty() -> bool:
    with repository.auth_session() as session:
        return repository.count_users(session) == 0


def find_user_by_username(username: str) -> dict | None:
    """First user with matching username (case-sensitive), or None."""
    wanted = (username or "").strip()
    if not wanted:
        return None
    with repository.auth_session() as session:
        user = repository.find_by_username(session, wanted)
        return repository.user_record(user) if user else None


def find_user_by_id(user_id: str) -> dict | None:
    """First user with matching user_id, or None."""
    if not user_id:
        return None
    with repository.auth_session() as session:
        user = repository.find_by_id(session, user_id)
        return repository.user_record(user) if user else None


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
    try:
        with repository.auth_session() as session:
            repository.set_role(session, user_id, normalized)
    except AccountConflict:
        raise ValueError("Could not update the account.") from None
    except ValueError:
        raise
    except AccountStoreError:
        raise


def list_user_summaries() -> list[dict]:
    """Return public account metadata for Main Admin user management."""
    with repository.auth_session() as session:
        return [
            {
                "user_id": user.user_id,
                "username": user.username,
                "role": normalize_role(user.role),
            }
            for user in repository.list_users(session)
            if user.user_id
        ]


def _assert_actor_may_change_target_role(actor_user_id: str, target_user_id: str) -> None:
    if actor_user_id and actor_user_id == target_user_id:
        raise ValueError("You cannot change your own role")


def promote_user_to_admin(target_user_id: str, actor_user_id: str | None = None) -> dict:
    """Promote a normal user to admin. Main Admin ownership cannot change here."""
    if not target_user_id:
        raise ValueError("user_id required")
    _assert_actor_may_change_target_role(actor_user_id or "", target_user_id)
    try:
        with repository.auth_session() as session:
            target = repository.find_by_id(session, target_user_id)
            if not target:
                raise LookupError("User not found")
            current_role = normalize_role(target.role)
            if current_role == ROLE_MAIN_ADMIN:
                raise ValueError("Main Admin ownership cannot be changed through promotion")
            if current_role != ROLE_USER:
                raise ValueError("Only user accounts can be promoted to admin")
            repository.set_role(session, target_user_id, ROLE_ADMIN)
            return {
                "user_id": target_user_id,
                "username": target.username,
                "role": ROLE_ADMIN,
            }
    except AccountStoreError:
        raise


def demote_admin_to_user(target_user_id: str, actor_user_id: str | None = None) -> dict:
    """Demote an admin to a regular user. Main Admin accounts are protected."""
    if not target_user_id:
        raise ValueError("user_id required")
    _assert_actor_may_change_target_role(actor_user_id or "", target_user_id)
    try:
        with repository.auth_session() as session:
            target = repository.find_by_id(session, target_user_id)
            if not target:
                raise LookupError("User not found")
            current_role = normalize_role(target.role)
            if current_role == ROLE_MAIN_ADMIN:
                raise ValueError("Main Admin ownership cannot be changed through demotion")
            if current_role != ROLE_ADMIN:
                raise ValueError("Only admin accounts can be demoted to user")
            if not repository.main_admin_ids(session):
                raise ValueError("At least one Main Admin account must remain")
            repository.set_role(session, target_user_id, ROLE_USER)
            return {
                "user_id": target_user_id,
                "username": target.username,
                "role": ROLE_USER,
            }
    except AccountStoreError:
        raise


def verify_password(user: dict, password: str) -> bool:
    """True if password matches user's stored hash."""
    return bool(user and check_password_hash(user.get("password_hash") or "", password or ""))


def create_initial_main_admin(username: str, password: str) -> dict:
    """Create the first account as Main Admin when the user store is empty."""
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        raise ValueError("username and password required")
    try:
        with repository.auth_session() as session:
            if repository.count_users(session):
                raise ValueError("User store is not empty")
            user = repository.insert_user(
                session,
                user_id=str(uuid.uuid4()),
                username=username,
                password_hash=generate_password_hash(password),
                role=ROLE_MAIN_ADMIN,
            )
            return {"user_id": user.user_id, "username": username}
    except AccountConflict:
        raise ValueError("Could not create the initial Main Admin account.") from None
    except AccountStoreError:
        raise


def create_user(username: str, password: str) -> dict | None:
    """Register user if username not taken. Return user dict or None."""
    username = (username or "").strip()
    password = password or ""
    if not username or len(password) < 1:
        return None
    try:
        with repository.auth_session() as session:
            if repository.find_by_username(session, username):
                return None
            user = repository.insert_user(
                session,
                user_id=str(uuid.uuid4()),
                username=username,
                password_hash=generate_password_hash(password),
                role=ROLE_USER,
            )
            return {"user_id": user.user_id, "username": user.username}
    except AccountConflict:
        return None
