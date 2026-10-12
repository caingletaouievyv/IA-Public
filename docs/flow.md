# Flow — trace by feature

Follow the code: step → where → what to look at. Index: [docs.md](docs.md). Product detail: [project.md](project.md).

---

## 1. POST /ai/ask (authenticated answer with optional memory)

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `backend/app/ai/routes.py` → `ask_ai()` | Authenticate first with `require_auth()`. Parse JSON; reject a missing/falsey `question` and invalid `note_context_mode` with 400. Missing mode defaults to `automatic` for older clients. Normalize `note_ids` only when it is a list; normalize prior `messages` to user/assistant turns. |
| 2 | `backend/app/credits/manager.py` and `auth/manager.py` | Claim a user-scoped operation using `Idempotency-Key`, `request_id`, or a generated UUID. A completed operation returns its saved result; an active duplicate returns 409 `operation_in_progress`. Unless the persisted role matches `AI_UNLIMITED_ROLE`, reserve `AI_ASK_CREDIT_COST` before AI work. Insufficient balance returns 402 and releases the claim without calling the engine. |
| 3 | `backend/app/ai/engine.py` → `ask()` | Build note context with the authenticated `user_id`, then wrap the existing packed note text and note titles in a `ContextItem(source="notes", content=..., metadata=...)` from `backend/app/context.py`. Notes are the only implemented source; the prompt receives the same note content and instructions as before. If previous messages exist, send system instructions + up to 30 prior turns + the current question in chat format. Otherwise send one prompt. |
| 4 | `backend/app/memory/manager.py` → `build_context()` | `off` returns empty context before loading notes, even if IDs were supplied. `focused` without IDs also returns empty context without loading notes. `automatic` without IDs considers all user notes; either enabled mode with IDs filters to those selected notes. Unknown IDs yield empty context. |
| 5 | `backend/app/memory/text_retrieval.py` or `memory/embeddings.py` | `MEMORY_RETRIEVAL=text` is the default and uses deterministic weighted lexical overlap over titles, metadata, and chunked note content. `MEMORY_RETRIEVAL=semantic` opts into temporary FAISS indexes. The SentenceTransformer model is imported and initialized lazily. Explicitly selected notes are retained if no positive match is found. |
| 6 | `backend/app/ai/client.py` → `call_ai()` and `ai/routes.py` | Apply the selected retriever's threshold, then pack, summarize long notes, and cap context tokens. Call the configured provider in single/ensemble/judge mode. Return `answer` and `tokens_estimated`, and persist the successful result with the operation record. If the engine raises, refund a charged reservation and release the pending operation so a retry can run. |

**Credit and idempotency behavior:** the default ask cost is one internal AI Credit, not one provider token. The configured unlimited role bypasses reservation. A completed retry for the same authenticated user and operation ID returns the persisted response without another provider call or debit. An active duplicate gets 409. An AI exception triggers a ledger refund and releases the pending record; insufficient balance is rejected before context/provider work and also releases the record. Operation results are stored in per-user JSON under a process-local lock, not a multi-worker transactional store.

**Conversation persistence:** `Ask.jsx` loads history from a note in category `_history`, passes its previous turns in `messages`, then saves the new user/assistant pair with `PUT /notes/<history-id>`.

**`POST /ai/estimate_tokens`:** authenticate, validate `question`, parse optional `note_ids`, build context using the engine's default automatic mode, and return `estimated_tokens` plus `context_tokens`.

---

## 2. POST /notes (create note)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/notes/routes.py` → `create_note()` | `require_auth()`; parse JSON; validate with `NoteCreate`; `add_note()`. |
| 2 | `backend/app/notes/manager.py` → `add_note()` | Append to list; set id, created_at, updated_at; `save_notes()` to `data/notes_{user_id}.json`. |

---

## 3. GET /notes (list notes, optional filter)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/notes/routes.py` → `list_notes()` | `require_auth()`; parse query params; call `get_notes_list(user_id, category, tag, limit)`; jsonify. No business logic in route. |
| 2 | `backend/app/notes/manager.py` → `get_notes_list()` | Load user's notes; filter by category/tag; apply limit; return list. |
| 3 | GET `/notes/auth-check` | Debug: same auth; returns auth_ok, header_received, lengths (no secret). |

---

## 4. POST /ai/debug/context (inspect memory context for a question)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/ai/routes.py` → `debug_context()` | Authenticate, parse `question` and optional `note_ids`, then return context, context_tokens, `best_faiss_score`, and dropped_notes. The response field name is retained for compatibility; it contains the active retriever's score, including lexical scores. |
| 2 | `backend/app/memory/manager.py` | Uses the configured retriever (`text` by default, optional `semantic`) and the default automatic context mode. |

---

