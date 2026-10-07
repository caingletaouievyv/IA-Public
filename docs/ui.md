# IA UI — page-based frontend reference
# UI reference — frontend

React 18 + Vite 5 SPA. Index: [docs.md](docs.md). API contract: [project.md](project.md). Engineering rules: [ia.md](ia.md).

---

## Overview

| Item | Value |
|------|--------|
| **Project** | IA — personal notes & AI ask with memory |
| **Stack** | React 18.2, React DOM 18.2, Vite 5, ES modules; no router, no global state library |
| **Design goals** | Dark, low-friction SPA; token auth; page-based authenticated shell; clear loading/errors; minimal layout shift |

---

## Folder structure

```text
frontend/
├── index.html              # Root shell, viewport meta, title "IA"
├── package.json            # Scripts: dev, build, preview
├── vite.config.js          # Dev server :5174; proxy /ai, /auth, /notes, /files, /settings → :5000
└── src/
    ├── main.jsx            # StrictMode; mounts App; imports index.css
    ├── App.jsx             # Route navigation, auth gate, authenticated page shell
    ├── api.js              # fetch wrappers, token storage, 401 handling
    ├── index.css             # Global theme, layout, component utility classes
    └── components/
        ├── PublicSite.jsx
        ├── Login.jsx
        ├── Ask.jsx
        ├── Notes.jsx
        ├── History.jsx
        ├── DebugContext.jsx
        └── Settings.jsx
```

| Path | Purpose |
|------|---------|
| `src/api.js` | Single API surface; `localStorage` token; custom event `ia:unauthorized` on 401 |
| `src/index.css` | All styling (CSS variables, app shell, notes/history chrome) |
| `src/components/*` | Feature panels rendered in the authenticated page shell or full-page `Login` |

---

## Theme and styling

### Colors (CSS variables, `:root`)

| Token | Hex / value | Role |
|-------|----------------|------|
| `--bg` | `#0a0a0a` | Deepest background reference |
| `--bg-subtle` | `#141414` | Subpanels |
| `--surface` | `#1a1a1a` | Body / cards |
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
- **Transitions:** `--transition: 0.2s ease` (buttons/links)
- **App shell:** `.app-fullpage` — `padding: 1.5rem 1.25rem`; `min-height: 100vh`

### Buttons and actions

- Native buttons share a 40px minimum height, theme border/radius, aligned content, medium-weight text, and token-based hover, pressed, disabled, and `:focus-visible` states. At widths below 768px, controls and icon buttons use a 44px minimum touch target.
- Use `.button-primary` for the main action, `.button-secondary` for supporting controls, `.button-subtle` for quiet toolbar/shortcut actions, `.button-danger` for destructive actions, and `.button-icon` for square icon controls. Subtle actions have a visible resting surface and border; destructive actions retain a quiet danger border at rest. `.button-toggle[aria-pressed="true"]` styles stateful toggles; keep `aria-expanded` for disclosure controls.
- Use `.nav-pills` for app navigation and pair `.link-button` with `.button-subtle` for quiet app actions. Login account switching is an exception: `.auth-switch` uses a muted question prefix and a bare, accent-colored `.auth-switch__action` with a visible `:focus-visible` ring, not a button surface or border. Every icon-only control needs an accessible name and a `title` tooltip.
- Ask shortcuts retain their compact visual language through `.ask-shortcut` and use the shared subtle/focus/pressed behavior. Keep button groups aligned with `align-items: center` and consistent gaps; use visible labels for non-universal actions.

### Responsive behavior

| Breakpoint / rule | Behavior |
|-------------------|----------|
| **Viewport** | `index.html` — `width=device-width`; content is fluid width (`max-width: none` on `#root`) |
| **Desktop** | Full-page shell with centered content and horizontal navigation |
| **`< 768px`** | Full-page shell stacks naturally, wraps controls, and uses normal document scrolling |

### Dark / light mode

- **Implemented:** Dark-only visual system (all surfaces tuned for dark).
- **Optional / not wired:** Settings form field `theme` (text) persists via API but **does not** switch CSS or `data-theme` in this repo. `.nav-pills` styles exist in `index.css` for a tab pattern **not** used by current `App.jsx`.

