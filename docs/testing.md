# Testing

Run backend checks from `backend/`; live API smoke tests require the app running with a configured AI provider. Index: [docs.md](docs.md). Current request behavior: [flow.md](flow.md).

**Auth:** `POST /auth/login` with `{"username","password"}` returns a JWT. Use `Authorization: Bearer <token>` on protected routes. The live smoke helper uses `TEST_USER` / `TEST_PASSWORD` from the repository-root `.env` (defaults `testuser` / `testpass`), registering the account if login returns 401.

The seed command is for development/test only. Set `APP_ENV=development` (or `test`) and `SEED_USER_PASSWORD` with at least 12 characters in the ignored root `.env` before running `python -m scripts.seed_user`. It refuses other environments or missing/short passwords, does not change an existing `demo` account's password or notes/settings/credits, adds missing demo notes, and initializes a missing credit account only. Any existing `ayi` account is left untouched.

The separate `python -m scripts.seed_render_demo` command requires explicit production environment, `RENDER_DEMO_SEED_ENABLED=true`, and a password-manager-generated `SEED_USER_PASSWORD` of at least 12 characters. Length alone does not guarantee entropy. It is intended only in the Render Start Command, never the Build Command. A pre-existing `demo` username is refused unless the instance-local marker matches the account ID created by this seeder.

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
| **GET /memories/** | GET | yes | Bearer | 200 current user's saved memories |
| **PUT /memories/<id>** | PUT | yes | Bearer `{"text":"..."}` | 200 updated memory, 400 invalid input, 404 not owned/not found |
| **DELETE /memories/<id>** | DELETE | yes | Bearer | 200 deleted, 404 not owned/not found |
| **DELETE /memories/clear** | DELETE | yes | Bearer; Manage asks for confirmation | 200 deleted record count |
| **GET /health** | GET | no | `curl .../health` | 200 `{"status":"ok"}` |
| **POST /credits/rewarded-ad** | POST | yes | Bearer + non-empty `reward_id` | 200 configured grant only in `APP_ENV=development` or `APP_ENV=test`; 404 when disabled elsewhere. The ID is not provider verification. |

---

For `/ai/ask`, Memory is controlled by the persisted `memory_enabled` boolean in `/settings/`, default false; a client request field cannot enable it. When enabled, Ask retrieves independent stored memories and performs best-effort extraction after the answer. When disabled, it does neither and preserves existing records. Notes continues to use `note_context_mode` (`off`, `automatic`, or `focused`; omitted defaults to `automatic`). Optional `note_ids` must be an array of non-empty strings and are resolved only within the authenticated user's Notes.

## Backend checks

Run from `backend/`:

```bash
python -m compileall -q app scripts
python -m scripts.test.test_ai_context_modes
python -m scripts.test.test_ai_credits
python -m scripts.test.test_memories
python -m scripts.test.test_ai_response_style
python -m scripts.test.test_lazy_embeddings
python -m scripts.test.test_text_retrieval
python -m scripts.test.test_seed_user
python -m scripts.test.test_seed_render_demo
python -m scripts.test.test_settings_preferences
```

`test_seed_user.py` checks the environment/password safety guard, repeated execution, and preservation of existing demo notes, settings, and credit balances using temporary JSON stores. `test_ai_credits.py` uses temporary account storage and mocks AI execution. It covers registration and lazy initialization at the configured starting balance, existing-account preservation when the initial-balance setting changes, per-user isolation, idempotent grants and ledger entries, rejection of unverified rewarded-ad grants outside dev/test, Ask spending, insufficient-credit rejection, unlimited-role behavior, refunds, JWT authentication, and rate limiting. It also verifies that completed Ask retries return the saved result without another provider call or debit, distinct IDs create distinct operations, and the same ID is isolated between users. It does not currently assert the active-pending 409 response. `test_ai_context_modes.py` covers all modes, selected IDs, missing-mode compatibility, and invalid modes. `test_text_retrieval.py` covers deterministic lexical scoring, filtering, thresholds, and token packing. `test_lazy_embeddings.py` verifies model initialization is deferred and supplies a test-only JWT secret for app startup.

`test_seed_render_demo.py` uses isolated temporary JSON stores to verify production environment and enable-flag rejection, missing/weak password rejection, refusal and non-modification of a pre-claimed `demo` account, marked-account rerun idempotence, sample-note creation, and preservation of the seeded account's password, role, settings, credit balance, and customized notes.

`test_selected_notes_context.py` is pytest-style and can be run with `python -m pytest scripts/test/test_selected_notes_context.py` if pytest is installed; pytest is not listed in `requirements.txt`.

`test_memories.py` uses temporary storage and mocked provider output. It covers the default-off persistent setting, user isolation, authenticated CRUD and clear-all, bounds/secrets, grounded explicit extraction, candidate-scoped sensitive consent (including independent requests, uncertain/negated/corrected/superseded claims, unrelated people and contrast clauses, unrelated history, quoted requests, and missing/fabricated/assistant-only evidence), targeted revocation of a unique standalone sensitive record with an in-process atomic unchanged-record check, a deterministic intervening-edit regression, fail-closed handling of ambiguous matches and compound records, update/deduplication, forget requests, and relevance. `test_ai_context_modes.py` verifies Memory and Notes are independent, Off skips retrieval/extraction, enabled Memory is injected as untrusted background data, and extraction failures do not fail an AI response. `test_ai_credits.py` verifies the server-side setting controls Memory and that a successful Ask with Memory still reserves only one credit.

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
| Persistent Memory | Toggle Memory in Ask or Manage, then inspect `/settings/` | `memory_enabled` persists per user, defaults off, and controls both automatic extraction and retrieval |
| Memory isolation/CRUD | `python -m scripts.test.test_memories` | Cross-user list/edit/delete/clear cannot access another account's records |
| Memory extraction/retrieval | `python -m scripts.test.test_memories` and `test_ai_context_modes` | Grounded bounded records, explicit remember/forget, deduplication/update, relevance, and independent prompt section; Off skips both |
| Memory failure behavior | `python -m scripts.test.test_ai_context_modes` | Extraction failure leaves normal Ask answer intact and returns unavailable status |
| Context request validation | Send invalid modes, malformed `note_ids`, or non-object JSON | 400 before operation claim or credit charge; no provider call |
| Default retrieval | Default config / `MEMORY_RETRIEVAL=text` | Deterministic lexical retrieval; no SentenceTransformer model load |
| Optional semantic retrieval | Set `MEMORY_RETRIEVAL=semantic` before starting backend and inspect `/ai/debug/context` with JWT | Semantic FAISS path; model loads only on first use; requires model dependencies and availability |
| Credits and idempotency | Use `test_ai_credits.py` | Charge, insufficient-balance 402, role bypass, refunds, completed retry result reuse, distinct operation IDs, and per-user operation isolation match behavior |
| Rewarded ads | Use `test_ai_credits.py` | Auth is required; caller-supplied reward IDs cannot grant outside explicit development/test mode |
| JWT startup validation | Use `test_ai_credits.py` | Missing, weak, and placeholder secrets fail app creation without logging the secret |
| Images | Notes UI or multipart `/notes/from-images` | 201; Tesseract required |

## Frontend component tests

From the repository root, run:

```bash
npm --prefix .\frontend test
```

This runs the existing Node source-mode tests and the Vitest/jsdom integration tests for the real `App`, `Ask`, and route-controlled `Login` components. The mocked HTTP API exercises Notes-backed restoration and saved updates without calling an AI provider. Regressions cover Login/Register route updates without a stale first render, Ask → Manage → Ask, loading the latest messages/title, explicit New conversation, switching conversations, deleted history, out-of-order responses, logout/account isolation, and editing/resending a User turn. Notes-context coverage verifies selected Note IDs and Notes mode survive remount and the expected IDs/mode are included in the next AI request. Context-source tests cover enabled/disabled label preferences, first-render Settings → Ask restoration, navigation during a pending label save, and account changes while a Settings read is waiting.

## Frontend manual regression checklist

Run the frontend production build from the repository root:

```bash
npm --prefix .\frontend run build
```

- Logged out: direct-load `/login` and `/register`; verify register switching follows the route, registration/login still works, and success lands on `/ask`.
- Verify `/` remains public, and `/privacy`, `/terms`, and `/contact` load directly.
- Verify `/ask` is the authenticated default; navigation order is Ask, Manage, Settings, Sign out. Signed-in users can still open `/debug` directly; the debug API requires authentication.
- Navigate Ask → Manage → Settings → Ask; verify browser Back and Forward update the visible page and URL. Confirm Debug is absent from navigation but remains available to signed-in users at `/debug`.
- Select a conversation in Ask, save a new turn, navigate to Manage, then return to Ask; verify the same conversation title and latest saved turns load. Start a new conversation and repeat the navigation; verify the new empty conversation stays active instead of reopening the previous one.
- Select Notes for context and set Notes mode to Selected or Automatic. Navigate to Manage and back; verify the mode and selected Note count remain, then submit a question and verify it uses the intended Notes. Log out or switch accounts and verify the previous account's selected IDs are not applied.
- Direct-load and refresh `/ask`, `/manage`, `/debug`, and `/settings`; verify each returns the SPA and renders the correct page.
- On `/manage`, switch among Notes, Conversations, and Memory. Verify Notes and Conversations expose the existing CRUD interfaces, Notes excludes `_history`, and Memory loads persisted per-user records with working edit/delete/clear controls and setting status.
- Verify logout and an unauthorized API response return to `/login`.
- Open Ask and enter a draft. Open and close Notes/History; verify the draft and existing conversation remain intact.
- Verify the Ask shortcuts open the in-place History and Notes selectors; selecting an item closes the selector without navigating away from `/ask`. Ask selectors remain selection-only; saved-content CRUD is in Manage.
- Cancel Notes selection and verify the existing note context is unchanged. Select notes and confirm; verify the selected context updates.
- Verify the Notes selector is selection-only: no Add note or Add from images shortcuts appear there. Confirm selected notes update Ask context, and verify Manage retains note creation and image import.
- Verify Manage → Conversations retains title editing and single/bulk delete. In the Ask selector, start a new conversation and select an existing conversation.
- Verify a new or unset Ask context-source preference shows Conversation, Notes, and Memory only. In Settings → Ask Context Sources, verify all seven entries have their existing icons and descriptions, Conversation stays checked/disabled, and toggling another source immediately saves.
- In Settings → Ask, turn **Show Ask labels** off and immediately navigate to Ask, including while the checkbox shows Saving; confirm labels never appear in the initial toolbar. Repeat with labels enabled and navigate away/back to confirm the saved preference is honored. Using Focus must not change this setting.
- Navigate back to Ask and verify only enabled source/mode controls appear, with no gaps. Refresh or sign out/in and verify visibility persists for that user; malformed or outdated visibility settings fall back to Conversation, Notes, and Memory.
- Verify Conversation has no mode button and opens the existing History UI. Visible Notes, Files, GitHub, Memory, Drive, and Web have separate source and mode buttons; each mode cycles `Off → Selected → Automatic → Off` without opening a menu. Notes Selected still uses the API's `focused` mode; Notes Off excludes note context and Automatic retains current note retrieval. Hiding and showing a source does not reset its mode or change its data or retrieval behavior.
- Verify active conversation turns continue to be sent as before. Placeholder source modes do not affect AI requests. Files remains an unavailable Ask context source while its backend file-tree listing remains intact.
- On desktop, hover and keyboard-focus each source button to show its details; confirm mode buttons do not show details. On mobile, tap a source to open its selector, press and hold to show details without opening the selector, move past the gesture threshold to cancel, scroll normally, dismiss details by tapping elsewhere, and dismiss with Escape.
- Verify Conversation History is expanded by default and its heading is not clickable. The separate Focus button should enter focus mode, hide the app header and Ask context shortcuts, and keep history, the question textarea, and Ask button available. Click Focus again and verify the normal layout returns without changing the active conversation, messages, or selection. Check independently scrollable history, message navigation, long-message wrapping, and chat submission on desktop and mobile.
- Verify the Focus button's accessible name and `aria-pressed` state. It should not expose `aria-expanded`; hidden header and shortcuts must not receive keyboard focus while focus mode is active.
- Verify Focus uses an outward-corner icon when inactive and inward-corner icon when active, while the Conversation History title remains left-aligned and Focus/navigation controls align right. In narrow widths, confirm controls remain usable without horizontal overflow.
- For multiple AI responses, activate each icon-only Copy button and verify only that response is copied as plain text, retaining line breaks and list structure. Verify accessible success feedback without a text-label change, clipboard failure feedback, keyboard activation, mobile usability, and visible focus; user messages should not have Copy buttons.
- Verify the Question label is visually hidden in Conversation History focus mode and remains an accessible name for the textarea. Confirm the textarea and Ask button remain usable.
- Click/tap a user bubble and verify the shared Ask overlay shows the complete message. Click Edit and verify the same overlay switches to Edit Message mode and focuses the textarea. Cancel returns to detail; Save updates the history and returns to detail without closing the overlay. Verify × and backdrop close the overlay, Escape returns from edit to detail and closes from detail, and clicks inside do not close it. Verify focus trap/restoration and no horizontal overflow on desktop and mobile.
- Use the previous/next controls to navigate only User messages; confirm AI turns are skipped, scrolling is smooth, the target gets focus/active indication, and controls disable at the first/last User message. Check the thin dark scrollbar and no horizontal overflow at desktop and mobile widths.
- Save an edited user turn through the overlay. Confirm the existing Ask flow resends only prior turns and later turns are replaced by the edited turn and new AI response. Cancel and Escape preserve the original.
- Confirm the overlay Edit action is keyboard accessible; confirm the focused textarea has a label and Save/Cancel are real buttons.
- Keyboard-tab through navigation, both buttons for each Ask source, Notes/History selectors and management actions; verify visible focus, accessible labels/descriptions, and clear button hover/pressed states. Source details should be available on keyboard focus without activating the source action.
- Verify active conversation styling.
- Verify loading, error, and empty states still render.
- At desktop, narrow desktop, and mobile widths, verify natural page scrolling, touch-friendly controls, and no horizontal overflow or floating/drag/resize behavior.

Responsive layout and browser-specific UX still require manual verification; the frontend component regressions cover route remounting and conversation behavior.

## Final repository check

From the repository root, run `git diff --check` after reviewing the Markdown diff. The frontend build command above is `npm --prefix .\frontend run build`.
