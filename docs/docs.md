# Documentation index

| Document | Path | Purpose |
|----------|------|---------|
| **README** | [README.md](../README.md) | Overview, quick start, API summary |
| **Project** | [project.md](project.md) | Stack, features (including contextual AI Suggestions), roadmap, configuration |
| **Session state** | [state.md](state.md) | Current State → Intent → Next (multi-machine / new AI chat) |
| **Implementation agreement** | [ia.md](ia.md) | Engineering principles, architecture, security, and testing conventions |
| **AI-assisted workflows** | [architecture/ai-assisted-workflows.md](architecture/ai-assisted-workflows.md) | Reusable pattern, safeguards, and adoption candidates for natural-language operations |
| **Understanding gaps** | [understanding-gaps.md](understanding-gaps.md) | Content-free fallback diagnostics, known gaps, and review format |
| **Flow** | [flow.md](flow.md) | Step-by-step traces in the codebase |
| **Testing** | [testing.md](testing.md) | Test scripts and per-endpoint reference |
| **UI** | [ui.md](ui.md) | Frontend layout, theme, components |

**Stack:** Python (repository-selected 3.13.5), Flask, Pydantic, Groq by default, startup-validated JWT authentication, PostgreSQL storage for accounts, Notes, Memory, Settings, AI Credit ledgers, activity events, diagnostics, and pending Ask confirmations, with lexical Notes retrieval by default and optional semantic retrieval that builds a temporary in-memory FAISS index from the authenticated user's PostgreSQL notes and discards it. Persistent Memories use PostgreSQL and lexical retrieval, not FAISS. The persistent pickle cache has been removed. SentenceTransformer weights may download into the local Hugging Face cache. Bounded lexical retrieval with AI-assisted matching covers low-overlap Memory queries, with metadata-only contextual suggestions and a React/Vite UI. See [project.md — JSON storage and deployment limits](project.md#json-storage-and-deployment-limits).

**How docs relate:** **project.md** describes what the product does today. **ia.md** describes engineering, architecture, security, and testing conventions. **flow.md** and **testing.md** help you navigate and verify behavior. **ui.md** covers the frontend.