---

## Components

| Component | Purpose | Props | Behavior / notes |
|-----------|---------|-------|------------------|
| **App** | Public/auth route handling, auth gate, page navigation | — | Public `/`, `/privacy`, `/terms`, `/contact`; auth `/login`, `/register`; authenticated `/ask`, `/debug`, `/settings` (default `/ask`). Uses `pathname`, `pushState`, and `popstate`; listens for `ia:unauthorized`; Notes and History are Ask-owned workflows. |
| **PublicSite** | Landing, Privacy, Terms, Contact | `path` | Path-based public shell with shared header/footer; no router or API dependency |
| **Header** | Brand + sign out | `onLogout?: fn` | Renders logout only if `onLogout` passed |
| **Login** | Sign in / register | `onLogin(token)`, `initialIsRegister`, `onModeChange` | Local `username`, `password`, `isRegister`, `loading`, `error`; validates non-empty; mode changes synchronize `/login` and `/register` |
| **Ask** | `/ask`: question, conversation, and optional note context | — | Owns draft, messages, active conversation, selected notes, context mode, and loading/error state. Conversation and Notes open in-place selectors and management views without unmounting Ask. Conversation History initially renders expanded; user turns are editable inline and saved through the existing Ask flow. Mode cycles Off → Focused → Automatic → Off. Turns persist in `_history` notes through `updateNote`; there is no edit endpoint. |
| **Notes** | Ask-owned note selection and management | `isSelectionMode`, `selectedIds`, `onSelect`, `onCloseSelection` | Existing CRUD, search, bulk delete, and image import are available in Ask's Manage view. The selector supports selecting notes, creating notes, and optionally selecting a newly created note before confirming. `getNotesMeta` supplies suggestions; first **100** matches shown; `_history` hidden. |
| **History** | Ask-owned conversation selection and management | `isSelectionMode`, `activeId`, `onSelect`, `onCloseSelection` | Existing list, title edit, and single/bulk delete remain in Ask's Manage view. The selector supports selecting an existing conversation or creating a new one; callbacks return the conversation ID to Ask. |
| **DebugContext** | Inspect retrieval context | — | `debugContext(question, null)`; JSON in `<pre>` |
| **Settings** | `/settings`; GET/PUT `/settings/` | — | Manual “Load settings”; form `theme`, `default_model`; local `prefs` merge |

**Internal helpers (not exported UI):** `App` owns route and auth transitions; `Notes` / `History` share confirm modal classes `.notes-delete-confirm*`.

### Route navigation

- App navigation uses native links with centralized `pushState` handling; `popstate` keeps Back/Forward synchronized with React.
- Direct loads and refreshes are served by Flask SPA routes for public, auth, and authenticated frontend paths.
- The active page is identified by `aria-current="page"` and a subtle accent surface.

### Ask shortcuts and conversation behavior

- **Conversation** opens an in-place History selector, marks the active conversation, and supports starting a new conversation. A Manage view retains conversation title and delete actions.
- **Notes** opens an in-place Notes selector in selection mode. Selected note count/title information appears on the shortcut; confirmation returns selected notes to Ask. A Manage view retains note CRUD and import actions.
- The third shortcut displays the active note-context mode and cycles `Off → Focused → Automatic → Off`. Off ignores selected IDs; Focused uses selected notes only and has no context without a selection; Automatic searches user notes when relevant and restricts the search when IDs are selected. Requests omitting the mode retain automatic behavior for older clients.
- Conversation History initially renders expanded and has a toggle. User messages appear on the right; AI messages appear on the left.
- On desktop, Edit is revealed by hover or keyboard focus. On mobile it remains visible beneath the user message. The inline editor has a visible label; Escape or Cancel leaves the stored message unchanged. Save sends the edited message through `/ai/ask` with only earlier turns, then updates the existing `_history` note and replaces following turns. There is no dedicated edit API.
- Ask shortcuts use the shared bordered subtle-button treatment at a compact size. Conversation, Notes, and mode shortcuts retain visible hover/active/focus states and accessible labels; they are controls, not plain text labels.

### Notes and History actions

