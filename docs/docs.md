# IA — Documentation index

**Updated:** 2026-03-23 · **Maintenance:** Bump **Updated** when you add, remove, or rename docs; keep the table in sync with [README.md](../README.md).

**Layout:** Detailed specs live in **`docs/`**. **`README.md`** stays at the **repository root** (runbook, feature/API table, quick start, first contact).

| Doc | Path (from repo root) | Use it for |
| --- | --- | --- |
| **README.md** | `README.md` | Run commands, demo steps, feature overview, quick start, seed script pointer. |
| **docs.md** | `docs/docs.md` | This index. |
| **project.md** | `docs/project.md` | Plan, roadmap, stack, folder tree, memory/FAISS rules, current state, tuning, run/seed/CORS. |
| **ia.example.md** | `docs/ia.example.md` | Tracked implementation agreement — architecture, API conventions, workflow, agent rules. |
| **ia.md** (optional) | `docs/ia.md` | Gitignored local copy; create from `ia.example.md` if you need private overrides. |
| **ui.md** | `docs/ui.md` | Frontend UX source of truth — layout, theme, components, patterns. |
| **flow.md** | `docs/flow.md` | Request/feature flows: step → where → what to read in code. |
| **testing.md** | `docs/testing.md` | How to run test scripts; per-API expectations and curl examples. |

**Stack:** Python 3.10+, Flask, Pydantic, Groq (default LLM), JWT auth, JSON per-user storage, FAISS memory · React 18 (Vite). See **`docs/project.md`** for detail and free-tier providers.

**Rule:** If **`docs/project.md`** and **`docs/ia.example.md`** disagree on *how* to build, follow **`docs/ia.example.md`**. For *what the product does today* (endpoints, behavior), follow **`docs/project.md`**. If you maintain a local **`docs/ia.md`**, it is not shared via Git; collaborators use **`ia.example.md`** only.
