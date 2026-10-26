# IA/backend/app/memories/remember_command.py
# Parse and execute the Ask !remember command without invoking the AI provider.

import re

from app.memories import manager

REMEMBER_COMMAND = re.compile(r"^\s*!remember(?:\s+(?P<text>[\s\S]*))?\s*$", re.IGNORECASE)


def parse_remember_command(question: str) -> str | None:
    """Return remembered text when question is a !remember command; otherwise None."""
    if not isinstance(question, str):
        return None
    match = REMEMBER_COMMAND.match(question)
    if not match:
        return None
    return match.group("text") or ""


def execute_remember_command(user_id: str, text: str, settings: dict) -> dict:
    """Validate settings gates and persist text through the Memory store."""
    if settings.get("remember_command_enabled") is False:
        raise ValueError("Remember command is disabled")
    if settings.get("memory_enabled") is not True:
        raise ValueError("Memory is disabled. Turn on Memory before using !remember.")
    if not (text or "").strip():
        raise ValueError("Provide text after !remember.")
    return manager.save_remember_command(user_id, text)
