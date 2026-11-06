# Flow — trace by feature

Follow the code: step → where → what to look at. Index: [docs.md](docs.md). Product detail: [project.md](project.md).

---

## 1. POST /ai/ask (authenticated answer with optional memory)

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `backend/app/ai/routes.py` → `ask_ai()` | Authenticate first with `require_auth()`. Require a JSON object; reject a missing/falsey `question`, malformed `note_ids`, invalid `note_context_mode`, or invalid legacy `memory_context_mode` with 400. Notes mode defaults to `automatic` for older clients. When the question matches the case-insensitive `!remember` command, branch to `app/memories/remember_command.py`: require `remember_command_enabled` (default on) and `memory_enabled`, validate and persist through `save_remember_command()`, return `{ remember_command, remember_status, message, operation_id }`, and skip credit reservation, provider calls, and conversation-history persistence. Otherwise read `memory_enabled` from server-side Settings; ignore request-supplied enablement. Normalize prior `messages` to user/assistant turns. |
| 2 | `backend/app/credits/manager.py` and `auth/manager.py` | Claim a user-scoped operation using `Idempotency-Key`, `request_id`, or a generated UUID, then commit. A completed operation returns its saved result; an active duplicate returns 409 `operation_in_progress`. Unless the persisted role matches `AI_UNLIMITED_ROLE`, reserve `AI_ASK_CREDIT_COST` in a separate transaction before AI work (skipped for `!remember`). Insufficient balance returns 402 and releases the claim without calling the engine. The provider call is not inside either transaction. |
| 3 | `backend/app/ai/engine.py` → `ask()` | Build Notes context only through `app/memory/manager.py` and the supplied Notes mode. Separately, when the persisted setting is on, call `app/memories/manager.py` to retrieve relevant dedicated Memory records. `_build_system_content()` puts Notes and Memory in separate sections; Memory and prior conversation turns are untrusted context, never executable instructions. If prior messages exist, send system instructions + up to 30 turns + the current question; history is not a Memory store. |
| 4 | `backend/app/memories/manager.py` → `retrieve_memories()` | Load only the authenticated user's PostgreSQL `memories` rows, rank by lexical overlap, deduplicate, and cap at eight records / 180 estimated tokens. Stable mutable preferences are grouped by key; legacy assistant-name records are recognized from their text. If a query has no lexical match to an available keyed preference, ask the configured AI provider to classify the requested key by meaning; invalid/unavailable classification falls back to lexical retrieval. Memory OFF skips retrieval and injection. The Notes retriever is not called to obtain Memory records. |
| 5 | `backend/app/ai/client.py` → `call_ai()` | Call the configured provider in single/ensemble/judge mode and generate the normal answer. The route keeps its existing one credit reservation and operation ID. |
| 6 | `backend/app/memories/extraction.py` → `best_effort_extract()` | Only when Memory is on, classify the current message and pass bounded user-message data and existing records to structured extraction as needed. Durable facts/preferences and explicit remember/forget requests may qualify; ordinary questions, hypothetical discussions, and temporary instructions do not. Temporary scope is applied to assistant-name candidates rather than aborting extraction for the whole message, so a separate grounded durable fact can still be saved. Quoted, reported, or hypothetical assistant-name instructions remain blocked from changing the saved preference. Require JSON output, non-empty exact quoted evidence from user messages, bounded text, known IDs, intent metadata for model-classified assistant-name candidates, and explicit user intent for deletes. Obvious assistant-name settings have a deterministic fast path; other paraphrases use the configured model's intent label. Accepted names are upserted under `assistant.name`; keyed values replace prior values while legacy records are reconciled without destructive migration. Sensitive candidates require their own targeted current-message remember request; separate requests are evaluated separately, while uncertain, negated, corrected, or superseded claims are rejected. A targeted explicit sensitive-memory revocation removes only its unique, standalone matching per-user record if the manager re-reads it unchanged while holding that user's memory lock before deletion. Ambiguous, changed, and compound records fail closed without deletion; correction alone does not remove an existing record. Candidate details must be supported by the request and quote; unrelated history or quoted instructions cannot grant consent to another candidate. Reject credential/secret patterns regardless of consent, deduplicate/upsert and apply explicitly requested deletes. Extraction or storage errors produce `memory_status="unavailable"` and do not fail the answer. No additional IA credit is reserved, though model classification uses configured provider requests. |
| 7 | `backend/app/ai/routes.py` | Return `answer`, `tokens_estimated`, and a non-sensitive `memory_status`, then persist that response with the operation record in its own transaction. If normal answer generation raises, refund a charged reservation and release the pending operation, each in its own transaction, so a retry can run. |

