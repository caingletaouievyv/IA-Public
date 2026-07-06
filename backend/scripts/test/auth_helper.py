# IA/backend/scripts/test/auth_helper.py
# Helper: get Bearer token via login (or register). For scripts that call protected APIs.

import os
import requests
from pathlib import Path
from dotenv import load_dotenv

_env = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env)
BASE = os.getenv("BASE_URL", "http://127.0.0.1:5000")
TEST_USER = os.getenv("TEST_USER", "testuser")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "testpass")


def get_token():
    """Login (or register then login); return Bearer token string. Raises on failure."""
    # Try login first
    r = requests.post(
        f"{BASE}/auth/login",
        json={"username": TEST_USER, "password": TEST_PASSWORD},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    if r.status_code == 200:
        return r.json()["token"]
    if r.status_code == 401:
        # Register then login
        r2 = requests.post(
            f"{BASE}/auth/register",
            json={"username": TEST_USER, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if r2.status_code not in (200, 201):
            raise RuntimeError(f"Register failed: {r2.status_code} {r2.text}")
        return r2.json()["token"]
    raise RuntimeError(f"Login failed: {r.status_code} {r.text}")
