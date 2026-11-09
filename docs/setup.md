# Local setup

**Index:** [docs.md](docs.md) · **Product reference:** [project.md](project.md)

---

## Environment

1. Copy [`.env.example`](../.env.example) to `.env` at the repo root.
2. Set **required** values:
   - `JWT_SECRET` — at least 32 characters with 8+ distinct characters (no placeholders).
   - `DATABASE_URL` — PostgreSQL connection string for auth, notes, memory, credits, and settings.
   - `AI_KEY` — provider API key (Groq by default via `MODEL_PROVIDER=groq`).
3. Optional: `IA_AUTO_SEED_MAIN_ADMIN` and related vars for a development Main Admin (see [project.md — Main Admin bootstrap](project.md#main-admin-bootstrap)).

Never commit `.env`. `backend/data/` is for local runtime files and is ignored by Git.

---

## Database

Auth and application data require PostgreSQL. Apply migrations from `backend/` before first run (see [testing.md](testing.md) for integration test setup patterns).

---

## Run

```bash
# Production-like (serves built frontend when frontend/dist exists)
cd backend
pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:5000**.

**Development (hot reload UI):**

```bash
# Terminal 1
cd backend && python run.py

# Terminal 2
cd frontend && npm install && npm run dev
```

Vite dev server (default **http://127.0.0.1:5174**) proxies `/ai`, `/auth`, `/notes`, `/memories`, `/activity`, `/files`, and `/settings` to port 5000.

---

## Build and test

```bash
cd frontend
npm install
npm run build
npm test

cd ../backend
pip install -r requirements.txt
python -m scripts.test.test_flashcard_provider
python -m scripts.test.test_flashcards
```

See [testing.md](testing.md) for the full script list.

---

## Optional demo user (development/test only)

From `backend/`, with `APP_ENV=development` or `test` and a strong `SEED_USER_PASSWORD` in `.env`:

```bash
python -m scripts.seed_user
```

The seed refuses production, refuses weak passwords, and does not overwrite an existing demo account password.

---

## Optional Render demo user

For a hosted demo, use `scripts.seed_render_demo` only with explicit production flags and a password-manager-generated `SEED_USER_PASSWORD` — see [project.md — Render production demo](project.md#render-production-demo). Do not embed passwords in build commands or source control.

---

## Split frontend deployment

When the SPA is hosted separately (e.g. Netlify), set `VITE_API_BASE_URL` on the frontend build and configure backend `CORS_ORIGINS`. `GET /health` remains unauthenticated.
