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

**Stack:** Python (repository-selected 3.13.5), Flask, Pydantic, Groq by default, startup-validated JWT authentication, ignored per-user JSON runtime storage for Notes, internal suggestion activity metadata, independent Memory (including keyed mutable preferences), Settings, and AI Credit ledgers, bounded lexical retrieval with AI-assisted matching for low-overlap Memory queries and metadata-only contextual suggestions, and React/Vite UI.

**How docs relate:** **project.md** describes what the product does today. **ia.md** describes engineering, architecture, security, and testing conventions. **flow.md** and **testing.md** help you navigate and verify behavior. **ui.md** covers the frontend.
