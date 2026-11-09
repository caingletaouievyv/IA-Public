# IA

Personal notes and AI assistant with memory. Store notes (including from PDFs, slides, and screenshots), ask questions with Notes and Memory context, study flashcard decks, and manage conversations per user.

**Live:** [https://ia-ai.netlify.app/login](https://ia-ai.netlify.app/login)

---

## Features

- **Notes** — Per-user CRUD, categories, tags; import from PDF, PPTX, or screenshots (server OCR when configured).
- **Ask** — JWT-protected Q&A with optional Notes context, persistent Memory, and conversation history; `!remember` for direct memory saves; Focus mode; per-message copy.
- **Flashcards** — Select source notes, generate decks (batched AI job with credit reservation), study and edit before saving as notes.
- **Memory** — Separate durable preferences and facts; lexical retrieval with optional AI-assisted matching when enabled.
- **AI Suggestions** — Contextual next-step overlay from recent activity metadata (no note content sent).
- **AI Credits** — PostgreSQL ledger; configurable cost per Ask and flashcard job; `admin` / `main_admin` bypass limits.
- **Admin & debug** — Main Admin bootstrap, user promotion, diagnostics events, and authenticated `/debug` tooling (development-oriented).
- **Auth** — Register, login, Bearer JWT on protected routes; roles stored in PostgreSQL.

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, Flask, Pydantic |
| Database | PostgreSQL (accounts, notes, memory, credits, settings) |
| LLM | Groq (default); Ollama, DeepSeek, OpenAI configurable |
| Retrieval | Lexical notes search; optional temporary FAISS for semantic notes |
| Frontend | React 18, Vite 5 |

---

## Quick start

**Prerequisites:** Python 3.10+, Node 18+, PostgreSQL, `.env` from [`.env.example`](.env.example)

| Step | Action |
|------|--------|
| Setup | Copy `.env.example` → `.env`; set `JWT_SECRET`, `DATABASE_URL`, and `AI_KEY` |
| Frontend | `cd frontend` → `npm install` → `npm run build` |
| Backend | `cd backend` → `pip install -r requirements.txt` → `python run.py` |
| Test | `cd backend` → `python -m scripts.test.test_flashcards` (see [docs/testing.md](docs/testing.md)) |

Open **http://127.0.0.1:5000** — sign in or register.

Full local setup, seeding, and deployment notes: [docs/setup.md](docs/setup.md)

---

## Security

- JWT authentication on protected APIs; `JWT_SECRET` validated at startup (length and entropy checks).
- Secrets and `.env` are never committed; runtime data under `backend/data/` is gitignored.
- Admin and credit-bypass behavior is role-gated in the backend, not exposed in client-only checks.
- Do not run development-only seed or rewarded-ad credit grants in production without hardening.

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/docs.md](docs/docs.md) | Documentation index |
| [docs/setup.md](docs/setup.md) | Environment, database, dev server, optional seeding |
| [docs/project.md](docs/project.md) | Product scope, API, configuration, deployment |
| [docs/flow.md](docs/flow.md) | Code flow traces |
| [docs/testing.md](docs/testing.md) | Test scripts and API reference |
| [docs/ui.md](docs/ui.md) | Frontend UX |

---

## License

See repository license file if present.
