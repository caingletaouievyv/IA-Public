# IA/backend/app/auth/routes.py
# POST /auth/register, POST /auth/login. Returns JWT; no API secret (docs/ia.md: JWT auth).

import datetime
import jwt
from flask import Blueprint, request, jsonify
from app.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXP_DAYS
from app.common.auth import require_auth
from app.auth.manager import find_user_by_id, find_user_by_username, get_user_role, verify_password, create_user

bp = Blueprint("auth", __name__)


def _issue_token(user_id: str) -> str:
    """Encode JWT with sub=user_id, exp=now+JWT_EXP_DAYS. Return token string."""
    payload = {
        "sub": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=JWT_EXP_DAYS),
    }
    out = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return out.decode() if isinstance(out, bytes) else out


@bp.route("/register", methods=["POST"])
def register():
    """Create user. JSON: username, password. Returns token + user on success."""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username:
        return jsonify({"error": "username required"}), 400
    if not password:
        return jsonify({"error": "password required"}), 400
    user = create_user(username, password)
    if not user:
        return jsonify({"error": "username already taken"}), 409
    token = _issue_token(user["user_id"])
    return jsonify({"token": token, "user_id": user["user_id"], "username": user["username"]}), 201


@bp.route("/me", methods=["GET"])
def me():
    """Return the authenticated user's id, username, and persisted role."""
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    user = find_user_by_id(user_id)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "user_id": user_id,
        "username": user.get("username"),
        "role": get_user_role(user_id),
    }), 200


@bp.route("/login", methods=["POST"])
def login():
    """Validate username+password; return JWT and user."""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    user = find_user_by_username(username)
    if not user or not verify_password(user, password):
        return jsonify({"error": "Invalid username or password"}), 401
    token = _issue_token(user["user_id"])
    return jsonify({
        "token": token,
        "user_id": user["user_id"],
        "username": user["username"],
    }), 200
