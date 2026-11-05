# IA/backend/app/auth/main_admin.py
# One-time Main Admin designation. The single owner is enforced in PostgreSQL.

import hmac
import logging
import os
import uuid
from pathlib import Path

from werkzeug.security import generate_password_hash

from sqlalchemy.exc import IntegrityError

from app.auth import manager as auth_manager
from app.auth import repository
from app.auth.manager import find_user_by_id
from app.auth.repository import AccountConflict, AccountStoreError
from app.auth.roles import ROLE_MAIN_ADMIN, normalize_role

MARKER_FILENAME = ".ia_main_admin.json"
BOOTSTRAP_ENABLED_ENV = "MAIN_ADMIN_BOOTSTRAP_ENABLED"
BOOTSTRAP_USERNAME_ENV = "MAIN_ADMIN_BOOTSTRAP_USERNAME"
BOOTSTRAP_SECRET_ENV = "MAIN_ADMIN_BOOTSTRAP_SECRET"
BOOTSTRAP_INITIAL_PASSWORD_ENV = "MAIN_ADMIN_BOOTSTRAP_INITIAL_PASSWORD"
MIN_BOOTSTRAP_SECRET_LENGTH = 8
MIN_INITIAL_PASSWORD_LENGTH = 1
RESERVED_DEMO_USERNAME = "demo"
AUTO_SEED_ENABLED_ENV = "IA_AUTO_SEED_MAIN_ADMIN"
AUTO_SEED_USERNAME_ENV = "IA_AUTO_SEED_MAIN_ADMIN_USERNAME"
AUTO_SEED_PASSWORD_ENV = "IA_AUTO_SEED_MAIN_ADMIN_PASSWORD"
PRODUCTION_BOOTSTRAP_ENABLED_ENV = "IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN"
PRODUCTION_BOOTSTRAP_USERNAME_ENV = "IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_USERNAME"
PRODUCTION_BOOTSTRAP_PASSWORD_ENV = "IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_PASSWORD"
PRODUCTION_BOOTSTRAP_SECRET_ENV = "IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_SECRET"
PRODUCTION_BOOTSTRAP_SECRET_CONFIRM_ENV = "IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_SECRET_CONFIRM"

_logger = logging.getLogger("IA")


class MainAdminBootstrapError(RuntimeError):
    """Operator-facing bootstrap refusal. Messages must not include secrets."""


def marker_path(data_dir: str | None = None) -> Path:
    base = Path(data_dir or auth_manager.DATA_DIR)
    return base / MARKER_FILENAME


def load_marker(data_dir: str | None = None) -> dict | None:
    """Return the Main Admin marker from PostgreSQL. data_dir is ignored."""
    del data_dir
    try:
        with repository.auth_session() as session:
            marker = repository.marker_view(session)
    except AccountStoreError as error:
        raise MainAdminBootstrapError("Main Admin marker is unreadable; refusing to continue.") from error
    if marker is None:
        return None
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
    with repository.auth_session() as session:
        return repository.main_admin_ids(session)


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


def _resolve_initial_password(
    environ: dict[str, str],
    operator_initial_password: str | None,
) -> str:
    """Initial account password from deployment config and/or operator confirmation."""
    configured = (environ.get(BOOTSTRAP_INITIAL_PASSWORD_ENV) or "").strip()
    if configured:
        if len(configured) < MIN_INITIAL_PASSWORD_LENGTH:
            raise MainAdminBootstrapError(
                f"Set {BOOTSTRAP_INITIAL_PASSWORD_ENV} to a non-empty initial password."
            )
        if operator_initial_password is None or not str(operator_initial_password).strip():
            raise MainAdminBootstrapError(
                "Initial Main Admin password requires operator confirmation."
            )
        if not hmac.compare_digest(configured, str(operator_initial_password)):
            raise MainAdminBootstrapError("Initial Main Admin password confirmation failed.")
        return configured
    if operator_initial_password is None or not str(operator_initial_password).strip():
        raise MainAdminBootstrapError(
            f"When the user store is empty, set {BOOTSTRAP_INITIAL_PASSWORD_ENV} "
            "or provide the initial password at the operator prompt."
        )
    plain = str(operator_initial_password)
    if len(plain) < MIN_INITIAL_PASSWORD_LENGTH:
        raise MainAdminBootstrapError("Initial Main Admin password must not be empty.")
    return plain


