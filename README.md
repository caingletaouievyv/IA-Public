# IA

Personal notes and AI assistant with semantic memory. Store notes (including from images), ask questions with context from your notes, and manage conversations per user.

**Documentation:** [docs/docs.md](docs/docs.md) · **Quick start below**

---

## Features

- **Notes** — CRUD per user; filter by category and tag; import from images (OCR + AI summary).
- **Ask** — Semantic search over your notes; optionally select notes and conversations through the UI; conversation history.
- **Auth** — Register and sign in; JWT for API access (no API secret in the UI).
- **Memory** — FAISS-based retrieval with thresholds, chunking, summarization, and token limits.
- **AI Credits** — Backend-owned internal credits; normal Ask costs the configured credit amount (default `1`). Users with the persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypass Ask credit consumption. Initial credits and ledger entries are persisted per user. A development-only JWT-protected rewarded-ad callback grants the configured amount (default `10`) idempotently by `reward_id`; provider/server verification is still required for production.
- **UI** — React SPA, dark theme, floating panels (Ask, Notes, History, Debug, Settings).

---

## Quick start

**Requirements:** Python 3.10+, Node 18+, `.env` at repo root.

```bash
# 1. Environment (repo root)
# JWT_SECRET=your-secret
# AI_KEY=your-groq-key   # https://console.groq.com

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

**Development:** `cd frontend && npm run dev` → http://127.0.0.1:5174 (proxies API to port 5000).

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
