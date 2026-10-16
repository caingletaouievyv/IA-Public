# IA

Personal notes and AI assistant with memory. Store notes (including from images), ask questions with context from your notes, and manage conversations per user.

**Documentation:** [docs/docs.md](docs/docs.md) · **Quick start below**

---

## Features

- **Notes** — CRUD per user; filter by category and tag; import from images (OCR + AI summary).
- **Ask** — Ask with optional Notes context, independent persistent Memory, and conversation history. Memory is a per-user ON/OFF setting: when on, IA may extract useful stable details and retrieve relevant saved memories; when off, it neither retrieves nor automatically saves. Notes and Conversation History remain separate. A separate Focus button beside the non-interactive Conversation History heading opens a work-only view, hiding the app header and Ask shortcuts while keeping the history, question form, and Ask button available. AI responses have a per-message Copy button that copies readable plain text. User turns appear as right-aligned, compact previews; activating one opens its full message in the shared Ask overlay. Edit switches that same overlay into edit mode; saving uses the existing conversation flow and replaces that turn and all later turns. AI turns remain left-aligned. Compact previous/next controls navigate only User turns.
- **Auth** — Register and sign in; protected API routes use a Bearer JWT. `JWT_SECRET` is required at Flask startup; it must be at least 32 characters with at least 8 distinct characters. Missing, weak, or placeholder values stop startup. No secret value belongs in source control or the UI.
- **Memory** — Separate persistent per-user JSON records under `backend/data/`. Memory is off by default. When enabled, it may save grounded user preferences/facts from conversations and retrieve relevant records under a bounded prompt budget. `/manage` lists, edits, deletes, and clears the user's actual memories. It does not use Notes or conversation history as its storage.
- **AI Credits** — Backend-owned internal credits; normal Ask costs the configured credit amount (default `1`). Users with the persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypass Ask credit consumption. Initial credits and ledger entries are persisted per user. The JWT-protected `/credits/rewarded-ad` callback accepts unverified reward IDs only in explicit `APP_ENV=development` or `APP_ENV=test`; it is disabled in production. A production reward flow requires server-side ad-provider verification first.
- **UI** — React/Vite SPA with a dark page-based authenticated shell at `/ask`, `/manage`, `/debug`, and `/settings`. Manage reuses the existing Notes and Conversations interfaces and provides independent Memory controls and CRUD.

---

## Quick start

**Requirements:** Python 3.10+, Node 18+, `.env` at repo root.

