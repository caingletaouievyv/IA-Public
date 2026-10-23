# IA

Personal notes and AI assistant with memory. Store notes (including from images), ask questions with context from your notes, and manage conversations per user.

**Documentation:** [docs/docs.md](docs/docs.md) · **Quick start below**

---

## Features

- **Notes** — CRUD per user; filter by category and tag; import from images (OCR + AI summary).
- **Ask** — Ask with optional Notes context, independent persistent Memory, and conversation history. Its collapsible Shortcuts section opens Flashcards in a centered overlay without leaving Ask. Browse saved decks, create a deck by selecting up to 20 searchable source Notes and choosing generation options, then review and edit one card at a time. Decks remain in the existing Notes store with category and tag `flashcards`; generated drafts are not saved until explicit approval. Saved decks can be opened, edited, and individually deleted with confirmation. Memory is a per-user ON/OFF setting: when on, IA may extract useful stable details and retrieve relevant saved memories; when off, it neither retrieves nor automatically saves. Notes and Conversation History remain separate. A separate Focus button beside the non-interactive Conversation History heading opens a work-only view, hiding the app header and Ask shortcuts while keeping the history, question form, and Ask button available. AI responses have a per-message Copy button that copies readable plain text. User turns appear as right-aligned, compact previews; activating one opens its full message in the shared Ask overlay. Edit switches that same overlay into edit mode; saving uses the existing conversation flow and replaces that turn and all later turns. AI turns remain left-aligned. Compact previous/next controls navigate only User turns.
- **Auth** — Register and sign in; protected API routes use a Bearer JWT. `JWT_SECRET` is required at Flask startup; it must be at least 32 characters with at least 8 distinct characters. Missing, weak, or placeholder values stop startup. No secret value belongs in source control or the UI.
- **Memory** — Separate persistent per-user JSON records under `backend/data/`. Memory is off by default. When enabled, the configured AI classifies message intent and may save grounded durable user facts/preferences, but not ordinary questions or temporary instructions. A temporary assistant-name instruction in a compound message is excluded without suppressing unrelated durable facts; quoted, reported, or hypothetical name instructions do not change the saved preference. Mutable assistant-name preferences use the stable `assistant.name` key, so direct persistent changes replace the current value and retrieval does not inject obsolete conflicting names. For low-overlap queries, the same configured AI classifies which saved preference is being asked about; if classification fails, lexical retrieval remains available. These best-effort classification calls do not add an IA credit charge. `/manage` lists, edits, deletes, and clears the user's actual memories. It does not use Notes or conversation history as its storage.
- **AI Suggestions** — A default-on, per-user Settings toggle enables a dismissible bottom suggestion overlay on authenticated pages. The configured AI chooses among working Ask, Flashcards, and Manage Notes actions using only recent, fixed event-type counts (never note content); a deterministic choice is used if the provider fails. Dismissals are scoped by user in browser storage. Suggestions do not debit IA Credits, though the configured provider may have its own usage policy. Content-free per-user event records are internal suggestion context, not a user-facing history page; writes remain best-effort if persistent storage fails.
- **AI Credits** — Backend-owned internal credits; newly registered accounts receive 100 credits by default (`AI_CREDIT_INITIAL_BALANCE`), and Ask and Flashcards generation each cost `AI_ASK_CREDIT_COST` (default 1). Both are configurable. Existing credit accounts keep their persisted balance when the initial-balance setting changes. Users with the persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypass AI credit consumption. Initial credits and ledger entries are persisted per user. The JWT-protected `/credits/rewarded-ad` callback accepts unverified reward IDs only in explicit `APP_ENV=development` or `APP_ENV=test`; it is disabled in production. A production reward flow requires server-side ad-provider verification first.
- **UI** — React/Vite SPA with a dark page-based authenticated shell at `/ask`, `/manage`, `/debug`, and `/settings`. Authenticated pages can show a non-blocking, dismissible AI Suggestions overlay. Manage reuses the existing Notes and Conversations interfaces and provides independent Memory controls and CRUD.

---

## Quick start

**Requirements:** Python 3.10+, Node 18+, `.env` at repo root.

