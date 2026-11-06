# Testing

Run backend checks from `backend/`; live API smoke tests require the app running with a configured AI provider. Index: [docs.md](docs.md). Current request behavior: [flow.md](flow.md).

**Auth:** `POST /auth/login` with `{"username","password"}` returns a JWT. Use `Authorization: Bearer <token>` on protected routes. The live smoke helper uses `TEST_USER` / `TEST_PASSWORD` from the repository-root `.env` (defaults `testuser` / `testpass`), registering the account if login returns 401.

The seed command is for development/test only. Set `APP_ENV=development` (or `test`) and `SEED_USER_PASSWORD` with at least 12 characters in the ignored root `.env` before running `python -m scripts.seed_user`. It refuses other environments or missing/short passwords, does not change an existing `demo` account's password or notes/settings/credits, adds missing demo notes, and initializes a missing credit account only. Any existing `ayi` account is left untouched.

The separate `python -m scripts.seed_render_demo` command requires explicit production environment, `RENDER_DEMO_SEED_ENABLED=true`, and a password-manager-generated `SEED_USER_PASSWORD` of at least 12 characters. Length alone does not guarantee entropy. It is intended only in the Render Start Command, after `alembic upgrade head`, never the Build Command. Gunicorn starts only if that upgrade succeeds. A pre-existing `demo` username is refused unless the instance-local marker matches the account ID created by this seeder.

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
| **GET /auth/me** | GET | yes | Bearer | 200 `{ user_id, username, role }` or 401 |
| **GET /admin/users** | GET | yes (`main_admin`) | Bearer | 200 `{ users: [{ user_id, username, role }] }`; 403 otherwise |
| **POST /admin/users/<user_id>/promote** | POST | yes (`main_admin`) | Bearer | 200 promoted `{ user_id, username, role: "admin" }`; 400 invalid state; 404 missing user; 403 otherwise |
| **POST /admin/users/<user_id>/demote** | POST | yes (`main_admin`) | Bearer | 200 demoted `{ user_id, username, role: "user" }`; 400 invalid state, self-change, or Main Admin protection; 404 missing user; 403 otherwise |
| **POST /ai/suggestions** | POST | yes | Authenticated; no body required | 200 no suggestion or an allow-listed action suggestion |
| **POST /ai/ask** | POST | yes | Bearer + `{"question":"..."}`; optional `note_context_mode`, `note_ids`, prior `messages` | 200 `answer`, `tokens_estimated`; 402 for insufficient credits |
| **POST /ai/estimate_tokens** | POST | yes | Bearer + `{"question":"..."}` | 200 `estimated_tokens`, `context_tokens` |
| **POST /ai/debug/context** | POST | yes | Bearer + `{"question":"..."}` | 200 context, scores, dropped_notes |
| **POST /notes** | POST | yes | Bearer + note JSON | 201 note |
| **POST /notes/from-images** | POST | yes | Multipart: title, category, files | 201 `{ note, appended }`; 503 when Tesseract is missing. Add Note does not call this route. |
| **POST /notes/from-images/extract** | POST | yes | Multipart: one or more image `files` | 200 `{ text, char_count, image_count }`; 400 for type/size/empty OCR; 503 when Tesseract is missing. Does not create a note. |
| **POST /notes/from-pdf/extract** | POST | yes | Multipart: single `file` (PDF) | 200 `{ text, page_count, char_count }` |
| **POST /notes/from-pptx/extract** | POST | yes | Multipart: single `file` (PPTX) | 200 `{ text, slide_count, char_count }`; 400 for invalid, empty, textless, or oversized files. Does not create a note. |
| **GET /notes** | GET | yes | Bearer; optional `?limit=500` | 200 array |
| **GET /notes/<id>** | GET | yes | Bearer | 200 or 404 |
| **PUT /notes/<id>** | PUT | yes | Bearer + partial JSON | 200 or 404 |
| **DELETE /notes/<id>** | DELETE | yes | Bearer | 200 or 404 |
| **GET /activity/** | GET | yes | Bearer; optional `?limit=50` | 200 newest-first events; default 50, maximum 100 |
| **POST /diagnostics/feedback** | POST | yes | Bearer + `operation_id`, `feature` (`ask`), `reason` (`wrong`/`unhelpful`/`harmful`/`other`) | 201 recorded metadata linked to a completed Ask operation; 404 when the operation is unknown or incomplete |
| **GET /diagnostics/events** | GET | yes (`admin` or `main_admin`) | Bearer; optional `?limit=50` | 200 newest-first content-free diagnostic events across users; 403 for `user` accounts |
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

The `/ai/ask` response also includes `memory_status` to report the best-effort Memory outcome without exposing saved content, and `operation_id` so the client can submit allow-listed answer feedback for that completed Ask operation.

## Backend checks

Run from `backend/`:

```bash
python -m compileall -q app scripts
python -m scripts.test.test_activity
python -m scripts.test.test_ai_suggestions
python -m scripts.test.test_ai_context_modes
python -m scripts.test.test_ai_credits
python -m scripts.test.test_memories
python -m scripts.test.test_remember_command
python -m scripts.test.test_ai_notes_actions
python -m scripts.test.test_pending_repository
python -m scripts.test.test_understanding_gaps
python -m scripts.test.test_diagnostics
python -m scripts.test.test_auth_roles
python -m scripts.test.test_main_admin_bootstrap
python -m scripts.test.test_auto_seed_main_admin
python -m scripts.test.test_admin_users

`test_diagnostics.py` covers automatic/fallback persistence, Ask `operation_id` responses, generic Ask failure responses, feedback ownership, duplicate feedback suppression, admin authorization, retention caps, disabled persistence, and content-free records. `python -m scripts.test.test_diagnostics_repository` checks ordering, equal timestamps, duplicate feedback, retention, invalid input, rollback, cascade delete, and secret-free database errors on SQLite. `python -m scripts.test.test_diagnostics_postgres` is the live PostgreSQL check and stays skipped until `IA_TEST_DATABASE_URL` is set. It checks the catalog, payload round-trip, concurrent retention, duplicate feedback, and lock release. `test_auth_roles.py` covers role permission helpers, `GET /auth/me`, diagnostics access for `admin` and `main_admin`, and unlimited Ask credits for operator roles. `test_auto_seed_main_admin.py` covers development-only startup seeding and production one-time startup bootstrap (empty store, skip when users exist, secret confirmation, idempotent restarts, missing credentials, dev/production refusal, concurrent seed). `test_main_admin_bootstrap.py` covers empty-store creation of the first Main Admin (hashed password, marker, login), normal registration after bootstrap, disabled bootstrap, missing initial password, existing users never overwritten, first bootstrap on an existing account, idempotent reruns, invalid configuration, operator secret and initial-password confirmation (missing, incorrect, matching), refusal messages that never echo secrets, demo refusal, marker conflicts, and concurrent bootstrap on an empty store. `test_admin_users.py` covers Main Admin list/promote authorization, `user`→`admin` promotion rules, and absence of password hashes in list responses. `test_auth_users_concurrency.py` covers concurrent registration and registration overlapping promotion in the account database. `test_auth_repository.py` covers case-sensitive usernames, stored password hashes, JWT claims without a role, `/auth/me`, rejection of a second Main Admin row, and bootstrap rollback. Those modules use SQLite and do not prove PostgreSQL cross-process bootstrap safety. `test_auth_postgres.py` runs only when `IA_TEST_DATABASE_URL` names a disposable PostgreSQL database; it refuses Neon hosts, wipes the auth tables there, and checks concurrent bootstrap. It is not part of the default suite. Frontend `askReportAnswer.test.jsx` verifies the feedback API adapter sends allow-listed reasons with the completed Ask `operation_id`.
python -m scripts.test.test_ai_response_style
python -m scripts.test.test_lazy_embeddings
python -m scripts.test.test_text_retrieval
python -m scripts.test.test_semantic_retrieval
python -m scripts.test.test_seed_user
python -m scripts.test.test_seed_render_demo
python -m scripts.test.test_settings_preferences
python -m scripts.test.test_pdf_to_note
python -m scripts.test.test_pptx_extract
python -m scripts.test.test_image_ocr
```

`python -m scripts.test.test_database` checks missing and unsupported `DATABASE_URL` values, engine settings, request rollback without an automatic commit, explicit `transaction()` commit and rollback, closed sessions that cannot run another query, and connection failures that omit credentials, URLs, and hostnames. Session behavior uses SQLite only and is not a PostgreSQL or Neon connection check. No test in this module opens a real PostgreSQL connection.

`python -m scripts.test.test_auth_repository` and the auth modules above use SQLite. `python -m scripts.test.test_notes_repository` uses that same SQLite database for note create/read/update/delete, user isolation, invalid and missing ids, empty input, rollback, append order, category/tag filters, API response shapes, and secret-free database errors. `python -m scripts.test.test_memories_repository` uses it for memory create/update/delete, deduplication, assistant-name replacement, user isolation, retrieval ranking, extraction, Ask injection, rollback, and secret-free database errors. `python -m scripts.test.test_settings_repository` uses it for default documents, merges, value types, user isolation, API shapes, invalid booleans, rollback, and secret-free database errors. `python -m scripts.test.test_credits_repository` uses it for lazy credit accounts, deductions, insufficient balance, refunds, duplicate operation results, per-user idempotency, provider-failure refund, expired pending claims, rollback, unlimited roles, cascade delete, and secret-free database errors. `python -m scripts.test.test_pending_repository` uses SQLite for create and delete confirmations, user isolation, replacement, a title that does not match, one-time consumption, expiry, invalid input, rollback, cascade delete, and secret-free database errors. `python -m scripts.test.test_pending_postgres` is the live PostgreSQL check and stays skipped until `IA_TEST_DATABASE_URL` is set. It checks the catalog, isolation, expiry, one-time consumption, concurrent consumption on separate connections, a different user proceeding while one row is locked, rollback that releases the lock, cascade delete, and secret-free database errors. `python -m scripts.test.test_auth_postgres`, `python -m scripts.test.test_notes_postgres`, `python -m scripts.test.test_memories_postgres`, `python -m scripts.test.test_settings_postgres`, `python -m scripts.test.test_credits_postgres`, `python -m scripts.test.test_activity_postgres`, `python -m scripts.test.test_diagnostics_postgres`, and `python -m scripts.test.test_pending_postgres` are the live PostgreSQL checks and stay skipped until `IA_TEST_DATABASE_URL` is set to a disposable non-Neon database. They refuse Neon hosts and refuse a URL equal to `DATABASE_URL`. They never use `DATABASE_URL` as the target. When they run, they apply Alembic through `c9a1e4f72b36` (`b7e1a2c4d5f6` for accounts, `c8a4e2b71d09` for notes, `d1e6a4c93b20` for memories, `e4b8c2d61f05` for settings, `f5c9d3e72a16` for credits, `a7d2e9f41b08` for activity, `b8e3c1a94d27` for diagnostics, then pending Ask confirmations). The activity module checks the catalog, newest-first order, equal timestamps, retention, concurrent inserts, and secret-free database errors. It also overlaps separate connections so one user's concurrent inserts stay within the retention cap, a different user is not blocked, a memory write does not wait on the activity lock, and a failed trim rolls back and releases its lock. The settings module also overlaps two connections so updates to different keys both persist and a failed merge rolls back without keeping the lock. The memories module also overlaps two connections: concurrent adds for one user both persist, one full replacement does not mix with another, a different user is not blocked, and a failed transaction rolls back and releases its lock. The credits module overlaps separate connections: concurrent deductions from one account both persist when the balance allows them, a balance that can pay only one does not go negative, the same idempotency key is claimed once, a second user with that key is not blocked, and a failed reservation rolls back and releases its row lock. The auth module checks downgrade and re-upgrade, checks that a failed upgrade does not stamp `alembic_version`, and exercises registration, roles, bootstrap, separate-connection bootstrap, the demo seed marker, and secret-free database errors. The notes module checks the notes catalog, CRUD, isolation, filters, rollback, cascade delete, API shapes, and secret-free errors.

`test_seed_user.py` checks the environment/password safety guard, repeated execution, and preservation of existing demo notes, settings, and credit balances. Notes, settings, and credits use the test database. `test_ai_credits.py` uses that database and mocks AI execution. It covers registration and lazy initialization at the configured starting balance, existing-account preservation when the initial-balance setting changes, per-user isolation, idempotent grants and ledger entries, rejection of unverified rewarded-ad grants outside dev/test, Ask spending, insufficient-credit rejection, unlimited-role behavior, refunds, JWT authentication, and rate limiting. It also verifies that completed Ask retries return the saved result without another provider call or debit, distinct IDs create distinct operations, and the same ID is isolated between users. It does not currently assert the active-pending 409 response. `test_ai_context_modes.py` covers all modes, selected IDs, missing-mode compatibility, and invalid modes. `test_text_retrieval.py` covers deterministic lexical scoring, filtering, thresholds, and token packing. `test_semantic_retrieval.py` stubs `encode_texts` with deterministic 384-dimensional vectors and uses real FAISS ranking. It checks that SentenceTransformer is not loaded, empty input skips encoding, only the supplied notes are searched, the best chunk wins, `top_n` limits results, query normalization honors `preserve_numbers`, no FAISS pickle files are opened, and semantic `build_context` uses the embeddings function while excluding `_history` notes. It does not download a model or call an external API. `test_lazy_embeddings.py` verifies model initialization is deferred, importing embeddings does not construct the removed persistent cache or open FAISS pickle files, and supplies a test-only JWT secret for app startup. Default retrieval is lexical. `MEMORY_RETRIEVAL=semantic` builds a temporary in-memory FAISS index from the authenticated user's PostgreSQL notes and discards it. Persistent Memories use lexical retrieval, not FAISS. SentenceTransformer weights may download into the local Hugging Face cache.

`test_seed_render_demo.py` uses the test database for the demo account, sample notes, settings, and credits. It verifies production environment and enable-flag rejection, missing/weak password rejection, refusal and non-modification of a pre-claimed `demo` account, marked-account rerun idempotence, sample-note creation, and preservation of the seeded account's password, role, settings, credit balance, and customized notes.

`python -m scripts.test.test_flashcards` verifies authenticated generation, selected-note ownership, request/card validation (including counts above 99 rejected before credit reservation), batched generation up to 99 cards, duplicate rejection across batches, middle-batch failure with a single refund, polling without extra charges, idempotent completed retries, startup recovery of unfinished jobs, guarded terminal operation transitions, concurrent expiry/completion behavior, idle versus max job lifetimes, worker cooperation when an operation leaves pending, provider grounding input, Retry-After waits, cancellation during cooldown, repeated HTTP 429 cooldown without spending the generation budget, adaptive batch size, job-deadline refusal, and json_schema to json_object to raw JSON fallback. `python -m scripts.test.test_flashcard_provider` verifies provider classification, uncapped Retry-After parsing (including non-finite and overflow headers), one-post 429 handling, and secret-free logs. `python -m scripts.test.test_credits_repository` adds flashcard expiry and transition regressions on SQLite. Frontend component tests cover the Ask Shortcuts placement/toggle, deck library listing, study mode (answer reveal and navigation reset), saved deck open/edit/delete confirmation, the complete new-deck flow, searchable source selection and the 20-note limit, back-navigation state retention, shared review/edit/navigation/add/remove, generation without automatic persistence, explicit create/update, and close prevention while saving (`FlashcardsPanel.test.jsx` and `activeConversation.test.jsx`).

`test_memories.py` also verifies extraction routing with mocked provider calls: supported standalone persistent assistant-name updates and recognized standalone temporary name commands skip extraction, while ambiguous and compound messages use the structured extraction request. Compound durable candidates are checked independently, and temporary, quoted, hypothetical, reported, and negated assistant-name candidates are rejected. These tests establish deterministic routing and validation behavior, not semantic accuracy from a live provider.

`test_selected_notes_context.py` is pytest-style and can be run with `python -m pytest scripts/test/test_selected_notes_context.py` if pytest is installed; pytest is not listed in `requirements.txt`.

`test_memories.py` uses temporary storage and mocked provider output. It covers the default-off persistent setting (including ignoring request-supplied enablement), user isolation, authenticated CRUD and clear-all, bounds/secrets, deterministic and model-classified assistant-name settings, several independent durable-name paraphrases, stable-key changes and legacy-record reconciliation, duplicate prevention, low-overlap name-query classification, conflicting legacy record selection, lexical fallback on classifier failure, question/hypothetical/temporary classification, compound messages that retain a durable fact but reject a temporary assistant name, grounded explicit extraction, candidate-scoped sensitive consent (including independent requests, uncertain/negated/corrected/superseded claims, unrelated people and contrast clauses, unrelated history, quoted requests, and missing/fabricated/assistant-only evidence), targeted revocation of a unique standalone sensitive record with an in-process atomic unchanged-record check, a deterministic intervening-edit regression, fail-closed handling of ambiguous matches and compound records, update/deduplication, forget requests, and relevance. Provider intent labels and retrieval key classifications are mocked; live-model semantic accuracy is not asserted and may vary by configured provider/model. `test_ai_context_modes.py` verifies Memory and Notes are independent, Off skips retrieval/extraction, enabled Memory is injected as untrusted background data, prior conversation turns are untrusted context, and extraction failures do not fail an AI response. `test_ai_credits.py` verifies the server-side setting controls Memory and that a successful Ask with Memory still reserves only one credit.

`test_understanding_gaps.py` verifies the fixed log schema, rejects unknown gap codes, proves exception/provider/OCR content is not emitted, checks privacy-sensitive log options default off, and verifies the empty-summary OCR-text fallback still saves its content. Fallback integration tests also check that Memory extraction and retrieval, suggestions, and Flashcards retain their existing outcomes while reporting fixed codes. Use [understanding-gaps.md](understanding-gaps.md) to classify new cases; provider mocks verify the fallback path, not live semantic accuracy. The persistent FAISS pickle cache and its score log have been removed. Intent-cache and dropped-note-title logs remain opt-in; detailed memory analytics persist query text and titles and should only be enabled with suitable test data.

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
| Ask !remember command | `python -m scripts.test.test_remember_command` and frontend `activeConversation.test.jsx` | Case-insensitive parse, no AI/credits/history append, settings gates, validation, save/update/unchanged/cap outcomes |
| Ask command autocomplete | `node --test src/askCommands.test.js` and `activeConversation.test.jsx` (`Ask command autocomplete`) | Registry filtering, prefix-only detection, keyboard/mouse acceptance, no submit-on-accept, disabled commands hidden, Shift+Enter newline |
| Memory failure behavior | `python -m scripts.test.test_ai_context_modes` | Extraction failure leaves normal Ask answer intact and returns unavailable status |
| Context request validation | Send invalid modes, malformed `note_ids`, or non-object JSON | 400 before operation claim or credit charge; no provider call |
| Default retrieval | Default config / `MEMORY_RETRIEVAL=text` | Deterministic lexical retrieval; no SentenceTransformer model load |
| Optional semantic retrieval | Set `MEMORY_RETRIEVAL=semantic` before starting backend and inspect `/ai/debug/context` with JWT | Temporary in-memory FAISS index built from the authenticated user's PostgreSQL notes and discarded after retrieval. The persistent pickle cache has been removed. The model loads only on first use and its weights may download into the local Hugging Face cache. |
| Credits and idempotency | Use `test_ai_credits.py` | Charge, insufficient-balance 402, role bypass, refunds, completed retry result reuse, distinct operation IDs, and per-user operation isolation match behavior |
| Rewarded ads | Use `test_ai_credits.py` | Auth is required; caller-supplied reward IDs cannot grant outside explicit development/test mode |
| JWT startup validation | Use `test_ai_credits.py` | Missing, weak, and placeholder secrets fail app creation without logging the secret |
| Screenshots | Manage → Add note → **Import screenshots**, or `python -m scripts.test.test_image_ocr` | Text appends in upload order; missing Tesseract returns 503; 8 MB per image, 32 MB total, 20 images |
| PDF import | `python -m scripts.test.test_pdf_to_note` or Manage → Add note → **Import PDF** overlay | 200 extract; save via `POST /notes/`; encrypted/blank/oversized rejected |
| PPTX import | `python -m scripts.test.test_pptx_extract` or Manage → Add note → **Import PPTX** overlay | Slide text in order; empty, corrupt, textless, and oversized files rejected; original file not stored |

## Frontend component tests

From the repository root, run:

```bash
npm --prefix .\frontend test
```

This runs the existing Node source-mode tests and the Vitest/jsdom integration tests for the real `App`, `Ask`, and route-controlled `Login` components. The mocked HTTP API exercises Notes-backed restoration and saved updates without calling an AI provider. Regressions cover Login/Register route updates without a stale first render, Ask → Manage → Ask, loading the latest messages/title, explicit New conversation, switching conversations, deleted history, out-of-order responses, logout/account isolation, and editing/resending a User turn. Notes-context coverage verifies selected Note IDs and Notes mode survive remount and the expected IDs/mode are included in the next AI request. Context-source tests cover enabled/disabled label preferences, first-render Settings → Ask restoration, navigation during a pending label save, and account changes while a Settings read is waiting.

**Admin frontend (`adminFrontend.test.jsx`, `authRoles.test.js`):** role-based nav visibility (`user` vs `admin` vs `main_admin`), redirect away from `/admin/users` for non–main-admin, user list loading/empty/error, promotion confirmation and refresh, diagnostics loading/empty/error, and safe metadata display only. Authenticated App tests mock `GET /auth/me` alongside existing endpoints.

## Frontend manual regression checklist

Run the frontend production build from the repository root:

```bash
npm --prefix .\frontend run build
```

- Logged out: direct-load `/login` and `/register`; verify register switching follows the route, registration/login still works, and success lands on `/ask`.
- Verify `/` remains public, and `/privacy`, `/terms`, and `/contact` load directly.
- Verify `/ask` is the authenticated default; navigation order is Ask, Manage, Settings, Sign out. Standard users do not see Users or Diagnostics. As `admin`, Diagnostics appears; as `main_admin`, Users and Diagnostics appear. Signed-in users can still open `/debug` directly; the debug API requires authentication.
- Navigate Ask → Manage → Settings → Ask; verify browser Back and Forward update the visible page and URL. Confirm Debug is absent from navigation but remains available to signed-in users at `/debug`.
- Select a conversation in Ask, save a new turn, navigate to Manage, then return to Ask; verify the same conversation title and latest saved turns load. Start a new conversation and repeat the navigation; verify the new empty conversation stays active instead of reopening the previous one.
- Select Notes for context and set Notes mode to Selected or Automatic. Navigate to Manage and back; verify the mode and selected Note count remain, then submit a question and verify it uses the intended Notes. Log out or switch accounts and verify the previous account's selected IDs are not applied.
- Direct-load and refresh `/ask`, `/manage`, `/debug`, `/settings`, `/admin/users`, and `/admin/diagnostics`; verify each returns the SPA and renders the correct page (or redirects to `/ask` when the role is not allowed).
- On `/manage`, switch among Notes, Conversations, and Memory. Verify Notes and Conversations expose the existing CRUD interfaces, Notes excludes `_history` and flashcard decks (`_flashcards` and legacy `flashcards`), and Memory loads persisted per-user records with working edit/delete/clear controls and setting status.
- Verify logout and an unauthorized API response return to `/login`.
- Open Ask and enter a draft. Open and close Notes/History; verify the draft and existing conversation remain intact.
- Verify the Ask shortcuts open the in-place History and Notes selectors; selecting an item closes the selector without navigating away from `/ask`. Ask selectors remain selection-only; saved-content CRUD is in Manage.
- Cancel Notes selection and verify the existing note context is unchanged. Select notes and confirm; verify the selected context updates.
- Verify the Notes selector is selection-only: no Add note shortcuts appear there. Confirm selected notes update Ask context, and verify Manage retains unified **Add note** (PDF extract optional; image OCR UI temporarily disabled).
- Verify Manage → Conversations retains title editing and single/bulk delete. In the Ask selector, start a new conversation and select an existing conversation.
- Verify a new or unset Ask context-source preference shows Conversation, Notes, and Memory only. In Settings → Ask Context Sources, verify all seven entries have their existing icons and descriptions, Conversation stays checked/disabled, and toggling another source immediately saves.
- In Settings → Ask, turn **Show Ask labels** off and immediately navigate to Ask, including while the checkbox shows Saving; confirm labels never appear in the initial toolbar. Repeat with labels enabled and navigate away/back to confirm the saved preference is honored. Using Focus must not change this setting.
- Navigate back to Ask and verify only enabled source/mode controls appear, with no gaps. Refresh or sign out/in and verify visibility persists for that user; malformed or outdated visibility settings fall back to Conversation, Notes, and Memory.
- Verify Conversation has no mode button and opens the existing History UI. Notes, Files, GitHub, Drive, and Web have separate source and mode buttons; each mode cycles `Off → Selected → Automatic → Off` without opening a menu. Memory is a persistent ON/OFF toggle, not a three-state mode. Notes Selected still uses the API's `focused` mode; Notes Off excludes note context and Automatic retains current note retrieval. Hiding and showing a source does not reset its mode or change its data or retrieval behavior.
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

## Internal suggestion event tracking

`GET /activity/` is an authenticated internal endpoint used by the suggestion overlay to fetch up to 50 newest events by default; `?limit=` accepts positive integers and is capped at 100. Events are scoped to the JWT subject. Note and flashcard-deck create/update/delete actions are recorded after successful mutations; `_history` conversations are excluded. Failed note operations do not create events. Recording remains best-effort: an activity write failure can leave a successful Note mutation without an event. Events are PostgreSQL rows.

Run the focused backend regressions from `backend/`:

```bash
python -m scripts.test.test_activity
```

`test_activity.py` verifies content-free event metadata, Note and flashcard-deck event types, `_history` exclusion, newest-first ordering, bounded limits, authentication, cross-user isolation, failed-mutation behavior, and concurrent writes without lost events. `python -m scripts.test.test_activity_repository` checks ordering, equal timestamps, retention, invalid input, rollback, and secret-free database errors on SQLite. `python -m scripts.test.test_activity_postgres` is the live PostgreSQL check and stays skipped until `IA_TEST_DATABASE_URL` is set. It checks that concurrent inserts on separate connections stay within the retention cap and that a failed trim releases the advisory lock. Frontend component tests cover authenticated suggestion generation, display, acceptance, and dismissal.

## AI Suggestions

`ai_suggestions_enabled` is stored per authenticated user through `GET/PUT /settings/`, defaults to true when absent, and is validated as a boolean. `POST /ai/suggestions` requires JWT auth and returns no suggestion when disabled or fewer than two tracked actions occurred within the last seven days. When eligible, the configured AI sees only counts of fixed internal event types and must choose an allow-listed action; no Note title/content or credential is sent. Invalid or unavailable provider output falls back to a fixed rule-based action. Suggestions do not debit IA Credits, but the configured provider may have separate usage costs.

Run focused backend regressions from `backend/`:

```bash
python -m scripts.test.test_settings_preferences
python -m scripts.test.test_ai_suggestions
```

These verify the default-on preference, saved OFF/ON behavior, per-user settings and activity isolation, authenticated-only generation, meaningful-activity threshold, metadata-only provider input, allow-listed actions, and provider-failure fallback. Frontend regressions verify authenticated-only display, setting changes, generated suggestion display, per-user dismissal, and the Flashcards/Ask/Manage accept actions.

## Final repository check

From the repository root, run `git diff --check` after reviewing the Markdown diff. The frontend build command above is `npm --prefix .\frontend run build`.
