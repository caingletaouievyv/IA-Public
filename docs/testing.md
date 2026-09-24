# Testing

Run integration checks from the **backend** directory with the app running (`python run.py`). Index: [docs.md](docs.md). API shapes: [project.md](project.md).

**Auth:** `POST /auth/login` with `{"username","password"}` → JWT. Use `Authorization: Bearer <token>` on protected routes. Scripts use `TEST_USER` / `TEST_PASSWORD` from `.env` (default `testuser` / `testpass`). After `python -m scripts.seed_user`, sign in as `ayi` with `Ayi!23` or set `TEST_USER=ayi` and `TEST_PASSWORD=Ayi!23` for the test scripts.

---

## Prerequisites

- `.env` at repo root: `JWT_SECRET` (or `API_SECRET` fallback), `AI_KEY` (Groq).
- Base URL: `http://127.0.0.1:5000`.
- **Notes from images:** Tesseract installed (e.g. Windows: `choco install tesseract`).

---

## API reference

| API | Method | Auth | How to test | Expected |
|-----|--------|------|-------------|----------|
| **POST /auth/register** | POST | no | `{"username","password"}` | 201 token + user_id or 409 |
| **POST /auth/login** | POST | no | `{"username","password"}` | 200 token or 401 |
| **POST /ai/ask** | POST | yes | Bearer + `{"question":"..."}`; optional `note_ids`, `messages` | 200 `answer`, `tokens_estimated` |
| **POST /ai/estimate_tokens** | POST | yes | Bearer + `{"question":"..."}` | 200 `estimated_tokens`, `context_tokens` |
| **POST /ai/debug/context** | POST | yes | Bearer + `{"question":"..."}` | 200 context, scores, dropped_notes |
| **POST /notes** | POST | yes | Bearer + note JSON | 201 note |
| **POST /notes/from-images** | POST | yes | Multipart: title, category, files | 201 `{ note, appended }` |
| **GET /notes** | GET | yes | Bearer; optional `?limit=500` | 200 array |
| **GET /notes/<id>** | GET | yes | Bearer | 200 or 404 |
| **PUT /notes/<id>** | PUT | yes | Bearer + partial JSON | 200 or 404 |
| **DELETE /notes/<id>** | DELETE | yes | Bearer | 200 or 404 |
| **GET /settings** | GET | yes | Bearer | 200 preferences |
| **PUT /settings** | PUT | yes | Bearer + JSON merge | 200 settings |
| **GET /health** | GET | no | `curl .../health` | 200 `{"status":"ok"}` |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/test/test_ask_note_ids_and_health.py` | Smoke: health, login, ask, note_ids |
| `scripts/test/stress_test_faiss_full.py` | Bulk notes + many ask/debug calls |
| `scripts/test/stress_test_faiss_heavy.py` | Heavy FAISS scenarios |
| `scripts/test/test_semantic_retrieval_and_chunked_notes.py` | Retrieval + chunking |

```bash
cd backend
python scripts/test/test_ask_note_ids_and_health.py
python scripts/test/test_ai_credits.py
```

`test_ai_credits.py` uses temporary credit storage and mocks the AI provider. It covers initial balances, per-user isolation, idempotent grants, the development rewarded-ad callback, Ask spending, insufficient-credit rejection, provider short-circuiting, refunds, retry-safe reservations, JWT authentication, and the existing IP rate limit.

---

## Quick checklist

| What | How | Expected |
|------|-----|----------|
| Health | `curl http://127.0.0.1:5000/health` | 200 ok |
| Ask | Login → POST `/ai/ask` with Bearer | 200 answer |
| Selected notes | Ask with `note_ids` array | Context from those notes only |
| Images | Notes UI or multipart `/notes/from-images` | 201; Tesseract required |

## Frontend manual regression checklist

Run the frontend build from the repository root:

```bash
npm --prefix .\frontend run build
```

- Login and register.
- Open Ask.
- Open the History selector from Ask; select a conversation; verify the selector closes and Ask uses the selected conversation.
- Open the Notes selector from Ask; select notes; verify the selector closes and Ask shows the selected context.
- Verify one History selector and one Notes selector maximum per Ask window.
- Verify selectors from different Ask windows remain independent.
- Create a new conversation from History; verify it appears and opens immediately.
- Verify active conversation styling.
- Verify normal Notes and History CRUD outside selection mode.
- Verify Ask, History, Debug, and Settings do not duplicate the FloatingWindow title.
- Verify loading, error, and empty states still render.

### Floating-window mobile and desktop regression

- Test at approximately `375×667`, `390×844`, and `412×915`.
- Touch-drag and touch-resize the Ask window.
- Touch-drag and touch-resize selector windows.
- Verify the floating body still scrolls on touch.
- Verify Minimize → Maximize/Restore → Close ordering.
- Verify maximize fills the usable viewport.
- Verify Restore returns the previous position and size.
- Verify maximize/restore is hidden while collapsed.
- Verify collapse/expand still works after maximizing/restoring.
- Verify desktop mouse drag and resize still work.
