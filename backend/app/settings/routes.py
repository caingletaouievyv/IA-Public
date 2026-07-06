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
    return jsonify(get_settings(user_id))

@bp.route("/", methods=["PUT"], strict_slashes=False)
def put_settings_route():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400
    updated = save_settings(user_id, data)
    return jsonify(updated)
