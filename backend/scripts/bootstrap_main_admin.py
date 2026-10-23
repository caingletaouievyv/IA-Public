# IA/backend/scripts/bootstrap_main_admin.py
# Operator command to designate exactly one Main Admin for this data directory.

import sys
from getpass import getpass
from pathlib import Path

root = Path(__file__).resolve().parents[2]
dotenv = root / ".env"
if dotenv.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv)

from app.auth.main_admin import MainAdminBootstrapError, bootstrap_main_admin


def main() -> None:
    operator_secret = getpass("Main Admin bootstrap secret: ")
    message = bootstrap_main_admin(operator_secret=operator_secret)
    print(message)


if __name__ == "__main__":
    try:
        main()
    except MainAdminBootstrapError as error:
        print(f"Main Admin bootstrap refused: {error}", file=sys.stderr)
        sys.exit(2)
