# Seed the first-time demo user and notes. Run from backend: python -m scripts.seed_user

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

SEED_USERNAME = "ayi"
SEED_PASSWORD = "Ayi!23"

SEED_NOTES = [
    {
        "title": "My goals for this month",
        "category": "Personal",
        "content": "I want to build a steadier weekly routine, finish one book, and make time for two short walks each week. I am trying to make progress without packing every day too tightly.",
        "tags": ["goals", "routine", "wellbeing"],
    },
    {
        "title": "Grocery list",
        "category": "Shopping",
        "content": "I need oats, bananas, eggs, spinach, rice, yogurt, coffee, and dish soap. I already have pasta and tomatoes, so I do not need to buy those this time.",
        "tags": ["groceries", "shopping"],
    },
    {
        "title": "Things to remember this week",
        "category": "Reminders",
        "content": "I need to reply to Mum, water the plants on Wednesday, return the library book by Friday, and bring my reusable bottle when I leave home.",
        "tags": ["reminders", "this-week"],
    },
    {
        "title": "Work task for Friday",
        "category": "Work",
        "content": "I need to finish the first draft of the community project update by Friday afternoon. My order is: check the latest figures, write the short summary, add the next steps, then ask a teammate to review it.",
        "tags": ["work", "priority", "friday"],
    },
    {
        "title": "Saturday museum plan",
        "category": "Plans",
        "content": "I am meeting Lea at the city museum on Saturday at 11:00. I want to leave home around 10:15, check the train before I go, and have lunch nearby afterward. I should bring my student card.",
        "tags": ["appointment", "saturday", "museum"],
    },
    {
        "title": "What works for me",
        "category": "Preferences",
        "content": "I prefer simple, budget-friendly meals and plans with a little breathing room. I focus best in the morning, like explanations in plain language, and appreciate a short checklist when a task has several steps.",
        "tags": ["preferences", "planning"],
    },
    {
        "title": "How I want to use my notes",
        "category": "Getting Started",
        "content": "I can save plans, lists, reminders, and preferences here, then ask questions using my notes as context. I can ask what I need to buy, what matters this week, or for help turning my notes into a plan.",
        "tags": ["getting-started", "ai", "questions"],
    },
]


def seed_user():
    user = find_user_by_username(SEED_USERNAME)
    created = False
    if not user:
        created = create_user(SEED_USERNAME, SEED_PASSWORD)
        if not created:
            print("Failed to create user", SEED_USERNAME, file=sys.stderr)
            sys.exit(1)
        user = created
        print(f"Created user {SEED_USERNAME} (user_id={user['user_id']})")
    else:
        print(f"User {SEED_USERNAME} already exists (user_id={user['user_id']})")

    user_id = user["user_id"]
    existing = load_notes(user_id)
    existing_keys = {
        ((note.get("title") or "").strip(), (note.get("category") or "").strip())
        for note in existing
    }
    added = 0
    for note in SEED_NOTES:
        key = (note["title"], note["category"])
        if key in existing_keys:
            continue
        add_note(note.copy(), user_id)
        existing_keys.add(key)
        added += 1
    print(f"Notes: {len(existing)} -> {len(existing) + added} (+{added} seed notes)")
    return {"user_id": user_id, "created": bool(created), "added_notes": added}


def main():
    seed_user()
    print("Done. Sign in with", SEED_USERNAME, "/", SEED_PASSWORD)


if __name__ == "__main__":
    main()
