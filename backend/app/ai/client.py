# IA/backend/app/ai/client.py
import json
import logging
import math
import time
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests
from requests.exceptions import JSONDecodeError, RequestException, Timeout

from app.config import (
    AI_KEY,
    AI_ENSEMBLE_PROVIDERS,
    AI_MODE,
    DEEPSEEK_ENDPOINT,
    DEEPSEEK_MODEL,
    GROQ_ENDPOINT,
    GROQ_MODEL,
    MODEL_PROVIDER,
    OLLAMA_ENDPOINT,
    OLLAMA_MODEL,
)

logger = logging.getLogger(__name__)
# provider -> model, endpoint, use_auth. Primary: groq (see docs/ia.md).
MODEL_MAP = {
    "groq": {"model": GROQ_MODEL, "endpoint": GROQ_ENDPOINT, "auth": True},
    "deepseek": {"model": DEEPSEEK_MODEL, "endpoint": DEEPSEEK_ENDPOINT, "auth": True},
    "ollama": {"model": OLLAMA_MODEL, "endpoint": OLLAMA_ENDPOINT, "auth": False},
    "openai": {"model": "gpt-4o-mini", "endpoint": "https://api.openai.com/v1/chat/completions", "auth": True},
}
_FLASHCARD_PROVIDER_TIMEOUT_SECONDS = 60
# Generation repairs and splits share this budget. Rate-limit cooldown posts do not.
FLASHCARD_PROVIDER_CALL_BUDGET_PER_BATCH = 8


