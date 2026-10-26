# IA/backend/app/settings/routes.py
# GET/PUT /settings: per-user preferences (Phase 8). Auth required.

from flask import Blueprint, request, jsonify
from app.common.auth import require_auth
from app.settings.manager import get_settings, save_settings

bp = Blueprint("settings", __name__)

@bp.route("/", methods=["GET"], strict_slashes=False)
def get_settings_route():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    settings = get_settings(user_id)
    settings.setdefault("memory_enabled", False)
    settings.setdefault("ai_suggestions_enabled", True)
    settings.setdefault("remember_command_enabled", True)
    return jsonify(settings)

@bp.route("/", methods=["PUT"], strict_slashes=False)
def put_settings_route():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400
    if "memory_enabled" in data and not isinstance(data["memory_enabled"], bool):
        return jsonify({"error": "'memory_enabled' must be a boolean"}), 400
    if "ai_suggestions_enabled" in data and not isinstance(data["ai_suggestions_enabled"], bool):
        return jsonify({"error": "'ai_suggestions_enabled' must be a boolean"}), 400
    if "remember_command_enabled" in data and not isinstance(data["remember_command_enabled"], bool):
        return jsonify({"error": "'remember_command_enabled' must be a boolean"}), 400
    updated = save_settings(user_id, data)
    return jsonify(updated)
