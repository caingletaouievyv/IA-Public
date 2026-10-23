# IA/backend/app/diagnostics/context.py
"""Request-scoped metadata for content-free AI diagnostic records."""

from contextvars import ContextVar
from dataclasses import dataclass, field

from app.config import AI_MODE, MODEL_PROVIDER, GROQ_MODEL, DEEPSEEK_MODEL, OLLAMA_MODEL

_MODEL_BY_PROVIDER = {
    "groq": GROQ_MODEL,
    "deepseek": DEEPSEEK_MODEL,
    "ollama": OLLAMA_MODEL,
    "openai": "gpt-4o-mini",
}


@dataclass
class DiagnosticContext:
    operation_id: str | None = None
    feature: str | None = None
    memory_status: str | None = None
    note_context_mode: str | None = None
    memory_enabled: bool | None = None
    extra: dict = field(default_factory=dict)


_CONTEXT = ContextVar("diagnostic_context", default=None)


def set_diagnostic_context(context: DiagnosticContext | None) -> None:
    _CONTEXT.set(context)


def get_diagnostic_context() -> DiagnosticContext | None:
    return _CONTEXT.get()


def provider_metadata() -> dict[str, str]:
    provider = MODEL_PROVIDER or "groq"
    return {
        "provider": provider,
        "model": _MODEL_BY_PROVIDER.get(provider, GROQ_MODEL),
        "ai_mode": AI_MODE or "single",
    }


def context_metadata() -> dict:
    """Merge provider config with any active request context."""
    metadata = provider_metadata()
    context = get_diagnostic_context()
    if context is None:
        return metadata
    if context.operation_id:
        metadata["operation_id"] = context.operation_id
    if context.feature:
        metadata["feature"] = context.feature
    if context.memory_status:
        metadata["memory_status"] = context.memory_status
    if context.note_context_mode:
        metadata["note_context_mode"] = context.note_context_mode
    if context.memory_enabled is not None:
        metadata["memory_enabled"] = context.memory_enabled
    metadata.update(context.extra)
    return metadata
