# IA

Full-stack personal notes and AI assistant — **React 18 / Vite** frontend, **Flask** API, **PostgreSQL**, **Groq** LLM, optional **FAISS** semantic note search.

**Live:** [https://ia-ai.netlify.app/login](https://ia-ai.netlify.app/login)

---

## Quick start

**Prerequisites:** Python 3.10+, Node 18+, PostgreSQL

| Step | Action |
|------|--------|
| Setup | Copy [`.env.example`](.env.example) → `.env`; set `JWT_SECRET`, `DATABASE_URL`, `AI_KEY` |
| Database | Apply migrations from `backend/` (see [docs/setup.md](docs/setup.md)) |
| Frontend | `cd frontend` → `npm install` → `npm run build` |
| Backend | `cd backend` → `pip install -r requirements.txt` → `python run.py` |
| Test | `cd backend` → `python -m scripts.test.test_flashcards` (see [docs/testing.md](docs/testing.md)) |

Open **http://127.0.0.1:5000** — sign in or register.

---

## Features

- **Notes** — CRUD, categories, tags; import from PDF, PPTX, screenshots
- **Ask** — JWT Q&A with Notes/Memory context, conversation history, `!remember`, Focus mode
- **Flashcards** — AI deck generation (background jobs), study and save as notes
- **Memory** — Durable user facts and preferences; lexical + optional AI-assisted matching
- **AI Suggestions** — Next-step overlay from activity metadata (no note bodies sent)
- **AI Credits** — Ledger per user; admin / main_admin bypass (configurable)
- **Admin & debug** — User promotion, diagnostics, `/debug` (dev-oriented)
- **Auth** — Register, login, role-based access

---

## Project structure

```text
IA/
├── .env.example
├── README.md
├── docs/              # project, setup, testing
├── backend/
│   ├── run.py
│   ├── app/           # ai, auth, credits, notes, memory, settings, …
│   └── scripts/       # tests, seeds, analytics
└── frontend/
    └── src/           # React SPA, api.js, components
```

Detail: [docs/project.md](docs/project.md#repository-layout)

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, Flask, Pydantic |
| Database | PostgreSQL |
| LLM | Groq (default); Ollama, DeepSeek, OpenAI |
| Retrieval | Lexical notes; optional in-memory FAISS |
| Frontend | React 18, Vite 5 |

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/project.md](docs/project.md) | Features, API, configuration |
| [docs/setup.md](docs/setup.md) | Local setup, deployment, security |
| [docs/testing.md](docs/testing.md) | Test scripts and API reference |

---

## License

See repository license file if present.
