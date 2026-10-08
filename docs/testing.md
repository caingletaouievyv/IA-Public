# Testing

Run backend checks from `backend/`; live API smoke tests require the app running with a configured AI provider. Index: [docs.md](docs.md). Current request behavior: [flow.md](flow.md).

**Auth:** `POST /auth/login` with `{"username","password"}` returns a JWT. Use `Authorization: Bearer <token>` on protected routes. The live smoke helper uses `TEST_USER` / `TEST_PASSWORD` from the repository-root `.env` (defaults `testuser` / `testpass`), registering the account if login returns 401. The seed command can create the demo account `ayi` / `Ayi!23`.

---

## Prerequisites

- `.env` at repo root: set `JWT_SECRET` to a non-placeholder value with at least 32 characters and at least 8 distinct characters. The Flask app fails during startup if it is missing or does not meet validation; there is no default or `API_SECRET` fallback. A live `/ai/ask` call also needs credentials for the configured provider; unit tests mock the AI call.
- Base URL: `http://127.0.0.1:5000`.
- **Notes from images:** Tesseract installed (e.g. Windows: `choco install tesseract`).

---

## API reference

| API | Method | Auth | How to test | Expected |
|-----|--------|------|-------------|----------|
| **POST /auth/register** | POST | no | `{"username","password"}` | 201 token + user_id or 409 |
| **POST /auth/login** | POST | no | `{"username","password"}` | 200 token or 401 |
| **POST /ai/ask** | POST | yes | Bearer + `{"question":"..."}`; optional `note_context_mode`, `note_ids`, prior `messages` | 200 `answer`, `tokens_estimated`; 402 for insufficient credits |
| **POST /ai/estimate_tokens** | POST | yes | Bearer + `{"question":"..."}` | 200 `estimated_tokens`, `context_tokens` |
| **POST /ai/debug/context** | POST | yes | Bearer + `{"question":"..."}` | 200 context, scores, dropped_notes |
| **POST /notes** | POST | yes | Bearer + note JSON | 201 note |
| **POST /notes/from-images** | POST | yes | Multipart: title, category, files | 201 `{ note, appended }` |
| **GET /notes** | GET | yes | Bearer; optional `?limit=500` | 200 array |
| **GET /notes/<id>** | GET | yes | Bearer | 200 or 404 |
| **PUT /notes/<id>** | PUT | yes | Bearer + partial JSON | 200 or 404 |
| **DELETE /notes/<id>** | DELETE | yes | Bearer | 200 or 404 |
| **GET /settings** | GET | yes | Bearer | 200 preferences |
| **PUT /settings** | PUT | yes | Bearer + JSON merge | 200 settings |
| **GET /health** | GET | no | `curl .../health` | 200 `{"status":"ok"}` |
| **POST /credits/rewarded-ad** | POST | yes | Bearer + non-empty `reward_id` | 200 configured grant only in `APP_ENV=development` or `APP_ENV=test`; 404 when disabled elsewhere. The ID is not provider verification. |

---

## Backend checks

Run from `backend/`:

```bash
python -m compileall -q app scripts
python -m scripts.test.test_ai_context_modes
python -m scripts.test.test_ai_credits
python -m scripts.test.test_ai_response_style
python -m scripts.test.test_lazy_embeddings
python -m scripts.test.test_text_retrieval
python -m scripts.test.test_seed_user
```

`test_ai_credits.py` uses temporary credit storage and mocks AI execution. It covers missing/unsafe JWT-secret startup rejection, initial balances, per-user isolation, idempotent grants, rejection of unverified rewarded-ad grants outside dev/test, Ask spending, insufficient-credit rejection, unlimited-role behavior, refunds, JWT authentication, and rate limiting. It also verifies that completed Ask retries return the saved result without another provider call or debit, distinct IDs create distinct operations, and the same ID is isolated between users. It does not currently assert the active-pending 409 response. `test_ai_context_modes.py` covers all modes, selected IDs, missing-mode compatibility, and invalid modes. `test_text_retrieval.py` covers deterministic lexical scoring, filtering, thresholds, and token packing. `test_lazy_embeddings.py` verifies model initialization is deferred and supplies a test-only JWT secret for app startup.

`test_selected_notes_context.py` is pytest-style and can be run with `python -m pytest scripts/test/test_selected_notes_context.py` if pytest is installed; pytest is not listed in `requirements.txt`.

### Live API smoke (optional)

Start the backend from `backend/` with `python run.py`, configure a provider key, and ensure the test account has AI Credits. Then run:

```bash
python -m scripts.test.test_ask_note_ids_and_health
```

This checks health, JWT login/registration, `/ai/ask`, and selected note IDs; it makes live requests and can create a test user. The `stress_test_faiss_*.py` scripts make bulk writes and AI calls, so they are not routine checks. `test_semantic_retrieval_and_chunked_notes.py` uses the obsolete API-secret-as-Bearer pattern; do not use it as a current authentication or retrieval check.

---

## Quick checklist

