# IA/backend/app/ai/routes.py
# AI routes: /ask, /estimate_tokens, /debug/context. Auth required (Phase 8); user_id scopes notes.

import time
import uuid
from flask import Blueprint, request, jsonify
from app import limiter, logger
from app.common.auth import require_auth
from app.auth.manager import get_user_role
from app.ai.engine import ask, get_token_estimate
from app.config import AI_ASK_CREDIT_COST, AI_UNLIMITED_ROLE
from app.credits.manager import InsufficientCreditsError, refund_credits, reserve_credits
from app.memory.manager import build_context

bp = Blueprint("ai", __name__)


def _parse_note_ids(data: dict) -> list | None:
    """Extract and normalize note_ids from request data; None if missing or not a list."""
    note_ids = data.get("note_ids")
    if note_ids is None or not isinstance(note_ids, list):
        return None
    return [str(x) for x in note_ids]


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
    data = request.get_json(silent=True) or {}
    question = data.get("question")
    if not question:
        return jsonify({"error": "Missing 'question' field"}), 400
    operation_id = _operation_id(data)
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
            return jsonify({
                "error": "insufficient_ai_credits",
                "message": "Not enough AI Credits",
                "credit_balance": e.balance,
                "credits_required": e.required,
            }), 402
    try:
        ask_started_at = time.perf_counter()
        logger.info("ai_ask ask_start")
        answer, tokens = ask(
            question,
            note_ids=_parse_note_ids(data),
            user_id=user_id,
            history_messages=_parse_history_messages(data),
        )
        logger.info("ai_ask ask_complete elapsed_seconds=%.3f", time.perf_counter() - ask_started_at)
        return jsonify({"answer": answer, "tokens_estimated": tokens}), 200
    except Exception as e:
        if reservation and reservation["charged"]:
            refund_credits(user_id, AI_ASK_CREDIT_COST, "ai_ask_refund", operation_id)
        return jsonify({"error": str(e)}), 500

@bp.route("/estimate_tokens", methods=["POST"])
def estimate_tokens_route():
    user_id, auth_err = require_auth()
    if auth_err: return auth_err
    data = request.get_json(silent=True) or {}
    question = data.get("question")
    if not question:
        return jsonify({"error": "Missing 'question' field"}), 400
    try:
        result = get_token_estimate(question, note_ids=_parse_note_ids(data), user_id=user_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/debug/context", methods=["POST"])
def debug_context():
    user_id, auth_err = require_auth()
    if auth_err: return auth_err
    data = request.get_json(silent=True) or {}
    question = data.get("question")
    if not question:
        return jsonify({"error": "Missing 'question'"}), 400
    result = build_context(question, note_ids=_parse_note_ids(data), user_id=user_id)
    return jsonify({
        "question": question,
        "context": result["context"],
        "context_tokens": result["tokens"],
        "best_faiss_score": result["best_score"],
        "dropped_notes": result["dropped_notes"]
    }), 200
