# IA — Engineering agreement

This document defines the lightweight engineering conventions for IA. The product and configuration reference is [project.md](project.md); use [docs.md](docs.md) as the documentation index.

## Architecture principles

- Keep the Flask API, React UI, and runtime data responsibilities separate.
- Backend feature code lives under `backend/app/<feature>/`; keep HTTP handling in `routes.py` and business/use-case logic in `manager.py` or `engine.py`.
- Prefer the existing feature structure and helpers over duplicate implementations.
- Validate external request data at the API boundary. Keep route handlers thin and return deliberate HTTP status codes.
- Frontend components own presentation and interaction state; use the existing API client for backend requests and existing shared controls/styles where practical.
- Keep Notes, Conversation History, and persistent Memory distinct. Memory uses per-user records in its own store, with settings and authenticated CRUD; it must not use Notes or history as a backing store.

## Code conventions

- Prefer simple, concise code and clear names over unnecessary abstraction.
- Add comments for non-obvious decisions, not line-by-line narration.
- Follow existing file-header conventions: source path header where established, followed by a short description when useful.
- Avoid adding dependencies for small UI needs that can be met with existing utilities or inline SVG.
- Keep loading, error, empty, disabled, keyboard-focus, and accessible-name states in UI changes.
- Do not remove existing user data or silently overwrite a user's saved content when adding seed/demo behavior.

## Security and configuration

- Never commit `.env`, runtime data, private keys, tokens, or real credentials.
- Never log passwords, provider keys, JWTs, or `JWT_SECRET`.
- Configuration secrets must come from environment configuration; do not hardcode deployable credentials in source.
- The Flask app requires a strong configured `JWT_SECRET` at startup.
- Demo seeding is limited to explicit development/test environments and requires a configured `SEED_USER_PASSWORD`. Never use the seed utility in production.
- Protected API routes must use the existing authentication boundary and derive per-user data access from the authenticated user identity.
- Treat model-produced Memory candidates as untrusted: require bounded schema-valid records grounded in user-message evidence, reject credentials/secrets, scope IDs to the authenticated user's records, and label saved memories as untrusted background context in prompts.
- Development/test rewarded-ad grants are not proof of ad completion; production credit grants require server-side provider verification.

## Documentation and testing

- Keep [docs.md](docs.md), [project.md](project.md), [state.md](state.md), [flow.md](flow.md), [testing.md](testing.md), [ui.md](ui.md), and [README.md](../README.md) consistent with implemented behavior.
- Update documentation when routes, API behavior, user-facing workflows, configuration, or test commands change.
- Run relevant backend tests and compilation, the frontend production build, focused frontend tests, and `git diff --check` before considering a change complete.
- Do not claim browser/manual checks were run unless they were actually performed.
- Review the full diff and staged file list before committing; do not commit or push unless requested.

## Repository layout

- `backend/app/`: Flask application, feature routes/managers/engines, configuration, and adapters.
- `backend/scripts/`: maintenance, seed, analysis, and test scripts.
- `frontend/src/`: React SPA, API client, reusable components, and styles.
- `docs/`: product, engineering, flow, testing, state, and UI documentation.
- `backend/data/` and root `.env`: local runtime/configuration only; both are excluded from source control.
