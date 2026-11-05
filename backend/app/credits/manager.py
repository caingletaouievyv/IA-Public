# IA/backend/app/credits/manager.py
# Credit accounts live in PostgreSQL. Credit JSON files are not read or written.
# Claim, reserve, complete, refund, and release each commit before the next step.
# The AI provider call stays outside those transactions.

import os

from app.config import AI_CREDIT_INITIAL_BALANCE
from app.credits import repository
from app.credits.repository import CreditStoreError, InsufficientCreditsError

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Kept so existing patches still bind. Credit rows do not use this directory.
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
_OPERATION_PENDING_TTL_SECONDS = 300


def _initial_balance() -> int:
    return max(0, int(AI_CREDIT_INITIAL_BALANCE))


def account_exists(user_id: str) -> bool:
    """Return whether a credit row exists. This does not create one."""
    if not user_id:
        return False
    with repository.credits_session() as session:
        return repository.account_row_exists(session, user_id)


def get_credit_account(user_id: str) -> dict:
    """Return the user's credit balance and ledger, creating initial state lazily."""
    if not user_id:
        raise ValueError("user_id required")
    with repository.locked_credits(user_id, _initial_balance()) as session:
        return repository.account_view(session, user_id)


def claim_operation(user_id: str, operation_id: str) -> dict:
    """Claim a user-scoped operation, or return its completed result/current state."""
    if not user_id:
        raise ValueError("user_id required")
    if not operation_id:
        raise ValueError("operation_id required")
    with repository.locked_credits(user_id, _initial_balance()) as session:
        return repository.apply_claim(
            session,
            user_id,
            operation_id,
            _OPERATION_PENDING_TTL_SECONDS,
        )


def complete_operation(user_id: str, operation_id: str, result: dict) -> None:
    """Persist a successful operation result for exact retries by the same user."""
    with repository.locked_credits(user_id, _initial_balance()) as session:
        repository.apply_complete(session, user_id, operation_id, result)


def release_operation(user_id: str, operation_id: str) -> None:
    """Allow a failed or rejected operation to be retried."""
    with repository.locked_credits(user_id, _initial_balance()) as session:
        repository.apply_release(session, user_id, operation_id)


def has_completed_operation(user_id: str, operation_id: str) -> bool:
    """Return True when the user owns a completed operation with this identifier."""
    if not user_id or not operation_id:
        return False
    with repository.locked_credits(user_id, _initial_balance()) as session:
        return repository.operation_completed(session, user_id, operation_id)


def grant_credits(user_id: str, amount: int, reason: str, operation_id: str) -> dict:
    """Grant credits and record the grant idempotently."""
    if not user_id:
        raise ValueError("user_id required")
    if amount <= 0:
        raise ValueError("amount must be positive")
    if not reason:
        raise ValueError("reason required")
    if not operation_id:
        raise ValueError("operation_id required")
    with repository.locked_credits(user_id, _initial_balance()) as session:
        return repository.apply_grant(session, user_id, amount, reason, operation_id)


def reserve_credits(user_id: str, amount: int, reason: str, operation_id: str) -> dict:
    """Reserve credits once for an operation and record the debit in the ledger."""
    if not user_id:
        raise ValueError("user_id required")
    if amount <= 0:
        raise ValueError("amount must be positive")
    if not operation_id:
        raise ValueError("operation_id required")
    with repository.locked_credits(user_id, _initial_balance()) as session:
        return repository.apply_reserve(session, user_id, amount, reason, operation_id)


def refund_credits(user_id: str, amount: int, reason: str, operation_id: str) -> dict:
    """Restore a failed reservation once and record the refund in the ledger."""
    if not user_id:
        raise ValueError("user_id required")
    if amount <= 0:
        raise ValueError("amount must be positive")
    if not operation_id:
        raise ValueError("operation_id required")
    with repository.locked_credits(user_id, _initial_balance()) as session:
        return repository.apply_refund(session, user_id, amount, reason, operation_id)