```bash
# 1. Environment (repo root)
# Set JWT_SECRET to a random value of at least 32 characters, with at least 8 distinct characters.
# AI_KEY=your-provider-key   # Groq by default; see backend/app/config.py

# 2. Frontend
cd frontend
npm install
npm run build
cd ..

# 3. Backend
cd backend
pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:5000** — sign in or register.

**Optional demo user** (development/test only; run from `backend/`):

Set `APP_ENV=development` and `SEED_USER_PASSWORD` in your local, ignored root `.env`.
Use a unique password of at least 12 characters; do not copy a real account password.

```bash
python -m scripts.seed_user
```

The seed refuses to run outside `APP_ENV=development` or `APP_ENV=test`, and refuses
an unset or too-short `SEED_USER_PASSWORD`. It is safe to rerun: it does not change an
existing `demo` account's password and only adds missing demo notes. Existing `ayi`
accounts are left untouched.

**Development:** run `python run.py` from `backend/`, then run `npm run dev` from `frontend/` → http://127.0.0.1:5174. Vite proxies `/ai`, `/auth`, `/notes`, `/memories`, `/files`, and `/settings` to port 5000.

**Runtime/deployment:** `npm run build` writes `frontend/dist`. When that built directory exists, Flask serves it (including Vite assets); otherwise Flask serves the frontend directory. `GET /health` is available without authentication. The tracked repository has no provider-specific backend deployment manifest; a separately hosted frontend can set `VITE_API_BASE_URL` and configure backend `CORS_ORIGINS`.
`backend/data/` contains local per-user and generated runtime files and is ignored by Git; do not commit its contents.

The backend currently uses local JSON files under `backend/data/` for runtime and per-user data. Start it for local development with `python run.py` from `backend/`; `run.py` creates the Flask app and enables the development server when executed directly. The repository does not currently include a Gunicorn configuration or cross-process lock. Do not assume the JSON stores are safe for multiple workers, multiple backend instances, or shared/network filesystems; their in-process safeguards do not make multi-step operations transactional. `backend/data/` is ignored by Git and must not be committed.

### Ask and memory behavior

- `POST /ai/ask` requires a valid JWT and a non-empty `question`. It accepts optional `note_context_mode`, `note_ids`, and prior `messages`. Memory enablement is read from the authenticated user's saved Settings, never from a request-supplied user or mode.
- Note context modes are `Off` (no notes), `Selected` (the API's `focused` mode; selected notes only), and `Automatic` (search all user notes when relevant, or selected notes only when IDs are supplied). The Ask Notes mode button cycles `Off → Selected → Automatic → Off`; the API mode name remains `focused`.
- Conversation is a source-only button in Ask and continues sending the active conversation's prior turns. Notes has its existing independent context modes. Memory has an ON/OFF button that persists `memory_enabled` in per-user Settings and controls both automatic extraction and retrieval. Its source button opens Memory management. Other source modes are visual placeholders and do not retrieve context.
- The Ask toolbar shows Conversation, Notes, and Memory by default. Visibility for all seven sources and **Show context source labels** are saved in the authenticated user's existing Settings. Ask initializes from the user-scoped in-memory Settings cache when available and waits for any pending Settings save before showing its context controls, preventing stale labels from flashing on navigation. Conversation is always visible; hiding a source only hides its controls and does not reset its saved mode or affect data or retrieval.
- Conversations are notes in the user's note store with category `_history`. The backend accepts up to 30 prior messages for a provider call. Conversation History is passed to the AI separately and is not Memory storage. The active conversation ID is kept in `sessionStorage` for the current tab, scoped to the authenticated user; when Ask mounts again it loads the latest title and messages from that existing note. Selected Notes IDs are also retained for the tab and user, while their content is loaded through the existing Notes API when needed. Logout clears both selections, and deleted conversation IDs fall back to the empty Ask state. Notes modes and source visibility remain in per-user Settings; drafts remain transient. Files has no Ask context flow, and GitHub, Drive, and Web context integrations are placeholders.
- Manage at `/manage` organizes saved Notes and Conversations by reusing the existing CRUD interfaces and provides independent Memory CRUD. Memory is stored separately in `memories_<user-hash>.json`; `memory_enabled` defaults to false. Manage and Ask both display the persisted setting. Extraction uses the configured AI provider in a best-effort structured pass; failure does not fail the answer. Extracted items require quoted user-message evidence, are bounded and deduplicated, and secret patterns are rejected. Context injection treats memories as untrusted background facts and is relevance/token bounded.
- Ask operations use a user-scoped `operation_id` from `Idempotency-Key`, `request_id`, or a generated ID. A request with the same user and operation ID after completion returns the persisted result without another provider call or charge; an active duplicate returns 409. Insufficient-credit rejections and AI execution failures release their pending record so they can be retried. This JSON-backed state uses a process-local lock and is not transactional across multiple workers.
- Normal users are charged the configured AI Credit cost for Ask (default 1, with 10 initial credits); a failed AI call refunds the reservation. A persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypasses the charge. Rewarded-ad credit grants are a development foundation, not a provider-verified production flow. There is no credit balance UI.
- Notes retrieval remains in its existing lexical/optional semantic engine. Independent Memory uses a small deterministic lexical relevance ranker over the authenticated user's dedicated memory records and injects at most eight records within a 180-token budget. Memory OFF skips both retrieval and extraction; disabling it preserves stored records. Each Ask still has only its normal single credit reservation; extraction adds no internal IA credit charge.

---

## API overview

| Area | Endpoints |
|------|-----------|
| Auth | `POST /auth/register`, `POST /auth/login` |
| Notes | `GET/POST /notes/`, `GET/PUT/DELETE /notes/<id>`, `POST /notes/from-images` |
| Memory | `GET /memories/`, `PUT/DELETE /memories/<id>`, `DELETE /memories/clear` |
| AI | `POST /ai/ask`, `POST /ai/estimate_tokens`, `POST /ai/debug/context` |
| Credits | `POST /credits/rewarded-ad` (development foundation; JWT required) |
| Settings | `GET/PUT /settings/` |
| Health | `GET /health` (no auth) |

All protected routes: `Authorization: Bearer <JWT>`. Details and curl examples: [docs/testing.md](docs/testing.md).

---

## Frontend checks

Run the React component regressions and existing source-mode unit tests with `npm --prefix .\frontend test`. These tests mock the Notes and AI HTTP responses; no live AI provider is required. Build the production frontend with `npm --prefix .\frontend run build`.

## Documentation

| Document | Description |
|----------|-------------|
| [docs/docs.md](docs/docs.md) | Index of all docs |
| [docs/project.md](docs/project.md) | Stack, roadmap, features, configuration |
| [docs/ia.md](docs/ia.md) | Engineering agreement (architecture, security, testing standards) |
| [docs/flow.md](docs/flow.md) | Code flow traces |
| [docs/testing.md](docs/testing.md) | Testing and API reference |
| [docs/ui.md](docs/ui.md) | Frontend UX |

---

## License

See repository license file if present.
