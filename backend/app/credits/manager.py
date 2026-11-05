# IA/backend/app/credits/manager.py
# Credit accounts live in PostgreSQL. Credit JSON files are not read or written.
# Claim, reserve, complete, refund, and release each commit before the next step.
# The AI provider call stays outside those transactions.

import os
import time

from app.config import (
    AI_ASK_CREDIT_COST,
    AI_CREDIT_INITIAL_BALANCE,
    FLASHCARD_JOB_IDLE_SECONDS,
    FLASHCARD_JOB_MAX_SECONDS,
)
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


def complete_operation(user_id: str, operation_id: str, result: dict) -> bool:
    """Persist a successful operation result for exact retries by the same user."""
    with repository.locked_credits(user_id, _initial_balance()) as session:
        return repository.apply_complete(session, user_id, operation_id, result)


def release_operation(user_id: str, operation_id: str) -> None:
    """Allow a failed or rejected operation to be retried."""
    with repository.locked_credits(user_id, _initial_balance()) as session:
        repository.apply_release(session, user_id, operation_id)


def update_pending_operation_result(user_id: str, operation_id: str, result: dict) -> bool:
    """Persist in-progress operation metadata while status stays pending."""
    if not user_id or not operation_id:
        raise ValueError("user_id and operation_id required")
    with repository.locked_credits(user_id, _initial_balance()) as session:
        return repository.apply_update_pending_result(session, user_id, operation_id, result)


def fail_flashcard_operation(user_id: str, operation_id: str, error_message: str, refund_amount: int | None = None) -> bool:
    """Refund a flashcard reservation once when pending becomes failed."""
    if not user_id or not operation_id:
        raise ValueError("user_id and operation_id required")
    amount = refund_amount if refund_amount is not None else AI_ASK_CREDIT_COST
    payload = {"kind": "flashcards_generation", "error": error_message}
    with repository.locked_credits(user_id, _initial_balance()) as session:
        if not repository.apply_fail(session, user_id, operation_id, payload):
            return False
        repository.apply_refund(session, user_id, amount, "ai_flashcards_refund", operation_id)
        return True


def _flashcard_job_expired(row) -> bool:
    now = time.time()
    started = float(row.started_at or 0)
    activity = repository.flashcard_last_activity_at(row)
    if now - started >= FLASHCARD_JOB_MAX_SECONDS:
        return True
    return now - activity >= FLASHCARD_JOB_IDLE_SECONDS


def maybe_fail_expired_flashcard_operation(user_id: str, operation_id: str) -> bool:
    """Fail and refund an expired flashcard job inside one credit lock. Returns True when marked failed."""
    if not user_id or not operation_id:
        return False
    amount = AI_ASK_CREDIT_COST
    error_message = "Flashcard generation timed out."
    payload = {"kind": "flashcards_generation", "error": error_message}
    with repository.locked_credits(user_id, _initial_balance()) as session:
        row = repository._operation(session, user_id, operation_id)
        if row is None or row.status != "pending":
            return False
        if not repository._is_flashcard_generation_result(row.result):
            return False
        if not _flashcard_job_expired(row):
            return False
        if not repository.apply_fail(session, user_id, operation_id, payload):
            return False
        repository.apply_refund(session, user_id, amount, "ai_flashcards_refund", operation_id)
        return True


def recover_abandoned_flashcard_operations() -> int:
    """Fail unfinished flashcard jobs after restart. Returns the number recovered."""
    with repository.credits_session() as session:
        pending = repository.list_pending_flashcard_operations(session)
    recovered = 0
    for user_id, operation_id in pending:
        if fail_flashcard_operation(user_id, operation_id, "Flashcard generation was interrupted."):
            recovered += 1
    return recovered


def operation_is_pending(user_id: str, operation_id: str) -> bool:
    operation = get_operation_status(user_id, operation_id)
    return operation is not None and operation.get("status") == "pending"


def operation_is_pending_guarded(user_id: str, operation_id: str) -> bool:
    """Return whether an operation is still pending under the user's credit row lock."""
    if not user_id or not operation_id:
        return False
    with repository.locked_credits(user_id, _initial_balance()) as session:
        row = repository._operation(session, user_id, operation_id)
        return row is not None and row.status == "pending"


def get_operation_status(user_id: str, operation_id: str) -> dict | None:
    if not user_id or not operation_id:
        return None
    with repository.credits_session() as session:
        return repository.read_operation(session, user_id, operation_id)


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
