# IA — Project reference

Product and technical reference: stack, features, roadmap, and operations.

**Related:** [docs.md](docs.md) (index) · [ia.md](ia.md) (engineering agreement) · [README.md](../README.md) (quick start)

---

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, Flask, Pydantic |
| LLM | Groq by default; Ollama, DeepSeek, and OpenAI provider entries are available in the client configuration |
| Storage | Local runtime JSON files: users, per-user notes, internal suggestion events, independent user memories, settings, AI Credit ledgers, and Ask operation results; `backend/data/` is ignored by Git |
| Notes retrieval | Deterministic lexical retrieval by default; optional FAISS/SentenceTransformer semantic retrieval, thresholds, chunking, summarization |
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
│   ├── data/            # users, notes, memories, settings, and per-user credit ledgers
│   └── scripts/         # seed_user, analyze_memory_analytics, test/
└── frontend/
    └── src/             # App, api.js, components/
```

---

## Features

- **Auth** — `POST /auth/register`, `/auth/login` → JWT; Bearer on protected routes. `GET /auth/me` returns the authenticated user's `user_id`, `username`, and persisted `role` (`user`, `admin`, or `main_admin`). Registration always creates `user`. Roles are stored in ignored `backend/data/users.json` and are not embedded in JWT claims. `JWT_SECRET` is required when `create_app()` starts, must be at least 32 characters with at least 8 distinct characters, and rejects missing, weak, or placeholder values. No default signing secret is used. Main Admin is designated only through the explicit operator command `python -m scripts.bootstrap_main_admin` (see [Main Admin bootstrap](#main-admin-bootstrap)). Main Admin may list accounts with `GET /admin/users`, promote `user`→`admin` with `POST /admin/users/<user_id>/promote`, and demote `admin`→`user` with `POST /admin/users/<user_id>/demote`; there is no generic role-update API and these routes cannot change Main Admin ownership or the actor's own role. Permission helpers live in `app/auth/permissions.py`.
- **Public site** — Unauthenticated landing page at `/`, plus `/privacy`, `/terms`, and `/contact`. Auth routes are `/login` and `/register`; authenticated pages are `/ask`, `/manage`, `/debug`, and `/settings`, with `/ask` as the default.
- **Notes** — Per-user CRUD; `GET /notes/meta` for categories/tags; `POST /notes/from-images` (OCR + AI; append when same title+category); `POST /notes/from-pdf/extract` (text-layer PDF only — returns extracted text for review, then save via normal `POST /notes/`; 15 MB / 512k-character limits; no OCR, AI, or stored PDF).
- **Ask** — `POST /ai/ask` requires JWT authentication and a non-empty `question`; it accepts optional `note_ids`, `note_context_mode`, and prior `messages`. The Ask toolbar offers Conversation, Notes, Files, GitHub, Memory, Drive, and Web. Conversation, Notes, and Memory are visible by default; visibility is configurable per user in Settings → Ask Context Sources, and Conversation is always visible. Conversation opens the existing History UI and sends active conversation turns separately. Notes retains its existing `Off → Selected → Automatic → Off` context cycle and retrieves only from the authenticated user's Notes. Memory is a distinct ON/OFF control backed by per-user `memory_enabled` Settings; when on, it retrieves relevant dedicated records and performs best-effort extraction from user messages after the answer. When off, neither retrieval nor extraction runs. Notes, Memory, and Conversation History remain independent. Files, GitHub, Drive, and Web remain UI placeholders and their modes do not retrieve context. Hiding a source only hides its controls; it does not reset the Memory setting. The `/files` endpoint lists a file tree, but Ask has no file-selection/context flow. Ask keeps Notes and conversation selection in-place; saved-content management is on `/manage`. AI turns are left-aligned; user turns are compact right-aligned bubbles. Selecting a user bubble opens its full message in the Ask overlay; Edit switches to a labeled form, Cancel/Escape return to detail, and Save resends through the existing conversation flow and replaces that turn and later turns. Previous/next controls navigate only User messages. There is no chat-edit endpoint.
- **Flashcards** — The Shortcuts section on `/ask` opens a centered overlay without navigation. Users can browse saved flashcard Notes, open a deck, explicitly edit it, or delete that individual deck after confirmation. **New Flashcards** starts a three-step flow: select/search up to 20 owned source Notes, configure generation options, and review/edit one generated card at a time. Back navigation preserves selections, options, and card edits. Generation never persists a deck; explicit approval creates a Note, while editing an existing deck explicitly updates that Note. Decks use the existing Notes store with category and tag `flashcards`; there is no separate persistence store.
- **AI Credits** — Backend-owned per-user balance and JSON ledger. Newly registered users initialize with `AI_CREDIT_INITIAL_BALANCE` (default `100`); normal `/ai/ask` and `/ai/flashcards/generate` requests each cost `AI_ASK_CREDIT_COST` (default `1`), and insufficient balance returns `402` before the AI provider is called. Changing the initial-balance setting does not alter existing credit-account files. Existing users whose account is not yet initialized receive the configured default on first credit access; there is no automatic blanket top-up. Users with persisted role `admin` or `main_admin` bypass AI credit reservation and deduction via `app/auth/permissions.py`, while retaining authentication and rate limits. A legacy stored role equal to `AI_UNLIMITED_ROLE` (default `admin`) is also treated as unlimited when it differs from the built-in role constants. Development/test rewarded-ad grants (`REWARDED_AD_CREDIT_AMOUNT`, default `10`) are configurable. `POST /credits/rewarded-ad` requires JWT auth and is enabled only for `APP_ENV=development` or `APP_ENV=test`; its caller-supplied reward ID is not provider verification. It is disabled in production, where a server-side ad-provider verification step is required before granting credits. Credit purchasing is not implemented. JSON persistence and its lock are process-local and are not a multi-worker transactional store.
- **Ask idempotency** — Each authenticated user's `operation_id` is stored with that user's credit account. It comes from `Idempotency-Key`, `request_id`, or a generated UUID. A completed retry returns the stored response without another provider call or debit; a currently pending duplicate returns `409 operation_in_progress`. Insufficient-credit and failed-provider operations release their pending record so they can be retried. The state uses the per-user JSON file and process-local lock; concurrent multi-worker coordination is not transactional.
- **Memory** — Independent per-user records are stored in `data/memories_<sha256(user_id)>.json`, separate from Notes and `_history`. Memory is off by default. When enabled, the configured AI classifies user-message intent and may save bounded, user-message-grounded durable facts/preferences; ordinary questions and temporary instructions are not retained. Mutable assistant-name preferences use the stable `assistant.name` key, so changes update one current record and retrieval filters obsolete legacy values. The same configured AI classifies low-overlap queries against available stable keys; on classifier failure, lexical retrieval remains available. These best-effort classifications do not add an IA credit charge. The optional record key is backward-compatible: existing assistant-name records are recognized by text, with no destructive migration. Retrieved content is capped and labeled as untrusted background facts. Extraction failures do not fail the answer; one Ask still incurs only its normal single internal credit reservation. Recognized credentials/secrets are rejected. Authenticated CRUD routes list, edit, delete, and clear only the current user's records.
- **Manage** — `/manage` organizes saved Notes and Conversations with the existing Notes and History interfaces. Its Memory section displays the actual user-specific records and setting, supports edit/delete, and requires confirmation before clearing all memories.
- **AI Suggestions** — A default-on per-user `ai_suggestions_enabled` setting controls a dismissible bottom overlay on authenticated pages. Internal `GET /activity/` and `POST /ai/suggestions` APIs require JWT auth; event data is scoped to the JWT subject. Successful non-history Note and flashcard-deck create/update/delete operations record fixed descriptions and timestamps in a separate hashed per-user JSON file. The activity endpoint returns newest-first events (50 by default, at most 100); the overlay uses them as context after at least two relevant actions in seven days. Events contain only an ID, event type, fixed short description, and timestamp; conversation `_history` changes and note contents are not recorded. JSON event writes remain best-effort after bounded Windows replacement retries. The configured AI receives only fixed event-type counts and chooses among three supported actions: prepare an Ask draft with Notes context, open Flashcards, or open Manage Notes. Provider failure uses a deterministic fallback. Dismissal identifiers are scoped by JWT subject in browser storage. Suggestions do not debit IA Credits; provider-side usage policies still apply. No note contents are sent for suggestions.
- **Conversation history** — Stored in the per-user notes file as notes with category `_history`; frontend saves turns with `PUT /notes/<id>`. The AI engine sends up to the most recent 30 prior messages to the provider. Ask's active conversation ID is transient per-tab UI state in `sessionStorage`, keyed by the authenticated JWT subject. Each Ask mount reloads the latest title and messages from the existing history note; selecting or creating a conversation updates the ID, and logout clears it. Missing or non-history notes clear the stale selection and show an empty Ask state. Selected Notes IDs are likewise tab-scoped and user-keyed so Ask can pass them to the existing Notes retrieval API after a page remount; no note contents, authentication tokens, or question draft are stored in session storage. Notes context mode and source visibility remain in per-user Settings.
- **Ask context sources** — Conversation history, Notes, and Memory have working context flows. Notes mode, source visibility, and `show_context_source_labels` (default true) are persisted in per-user Settings; selected note IDs are transient per-tab `sessionStorage` state keyed by JWT subject and are sent with `POST /ai/ask` when Notes mode is enabled. The backend filters selection to the authenticated user's non-history Notes and places retrieved Note content in the provider system context. Memory enablement is persisted separately in `memory_enabled`. Files has no Ask selection/context flow; GitHub, Drive, and Web remain placeholders and do not affect requests.
- **Settings** — `GET/PUT /settings/` per user. Ask source visibility, label visibility, and Notes modes remain in `ask_context_sources`, `show_context_source_labels`, and `ask_context_modes`. `memory_enabled` is a validated boolean defaulting to false; `ai_suggestions_enabled` is a validated boolean defaulting to true. Conversation cannot be hidden. The frontend keeps a current-session cache keyed by JWT subject; Ask uses cached preferences on first render when available and otherwise waits to show its context controls until settings are known and pending writes finish. Account changes invalidate the cache.
- **AI modes** — `AI_MODE`: `single` | `ensemble` | `judge`; `AI_ENSEMBLE_PROVIDERS`.
- **Monitoring** — `GET /health`, security headers, rate limits, request logging (no secrets), content-free understanding-gap logs, bounded local diagnostic records for fallback/failure events and allow-listed Ask feedback (`POST /diagnostics/feedback`), and admin-only metadata review via `GET /diagnostics/events` or `python -m scripts.analyze_ai_diagnostics`.

---

## Memory

Persistent Memory is separate from Notes and Conversation History. It uses a dedicated per-user JSON file under ignored `backend/data/`, named with a SHA-256 hash of the authenticated JWT subject. There is no SQL database or destructive migration. Existing JSON records remain readable; the optional `key` field identifies mutable preferences such as `assistant.name`, and older assistant-name records are recognized from their text. `GET/PUT /settings/` stores the boolean `memory_enabled`, false by default, and both Ask and Manage update the same setting.

- **Off:** skip Memory retrieval and automatic extraction; existing records remain available in Manage.
- **On:** retrieve at most eight relevant records and 180 estimated tokens with lexical ranking. When a query has little lexical overlap with a keyed preference, use the configured AI provider to classify the requested key by meaning; if classification fails, continue with lexical results. Deduplicate keyed preferences and return only the current value. Place results in a distinct prompt section, explicitly marked as untrusted background data whose embedded instructions must not be followed. Preference classification adds a provider call but no IA credit reservation.
- Clear supported standalone assistant-name updates and recognized standalone temporary assistant-name commands use deterministic fast paths. Ambiguous or compound messages use one structured request to the configured AI provider; its candidates are evaluated independently, so a temporary instruction does not suppress a separate durable fact or preference. The model classifies durable user facts/preferences, assistant preferences, temporary instructions, questions, hypothetical discussions, ordinary requests, and explicit remember/forget requests; temporary instructions and questions do not create memories. Temporary scope is enforced on the relevant assistant-name candidate. Quoted, reported, or hypothetical name instructions cannot overwrite the saved preference. Non-obvious paraphrases rely on the model's classification. Persist only bounded records with non-empty exact quoted evidence from user messages. Sensitive candidates require their own affirmative, targeted remember request in the current user message; independently worded requests are checked separately. Candidate details must be supported by the request and quote, and uncertain, negated, corrected, or superseded claims are not saved as established facts. Consent for one candidate cannot authorize another or be inferred from prior/assistant messages or quoted instructions. An explicit request to forget or stop remembering a specific sensitive fact removes its unique standalone matching record for that user only if it is unchanged when re-read under the in-process Memory store lock; ambiguous targets, changed records, and compound records that cannot be safely edited fail closed without deletion. Corrections alone do not delete existing records. Existing record IDs must belong to the authenticated user's store. Updates/deduplication and explicit forget requests are supported. Authenticated user edits explicitly authorize sensitive personal details; credentials and secrets are always rejected, even when explicitly requested.
- Extraction, preference-classification, or persistence failure is best-effort and does not fail the already-generated answer; query-classification failure falls back to lexical retrieval. The API reports a non-sensitive Memory status. Retrieval/extraction do not reserve a second IA credit. Provider classification is probabilistic and is not guaranteed to understand every paraphrase.
- Authenticated APIs: `GET /memories/`, `PUT /memories/<id>`, `DELETE /memories/<id>`, and `DELETE /memories/clear`. Manage confirms clear-all. Per-process atomic JSON writes follow the repository's existing storage model; the lock is not cross-worker transactional.

`MEMORY_RETRIEVAL=text` and optional FAISS/SentenceTransformer retrieval remain Notes-only. Notes retains `MAX_CONTEXT_TOKENS` packing, retrieval thresholds, and `_history` exclusion. Notes and Memory are not composed or deduplicated together. See [flow.md](flow.md).

### Retrieval configuration

- `MEMORY_RETRIEVAL=text` (default): deterministic weighted lexical overlap; no embedding model is loaded.
- `MEMORY_RETRIEVAL=semantic` (opt-in): uses a temporary FAISS index for the current user's candidate notes and the `sentence-transformers/all-MiniLM-L6-v2` model. Model loading is lazy. The normal manager path does not use the persistent global vector cache.
- Text and FAISS retrieval use their own lookup/exploratory thresholds. Context size is controlled by `MAX_CONTEXT_TOKENS`; both modes use `MAX_FAISS_RESULTS` as the configured top-N count.
- Query-bearing diagnostics (`FAISS_LOG_SCORES`, `INTENT_CACHE_LOG_HITS`) and dropped-note-title logs (`LOG_DROPPED_NOTES`) default off. `MEMORY_ANALYTICS_ENABLED` also defaults off; when enabled, its local records include query text and note titles. Understanding-gap logs use fixed content-free codes; see [understanding-gaps.md](understanding-gaps.md).

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
- **Seed:** `python -m scripts.seed_user` is for development/test only. Set `APP_ENV=development` (or `test`) and `SEED_USER_PASSWORD` with at least 12 characters in the ignored root `.env` before running it. The command refuses production/default environments and missing or short passwords. It does not update an existing `demo` account's password or overwrite its notes/settings/credit balance; it adds missing demo notes and initializes a missing credit account only. Any existing `ayi` account is left untouched.
- **Render production demo:** A separate opt-in command, `python -m scripts.seed_render_demo`, can create the fixed `demo` account and fill in missing sample notes before the production server starts. It requires `APP_ENV=production`, `RENDER_DEMO_SEED_ENABLED=true`, and `SEED_USER_PASSWORD` set through Render's protected environment configuration. Generate a cryptographically random password with a password manager; the minimum length/distinct-character checks are policy gates, not proof of entropy. It never prints the password. An existing `demo` account is rejected unless an instance-local provenance marker matches its user ID; only a marked account created by this seeder can be seeded again. New accounts receive the normal `user` role. The development/test-only `scripts.seed_user` guard is unchanged. See [Render production demo](#render-production-demo) for the Start Command and operational limitations.
- **CORS:** `CORS_ORIGINS` in `.env` when frontend and API are on different origins.
- **Notes from images:** Tesseract OCR must be installed on the server.
- **Notes from PDF:** Python dependency `pypdf` only; text-based PDFs (no OCR for scanned pages).
- **Runtime:** the repository selects Python `3.13.5` in `.python-version`; the frontend package version is `0.0.1`. Flask serves `frontend/dist` when it exists, otherwise it serves the frontend directory. `/health` is unauthenticated. Vite development proxies `/ai`, `/auth`, `/notes`, `/memories`, `/activity`, `/files`, and `/settings` to the backend at `127.0.0.1:5000`; the frontend API can use `VITE_API_BASE_URL` for a separate API origin. `backend/data/` is local runtime/user data and generated AI-memory artifacts, ignored by Git and not a source-controlled dataset.
- **Deployment configuration:** the tracked repository contains no provider-specific backend deployment manifest. The frontend includes a static-host SPA fallback in `frontend/public/_redirects`; actual frontend/backend hostnames, build commands, and secret values are deployment-specific and are not specified here. `backend/run.py` loads the repository-root `.env`, creates the Flask app, and starts Flask's development server when executed directly. Although `gunicorn` is listed as a dependency, the repository does not currently include `gunicorn.conf.py`, a guarded WSGI entrypoint, or a cross-process data-directory lock. See [JSON storage and deployment limits](#json-storage-and-deployment-limits) before running more than one worker or instance against the same data directory.

### JSON storage and deployment limits

Runtime state is stored as JSON under ignored `backend/data/`. Read-modify-write paths in the backend use **process-local** `threading` locks (or, for the Main Admin marker, a one-time exclusive file create). They coordinate concurrent **threads inside one Python process** only.

| Store | Primary path(s) | Coordination in code |
|-------|-----------------|----------------------|
| Accounts and roles | `users.json` | `app/auth/manager.py` — `_USERS_LOCK` (`RLock`) on registration and role updates |
| AI Credits and Ask operation results | `credits_<user_id>.json` | `app/credits/manager.py` — `_FILE_LOCK` |
| AI diagnostics events | `diagnostics_<user-hash>.json` | `app/diagnostics/manager.py` — `_STORE_LOCK` |
| Main Admin designation | `.ia_main_admin.json` | `O_CREAT\|O_EXCL` on first marker write in `app/auth/main_admin.py`; not a lock for ongoing `users.json` updates |

**Supported model today:** one application process and one local `backend/data/` directory on that host (for example `python run.py` for development, or `gunicorn --workers 1` when a WSGI server is used). Stop all backend processes before backup, restore, or manual file edits.

**Not safe with the current implementation:**

- **Multiple worker processes** (for example `gunicorn --workers 2+`) sharing one data directory — each worker has separate in-memory locks; concurrent JSON writes can interleave and lose updates (credits, roles, idempotency, diagnostics).
- **Multiple app instances or containers** pointing at the **same** data directory, including on a **shared or network-mounted volume** — mounting one folder in many places does **not** make JSON read-modify-write atomic or transactional.
- Using these JSON files as a shared-database substitute across hosts.

If multi-worker or multi-instance deployment is required, **migrate to a database** (or another store with transactional updates), **or** design, implement, and test operating-system-level file locking and atomic write behavior for every affected store. The tracked repository does not ship that cross-process layer.

The Render demo Start Command example uses `gunicorn --workers 1` for this reason; that example does not define worker count for other environments.

### Render production demo

Render's Build Command should remain unchanged and must not run the demo seeder. In the Render service's protected environment variables, set:

- `APP_ENV=production`
- `RENDER_DEMO_SEED_ENABLED=true`
- `SEED_USER_PASSWORD` to a password generated by a password manager; the seeder requires at least 12 characters, but length alone does not guarantee entropy

Do not commit this password, put it in the Build Command, or include it in shell arguments. Generate/store it with a password manager and provide it to demo users through a secure channel. The seed command does not log it.

Set the Render **Start Command** to run the seed once per process start before Gunicorn:

```text
cd backend && python -m scripts.seed_render_demo && gunicorn --workers 1 run:app
```

The seeder creates `demo` only if absent. It records the newly created user ID in `.render_demo_seed.json` under `backend/data/`; subsequent runs proceed only if that marker is valid and matches the current `demo` account ID. If `demo` already exists without a matching marker, or the marker is missing/corrupt/mismatched, the seeder fails closed before adding notes or initializing credits. This prevents an account claimed through public registration from receiving the sample data. After the seeder has created the account, reruns initialize only missing credits and add only missing sample notes; they do not change the password, role, settings, or existing balance. If the seeder rejects configuration or fails, the chained command does not start the web server. To disable production seeding, remove the seeder from the Start Command and unset `RENDER_DEMO_SEED_ENABLED`; keep `SEED_USER_PASSWORD` only if another approved process needs it.

This account is shared demo data: anyone with its password uses the same account and can see or change its notes. Share the password only with intended users and rotate it by an explicit, controlled account-management procedure; the seeder will not reset an existing password. If a public user claims `demo` before the seeder has created it, startup seeding fails and requires operator resolution; it will not adopt that account. Public registration remains available independently.

Render Free has no persistent disk attached. User records, sample data, and the provenance marker are local files under `backend/data/`, so replacements/restarts that use a fresh filesystem can lose changes. If the account and marker disappear together, the next start can create a fresh demo account; if an account remains but its marker is lost, startup fails closed and requires operator resolution. The seed does not restore other users' accounts or their data. For JSON persistence limits, run **one worker process on one instance** with a **local** `backend/data/` directory; do not assume a shared network volume makes JSON writes safe across instances (see [JSON storage and deployment limits](#json-storage-and-deployment-limits)).

### Local development: optional Main Admin auto-seed

**Disabled by default.** For local development only, `create_app()` can create the first Main Admin when **`users.json` is empty** and **no** `.ia_main_admin.json` marker exists. It does **not** promote existing accounts.

| Variable | Purpose |
|----------|---------|
| `IA_AUTO_SEED_MAIN_ADMIN` | Set to `true` to enable (requires `APP_ENV=development` or `test`) |
| `IA_AUTO_SEED_MAIN_ADMIN_USERNAME` | Non-empty username (not `demo`) |
| `IA_AUTO_SEED_MAIN_ADMIN_PASSWORD` | Non-empty password (hashed with `generate_password_hash`) |

**Refused when `APP_ENV=production`.** If the user store already has accounts, startup skips seeding silently. Uses the same `create_initial_main_admin` lock and exclusive marker create as CLI bootstrap. Never commit credentials; keep these in repo-root `.env` only.

### Production: one-time startup bootstrap (empty user store)

**Disabled by default.** When `APP_ENV=production`, a **separate** opt-in allows **one** startup pass to create the first Main Admin only if **`users.json` is empty** and **no** `.ia_main_admin.json` marker exists. It does **not** run on every restart after the marker exists, does **not** promote existing users, and is **not** the same as local `IA_AUTO_SEED_MAIN_ADMIN` (never enable both).

| Variable | Purpose |
|----------|---------|
| `IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN` | Set to `true` for the first deploy only |
| `IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_USERNAME` | Non-empty username (not `demo`) |
| `IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_PASSWORD` | Non-empty account password (hashed at rest) |
| `IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_SECRET` | Bootstrap operator secret (≥ 8 chars); host secret only |
| `IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_SECRET_CONFIRM` | Must match the secret exactly (`hmac.compare_digest`); unset after success |

**Deployment steps (fresh data directory):**

1. Set host secrets above plus `APP_ENV=production` and a valid `JWT_SECRET`. Use **one** worker/instance and a persistent mount for the app data directory if accounts must survive restarts.
2. Deploy and start the backend once. Startup creates the Main Admin account and marker, then logs a single completion line (no credentials in logs).
3. Verify login (`POST /auth/login`), then **remove** `IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN` and **all** `IA_PRODUCTION_BOOTSTRAP_MAIN_ADMIN_*` variables from the runtime environment (including secret confirm). Redeploy or restart so later boots do not carry bootstrap credentials.
4. If `users.json` already has accounts or a marker already exists, startup **skips** bootstrap without modifying data. For a non-empty store with an existing owner, use [CLI bootstrap B](#b-existing-owner-account-non-empty-user-store) instead.

Alternative: use the [CLI bootstrap](#main-admin-bootstrap) without startup flags when shell access is preferred.

### Main Admin bootstrap

Main Admin is **never** assigned during registration, demo seeding, or first login. Operators run **one** explicit bootstrap command against the deployment's **actual** user data directory (the same path the running app uses for `users.json` — locally `backend/data/`, on a host whatever persistent disk or mount is configured). There is **no** HTTP admin-creation endpoint; bootstrap is CLI-only and must be disabled after success.

**Environment variables** (host secrets / `.env`, never committed):

| Variable | Required | Purpose |
|----------|----------|---------|
| `MAIN_ADMIN_BOOTSTRAP_ENABLED` | yes (`true`) | Explicit opt-in for the one-time command |
| `MAIN_ADMIN_BOOTSTRAP_USERNAME` | yes | Case-sensitive owner username; not `demo` |
| `MAIN_ADMIN_BOOTSTRAP_SECRET` | yes (≥ 8 chars) | Confirmed on stdin via `getpass`; never logged |
| `MAIN_ADMIN_BOOTSTRAP_INITIAL_PASSWORD` | when `users.json` is empty | Initial account password (non-empty); confirmed on stdin when set |

#### A. First production account (empty user store)

Use when the deployment has **zero** users (fresh disk or first boot):

1. Stop every backend process using that data directory.
2. Set the four variables above (including `MAIN_ADMIN_BOOTSTRAP_INITIAL_PASSWORD` in host secrets for production).
3. From `backend/` on a shell that loads the same secrets and `DATA_DIR` as production: `python -m scripts.bootstrap_main_admin`.
   - Prompts: bootstrap secret (must match `MAIN_ADMIN_BOOTSTRAP_SECRET`), then initial password confirmation (must match `MAIN_ADMIN_BOOTSTRAP_INITIAL_PASSWORD` when configured).
4. Unset `MAIN_ADMIN_BOOTSTRAP_ENABLED` and remove bootstrap secrets from the runtime environment; restart the backend.
5. Sign in with `POST /auth/login` using the configured username and initial password. Normal `POST /auth/register` continues to create `user` roles only.

The command creates exactly one hashed account with role `main_admin`, writes `backend/data/.ia_main_admin.json` (or the equivalent path on the deployment disk), and refuses to run if any user already exists unless the username matches an existing account (see B).

#### B. Existing owner account (non-empty user store)

When at least one user already exists:

1. Stop the backend.
2. Set `MAIN_ADMIN_BOOTSTRAP_ENABLED`, `MAIN_ADMIN_BOOTSTRAP_USERNAME` (must match an **existing** account), and `MAIN_ADMIN_BOOTSTRAP_SECRET`. Do **not** rely on initial-password creation.
3. Run `python -m scripts.bootstrap_main_admin` and confirm the bootstrap secret on stdin.
4. Unset bootstrap env vars and restart.

The command sets only that account's role to `main_admin` and does not change passwords or other users. Reruns with the same username are idempotent. Reruns with a different username are rejected. If `users.json` already contains `main_admin` without a valid marker, the command fails closed until an operator resolves the data directory manually.

**Concurrency:** marker creation uses an exclusive file create (`O_CREAT|O_EXCL`) so two simultaneous bootstrap processes on the **same filesystem** cannot both claim ownership on the first create; this is the same class of guarantee as the Render demo marker. That does not lock `users.json` across processes afterward. Run bootstrap once while the data directory is not being served by other backend processes. **Exactly-one Main Admin is not guaranteed** across multiple app instances or hosts that do not share a single, consistently updated data directory and a single bootstrap run.

**Recovery:** stop the backend; back up `backend/data/`; restore `users.json` and `.ia_main_admin.json` together from backup, or edit them manually so one account has `main_admin` and the marker matches that `user_id` and `username`. There is no automatic recovery command in this phase.

### Runtime data backup and restore

All current user/application persistence is in JSON files under `backend/data/`; the repository does not connect to a relational or document database. Stop the backend before copying or restoring the complete directory to avoid capturing files mid-write. Store backups in access-controlled, encrypted storage and protect `.env`/signing secrets separately. For restore, stop the backend, preserve a separate copy of the current data directory, restore the selected data-directory backup, verify ownership and permissions, and restart. No production storage volume or backup schedule is declared in tracked deployment configuration.

---

## UX

Dark theme, page-based authenticated shell (`/ask`, `/manage`, `/debug`, `/settings`), shared button hierarchy, and clear loading and error states. Manage reuses Notes and History for saved-content CRUD; Ask keeps their selection workflows. The Ask toolbar offers all seven sources and defaults to Conversation, Notes, and Memory. Visibility is configurable per user in Settings and Conversation is fixed visible. Conversation is source-only, Notes has the implemented context mode, and the other modes are display-only placeholders. Ask has no file-selection/context flow despite the backend file-tree endpoint. Conversation history starts expanded, with right-aligned compact user bubbles that open a full-message detail in the shared Ask overlay. A separate Focus button beside the non-clickable Conversation History heading opens a work-only layout: the app header and Ask shortcuts are hidden while the history, question field, and Ask button remain available. Exiting focus restores the normal layout. AI responses have individual Copy controls that copy plain text with line breaks and list structure preserved. Edit switches the same message overlay to edit mode; Cancel returns to detail and Save uses the existing conversation update flow. Previous/next controls navigate only User messages. Detail: [ui.md](ui.md).
