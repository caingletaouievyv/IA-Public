# UI/UX source of truth — IA frontend

**Updated:** 2026-03-23 · **Scope:** `frontend/` (React 18 + Vite 5). **Maintenance:** Update **Updated** when components, theme tokens, or data flow change. Doc index: `docs/docs.md`. Backend contract: `docs/project.md`. Engineering rules: `docs/ia.example.md`.

---

## Overview

| Item | Value |
|------|--------|
| **Project** | IA — personal notes & AI ask with memory |
| **Stack** | React 18.2, React DOM 18.2, Vite 5, ES modules; no router, no global state library |
| **Design goals** | Dark, low-friction SPA; token auth; floating panels for primary tasks; clear loading/errors; minimal layout shift |

---

## Folder structure

```text
frontend/
├── index.html              # Root shell, viewport meta, title "IA"
├── package.json            # Scripts: dev, build, preview
├── vite.config.js          # Dev server :5174; proxy /ai, /auth, /notes, /files, /settings → :5000
└── src/
    ├── main.jsx            # StrictMode; mounts App; imports index.css
    ├── App.jsx             # Auth gate, header, floating-window orchestration
    ├── api.js              # fetch wrappers, token storage, 401 handling
    ├── index.css             # Global theme, layout, component utility classes
    └── components/
        ├── Login.jsx
        ├── FloatingWindow.jsx
        ├── Ask.jsx
        ├── Notes.jsx
        ├── History.jsx
        ├── DebugContext.jsx
        └── Settings.jsx
```

| Path | Purpose |
|------|---------|
| `src/api.js` | Single API surface; `localStorage` token; custom event `ia:unauthorized` on 401 |
| `src/index.css` | All styling (CSS variables, floating window, notes/history chrome) |
| `src/components/*` | Feature panels rendered inside `FloatingWindow` or full-page `Login` |

---

## Theme and styling

### Colors (CSS variables, `:root`)

| Token | Hex / value | Role |
|-------|----------------|------|
| `--bg` | `#0a0a0a` | Deepest background reference |
| `--bg-subtle` | `#141414` | Subpanels, titlebars |
| `--surface` | `#1a1a1a` | Body / cards / windows |
| `--surface-hover` | `#252525` | Hover surfaces |
| `--border` | `#333333` | Borders |
| `--text` | `#e5e5e5` | Primary text |
| `--text-muted` | `#737373` | Secondary / labels |
| `--accent` / `--accent-hover` | `#5b9aff` / `#7aadff` | Links, focus, selection |
| `--hover-dark` | `#252525` | Button hover |
| `--success` | `#34c759` | Success messages (class `.success-msg`) |
| `--error` | `#f44336` | Errors, destructive hover |
| `--shadow-focus` | `0 0 0 2px rgba(91,154,255,0.35)` | Focus rings |

### Typography

| Element | Pattern |
|---------|---------|
| **Body** | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`; `15px`; `line-height: 1.55` |
| **H1 (app)** | `.app-header__title` — `1.75rem`, weight 700 |
| **Section titles** | `.section__title` / `.app-panel__title` — uppercase muted labels in toolbars |
| **Monospace** | `.out pre` — `ui-monospace` for JSON debug |

### Spacing and radii

- **Radii:** `--radius: 10px`, `--radius-sm: 6px`
- **Transitions:** `--transition: 0.2s ease` (buttons/links); floating window uses same token
- **App shell:** `.app-fullpage` — `padding: 1.5rem 1.25rem`; `min-height: 100vh`

### Responsive behavior

| Breakpoint / rule | Behavior |
|-------------------|----------|
| **Viewport** | `index.html` — `width=device-width`; content is fluid width (`max-width: none` on `#root`) |
| **`FloatingWindow` `>= 768px`** | Default window size up to `640×520` (clamped to viewport) |
| **`< 768px`** | Narrower default width (`MIN_WIDTH` 280); height capped |
| **Floating windows** | `maxWidth: calc(100vw - 2rem)`, `maxHeight: calc(100vh - 2rem)` when expanded |

