# IA/backend/app/admin/routes.py
# Main Admin user management APIs.

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from app import limiter
from app.auth.manager import get_user_role, list_user_summaries, promote_user_to_admin
from app.auth.permissions import can_promote_users
from app.common.auth import require_auth

bp = Blueprint("admin", __name__)


def _require_main_admin():
    user_id, auth_err = require_auth()
    if auth_err:
        return None, auth_err
    if not can_promote_users(get_user_role(user_id)):
        return None, (jsonify({"error": "Forbidden"}), 403)
    return user_id, None


def _serve_users_page_shell():
    """Browser document loads for /admin/users; API clients send Authorization."""
    if request.method != "GET" or request.headers.get("Authorization"):
        return None
    accept = (request.headers.get("Accept") or "").lower()
    if "text/html" not in accept:
        return None
    return send_from_directory(current_app.static_folder, "index.html")


@bp.route("/users", methods=["GET"])
@limiter.limit("30 per minute")
def list_users():
    shell = _serve_users_page_shell()
    if shell is not None:
        return shell
    _, auth_err = _require_main_admin()
    if auth_err:
        return auth_err
    return jsonify({"users": list_user_summaries()}), 200


@bp.route("/users/<user_id>/promote", methods=["POST"])
@limiter.limit("30 per minute")
def promote_user(user_id):
    _, auth_err = _require_main_admin()
    if auth_err:
        return auth_err
    try:
        promoted = promote_user_to_admin(user_id)
    except LookupError:
        return jsonify({"error": "User not found"}), 404
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(promoted), 200
