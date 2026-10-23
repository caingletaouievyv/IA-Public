# IA/backend/app/auth/main_admin.py
# One-time Main Admin designation via marker file + explicit operator configuration.

import datetime
import hmac
import json
import os
from pathlib import Path

from app.auth import manager as auth_manager
from app.auth.manager import find_user_by_id, find_user_by_username, set_user_role
from app.auth.roles import ROLE_MAIN_ADMIN, normalize_role

MARKER_FILENAME = ".ia_main_admin.json"
BOOTSTRAP_ENABLED_ENV = "MAIN_ADMIN_BOOTSTRAP_ENABLED"
BOOTSTRAP_USERNAME_ENV = "MAIN_ADMIN_BOOTSTRAP_USERNAME"
BOOTSTRAP_SECRET_ENV = "MAIN_ADMIN_BOOTSTRAP_SECRET"
MIN_BOOTSTRAP_SECRET_LENGTH = 32
RESERVED_DEMO_USERNAME = "demo"


class MainAdminBootstrapError(RuntimeError):
    """Operator-facing bootstrap refusal. Messages must not include secrets."""


def marker_path(data_dir: str | None = None) -> Path:
    base = Path(data_dir or auth_manager.DATA_DIR)
    return base / MARKER_FILENAME


def load_marker(data_dir: str | None = None) -> dict | None:
    path = marker_path(data_dir)
    try:
        with path.open(encoding="utf-8") as handle:
            marker = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise MainAdminBootstrapError("Main Admin marker is unreadable; refusing to continue.") from error
    _validate_marker_shape(marker)
    return marker


def _validate_marker_shape(marker: dict) -> None:
    if (
        not isinstance(marker, dict)
        or not isinstance(marker.get("username"), str)
        or not marker.get("username").strip()
        or not isinstance(marker.get("user_id"), str)
        or not marker.get("user_id").strip()
        or not isinstance(marker.get("created_at"), str)
        or not marker.get("created_at").strip()
    ):
        raise MainAdminBootstrapError("Main Admin marker is invalid; refusing to continue.")


def list_main_admin_user_ids() -> list[str]:
    user_ids = []
    for user in auth_manager._load_users():
        if normalize_role(user.get("role")) == ROLE_MAIN_ADMIN:
            user_ids.append(user["user_id"])
    return user_ids


def _validate_bootstrap_configuration(environ: dict[str, str]) -> tuple[str, str]:
    enabled = (environ.get(BOOTSTRAP_ENABLED_ENV) or "").strip().lower()
    if enabled != "true":
        raise MainAdminBootstrapError(
            f"Set {BOOTSTRAP_ENABLED_ENV}=true to explicitly enable Main Admin bootstrap."
        )

    username = (environ.get(BOOTSTRAP_USERNAME_ENV) or "").strip()
    if not username:
        raise MainAdminBootstrapError(f"Set {BOOTSTRAP_USERNAME_ENV} to the owner account username.")

    if username.casefold() == RESERVED_DEMO_USERNAME:
        raise MainAdminBootstrapError(
            "Refusing to designate the shared demo account as Main Admin."
        )

    configured_secret = (environ.get(BOOTSTRAP_SECRET_ENV) or "").strip()
    if len(configured_secret) < MIN_BOOTSTRAP_SECRET_LENGTH:
        raise MainAdminBootstrapError(
            f"Set {BOOTSTRAP_SECRET_ENV} to at least {MIN_BOOTSTRAP_SECRET_LENGTH} characters."
        )
    return username, configured_secret


def _verify_operator_secret(configured_secret: str, operator_secret: str | None) -> None:
    """Require the operator to confirm the configured secret without logging it."""
    if operator_secret is None or not str(operator_secret).strip():
        raise MainAdminBootstrapError(
            "Main Admin bootstrap requires operator confirmation of the configured secret."
        )
    if not hmac.compare_digest(configured_secret, str(operator_secret)):
        raise MainAdminBootstrapError("Main Admin bootstrap secret confirmation failed.")


def _try_create_marker(path: Path, payload: dict) -> bool:
    """Create marker exclusively. Returns False if another process created it first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return True


def _remove_marker(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise MainAdminBootstrapError("Could not roll back Main Admin marker after a failed update.") from error


def bootstrap_main_admin(
    environ: dict[str, str] | None = None,
    *,
    operator_secret: str | None = None,
) -> str:
    """
    Designate exactly one Main Admin for this data directory.
    Safe to rerun when the same owner is already designated.
    """
    env = os.environ if environ is None else environ
    username, configured_secret = _validate_bootstrap_configuration(env)
    _verify_operator_secret(configured_secret, operator_secret)
    path = marker_path()
    target_user = find_user_by_username(username)
    if not target_user:
        raise MainAdminBootstrapError(
            "Bootstrap username does not match an existing account. Register the owner first."
        )
    target_user_id = target_user["user_id"]

    existing_marker = load_marker()
    if existing_marker:
        return _bootstrap_with_existing_marker(existing_marker, username, target_user_id)

    existing_main_admins = list_main_admin_user_ids()
    if existing_main_admins:
        raise MainAdminBootstrapError(
            "Users file already contains a main_admin role but no Main Admin marker; "
            "resolve manually before bootstrapping."
        )

    payload = {
        "username": username,
        "user_id": target_user_id,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    created = _try_create_marker(path, payload)
    if not created:
        existing_marker = load_marker()
        if not existing_marker:
            raise MainAdminBootstrapError(
                "Main Admin marker could not be created; another bootstrap may be in progress."
            )
        return _bootstrap_with_existing_marker(existing_marker, username, target_user_id)

    try:
        set_user_role(target_user_id, ROLE_MAIN_ADMIN)
    except (OSError, ValueError) as error:
        _remove_marker(path)
        raise MainAdminBootstrapError("Could not update the designated account role.") from error

    return f"Main Admin designated for username {username}."


def _bootstrap_with_existing_marker(marker: dict, username: str, target_user_id: str) -> str:
    marker_user_id = marker["user_id"]
    marker_username = marker["username"]
    marker_user = find_user_by_id(marker_user_id)
    if not marker_user:
        raise MainAdminBootstrapError(
            "Main Admin marker exists but the designated account is missing; resolve manually."
        )

    if marker_user_id != target_user_id or marker_username != username:
        raise MainAdminBootstrapError(
            "Main Admin is already designated for a different account; reruns cannot change the owner."
        )

    if normalize_role(marker_user.get("role")) != ROLE_MAIN_ADMIN:
        set_user_role(marker_user_id, ROLE_MAIN_ADMIN)
        return f"Main Admin role restored for username {username}."

    return f"Main Admin already designated for username {username}."