def _verify_operator_secret(configured_secret: str, operator_secret: str | None) -> None:
    """Require the operator to confirm the configured secret without logging it."""
    if operator_secret is None or not str(operator_secret).strip():
        raise MainAdminBootstrapError(
            "Main Admin bootstrap requires operator confirmation of the configured secret."
        )
    if not hmac.compare_digest(configured_secret, str(operator_secret)):
        raise MainAdminBootstrapError("Main Admin bootstrap secret confirmation failed.")


def _validate_initial_account_credentials(username: str, password: str) -> None:
    if not (username or "").strip():
        raise MainAdminBootstrapError("A non-empty owner username is required.")
    if len(password or "") < MIN_INITIAL_PASSWORD_LENGTH:
        raise MainAdminBootstrapError("A non-empty initial password is required.")
    if username.strip().casefold() == RESERVED_DEMO_USERNAME:
        raise MainAdminBootstrapError(
            "Refusing to designate the shared demo account as Main Admin."
        )


def _run_bootstrap_transaction(action):
    """Lock accounts, run action, and reconcile a lost race without leaking secrets."""
    try:
        with repository.auth_session() as session:
            repository.lock_user_table(session)
            return action(session)
    except (IntegrityError, AccountConflict):
        return None
    except AccountStoreError as error:
        raise MainAdminBootstrapError("Could not update the Main Admin account.") from error


def _create_owner_and_marker(session, username: str, password: str) -> str:
    user_id = str(uuid.uuid4())
    repository.insert_user(
        session,
        user_id=user_id,
        username=username,
        password_hash=generate_password_hash(password),
        role=ROLE_MAIN_ADMIN,
    )
    repository.insert_main_admin_marker(session, user_id)
    user = repository.find_by_id(session, user_id)
    if user is None or normalize_role(user.role) != ROLE_MAIN_ADMIN:
        raise MainAdminBootstrapError("Could not verify the initial Main Admin account role.")
    return f"Main Admin account created for username {username}."


def _restore_or_reject(session, marker: dict, username: str, target_user_id: str) -> str:
    marker_user = repository.find_by_id(session, marker["user_id"])
    if marker_user is None:
        raise MainAdminBootstrapError(
            "Main Admin marker exists but the designated account is missing; resolve manually."
        )
    if marker["user_id"] != target_user_id or marker["username"] != username:
        raise MainAdminBootstrapError(
            "Main Admin is already designated for a different account; reruns cannot change the owner."
        )
    if normalize_role(marker_user.role) != ROLE_MAIN_ADMIN:
        try:
            repository.set_role(session, marker["user_id"], ROLE_MAIN_ADMIN)
        except ValueError as error:
            raise MainAdminBootstrapError("Could not update the designated account role.") from error
        return f"Main Admin role restored for username {username}."
    return f"Main Admin already designated for username {username}."


def _refuse_owner_without_marker(session) -> None:
    if repository.main_admin_ids(session):
        raise MainAdminBootstrapError(
            "Users file already contains a main_admin role but no Main Admin marker; "
            "resolve manually before bootstrapping."
        )


def _reconcile_same_owner(username: str) -> str:
    with repository.auth_session() as session:
        repository.lock_user_table(session)
        marker = repository.marker_view(session)
        user = repository.find_by_username(session, username)
        if marker and user and marker["user_id"] == user.user_id:
            return _restore_or_reject(session, marker, username, user.user_id)
    raise MainAdminBootstrapError("Could not create the initial Main Admin account.")


