# Documentation index

| Document | Path | Purpose |
|----------|------|---------|
| **README** | [README.md](../README.md) | Overview, quick start, API summary |
| **Project** | [project.md](project.md) | Stack, features, roadmap, configuration |
| **Session state** | [state.md](state.md) | Current State → Intent → Next (multi-machine / new AI chat) |
| **Implementation agreement** | [ia.md](ia.md) | Architecture, layers, API and engineering standards |
| **Flow** | [flow.md](flow.md) | Step-by-step traces in the codebase |
| **Testing** | [testing.md](testing.md) | Test scripts and per-endpoint reference |
| **UI** | [ui.md](ui.md) | Frontend layout, theme, components |

**Stack:** Python (repository-selected 3.13.5), Flask, Pydantic, Groq by default, startup-validated JWT authentication, ignored per-user JSON runtime storage and AI Credit ledgers, deterministic lexical note retrieval by default with optional lazy-loaded FAISS/SentenceTransformer retrieval, and React/Vite UI.

**How docs relate:** **project.md** describes what the product does today. **ia.md** describes how we build it. **flow.md** and **testing.md** help you navigate and verify behavior. **ui.md** covers the frontend.
