# IA — AI Agent Instructions

When working in this repository, load context in this order before responding to project questions:

1. `START_HERE.md`
2. `.cursor/rules/ia-repo.mdc` (auto-applied by Cursor)
3. `docs/docs.md` — documentation index
4. `docs/state.md` — current implementation snapshot
5. `docs/ia.md` — engineering agreement
6. `docs/project.md` — product, stack, roadmap

Then load only the relevant document per `docs/docs.md` (`flow.md`, `testing.md`, `ui.md`, `understanding-gaps.md`, `architecture/*`).

Rules:
- Treat this repo as structured context, not unquestionable truth. Check dates on state files.
- Never store secrets, credentials, API keys, tokens, passwords, or NDA-protected material.
- Do not assume missing information; state what's missing and ask.
- Keep changes simple and compatible with the existing architecture (`docs/ia.md`).
- Run relevant tests and `git diff --check` before considering a change complete.
- Do not commit, push, or deploy unless explicitly instructed.

## Workflow (Cursor strat)

OpenCode is the brain + git owner. Cursor is the code executor.

- The user may ask about issues, tasks, or bugs. OpenCode reads context, plans, and provides a clear Cursor instruction block (files to touch, what to do, constraints, relevant source-of-truth refs such as `docs/ia.md`, `docs/project.md`, `docs/state.md`, `docs/flow.md`, `docs/testing.md`).
- The user pastes that block into Cursor, which implements the code. The user tests and reports back to OpenCode.
- OpenCode then updates materially affected docs, commits with a clear prefix, and pushes to `origin/main` only when explicitly instructed.
- OpenCode may write code directly if asked, but the preferred strat is handoff to Cursor so context stays the single source of truth.
- Always ground Cursor instructions in the actual repo truth rather than guessing.
- No conversation logs are kept in this repo (by design).
" 
path">
C:\Users\Aouie Vyv Cainglet\IA\AGENTS.md