**Credit and idempotency behavior:** the default Ask cost is one internal AI Credit, not one provider token/call. The configured unlimited role bypasses reservation. A completed retry for the same authenticated user and operation ID returns the persisted response without another call or debit. An active duplicate gets 409. An AI exception triggers a ledger refund and releases the pending record; insufficient balance is rejected before context/provider work. Memory extraction is best-effort after the main answer and makes no additional internal-credit reservation. Balances, ledger rows, and operation results are PostgreSQL rows. A balance or operation change locks that user's `credit_accounts` row until the transaction commits or rolls back. Claim, reserve, complete, refund, and release are separate transactions, so the provider call does not hold the lock. The same operation ID for a different user is a separate record. Pending claims expire after 300 seconds. A refunded debit can be reserved again with the same operation ID. Activity events, diagnostic events, and pending Ask confirmations are PostgreSQL rows. Default Notes retrieval is lexical. Optional semantic retrieval builds a temporary in-memory FAISS index from the authenticated user's PostgreSQL notes and discards it. Persistent Memories use lexical retrieval, not FAISS. The persistent pickle cache has been removed.

**Pending Ask confirmations:** `app/ai/notes_actions.py` stores one create confirmation and one delete confirmation per authenticated user in PostgreSQL `ask_pending_confirmations`. There is no confirmation UUID and no conversation id. A new save replaces that user's row of the same kind. Each row expires 900 seconds after it is saved; an expired read deletes it and Ask continues. Cancel deletes the row and returns the existing cancelled payload. A delete follow-up whose title does not match leaves the row in place. A matching delete, a successful create, and a cancel each delete the row with `SELECT … FOR UPDATE` on PostgreSQL and commit before `add_note` or `delete_note`. A second concurrent request finds no row. If note creation fails or does not execute, the create row is restored with its original expiry. The provider call is not inside the confirmation transaction. Legacy pending JSON files are not read or written. Semantic FAISS indexes are temporary memory and are discarded after retrieval. The persistent pickle cache has been removed.

**Conversation persistence:** `Ask.jsx` loads history from a note in category `_history`, passes prior turns in `messages`, then saves the new user/assistant pair with `PUT /notes/<history-id>` for normal Ask answers only. `!remember` shows a status message and does not append the command or an assistant reply. Extraction considers user turns only and never uses history as persistent Memory storage.

**`POST /ai/estimate_tokens`:** authenticate, validate `question`, parse optional `note_ids`, build context using the engine's default automatic mode, and return `estimated_tokens` plus `context_tokens`.

---

## Flashcards shortcut and generation

The Ask page's collapsible Shortcuts section opens a centered accessible overlay without navigation. The initial **Deck library** lists saved deck Notes from the authenticated user's existing Notes store (**Decks** + **New Flashcard**). **Open** enters **Study mode** (question visible, answer revealed on demand, prev/next navigation). **Edit** opens the shared review editor (deck title, per-card question/answer textareas, **Add card**, remove, navigate). **New Flashcard** opens the first generation step, where the user can search and select up to 20 non-history, non-deck Notes; the second step collects generation options (default 10 cards, maximum 99); the third step uses the same review editor for generated drafts. Back navigation retains the current selections, options, and draft edits.

