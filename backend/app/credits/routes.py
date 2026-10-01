# IA/backend/app/credits/routes.py

from flask import Blueprint, jsonify, request

from app.common.auth import require_auth
from app.config import APP_ENV, REWARDED_AD_CREDIT_AMOUNT
from app.credits.manager import grant_credits, get_credit_account

bp = Blueprint("credits", __name__)


def _has_reward(account: dict, reward_id: str) -> bool:
    return any(
        entry.get("operation_id") == reward_id
        and entry.get("amount") == REWARDED_AD_CREDIT_AMOUNT
        and entry.get("reason") == "rewarded_ad"
        and not entry.get("related_entry_id")
        for entry in account.get("ledger", [])
    )


@bp.route("/rewarded-ad", methods=["POST"])
def rewarded_ad():
    """Unverified reward grants are available only in explicit development/test mode."""
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    if APP_ENV not in {"development", "test"}:
        return jsonify({"error": "rewarded_ad_disabled"}), 404

    data = request.get_json(silent=True) or {}
    reward_id = data.get("reward_id")
    if not isinstance(reward_id, str) or not reward_id.strip():
        return jsonify({"error": "reward_id required"}), 400
    reward_id = reward_id.strip()

    was_already_granted = _has_reward(get_credit_account(user_id), reward_id)
    try:
        account = grant_credits(
            user_id,
            REWARDED_AD_CREDIT_AMOUNT,
            "rewarded_ad",
            reward_id,
        )
    except ValueError as exc:
        return jsonify({"error": "reward_id conflict", "message": str(exc)}), 409

    return jsonify({
        "credit_balance": account["credit_balance"],
        "credits_granted": REWARDED_AD_CREDIT_AMOUNT,
        "reward_id": reward_id,
        "idempotent": was_already_granted,
    }), 200