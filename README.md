# IA

Personal developer assistant API: store notes and ideas. Flask, feature-based layout. AI can reference your dev context via notes + semantic memory (FAISS).

**Documentation index:** [docs/docs.md](docs/docs.md) — where each doc lives and what it is for.

**Layout:** This **README** is the runbook (commands, demo table, quick start). Detailed specs live under **`docs/`** (see docs.md).

**Implementation agreement (tracked):** [docs/ia.example.md](docs/ia.example.md). Optional local `docs/ia.md` is gitignored (copy from `ia.example.md` if you need overrides).

---

## Demo

| Feature | GIF | Steps |
|---------|-----|--------|
| **Ask with memory** | — | 1. Build: `cd frontend && npm i && npm run build`. 2. `cd backend && python run.py`. 3. Open http://127.0.0.1:5000 → **Sign in** (or register). 4. Ask · Notes · History · Debug · Settings. Or POST `/auth/login` then POST `/ai/ask` with Bearer token. |
| **Ask with selected notes** | — | After login: in Ask → Load notes → select notes → ask (e.g. “make a reviewer from these notes”). Or POST `/ai/ask` with `{"question":"...", "note_ids":["id1","id2"]}`. |
| **Create note** | — | POST `/notes` with `{"title","category","content","tags"}` and `Authorization: Bearer <JWT from login>`. 201 + note. |
| **Note from images** | — | After login: Notes → “Add note from images” — title, category, upload images. Or POST `/notes/from-images` (multipart; Tesseract on server). |
| **List / filter notes** | — | GET `/notes/` or `/notes/?limit=500` with Bearer token. UI: sign in → Notes → “List notes”. |
| **Token estimate** | — | POST `/ai/estimate_tokens` with Bearer token and `{"question": "..."}`. |
| **Debug context** | — | POST `/ai/debug/context` with Bearer token and `{"question": "..."}`. |
| **Memory analytics** | — | `MEMORY_ANALYTICS_ENABLED=true`; use `/ai/ask`. Then `cd backend && python -m scripts.analyze_memory_analytics`; set thresholds in `.env` ([project.md — FAISS tuning](docs/project.md#faiss-threshold-tuning)). |
| **Stress test** | — | Backend running; `.env` has `JWT_SECRET` (or `API_SECRET`), `AI_KEY` (Groq). Optional `TEST_USER`, `TEST_PASSWORD`. `cd backend && python scripts/test/stress_test_faiss_full.py`. |
| **Health** | — | GET `/health` → 200 `{"status": "ok"}` (Phase 6; deploy probes). |

---

## Current features

- **Notes API** — CRUD; UUID + ISO8601; filter by category/tag. Notes per user.
- **Auth** — **Login/register** (no API secret). POST `/auth/login` and `/auth/register`; JWT in response; use `Authorization: Bearer <token>` for /notes, /ai, /settings. GET `/notes/auth-check` for debug. Users in `data/users.json`.
- **AI /ask** — Groq (default; free). Optional memory context from FAISS. Alternatives: DeepSeek, Ollama (see [docs/project.md](docs/project.md)).
- **Memory** — Gated: intent → FAISS → threshold → dedupe → summarization → token cap.
- **Modes** — `AI_MODE`: single | ensemble | judge. Optional `AI_ENSEMBLE_PROVIDERS=groq,ollama` ([docs/project.md](docs/project.md) Phase 4).
- **UI** — React (Vite) SPA; **black & dark gray** theme (light gray text). Login page first; then header + **Ask · Notes · History · Debug · Settings** (floating windows). Notes and AI context per user; token in localStorage; Sign out. Served by Flask from `frontend/dist/`.

**Phase 8 (user-centric):** Login auth (JWT); notes by user (`notes_{user_id}.json`); settings per user (GET/PUT `/settings`). No API secret in UI. See [docs/project.md](docs/project.md) roadmap.

---

## Docs

Full table: [docs/docs.md](docs/docs.md). Short map:

| Doc | Purpose |
|-----|--------|
| [docs/docs.md](docs/docs.md) | Index of all documentation. |
| [docs/ia.example.md](docs/ia.example.md) | Engineering agreement — architecture, API conventions, agent rules. |
| [docs/project.md](docs/project.md) | Product state — stack, roadmap, features, FAISS tuning, run/seed. |
| [docs/flow.md](docs/flow.md) | Flow traces in code. |
| [docs/testing.md](docs/testing.md) | Test scripts and per-API reference. |
| [docs/ui.md](docs/ui.md) | Frontend UI/UX source of truth. |

---

## Quick start

```bash
# .env at repo root: JWT_SECRET (or API_SECRET), AI_KEY (Groq). See docs/project.md and docs/ia.example.md.

# 1. Build frontend (React)
cd frontend
npm install
npm run build
cd ..

# 2. Run backend (serves built app at /)
cd backend
pip install -r requirements.txt
python run.py
# → http://127.0.0.1:5000 — UI at /, API at /ai, /notes, /files
```

**Frontend dev (hot reload):** In `frontend/`, run `npm run dev` → http://127.0.0.1:5174 (proxies API to backend). Keep backend running on 5000.

**Seed demo user (optional):** From `backend/`: `python -m scripts.seed_user` — creates user **testuser** / **password123** with 5 sample notes (title, category, content, tags). Sign in with those credentials to see pre-filled notes.