Generation sends only explicitly selected note IDs with validated options to `POST /ai/flashcards/generate`. The route reserves one AI Credit, starts a background batched job (10 cards per batch), and returns `202` with an `operation_id` and batch progress. The client polls `GET /ai/flashcards/generate/<operation_id>` without charging again until the job completes or fails. The backend resolves every note ID using the authenticated user's identity, rejects unavailable/history notes, treats notes and extra instructions as untrusted prompt data, validates each batch and the final exact card count, and rejects duplicate questions across batches. Groq HTTP 429 responses wait for Retry-After instead of a 5-second cap. The wait checks pending status about every half second, so cancellation stops the cooldown without shortening that delay. Cooldown retries are separate from JSON or duplicate repairs, do not spend the eight-call batch budget, and stop when the job max or idle deadline would be exceeded. A json_validate_failed response moves the next attempt from strict json_schema to json_object, then to raw JSON. Smaller split batches do not return to a response mode Groq already rejected. Repeated rate limits shrink later batches from 10 to 5, then 2. Provider failures, validation failures, process restarts, or expired pending jobs refund the single reservation exactly once and mark the operation failed; terminal `completed` and `failed` states are guarded so they cannot flip. Job expiry uses two limits: `FLASHCARD_JOB_MAX_SECONDS` (default 600) from claim time and `FLASHCARD_JOB_IDLE_SECONDS` (default 300) from the last persisted batch progress; progress refreshes idle only, not total lifetime. Poll and worker paths check pending status under the user's credit lock before failing or completing. Completed operations return the full card list idempotently for the same user and operation ID. Run flashcard generation with one Gunicorn worker so in-process job threads and startup recovery stay coherent.

Generated cards remain an editable client-side draft. Only **Save approved deck** creates a regular Note in the user's existing Notes store (category `_flashcards`, tag `flashcards`, JSON card content). Legacy decks with category `flashcards` remain readable; saves upgrade category to `_flashcards`. Editing a saved deck updates that selected Note only after explicit **Save changes**; deleting requires confirmation and calls the existing user-scoped Notes delete API for that deck ID. Saving or deleting prevents the overlay from closing while the request is in progress. No separate deck store is used.

---

## 2. POST /notes (create note)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/notes/routes.py` → `create_note()` | `require_auth()`; parse JSON; validate with `NoteCreate`; `add_note()`. |
| 2 | `backend/app/notes/manager.py` → `add_note()` | Insert a PostgreSQL `notes` row for the JWT user; set id, created_at, updated_at. Append order is an internal `seq`. |

---

## 3. GET /notes (list notes, optional filter)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/notes/routes.py` → `list_notes()` | `require_auth()`; parse query params; call `get_notes_list(user_id, category, tag, limit)`; jsonify. No business logic in route. |
| 2 | `backend/app/notes/manager.py` → `get_notes_list()` | Load the user's notes in append order; exact category and tag filters; apply limit; return list. |
| 3 | GET `/notes/auth-check` | Debug: same auth; returns auth_ok, header_received, lengths (no secret). |

---

## 4. Memory settings and management

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `backend/app/settings/routes.py` → `put_settings_route()` | Validate `memory_enabled` is boolean; `settings/manager.py` persists it alongside existing per-user preferences. Missing setting is false. |
| 2 | `backend/app/memories/routes.py` | Authenticated list, update, delete, and clear routes derive owner from `require_auth()`. Memory IDs are resolved only inside that owner's PostgreSQL rows. |
| 3 | `backend/app/memories/manager.py` | Store records in PostgreSQL. A read-modify-write locks that user before the read and commits the replacement in the same transaction. Optional stable keys update mutable preferences. Validate lengths and recognized secrets; retrieve with a separate lexical ranker. |
| 4 | `frontend/src/components/MemoryManager.jsx` | Manage loads actual backend memories/settings, offers individual edit/delete and confirmation before clear-all, and shows loading/empty/success/error state. Ask's Memory toggle opens this section and shares the same saved setting. |

---

## 5. Memory request safeguards

`backend/app/memories/extraction.py` uses the existing AI provider client. Its system prompt treats conversation/memory fields as untrusted data, while the parser independently checks JSON shape, record length, exact evidence excerpts, known user-owned IDs, and explicit current-message forget intent. It caps input/output and returns statuses without text contents. Recognized credentials/tokens/private keys are rejected regardless of user intent; selected sensitive categories are skipped unless explicitly requested. Extraction errors are logged without record contents and converted to an unavailable status so the already-generated answer succeeds.

Supported standalone persistent assistant-name updates and recognized standalone temporary name commands take deterministic fast paths. Questions and ordinary requests that are confidently non-memory also exit without extraction. Ambiguous or compound messages use one structured extraction request; returned candidates are checked independently so temporary name instructions do not block unrelated durable candidates. These fast paths are limited to clear cases; non-obvious intent depends on model output and the existing evidence and intent validation.

---

