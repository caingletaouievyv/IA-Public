# IA/backend/app/ai/client.py
import json
import logging
import time

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
_FLASHCARD_RATE_LIMIT_MAX_RETRIES = 1


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
    ):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.provider = provider
        self.model = model


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
) -> None:
    logger.warning(
        "flashcard_provider_failure provider=%s model=%s category=%s batch=%s batch_size=%s "
        "operation_id=%s status_code=%s retry_after=%s error_type=%s error_snippet=%s",
        provider,
        model,
        category,
        batch_index,
        batch_size,
        operation_id or "",
        status_code if status_code is not None else "",
        retry_after or "",
        error_type or "",
        error_snippet,
    )


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
) -> str:
    """Flashcard-only provider call with bounded output, JSON mode, and safe diagnostics."""
    provider = MODEL_PROVIDER
    config = MODEL_MAP.get(provider, MODEL_MAP["groq"])
    model = config["model"]
    endpoint = config["endpoint"]
    max_tokens = min(8000, max(800, batch_size * 350))
    headers = {"Content-Type": "application/json"}
    if config.get("auth", True) and AI_KEY:
        headers["Authorization"] = f"Bearer {AI_KEY}"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    response = None
    for attempt in range(_FLASHCARD_RATE_LIMIT_MAX_RETRIES + 1):
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=_FLASHCARD_PROVIDER_TIMEOUT_SECONDS,
            )
        except Timeout as error:
            _log_flashcard_provider_failure(
                provider=provider,
                model=model,
                category="timeout",
                batch_index=batch_index,
                batch_size=batch_size,
                operation_id=operation_id,
                error_type=type(error).__name__,
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
            )
            raise AIProviderError(
                "Flashcard provider request failed.",
                category="transport_error",
                provider=provider,
                model=model,
            ) from error

        if response.status_code == 429 and attempt < _FLASHCARD_RATE_LIMIT_MAX_RETRIES:
            retry_after = response.headers.get("Retry-After", "2")
            _log_flashcard_provider_failure(
                provider=provider,
                model=model,
                category="rate_limit",
                batch_index=batch_index,
                batch_size=batch_size,
                operation_id=operation_id,
                status_code=429,
                error_snippet=_safe_error_snippet(response),
                retry_after=retry_after,
            )
            try:
                delay_seconds = min(max(int(retry_after), 1), 5)
            except ValueError:
                delay_seconds = 2
            time.sleep(delay_seconds)
            continue

        if response.status_code == 429:
            category = "rate_limit"
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
                retry_after=response.headers.get("Retry-After"),
            )
            raise AIProviderError(
                "Flashcard provider request failed.",
                category=category,
                status_code=response.status_code,
                provider=provider,
                model=model,
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
            )
            raise AIProviderError(
                "Flashcard provider returned an empty response.",
                category="empty_response",
                status_code=response.status_code,
                provider=provider,
                model=model,
            )
        return content

    raise AIProviderError(
        "Flashcard provider request failed.",
        category="rate_limit",
        status_code=429,
        provider=provider,
        model=model,
    )


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