def provision_initial_main_admin_account(username: str, password: str) -> str:
    """Create Main Admin and marker together when the account table is empty."""
    username = (username or "").strip()
    _validate_initial_account_credentials(username, password)

    def act(session) -> str:
        marker = repository.marker_view(session)
        if marker:
            return _restore_or_reject(session, marker, username, marker["user_id"])
        _refuse_owner_without_marker(session)
        if repository.count_users(session) == 0:
            return _create_owner_and_marker(session, username, password)
        target = repository.find_by_username(session, username)
        if target is None:
            raise MainAdminBootstrapError(
                "User store is no longer empty; bootstrap username does not match an existing account."
            )
        repository.insert_main_admin_marker(session, target.user_id)
        if normalize_role(target.role) != ROLE_MAIN_ADMIN:
            repository.set_role(session, target.user_id, ROLE_MAIN_ADMIN)
        return f"Main Admin designated for username {username}."

    result = _run_bootstrap_transaction(act)
    if result is None:
        return _reconcile_same_owner(username)
    return result


def _bootstrap_initial_empty_store(
    environ: dict[str, str],
    username: str,
    operator_initial_password: str | None,
) -> str:
    """Create the first Main Admin account when the users table is empty."""
    initial_password = _resolve_initial_password(environ, operator_initial_password)
    return provision_initial_main_admin_account(username, initial_password)


class MainAdminAutoSeedError(RuntimeError):
    """Development auto-seed misconfiguration. Messages must not include secrets."""


def maybe_auto_seed_main_admin_on_startup() -> None:
    """Development/test only: seed Main Admin when the user store and marker are both empty."""
    from app.config import APP_ENV, IA_AUTO_SEED_MAIN_ADMIN, IA_AUTO_SEED_MAIN_ADMIN_USERNAME

    if not IA_AUTO_SEED_MAIN_ADMIN:
        return

    if APP_ENV == "production":
        raise MainAdminAutoSeedError(
            f"{AUTO_SEED_ENABLED_ENV} cannot be enabled when APP_ENV is production."
        )
    if APP_ENV not in {"development", "test"}:
        raise MainAdminAutoSeedError(
            f"{AUTO_SEED_ENABLED_ENV} is only allowed when APP_ENV is development or test."
        )

    username = IA_AUTO_SEED_MAIN_ADMIN_USERNAME
    password = (os.getenv(AUTO_SEED_PASSWORD_ENV) or "")
    if not username or len(password) < MIN_INITIAL_PASSWORD_LENGTH:
        raise MainAdminAutoSeedError(
            f"{AUTO_SEED_ENABLED_ENV} requires non-empty {AUTO_SEED_USERNAME_ENV} "
            f"and {AUTO_SEED_PASSWORD_ENV}."
        )
    if username.casefold() == RESERVED_DEMO_USERNAME:
        raise MainAdminAutoSeedError(
            "Refusing to auto-seed the shared demo account as Main Admin."
        )

    if auth_manager._load_users():
        return

    marker = load_marker()
    if marker:
        marker_user = find_user_by_id(marker["user_id"])
        if marker_user and normalize_role(marker_user.get("role")) == ROLE_MAIN_ADMIN:
            return
        raise MainAdminAutoSeedError(
            "Main Admin marker exists but the user store is empty; resolve manually."
        )

    provision_initial_main_admin_account(username, password)
    _logger.info("Main Admin auto-seed completed for local development.")


def _verify_production_bootstrap_secrets(configured_secret: str, confirm_secret: str) -> None:
    """Non-interactive operator confirmation for production startup bootstrap."""
    if len(configured_secret) < MIN_BOOTSTRAP_SECRET_LENGTH:
        raise MainAdminAutoSeedError(
            f"Set {PRODUCTION_BOOTSTRAP_SECRET_ENV} to at least {MIN_BOOTSTRAP_SECRET_LENGTH} characters."
        )
    if not confirm_secret.strip():
        raise MainAdminAutoSeedError(
            f"Set {PRODUCTION_BOOTSTRAP_SECRET_CONFIRM_ENV} to confirm the production bootstrap secret."
        )
    if not hmac.compare_digest(configured_secret, confirm_secret):
        raise MainAdminAutoSeedError("Production bootstrap secret confirmation failed.")


