# IA/backend/app/notes/manager.py
# Per-user notes in PostgreSQL. Note JSON files are not read or written.

import os

from app.notes.repository import (
    NoteStoreError,
    delete_note as delete_note_row,
    find_note,
    insert_note,
    list_notes,
    notes_session,
    replace_notes,
    update_note as update_note_row,
)

# Conversation histories stored as notes with this category (same table; excluded from Notes UI meta).
HISTORY_CATEGORY = "_history"
# Flashcard decks (Flashcards UI); legacy saves used category "flashcards".
FLASHCARD_DECK_CATEGORY = "_flashcards"
LEGACY_FLASHCARD_DECK_CATEGORY = "flashcards"

# Legacy note JSON paths are unused. Pending Ask confirmations are PostgreSQL rows.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
NOTES_FILE = os.path.join(DATA_DIR, "notes.json")


def is_flashcard_deck_category(category) -> bool:
    value = (category or "").strip()
    return value in (FLASHCARD_DECK_CATEGORY, LEGACY_FLASHCARD_DECK_CATEGORY)


def load_notes(user_id: str):
    """Return this user's notes in append order."""
    with notes_session() as session:
        return list_notes(session, user_id)


def save_notes(notes: list, user_id: str):
    """Replace this user's notes, preserving order and any ids already on the items."""
    with notes_session() as session:
        replace_notes(session, user_id, notes)


def add_note(note_data: dict, user_id: str):
    """Append a note with a new id and timestamps. Return the stored note."""
    with notes_session() as session:
        stored = insert_note(session, user_id, note_data)
    note_data["id"] = stored["id"]
    note_data["created_at"] = stored["created_at"]
    note_data["updated_at"] = stored["updated_at"]
    return stored


def update_note(note_id: str, updated_data: dict, user_id: str):
    """Update title, category, content, or tags. Return the note, or None when it is missing."""
    with notes_session() as session:
        return update_note_row(session, user_id, note_id, updated_data)


def get_notes_list(user_id: str, category=None, tag=None, limit=None):
    """Filter by exact category and exact tag, then keep the first limit items."""
    notes = load_notes(user_id)
    if category:
        notes = [note for note in notes if note.get("category") == category]
    if tag:
        notes = [note for note in notes if tag in (note.get("tags") or [])]
    if limit is not None and limit > 0:
        notes = notes[:limit]
    return notes


def find_note_by_title_category(title: str, category: str, user_id: str):
    """First note with the same stripped title and category, or None."""
    wanted_title = (title or "").strip()
    wanted_category = (category or "").strip()
    for note in load_notes(user_id):
        if (note.get("title") or "").strip() == wanted_title and (note.get("category") or "").strip() == wanted_category:
            return note
    return None


def get_note(note_id: str, user_id: str):
    """Return one owned note, or None."""
    with notes_session() as session:
        return find_note(session, user_id, note_id)


def delete_note(note_id: str, user_id: str) -> bool:
    """Remove one owned note. Return False when it is missing."""
    with notes_session() as session:
        return delete_note_row(session, user_id, note_id)


def get_categories(user_id: str):
    """Sorted categories, excluding history and flashcard decks."""
    categories = set()
    for note in load_notes(user_id):
        category = str(note.get("category") or "").strip()
        if category and category != HISTORY_CATEGORY and not is_flashcard_deck_category(category):
            categories.add(category)
    return sorted(categories)


def get_tags(user_id: str):
    """Sorted distinct tags from this user's notes."""
    tags = set()
    for note in load_notes(user_id):
        for tag in note.get("tags") or []:
            if (tag or "").strip():
                tags.add(str(tag).strip())
    return sorted(tags)


__all__ = [
    "DATA_DIR",
    "FLASHCARD_DECK_CATEGORY",
    "HISTORY_CATEGORY",
    "LEGACY_FLASHCARD_DECK_CATEGORY",
    "NOTES_FILE",
    "NoteStoreError",
    "add_note",
    "delete_note",
    "find_note_by_title_category",
    "get_categories",
    "get_note",
    "get_notes_list",
    "get_tags",
    "is_flashcard_deck_category",
    "load_notes",
    "save_notes",
    "update_note",
]