- Notes and History use the shared button hierarchy: primary for save/submit, subtle for navigation and selection tools, danger for delete, and fixed-size icon buttons for compact actions.
- History includes new conversation, selection, title save, and single/bulk delete actions. Notes includes add/import, selection, save, and single/bulk delete actions. Selection-mode cards support click and Enter/Space; action buttons expose names/labels where icons alone would be unclear.

---

## Layout and pages

| Layer | Structure |
|-------|-----------|
| **Unauthenticated** | Full viewport flex center (`.login-page`) → centered `.login-card` |
| **Authenticated** | `.app-fullpage`: header, compact Ask/Debug/Settings navigation, and one route-selected page in `<main>` |
| **Ask selectors** | `.ask-selector` panels render Notes or History workflows beneath Ask without navigating away or unmounting it |
| **Panels** | Repeated pattern: `.section`, `.card.app-panel`, `.form--compact`, `.app-panel__title` |
| **Grids** | `.form-row` — `grid-template-columns: 1fr 1fr` (available for forms; used where applicable in CSS) |
| **Notes / History lists** | `.notes-list-header` — flex wrap: search or title left, toolbar right; `.notes-list` — vertical flex list of `.note-card` |

**Route-based pages:** `/ask`, `/debug`, and `/settings` are authenticated pages. Notes/History list, detail, and add modes stay inside Ask-owned selectors/management panels.

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
| **Focus / keyboard** | `:focus-visible` + `box-shadow: var(--shadow-focus)` on buttons/inputs; selector cards support Enter/Space; Ask shortcut badges expose keyboard focus/tooltips; inline edit uses a labeled textarea and keyboard-operable buttons |
| **Interaction** | Shared button variants distinguish primary, secondary, subtle, destructive, icon, and pressed-toggle actions; `button:active` gives pressed feedback; link-style actions use `.link-button` |

---

## State and data handling

| Concern | Approach |
|---------|----------|
| **Global auth** | `App` holds `token`; syncs with `api.setToken` / `getToken`; 401 clears token and dispatches `ia:unauthorized` |
| **React context** | **Not used** |
| **Hooks** | Per-component `useState`, `useEffect`, `useRef`, `useCallback` |
| **API layer** | `api.js`: relative `BASE ""` (same origin or Vite proxy); `Authorization: Bearer`; `handleResponse` for 401/Errors |
| **Data flow** | Components call `api` directly; App owns route/auth transitions and passes `Login.onLogin` / `Header.onLogout`; Ask owns selector callbacks and conversation context |
| **Persistence** | `localStorage`: `ia_token`. AI Credit balances and ledgers are backend-owned JSON; no credit UI is currently implemented. |

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

- **Maintainability:** One global stylesheet; BEM-like prefixes (`.app-header__`, `.note-card__`, `.ask-selector__`); feature components colocated under `components/`.
- **Consistency:** Shared `.notes-*` toolbar/card/modal classes between Notes and History; Ask/Debug/Settings use same `.card` / `.form--compact` / `.out` language.
- **Predictability:** App routes use native history state; 401 always clears session via the same event.
- **Accessibility:** Labels, `aria-*` on several controls, dialog roles on confirms, visible focus rings.

### Reusable patterns

1. **CSS variable theme** — single `:root` contract for color, radius, shadow, transition.
2. **`api.js` pattern** — token helper, `handleResponse`, 401 → clear + event (decouples components from auth side effects).
3. **`.loading` on form** — disables interaction without ad hoc spinners everywhere.
4. **`.out` / `.out.err` / `.meta`** — consistent result and error blocks.
5. **List refresh on `visibilitychange` + interval** — simple staleness control without a data library.

---

## Notes for reuse

- Cross-reference: [ia.md](ia.md), [project.md](project.md).
- App uses `.nav-pills` for compact page navigation; keep browser history and direct-load behavior aligned with Flask SPA routes.
- If implementing real light mode, add `data-theme` (or class) on `document.documentElement` and mirror `:root` tokens; wire Settings `theme` to that toggle.
- New panels should follow: `section.section--*` → `card app-panel` → optional `form--compact` → `out` for feedback.
