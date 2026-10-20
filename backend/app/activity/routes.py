"""Authenticated suggestion event context API."""

import logging

from flask import Blueprint, jsonify, request

from app.activity import manager
from app.common.auth import require_auth

logger = logging.getLogger(__name__)
bp = Blueprint("activity", __name__)


@bp.route("/", methods=["GET"], strict_slashes=False)
def get_activity():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err

    raw_limit = request.args.get("limit")
    try:
        limit = manager.DEFAULT_ACTIVITY_LIMIT if raw_limit is None else int(raw_limit)
    except ValueError:
        return jsonify({"error": "limit must be a positive integer"}), 400
    if limit < 1:
        return jsonify({"error": "limit must be a positive integer"}), 400

    try:
        return jsonify(manager.list_activity(user_id, limit))
    except (OSError, ValueError):
        logger.exception("activity_history_read_failed")
        return jsonify({"error": "Failed to load suggestion context"}), 500
