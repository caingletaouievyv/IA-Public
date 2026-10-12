# IA

Personal notes and AI assistant with memory. Store notes (including from images), ask questions with context from your notes, and manage conversations per user.

**Documentation:** [docs/docs.md](docs/docs.md) · **Quick start below**

---

## Features

- **Notes** — CRUD per user; filter by category and tag; import from images (OCR + AI summary).
- **Ask** — Ask with optional note context and conversation history. The toolbar shows Conversation, Notes, and Memory by default; per-user Settings control visibility of the other context sources, while Conversation remains required. A separate Focus button beside the non-interactive Conversation History heading opens a work-only view, hiding the app header and Ask shortcuts while keeping the history, question form, and Ask button available. Use Focus again to restore the normal layout. AI responses have a per-message Copy button that copies readable plain text. User turns appear as right-aligned, compact previews; activating one opens its full message in the shared Ask overlay. Edit switches that same overlay into edit mode; saving uses the existing conversation flow and replaces that turn and all later turns. AI turns remain left-aligned. Compact previous/next controls navigate only User turns.
- **Auth** — Register and sign in; protected API routes use a Bearer JWT. `JWT_SECRET` is required at Flask startup; it must be at least 32 characters with at least 8 distinct characters. Missing, weak, or placeholder values stop startup. No secret value belongs in source control or the UI.
- **Memory** — Deterministic lexical retrieval is the default (`MEMORY_RETRIEVAL=text`). Optional semantic retrieval uses FAISS and SentenceTransformers; its model loads lazily.
- **AI Credits** — Backend-owned internal credits; normal Ask costs the configured credit amount (default `1`). Users with the persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypass Ask credit consumption. Initial credits and ledger entries are persisted per user. The JWT-protected `/credits/rewarded-ad` callback accepts unverified reward IDs only in explicit `APP_ENV=development` or `APP_ENV=test`; it is disabled in production. A production reward flow requires server-side ad-provider verification first.
- **UI** — React/Vite SPA with a dark page-based authenticated shell at `/ask`, `/manage`, `/debug`, and `/settings`. Manage reuses the existing Notes and Conversations interfaces; its Memory section explains that retrieval currently uses saved notes.

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

**Optional demo user** (from `backend/`):

```bash
python -m scripts.seed_user
# demo / 12345678
```

The seed is safe to rerun: an existing `demo` account's password and notes are not
overwritten, and only missing demo notes are added. An existing `ayi` account is
left untouched.

**Development:** run `python run.py` from `backend/`, then run `npm run dev` from `frontend/` → http://127.0.0.1:5174. Vite proxies `/ai`, `/auth`, `/notes`, `/files`, and `/settings` to port 5000.

**Runtime/deployment:** `npm run build` writes `frontend/dist`. When that built directory exists, Flask serves it (including Vite assets); otherwise Flask serves the frontend directory. `GET /health` is available without authentication. The tracked repository has no provider-specific backend deployment manifest; a separately hosted frontend can set `VITE_API_BASE_URL` and configure backend `CORS_ORIGINS`.
`backend/data/` contains local per-user and generated runtime files and is ignored by Git; do not commit its contents.

### Ask and memory behavior

- `POST /ai/ask` requires a valid JWT and a non-empty `question`. It accepts optional `note_context_mode`, `note_ids`, and prior `messages`; missing mode remains compatible with older clients by using `automatic`.
- Note context modes are `Off` (no notes), `Selected` (the API's `focused` mode; selected notes only), and `Automatic` (search all user notes when relevant, or selected notes only when IDs are supplied). The Ask Notes mode button cycles `Off → Selected → Automatic → Off`; the API mode name remains `focused`.
- Conversation is a source-only button in Ask and continues sending the active conversation's prior turns. Notes, Files, GitHub, Memory, Drive, and Web each have independent mode buttons. Notes is the only implemented AI context source; its Selected UI mode maps to API `focused`. Other source modes are visual placeholders and do not retrieve context.
- The Ask toolbar shows Conversation, Notes, and Memory by default. Visibility for all seven sources is configurable in **Settings → Ask Context Sources** and is saved with the authenticated user's existing settings. Conversation is always visible; hiding a source only hides its controls and does not reset its saved mode or affect data or retrieval.
- Conversations are notes in the user's note store with category `_history`. The backend accepts up to 30 prior messages for a provider call. The backend `/files` endpoint lists a file tree, but Ask does not currently provide file selection or file context; GitHub, Drive, and Web context integrations are not implemented. Memory retrieval remains part of Notes Automatic mode, not a separate source.
- Manage at `/manage` organizes saved Notes and Conversations by reusing the existing CRUD interfaces. Memory is not an independent editable store; relevant saved notes currently provide information for retrieval.
- Ask operations use a user-scoped `operation_id` from `Idempotency-Key`, `request_id`, or a generated ID. A request with the same user and operation ID after completion returns the persisted result without another provider call or charge; an active duplicate returns 409. Insufficient-credit rejections and AI execution failures release their pending record so they can be retried. This JSON-backed state uses a process-local lock and is not transactional across multiple workers.
- Normal users are charged the configured AI Credit cost for Ask (default 1, with 10 initial credits); a failed AI call refunds the reservation. A persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypasses the charge. Rewarded-ad credit grants are a development foundation, not a provider-verified production flow. There is no credit balance UI.
- Note retrieval is lightweight deterministic lexical matching by default. Set `MEMORY_RETRIEVAL=semantic` to opt into semantic FAISS retrieval; the SentenceTransformer model is loaded only when needed.

---

## API overview

| Area | Endpoints |
|------|-----------|
| Auth | `POST /auth/register`, `POST /auth/login` |
| Notes | `GET/POST /notes/`, `GET/PUT/DELETE /notes/<id>`, `POST /notes/from-images` |
| AI | `POST /ai/ask`, `POST /ai/estimate_tokens`, `POST /ai/debug/context` |
| Credits | `POST /credits/rewarded-ad` (development foundation; JWT required) |
| Settings | `GET/PUT /settings/` |
| Health | `GET /health` (no auth) |

All protected routes: `Authorization: Bearer <JWT>`. Details and curl examples: [docs/testing.md](docs/testing.md).

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/docs.md](docs/docs.md) | Index of all docs |
| [docs/project.md](docs/project.md) | Stack, roadmap, features, configuration |
| [docs/ia.md](docs/ia.md) | Engineering agreement (architecture, API standards) |
| [docs/flow.md](docs/flow.md) | Code flow traces |
| [docs/testing.md](docs/testing.md) | Testing and API reference |
| [docs/ui.md](docs/ui.md) | Frontend UX |

---

## License

See repository license file if present.
