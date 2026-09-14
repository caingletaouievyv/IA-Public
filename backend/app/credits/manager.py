# IA/backend/app/credits/manager.py

import datetime
import json
import os
import threading
import uuid

from app.config import AI_CREDIT_INITIAL_BALANCE

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
_FILE_LOCK = threading.RLock()


class InsufficientCreditsError(Exception):
    """Raised when a user cannot reserve the requested AI Credits."""

    def __init__(self, balance: int, required: int):
        self.balance = balance
        self.required = required
        super().__init__("Insufficient AI Credits")


def _credits_path(user_id: str) -> str:
    return os.path.join(DATA_DIR, f"credits_{user_id}.json")


def _timestamp() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _ledger_entry(user_id: str, amount: int, reason: str, operation_id: str | None = None, related_entry_id: str | None = None) -> dict:
    entry = {
        "entry_id": str(uuid.uuid4()),
        "user_id": user_id,
        "amount": amount,
        "reason": reason,
        "created_at": _timestamp(),
    }
    if operation_id:
        entry["operation_id"] = operation_id
    if related_entry_id:
        entry["related_entry_id"] = related_entry_id
    return entry


def _save_account(account: dict, user_id: str) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = _credits_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(account, f, indent=2)


def _load_account(user_id: str) -> dict:
    path = _credits_path(user_id)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                account = json.load(f)
            account.setdefault("user_id", user_id)
            account.setdefault("credit_balance", 0)
            account.setdefault("ledger", [])
            return account
        except (OSError, ValueError, TypeError):
            pass

    initial_balance = max(0, int(AI_CREDIT_INITIAL_BALANCE))
    return {
        "user_id": user_id,
        "credit_balance": initial_balance,
        "ledger": [_ledger_entry(user_id, initial_balance, "initial_balance")],
    }


def _get_account_locked(user_id: str) -> dict:
    account = _load_account(user_id)
    if not os.path.exists(_credits_path(user_id)):
        _save_account(account, user_id)
    return account


def get_credit_account(user_id: str) -> dict:
    """Return the user's credit balance and ledger, creating initial state lazily."""
    if not user_id:
        raise ValueError("user_id required")
    with _FILE_LOCK:
        return _get_account_locked(user_id)


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
    with _FILE_LOCK:
        account = _get_account_locked(user_id)
        for entry in account["ledger"]:
            if entry.get("operation_id") != operation_id:
                continue
            if entry.get("amount") == amount and entry.get("reason") == reason and not entry.get("related_entry_id"):
                return account
            raise ValueError("operation_id already used for a different grant")
        account["credit_balance"] += amount
        account["ledger"].append(_ledger_entry(user_id, amount, reason, operation_id))
        _save_account(account, user_id)
        return account


def reserve_credits(user_id: str, amount: int, reason: str, operation_id: str) -> dict:
    """Reserve credits once for an operation and record the debit in the ledger."""
    if not user_id:
        raise ValueError("user_id required")
    if amount <= 0:
        raise ValueError("amount must be positive")
    if not operation_id:
        raise ValueError("operation_id required")
    with _FILE_LOCK:
        account = _get_account_locked(user_id)
        existing_debit = None
        for entry in reversed(account["ledger"]):
            if entry.get("operation_id") != operation_id or entry.get("amount") != -amount:
                continue
            if not any(item.get("related_entry_id") == entry.get("entry_id") for item in account["ledger"]):
                existing_debit = entry
                break
        if existing_debit and not any(
            entry.get("related_entry_id") == existing_debit.get("entry_id")
            for entry in account["ledger"]
        ):
            return {"account": account, "charged": False}
        if account["credit_balance"] < amount:
            raise InsufficientCreditsError(account["credit_balance"], amount)
        account["credit_balance"] -= amount
        account["ledger"].append(_ledger_entry(user_id, -amount, reason, operation_id))
        _save_account(account, user_id)
        return {"account": account, "charged": True}


def refund_credits(user_id: str, amount: int, reason: str, operation_id: str) -> dict:
    """Restore a failed reservation once and record the refund in the ledger."""
    if not user_id:
        raise ValueError("user_id required")
    if amount <= 0:
        raise ValueError("amount must be positive")
    if not operation_id:
        raise ValueError("operation_id required")
    with _FILE_LOCK:
        account = _get_account_locked(user_id)
        debit = None
        for entry in reversed(account["ledger"]):
            if entry.get("operation_id") != operation_id or entry.get("amount") != -amount:
                continue
            if not any(item.get("related_entry_id") == entry.get("entry_id") for item in account["ledger"]):
                debit = entry
                break
        if not debit:
            return account
        if any(entry.get("related_entry_id") == debit.get("entry_id") for entry in account["ledger"]):
            return account
        account["credit_balance"] += amount
        account["ledger"].append(_ledger_entry(user_id, amount, reason, operation_id, debit.get("entry_id")))
        _save_account(account, user_id)
        return account