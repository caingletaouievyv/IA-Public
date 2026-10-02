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
| Note context modes | Ask with each `note_context_mode` | Off ignores IDs; Focused uses only selected IDs; Automatic searches all notes unless IDs restrict it; omitted mode defaults to Automatic |
| Selected notes | Ask with `note_ids` array in Focused or Automatic | Only selected candidates can be used; selected notes remain eligible if no lexical match is found |
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

- Login and register.
- Open Ask.
- Verify the Ask shortcuts open the History and Notes selectors; selecting an item returns to Ask and closes the selector.
- Verify the note mode cycles `Off → Focused → Automatic → Off`; Off ignores selected IDs, Focused without IDs supplies no context, and Automatic searches all notes only when IDs are absent.
- Verify conversation history is expanded by default, user turns are right-aligned, and AI turns are left-aligned.
- Edit a user turn inline. Cancel and Escape preserve the original. Save resends through the current conversation; confirm later turns are replaced by the edited turn and new AI response.
- Verify Edit is available to keyboard focus and remains visible on mobile; confirm the textarea has a label and Save/Cancel are real buttons.
- Keyboard-tab through Ask shortcuts, mode toggle, Notes/History action buttons, and floating-window controls; verify visible focus, accessible labels, and a clear button surface/hover/pressed state. Compact Ask shortcuts should still read as buttons, not plain labels.
- Verify one History selector and one Notes selector maximum per Ask window.
- Verify selectors from different Ask windows remain independent.
- Create a new conversation from History; verify it appears and opens immediately.
- Verify active conversation styling.
- Verify normal Notes and History CRUD outside selection mode.
- Verify Ask, History, Debug, and Settings do not duplicate the FloatingWindow title.
- Verify loading, error, and empty states still render.

### Floating-window mobile and desktop regression (manual)

- Test at approximately `375×667`, `390×844`, and `412×915`.
- Touch-drag and touch-resize the Ask window.
- Touch-drag and touch-resize selector windows.
- Verify the floating body still scrolls on touch.
- Verify Minimize → Maximize/Restore → Close ordering.
- Verify maximize fills the usable viewport.
- Verify Restore returns the previous position and size.
- Verify maximize/restore is hidden while collapsed.
- Verify collapse/expand still works after maximizing/restoring.
- Verify desktop mouse drag and resize still work.

There is no frontend component-test or browser-automation suite in the repository. Do not treat a browser automation run as a required check.

## Final repository check

From the repository root, run `git diff --check` after reviewing the Markdown diff. The frontend build command above is `npm --prefix .\frontend run build`.
