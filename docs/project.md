# IA — Project state & product reference

**Updated:** 2026-03-23 · **Maintenance:** Bump **Updated** when roadmap, features, or run instructions change; keep folder tree aligned with the repo.

**Documentation index:** [docs.md](docs.md).  
**Implementation agreement (principles, layers, API norms):** [ia.example.md](ia.example.md).  
**Agent rules:** [ia.example.md](ia.example.md#rules-for-ai-agents). This file is **product and stack truth** (what exists, how to run, roadmap).

---

## Conventions (quick)

- **Roadmap** — Phase table below; status Complete / Planned.  
- **Folders** — `backend/` (Flask), `frontend/` (React Vite), `docs/`.  
- **File header** — `# IA/path/to/file` first line; short docstring.  
- **Code** — Small, readable modules; one comment line per logical block.  
- **Docs** — [flow.md](flow.md) traces; [testing.md](testing.md) APIs; [ui.md](ui.md) frontend; [README.md](../README.md) demo.

---

## Clean architecture (pointer)

Layers: **Routes** → **engine/manager** → **adapters** (JSON files, FAISS, LLM client). Validation with Pydantic on the boundary. Full rules: [ia.example.md](ia.example.md#architecture-standard-ia-mapping).

---

## Tech stack

- **Python 3.10+**, **Flask** (factory + blueprints)  
- **Groq** default LLM — `AI_KEY` in `.env`; `MODEL_PROVIDER=groq`; optional `GROQ_*`  
- **Pydantic**, **python-dotenv**, **requests** / asyncio as used  
- **JSON** per-user files (`notes_{user_id}.json`, `settings_{user_id}.json`, `users.json`)  
- **Logging**, **FAISS** (semantic recall, gated thresholds), heuristic intent  
- **React 18 + Vite** — SPA, dark theme; JWT in `localStorage`  
- **OpenAI** — future optional provider  

---

## Free-tier LLM plan

| Option | Free? | Use in IA |
|--------|--------|-----------|
| **Groq (Llama)** | Yes, no card | **Primary.** `AI_KEY=<Groq key>`; [console.groq.com](https://console.groq.com). Deploy-friendly. May 429 under burst. |
| **Ollama** | Yes, local | `MODEL_PROVIDER=ollama`. Local dev; not for typical cloud deploy. |
| **DeepSeek** | Often needs billing | `MODEL_PROVIDER=deepseek` + endpoint + `AI_KEY`. |
| **OpenRouter / OpenAI** | Paid | Not in default free setup. |

---

## Folder structure

```text
IA/
├── .env                    # do not commit
├── README.md
├── docs/
│   ├── docs.md             # documentation index
│   ├── ia.example.md       # implementation agreement (tracked)
│   ├── project.md          # this file
│   ├── flow.md
│   ├── testing.md
│   └── ui.md
├── backend/
│   ├── run.py
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── ai/
│   │   ├── auth/
│   │   ├── common/
│   │   ├── files/
│   │   ├── memory/
│   │   ├── notes/
│   │   └── settings/
│   ├── data/
│   └── scripts/
│       ├── analyze_memory_analytics.py
│       ├── seed_user.py
│       └── test/
└── frontend/
    ├── vite.config.js
    └── src/  (main, App, index.css, api.js, components/)
```

---

## Key features (implemented)

- **Notes API** — CRUD, UUID, ISO8601, tag/category filter; **per user** `notes_{user_id}.json`.  
- **Auth** — POST `/auth/register`, `/auth/login` → JWT; Bearer on protected routes; `user_id` from `sub`. GET `/notes/auth-check` debug.  
- **GET /notes/meta** — `categories`, `tags` for UI autocomplete.  
- **POST /ai/ask** — context from memory; optional `note_ids`, optional `messages` (history). Auth required.  
- **POST /ai/estimate_tokens**, **POST /ai/debug/context**  
- **Model modes** — `AI_MODE`: `single` | `ensemble` | `judge`; `AI_ENSEMBLE_PROVIDERS`  
- **Token cap**, chunking, summarization, dedupe, per-query analytics → `memory_analytics.csv` when enabled  
- **POST /notes/from-images** — multipart; OCR + AI; append when same title+category  
- **Settings** — GET/PUT `/settings/` per user  
- **Stress scripts** — e.g. 500 notes / 200 queries (see testing.md)  

---

## Memory strategy

Semantic search every time; **gated by threshold**. Temp FAISS index per request on multi-user path; optional persistent cache code path exists (unused).

- **No `note_ids`** — search over all user notes.  
- **With `note_ids`** — search only within those notes.  

Pipeline: load notes → FAISS → intent → threshold → dedupe → summarize → token cap. See [flow.md](flow.md).

---

## Optimizations (recap)

Token estimation, chunking, summarization, top-k + token-limited context, adaptive thresholds per intent, score-weighted packing (manager sorts by score before packing), analytics logging.

---

## Phase 3 — Memory layer (complete)

FAISS, intent thresholds, dedupe, chunked embeddings, max context, dropped-notes logging, stress validation.

---

## Phase 4 — Ensemble and judge (complete)

- **`.env`:** `AI_MODE`, `AI_ENSEMBLE_PROVIDERS` (e.g. `groq,ollama`).  
- **Behavior:** `single` one provider; `ensemble` concatenate; `judge` heuristic best (relevance, length, clarity); failures deprioritized.  
- **Trade-off:** more cost and latency vs diversity.

---

## Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Notes API enhancements | Complete |
| 2 | AI integration | Complete |
| 3 | Memory (FAISS + gating) | Complete |
| 4 | Ensemble and judge | Complete |
| 5 | UI frontend | Complete |
| 6 | Security and monitoring | Complete |
| 7 | Mobile + monetization | Planned |
| 8 | User-centric (notes by user, settings, login UI) | Complete |

**Run:** `cd frontend && npm i && npm run build`; `cd backend && python run.py` → http://127.0.0.1:5000. **Dev:** `npm run dev` in frontend → :5174 (proxy to :5000). **Seed:** `python -m scripts.seed_user` → `testuser` / `password123`. **CORS:** `CORS_ORIGINS` in `.env`.

**Phase 6 (done):** `/health`, security headers, Flask-Limiter (e.g. 30/min on POST `/ai/ask`), structured request logging (no secrets).

---

## Project goal

Efficient personal context storage and recall; multi-provider AI; minimize token cost (summarization, chunking, memory); transparent configuration; path to web / desktop / mobile.

---

## Next steps and tuning

**Current focus:** Phase 7 when prioritized. Phase 8 and 6 are done.

### FAISS threshold tuning

Run `python -m scripts.analyze_memory_analytics` from `backend/`; set `FAISS_THRESHOLD_LOOKUP`, `FAISS_THRESHOLD_EXPLORATORY` in `.env`; restart. Use `/ai/debug/context` to inspect scores. Optional percentile `p25` from script output.

- **Notes UX** — Toolbar pattern (Back + primary action); list cards (title row, category/tags row); category prefix dropdown from meta; tags as chips; `_history` hidden in Notes, shown in History.  
- **Ask** — Optional note multi-select → `note_ids`; conversation histories as notes with category `_history`; `messages` capped (e.g. last 30) for context.  
- **History panel** — List/search, edit title, delete, bulk delete, visibility + 30s refresh (same idea as Notes list).  
- **Long-conversation strategy (proposed)** — Topic segmentation + rolling summaries + similarity merge; implement in backend manager/engine when caps demand it.  
- **Analytics** — `MEMORY_ANALYTICS_ENABLED`; CSV/JSONL for dropped notes and scores.

### Score-weighted token packing

Manager sorts FAISS matches by score descending before filling to `MAX_CONTEXT_TOKENS` (see `memory/manager.py` and flow.md).

---

## UX (summary)

Black and dark gray theme; smooth feedback; floating windows (drag, resize, collapse). Detail: [ui.md](ui.md).
