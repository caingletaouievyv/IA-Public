# Documentation index

| Document | Path | Purpose |
|----------|------|---------|
| **README** | [README.md](../README.md) | Overview, quick start, live demo link |
| **Setup** | [setup.md](setup.md) | Local development, `.env`, seeding, deployment notes |
| **Project** | [project.md](project.md) | Stack, features, roadmap, configuration |
| **AI-assisted workflows** | [architecture/ai-assisted-workflows.md](architecture/ai-assisted-workflows.md) | Pattern for natural-language operations and safeguards |
| **Flow** | [flow.md](flow.md) | Step-by-step traces in the codebase |
| **Testing** | [testing.md](testing.md) | Test scripts and per-endpoint reference |
| **UI** | [ui.md](ui.md) | Frontend layout, theme, components |

**Stack:** Python 3.10+, Flask, Pydantic, PostgreSQL, Groq by default, JWT authentication, optional semantic Notes retrieval (temporary FAISS), lexical Memory retrieval, React/Vite UI. See [project.md](project.md).

**How docs relate:** **project.md** describes what the product does. **flow.md** and **testing.md** help you navigate and verify behavior. **ui.md** covers the frontend.