## 6. POST /ai/debug/context (inspect Notes context for a question)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/ai/routes.py` → `debug_context()` | Authenticate, parse `question` and optional `note_ids`, then return context, context_tokens, `best_faiss_score`, and dropped_notes. The response field name is retained for compatibility; it contains the active retriever's score, including lexical scores. |
| 2 | `backend/app/memory/manager.py` | Default retrieval is lexical. `MEMORY_RETRIEVAL=semantic` builds a temporary in-memory FAISS index from the authenticated user's PostgreSQL notes and discards it. SentenceTransformer weights may download into the local Hugging Face cache. The persistent pickle cache has been removed. |

---

## 7. Memory analytics (Notes retrieval per query)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/memory/manager.py` → `build_context()` | After building result, `log_memory_event(...)` if enabled. |
| 2 | `backend/app/memory/analytics.py` → `log_memory_event()` | If `MEMORY_ANALYTICS_ENABLED`: append one row to CSV or JSONL at `MEMORY_ANALYTICS_PATH`. |
| 3 | `backend/scripts/analyze_memory_analytics.py` | Read CSV; group by intent; compute stats, suggested threshold, and p25 percentile (3.2b); print. Run from backend: `python -m scripts.analyze_memory_analytics`. |
| 4 | `.env` + restart | For default text retrieval, set `TEXT_RETRIEVAL_THRESHOLD_LOOKUP` and `TEXT_RETRIEVAL_THRESHOLD_EXPLORATORY`; for semantic retrieval, use the `FAISS_THRESHOLD_*` settings. Restart and re-test `/ai/ask` or `/ai/debug/context`. |

---

## Understanding gaps and fallback reports

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `backend/app/common/understanding_gaps.py` | `report_understanding_gap()` accepts only registered codes and logs fixed feature/category/fallback metadata plus exception class. It never logs exception text or caller content. |
| 2 | Memory extraction/retrieval, suggestions, Flashcards, and image-to-Note fallback paths | Report only observed provider, output-validation, or fallback failures. Ordinary no-candidate and no-note-match outcomes are not automatically gaps. |
| 3 | Backend logs → [understanding-gaps.md](understanding-gaps.md) | Search for `understanding_gap`, classify by code, and add sanitized expected/actual/test details to the register. Do not paste raw prompts or note data. |
| 4 | `backend/app/diagnostics/manager.py` | When `DIAGNOSTICS_ENABLED=true`, append bounded per-user PostgreSQL rows for automatic fallback/failure events and user Ask feedback linked to `operation_id`. The insert, duplicate check, and retention trim share that user's transaction advisory lock. Legacy diagnostics JSON files are not read or written. |
| 5 | `GET /diagnostics/events` or `python -m scripts.analyze_ai_diagnostics` | Admin-only metadata review. User feedback and automatic events remain content-free. |

---

## 8. Auth (login; no API secret)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/auth/routes.py` | POST `/auth/register`: create the user in PostgreSQL, then issue JWT. The credit account is created on first credit access. POST `/auth/login`: validate credentials → JWT. Roles stay in `users` and are not JWT claims. |
| 2 | `backend/app/common/auth.py` → `require_auth()` | Bearer token = JWT; decode with JWT_SECRET; user_id from `sub`. No API_SECRET. |
| 3 | GET `/notes/auth-check` | `auth_debug()`: returns auth_ok, header_received, header_length (no secret). |

`create_app()` validates `JWT_SECRET` during startup. It must have at least 32 characters and at least 8 distinct characters; missing, weak, or placeholder values raise a generic startup error. No secret value is logged or returned.

### Rewarded-ad credit callback

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `backend/app/credits/routes.py` → `rewarded_ad()` | Require a valid Bearer JWT first. The route is enabled only when `APP_ENV` is `development` or `test`; otherwise it returns 404 without granting credits. |
| 2 | `backend/app/credits/manager.py` → `grant_credits()` | In development/test only, a caller-supplied `reward_id` identifies an idempotent ledger grant; it is not proof that an ad was completed. |

Production must not grant credits from this unverified callback. A future production integration requires actual server-side verification with an ad provider before invoking the server-authoritative grant logic; no provider integration currently exists.

---