class FlashcardProviderCallBudget:
    """Tracks shared provider HTTP calls for one original deck batch."""

    def __init__(self, limit: int = FLASHCARD_PROVIDER_CALL_BUDGET_PER_BATCH):
        self.limit = limit
        self.used = 0

    def try_consume(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def exhausted(self) -> bool:
        return self.used >= self.limit


class AIProviderError(RuntimeError):
    """Raised when a configured AI provider request fails."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "provider_error",
        status_code: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.provider = provider
        self.model = model
        self.retry_after = retry_after


def _whole_retry_seconds(value: float) -> int | None:
    """Convert a finite delay to whole seconds. Unusable numbers return None."""
    if not math.isfinite(value):
        return None
    try:
        seconds = math.ceil(value)
    except (OverflowError, ValueError):
        return None
    if isinstance(seconds, float):
        if not math.isfinite(seconds):
            return None
        try:
            seconds = int(seconds)
        except (OverflowError, ValueError):
            return None
    if seconds < 0:
        return 0
    return seconds


def parse_retry_after_seconds(header: str | None, *, now: float | None = None) -> int | None:
    """Return Retry-After as whole seconds, or None when the header is unusable."""
    if header is None:
        return None
    text = str(header).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except (ValueError, OverflowError):
        numeric = None
    else:
        return _whole_retry_seconds(numeric)
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError, IndexError, OSError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    current = time.time() if now is None else now
    try:
        delta = parsed.timestamp() - current
    except (OverflowError, OSError, ValueError):
        return None
    return _whole_retry_seconds(delta)


def _groq_error_block(response: requests.Response | None) -> dict:
    if response is None:
        return {}
    try:
        payload = response.json()
    except (JSONDecodeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    error_block = payload.get("error")
    return error_block if isinstance(error_block, dict) else {}


def _groq_error_code(response: requests.Response | None) -> str:
    error_block = _groq_error_block(response)
    code = error_block.get("code")
    return str(code).strip() if code else ""


def _failed_generation_length(response: requests.Response | None) -> int:
    error_block = _groq_error_block(response)
    failed_generation = error_block.get("failed_generation")
    if isinstance(failed_generation, str):
        return len(failed_generation)
    return 0


def _safe_error_snippet(response: requests.Response | None) -> str:
    if response is None:
        return ""
    try:
        payload = response.json()
    except (JSONDecodeError, ValueError):
        text = (response.text or "").strip()
        return text[:200]
    if not isinstance(payload, dict):
        return str(payload)[:200]
    error_block = payload.get("error")
    if isinstance(error_block, dict):
        parts = [error_block.get("code"), error_block.get("type"), error_block.get("message")]
        message = " ".join(str(part) for part in parts if part)
        return message[:200]
    if error_block:
        return str(error_block)[:200]
    return str(payload)[:200]


def _log_flashcard_provider_failure(
    *,
    provider: str,
    model: str,
    category: str,
    batch_index: int | None,
    batch_size: int,
    operation_id: str | None,
    status_code: int | None = None,
    error_snippet: str = "",
    retry_after: str | None = None,
    error_type: str | None = None,
    error_code: str = "",
    failed_generation_len: int = 0,
    attempt: int | None = None,
    budget_limit: int | None = None,
    budget_used: int | None = None,
) -> None:
    logger.warning(
        "flashcard_provider_failure provider=%s model=%s category=%s batch=%s batch_size=%s "
        "operation_id=%s status_code=%s retry_after=%s error_type=%s error_code=%s "
        "failed_generation_len=%s attempt=%s budget_limit=%s budget_used=%s error_snippet=%s",
        provider,
        model,
        category,
        batch_index,
        batch_size,
        operation_id or "",
        status_code if status_code is not None else "",
        retry_after or "",
        error_type or "",
        error_code,
        failed_generation_len,
        attempt if attempt is not None else "",
        budget_limit if budget_limit is not None else "",
        budget_used if budget_used is not None else "",
        error_snippet,
    )


def _log_flashcard_provider_budget_exhausted(
    *,
    batch_index: int | None,
    batch_size: int,
    operation_id: str | None,
    budget: FlashcardProviderCallBudget,
) -> None:
    logger.warning(
        "flashcard_provider_budget_exhausted batch=%s batch_size=%s operation_id=%s budget=%s used=%s",
        batch_index,
        batch_size,
        operation_id or "",
        budget.limit,
        budget.used,
    )


def _consume_flashcard_provider_budget(
    budget: FlashcardProviderCallBudget | None,
    *,
    provider: str,
    model: str,
    batch_index: int | None,
    batch_size: int,
    operation_id: str | None,
    attempt: int | None,
) -> None:
    if budget is None:
        return
    if budget.try_consume():
        return
    _log_flashcard_provider_budget_exhausted(
        batch_index=batch_index,
        batch_size=batch_size,
        operation_id=operation_id,
        budget=budget,
    )
    _log_flashcard_provider_failure(
        provider=provider,
        model=model,
        category="provider_budget_exhausted",
        batch_index=batch_index,
        batch_size=batch_size,
        operation_id=operation_id,
        attempt=attempt,
        budget_limit=budget.limit,
        budget_used=budget.used,
    )
    raise AIProviderError(
        "Flashcard provider call budget exhausted.",
        category="provider_budget_exhausted",
        provider=provider,
        model=model,
    )


def _flashcard_response_format(batch_size: int, *, use_json_schema: bool) -> dict:
    if use_json_schema:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "flashcard_batch",
                "description": "Batch of flashcards with question and answer pairs.",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "cards": {
                            "type": "array",
                            "minItems": batch_size,
                            "maxItems": batch_size,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "question": {"type": "string"},
                                    "answer": {"type": "string"},
                                },
                                "required": ["question", "answer"],
                            },
                        }
                    },
                    "required": ["cards"],
                },
            },
        }
    return {"type": "json_object"}


def call_single(
    prompt: str | None = None,
    messages: list | None = None,
    provider: str = None,
    *,
    max_tokens: int | None = None,
    response_format: dict | None = None,
    timeout: int = 60,
) -> str:
    """Call one provider. Use messages (chat format) if provided; else single user message from prompt."""
    config = MODEL_MAP.get(provider or MODEL_PROVIDER, MODEL_MAP["groq"])
    headers = {"Content-Type": "application/json"}
    if config.get("auth", True) and AI_KEY:
        headers["Authorization"] = f"Bearer {AI_KEY}"
    if messages:
        payload = {"model": config["model"], "messages": messages}
    else:
        payload = {"model": config["model"], "messages": [{"role": "user", "content": prompt or ""}]}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if response_format is not None:
        payload["response_format"] = response_format
    try:
        response = requests.post(config["endpoint"], headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
    except RequestException as error:
        logger.warning(
            "ai_provider_request_failed provider=%s error_type=%s",
            provider or MODEL_PROVIDER,
            type(error).__name__,
        )
        raise AIProviderError(f"{provider} request failed") from error
    result = response.json()
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")


def call_flashcard_batch(
    messages: list,
    batch_size: int,
    batch_index: int | None = None,
    operation_id: str | None = None,
    attempt: int | None = None,
    *,
    use_json_schema: bool | None = None,
    provider_budget: FlashcardProviderCallBudget | None = None,
    external_budget_charge: bool = False,
) -> str:
    """Flashcard-only provider call with bounded output, JSON mode, and safe diagnostics.

    One HTTP post. HTTP 429 is returned to the caller with retry_after seconds;
    cooldown waits are applied by flashcard generation, not here.
    """
    provider = MODEL_PROVIDER
    config = MODEL_MAP.get(provider, MODEL_MAP["groq"])
    model = config["model"]
    endpoint = config["endpoint"]
    max_tokens = min(8000, max(900, batch_size * 400))
    headers = {"Content-Type": "application/json"}
    if config.get("auth", True) and AI_KEY:
        headers["Authorization"] = f"Bearer {AI_KEY}"
    schema_enabled = True if use_json_schema is None else use_json_schema
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "response_format": _flashcard_response_format(batch_size, use_json_schema=schema_enabled),
    }

    def post_once() -> requests.Response:
        if not external_budget_charge:
            _consume_flashcard_provider_budget(
                provider_budget,
                provider=provider,
                model=model,
                batch_index=batch_index,
                batch_size=batch_size,
                operation_id=operation_id,
                attempt=attempt,
            )
        return requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=_FLASHCARD_PROVIDER_TIMEOUT_SECONDS,
        )

    try:
        response = post_once()
    except AIProviderError:
        raise
    except Timeout as error:
        _log_flashcard_provider_failure(
            provider=provider,
            model=model,
            category="timeout",
            batch_index=batch_index,
            batch_size=batch_size,
            operation_id=operation_id,
            error_type=type(error).__name__,
            attempt=attempt,
            budget_limit=provider_budget.limit if provider_budget else None,
            budget_used=provider_budget.used if provider_budget else None,
        )
        raise AIProviderError(
            "Flashcard provider request timed out.",
            category="timeout",
            status_code=None,
            provider=provider,
            model=model,
        ) from error
    except RequestException as error:
        _log_flashcard_provider_failure(
            provider=provider,
            model=model,
            category="transport_error",
            batch_index=batch_index,
            batch_size=batch_size,
            operation_id=operation_id,
            error_type=type(error).__name__,
            attempt=attempt,
        )
        raise AIProviderError(
            "Flashcard provider request failed.",
            category="transport_error",
            provider=provider,
            model=model,
        ) from error

    error_code = _groq_error_code(response)
    failed_generation_len = _failed_generation_length(response)
    retry_after_header = response.headers.get("Retry-After") if response.status_code == 429 else None
    parsed_retry_after = parse_retry_after_seconds(retry_after_header) if response.status_code == 429 else None
    if response.status_code == 429:
        category = "rate_limit"
    elif error_code == "json_validate_failed":
        category = "json_validate_failed"
    elif response.status_code >= 500:
        category = "server_error"
    elif response.status_code >= 400:
        category = "http_error"
    else:
        category = "provider_error"

    if not response.ok:
        _log_flashcard_provider_failure(
            provider=provider,
            model=model,
            category=category,
            batch_index=batch_index,
            batch_size=batch_size,
            operation_id=operation_id,
            status_code=response.status_code,
            error_snippet=_safe_error_snippet(response),
            retry_after=retry_after_header,
            error_code=error_code,
            failed_generation_len=failed_generation_len,
            attempt=attempt,
            budget_limit=provider_budget.limit if provider_budget else None,
            budget_used=provider_budget.used if provider_budget else None,
        )
        raise AIProviderError(
            "Flashcard provider request failed.",
            category=category,
            status_code=response.status_code,
            provider=provider,
            model=model,
            retry_after=parsed_retry_after,
        )

    try:
        result = response.json()
    except (JSONDecodeError, ValueError) as error:
        _log_flashcard_provider_failure(
            provider=provider,
            model=model,
            category="response_parse_error",
            batch_index=batch_index,
            batch_size=batch_size,
            operation_id=operation_id,
            status_code=response.status_code,
            error_snippet=_safe_error_snippet(response),
            error_type=type(error).__name__,
            attempt=attempt,
        )
        raise AIProviderError(
            "Flashcard provider returned invalid JSON.",
            category="response_parse_error",
            status_code=response.status_code,
            provider=provider,
            model=model,
        ) from error

    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        _log_flashcard_provider_failure(
            provider=provider,
            model=model,
            category="empty_response",
            batch_index=batch_index,
            batch_size=batch_size,
            operation_id=operation_id,
            status_code=response.status_code,
            attempt=attempt,
        )
        raise AIProviderError(
            "Flashcard provider returned an empty response.",
            category="empty_response",
            status_code=response.status_code,
            provider=provider,
            model=model,
        )
    return content


def judge_answers(question: str, answers: list) -> str:
    """Pick best answer by relevance + length + clarity (fewer ?)."""
    scored = []
    for ans in answers:
        if "failed" in ans.lower():
            scored.append((-1, ans))
            continue
        relevance = sum(word in ans.lower() for word in question.lower().split())
        length_score = min(len(ans) / 50, 3)
        clarity_penalty = ans.count("?") * -0.3
        scored.append((relevance + length_score + clarity_penalty, ans))
    best = max(scored, key=lambda x: x[0])
    return best[1] if best else answers[0]


def call_ai(prompt: str, question: str | None = None, messages: list | None = None) -> str:
    """single → one provider; ensemble → all listed providers combined; judge → best of listed (project.md Phase 4).
    If messages (chat format) is provided, use that for the API call; else use prompt as single user message.
    question used for judge relevance when provided."""
    try:
        if AI_MODE == "single":
            return call_single(prompt=prompt, messages=messages, provider=MODEL_PROVIDER)
        providers = [p for p in AI_ENSEMBLE_PROVIDERS if p in MODEL_MAP]
        if not providers:
            providers = ["groq"]
        answers = [call_single(prompt=prompt, messages=messages, provider=p) for p in providers]
        if AI_MODE == "judge":
            return judge_answers(question or prompt, answers)
        return "\n\n---\n\n".join(answers)
    except AIProviderError:
        raise
    except Exception as error:
        logger.error("ai_client_unexpected_error error_type=%s", type(error).__name__)
        raise RuntimeError(f"AI request error: {str(error)}")
