# IA — Session state

**Purpose:** Current implementation snapshot for handoff. Architecture and engineering conventions live in [ia.md](ia.md) and product details live in [project.md](project.md).

**Updated:** 2026-10-12  
**Version:** Frontend package `0.0.1`; no repository-wide release version is declared. `.python-version` selects Python `3.13.5`.

---

## Current state

- **Architecture/runtime:** Flask backend and React 18/Vite frontend. `backend/run.py` loads the repository-root `.env`. Flask serves `frontend/dist` when built, otherwise serves the frontend directory. Vite dev server uses port 5174 and proxies API paths to port 5000.
- **Authentication:** Registration/login store password hashes in ignored local `backend/data/users.json` and issue HS256 JWTs. `JWT_SECRET` is required during `create_app()` startup; it must be at least 32 characters with at least 8 distinct characters. Missing, weak, or placeholder values fail startup with a generic error. Protected routes read the user ID from `sub`; token lifetime defaults to seven days. The frontend stores the token in `localStorage` and clears it after a rejected 401.
- **AI Credits:** Per-user JSON balance, ledger, and Ask operation results are stored under ignored `backend/data/`. Defaults are 10 initial credits and 1 per Ask. Ask reserves before AI work, rejects insufficient balance with 402, and refunds when AI execution raises. Completed duplicate operations return the saved result; active duplicates return 409. The process-local lock is not a multi-worker transaction. The configured unlimited role defaults to `admin`. Rewarded-ad grants are enabled only in development/test and are not provider-verified.
- **Memory/retrieval:** `MEMORY_RETRIEVAL=text` is the default deterministic lexical path over title, metadata, and chunked note content. `MEMORY_RETRIEVAL=semantic` opts into temporary FAISS retrieval. SentenceTransformer model initialization is lazy.
- **Ask context:** Notes mode cycles `Off → Selected → Automatic → Off`. Selected maps to API mode `focused`; Automatic searches relevant user notes unless IDs restrict it. Conversation opens the existing history selector. Conversation, Notes, and Memory are visible by default; source visibility and modes are saved in per-user Settings. Other source controls are placeholders and do not retrieve context.
- **Conversation history:** Conversations are per-user notes with category `_history`. Ask sends up to 30 prior turns to the AI provider and saves the next user/assistant pair through `PUT /notes/<id>`.
- **Ask focus and messages:** The separate Focus control hides the app header and Ask context shortcuts while retaining history, the question textarea, and Ask button. AI responses have per-message Copy controls that copy plain text with line breaks and list structure preserved. Only user turns are editable; edit/resend replaces that turn and later turns through the existing Ask and note-update flow.
- **Manage:** The authenticated `/manage` page organizes Notes and Conversations by reusing the existing Notes and History interfaces. Its Memory section explains that retrieval uses saved notes; there is no separate memory collection or CRUD API. Note creation and image import remain available in Manage, not in the Ask Notes selector.
- **Notes:** Per-user JSON CRUD, category/tag filters, and image import using OCR plus AI summary. Image imports with a matching title/category append to that note.
- **Runtime data/deployment:** `backend/data/` holds local user and generated AI-memory artifacts and is ignored by Git. `frontend/public/_redirects` provides a static-host SPA fallback. Deployment values remain external and no provider-specific backend deployment manifest or hostname is declared in tracked files.

## Seed safety

`backend/scripts/seed_user.py` is a development/test utility. It refuses to run unless `APP_ENV=development` or `APP_ENV=test` and `SEED_USER_PASSWORD` is configured with at least 12 characters. The script does not change an existing account's password and only adds missing demo notes. Do not run demo seeding in production or commit local credentials.

## Current verification surface

- Backend checks are documented in [testing.md](testing.md), including compilation, AI/context/credit tests, seed idempotence, and settings persistence.
- Frontend verification is the Vite production build plus manual UI regression; no frontend component-test or browser-automation suite is configured.

## Pointers

| Need | Open |
|------|------|
| Engineering agreement and layers | [ia.md](ia.md) |
| Project behavior and configuration | [project.md](project.md) |
| Documentation index | [docs.md](docs.md) |
| Run and test | [README.md](../README.md), [testing.md](testing.md) |
| Ask request and edit flow | [flow.md](flow.md) |
| UI behavior | [ui.md](ui.md) |
