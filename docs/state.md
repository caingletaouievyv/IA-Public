# IA — Session state

**Purpose:** Handoff for you and any AI on any machine. Not architecture (that is `ia.md` / `project.md`).

**How to use:** Paste this file (or say “read `docs/state.md`”) at the start of a new chat. After a session, update **State / Intent / Next** only.

**Updated:** 2026-09-08

---

## State (where we are)

- Phases 1–6 and 8 are done (notes, AI, memory, ensemble/judge, UI, security, JWT + per-user notes).
- Phase 7 (mobile + monetization) is **not** started.
- The frontend uses floating Ask, Notes, History, Debug, and Settings windows.
- Ask can open History in selection mode for a conversation and Notes in selection mode for note context.
- Selector windows are centered, scoped to their parent Ask window, and limited to one History selector plus one Notes selector per Ask window.
- Selecting a conversation or note returns the selection to Ask and closes the selector.
- History can create a new conversation, immediately view the created conversation, and visually indicate the active conversation.
- Ask can use selected notes; if none selected, semantic search over all user notes.
- FloatingWindow owns the top-level title; redundant Ask, History, Debug, and Settings panel titles have been removed.
- Notes from images: OCR → summarize → one note; same title+category **appends**.
- Built UI at `:5000` uses Flask to serve the built frontend assets.

## Intent (what we want)

Keep work continuous across machines and AI chats: same rules, same next step, no re-explaining the whole project.

## Next action

1. Keep Phase 7 (mobile + monetization) as a future product decision.
2. Continue frontend regression/manual testing and focused UX polish as needed.
3. When ready to code: choose a Phase 7 decision or a specific polish task.

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
