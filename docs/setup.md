# Local setup

**Index:** [docs.md](docs.md) · **Product:** [project.md](project.md)

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL
- Groq API key (or another configured provider)

---

## Environment (`.env`)

1. Copy [`.env.example`](../.env.example) to `.env` at the repo root.
2. **Required**
   - `JWT_SECRET` — at least 32 characters, 8+ distinct characters; validated at Flask startup.
   - `DATABASE_URL` — PostgreSQL connection string.
   - `AI_KEY` — provider key (`MODEL_PROVIDER=groq` by default).
3. **Optional (development):** `IA_AUTO_SEED_MAIN_ADMIN` and related vars for a local Main Admin — see [project.md](project.md#main-admin-bootstrap).

Never commit `.env`. Runtime files under `backend/data/` are gitignored.

---

## Database

PostgreSQL holds accounts, notes, memories, settings, credits, and activity. From `backend/`:

```bash
pip install -r requirements.txt
alembic upgrade head
```

Integration test patterns: [testing.md](testing.md).

---

## Run locally

**Single process (serves built UI):**

```bash
cd frontend && npm install && npm run build
cd ../backend && pip install -r requirements.txt && python run.py
```

Open **http://127.0.0.1:5000**.

**Development (hot reload):**

```bash
# Terminal 1 — backend
cd backend && python run.py

# Terminal 2 — frontend
cd frontend && npm install && npm run dev
```

Vite (**http://127.0.0.1:5174**) proxies API routes to port 5000.

---

## Tests

```bash
cd frontend && npm test
cd ../backend
python -m scripts.test.test_flashcard_provider
python -m scripts.test.test_flashcards
```

Full list: [testing.md](testing.md).

---

## Optional demo user

Development/test only: `APP_ENV=development` (or `test`) and `SEED_USER_PASSWORD` (12+ chars) in `.env`, then from `backend/`:

```bash
python -m scripts.seed_user
```

Refuses production and does not overwrite an existing demo password.

---

## Deployment

**Frontend (e.g. Netlify):** build with `npm run build`; set `VITE_API_BASE_URL` to your API origin.

**Backend (e.g. Render):** set `DATABASE_URL`, `JWT_SECRET`, `AI_KEY`, and `CORS_ORIGINS` for the Netlify origin. Run migrations before serving. `GET /health` is public.

**Live demo:** [https://ia-ai.netlify.app/login](https://ia-ai.netlify.app/login)

Optional hosted demo user seeding is documented in [project.md](project.md#render-production-demo) — use strong generated passwords only; never commit secrets or put passwords in build commands.

---

## Security

- Bearer JWT on protected routes; weak or placeholder `JWT_SECRET` values block startup.
- Secrets live in `.env` only; [`.env.example`](../.env.example) uses placeholders.
- Admin roles and unlimited AI credits are enforced server-side.
- Development-only rewarded-ad credit grants and demo seeds must stay out of production unless hardened.
