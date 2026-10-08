# IA — Project reference

Product and technical reference: stack, features, roadmap, and operations.

**Related:** [docs.md](docs.md) (index) · [ia.md](ia.md) (engineering agreement) · [README.md](../README.md) (quick start)

---

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, Flask, Pydantic |
| LLM | Groq by default; Ollama, DeepSeek, and OpenAI provider entries are available in the client configuration |
| Storage | Local runtime JSON files: users, per-user notes/settings, AI Credit ledgers, and Ask operation results; `backend/data/` is ignored by Git |
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

- **Auth** — `POST /auth/register`, `/auth/login` → JWT; Bearer on protected routes. `JWT_SECRET` is required when `create_app()` starts, must be at least 32 characters with at least 8 distinct characters, and rejects missing, weak, or placeholder values. No default signing secret is used.
- **Public site** — Unauthenticated landing page at `/`, plus `/privacy`, `/terms`, and `/contact`. Auth routes are `/login` and `/register`; authenticated pages are `/ask`, `/debug`, and `/settings`, with `/ask` as the default.
- **Notes** — Per-user CRUD; `GET /notes/meta` for categories/tags; `POST /notes/from-images` (OCR + AI; append when same title+category).
- **Ask** — `POST /ai/ask` requires JWT authentication and a non-empty `question`; it accepts optional `note_ids`, `note_context_mode`, and prior `messages`. The Ask header shows Conversation, Notes, Files, GitHub, Memory, Drive, and Web. Conversation is a source-only control that opens the existing History UI and continues sending active conversation turns as before. Notes, Files, GitHub, Memory, Drive, and Web each have separate source and mode buttons; modes cycle `Off → Selected → Automatic → Off`. Notes defaults to Off; Selected maps to the existing API mode `focused`, and Automatic retains current note retrieval. Notes are the Context Layer's first and only implemented AI context source; the other listed sources are UI placeholders and their modes do not retrieve context. The `/files` endpoint lists a file tree, but no Ask file-selection or file-context flow is implemented. Notes selection/management and conversation history/management remain in-place Ask workflows, not top-level pages. AI turns are left-aligned; user turns appear as right-aligned compact bubbles. Selecting a user bubble opens its complete message in the shared Ask overlay. Edit switches that same overlay to a labeled edit form; Cancel returns to detail, Escape returns to detail while editing and closes from detail, and Save uses the existing inline edit/resend flow. Compact previous/next controls navigate only User messages, skipping AI turns. Saving an edit resends through the same conversation flow and replaces that turn and later turns. There is no chat-edit endpoint.
- **AI Credits** — Backend-owned per-user balance and JSON ledger. Normal `/ai/ask` costs the configured number of internal AI Credits (default `1`); insufficient balance returns `402` before the AI provider is called. Users with the persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypass AI credit reservation and deduction, while retaining authentication and rate limits. Initial balance and development/test rewarded-ad grants (`REWARDED_AD_CREDIT_AMOUNT`, default `10`) are configurable. `POST /credits/rewarded-ad` requires JWT auth and is enabled only for `APP_ENV=development` or `APP_ENV=test`; its caller-supplied reward ID is not provider verification. It is disabled in production, where a server-side ad-provider verification step is required before granting credits. Credit purchasing is not implemented. JSON persistence and its lock are process-local and are not a multi-worker transactional store.
- **Ask idempotency** — Each authenticated user's `operation_id` is stored with that user's credit account. It comes from `Idempotency-Key`, `request_id`, or a generated UUID. A completed retry returns the stored response without another provider call or debit; a currently pending duplicate returns `409 operation_in_progress`. Insufficient-credit and failed-provider operations release their pending record so they can be retried. The state uses the per-user JSON file and process-local lock; concurrent multi-worker coordination is not transactional.
- **Conversation history** — Stored in the per-user notes file as notes with category `_history`; frontend saves turns with `PUT /notes/<id>`. The AI engine sends up to the most recent 30 prior messages to the provider.
- **Settings** — `GET/PUT /settings/` per user.
- **AI modes** — `AI_MODE`: `single` | `ensemble` | `judge`; `AI_ENSEMBLE_PROVIDERS`.
- **Monitoring** — `GET /health`, security headers, rate limits, request logging (no secrets).

---

## Memory

`MEMORY_RETRIEVAL=text` is the default. It uses deterministic lightweight lexical matching over note titles, categories, tags, and chunked content. Results are gated by the mode-specific relevance threshold and context token cap.

- **Off** — AI does not use notes; supplied `note_ids` are ignored. The Ask UI omits those IDs when Off.
- **Selected** (API mode `focused`) — only explicitly selected notes are used; with no IDs, context is empty and notes are not loaded.
- **Automatic** — searches the user's notes when relevant; supplied IDs restrict the search to those notes.
- **Notes cycle in Ask:** `Off → Selected → Automatic → Off`. The UI's Selected mode maps to API `focused`; the API contract remains unchanged. Other visible context-source placeholders cycle display state only and do not affect retrieval.
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
| 7 | Mobile support; AI Credits | Mobile support and credit foundation implemented; development rewarded-ad callback foundation added |
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
- **Runtime:** the repository selects Python `3.13.5` in `.python-version`; the frontend package version is `0.0.1`. Flask serves `frontend/dist` when it exists, otherwise it serves the frontend directory. `/health` is unauthenticated. Vite development proxies `/ai`, `/auth`, `/notes`, `/files`, and `/settings` to the backend; the frontend API can use `VITE_API_BASE_URL` for a separate API origin. `backend/data/` is local runtime/user data and generated AI-memory output, ignored by Git and not a source-controlled dataset.
- **Deployment configuration:** the tracked repository contains no provider-specific backend deployment manifest. The frontend includes a static-host SPA fallback in `frontend/public/_redirects`; actual frontend/backend hostnames, build commands, and secret values are deployment-specific and are not specified here.

---

## UX

Dark theme, page-based authenticated shell (`/ask`, `/debug`, `/settings`), shared button hierarchy, and clear loading and error states. Ask shows Conversation, Notes, Files, GitHub, Memory, Drive, and Web; Conversation is source-only, Notes has the implemented context mode, and the other modes are display-only placeholders. Ask has no file-selection/context flow despite the backend file-tree endpoint. Conversation history starts expanded, with right-aligned compact user bubbles that open a full-message detail in the shared Ask overlay. Edit switches the same overlay to edit mode; Cancel returns to detail and Save uses the existing conversation update flow. Previous/next controls navigate only User messages. Detail: [ui.md](ui.md).
