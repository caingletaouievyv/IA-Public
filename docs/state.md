# IA — Session state

**Purpose:** Current implementation snapshot for handoff; architecture details live in [project.md](project.md) and the local engineering agreement.

**Updated:** 2026-10-02
**Version:** Frontend package `0.0.1`; no repository-wide release version is declared. `.python-version` selects Python `3.13.5`.

---

## Current state

- **Architecture/runtime:** Flask backend and React 18/Vite frontend. `backend/run.py` loads the repository-root `.env`. Flask serves `frontend/dist` when built, otherwise serves the frontend directory. Vite dev server uses port 5174 and proxies the current API paths to port 5000.
- **Authentication:** Registration/login store password hashes in ignored local `backend/data/users.json` and issue HS256 JWTs. `JWT_SECRET` is required during `create_app()` startup; it must be at least 32 characters with at least 8 distinct characters, and missing, weak, or placeholder values fail startup with a generic error. Protected routes read the user ID from `sub`; token lifetime defaults to seven days. The frontend stores the token in `localStorage` and clears it after a rejected 401.
- **AI Credits:** Per-user JSON balance, ledger, and Ask operation results are stored under ignored `backend/data/`. Defaults are 10 initial credits and 1 per Ask. Ask reserves before AI work, rejects insufficient balance with 402, and refunds when AI execution raises. Requests reusing a completed operation ID for the same user return the persisted result without another provider call or debit; active duplicates return 409. Insufficient-credit rejections and AI execution failures release their pending record. The process-local lock is not a multi-worker transaction. The configured unlimited role defaults to `admin`. The authenticated rewarded-ad endpoint is enabled only in explicit development/test mode; its reward ID is unverified and production requires server-side provider verification. There is no frontend balance/ledger UI or purchase flow.
- **Memory/retrieval:** `MEMORY_RETRIEVAL=text` is the default deterministic lexical path over title, metadata, and chunked note content. `MEMORY_RETRIEVAL=semantic` opts into temporary FAISS retrieval. SentenceTransformer model initialization is lazy. Context has relevance thresholds, summarization, token packing, and optional analytics.
- **Note context:** `Off` ignores IDs and uses no notes. `Focused` uses explicitly selected notes only and returns empty context without IDs. `Automatic` searches user notes when relevant; IDs restrict it to selected notes. Ask cycles `Off → Focused → Automatic → Off`. Missing mode in older requests defaults to `automatic`.
- **Conversation history:** Conversations are per-user notes with category `_history`. Ask sends up to 30 prior turns to the AI provider and saves the next user/assistant pair through `PUT /notes/<id>`.
- **Chat editing/layout:** Only user turns are editable. Editing is inline; Cancel or Escape leaves the original turn intact. Save resends through the same `/ai/ask` conversation flow using earlier turns, then stores the edited turn and new answer, replacing later turns. User messages are right-aligned; AI messages are left-aligned. There is no edit endpoint.
- **UI:** Dark visual system, shared primary/subtle/danger/icon buttons, compact but bordered Ask shortcuts, accessible names/focus states, and draggable/resizable floating Ask, Notes, History, Debug, and Settings windows. Mobile windows open maximized; selector windows are scoped to their Ask window.
- **Notes:** Per-user JSON CRUD, category/tag filters, and image import using OCR plus AI summary. Image imports with a matching title/category append to that note.
- **Runtime data/deployment:** `backend/data/` holds local user and generated AI-memory artifacts and is ignored by Git. `frontend/public/_redirects` provides a static-host SPA fallback. No provider-specific backend deployment manifest or deployed hostname is declared in tracked files; deployment environment values remain external.

## Current verification surface

- Backend scripts cover auth/credit behavior, context modes, lexical retrieval, lazy embeddings, response instructions, and seed idempotence. The selected-note pytest-style check is separate from the standard-library unittest scripts.
- Frontend verification is the Vite production build plus manual UI regression; no frontend component-test or browser-automation suite is configured.

## Pointers

| Need | Open |
|------|------|
| Project behavior and configuration | [project.md](project.md) |
| Documentation index | [docs.md](docs.md) |
| Run and test | [README.md](../README.md), [testing.md](testing.md) |
| Ask request and edit flow | [flow.md](flow.md) |
| UI behavior | [ui.md](ui.md) |
