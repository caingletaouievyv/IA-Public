# IA — Project reference

Product and technical reference: stack, features, roadmap, and operations.

**Related:** [docs.md](docs.md) (index) · [ia.md](ia.md) (engineering agreement) · [README.md](../README.md) (quick start)

---

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, Flask, Pydantic |
| LLM | Groq by default; Ollama, DeepSeek, and OpenAI provider entries are available in the client configuration |
| Storage | JSON files: users, per-user notes/settings, and per-user AI Credit ledgers |
| Memory | Deterministic lexical retrieval by default; optional FAISS/SentenceTransformer semantic retrieval, thresholds, chunking, summarization |
| Frontend | React 18, Vite 5, JWT in `localStorage` |

### LLM providers

| Provider | Notes |
|----------|--------|
| **Groq** | Primary; free tier; [console.groq.com](https://console.groq.com) |
| **Ollama** | Local development (`MODEL_PROVIDER=ollama`) |
| **DeepSeek** | Optional; may require billing |
| **OpenAI** | Available as a provider entry in `backend/app/ai/client.py` |

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
- **Ask** — `POST /ai/ask` requires JWT authentication and a non-empty `question`; it accepts optional `note_ids`, `note_context_mode`, and prior `messages`. The mode is per Ask window and defaults to `off` in the frontend. User turns are right-aligned and AI turns left-aligned. Only user turns can be edited inline; saving resends through the same conversation flow and replaces that turn and later turns. There is no chat-edit endpoint.
- **AI Credits** — Backend-owned per-user balance and JSON ledger. Normal `/ai/ask` costs the configured number of internal AI Credits (default `1`); insufficient balance returns `402` before the AI provider is called. Users with the persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypass AI credit reservation and deduction, while retaining authentication and rate limits. Initial balance and development rewarded-ad grants (`REWARDED_AD_CREDIT_AMOUNT`, default `10`) are configurable. `POST /credits/rewarded-ad` is JWT-protected and idempotent by `reward_id`, but is only a development foundation and must not be exposed as a production reward mechanism until an ad provider/server verification step is integrated. Credit purchasing is not implemented. Persistence is protected by a process-local lock and is not a multi-worker transactional store.
- **Conversation history** — Stored in the per-user notes file as notes with category `_history`; frontend saves turns with `PUT /notes/<id>`. The AI engine sends up to the most recent 30 prior messages to the provider.
- **Settings** — `GET/PUT /settings/` per user.
- **AI modes** — `AI_MODE`: `single` | `ensemble` | `judge`; `AI_ENSEMBLE_PROVIDERS`.
- **Monitoring** — `GET /health`, security headers, rate limits, request logging (no secrets).

---

## Memory

`MEMORY_RETRIEVAL=text` is the default. It uses deterministic lightweight lexical matching over note titles, categories, tags, and chunked content. Results are gated by the mode-specific relevance threshold and context token cap.

- **Off** — AI does not use notes; supplied `note_ids` are ignored.
- **Focused** — only explicitly selected notes are used; with no IDs, context is empty and notes are not loaded.
- **Automatic** — searches the user's notes when relevant; supplied IDs restrict the search to those notes.
- **Cycle in Ask:** `Off → Focused → Automatic → Off`.
- **Compatibility:** a missing `note_context_mode` defaults to `automatic` for older clients.

For explicitly selected notes, if lexical/semantic matching finds no positive score, the selected notes are still included subject to context packing. Otherwise the configured retriever ranks notes, then the manager applies the threshold, deduplicates, summarizes long content, and enforces `MAX_CONTEXT_TOKENS`. See [flow.md](flow.md).

### Retrieval configuration

- `MEMORY_RETRIEVAL=text` (default): deterministic weighted lexical overlap; no embedding model is loaded.
- `MEMORY_RETRIEVAL=semantic` (opt-in): uses a temporary FAISS index for the current user's candidate notes and the `sentence-transformers/all-MiniLM-L6-v2` model. Model loading is lazy. The normal manager path does not use the persistent global vector cache.
- Text and FAISS retrieval use their own lookup/exploratory thresholds. Context size is controlled by `MAX_CONTEXT_TOKENS`; both modes use `MAX_FAISS_RESULTS` as the configured top-N count.

### Retrieval threshold tuning

1. Enable `MEMORY_ANALYTICS_ENABLED=true` and run queries.
2. From `backend/`: `python -m scripts.analyze_memory_analytics`
3. Set `TEXT_RETRIEVAL_THRESHOLD_LOOKUP` / `TEXT_RETRIEVAL_THRESHOLD_EXPLORATORY` for the default path, or `FAISS_THRESHOLD_LOOKUP` / `FAISS_THRESHOLD_EXPLORATORY` for semantic retrieval; restart.
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
- **Seed:** `python -m scripts.seed_user` → `ayi` / `Ayi!23`. The command preserves an existing `ayi` account and notes and only adds missing demo notes.
- **CORS:** `CORS_ORIGINS` in `.env` when frontend and API are on different origins.
- **Notes from images:** Tesseract OCR must be installed on the server.
- **Runtime:** the repository selects Python `3.13.5` in `.python-version`; the frontend package version is `0.0.1`. Flask serves `frontend/dist` when it exists, otherwise it serves the frontend directory. `/health` is unauthenticated. Vite development proxies `/ai`, `/auth`, `/notes`, `/files`, and `/settings` to the backend; the frontend API can use `VITE_API_BASE_URL` for a separate API origin.
- **Deployment configuration:** the tracked repository contains no provider-specific backend deployment manifest. The frontend includes a static-host SPA fallback in `frontend/public/_redirects`; actual frontend/backend hostnames, build commands, and secret values are deployment-specific and are not specified here.

---

## UX

Dark theme, floating windows, shared button hierarchy, and clear loading and error states. Ask has Conversation and Notes shortcuts plus the note-context mode control. Conversation history starts expanded; user messages can be edited inline and resent using the existing conversation update flow. Detail: [ui.md](ui.md).
