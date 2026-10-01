# IA

Personal notes and AI assistant with memory. Store notes (including from images), ask questions with context from your notes, and manage conversations per user.

**Documentation:** [docs/docs.md](docs/docs.md) · **Quick start below**

---

## Features

- **Notes** — CRUD per user; filter by category and tag; import from images (OCR + AI summary).
- **Ask** — Ask with optional note context and conversation history. User turns are right-aligned and AI turns are left-aligned. Edit a user turn inline; saving resends it through the current conversation and replaces that turn and all later turns.
- **Auth** — Register and sign in; protected API routes use a Bearer JWT (no API secret in the UI).
- **Memory** — Deterministic lexical retrieval is the default (`MEMORY_RETRIEVAL=text`). Optional semantic retrieval uses FAISS and SentenceTransformers; its model loads lazily.
- **AI Credits** — Backend-owned internal credits; normal Ask costs the configured credit amount (default `1`). Users with the persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypass Ask credit consumption. Initial credits and ledger entries are persisted per user. A development-only JWT-protected rewarded-ad callback grants the configured amount (default `10`) idempotently by `reward_id`; provider/server verification is still required for production.
- **UI** — React/Vite SPA, dark theme, floating Ask, Notes, History, Debug, and Settings windows, with shared primary, subtle, destructive, and icon button styles.

---

## Quick start

**Requirements:** Python 3.10+, Node 18+, `.env` at repo root.

```bash
# 1. Environment (repo root)
# JWT_SECRET=your-secret
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
# ayi / Ayi!23
```

The seed is safe to rerun: it keeps an existing `ayi` account and notes, and only adds missing demo notes.

**Development:** run `python run.py` from `backend/`, then run `npm run dev` from `frontend/` → http://127.0.0.1:5174. Vite proxies `/ai`, `/auth`, `/notes`, `/files`, and `/settings` to port 5000.

**Runtime/deployment:** `npm run build` writes `frontend/dist`. When that built directory exists, Flask serves it (including Vite assets); otherwise Flask serves the frontend directory. `GET /health` is available without authentication. The tracked repository has no provider-specific backend deployment manifest; a separately hosted frontend can set `VITE_API_BASE_URL` and configure backend `CORS_ORIGINS`.

### Ask and memory behavior

- `POST /ai/ask` requires a valid JWT and a non-empty `question`. It accepts optional `note_context_mode`, `note_ids`, and prior `messages`; missing mode remains compatible with older clients by using `automatic`.
- Note context modes are `Off` (no notes; IDs ignored), `Focused` (selected notes only), and `Automatic` (search all user notes when relevant, or selected notes only when IDs are supplied). The Ask shortcut cycles `Off → Focused → Automatic → Off`.
- Conversations are notes in the user's note store with category `_history`. Ask sends previous turns as chat history; the backend accepts up to 30 prior messages for a provider call.
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