## 9. Phase 4: Ensemble & Judge (AI_MODE)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `.env` | `AI_MODE=single` \| `ensemble` \| `judge`; optional `AI_ENSEMBLE_PROVIDERS=groq,ollama` (comma-separated; default groq). |
| 2 | `backend/app/ai/client.py` → `call_ai()` | single: `call_single(prompt, MODEL_PROVIDER)`. ensemble/judge: call each provider in `AI_ENSEMBLE_PROVIDERS`; ensemble → join with `---`; judge → `judge_answers(question, answers)` (relevance + length − clarity). |
| 3 | `backend/app/ai/client.py` → `judge_answers()` | Score each answer; deprioritize `[failed]`; return highest-scoring. |

---

## 8. Phase 5: UI (frontend)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/run.py` | Run from repo root: `cd backend && python run.py`. Loads `.env` from the repository root and creates the Flask app; direct execution starts Flask's development server. |
| 2 | `backend/app/__init__.py` → `create_app()` | Serves from `frontend/dist/` if built, else `frontend/`. Route `/` → `index.html`. |
| 3 | `frontend/` | React SPA. Public pages at `/`, `/privacy`, `/terms`, `/contact`; auth at `/login` and `/register`; authenticated pages at `/ask`, `/manage`, `/debug`, `/settings`. Manage reuses Notes and History for organization; Ask retains their selection workflows. Auth: JWT in localStorage; 401 → clear token and show login. Vite proxies /ai, /auth, /notes, /memories, /activity, /files, /settings → backend at `127.0.0.1:5000`. |
| 4 | `frontend/src/api.js` | `login()`, `register()`, `ask()`, `listNotes()`, `checkNotesAuth()`, `debugContext()`, `getSettings()`, `putSettings()`, `listActivity()`, and `requestAiSuggestion()`. Token from localStorage; no API secret. |

The repository currently has no `gunicorn.conf.py`, guarded WSGI entrypoint, or cross-process lock. `backend/data/` is local JSON persistence with in-process safeguards only; it is not transactional across multiple workers or instances. Treat the documented `python run.py` command as local development, not proof of production multi-worker safety.

---

