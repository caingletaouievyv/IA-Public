# IA/backend/app/ai/routes.py
# AI routes: Ask, flashcard generation, estimates, and context debugging. Auth required; user_id scopes notes.

import time
import uuid
from flask import Blueprint, request, jsonify
from app import limiter, logger
from app.common.auth import require_auth
from app.common.understanding_gaps import report_understanding_gap
from app.auth.manager import get_user_role
from app.ai.engine import ask, get_token_estimate
from app.ai.flashcards import (
    generate_flashcards,
    validate_flashcard_request,
)
from app.ai.suggestions import generate_suggestion
from app.config import AI_ASK_CREDIT_COST, AI_UNLIMITED_ROLE
from app.credits.manager import (
    InsufficientCreditsError,
    claim_operation,
    complete_operation,
    refund_credits,
    release_operation,
    reserve_credits,
)
from app.memory.manager import build_context
from app.settings.manager import get_settings

bp = Blueprint("ai", __name__)


def _parse_note_ids(data: dict) -> list | None:
    """Extract note IDs from request data and reject malformed selections."""
    note_ids = data.get("note_ids")
    if note_ids is None:
        return None
    if not isinstance(note_ids, list) or any(not isinstance(note_id, str) or not note_id for note_id in note_ids):
        raise ValueError("Invalid 'note_ids'; expected an array of non-empty strings")
    return note_ids


def _parse_note_context_mode(data: dict) -> str:
    """Return the requested note context mode, defaulting legacy requests to automatic."""
    mode = data.get("note_context_mode", "automatic")
    if not isinstance(mode, str) or mode not in ("off", "automatic", "focused"):
        raise ValueError("Invalid 'note_context_mode'; expected 'off', 'automatic', or 'focused'")
    return mode


def _parse_memory_context_mode(data: dict) -> str:
    """Return the requested Memory mode, defaulting legacy requests to off."""
    mode = data.get("memory_context_mode", "off")
    if not isinstance(mode, str) or mode not in ("off", "selected", "automatic"):
        raise ValueError("Invalid 'memory_context_mode'; expected 'off', 'selected', or 'automatic'")
    return mode


def _parse_history_messages(data: dict) -> list | None:
    """Extract messages (list of {role, content}) for conversation history; None if missing or invalid."""
    raw = data.get("messages")
    if not isinstance(raw, list):
        return None
    out = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "user").lower()
        if role not in ("user", "assistant"):
            role = "user"
        content = m.get("content")
        if content is None:
            content = ""
        out.append({"role": role, "content": str(content)})
    return out if out else None


def _operation_id(data: dict) -> str:
    """Use a client retry key when supplied; otherwise create one request identifier."""
    return request.headers.get("Idempotency-Key") or str(data.get("request_id") or uuid.uuid4())


