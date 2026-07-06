# Testing

**Path:** `docs/testing.md` · **Updated:** 2026-03-23

Run from **backend** directory. App must be running (`cd backend && python run.py`) for integration tests. Index: [docs.md](docs.md). Agreement: [ia.example.md](ia.example.md). Product detail: [project.md](project.md).

Auth: **Login** (no API secret). POST `/auth/login` with `{"username","password"}` → returns `token` (JWT). Use `Authorization: Bearer <token>` for all protected routes. Optional: POST `/auth/register` to create account. Test scripts use `TEST_USER`/`TEST_PASSWORD` from `.env` (default `testuser`/`testpass`). To use the user created by `python -m scripts.seed_user`, set `TEST_PASSWORD=password123`.

---

## Prerequisites

- `.env` at **repo root**: `JWT_SECRET` (or `API_SECRET` as fallback) for signing JWTs; `AI_KEY` (Groq) for `/ai/ask`. Optional `TEST_USER`, `TEST_PASSWORD` for test scripts (default `testuser`/`testpass`; use `TEST_PASSWORD=password123` to match `scripts/seed_user`). For memory analytics: `MEMORY_ANALYTICS_ENABLED=true`. For FAISS tuning: `FAISS_THRESHOLD_*` from `python -m scripts.analyze_memory_analytics`. For ensemble/judge: `AI_MODE`, `AI_ENSEMBLE_PROVIDERS`. Base URL: `http://127.0.0.1:5000`. For **notes from images**: Tesseract OCR on system (e.g. Windows: `choco install tesseract`).

---

## Per API

| API | Method | Auth | How to test | Expected |
|-----|--------|------|-------------|----------|
| **POST /auth/register** | POST | no | `curl -X POST .../auth/register -H "Content-Type: application/json" -d '{"username":"u","password":"p"}'` | 201 `token`, `user_id`, `username` or 409 username taken |
| **POST /auth/login** | POST | no | `curl -X POST .../auth/login -H "Content-Type: application/json" -d '{"username":"u","password":"p"}'` | 200 `token`, `user_id`, `username` or 401 invalid |
| **POST /ai/ask** | POST | **yes** | Get token from login; `curl -X POST .../ai/ask -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"question":"find note X"}'`. Optional `note_ids`, optional `messages` (conversation history: list of `{role, content}`). | 200, `answer`, `tokens_estimated`. 401 without auth. Rate limited 30/min. |
| **POST /ai/estimate_tokens** | POST | **yes** | Same header + `{"question":"..."}`; optional `note_ids`. | 200, `estimated_tokens`, `context_tokens`. 401 without auth. |
| **POST /ai/debug/context** | POST | **yes** | Same header + `{"question":"..."}`; optional `note_ids`. | 200, `context`, `context_tokens`, `best_faiss_score`, `dropped_notes`. 401 without auth. |
| **POST /notes** | POST | yes | `curl -X POST .../notes -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"title":"T","category":"C","content":"body","tags":[]}'` | 201, note with `id`, `created_at`, `updated_at`. Per user. |
| **POST /notes/from-images** | POST | yes | Multipart: `title`, `category`, `files`. OCR + AI summarize. Per user. | 201 or 400/500. Tesseract required. Rate limited 10/min. |
| **GET /notes** | GET | yes | `curl .../notes/ -H "Authorization: Bearer $TOKEN"` or `?limit=500`. | 200, JSON array (current user's notes). |
| **GET /notes/auth-check** | GET | optional | Same header; returns auth_ok, header_received, header_length (debug). | 200, JSON |
| **GET /notes/<id>** | GET | **yes** | `curl .../notes/<id> -H "Authorization: Bearer $TOKEN"` | 200 note or 404 |
| **PUT /notes/<id>** | PUT | yes | `curl -X PUT .../notes/<id> -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"title":"Updated"}'` | 200 updated note or 404 |
| **DELETE /notes/<id>** | DELETE | yes | `curl -X DELETE .../notes/<id> -H "Authorization: Bearer $TOKEN"` | 200 `{"message":"Note deleted"}` or 404 |
| **GET /settings** | GET | yes | `curl .../settings/ -H "Authorization: Bearer $TOKEN"` | 200, JSON (user preferences). |
| **PUT /settings** | PUT | yes | `curl -X PUT .../settings/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"theme":"dark"}'` | 200, full settings JSON. Merge semantics. |
| **GET /files** | GET | yes | `curl .../files -H "Authorization: Bearer $TOKEN"` | 200, folder tree JSON |
| **GET /health** | GET | no | `curl .../health` (deploy probes). | 200, `{"status": "ok"}` |

---

## Scripts (scripts/test/)

| Script | Covers |
|--------|--------|
| `stress_test_faiss_full.py` | Login (or register) via auth_helper; POST /notes (bulk), POST /ai/ask, POST /ai/debug/context, POST /ai/estimate_tokens. Uses TEST_USER/TEST_PASSWORD. Groq free tier may 429. |
| `test_ask_note_ids_and_health.py` | GET /health; login; POST /ai/ask; GET /notes + POST /ai/ask with note_ids (if ≥2 notes). Smoke only. |
| `stress_test_faiss_heavy.py` | Heavy FAISS + fallback behavior |
| `test_semantic_retrieval_and_chunked_notes.py` | Semantic retrieval + chunked notes |

**Run:** From backend: `python scripts/test/stress_test_faiss_full.py` (and similarly for others).

---

## How to test (quick checklist)

**Backend running:** `cd backend && python run.py`. **Frontend (optional):** `cd frontend && npm run build` then open http://127.0.0.1:5000, or `npm run dev` for :5174.

| What | How | Expected |
|------|-----|----------|
| **Ask (semantic search)** | 1. POST `/auth/login` with `{"username","password"}` → get `token`. 2. POST `/ai/ask` with `Authorization: Bearer $TOKEN` and `{"question":"something"}`. | 200; answer uses context from **your** notes. 401 without auth. |
| **Ask with selected notes** | POST `/ai/ask` with auth and `{"question":"...", "note_ids":["<id1>","<id2>"]}` (IDs from GET /notes). | 200; answer uses only those notes. |
| **Notes from images** | UI: sign in → Notes → Add note from images → title, category, pick image(s) → submit. Or curl multipart with Bearer token. | 201 `{ note, appended: false }` first time; same title+category again → 201 `{ note, appended: true }`. |
| **Health** | `curl http://127.0.0.1:5000/health` | 200 `{"status":"ok"}`. |
| **Auth** | GET `/notes/` without header → 401. With `Authorization: Bearer <JWT from login>` → 200. | Per table above. |

**Notes from images** needs Tesseract installed; without it you get 400 "No text extracted from images". Existing stress tests do not call `/notes/from-images` (no image fixtures).

---

## When to add tests

- New endpoint: add a script in `scripts/test/` that calls the API and asserts status or response shape.
- Keep scripts runnable; no broken imports or missing env.

---

## Rules (from docs/ia.example.md and project.md)

- Keep `scripts/test/` runnable.
- Add tests for new behavior when practical.
