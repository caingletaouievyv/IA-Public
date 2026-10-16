# IA — Session state

**Purpose:** Current implementation snapshot for handoff. Architecture and engineering conventions live in [ia.md](ia.md) and product details live in [project.md](project.md).

**Updated:** 2026-10-14
**Version:** Frontend package `0.0.1`; no repository-wide release version is declared. `.python-version` selects Python `3.13.5`.

---

## Current state

- **Architecture/runtime:** Flask backend and React 18/Vite frontend. `backend/run.py` loads the repository-root `.env`. Flask serves `frontend/dist` when built, otherwise serves the frontend directory. Vite dev server uses port 5174 and proxies API paths to port 5000.
- **Authentication:** Registration/login store password hashes in ignored local `backend/data/users.json` and issue HS256 JWTs. `JWT_SECRET` is required during `create_app()` startup; it must be at least 32 characters with at least 8 distinct characters. Missing, weak, or placeholder values fail startup with a generic error. Protected routes read the user ID from `sub`; token lifetime defaults to seven days. The frontend stores the token in `localStorage` and clears it after a rejected 401.
- **AI Credits:** Per-user JSON balance, ledger, and Ask operation results are stored under ignored `backend/data/`. Defaults are 100 initial credits for newly initialized accounts and 1 per Ask. Registration initializes a credit account; changing the initial balance does not change an existing account file. Ask reserves before AI work, rejects insufficient balance with 402, and refunds when AI execution raises. Completed duplicate operations return the saved result; active duplicates return 409. The process-local lock is not a multi-worker transaction. The configured unlimited role defaults to `admin`. Rewarded-ad grants are enabled only in development/test and are not provider-verified.
- **Memory:** Independent records live in `backend/data/memories_<user-hash>.json`, separate from Notes and `_history` conversations. The per-user `memory_enabled` Setting defaults to false. When enabled, Ask retrieves relevant records with a lexical ranker (up to eight items / 180 estimated tokens), injects them as untrusted background facts, then best-effort extracts bounded user-grounded memories from user messages. Extraction failure does not fail the answer; explicit forget requests can remove matching owned records. Secret patterns are rejected. No relational database or migration is used because the repository's persistence convention is per-user JSON.
- **Ask context:** Source visibility, the `show_context_source_labels` preference (default true), and Notes context modes persist in per-user Settings; selected Note IDs are retained in per-tab `sessionStorage` keyed by JWT subject so the selected context survives Ask → Manage → Ask. The API keeps a current-session Settings cache keyed by JWT subject, invalidates it on account changes, and waits for pending writes before returning settings. Ask uses cached preferences on the first render when available and keeps its toolbar hidden while preferences are unknown. Note content remains in the existing per-user Notes store and the IDs are sent only when Notes mode is enabled. Memory is an ON/OFF setting persisted in per-user Settings; it controls both automatic extraction and retrieval. Its mode is not client-authoritative: the AI route reads `memory_enabled` from server-side settings for the authenticated JWT subject. Memory and Notes do not share context composition. Conversation opens the existing history selector and continues through its separate `messages` flow. Conversation, Notes, and Memory are visible by default. Files has no Ask context flow; GitHub, Drive, and Web remain placeholders and do not retrieve context.
- **Conversation history:** Conversations are per-user notes with category `_history`. Ask sends up to 30 prior turns to the AI provider and saves the next user/assistant pair through `PUT /notes/<id>`. Because the page switch unmounts Ask, its active note ID is saved in per-tab `sessionStorage` scoped by the authenticated JWT subject. On remount, Ask reloads the current title and messages using the existing Notes API. A newly selected/created conversation replaces the ID; logout clears it, and a missing or non-history note safely clears the stale selection. Only the active ID is persisted: drafts, selected note IDs, and scroll position remain transient; Notes context preferences continue to use per-user Settings.
- **Ask focus and messages:** The separate Focus control hides the app header and Ask context shortcuts while retaining history, the question textarea, and Ask button. AI responses have per-message Copy controls that copy plain text with line breaks and list structure preserved. Only user turns are editable; edit/resend replaces that turn and later turns through the existing Ask and note-update flow.
- **Manage:** The authenticated `/manage` page organizes Notes and Conversations by reusing their existing interfaces. Its Memory section loads persisted user records from authenticated `/memories/` APIs, shows the ON/OFF setting, and supports editing, deleting, and confirmation-protected clearing. Note creation and image import remain available in Manage, not in the Ask Notes selector.
- **Notes:** Per-user JSON CRUD, category/tag filters, and image import using OCR plus AI summary. Image imports with a matching title/category append to that note.
- **Runtime data/deployment:** `backend/data/` holds local user and generated AI-memory artifacts and is ignored by Git. `backend/run.py` loads the repository-root `.env`, creates the Flask app, and runs the Flask development server when executed directly. The repository does not currently contain `gunicorn.conf.py` or a cross-process data-directory lock. JSON storage and its in-process safeguards are not transactional across multiple workers/instances and are not a shared-database solution. `frontend/public/_redirects` provides a static-host SPA fallback. Deployment values remain external and no provider-specific backend deployment manifest, shared-volume type, or hostname is declared in tracked files.

For backup or restore, stop the backend and copy/restore the entire `backend/data/` directory; keep backups encrypted and access-controlled, and protect `.env` secrets separately. The repository does not configure or verify persistent production volumes, backup schedules, or a production restore procedure.

## Seed safety

`backend/scripts/seed_user.py` is a development/test utility. It refuses to run unless `APP_ENV=development` or `APP_ENV=test` and `SEED_USER_PASSWORD` is configured with at least 12 characters. The script does not change an existing account's password and only adds missing demo notes. Do not run demo seeding in production or commit local credentials.

## Current verification surface

- Backend checks are documented in [testing.md](testing.md), including compilation, AI/context/credit tests, seed idempotence, and settings persistence.
- Frontend verification includes the Vitest/jsdom App/Ask regressions and existing Node source-mode tests (`npm --prefix .\frontend test`), the Vite production build, and manual UI regression. Component tests mock Notes and AI HTTP responses and do not require a live provider.

## Pointers

| Need | Open |
|------|------|
| Engineering agreement and layers | [ia.md](ia.md) |
| Project behavior and configuration | [project.md](project.md) |
| Documentation index | [docs.md](docs.md) |
| Run and test | [README.md](../README.md), [testing.md](testing.md) |
| Ask request and edit flow | [flow.md](flow.md) |
| UI behavior | [ui.md](ui.md) |