| What | How | Expected |
|------|-----|----------|
| Health | `curl http://127.0.0.1:5000/health` | 200 ok |
| Ask | Login → POST `/ai/ask` with Bearer | 200 answer |
| Note context modes | Ask with each `note_context_mode` | Off ignores IDs; API `focused` (UI Selected) uses only selected IDs; Automatic searches all notes unless IDs restrict it; omitted mode defaults to Automatic |
| Selected notes | Ask with `note_ids` array in API `focused` (UI Selected) or Automatic | Only selected candidates can be used; selected notes remain eligible if no lexical match is found |
| Default retrieval | Default config / `MEMORY_RETRIEVAL=text` | Deterministic lexical retrieval; no SentenceTransformer model load |
| Optional semantic retrieval | Set `MEMORY_RETRIEVAL=semantic` before starting backend and inspect `/ai/debug/context` with JWT | Semantic FAISS path; model loads only on first use; requires model dependencies and availability |
| Credits and idempotency | Use `test_ai_credits.py` | Charge, insufficient-balance 402, role bypass, refunds, completed retry result reuse, distinct operation IDs, and per-user operation isolation match behavior |
| Rewarded ads | Use `test_ai_credits.py` | Auth is required; caller-supplied reward IDs cannot grant outside explicit development/test mode |
| JWT startup validation | Use `test_ai_credits.py` | Missing, weak, and placeholder secrets fail app creation without logging the secret |
| Images | Notes UI or multipart `/notes/from-images` | 201; Tesseract required |

## Frontend manual regression checklist

Run the frontend production build from the repository root:

```bash
npm --prefix .\frontend run build
```

- Logged out: direct-load `/login` and `/register`; verify register switching follows the route, registration/login still works, and success lands on `/ask`.
- Verify `/` remains public, and `/privacy`, `/terms`, and `/contact` load directly.
- Verify `/ask` is the authenticated default; navigation contains only Ask, Debug, and Settings.
- Navigate Ask → Debug → Settings → Ask; verify browser Back and Forward update the visible page and URL.
- Direct-load and refresh `/ask`, `/debug`, and `/settings`; verify each returns the SPA and renders the correct page.
- Verify logout and an unauthorized API response return to `/login`.
- Open Ask and enter a draft. Open and close Notes/History; verify the draft and existing conversation remain intact.
- Verify the Ask shortcuts open the in-place History and Notes selectors; selecting an item closes the selector without navigating away from `/ask`.
- Cancel Notes selection and verify the existing note context is unchanged. Select notes and confirm; verify the selected context updates.
- Create a note from the Notes selector, verify it appears selected, and confirm to add it to Ask context. Verify Notes Manage still supports CRUD and image import.
- Verify History Manage retains title editing and single/bulk delete. In the selector, start a new conversation and select an existing conversation.
- Verify the header shows Conversation, Notes, Files, GitHub, Memory, Drive, and Web. Conversation has no mode button and opens the existing History UI.
- Verify Notes, Files, GitHub, Memory, Drive, and Web each have separate source and mode buttons; each mode cycles `Off → Selected → Automatic → Off` without opening a menu. Notes Selected still uses the API's `focused` mode; Notes Off excludes note context and Automatic retains current note retrieval.
- Verify active conversation turns continue to be sent as before. Placeholder source modes do not affect AI requests. Files remains an unavailable Ask context source while its backend file-tree listing remains intact.
- On desktop, hover and keyboard-focus each source button to show its details; confirm mode buttons do not show details. On mobile, tap a source to open its selector, press and hold to show details without opening the selector, move past the gesture threshold to cancel, scroll normally, dismiss details by tapping elsewhere, and dismiss with Escape.
- Verify conversation history is expanded by default, AI turns are left-aligned, and user bubbles are right-aligned with long messages clamped to a compact preview.
- Click/tap a user bubble and verify the shared Ask overlay shows the complete message. Click Edit and verify the same overlay switches to Edit Message mode and focuses the textarea. Cancel returns to detail; Save updates the history and returns to detail without closing the overlay. Verify × and backdrop close the overlay, Escape returns from edit to detail and closes from detail, and clicks inside do not close it. Verify focus trap/restoration and no horizontal overflow on desktop and mobile.
- Use the previous/next controls to navigate only User messages; confirm AI turns are skipped, scrolling is smooth, the target gets focus/active indication, and controls disable at the first/last User message. Check the thin dark scrollbar and no horizontal overflow at desktop and mobile widths.
- Save an edited user turn through the overlay. Confirm the existing Ask flow resends only prior turns and later turns are replaced by the edited turn and new AI response. Cancel and Escape preserve the original.
- Confirm the overlay Edit action is keyboard accessible; confirm the focused textarea has a label and Save/Cancel are real buttons.
- Keyboard-tab through navigation, both buttons for each Ask source, Notes/History selectors and management actions; verify visible focus, accessible labels/descriptions, and clear button hover/pressed states. Source details should be available on keyboard focus without activating the source action.
- Verify active conversation styling.
- Verify loading, error, and empty states still render.
- At desktop, narrow desktop, and mobile widths, verify natural page scrolling, touch-friendly controls, and no horizontal overflow or floating/drag/resize behavior.

There is no frontend component-test or browser-automation suite in the repository. Do not treat a browser automation run as a required check.

## Final repository check

From the repository root, run `git diff --check` after reviewing the Markdown diff. The frontend build command above is `npm --prefix .\frontend run build`.