```bash
# 1. Environment (repo root)
# Set JWT_SECRET to a random value of at least 32 characters, with at least 8 distinct characters.
# AI_KEY=your-provider-key   # Groq by default; see backend/app/config.py

# 2. Frontend
cd frontend
npm install
npm run build
cd ..

# 3. Backend
cd backend
pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:5000** — sign in or register.

**Optional demo user** (development/test only; run from `backend/`):

Set `APP_ENV=development` and `SEED_USER_PASSWORD` in your local, ignored root `.env`.
Use a unique password of at least 12 characters; do not copy a real account password.

```bash
python -m scripts.seed_user
```

The seed refuses to run outside `APP_ENV=development` or `APP_ENV=test`, and refuses
an unset or too-short `SEED_USER_PASSWORD`. It is safe to rerun: it does not change an
existing `demo` account's password, adds only missing demo notes, initializes the demo
credit account only if it is missing, and does not alter settings or an existing credit
balance. Existing `ayi` accounts are left untouched.

**Optional Render production demo:** To deliberately provision the `demo` user and sample notes before the web server starts, use the separate `scripts.seed_render_demo` command described in [the deployment notes](docs/project.md#render-production-demo). It requires `APP_ENV=production`, `RENDER_DEMO_SEED_ENABLED=true`, and a password-manager-generated password of at least 12 characters supplied as protected `SEED_USER_PASSWORD`; length alone does not guarantee entropy. The seeder refuses to touch a pre-existing `demo` account unless its local provenance marker matches the account ID. Never put the password in source control or the Build Command. Render Free has no persistent disk, so local JSON accounts, credits, notes, and the provenance marker are ephemeral and can be lost when the instance is replaced.

**Development:** run `python run.py` from `backend/`, then run `npm run dev` from `frontend/` → http://127.0.0.1:5174. Vite proxies `/ai`, `/auth`, `/notes`, `/memories`, `/activity`, `/files`, and `/settings` to port 5000.

**Runtime/deployment:** `npm run build` writes `frontend/dist`. When that built directory exists, Flask serves it (including Vite assets); otherwise Flask serves the frontend directory. `GET /health` is available without authentication. The tracked repository has no provider-specific backend deployment manifest; a separately hosted frontend can set `VITE_API_BASE_URL` and configure backend `CORS_ORIGINS`.
`backend/data/` contains local per-user and generated runtime files and is ignored by Git; do not commit its contents.

The backend currently uses local JSON files under `backend/data/` for runtime and per-user data. Start it for local development with `python run.py` from `backend/`; `run.py` creates the Flask app and enables the development server when executed directly. The repository does not currently include a Gunicorn configuration or cross-process lock. Use **one backend process** and **one local `backend/data/` directory**; JSON is not safe for multiple workers, multiple instances, or a shared/network filesystem. Detail: [docs/project.md — JSON storage and deployment limits](docs/project.md#json-storage-and-deployment-limits). `backend/data/` is ignored by Git and must not be committed.

**Back up and restore data:** stop every backend process before copying or restoring the complete `backend/data/` directory, which contains account, note, internal suggestion-activity metadata, settings, memory, credit-ledger, and Ask idempotency JSON files. Store backups in access-controlled, encrypted storage; keep `.env` and secrets protected separately. To restore, stop the backend, preserve a separate copy of the current data directory, restore the selected backup to `backend/data/`, verify file ownership/permissions, then restart. No production backup or restore has been performed or configured by this repository.

### Ask and memory behavior

- `POST /ai/ask` requires a valid JWT and a non-empty `question`. It accepts optional `note_context_mode`, `note_ids`, and prior `messages`. Memory enablement is read from the authenticated user's saved Settings, never from a request-supplied user or mode.
- Note context modes are `Off` (no notes), `Selected` (the API's `focused` mode; selected notes only), and `Automatic` (search all user notes when relevant, or selected notes only when IDs are supplied). The Ask Notes mode button cycles `Off → Selected → Automatic → Off`; the API mode name remains `focused`.
- Conversation is a source-only button in Ask and continues sending the active conversation's prior turns. Notes has its existing independent context modes. Memory has an ON/OFF button that persists `memory_enabled` in per-user Settings and controls both automatic extraction and retrieval. Its source button opens Memory management. Other source modes are visual placeholders and do not retrieve context.
- The Ask toolbar shows Conversation, Notes, and Memory by default. Visibility for all seven sources and the **Show Ask labels** preference are saved in the authenticated user's existing Settings. The preference appears in Settings → Ask; Ask initializes from the user-scoped in-memory Settings cache when available and waits for any pending Settings save before showing its context controls, preventing stale labels from flashing on navigation. Focus behavior is unchanged. Visually hidden labels remain available to assistive technology through each source button's accessible name. Conversation is always visible; hiding a source only hides its controls and does not reset its saved mode or affect data or retrieval.
- Conversations are notes in the user's note store with category `_history`. The backend accepts up to 30 prior messages for a provider call. Conversation History is passed as untrusted conversational context and is not Memory storage. The active conversation ID is kept in `sessionStorage` for the current tab, scoped to the authenticated user; when Ask mounts again it loads the latest title and messages from that existing note. Selected Notes IDs are also retained for the tab and user, while their content is loaded through the existing Notes API when needed. Logout clears both selections, and deleted conversation IDs fall back to the empty Ask state. Notes modes and source visibility remain in per-user Settings; drafts remain transient. Files has no Ask context flow, and GitHub, Drive, and Web context integrations are placeholders.
- Manage at `/manage` organizes saved Notes and Conversations by reusing the existing CRUD interfaces and provides independent Memory CRUD. Memory is stored separately in `memories_<user-hash>.json`; `memory_enabled` defaults to false. Manage and Ask both display the persisted setting. Clear supported assistant-name preferences and recognized standalone temporary name commands use deterministic paths; ambiguous or compound messages use one structured extraction request, with candidates validated independently. Extraction is best-effort and does not fail the answer. Extracted items require quoted user-message evidence, are bounded and deduplicated, and secret patterns are rejected. Context injection treats memories as untrusted background facts and is relevance/token bounded.
- Ask operations use a user-scoped `operation_id` from `Idempotency-Key`, `request_id`, or a generated ID. A request with the same user and operation ID after completion returns the persisted result without another provider call or charge; an active duplicate returns 409. Insufficient-credit rejections and AI execution failures release their pending record so they can be retried. This JSON-backed state uses a process-local lock and is not transactional across multiple workers.
- Normal users are charged the configured AI Credit cost for Ask (default 1, with 100 credits for newly registered accounts); a failed AI call refunds the reservation. Changing `AI_CREDIT_INITIAL_BALANCE` does not change an existing persisted credit account. A persisted role matching `AI_UNLIMITED_ROLE` (default `admin`) bypasses the charge. Rewarded-ad credit grants are a development foundation, not a provider-verified production flow. There is no credit balance UI.
- Notes retrieval remains in its existing lexical/optional semantic engine. Independent Memory uses a small deterministic lexical relevance ranker over the authenticated user's dedicated memory records and injects at most eight records within a 180-token budget. Memory OFF skips both retrieval and extraction; disabling it preserves stored records. Each Ask still has only its normal single credit reservation; extraction adds no internal IA credit charge.

---

## API overview

| Area | Endpoints |
|------|-----------|
| Auth | `POST /auth/register`, `POST /auth/login` |
| Notes | `GET/POST /notes/`, `GET/PUT/DELETE /notes/<id>`, `POST /notes/from-images` |
| Memory | `GET /memories/`, `PUT/DELETE /memories/<id>`, `DELETE /memories/clear` |
| AI | `POST /ai/ask`, `POST /ai/suggestions`, `POST /ai/flashcards/generate`, `POST /ai/estimate_tokens`, `POST /ai/debug/context` |
| Credits | `POST /credits/rewarded-ad` (development foundation; JWT required) |
| Settings | `GET/PUT /settings/` (`ai_suggestions_enabled` defaults to true per user) |
| Health | `GET /health` (no auth) |

All protected routes: `Authorization: Bearer <JWT>`. Details and curl examples: [docs/testing.md](docs/testing.md).

---

## Frontend checks

Run the React component regressions and existing source-mode unit tests with `npm --prefix .\frontend test`. These tests mock Notes, suggestion-event, and AI HTTP responses; no live AI provider is required. Build the production frontend with `npm --prefix .\frontend run build`.

## Documentation

| Document | Description |
|----------|-------------|
| [docs/docs.md](docs/docs.md) | Index of all docs |
| [docs/project.md](docs/project.md) | Stack, roadmap, features, configuration |
| [docs/ia.md](docs/ia.md) | Engineering agreement (architecture, security, testing standards) |
| [docs/flow.md](docs/flow.md) | Code flow traces |
| [docs/testing.md](docs/testing.md) | Testing and API reference |
| [docs/ui.md](docs/ui.md) | Frontend UX |

---

## License

See repository license file if present.
