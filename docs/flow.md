# Flow — trace by feature

Follow the code: step → where → what to look at. Index: [docs.md](docs.md). Product detail: [project.md](project.md).

---

## 1. POST /ai/ask (answer a question with optional memory)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/ai/routes.py` → `ask_ai()` | Parse `question`, optional `note_ids` via `_parse_note_ids(data)`, optional `messages` via `_parse_history_messages(data)`; call `ask(..., history_messages=...)`. |
| 2 | `backend/app/ai/engine.py` → `ask()` | Build context (notes). If `history_messages`: chat format (system + history + current question), cap 30 messages, `call_ai(..., messages=...)`. Else: single prompt, `call_ai(prompt, question=question)`. Return answer + token count. |
| 3 | `backend/app/memory/manager.py` → `build_context()` | If note_ids: filter notes to subset; use `get_relevant_notes_subset()`. Else: load user's notes; intent cache key; `get_relevant_notes_subset()` (temp FAISS); threshold filter; sort by score desc ([project.md](project.md) — score-weighted packing); dedupe; summarize long notes; trim to `MAX_CONTEXT_TOKENS`; log analytics; return dict. |
| 4 | `backend/app/memory/embeddings.py` | `get_relevant_notes_subset()`: temp FAISS index from user's notes (all or filtered by note_ids); no global cache in multi-user path. |
| 5 | `backend/app/ai/client.py` → `call_ai()` | If `messages`: `call_single(messages=...)` (chat API). Else: `call_single(prompt=...)`. Single/ensemble/judge from config. |

**estimate_tokens:** Route parses `question`, calls `engine.get_token_estimate(question)` (builds context + prompt, returns estimated_tokens, context_tokens); route jsonifies. Business logic in engine only.

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
| 1 | `backend/app/ai/routes.py` → `debug_context()` | Parse `question`; `build_context(question)`; return context, context_tokens, best_faiss_score (real score even when below threshold; see [project.md — FAISS threshold tuning](project.md#faiss-threshold-tuning)), dropped_notes. |
| 2 | Same as flow 1 steps 3–4 | `build_context` → manager → embeddings/FAISS. |

---

## 5. Memory analytics (per query)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/memory/manager.py` → `build_context()` | After building result, `log_memory_event(...)` if enabled. |
| 2 | `backend/app/memory/analytics.py` → `log_memory_event()` | If `MEMORY_ANALYTICS_ENABLED`: append one row to CSV or JSONL at `MEMORY_ANALYTICS_PATH`. |
| 3 | `backend/scripts/analyze_memory_analytics.py` | Read CSV; group by intent; compute stats, suggested threshold, and p25 percentile (3.2b); print. Run from backend: `python -m scripts.analyze_memory_analytics`. |
| 4 | `.env` + restart | Set `FAISS_THRESHOLD_LOOKUP`, `FAISS_THRESHOLD_EXPLORATORY` from script output ([project.md — FAISS threshold tuning](project.md#faiss-threshold-tuning)); restart app; re-test /ask or stress test. |

---

## 6. Auth (login; no API secret)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/auth/routes.py` | POST `/auth/register`: create user (username, password) → JWT. POST `/auth/login`: validate credentials → JWT. |
| 2 | `backend/app/common/auth.py` → `require_auth()` | Bearer token = JWT; decode with JWT_SECRET; user_id from `sub`. No API_SECRET. |
| 3 | GET `/notes/auth-check` | `auth_debug()`: returns auth_ok, header_received, header_length (no secret). |

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
| 3 | `frontend/` | React SPA. **Login page** first (sign in / register); then header + **Ask · Notes · Debug · Settings** (floating windows). Auth: JWT in localStorage; 401 → clear token and show login. Proxy: /ai, /auth, /notes, /files, /settings → backend. |
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

## 11. Ask with selected notes (chat context)

| Step | Where | What to look at |
|------|--------|------------------|
| 1 | `backend/app/ai/routes.py` → `ask_ai()` | Parse optional `note_ids: string[]` from JSON; call `ask(question, note_ids=note_ids)`. |
| 2 | `backend/app/ai/engine.py` → `ask()` | Pass `note_ids` to `build_context(question, max_tokens, note_ids)`. |
| 3 | `backend/app/memory/manager.py` → `build_context(..., note_ids=None)` | If `note_ids`: filter notes to id in set(note_ids); call `get_relevant_notes_subset()` (temp FAISS, no global cache). Else: load user's notes; build temp FAISS; same pipeline: threshold, summarization, token cap. |
| 4 | `backend/app/memory/embeddings.py` → `get_relevant_notes_subset()` | Build temporary FAISS index from subset; search; return (score, note) list; do not touch global vector_cache. |

Frontend: optional multi-select of notes in Ask; send `note_ids` with each question so "make a reviewer from these notes" uses only selected notes.

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

## 13. Ask → select conversation

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/Ask.jsx` | Ask invokes `onHistoryPicker` when the user chooses Select conversation. |
| 2 | `frontend/src/App.jsx` → `openHistoryForSelection()` | App creates a History floating window with `isSelectionMode`, the Ask window's `parentAskId`, the selection callback, and `centeredInitialPosition()`. It reuses the existing selector for that Ask when one is already open. |
| 3 | `frontend/src/components/History.jsx` | Selection mode renders conversations as selectable cards. Click or Enter/Space calls `onSelect(h.id)`. |
| 4 | `frontend/src/components/Ask.jsx` and `App.jsx` | The callback sets `currentHistoryId` in Ask; `onCloseSelection` removes the selector window. Ask then loads the conversation note and its messages. |

## 14. Ask → select notes

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/Ask.jsx` | Ask invokes `onNotesPicker` when the user chooses Load notes. |
| 2 | `frontend/src/App.jsx` → `openNotesForSelection()` | App creates a Notes floating window with `isSelectionMode`, the Ask window's `parentAskId`, the selection callback, and `centeredInitialPosition()`. It reuses the existing selector for that Ask when one is already open. |
| 3 | `frontend/src/components/Notes.jsx` | Selection mode renders notes as selectable cards. Click or Enter/Space calls `onSelect(n)`. |
| 4 | `frontend/src/components/Ask.jsx` and `App.jsx` | The callback stores the selected note in Ask, updates the selected note ID set, and `onCloseSelection` removes the selector window. The next Ask request sends the selected `note_ids`. |

## 15. New conversation

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/components/History.jsx` → `handleNew()` | History calls `createHistory("New conversation")`. |
| 2 | `frontend/src/components/History.jsx` | The created history note is appended to local state, `viewingId` is set to the created ID, and `loadHistoryList()` refreshes the list. |
| 3 | `frontend/src/components/History.jsx` | The created conversation is immediately available for viewing and receives the active `note-card--active` styling while viewed. |

## 16. Floating selector ownership

| Step | Where | What to look at |
|------|-------|------------------|
| 1 | `frontend/src/App.jsx` | Each selector stores `parentAskId`; selector windows are associated with the Ask window that opened them. |
| 2 | `frontend/src/App.jsx` | The existing-selector checks enforce one History selector and one Notes selector per Ask window. Different Ask IDs can own independent selectors. |
| 3 | `frontend/src/components/History.jsx` / `Notes.jsx` | Selection callbacks run before `onCloseSelection`, returning the selection and closing the selector. |

---

**Related docs:** [docs.md](docs.md), [ia.md](ia.md), [project.md](project.md).
