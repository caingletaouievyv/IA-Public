# IA/backend/app/ai/feature_catalog.py
# Accurate IA capability summary for Ask system context and feature Q&A.

IA_CAPABILITIES = """
Implemented today (authenticated web app):
- Ask: chat with optional Notes context, Conversation history, and Memory (when enabled). Message-prefix !remember saves to Memory when Memory and the remember command are enabled. Ask uses AI Credits per question unless the account has an unlimited role.
- Notes: per-user saved notes with title, category, content, and tags. Ask Notes context (Off, Selected, Automatic) supplies relevant note content for questions; explicit Ask actions can list all notes, create, append or replace content, rename, and delete (delete requires typing the exact title to confirm). Manage supports full editing, images, and PDF import. Conversation histories use category _history; flashcard decks use category flashcards.
- Memory: separate durable facts/preferences (not Notes). Managed in Manage; optional automatic extraction during Ask when Memory is on.
- Manage: CRUD for Notes, Conversations (_history), and Memory.
- Flashcards: generate study decks from selected notes; saved as flashcard notes.
- Settings: per-user preferences (Ask context visibility, Memory, !remember command, AI suggestions, theme).
- Files, GitHub, Drive, and Web in Ask are UI placeholders only — they do not retrieve context or run actions yet.
- AI cannot access other users' data; all note and memory operations are scoped to the signed-in account.
""".strip()


def build_capabilities_system_section() -> str:
    return (
        "You are IA, the assistant inside this application. "
        "Describe only capabilities listed below; do not invent integrations or actions the app lacks.\n\n"
        f"{IA_CAPABILITIES}"
    )


def answer_feature_question(question: str) -> str | None:
    """Deterministic short answers for common capability questions; None if not a feature FAQ."""
    text = (question or "").casefold()
    if not any(token in text for token in ("what can you", "what do you", "features", "capabilities", "what is ia", "help me with")):
        return None
    if "note" in text and "memory" in text:
        return (
            "Notes are your saved documents (title, category, content, tags) in Manage and Ask context. "
            "Memory is separate durable facts the app can retrieve when Memory is on; !remember saves explicitly. "
            "Conversation history is stored as _history notes and is not the same as Memory."
        )
    if "note" in text:
        return (
            "I can help with your Notes: turn on Notes context in Ask to answer from saved content, "
            "list all notes, create, append or replace text, rename, or delete "
            "(delete requires typing the exact title to confirm). "
            "Use Manage for images and PDF import. Tell me clearly what to create or which note to change."
        )
    if "memory" in text or "remember" in text:
        return (
            "Memory stores durable facts separately from Notes. Turn Memory on in Ask or Manage. "
            "Use !remember in Ask to save text when the command is enabled. "
            "I do not save ordinary chat turns as Memory automatically unless Memory extraction applies."
        )
    if "flashcard" in text:
        return "Flashcards builds decks from your notes and saves them as flashcard-category notes. Open Flashcards from Ask → Shortcuts."
    if "file" in text or "github" in text or "drive" in text or "web" in text:
        return "Those Ask sources are placeholders today — they do not load context or perform actions yet."
    return (
        "IA includes Ask (chat), Notes, Conversations, Memory, Flashcards, Manage, and Settings. "
        "I can answer questions and, for Notes, perform supported create/list/update/delete actions "
        "when your request is clear. I cannot access other users' data or features not listed in the app."
    )
