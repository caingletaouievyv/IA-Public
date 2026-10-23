# IA/backend/app/auth/roles.py
# Persisted role string constants for IA accounts.

ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLE_MAIN_ADMIN = "main_admin"

KNOWN_ROLES = frozenset({ROLE_USER, ROLE_ADMIN, ROLE_MAIN_ADMIN})


def normalize_role(value: str | None) -> str:
    """Return a known role string; unknown values stay as-is for legacy env matching."""
    cleaned = (value or ROLE_USER).strip()
    if cleaned in KNOWN_ROLES:
        return cleaned
    return cleaned or ROLE_USER
