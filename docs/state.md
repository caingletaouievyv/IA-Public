# IA — Session state

**Purpose:** Handoff for you and any AI on any machine. Not architecture (that is `ia.md` / `project.md`).

**How to use:** Paste this file (or say “read `docs/state.md`”) at the start of a new chat. After a session, update **State / Intent / Next** only.

**Updated:** 2026-08-16

---

## State (where we are)

- Phases 1–6 and 8 are done (notes, AI, memory, ensemble/judge, UI, security, JWT + per-user notes).
- Phase 7 (mobile + monetization) is **not** started.
- Ask can use selected notes; if none selected, semantic search over all user notes.
- Notes from images: OCR → summarize → one note; same title+category **appends**.
- Built UI at `:5000` needs Flask `/assets/` route (fixed; do not drop it).
- Public GitHub repo. **Not in git:** `.env`, `docs/ia.md`, `backend/data/users.json`, `backend/data/notes_*.json`. Copy those between machines.

## Intent (what we want)

Keep work continuous across machines and AI chats: same rules, same next step, no re-explaining the whole project.

## Next action

1. Copy private files to the other machine (`.env`, `docs/ia.md`, `users.json`, `notes_*.json`).
2. Clone, `npm run build`, `python run.py`.
3. When ready to code: **Phase 7** or polish you name in chat.

## Do not put here

Secrets, passwords, API keys, full note dumps, long architecture essays.

---

## Pointers

| Need | Open |
|------|------|
| How we build | `docs/ia.md` (copy; gitignored) |
| What the product is | `docs/project.md` |
| Doc index | `docs/docs.md` |
| Run / APIs | `README.md`, `docs/testing.md` |
