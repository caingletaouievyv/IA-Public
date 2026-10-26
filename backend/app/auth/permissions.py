# IA/backend/app/auth/permissions.py
# Centralized role checks for credits, diagnostics, and future admin actions.

from app.auth.roles import ROLE_ADMIN, ROLE_MAIN_ADMIN, ROLE_USER, normalize_role
from app.config import AI_UNLIMITED_ROLE


def has_unlimited_credits(role: str) -> bool:
    """True when Ask and flashcard generation skip IA credit reservation."""
    normalized = normalize_role(role)
    if normalized in (ROLE_ADMIN, ROLE_MAIN_ADMIN):
        return True
    # Legacy deployments may use AI_UNLIMITED_ROLE as the stored role string.
    return bool(AI_UNLIMITED_ROLE) and normalized == AI_UNLIMITED_ROLE


def can_view_diagnostics(role: str) -> bool:
    """True for operator roles that may read content-free diagnostic events."""
    return has_unlimited_credits(role)


def can_promote_users(role: str) -> bool:
    """True only for the Main Admin role (promote/demote user-management APIs)."""
    return normalize_role(role) == ROLE_MAIN_ADMIN


def can_assign_role(actor_role: str, target_role: str) -> bool:
    """Main Admin may promote users to admin only."""
    if not can_promote_users(actor_role):
        return False
    return normalize_role(target_role) == ROLE_ADMIN
