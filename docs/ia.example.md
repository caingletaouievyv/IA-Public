# IA — Implementation Agreement

**Updated:** 2026-03-23  
**Maintenance:** Update the **Updated** date when engineering rules, layers, or API standards change. Keep the document role table aligned with [docs.md](docs.md).

---

## Single source of truth

All architecture, code, and decisions must align with this document and with **[project.md](project.md)** (stack, roadmap, product features, tuning).  
**If conflict exists:** this file wins for *engineering rules*; **project.md** wins for *current product behavior and endpoints*.

| Doc | Role |
|-----|------|
| **[docs.md](docs.md)** | Documentation index — start here for paths and roles |
| **ia.example.md** (this file) | Agreement: principles, layers, API norms, cross-cutting standards |
| **[project.md](project.md)** | Product state: tech detail, folder tree, roadmap, memory/FAISS, features list |
| **[flow.md](flow.md)** | Step-by-step traces per feature |
| **[testing.md](testing.md)** | How to run tests and smoke APIs |
| **[ui.md](ui.md)** | Frontend UI/UX source of truth |

---

## Core rules

- Prefer simple solutions over complex ones.  
- Prefer consistency over one-off creativity.  
- Prefer explicit behavior over implicit magic.  
- Prefer maintainable code over clever shortcuts.  
- Prefer configuration (env / `config.py`) over hardcoded literals in business logic.

**Framework:** State → Intent → Action (state current behavior, then intent, then change).

**Repository conventions:** keep modules small and readable; one short comment per logical block; first line of each source file is the canonical path (`# IA/...` in Python, `// IA/...` in JavaScript).

---

## System goal

Build systems that are:

- Predictable  
- Scalable  
- Easy to onboard  
- Easy to extend  
- Suitable for production with clear configuration and operations  

**IA product goal (summary):** personal context storage and recall with multi-provider AI; minimize token cost; transparent configuration. Detail: [project.md](project.md).

---

## Architecture standard (IA mapping)

This repo is **Flask + Python**, not ASP.NET. Map the default pattern as follows:

| Generic layer | IA implementation |
|---------------|-------------------|
| **Controller** (HTTP only) | **Routes** in `backend/app/<feature>/routes.py` — parse body/query, validate (Pydantic), call one manager/engine function, return JSON |
| **Service** (logic, orchestration) | **`manager.py`**, **`engine.py`** — no Flask `request` / `g`; rules and orchestration here |
| **Data** (persistence only) | JSON files under `backend/data/`, FAISS/embeddings adapters, external LLM HTTP (`client.py`) |
| **DTO / contract** | **Pydantic schemas** next to routes; request/response shapes documented in testing.md / project.md when they change |

**Clean architecture (dependencies inward):**

1. **Presentation** — Routes; frontend components + `api.js`. No business logic.  
2. **Use cases** — Engine, manager.  
3. **Adapters** — LLM client, embeddings, file storage; `config.py` + `.env`.

**Rules:** Validate at the boundary (Pydantic). One concern per module. New code respects these layers. See also `.cursor/rules/ia-repo.mdc`.

---

## Standard structure

### Backend (actual)

```text
backend/
├── run.py
├── requirements.txt
├── app/
│   ├── __init__.py      # factory, blueprints
│   ├── config.py
│   ├── ai/              # routes, engine, client
│   ├── auth/
│   ├── common/          # JWT helpers, shared auth
│   ├── files/
│   ├── memory/          # FAISS, chunker, manager pieces, analytics
│   ├── notes/
│   └── settings/
├── data/                # users, notes_*, settings_*, analytics, faiss artifacts
└── scripts/             # analytics, seed_user, test/
```

### Frontend (actual)

```text
frontend/src/
├── main.jsx
├── App.jsx
├── index.css
├── api.js               # centralized fetch + token
└── components/          # Login, FloatingWindow, Ask, Notes, History, DebugContext, Settings
```

**Optional evolution (portfolio alignment):** add `hooks/`, `context/`, `pages/` when a feature needs them; keep **presentation-only** in components.

---

## API design standard

- **REST-style** resources: `/auth/*`, `/notes/*`, `/ai/*`, `/settings/*`, `/files`, `/health`.  
- **HTTP verbs** used as appropriate (GET/POST/PUT/DELETE).  
- **Versioning:** optional future prefix (e.g. `/api/v1/...`); not required today.

### Response format

**Portfolio target (strict envelope):**

```json
{
  "success": true,
  "message": "",
  "data": {}
}
```

**Current IA APIs:** many endpoints return **resource-specific JSON** directly (e.g. `{ "answer", "tokens_estimated" }`, arrays for GET `/notes/`, `{ "token", "user_id" }` for login). That is **allowed** until refactored; new public APIs should prefer the envelope where practical. Document shape changes in **project.md** / **testing.md** / commit message.

**Rules:**

- Do not leak stack traces or internal exceptions to clients; use clear HTTP status + safe message.  
- No business logic in routes.  
- Idempotent where applicable (e.g. safe GET).  
- **Pagination-ready:** list endpoints should evolve toward `page` / `pageSize` / totals; today notes list uses `limit` — see [project.md](project.md).

---

## Real-world features layer

### Pagination

