"""Authenticated CRUD routes for a user's independent Memory records."""

from flask import Blueprint, jsonify, request

from app.common.auth import require_auth
from app.memories import manager
from app.memories.repository import MemoryStoreError

bp = Blueprint("memories", __name__)


@bp.route("/", methods=["GET"], strict_slashes=False)
def list_memories():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    try:
        return jsonify(manager.list_memories(user_id))
    except Exception:
        return jsonify({"error": "Failed to load memories"}), 500


@bp.route("/<string:memory_id>", methods=["PUT"])
def edit_memory(memory_id):
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"text"}:
        return jsonify({"error": "JSON object with a text field required"}), 400
    try:
        updated = manager.update_memory(user_id, memory_id, data["text"])
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except MemoryStoreError:
        return jsonify({"error": "Failed to update memory"}), 500
    if updated is None:
        return jsonify({"error": "Memory not found"}), 404
    return jsonify(updated)


@bp.route("/<string:memory_id>", methods=["DELETE"])
def remove_memory(memory_id):
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    try:
        deleted = manager.delete_memory(user_id, memory_id)
    except MemoryStoreError:
        return jsonify({"error": "Failed to delete memory"}), 500
    if not deleted:
        return jsonify({"error": "Memory not found"}), 404
    return jsonify({"message": "Memory deleted"})


@bp.route("/clear", methods=["DELETE"])
def clear_memories():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    try:
        deleted = manager.clear_memories(user_id)
    except MemoryStoreError:
        return jsonify({"error": "Failed to clear memories"}), 500
    return jsonify({"deleted": deleted})
