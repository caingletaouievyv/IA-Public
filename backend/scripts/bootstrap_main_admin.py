# IA/backend/scripts/bootstrap_main_admin.py
# Operator command to designate exactly one Main Admin for this data directory.

import os
import sys
from getpass import getpass
from pathlib import Path

root = Path(__file__).resolve().parents[2]
dotenv = root / ".env"
if dotenv.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv)

from app.auth import manager as auth_manager
from app.auth.main_admin import (
    BOOTSTRAP_INITIAL_PASSWORD_ENV,
    MainAdminBootstrapError,
    bootstrap_main_admin,
)


def main() -> None:
    operator_secret = getpass("Main Admin bootstrap secret: ")
    operator_initial_password = None
    if auth_manager.store_is_empty():
        configured_password = (os.environ.get(BOOTSTRAP_INITIAL_PASSWORD_ENV) or "").strip()
        if configured_password:
            operator_initial_password = getpass("Confirm initial Main Admin password: ")
        else:
            operator_initial_password = getpass("Initial Main Admin password: ")
    message = bootstrap_main_admin(
        operator_secret=operator_secret,
        operator_initial_password=operator_initial_password,
    )
    print(message)


if __name__ == "__main__":
    try:
        main()
    except MainAdminBootstrapError as error:
        print(f"Main Admin bootstrap refused: {error}", file=sys.stderr)
        sys.exit(2)
