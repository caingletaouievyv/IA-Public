# IA/scripts/test/test_ask_note_ids_and_health.py
# Smoke test: health, POST /auth/login, POST /ai/ask, GET /notes. Run from backend/ with app running.

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

_env = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env)
BASE = os.getenv("BASE_URL", "http://127.0.0.1:5000")

try:
    from scripts.test.auth_helper import get_token
except ImportError:
    from auth_helper import get_token


def test_health():
    r = requests.get(f"{BASE}/health", timeout=5)
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "ok"
    print("GET /health OK")


def test_login():
    token = get_token()
    assert token, "get_token returned empty"
    print("POST /auth/login (or register) OK")


def test_ask_no_note_ids():
    token = get_token()
    r = requests.post(
        f"{BASE}/ai/ask",
        json={"question": "hello"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "answer" in data and "tokens_estimated" in data
    print("POST /ai/ask (no note_ids) OK")


def test_ask_with_note_ids():
    token = get_token()
    r = requests.get(f"{BASE}/notes/", headers={"Authorization": f"Bearer {token}"}, timeout=5)
    assert r.status_code == 200, r.text
    notes = r.json()
    if not isinstance(notes, list) or len(notes) < 2:
        print("Skip note_ids test (fewer than 2 notes)")
        return
    ids = [n["id"] for n in notes[:2]]
    r2 = requests.post(
        f"{BASE}/ai/ask",
        json={"question": "summarize", "note_ids": ids},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert r2.status_code == 200, r2.text
    assert "answer" in r2.json()
    print("POST /ai/ask with note_ids OK")


def main():
    try:
        test_health()
        test_login()
        test_ask_no_note_ids()
        test_ask_with_note_ids()
        print("All checks passed.")
    except requests.exceptions.ConnectionError:
        print("Backend not reachable. Run: cd backend && python run.py", file=sys.stderr)
        sys.exit(1)
    except AssertionError as e:
        print(f"Assert failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