@bp.route("/ask", methods=["POST"])
@limiter.limit("30 per minute")
def ask_ai():
    user_id, auth_err = require_auth()
    if auth_err: return auth_err
    raw_data = request.get_data(cache=True)
    parsed_data = request.get_json(silent=True)
    logger.info(
        "ai_ask request metadata content_type=%s content_length=%s has_data=%s json_parse_success=%s",
        request.content_type,
        request.content_length,
        bool(raw_data),
        parsed_data is not None,
    )
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400
    question = data.get("question")
    if not question:
        return jsonify({"error": "Missing 'question' field"}), 400
    try:
        note_context_mode = _parse_note_context_mode(data)
        _parse_memory_context_mode(data)
        note_ids = _parse_note_ids(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    operation_id = _operation_id(data)
    operation = claim_operation(user_id, operation_id)
    if operation["status"] == "completed":
        return jsonify(operation["result"]), 200
    if operation["status"] == "pending":
        return jsonify({"error": "operation_in_progress"}), 409
    reservation = None
    if get_user_role(user_id) != AI_UNLIMITED_ROLE:
        try:
            reservation = reserve_credits(
                user_id,
                AI_ASK_CREDIT_COST,
                "ai_ask",
                operation_id,
            )
        except InsufficientCreditsError as e:
            release_operation(user_id, operation_id)
            return jsonify({
                "error": "insufficient_ai_credits",
                "message": "Not enough AI Credits",
                "credit_balance": e.balance,
                "credits_required": e.required,
            }), 402
    try:
        ask_started_at = time.perf_counter()
        logger.info("ai_ask ask_start")
        memory_enabled = get_settings(user_id).get("memory_enabled") is True
        answer, tokens, memory_status = ask(
            question,
            note_ids=note_ids,
            note_context_mode=note_context_mode,
            user_id=user_id,
            history_messages=_parse_history_messages(data),
            memory_enabled=memory_enabled,
        )
        logger.info("ai_ask ask_complete elapsed_seconds=%.3f", time.perf_counter() - ask_started_at)
        result = {"answer": answer, "tokens_estimated": tokens, "memory_status": memory_status}
        complete_operation(user_id, operation_id, result)
        return jsonify(result), 200
    except Exception as e:
        if reservation and reservation["charged"]:
            refund_credits(user_id, AI_ASK_CREDIT_COST, "ai_ask_refund", operation_id)
        release_operation(user_id, operation_id)
        return jsonify({"error": str(e)}), 500


@bp.route("/flashcards/generate", methods=["POST"])
@limiter.limit("10 per minute")
def generate_flashcards_route():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400
    try:
        validate_flashcard_request(data)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    operation_id = _operation_id(data)
    operation = claim_operation(user_id, operation_id)
    if operation["status"] == "completed":
        return jsonify(operation["result"]), 200
    if operation["status"] == "pending":
        return jsonify({"error": "operation_in_progress"}), 409

    reservation = None
    if get_user_role(user_id) != AI_UNLIMITED_ROLE:
        try:
            reservation = reserve_credits(
                user_id,
                AI_ASK_CREDIT_COST,
                "ai_flashcards",
                operation_id,
            )
        except InsufficientCreditsError as error:
            release_operation(user_id, operation_id)
            return jsonify({
                "error": "insufficient_ai_credits",
                "message": "Not enough AI Credits",
                "credit_balance": error.balance,
                "credits_required": error.required,
            }), 402

    try:
        result = {"cards": generate_flashcards(user_id, data)}
        complete_operation(user_id, operation_id, result)
        return jsonify(result), 200
    except ValueError as error:
        if reservation and reservation["charged"]:
            refund_credits(user_id, AI_ASK_CREDIT_COST, "ai_flashcards_refund", operation_id)
        release_operation(user_id, operation_id)
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        if reservation and reservation["charged"]:
            refund_credits(user_id, AI_ASK_CREDIT_COST, "ai_flashcards_refund", operation_id)
        release_operation(user_id, operation_id)
        report_understanding_gap("flashcards.generation_failed", error)
        return jsonify({"error": "Flashcard generation failed"}), 502


@bp.route("/suggestions", methods=["POST"])
@limiter.limit("10 per minute")
def get_ai_suggestion():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    if get_settings(user_id).get("ai_suggestions_enabled", True) is not True:
        return jsonify({"suggestion": None}), 200
    try:
        return jsonify({"suggestion": generate_suggestion(user_id)}), 200
    except (OSError, ValueError):
        logger.exception("ai_suggestion_context_failed")
        return jsonify({"error": "Could not load a suggestion"}), 500


@bp.route("/estimate_tokens", methods=["POST"])
def estimate_tokens_route():
    user_id, auth_err = require_auth()
    if auth_err: return auth_err
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400
    question = data.get("question")
    if not question:
        return jsonify({"error": "Missing 'question' field"}), 400
    try:
        result = get_token_estimate(question, note_ids=_parse_note_ids(data), user_id=user_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/debug/context", methods=["POST"])
def debug_context():
    user_id, auth_err = require_auth()
    if auth_err: return auth_err
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400
    question = data.get("question")
    if not question:
        return jsonify({"error": "Missing 'question'"}), 400
    try:
        note_ids = _parse_note_ids(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    result = build_context(question, note_ids=note_ids, user_id=user_id)
    return jsonify({
        "question": question,
        "context": result["context"],
        "context_tokens": result["tokens"],
        "best_faiss_score": result["best_score"],
        "dropped_notes": result["dropped_notes"]
    }), 200
