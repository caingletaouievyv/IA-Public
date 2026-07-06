# IA/backend/app/common/auth.py
# Auth: Bearer JWT only (login token). user_id from JWT sub. No API secret (docs/ia.md: JWT).

import logging
import jwt
from flask import request, jsonify
from app.config import JWT_SECRET, JWT_ALGORITHM

logger = logging.getLogger(__name__)


def _bearer_token():
    """Extract Bearer token from Authorization header, or None."""
    raw = request.headers.get("Authorization") or ""
    if not raw.strip().lower().startswith("bearer "):
        return None
    return raw[7:].strip() or None


def _decode_token(token: str) -> str | None:
    """Return user_id (sub) if token valid; else None."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


def check_auth():
    """True if request has valid Bearer JWT."""
    token = _bearer_token()
    return _decode_token(token) is not None


def get_user_id():
    """Stable user_id from request JWT (sub claim). Call after check_auth() or require_auth()."""
    token = _bearer_token()
    return _decode_token(token) or ""


def require_auth():
    """(user_id, None) if valid JWT; else (None, (jsonify error, 401)). Routes: user_id, err = require_auth(); if err: return err."""
    token = _bearer_token()
    user_id = _decode_token(token) if token else None
    if not user_id:
        # Log without token value: debug missing header vs invalid/expired token (docs/ia.md: no secrets in logs).
        logger.warning("auth_fail path=%s method=%s header_present=%s", request.path, request.method, bool(token))
        return (None, (jsonify({"error": "Unauthorized"}), 401))
    return (user_id, None)


def auth_debug():
    """Return auth debug info (no secret). GET /notes/auth-check with Bearer JWT."""
    token = _bearer_token()
    ok = _decode_token(token) is not None
    return jsonify({
        "auth_ok": ok,
        "header_received": bool(token),
        "header_length": len(token) if token else 0,
    })
