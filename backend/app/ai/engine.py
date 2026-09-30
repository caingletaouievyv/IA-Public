# IA/backend/app/ai/engine.py
"""
AI execution engine. Single entry point for all AI calls. Default provider: Groq (see docs/ia.md).
Supports conversation history: when history_messages are provided, sends chat format so the model remembers the thread.
"""

import logging
import time
from app.ai.client import call_ai
from app.memory.manager import build_context
from app.memory.utils import estimate_tokens

logger = logging.getLogger(__name__)


def _build_system_content(context: str, note_titles: list) -> str:
    """Single system block: instructions plus optional note context."""
    if context.strip():
        topic_line = "The following context is from the user's notes"
        if note_titles and len(note_titles) == 1:
            topic_line += f" (topic: {note_titles[0]})."
        elif note_titles:
            topic_line += f" (topics: {', '.join(note_titles)})."
        else:
            topic_line += "."
        topic_line += (
            " Use this material as the primary source. Prefer short, natural, readable answers. "
            "When the user asks about notes, answer directly from the notes and keep it conversational. "
            "Use simple bullets when listing relevant notes. Mention the note title and a brief description of what it contains. "
            "Do not use tables unless the user explicitly asks for one. Do not add headings like 'Bottom line', 'Summary', or 'General knowledge' "
            "when the answer is based on the user's notes. Do not repeat the user's question. Do not force markdown formatting when plain prose is better. "
            "Keep explanations brief, clear, and grounded in the provided note content."
        )
        return f"You are a helpful assistant.\n{topic_line}\n\nContext:\n{context}"
    return (
        "You are a helpful assistant. Use context only if relevant. Keep answers short, natural, and conversational. "
        "Prefer simple prose or bullets over tables or heavy markdown. Do not add forced summary sections unless the user asks for one. "
        "No note context is available. Do not mention or imply that your response came from the user's notes, and do not add labels such as '[From your notes]'. "
        "Respond normally and conversationally, including to short messages.\n\nContext:\n{context}"
    ).format(context=context)


def ask(question: str, max_tokens: int = 2000, note_ids: list | None = None, user_id: str = None, history_messages: list | None = None, note_context_mode: str = "automatic"):
    """Answer question with optional note context and conversation history. When history_messages is provided, sends chat format so the model remembers the thread."""
    context_started_at = time.perf_counter()
    logger.info("ai_ask context_start")
    result = build_context(question, max_tokens, note_ids=note_ids, user_id=user_id, note_context_mode=note_context_mode)
    logger.info("ai_ask context_complete elapsed_seconds=%.3f", time.perf_counter() - context_started_at)
    context = result.get("context", "") if result else ""
    note_titles = result.get("note_titles") or []
    system_content = _build_system_content(context, note_titles)

    if history_messages:
        # Chat format: system + previous turns + current question (so model remembers e.g. "your name is Brian").
        # Cap history to last N messages to stay within context limits (best practice).
        max_history = 30
        if len(history_messages) > max_history:
            history_messages = history_messages[-max_history:]
        messages = [{"role": "system", "content": system_content}]
        for m in history_messages:
            role = (m.get("role") or "user").lower()
            if role not in ("user", "assistant", "system"):
                role = "user"
            content = m.get("content") or ""
            if role == "system":
                continue
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": question})
        provider_started_at = time.perf_counter()
        logger.info("ai_ask provider_start")
        answer = call_ai(prompt="", question=question, messages=messages)
        logger.info("ai_ask provider_complete elapsed_seconds=%.3f", time.perf_counter() - provider_started_at)
        full_text = system_content + "\n\n" + "\n\n".join(f"{m['role']}: {m['content']}" for m in messages[1:])
        return answer, estimate_tokens(full_text)
    else:
        prompt = (
            f"{system_content}\n\n"
            f"Question:\n{question}"
        )
        provider_started_at = time.perf_counter()
        logger.info("ai_ask provider_start")
        answer = call_ai(prompt, question=question)
        logger.info("ai_ask provider_complete elapsed_seconds=%.3f", time.perf_counter() - provider_started_at)
        return answer, estimate_tokens(prompt)


def get_token_estimate(question: str, note_ids: list | None = None, user_id: str = None):
    """Build context for question (user's notes, optional note_ids subset); return estimated_tokens and context_tokens."""
    result = build_context(question, note_ids=note_ids, user_id=user_id)
    prompt = (
        "You are a helpful assistant with access to the user's notes.\n\n"
        f"Context:\n{result['context']}\n\nQuestion:\n{question}"
    )
    return {
        "estimated_tokens": estimate_tokens(prompt),
        "context_tokens": result["tokens"],
    }


def summarize_for_note(raw_text: str) -> str:
    """Summarize extracted text for a note: lazy, simple, concise, full details. Used by notes-from-images."""
    if not (raw_text or "").strip():
        return ""
    prompt = (
        "Summarize the following text for a study note. Keep it lazy, simple, and concise but include all important details. "
        "Output only the summary, no preamble.\n\n"
        f"{raw_text[:12000]}"
    )
    return call_ai(prompt)