### Dark / light mode

- **Implemented:** Dark-only visual system (all surfaces tuned for dark).
- **Optional / not wired:** Settings form field `theme` (text) persists via API but **does not** switch CSS or `data-theme` in this repo. `.nav-pills` styles exist in `index.css` for a tab pattern **not** used by current `App.jsx`.

---

## Components

| Component | Purpose | Props | Behavior / notes |
|-----------|---------|-------|------------------|
| **App** | Auth gate; opens/closes floating panels | — | `token` from `getToken()`; `Login` if absent; listens `ia:unauthorized`; `Header` + link-style triggers; stack of `FloatingWindow` |
| **Header** | Brand + sign out | `onLogout?: fn` | Renders logout only if `onLogout` passed |
| **Login** | Sign in / register | `onLogin(token)` | Local `username`, `password`, `isRegister`, `loading`, `error`; validates non-empty; toggles register via `link-button` |
| **FloatingWindow** | Draggable, resizable, collapsible shell | `title`, `id`, `initialPosition`, `onClose`, `onBringToFront`, `isFront`, `stackIndex`, `collapsedStackIndex`, `onCollapsedChange`, `children` | Position/size per-id in `localStorage` (`ia-floating-window-{id}`); collapse docks bottom-left with horizontal stack; double-click titlebar or toggle button; resize handle; `zIndex` bump when front |
| **Ask** | `/ai/ask` + optional `note_ids` + conversation | — | Loads histories (`listHistories`); optional `currentHistoryId` + `messages` JSON in note; checkbox note pick (`listNotes`, exclude `_history`); `ask(question, noteIds, messages)`; persists turns via `updateNote` |
| **Notes** | CRUD, search, bulk delete, image import | — | List vs add (`note` \| `from-images`) vs detail edit; `getNotesMeta` for tag/category suggestions; client search; first **100** matches shown; visibility + 30s poll when list visible; `_history` hidden |
| **History** | Conversations (`_history` notes) | — | Same list/card/toolbar patterns as Notes; title edit; single + bulk delete modals; visibility + 30s refresh when list visible |
| **DebugContext** | Inspect retrieval context | — | `debugContext(question, null)`; JSON in `<pre>` |
| **Settings** | GET/PUT `/settings/` | — | Manual “Load settings”; form `theme`, `default_model`; optimistic local `prefs` merge |

**Internal helpers (not exported UI):** `App` uses `newFloatId()`, `FLOAT_OFFSET`, `UNAUTH_EVENT`; `Notes` / `History` share confirm modal classes `.notes-delete-confirm*`.

---

## Layout and pages

| Layer | Structure |
|-------|-----------|
| **Unauthenticated** | Full viewport flex center (`.login-page`) → centered `.login-card` |
| **Authenticated** | `.app-fullpage` column: flex header (`.app-header--main`), row of `.float-triggers` (`link-button` + `·` separators), then N `FloatingWindow` instances (`position: fixed`) |
| **Inside windows** | `.floating-body` — column flex, `flex: 1`, `min-height: 0`, scroll with thin themed scrollbar |
| **Panels** | Repeated pattern: `.section`, `.card.app-panel`, `.form--compact`, `.app-panel__title` |
| **Grids** | `.form-row` — `grid-template-columns: 1fr 1fr` (available for forms; used where applicable in CSS) |
| **Notes / History lists** | `.notes-list-header` — flex wrap: search or title left, toolbar right; `.notes-list` — vertical flex list of `.note-card` |

**No route-based pages:** “Pages” are modes inside `Notes`/`History` (list vs detail vs add) and which floating window is open.

---

## UX patterns

