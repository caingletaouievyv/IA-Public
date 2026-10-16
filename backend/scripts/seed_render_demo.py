"""Explicitly seed the demo account before starting a Render production service."""

import os
import sys
import json
import tempfile
from pathlib import Path

# Load the repository-root .env before importing configuration, matching the existing seed command.
root = Path(__file__).resolve().parents[2]
dotenv = root / ".env"
if dotenv.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv)

from scripts.seed_user import seed_demo_data
from app.auth import manager as auth_manager
from app.auth.manager import create_user, find_user_by_username

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
    marker_path = Path(auth_manager.DATA_DIR) / SEED_MARKER_FILENAME
    user = find_user_by_username(DEMO_USERNAME)
    marker_user_id = _load_seed_marker(marker_path)
    created = False

    if user:
        if marker_user_id != user.get("user_id"):
            raise RuntimeError(
                "Refusing to seed an existing demo account not verified as created by "
                "the Render demo seeder."
            )
    else:
        if marker_user_id is not None:
            raise RuntimeError(
                "Render demo seed marker exists but the demo account is missing; "
                "refusing to recreate it automatically."
            )
        user = create_user(DEMO_USERNAME, password)
        if not user:
            raise RuntimeError("Could not create the demo account; it may have been registered concurrently.")
        _save_seed_marker(marker_path, user["user_id"])
        created = True

    return seed_demo_data(DEMO_USERNAME, password, created=created)


def _load_seed_marker(marker_path: Path) -> str | None:
    try:
        with marker_path.open(encoding="utf-8") as marker_file:
            marker = json.load(marker_file)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise RuntimeError("Render demo seed marker is unreadable; refusing to seed.") from error

    if (
        not isinstance(marker, dict)
        or marker.get("username") != DEMO_USERNAME
        or not isinstance(marker.get("user_id"), str)
        or not marker["user_id"]
    ):
        raise RuntimeError("Render demo seed marker is invalid; refusing to seed.")
    return marker["user_id"]


def _save_seed_marker(marker_path: Path, user_id: str) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=marker_path.parent,
            prefix=".render-demo-seed-",
            suffix=".tmp",
            delete=False,
        ) as marker_file:
            temp_path = Path(marker_file.name)
            json.dump({"username": DEMO_USERNAME, "user_id": user_id}, marker_file)
            marker_file.flush()
            os.fsync(marker_file.fileno())
        os.replace(temp_path, marker_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def main() -> None:
    seed_render_demo()
    print("Render demo account and missing sample notes are ready.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"Render demo seed refused: {error}", file=sys.stderr)
        sys.exit(2)
