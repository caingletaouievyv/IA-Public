# IA/backend/app/diagnostics/routes.py
"""Authenticated diagnostic feedback and admin-only event review."""

import logging

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app import limiter
from app.auth.manager import get_user_role
from app.common.auth import require_auth
from app.common.understanding_gaps import report_user_feedback
from app.config import AI_UNLIMITED_ROLE
from app.credits.manager import has_completed_operation
from app.diagnostics import manager
from app.diagnostics.schemas import DiagnosticFeedbackRequest

logger = logging.getLogger(__name__)
bp = Blueprint("diagnostics", __name__)


@bp.route("/feedback", methods=["POST"])
@limiter.limit("30 per minute")
def submit_feedback():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400
    try:
        payload = DiagnosticFeedbackRequest.model_validate(data)
    except ValidationError as error:
        return jsonify({"error": error.errors()[0]["msg"]}), 400

    if not has_completed_operation(user_id, payload.operation_id):
        return jsonify({"error": "Unknown or incomplete Ask operation"}), 404

    try:
        event = report_user_feedback(
            user_id,
            feature=payload.feature,
            reason=payload.reason,
            operation_id=payload.operation_id,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except (OSError, ValueError):
        logger.exception("diagnostics_feedback_write_failed")
        return jsonify({"error": "Failed to record feedback"}), 500

    return jsonify({"status": "recorded", "event_id": event["event_id"]}), 201


@bp.route("/events", methods=["GET"])
@limiter.limit("30 per minute")
def list_events():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    if get_user_role(user_id) != AI_UNLIMITED_ROLE:
        return jsonify({"error": "Forbidden"}), 403

    raw_limit = request.args.get("limit")
    try:
        limit = manager.DEFAULT_ADMIN_LIMIT if raw_limit is None else int(raw_limit)
    except ValueError:
        return jsonify({"error": "limit must be a positive integer"}), 400
    if limit < 1:
        return jsonify({"error": "limit must be a positive integer"}), 400

    try:
        return jsonify({"events": manager.list_events_admin(limit=limit)}), 200
    except (OSError, ValueError):
        logger.exception("diagnostics_events_read_failed")
        return jsonify({"error": "Failed to load diagnostic events"}), 500
