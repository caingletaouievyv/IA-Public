# IA/backend/scripts/seed_user.py
# Seed user testuser/password123 and add sample notes (all fields filled). Run from backend: python -m scripts.seed_user

import os
import sys
from pathlib import Path

# Load .env from repo root
root = Path(__file__).resolve().parents[2]
dotenv = root / ".env"
if dotenv.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv)

from app.auth.manager import find_user_by_username, create_user
from app.notes.manager import load_notes, add_note

SEED_USERNAME = "testuser"
SEED_PASSWORD = "password123"

SEED_NOTES = [
    {
        "title": "FAISS and semantic search",
        "category": "DevNotes",
        "content": "We use FAISS for vector similarity over note embeddings. Intent classifier decides lookup vs exploratory; different thresholds apply. Context is built from top-k matches, deduplicated and summarized to fit MAX_CONTEXT_TOKENS.",
        "tags": ["memory", "faiss", "ai"],
    },
    {
        "title": "Groq free tier",
        "category": "Setup",
        "content": "Groq is the primary LLM: free, no card, deploy-friendly. Set AI_KEY in .env. Console at console.groq.com. Optional GROQ_ENDPOINT and GROQ_MODEL. May 429 under burst; reduce concurrency or add delay.",
        "tags": ["groq", "llm", "free-tier"],
    },
    {
        "title": "Notes from images",
        "category": "Features",
        "content": "POST /notes/from-images: multipart with title, category, files. Backend runs OCR (Tesseract), then AI summarizes the text. Same title+category appends content to one note. Requires Tesseract on the server.",
        "tags": ["ocr", "images", "notes"],
    },
    {
        "title": "Login auth",
        "category": "Auth",
        "content": "No API secret in UI. POST /auth/register and /auth/login return a JWT. Bearer token for /notes, /ai, /settings. user_id from JWT sub; notes stored in notes_{user_id}.json.",
        "tags": ["auth", "jwt", "login"],
    },
    {
        "title": "Ask with selected notes",
        "category": "Features",
        "content": "POST /ai/ask accepts optional note_ids. When set, context is built only from those notes (temp FAISS subset). Use case: make a reviewer from chosen notes. Frontend: Load notes, select checkboxes, then ask.",
        "tags": ["ask", "context", "notes"],
    },
]


def main():
    user = find_user_by_username(SEED_USERNAME)
    if not user:
        created = create_user(SEED_USERNAME, SEED_PASSWORD)
        if not created:
            print("Failed to create user", SEED_USERNAME, file=sys.stderr)
            sys.exit(1)
        user_id = created["user_id"]
        print(f"Created user {SEED_USERNAME} (user_id={user_id})")
    else:
        user_id = user["user_id"]
        print(f"User {SEED_USERNAME} already exists (user_id={user_id})")

    existing = load_notes(user_id)
    count_before = len(existing)
    for note in SEED_NOTES:
        add_note(note.copy(), user_id)
    count_after = len(load_notes(user_id))
    added = count_after - count_before
    print(f"Notes: {count_before} -> {count_after} (+{added} seed notes)")
    print("Done. Sign in with", SEED_USERNAME, "/", SEED_PASSWORD)


if __name__ == "__main__":
    main()