| Pattern | Implementation |
|---------|----------------|
| **Loading** | `loading` state + `className` `loading` on forms (opacity ~0.7, `pointer-events: none`); submit labels `…` or `Saving…` / `Deleting…`; buttons `disabled` |
| **Errors** | `div.out.err` or `out out--compact err`; API throws → `catch` → `setError` |
| **Empty states** | `.notes-list-empty` copy for no data, no search hits, loading initial list |
| **Success** | `.success-msg` or plain text in `.out`; Notes/History use `out--compact` |
| **Forms** | HTML5 `label` + `htmlFor`; required fields validated in handlers before API |
| **Destructive** | Modal `.notes-delete-confirm` (backdrop click dismiss); `.notes-toolbar-btn--danger` |
| **Focus / keyboard** | `:focus-visible` + `box-shadow: var(--shadow-focus)` on buttons/inputs; note cards `role="button"` + Enter/Space; floating titlebar keyboard toggles collapse |
| **Interaction** | `button:active { transform: scale(0.98) }`; link-style actions via `.link-button` |

---

## State and data handling

| Concern | Approach |
|---------|----------|
| **Global auth** | `App` holds `token`; syncs with `api.setToken` / `getToken`; 401 clears token and dispatches `ia:unauthorized` |
| **React context** | **Not used** |
| **Hooks** | Per-component `useState`, `useEffect`, `useRef`, `useCallback` (`FloatingWindow` only) |
| **API layer** | `api.js`: relative `BASE ""` (same origin or Vite proxy); `Authorization: Bearer`; `handleResponse` for 401/Errors |
| **Data flow** | Components call `api` directly; parent passes callbacks only where needed (`Login.onLogin`, `FloatingWindow` callbacks, `Header.onLogout`) |
| **Persistence** | `localStorage`: `ia_token`, `ia-floating-window-{id}` window geometry |

---

## Real-world features layer

| Feature | Where |
|---------|--------|
| **Filtering** | Client-side: `Notes` search on title/category/content/tags; `History` search on title |
| **Pagination** | **Not generic API pagination.** Notes list UI caps display at **100** items with “Showing first 100.” (`limit: 500` fetch) |
| **Caching** | No SWR/React Query; optional refresh on visibility + 30s interval for Notes/History lists |
| **Logging** | No frontend analytics/logger |
| **Middleware** | Vite dev proxy only; no client interceptors beyond `fetch` wrappers |

---

## UX principles (as implemented)

- **Maintainability:** One global stylesheet; BEM-like prefixes (`.app-header__`, `.note-card__`, `.floating-*`); feature components colocated under `components/`.
- **Consistency:** Shared `.notes-*` toolbar/card/modal classes between Notes and History; Ask/Debug/Settings use same `.card` / `.form--compact` / `.out` language.
- **Predictability:** Floating windows remember size/position; collapse stack is deterministic; 401 always clears session via same event.
- **Accessibility:** Labels, `aria-*` on several controls, dialog roles on confirms, visible focus rings.

### Reusable patterns

1. **CSS variable theme** — single `:root` contract for color, radius, shadow, transition.
2. **`api.js` pattern** — token helper, `handleResponse`, 401 → clear + event (decouples components from auth side effects).
3. **`.loading` on form** — disables interaction without ad hoc spinners everywhere.
4. **`.out` / `.out.err` / `.meta`** — consistent result and error blocks.
5. **Floating window + persisted geometry** — self-contained shell for multi-panel desktop-like UX.
6. **List refresh on `visibilitychange` + interval** — simple staleness control without a data library.

---

## Notes for reuse

- Cross-reference: `docs/ia.example.md` (engineering rules), `docs/project.md` (API shapes, auth).
- When adding routes, either adopt unused `.nav-pills` or remove dead CSS to avoid drift.
- If implementing real light mode, add `data-theme` (or class) on `document.documentElement` and mirror `:root` tokens; wire Settings `theme` to that toggle.
- New panels should follow: `section.section--*` → `card app-panel` → optional `form--compact` → `out` for feedback.
