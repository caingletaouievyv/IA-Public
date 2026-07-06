# IA/backend/app/ai/engine.py
"""
AI execution engine. Single entry point for all AI calls. Default provider: Groq (see docs/ia.example.md).
Supports conversation history: when history_messages are provided, sends chat format so the model remembers the thread.
"""

import logging
from app.ai.client import call_ai
from app.memory.manager import build_context
from app.memory.utils import estimate_tokens

logger = logging.getLogger(__name__)


def _build_system_content(context: str, note_titles: list) -> str:
    """Single system block: instructions plus optional note context."""
    if note_titles:
        topic_line = "The following context is from the user's selected notes"
        if len(note_titles) == 1:
            topic_line += f" (topic: {note_titles[0]})."
        else:
            topic_line += f" (topics: {', '.join(note_titles)})."
        topic_line += (
            " Base your answer on this material when relevant. You may add alternatives from general knowledge; "
            "label what is from their notes vs. general knowledge. Keep explanations lazy, simple, and concise."
        )
        return f"You are a helpful assistant.\n{topic_line}\n\nContext:\n{context}"
    return f"You are a helpful assistant. Use context only if relevant.\n\nContext:\n{context}"


def ask(question: str, max_tokens: int = 2000, note_ids: list | None = None, user_id: str = None, history_messages: list | None = None):
    """Answer question with optional note context and conversation history. When history_messages is provided, sends chat format so the model remembers the thread."""
    result = build_context(question, max_tokens, note_ids=note_ids, user_id=user_id)
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
        answer = call_ai(prompt="", question=question, messages=messages)
        full_text = system_content + "\n\n" + "\n\n".join(f"{m['role']}: {m['content']}" for m in messages[1:])
        return answer, estimate_tokens(full_text)
    else:
        prompt = (
            f"{system_content}\n\n"
            f"Question:\n{question}"
        )
        answer = call_ai(prompt, question=question)
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