## 5. Memory analytics (per query)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/memory/manager.py` → `build_context()` | After building result, `log_memory_event(...)` if enabled. |
| 2 | `backend/app/memory/analytics.py` → `log_memory_event()` | If `MEMORY_ANALYTICS_ENABLED`: append one row to CSV or JSONL at `MEMORY_ANALYTICS_PATH`. |
| 3 | `backend/scripts/analyze_memory_analytics.py` | Read CSV; group by intent; compute stats, suggested threshold, and p25 percentile (3.2b); print. Run from backend: `python -m scripts.analyze_memory_analytics`. |
| 4 | `.env` + restart | For default text retrieval, set `TEXT_RETRIEVAL_THRESHOLD_LOOKUP` and `TEXT_RETRIEVAL_THRESHOLD_EXPLORATORY`; for semantic retrieval, use the `FAISS_THRESHOLD_*` settings. Restart and re-test `/ai/ask` or `/ai/debug/context`. |

---

## 6. Auth (login; no API secret)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/auth/routes.py` | POST `/auth/register`: create user (username, password) → JWT. POST `/auth/login`: validate credentials → JWT. |
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

## 7. Phase 4: Ensemble & Judge (AI_MODE)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `.env` | `AI_MODE=single` \| `ensemble` \| `judge`; optional `AI_ENSEMBLE_PROVIDERS=groq,ollama` (comma-separated; default groq). |
| 2 | `backend/app/ai/client.py` → `call_ai()` | single: `call_single(prompt, MODEL_PROVIDER)`. ensemble/judge: call each provider in `AI_ENSEMBLE_PROVIDERS`; ensemble → join with `---`; judge → `judge_answers(question, answers)` (relevance + length − clarity). |
| 3 | `backend/app/ai/client.py` → `judge_answers()` | Score each answer; deprioritize `[failed]`; return highest-scoring. |

---

## 8. Phase 5: UI (frontend)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/run.py` | Run from repo root: `cd backend && python run.py`. Loads `.env` from repo root. |
| 2 | `backend/app/__init__.py` → `create_app()` | Serves from `frontend/dist/` if built, else `frontend/`. Route `/` → `index.html`. |
| 3 | `frontend/` | React SPA. Public pages at `/`, `/privacy`, `/terms`, `/contact`; auth at `/login` and `/register`; authenticated pages at `/ask`, `/manage`, `/debug`, `/settings`. Manage reuses Notes and History for organization; Ask retains their selection workflows. Auth: JWT in localStorage; 401 → clear token and show login. Proxy: /ai, /auth, /notes, /files, /settings → backend. |
| 4 | `frontend/src/api.js` | `login()`, `register()`, `ask()`, `listNotes()`, `checkNotesAuth()`, `debugContext()`, `getSettings()`, `putSettings()`. Token from localStorage; no API secret. |

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

## 10. Notes from images (pre–Phase 7)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/notes/routes.py` → `create_note_from_images()` | `require_auth()`; multipart: title, category, files (images); call `process_images_to_note()`. |
| 2 | `backend/app/notes/image_to_note.py` → `process_images_to_note()` | OCR each image → concatenate text; `summarize_for_note(raw_text)`. If note with same title+category exists (`find_note_by_title_category`), append content with `---` and `update_note`; else `add_note()`. Returns (note, appended). |
| 3 | `backend/app/notes/manager.py` → `find_note_by_title_category()` | Return first note matching title+category; used to decide append vs create. |
| 4 | `backend/app/ai/engine.py` → `summarize_for_note()` | Prompt: summarize lazy, simple, concise, full details; `call_ai(prompt)`; return summary text. |

**Prerequisite:** Tesseract OCR installed on system (e.g. Windows: choco install tesseract; path in PATH or set in .env).

---

## 11. Ask with selected notes (context filtering)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `frontend/src/components/Ask.jsx` → `sendQuestion()` | Send selected note IDs plus the current Notes mode; Off omits IDs, and the UI's Selected mode maps to API `focused`. Prior turns from the active Conversation continue to be sent as before. Other visible source modes are placeholders and do not affect the request. |
| 2 | `backend/app/ai/routes.py` → `ask_ai()` | Parse the mode and optional `note_ids`, then pass them with the authenticated user ID to `ask()`. |
| 3 | `backend/app/memory/manager.py` → `build_context()` | `off` ignores IDs. In `focused` and `automatic`, supplied IDs restrict the candidate set to those notes. In focused mode without IDs, return empty context. If selected candidates have no positive retrieval score, include the selected candidates subject to token packing. |
| 4 | `backend/app/memory/text_retrieval.py` / `memory/embeddings.py` | Use deterministic lexical retrieval by default. Only `MEMORY_RETRIEVAL=semantic` imports the optional FAISS path; its embedding model is lazy-loaded. |

