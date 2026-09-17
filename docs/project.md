| **Frontend** | React 18, Vite 5, public pages plus authenticated app, JWT in `localStorage` |
# IA — Project reference

Product and technical reference: stack, features, roadmap, and operations.

**Related:** [docs.md](docs.md) (index) · [ia.md](ia.md) (engineering agreement) · [README.md](../README.md) (quick start)

---

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, Flask, Pydantic |
| LLM | Groq (default; `AI_KEY` in `.env`) — optional Ollama, DeepSeek |
| Storage | JSON per user (`notes_{user_id}.json`, `settings_{user_id}.json`, `users.json`) |
| Memory | FAISS semantic search, intent thresholds, chunking, summarization |
| Frontend | React 18, Vite 5, JWT in `localStorage` |

### LLM providers

| Provider | Notes |
|----------|--------|
| **Groq** | Primary; free tier; [console.groq.com](https://console.groq.com) |
| **Ollama** | Local development (`MODEL_PROVIDER=ollama`) |
| **DeepSeek** | Optional; may require billing |

---

## Repository layout

```text
IA/
├── .env                 # not committed
├── README.md
├── docs/
├── backend/
│   ├── run.py
│   ├── app/             # ai, auth, credits, notes, memory, settings, …
│   ├── data/            # users, notes, settings, and per-user credit ledgers
│   └── scripts/         # seed_user, analyze_memory_analytics, test/
└── frontend/
    └── src/             # App, api.js, components/
```

---

## Features

- **Auth** — `POST /auth/register`, `/auth/login` → JWT; Bearer on protected routes.
- **Public site** — Unauthenticated landing page at `/`, plus public Privacy, Terms, and Contact pages. `/app` enters the existing authenticated app.
- **Notes** — Per-user CRUD; `GET /notes/meta` for categories/tags; `POST /notes/from-images` (OCR + AI; append when same title+category).
- **Ask** — `POST /ai/ask` with optional `note_ids` and `messages` (history); semantic search over user notes. The floating Ask window can open History and Notes in selection mode; selected conversation and note context return to Ask through callbacks.
- **AI Credits** — Backend-owned per-user balance and JSON ledger. Normal `/ai/ask` costs the configured number of internal AI Credits (default `1`); insufficient balance returns `402` before the AI provider is called. Users with the persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypass AI credit reservation and deduction, while retaining authentication and rate limits. Initial balance and development rewarded-ad grants (`REWARDED_AD_CREDIT_AMOUNT`, default `10`) are configurable. `POST /credits/rewarded-ad` is JWT-protected and idempotent by `reward_id`, but is only a development foundation and must not be exposed as a production reward mechanism until an ad provider/server verification step is integrated. Credit purchasing is not implemented. Persistence is protected by a process-local lock and is not a multi-worker transactional store.
- **Settings** — `GET/PUT /settings/` per user.
- **AI modes** — `AI_MODE`: `single` | `ensemble` | `judge`; `AI_ENSEMBLE_PROVIDERS`.
- **Monitoring** — `GET /health`, security headers, rate limits, request logging (no secrets).

---

## Memory

Semantic search on every ask; results gated by similarity threshold and token cap.

- **No `note_ids`** — search all of the user's notes.
- **With `note_ids`** — search only within selected notes.

Pipeline: load notes → FAISS → threshold → dedupe → summarize long content → enforce `MAX_CONTEXT_TOKENS`. See [flow.md](flow.md).

### FAISS threshold tuning

1. Enable `MEMORY_ANALYTICS_ENABLED=true` and run queries.
2. From `backend/`: `python -m scripts.analyze_memory_analytics`
3. Set `FAISS_THRESHOLD_LOOKUP` and `FAISS_THRESHOLD_EXPLORATORY` in `.env`; restart.
4. Use `POST /ai/debug/context` to inspect scores and dropped notes.

---

## Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| 1–4 | Notes, AI, memory, ensemble/judge | Complete |
| 5 | UI frontend | Complete |
| 6 | Security and monitoring | Complete |
| 7 | Mobile floating-window support; AI Credits | Mobile support and credit foundation implemented; development rewarded-ad callback foundation added |
| 8 | User-centric auth, per-user notes and settings | Complete |

---

## Run and deploy

```bash
cd frontend && npm i && npm run build
cd backend && pip install -r requirements.txt && python run.py
# → http://127.0.0.1:5000
```

- **Dev:** `npm run dev` in `frontend/` (port 5174, proxy to 5000).
- **Seed:** `python -m scripts.seed_user` → `testuser` / `password123`.
- **CORS:** `CORS_ORIGINS` in `.env` when frontend and API are on different origins.
- **Notes from images:** Tesseract OCR must be installed on the server.

---

## UX

Dark theme, floating windows, clear loading and error states. Ask supports selecting a conversation or notes through scoped selector windows; normal History and Notes CRUD remains available outside selection mode. Detail: [ui.md](ui.md).