## 9. Phase 6: Security & monitoring

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/__init__.py` → `health()` | GET `/health` (no auth); returns `{"status": "ok"}` for deploy probes. |
| 2 | `backend/app/__init__.py` → `security_headers()` | `after_request`: X-Content-Type-Options nosniff, X-Frame-Options DENY, Referrer-Policy. |
| 3 | `backend/app/__init__.py` → `limiter` | Flask-Limiter: default 100/min per IP; `limiter.init_app(app)`. |
| 4 | `backend/app/ai/routes.py` → `ask_ai()` | `@limiter.limit("30 per minute")` on POST `/ai/ask`; 429 when exceeded. |
| 5 | `backend/app/__init__.py` → `request_log()` | `after_request`: log method, path, status (no secrets). |

---

## 10. Notes from images

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `frontend/src/components/Notes.jsx` | Manage → **Add note** → **Import screenshots**: one or more images → **Extract screenshot text** → review/edit Content → **Add note** via `createNote()`. |
| 2 | `frontend/src/api.js` → `extractImageText()` | Multipart `POST /notes/from-images/extract` with `files` in selection order. |
| 3 | `backend/app/notes/routes.py` → `extract_note_text_from_images()` | `require_auth()`; OCR only. Missing Tesseract returns 503. Does not create a note. |
| 4 | `backend/app/notes/image_to_note.py` → `extract_text_from_images()` | Validate type and size, call `ensure_tesseract_ready()`, then OCR in upload order. |
| 5 | `backend/app/notes/tesseract_runtime.py` | Resolve `TESSERACT_CMD` or `PATH`. Raise `OcrUnavailableError` when the binary cannot run. |

The legacy `POST /notes/from-images` route still calls `process_images_to_note()`, which summarizes with AI and creates or appends a note. Add Note does not call that route.

**Prerequisite:** Tesseract OCR installed on the system (Windows: `choco install tesseract`; path on `PATH` or `TESSERACT_CMD` in `.env`). The Docker image installs `tesseract-ocr`.

---

## 10b. Notes from PDF (text layer)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `frontend/src/components/Notes.jsx` | Manage → **Add note** → **Import PDF**: pick one file → **Extract PDF text** → review/edit Content → **Add note** via `createNote()`. |
| 2 | `frontend/src/api.js` → `extractPdfText()` | Multipart `POST /notes/from-pdf/extract`; save uses existing `POST /notes/`. |
| 3 | `backend/app/notes/routes.py` → `extract_note_text_from_pdf()` | `require_auth()`; single PDF file; call `extract_text_from_pdf()`; return `{ text, page_count, char_count }`. Does not persist the PDF or create a note. |
| 4 | `backend/app/notes/pdf_extract.py` | Validate `.pdf`, 15 MB cap, `%PDF` magic; `pypdf` page text extraction; reject encrypted, invalid, empty/image-only PDFs and text over 512k characters. |
| 5 | `backend/app/notes/routes.py` → `create_note()` | After client review, normal `NoteCreate` + `add_note()` + activity `note.created`. |

**Prerequisite:** `pypdf` in backend requirements. Scanned/image-only PDFs are out of scope (no OCR).

---

## 10c. Notes from PPTX

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `frontend/src/components/Notes.jsx` | Manage → **Add note** → **Import PPTX**: pick one `.pptx` → **Extract PPTX text** → review/edit Content → **Add note** via `createNote()`. |
| 2 | `frontend/src/api.js` → `extractPptxText()` | Multipart `POST /notes/from-pptx/extract`; save uses existing `POST /notes/`. |
| 3 | `backend/app/notes/routes.py` → `extract_note_text_from_pptx()` | `require_auth()`; one PPTX; return `{ text, slide_count, char_count }`. Does not persist the file or create a note. |
| 4 | `backend/app/notes/pptx_extract.py` | Validate `.pptx`, 15 MB cap, ZIP magic; `python-pptx` text frames, tables, and speaker notes in slide order, labeled `--- Slide N ---`. Pictures inside slides are not OCR'd. Reject empty, corrupt, textless, and over-512k extracts. |

**Prerequisite:** `python-pptx` in backend requirements.

---

## 11. Ask with Notes and persistent Memory

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `frontend/src/components/Ask.jsx` → `sendQuestion()` | Send the selected Notes mode/IDs and prior turns from the active Conversation. Memory is controlled by the persisted `memory_enabled` setting and is not a client-selected note mode. |
| 2 | `backend/app/ai/routes.py` → `ask_ai()` | Validate Notes inputs before claiming an operation/reserving credits. Derive the user ID from the JWT, then read the server-side Memory setting; request-supplied enablement is not authoritative. |
| 3 | `backend/app/ai/engine.py` → `ask()` | Build optional Notes context with the existing note retrieval manager. Separately retrieve persistent Memory only when enabled; history turns remain a third, independent context path. |
| 4 | `backend/app/memories/manager.py` → `retrieve_memories()` | Read only the authenticated user's dedicated memory file, rank by lexical overlap, deduplicate, and cap at eight records / 180 estimated tokens. No Notes or `_history` record is used as Memory. |
| 5 | `backend/app/memories/extraction.py` → `best_effort_extract()` | After the answer and only when enabled, use structured extraction from user messages, validate exact evidence/length/known IDs/secrets, then update, deduplicate, or honor explicit forget requests. Failure does not fail the answer or reserve another IA credit. |

Memory's source button opens Manage → Memory. Manage displays persisted records, the shared ON/OFF setting, individual edit/delete actions, and confirmation-protected clear-all. Notes context modes affect only Notes. Conversation History remains separate from both Notes retrieval and Memory storage. Context-source visibility remains in the existing per-user Settings record.

### Ask context preference initialization

Settings are PostgreSQL rows behind the existing per-user `GET/PUT /settings/` API. The frontend API client keeps loaded/updated Settings in an in-memory cache keyed by the JWT subject and invalidates cached values when the account changes. Ask reads that cache in its initial state so saved context-source visibility and labels are correct on the first render. If Settings are not cached, or a Settings write is still pending, Ask does not render the context toolbar until the request/write completes. No preference or credential is added to browser storage.

---

## 12. Phase 8: User-centric — login auth, notes by user, settings (implemented)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/auth/` | POST `/auth/register`, `/auth/login`; accounts in PostgreSQL; JWT issued (sub=user_id). |
| 2 | `backend/app/common/auth.py` | `require_auth()` validates Bearer JWT; returns user_id from `sub`. No API secret. |
| 3 | `backend/app/notes/manager.py` | PostgreSQL `notes` filtered by `user_id` from JWT (UUID). Note JSON files are not read. |
| 4 | `backend/app/settings/` | GET/PUT `/settings`. One PostgreSQL `settings` document per user. Settings JSON files are not read. |
| 5 | `frontend/` | Login page; token in localStorage; Sign out; all API calls use token; 401 → clear and show login. |