- **Target:** `GET /resource?page=1&pageSize=10` with `{ items, page, pageSize, totalCount, totalPages }` inside `data`.  
- **Current:** GET `/notes/` supports `limit`; UI caps display (see [ui.md](ui.md)). Implement slicing in manager layer when adding full pagination.

### Filtering and search

- Query params where applicable (e.g. `category`, `tag`, `limit`).  
- Logic in **manager**, not routes.

### Caching

- Read-heavy paths may use in-memory or explicit caches **in manager/service layer** with TTL.  
- Do not cache security-sensitive or must-be-fresh auth decisions incorrectly.  
- IA memory layer has optional analytics and temp FAISS per request — see [project.md](project.md).

### Logging

- Structured or consistent log lines for errors, important mutations, external API calls.  
- Levels: info / warning / error as appropriate.  
- **Never** log secrets, JWTs, or API keys.  
- IA: request logging and limits described in [project.md](project.md) (Phase 6).

### Error handling

- Prefer consistent JSON errors; avoid exposing internal details.  
- Frontend: show user-safe messages (`api.js` + UI patterns in [ui.md](ui.md)).

### Configuration

- **`.env`** (repo root) + **`config.py`** — no secrets in code; no hardcoded provider keys.

### Feature toggles (optional)

- Use env flags (e.g. `MEMORY_ANALYTICS_ENABLED`, `AI_MODE`) — same idea as `appsettings` feature blocks.

### Rate limiting

- Applied at app level (e.g. Flask-Limiter on hot POST routes). Details: [project.md](project.md).

### Auth

- **Implemented:** JWT access token after login/register; `Authorization: Bearer <token>`.  
- **Refresh tokens / roles:** not required for current IA; design should allow adding middleware and claims later without putting auth logic inside managers.

---

## Backend engineering standards

- **Dependencies:** Flask factory + blueprints; inject shared helpers via imports and app config (explicit over hidden IoC).  
- **I/O:** use async only where the stack already does; otherwise clear synchronous flows with timeouts where needed.  
- **Validation:** Pydantic at route boundary; business rules in manager/engine.  
- **Errors:** map to HTTP status + safe body; no raw exception text to clients.

---

## Frontend engineering standards

- **UI = presentation only**; **backend = source of truth** for rules and data.  
- **Centralized API:** `api.js`.  
- **Typing:** optional future TypeScript; JS is acceptable for this repo.  
- **Reusable components** under `components/`.  
- **UX:** loading, error, empty states — see [ui.md](ui.md).  
- **Auth:** login gate in `App.jsx`; 401 clears token and returns to login (`ia:unauthorized` event).

---

## State and data flow

- Backend owns persistence and business rules.  
- Frontend consumes APIs; no duplicated business logic.  
- Token in `localStorage`; see `api.js`.

---

## Testing strategy

- **Backend:** scripts under `backend/scripts/test/`; manual curl per [testing.md](testing.md). Prefer unit tests for pure logic in managers when added.  
- **Frontend:** manual + optional future component/e2e tests.  
- Keep `scripts/test/` runnable when changing APIs.

---

## Development workflow

1. Read **ia.example.md** + **project.md** for the task (optional local `docs/ia.md` is gitignored; use the tracked example for shared truth).  
2. Define state (what exists).  
3. Define intent (what should change).  
4. Execute action (minimal diff, correct layer).  
5. Validate against this agreement and **project.md**; update **flow.md** / **testing.md** / **ui.md** when behavior changes; update **docs.md** if the doc set or roles change.

---

## Engineering principles

- Ship a minimal viable scope first; expand when needed.  
- Prefer composition over duplication.  
- Avoid premature abstraction.  
- Prefer readability over cleverness.

---

## Constraints

- No mixed responsibilities across layers.  
- No hidden magic (document env flags and endpoints).  
- No inconsistent structure (follow feature folders above).  
- No overengineering.

---

## Decision rule

If multiple solutions exist: choose the **simplest** that keeps **consistency** and leaves room to scale (pagination envelope, clear layers).

---

## Mapping from other stacks

Other codebases may use Controllers/Services/EF Core and versioned `/api/v1` routes with strict JSON envelopes. This repository applies the same layering ideas using Flask, Python, and React as described above. When reusing patterns, map responsibilities, not folder names literally.

---

## Review checklist

If a change violates layers or secrets rules, restate **State → Intent → Action** and realign with **ia.example.md** and **project.md**.

---

## Rules for AI (agents)

| Principle | Rule |
|-----------|------|
| **Sync** | Check **ia.example.md** (tracked) and **project.md** before acting; product behavior must match **project.md**. |
| **Architecture** | Presentation → use cases → adapters; no business logic in routes or React beyond UI state. |
| **Secrets** | Never commit `.env`; never log API keys, tokens, `JWT_SECRET`, passwords. |
| **APIs** | Document request/response changes in **project.md** and/or **testing.md** and commit message. |
| **Tests** | Keep `scripts/test/` runnable; add tests when practical. |
| **Docs** | Keep docs.md, ia.example.md, flow.md, testing.md, README, ui.md, project.md in sync when behavior changes. |
| **UX** | [ui.md](ui.md) — dark theme, loading/errors, floating windows, accessibility. |

Keep documentation and code structure consistent across changes.
