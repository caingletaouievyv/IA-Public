# IA/backend/app/ai/client.py
import requests
import logging
from app.config import (
    AI_KEY,
    MODEL_PROVIDER,
    AI_MODE,
    AI_ENSEMBLE_PROVIDERS,
    DEEPSEEK_ENDPOINT,
    DEEPSEEK_MODEL,
    GROQ_ENDPOINT,
    GROQ_MODEL,
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


class AIProviderError(RuntimeError):
    """Raised when a configured AI provider request fails."""


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
    except requests.RequestException as error:
        logger.warning(
            "ai_provider_request_failed provider=%s error_type=%s",
            provider or MODEL_PROVIDER,
            type(error).__name__,
        )
        raise AIProviderError(f"{provider} request failed") from error
    result = response.json()
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")


def call_flashcard_batch(messages: list, batch_size: int) -> str:
    """Flashcard-only provider call with bounded output and JSON mode."""
    max_tokens = min(8000, max(800, batch_size * 350))
    return call_single(
        messages=messages,
        provider=MODEL_PROVIDER,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
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