See [project.md](project.md) roadmap (Phase 8).

---

## 13. Manage saved content

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/App.jsx` and `backend/app/__init__.py` | Authenticated `/manage` route, navigation link, and direct-load/refresh SPA route. |
| 2 | `frontend/src/components/Manage.jsx` | Internal Notes, Conversations, and Memory sections. |
| 3 | `frontend/src/components/Notes.jsx` and `History.jsx` | Manage embeds these existing CRUD interfaces directly. Ask opens the same components in selection mode. |
| 4 | `backend/app/memories/manager.py` and `backend/app/memories/routes.py` | Memory records are PostgreSQL rows filtered by `user_id` from the JWT. Memory JSON files are not read. Authenticated CRUD routes are registered under `/memories`: `GET /memories/`, `PUT`/`DELETE /memories/<id>`, and `DELETE /memories/clear`. |

## 14. Ask → select conversation

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/Ask.jsx` | The Conversation shortcut opens the in-place History selector; Ask stays mounted while this overlay is open, so its draft, messages, active conversation, and selected-note context remain in memory. |
| 2 | `frontend/src/components/History.jsx` | Selection mode renders conversations as selectable cards. Click or Enter/Space calls `onSelect(h.id)`; creating a conversation in the selector returns its ID. Manage mode retains title and delete operations. |
| 3 | `frontend/src/components/Ask.jsx` | The callback sets `currentHistoryId` and closes the selector. Ask then loads the selected conversation note and its messages. Closing or canceling without a selection leaves the current conversation unchanged. Notes selections are similarly returned to Ask and their IDs retained in user-scoped tab state for an Ask page remount. |

## 15. Ask → select notes

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/Ask.jsx` | The Notes shortcut opens the in-place Notes selector; the Ask component remains mounted. |
| 2 | `frontend/src/components/Notes.jsx` | Selection mode renders notes as selectable cards. Click or Enter/Space toggles selection; Cancel closes without returning the temporary selection; confirmation calls `onSelect(notes)`. Note creation and image import are available in Manage, not in Ask selection mode. |
| 3 | `frontend/src/components/Ask.jsx` | On confirmation, Ask replaces its selected notes and ID set, then closes the selector. The next Ask request sends the selected `note_ids`; canceling leaves the existing context unchanged. Manage mode retains normal Notes CRUD and import operations. |

## 16. New conversation

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/History.jsx` → `handleNew()` | History calls `createHistory("New conversation")`. In Ask selection mode it returns the new ID to Ask and closes the selector; Manage mode adds it to the list and opens it for management. |
| 2 | `frontend/src/components/Ask.jsx` | Ask marks the created ID active and starts with the new note's empty messages. It does not restore the previously active conversation. |
| 3 | `frontend/src/components/History.jsx` | In Manage, the created conversation is immediately available for viewing and receives the active `note-card--active` styling while viewed. |

## 17. Ask selector and route restoration

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/App.jsx` | Page rendering is conditional: navigating from `/ask` to `/manage` unmounts `Ask`, and returning mounts a fresh component. Ask's local messages, title, and active ID therefore do not survive the page switch by themselves. |
| 2 | `frontend/src/activeConversation.js` and `frontend/src/App.jsx` | Store only the active history-note ID in `sessionStorage`, keyed by the authenticated JWT subject. Logout and account changes clear the prior user's selection; no token or message content is stored there. |
| 3 | `frontend/src/components/Ask.jsx` and `frontend/src/api.js` | On mount, read the scoped ID and use `GET /notes/<id>` to load the latest `_history` title and messages. Selecting or creating a conversation updates the saved ID; clearing the selection removes it. |
| 4 | `frontend/src/components/Ask.jsx` | Loading disables Ask and displays feedback. A missing/non-history note clears the stale ID and returns to the empty state. Cancelled requests and active-ID checks prevent an old delayed load or answer from replacing a newer selection. Selected Notes IDs are independently kept in user-scoped per-tab state; only the IDs survive navigation, while content remains in Notes and the normal `POST /ai/ask` retrieval flow. Message writes continue through the existing `PUT /notes/<id>` flow. |

## 18. Ask selector ownership

Notes and History selectors are state owned by `Ask.jsx` and rendered in its page. They do not change routes or unmount Ask. The existing `History.jsx` and `Notes.jsx` selection callbacks return the chosen conversation ID or note objects; cancellation only closes the selector.

---

## 19. Edit and resend a user message

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/Ask.jsx` → `App.jsx` → `AskOverlay.jsx` | Activating a User bubble opens the full message in the shared Notes/History overlay shell. Edit switches the same overlay into edit mode and focuses its labeled textarea. Cancel returns to detail; Escape returns to detail while editing or closes from detail. |
| 2 | `frontend/src/components/Ask.jsx` | Previous/next controls navigate only User message elements, skipping assistant turns; the target is smoothly scrolled into view and focused. |
| 3 | `saveUserMessage()` → `sendQuestion()` | Save in the overlay sends the edited text through the normal Ask API flow using only messages before the edited turn; on success, the overlay remains open and shows the updated detail. |
| 4 | `sendQuestion()` → `updateNote()` | On success, save the edited user turn and new AI response to the same `_history` note. Turns after the edited message are replaced. |

