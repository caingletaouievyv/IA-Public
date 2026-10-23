# IA — Engineering agreement

This document defines the lightweight engineering conventions for IA. The product and configuration reference is [project.md](project.md); use [docs.md](docs.md) as the documentation index.

## Architecture principles

- Keep the Flask API, React UI, and runtime data responsibilities separate.
- Backend feature code lives under `backend/app/<feature>/`; keep HTTP handling in `routes.py` and business/use-case logic in `manager.py` or `engine.py`.
- Prefer the existing feature structure and helpers over duplicate implementations.
- Validate external request data at the API boundary. Keep route handlers thin and return deliberate HTTP status codes.
- Frontend components own presentation and interaction state; use the existing API client for backend requests and existing shared controls/styles where practical.
- Keep Notes, Conversation History, and persistent Memory distinct. Memory uses per-user records in its own store, with settings and authenticated CRUD; it must not use Notes or history as a backing store. Mutable preferences use a stable key where available, and legacy records are recognized lazily without destructive migration.
- For future natural-language operations, use the [AI-assisted decision workflow](architecture/ai-assisted-workflows.md): AI proposes an interpretation; application code remains responsible for validation, authorization, domain operations, and outcome verification.
- Record actual prompt-understanding/provider fallback gaps using the allow-listed, content-free logger and review format in [understanding-gaps.md](understanding-gaps.md). Do not log prompts, notes, credentials, provider output, or exception messages. Treat valid empty/no-match outcomes as expected unless a sanitized regression demonstrates a miss.
- Contextual suggestions may use only fixed, content-free event metadata unless the user has separately consented to sharing Note content. Validate model-selected actions against an application allow-list, and keep the accepted operation under normal application authorization and user confirmation.

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
- `backend/scripts/seed_user.py` is limited to explicit development/test environments. The separate `backend/scripts/seed_render_demo.py` production command requires `APP_ENV=production`, `RENDER_DEMO_SEED_ENABLED=true`, and a password-manager-generated random `SEED_USER_PASSWORD`; it refuses an existing `demo` account unless its instance-local user-ID marker matches. Do not commit or log the password.
- Protected API routes must use the existing authentication boundary and derive per-user data access from the authenticated user identity.
- Treat model-produced Memory candidates as untrusted: require bounded schema-valid records grounded in non-empty user-message evidence; classify durable user facts/preferences, assistant preferences, temporary instructions, questions, ordinary requests, and explicit remember/forget requests. Do not retain ordinary questions or temporary instructions. Apply temporary scope to the relevant preference candidate, not the entire message: a temporary assistant-name instruction must not prevent a separate durable fact in the same message from being considered. Quoted, reported, or hypothetical name instructions must not overwrite a saved assistant-name preference. Mutable assistant-name preferences use the stable `assistant.name` key; deduplicate/upsert that key and retrieve only its latest value. Existing unkeyed assistant-name records are recognized from their text and reconciled when updated or filtered at retrieval; no destructive migration is required. Each sensitive candidate needs its own affirmative, targeted remember request in the current user message, with candidate-specific factual terms supported by the request and quote. Reject uncertain, negated, corrected, retracted, or subsequently revoked claims rather than storing them as established facts. An explicit request to forget or stop remembering a specific sensitive fact removes its unique, standalone matching record for the authenticated user only if the record is unchanged when re-read under the in-process Memory store lock. If the target is ambiguous or the record changed or contains a compound fact that cannot be safely edited in place, fail closed without deleting it. Corrections alone do not delete existing records. Do not let consent for one candidate authorize another. Authenticated user edits explicitly authorize sensitive personal details, but credentials/secrets remain rejected regardless of consent. Scope IDs to the authenticated user's records and label saved memories and prior conversation turns as untrusted context, never executable instructions.
- Use deterministic fast paths only for supported standalone assistant-name preferences, recognized standalone temporary name commands, and other clearly non-memory cases. Ambiguous or compound messages use one existing structured extraction request; validate and apply each candidate independently. Test provider-call expectations with mocks and do not imply those tests guarantee live-model semantic accuracy.
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
