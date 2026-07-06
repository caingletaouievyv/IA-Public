# IA/backend/app/notes/manager.py
# CRUD for notes: per-user files (notes_{user_id}.json). UUID + ISO8601. Migrate legacy notes.json on first load (project.md Phase 8).

import datetime
import json
import os
import shutil
import uuid

# Conversation histories stored as notes with this category (same table; excluded from Notes UI meta).
HISTORY_CATEGORY = "_history"

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BACKEND_DIR, "data")
NOTES_FILE = os.path.join(DATA_DIR, "notes.json")

def _notes_path(user_id: str):
    return os.path.join(DATA_DIR, f"notes_{user_id}.json")

def _migrate_legacy(user_id: str):
    """If legacy notes.json exists and notes_{user_id}.json does not, copy once."""
    dest = _notes_path(user_id)
    if os.path.exists(dest) or not os.path.exists(NOTES_FILE):
        return
    try:
        shutil.copy2(NOTES_FILE, dest)
    except Exception:
        pass

def load_notes(user_id: str):
    """Return list of notes for user; [] if file missing. Migrates legacy notes.json once."""
    _migrate_legacy(user_id)
    path = _notes_path(user_id)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_notes(notes: list, user_id: str):
    """Overwrite user's notes file with JSON."""
    path = _notes_path(user_id)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2)

def add_note(note_data: dict, user_id: str):
    """Append note with id, created_at, updated_at; save; return note."""
    notes = load_notes(user_id)
    now = datetime.datetime.utcnow().isoformat() + "Z"
    note_data["id"] = str(uuid.uuid4())
    note_data["created_at"] = now
    note_data["updated_at"] = now
    notes.append(note_data)
    save_notes(notes, user_id)
    return note_data

def update_note(note_id: str, updated_data: dict, user_id: str):
    """Update first matching note by id; set updated_at; save; return note or None."""
    notes = load_notes(user_id)
    for note in notes:
        if note.get("id") == note_id:
            for k, v in updated_data.items():
                note[k] = v
            note["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
            save_notes(notes, user_id)
            return note
    return None

def get_notes_list(user_id: str, category=None, tag=None, limit=None):
    """Load notes for user, filter by category/tag, apply limit."""
    notes = load_notes(user_id)
    if category:
        notes = [n for n in notes if n.get("category") == category]
    if tag:
        notes = [n for n in notes if tag in n.get("tags", [])]
    if limit is not None and limit > 0:
        notes = notes[:limit]
    return notes

def find_note_by_title_category(title: str, category: str, user_id: str):
    """First note with matching title and category, or None. Used for append-on-upload."""
    notes = load_notes(user_id)
    t, c = (title or "").strip(), (category or "").strip()
    for n in notes:
        if (n.get("title") or "").strip() == t and (n.get("category") or "").strip() == c:
            return n
    return None

def get_note(note_id: str, user_id: str):
    """Return note by id for user, or None. Keeps route thin."""
    notes = load_notes(user_id)
    for n in notes:
        if n.get("id") == note_id:
            return n
    return None

def delete_note(note_id: str, user_id: str) -> bool:
    """Remove note by id; save. Return True if removed, False if not found."""
    notes = load_notes(user_id)
    kept = [n for n in notes if n.get("id") != note_id]
    if len(kept) == len(notes):
        return False
    save_notes(kept, user_id)
    return True

def get_categories(user_id: str):
    """Distinct categories from user's notes, sorted. Excludes history category."""
    notes = load_notes(user_id)
    cats = {str(n.get("category") or "").strip() for n in notes if (n.get("category") or "").strip() and (n.get("category") or "").strip() != HISTORY_CATEGORY}
    return sorted(cats)

def get_tags(user_id: str):
    """Distinct tags from user's notes, sorted."""
    notes = load_notes(user_id)
    tags = set()
    for n in notes:
        for t in n.get("tags") or []:
            if (t or "").strip():
                tags.add(str(t).strip())
    return sorted(tags)