There is no backend chat-edit endpoint; the frontend uses `POST /ai/ask` and the existing `PUT /notes/<id>` history update.

## 20. Internal suggestion activity events

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `backend/app/notes/routes.py` | After a Note create/update/delete succeeds, record one fixed event. Flashcards are identified by `_flashcards` or legacy `flashcards` category. `_history` conversation-note operations are excluded. Image imports record once after the image operation succeeds, as a create or update. |
| 2 | `backend/app/activity/manager.py` | Store only `event_id`, `event_type`, fixed `description`, and a timezone-aware UTC `timestamp` in PostgreSQL `activity_events`. Retain at most 500 events per user. The insert and trim take that user's transaction advisory lock before writing and release it on commit or rollback. Equal timestamps order by the internal identity, newest insert first. No note title, content, settings, or credentials are written. |
| 3 | `backend/app/activity/routes.py` → `GET /activity/` | Internal suggestion context endpoint. Require JWT auth and derive ownership from `sub`. Return newest first, default 50 and maximum 100; reject invalid/non-positive limits. Database failures return a generic error. |

Settings and `_history` updates are not included: these events are internal suggestion context and track saved Notes and flashcard decks only. The note write and the activity insert are separate transactions. If the activity insert fails, the successful Note action remains successful and the failure is logged. Pending Ask confirmations are PostgreSQL rows in `ask_pending_confirmations`. Semantic FAISS indexes are temporary memory, built from PostgreSQL notes and discarded after retrieval. The persistent pickle cache has been removed.

## 21. Contextual AI Suggestions

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `backend/app/settings/routes.py` → `GET/PUT /settings/` | `ai_suggestions_enabled` is per-user, defaults to `true` only when no saved value exists, and accepts booleans only. OFF blocks suggestion generation at the API boundary. |
| 2 | `frontend/src/App.jsx` → `AISuggestion.jsx` | Mount the non-blocking bottom overlay only in the authenticated shell. It reads the authenticated user's internal event metadata and requests a suggestion only when at least two tracked actions occurred within seven days. Dismissal IDs are kept in local storage under the authenticated user ID. |
| 3 | `backend/app/ai/routes.py` → `POST /ai/suggestions` → `app/ai/suggestions.py` | Derive user identity from JWT `sub`, re-check the saved setting, and use only recent fixed event-type counts. The configured AI chooses one of three allow-listed actions; UI copy and behavior are fixed by the action type. Provider or output failure selects a deterministic fallback. No note text, title, or credential is included. Suggestions do not reserve IA Credits. |
| 4 | `frontend/src/App.jsx` → `Ask.jsx` / Manage | `prepare_ask` navigates to Ask, fills a draft question, and enables Automatic Notes context; the user must still submit it. `open_flashcards` opens the existing Flashcards panel. `review_activity` opens Manage with Notes selected. Accept and dismiss both suppress that activity-context suggestion for that user. |

The existing configured provider may have its own usage/billing policy even though these requests do not debit IA Credits. Only successful Note/deck API operations trigger a client-side event refresh; `_history` edits are explicitly excluded. If suggestion-event storage fails, the underlying Note mutation remains successful and a corresponding suggestion may not be generated.

**Related docs:** [docs.md](docs.md), [ia.md](ia.md), [project.md](project.md).