The Notes UI mode cycle is `Off → Selected → Automatic → Off`; Selected maps to the existing API mode `focused`. Automatic with no selected IDs can search all user notes; selected IDs narrow either enabled mode. Conversation remains a source-only History selector and prior turns continue to be sent as before. The Ask toolbar defaults to Conversation, Notes, and Memory; users configure source visibility in Settings, persisted through the existing per-user `/settings/` API. Context modes are saved independently in that same settings record so hiding a source does not reset its mode. Conversation is always visible, and missing or invalid visibility preferences restore the defaults. Files, GitHub, Memory, Drive, and Web modes only cycle visibly; they do not retrieve context. The Files backend route continues to provide its existing file-tree listing and is not changed here.

---

## 12. Phase 8: User-centric — login auth, notes by user, settings (implemented)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/auth/` | POST `/auth/register`, `/auth/login`; user store `data/users.json`; JWT issued (sub=user_id). |
| 2 | `backend/app/common/auth.py` | `require_auth()` validates Bearer JWT; returns user_id from `sub`. No API secret. |
| 3 | `backend/app/notes/manager.py` | `notes_{user_id}.json`; user_id from JWT (UUID). |
| 4 | `backend/app/settings/` | GET/PUT `/settings`; `data/settings_{user_id}.json`. |
| 5 | `frontend/` | Login page; token in localStorage; Sign out; all API calls use token; 401 → clear and show login. |

See [project.md](project.md) roadmap (Phase 8).

---

## 13. Manage saved content

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/App.jsx` and `backend/app/__init__.py` | Authenticated `/manage` route, navigation link, and direct-load/refresh SPA route. |
| 2 | `frontend/src/components/Manage.jsx` | Internal Notes, Conversations, and Memory sections. |
| 3 | `frontend/src/components/Notes.jsx` and `History.jsx` | Manage embeds these existing CRUD interfaces directly. Ask opens the same components in selection mode. |
| 4 | `backend/app/memory/manager.py` → `build_context()` | Memory retrieval uses relevant saved notes; there is no separate memory collection or CRUD API. |

## 14. Ask → select conversation

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/Ask.jsx` | The Conversation shortcut opens the in-place History selector; Ask remains mounted with its draft, messages, active conversation, and selected-note context. |
| 2 | `frontend/src/components/History.jsx` | Selection mode renders conversations as selectable cards. Click or Enter/Space calls `onSelect(h.id)`; creating a conversation in the selector returns its ID. Manage mode retains title and delete operations. |
| 3 | `frontend/src/components/Ask.jsx` | The callback sets `currentHistoryId` and closes the selector. Ask then loads the selected conversation note and its messages. Closing or canceling without a selection leaves the current conversation unchanged. |

## 15. Ask → select notes

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/Ask.jsx` | The Notes shortcut opens the in-place Notes selector; the Ask component remains mounted. |
| 2 | `frontend/src/components/Notes.jsx` | Selection mode renders notes as selectable cards. Click or Enter/Space toggles selection; Cancel closes without returning the temporary selection; confirmation calls `onSelect(notes)`. Note creation and image import are available in Manage, not in Ask selection mode. |
| 3 | `frontend/src/components/Ask.jsx` | On confirmation, Ask replaces its selected notes and ID set, then closes the selector. The next Ask request sends the selected `note_ids`; canceling leaves the existing context unchanged. Manage mode retains normal Notes CRUD and import operations. |

## 16. New conversation

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/History.jsx` → `handleNew()` | History calls `createHistory("New conversation")`. |
| 2 | `frontend/src/components/History.jsx` | The created history note is appended to local state, `viewingId` is set to the created ID, and `loadHistoryList()` refreshes the list. |
| 3 | `frontend/src/components/History.jsx` | The created conversation is immediately available for viewing and receives the active `note-card--active` styling while viewed. |

## 17. Ask selector ownership

Notes and History selectors are state owned by `Ask.jsx` and rendered in its page. They do not change routes or unmount Ask. The existing `History.jsx` and `Notes.jsx` selection callbacks return the chosen conversation ID or note objects; cancellation only closes the selector.

---

## 18. Edit and resend a user message

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/Ask.jsx` → `App.jsx` → `AskOverlay.jsx` | Activating a User bubble opens the full message in the shared Notes/History overlay shell. Edit switches the same overlay into edit mode and focuses its labeled textarea. Cancel returns to detail; Escape returns to detail while editing or closes from detail. |
| 2 | `frontend/src/components/Ask.jsx` | Previous/next controls navigate only User message elements, skipping assistant turns; the target is smoothly scrolled into view and focused. |
| 3 | `saveUserMessage()` → `sendQuestion()` | Save in the overlay sends the edited text through the normal Ask API flow using only messages before the edited turn; on success, the overlay remains open and shows the updated detail. |
| 4 | `sendQuestion()` → `updateNote()` | On success, save the edited user turn and new AI response to the same `_history` note. Turns after the edited message are replaced. |

There is no backend chat-edit endpoint; the frontend uses `POST /ai/ask` and the existing `PUT /notes/<id>` history update.

**Related docs:** [docs.md](docs.md), [ia.md](ia.md), [project.md](project.md).