def maybe_production_bootstrap_main_admin_on_startup() -> None:
    """Production one-time bootstrap when the user store and marker are both empty."""
    from app.config import APP_ENV, IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN

    if not IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN:
        return

    if APP_ENV != "production":
        raise MainAdminAutoSeedError(
            f"{PRODUCTION_BOOTSTRAP_ENABLED_ENV} is only allowed when APP_ENV is production."
        )

    username = (os.getenv(PRODUCTION_BOOTSTRAP_USERNAME_ENV) or "").strip()
    password = os.getenv(PRODUCTION_BOOTSTRAP_PASSWORD_ENV) or ""
    configured_secret = (os.getenv(PRODUCTION_BOOTSTRAP_SECRET_ENV) or "").strip()
    confirm_secret = os.getenv(PRODUCTION_BOOTSTRAP_SECRET_CONFIRM_ENV) or ""

    if not username or len(password) < MIN_INITIAL_PASSWORD_LENGTH:
        raise MainAdminAutoSeedError(
            f"{PRODUCTION_BOOTSTRAP_ENABLED_ENV} requires non-empty "
            f"{PRODUCTION_BOOTSTRAP_USERNAME_ENV} and {PRODUCTION_BOOTSTRAP_PASSWORD_ENV}."
        )
    if username.casefold() == RESERVED_DEMO_USERNAME:
        raise MainAdminAutoSeedError(
            "Refusing to bootstrap the shared demo account as Main Admin."
        )
    _verify_production_bootstrap_secrets(configured_secret, confirm_secret)

    if auth_manager._load_users():
        return

    marker = load_marker()
    if marker:
        marker_user = find_user_by_id(marker["user_id"])
        if marker_user and normalize_role(marker_user.get("role")) == ROLE_MAIN_ADMIN:
            return
        raise MainAdminAutoSeedError(
            "Main Admin marker exists but the user store is empty; resolve manually."
        )

    provision_initial_main_admin_account(username, password)
    _logger.info("Production Main Admin one-time bootstrap completed.")


def maybe_provision_main_admin_on_startup() -> None:
    """Local dev auto-seed and optional production one-time empty-store bootstrap."""
    from app.config import IA_AUTO_SEED_MAIN_ADMIN, IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN

    if IA_AUTO_SEED_MAIN_ADMIN and IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN:
        raise MainAdminAutoSeedError(
            "Enable only one of "
            f"{AUTO_SEED_ENABLED_ENV} or {PRODUCTION_BOOTSTRAP_ENABLED_ENV}, not both."
        )
    maybe_auto_seed_main_admin_on_startup()
    maybe_production_bootstrap_main_admin_on_startup()


def bootstrap_main_admin(
    environ: dict[str, str] | None = None,
    *,
    operator_secret: str | None = None,
    operator_initial_password: str | None = None,
) -> str:
    """
    Designate exactly one Main Admin.
    Safe to rerun when the same owner is already designated.
    """
    env = os.environ if environ is None else environ
    username, configured_secret = _validate_bootstrap_configuration(env)
    _verify_operator_secret(configured_secret, operator_secret)

    def act(session) -> str:
        target = repository.find_by_username(session, username)
        if target is None:
            if repository.count_users(session):
                raise MainAdminBootstrapError(
                    "Bootstrap username does not match an existing account. Register the owner first."
                )
            password = _resolve_initial_password(env, operator_initial_password)
            _validate_initial_account_credentials(username, password)
            marker = repository.marker_view(session)
            if marker:
                return _restore_or_reject(session, marker, username, marker["user_id"])
            _refuse_owner_without_marker(session)
            return _create_owner_and_marker(session, username, password)
        marker = repository.marker_view(session)
        if marker:
            return _restore_or_reject(session, marker, username, target.user_id)
        _refuse_owner_without_marker(session)
        repository.insert_main_admin_marker(session, target.user_id)
        if normalize_role(target.role) != ROLE_MAIN_ADMIN:
            try:
                repository.set_role(session, target.user_id, ROLE_MAIN_ADMIN)
            except ValueError as error:
                raise MainAdminBootstrapError("Could not update the designated account role.") from error
        return f"Main Admin designated for username {username}."

    result = _run_bootstrap_transaction(act)
    if result is None:
        reconciled = _reconcile_same_owner(username)
        if reconciled:
            return reconciled
    return result
