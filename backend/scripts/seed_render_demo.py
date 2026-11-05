"""Explicitly seed the demo account before starting a Render production service."""

import os
import sys
import uuid
from pathlib import Path

# Load the repository-root .env before importing configuration, matching the existing seed command.
root = Path(__file__).resolve().parents[2]
dotenv = root / ".env"
if dotenv.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv)

from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from scripts.seed_user import seed_demo_data
from app.auth import repository
from app.auth.repository import AccountConflict, AccountStoreError
from app.auth.roles import ROLE_USER

SEED_ENABLED_ENV = "RENDER_DEMO_SEED_ENABLED"
SEED_PASSWORD_ENV = "SEED_USER_PASSWORD"
DEMO_USERNAME = "demo"
MIN_PASSWORD_LENGTH = 12
SEED_MARKER_FILENAME = ".render_demo_seed.json"


def validate_render_seed_configuration(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    app_env = (env.get("APP_ENV") or "").strip().lower()
    if app_env != "production":
        raise RuntimeError("Render demo seeding requires APP_ENV=production.")
    if (env.get(SEED_ENABLED_ENV) or "").strip().lower() != "true":
        raise RuntimeError(f"Set {SEED_ENABLED_ENV}=true to explicitly enable Render demo seeding.")

    password = (env.get(SEED_PASSWORD_ENV) or "").strip()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise RuntimeError(
            f"Set {SEED_PASSWORD_ENV} to a password of at least "
            f"{MIN_PASSWORD_LENGTH} characters."
        )
    return password


def seed_render_demo(environ: dict[str, str] | None = None) -> dict:
    password = validate_render_seed_configuration(environ)
    created = _ensure_demo_account(password)
    return seed_demo_data(DEMO_USERNAME, password, created=created)


def _ensure_demo_account(password: str) -> bool:
    """Create the demo user and its singleton marker in one transaction."""
    try:
        with repository.auth_session() as session:
            repository.lock_user_table(session)
            user = repository.find_by_username(session, DEMO_USERNAME)
            marker_user_id = repository.demo_marker_user_id(session)
            if user:
                if marker_user_id != user.user_id:
                    raise RuntimeError(
                        "Refusing to seed an existing demo account not verified as created by "
                        "the Render demo seeder."
                    )
                return False
            if marker_user_id is not None:
                raise RuntimeError(
                    "Render demo seed marker exists but the demo account is missing; "
                    "refusing to recreate it automatically."
                )
            created = repository.insert_user(
                session,
                user_id=str(uuid.uuid4()),
                username=DEMO_USERNAME,
                password_hash=generate_password_hash(password),
                role=ROLE_USER,
            )
            repository.insert_demo_marker(session, created.user_id)
            return True
    except (IntegrityError, AccountConflict):
        raise RuntimeError(
            "Could not create the demo account; it may have been registered concurrently."
        ) from None
    except AccountStoreError as error:
        raise RuntimeError("Could not create the demo account.") from error


def main() -> None:
    seed_render_demo()
    print("Render demo account and missing sample notes are ready.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"Render demo seed refused: {error}", file=sys.stderr)
        sys.exit(2)
