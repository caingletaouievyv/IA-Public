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
├── vite.config.js          # Dev server :5174; proxy /ai, /auth, /notes, /memories, /activity, /files, /settings, /diagnostics, /admin → :5000
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
        ├── MemoryManager.jsx
        ├── DebugContext.jsx
        ├── Settings.jsx
        ├── AdminUsers.jsx
        └── AdminDiagnostics.jsx
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
| **App** | Public/auth route handling, auth gate, page navigation | — | Public `/`, `/privacy`, `/terms`, `/contact`; auth `/login`, `/register`; authenticated `/ask`, `/manage`, `/debug`, `/settings`, `/admin/users`, `/admin/diagnostics` (default `/ask`). After login, loads `GET /auth/me` into in-memory session `{ user_id, username, role }` (not persisted separately from the JWT). Uses `pathname`, `pushState`, and `popstate`; listens for `ia:unauthorized`; Ask opens Notes and History in selection mode. The authenticated shell mounts the contextual suggestion overlay; public and login routes do not. Page changes unmount Ask; the active history-note ID is restored from user-scoped `sessionStorage` on remount. Logout/account changes clear the old selection and invalidate the current-session Settings cache. Non–main-admin users who open `/admin/users`, or users without diagnostics access who open `/admin/diagnostics`, are redirected to `/ask` (backend still enforces 403). |
| **PublicSite** | Landing, Privacy, Terms, Contact | `path` | Path-based public shell with shared header/footer; no router or API dependency |
| **Header** | Brand + sign out | `onLogout?: fn`, `role` | Authenticated navigation shows Ask, Manage, and Settings for all signed-in users. **Users** (`/admin/users`) appears only for `main_admin`. **Diagnostics** (`/admin/diagnostics`) appears for `admin` and `main_admin`. `/debug` remains a directly addressable authenticated route. |
| **Login** | Sign in / register | `onLogin(token, userId)`, `initialIsRegister`, `onModeChange` | Local `username`, `password`, `loading`, `error`; when routed by App, the URL prop controls mode synchronously so Back/Forward does not flash the prior form; standalone use retains a local mode fallback. Validates non-empty. |
| **Ask** | `/ask`: question, conversation, Notes, and persistent Memory | `userId` | Owns transient draft, messages, active conversation, selected Notes, source preferences, and Memory setting. The active `_history` note ID and selected Notes IDs are stored in per-tab `sessionStorage`, keyed by authenticated user ID. Ask loads conversation title/messages and submits Notes IDs through the existing Notes API; note content is never copied into browser storage. Logout/account changes clear the prior selection. Missing history clears the conversation selection. Drafts remain in component state; Notes context modes, source visibility, and `show_context_source_labels` use per-user Settings. Ask initializes from cached Settings on first render; when settings are unknown or a save is pending, the toolbar remains hidden until values are ready. The label preference control is in Ask; Focus temporarily hides source labels and exiting Focus restores the saved preference. Conversation, Notes, and Memory are defaults, and Conversation cannot be hidden. Conversation opens History and has no mode button. Notes cycles Off → Selected → Automatic → Off and uses Notes only. Memory is ON/OFF via server-side `memory_enabled`; it controls independent retrieval and best-effort extraction. Its source button opens Manage → Memory. Files has no Ask context flow; GitHub, Drive, and Web remain placeholders. Conversation History has a separate Focus button. AI responses have per-message Copy buttons with accessible feedback. User turns persist in `_history` notes; history is not Memory storage. |
| **Manage** | `/manage`: organize saved Notes, Conversations, and Memory | `initialSection` | Notes and History reuse existing components. Memory loads actual backend records and setting; users can toggle Memory, edit/delete individual items, and clear all with confirmation. Loading, empty, error, and success feedback are surfaced. |
| **AISuggestion** | Authenticated bottom suggestion overlay | `userId`, `onAccept` | Non-blocking, dismissible card based on recent tracked action types. Accept opens Flashcards, prepares an Ask draft with automatic Notes context, or opens Manage with Notes selected. Dismissal IDs are stored per JWT subject in local storage. |
| **MemoryManager** | Manage's independent Memory CRUD | — | Uses the `api.js` Memory methods. Reports changes only after successful responses. |
| **Notes** | Saved-note management and Ask selection | `isSelectionMode`, `selectedIds`, `onSelect`, `onCloseSelection` | Manage uses the existing CRUD, search, bulk delete, image import, and PDF import (extract → review → save). Ask selection mode is limited to choosing saved notes; note creation and imports remain in Manage. `getNotesMeta` supplies suggestions; first **100** matches shown; `_history` hidden. |
| **History** | Saved-conversation management and Ask selection | `isSelectionMode`, `activeId`, `onSelect`, `onCloseSelection` | Manage uses the existing conversation list, title editing, and single/bulk delete. Ask uses selection mode to select or create a conversation; callbacks return its ID to Ask. |
| **Memory** | Persistent user-specific memories | — | Independent per-user records with authenticated list/update/delete/clear operations; Ask setting controls automatic extraction and retrieval. |
| **DebugContext** | Authenticated `/debug`: inspect retrieval context | — | The page remains available by direct path to signed-in users but is omitted from normal navigation. The debug API also requires authentication; results show retrieval context for the current user's notes. |
| **Settings** | `/settings`; GET/PUT `/settings/` | — | Per-user `theme` and `default_model` preferences, Ask labels/context visibility, and the **AI Suggestions** toggle (`ai_suggestions_enabled`, default ON). Changes save through the existing settings API and update the current-session user-scoped cache; Conversation remains checked and disabled. |
| **AdminUsers** | `/admin/users`; GET/POST admin APIs | — | Main Admin only. Lists `{ user_id, username, role }`, promotes `user` → `admin` and demotes `admin` → `user` with confirmation modals, loading/empty/error/success states, and in-list role updates after success. No actions for `main_admin` accounts. |
| **AdminDiagnostics** | `/admin/diagnostics`; GET `/diagnostics/events` | — | Admin and Main Admin. Shows newest content-free event metadata (`limit` query only; no client-side filter masquerading as server filters). Refresh reloads from the API. Never displays prompts, answers, tokens, or raw exception text. |

**Internal helpers (not exported UI):** `App` owns route and auth transitions; `Notes` / `History` share confirm modal classes `.notes-delete-confirm*`.

### Route navigation

- App navigation uses native links with centralized `pushState` handling; `popstate` keeps Back/Forward synchronized with React.
- Authenticated navigation order is Ask, Manage, Settings, optional Users and Diagnostics (role-gated), Sign out. `/debug` remains available to authenticated users by direct path.
- Direct loads and refreshes are served by Flask SPA routes for public, auth, and authenticated frontend paths.
- `/manage` reuses the existing Notes and History components for CRUD; Ask keeps their selector workflows.
- The active page is identified by `aria-current="page"` and a subtle accent surface.
- A fixed suggestion card appears at the bottom only after enough recent tracked activity; the surrounding layer does not intercept page input, and the card has explicit accept and dismiss controls.

### Ask context controls and conversation behavior

- Conversation is a source-only button that opens the in-place History selector, marks the active conversation, and supports starting a new conversation. Manage is the main destination for conversation title and delete actions. The active ID survives Ask unmount/remount through user-scoped session storage; messages/title are reloaded from the latest `_history` note, not copied into browser storage. Starting a new conversation replaces the saved ID; clearing the active selection removes it. Existing active-conversation turns continue to be sent as before.
- The Ask header offers Conversation, Notes, Files, GitHub, Memory, Drive, and Web. Conversation, Notes, and Memory are visible by default. Settings → Ask Context Sources controls visibility for all seven; Conversation is always visible. Source visibility and Notes modes are stored in the authenticated user's existing settings. Missing or invalid visibility preferences use the defaults. Hiding a source removes its controls without resetting data or Memory's persistent setting. Conversation has no mode. Notes and placeholder sources retain independent Off/Selected/Automatic controls; Memory is a persistent ON/OFF toggle.
- **Notes** opens the in-place Notes selector in selection mode. Confirmation returns selected notes to Ask. Selected Note IDs are stored per tab and authenticated user so they survive navigation that unmounts Ask; their content stays in the existing Notes store and is retrieved only through the authenticated API. Logout/account changes clear prior selected IDs. The selector is selection-only; note creation and image import are available in Manage. Notes mode defaults to Off; Selected uses only selected notes (sent through the existing API `focused` mode), and Automatic uses the existing Notes retrieval behavior. Notes IDs never select or provide Memory records.
- **Memory** is independent of Notes and conversation history. Its Ask control reflects and updates persisted `memory_enabled` (default Off); when enabled it permits automatic extraction and relevant retrieval. Its source button opens Manage → Memory. Manage shows actual per-user backend records and setting, supports individual edit/delete, and requires confirmation before clear-all. Relevant saved records are added in a distinct bounded prompt section marked as untrusted background data. The backend `/files` route lists a file tree, but Ask has no file-selection or file-context flow. Files, GitHub, Drive, and Web remain placeholders.
- Source details appear on hover and keyboard focus on desktop. On touch, press and hold a source button to show details; a normal tap opens its implemented selector or shows the unavailable-source details. Mode buttons do not show source details.
- Context-source labels follow the saved **Show Ask labels** preference at every viewport size. It is controlled under Settings → Ask and saved through the existing per-user Settings API. Ask renders from already-loaded Settings when possible; otherwise it withholds the toolbar until the preference is known, including while a save is pending, so defaults do not flash during navigation. Labels hidden visually remain available to assistive technology through each source button's accessible name. Focus behavior is unchanged and is independent of this setting.
- Conversation History initially renders expanded. Its heading is non-clickable; a separate Focus button with the Conversation icon enters focus mode. This work-only layout hides the app header and Ask shortcuts from both the layout and keyboard order, gives history the available vertical space, and keeps the question textarea and Ask button available. Activating Focus again restores the normal layout. The button uses `aria-pressed` for focus state; it does not use `aria-expanded` because it does not expand or collapse history. The heading remains left-aligned while Focus and previous/next controls align right. The history area scrolls independently and avoids horizontal overflow on desktop and mobile. The visible Question label stays hidden in focus mode while the textarea remains labeled accessibly. AI messages are left-aligned and each has an icon-only Copy button next to its response; it copies that response's plain text, preserving line breaks and list structure while removing common Markdown markers. Copy success or clipboard failure is announced accessibly without changing the button label. Each AI response also offers a compact icon-only **Report answer** action beside Copy; it opens the shared `AskOverlay` dialog with four allow-listed reasons and submits metadata linked to that Ask `operation_id` without attaching conversation text. Loading, success, and error states appear inside the dialog. User messages are right-aligned bubbles with a compact three-line preview. Activating a user bubble opens the complete message in the shared `AskOverlay` shell used by the Notes and History selectors. Its backdrop and close button dismiss it, focus is trapped/restored, and × closes it. Edit switches the same overlay into edit mode with the existing labeled textarea; the textarea receives focus, Cancel returns to detail, Escape returns to detail while editing and closes from detail, and Save keeps the overlay open on the updated detail.
- Compact previous/next controls navigate only between User-message elements, smoothly scroll to and focus the target, and show a subtle active indication. AI messages are skipped. Previous is disabled at the first User message and next at the last.
- The inline editor has a visible label; Escape or Cancel leaves the stored message unchanged. Save sends the edited message through `/ai/ask` with only earlier turns, then updates the existing `_history` note and replaces following turns. There is no dedicated edit API. The history area retains its current height and uses a thin, dark-theme scrollbar without horizontal scrolling.
- Ask context controls use compact segmented dark-surface groups, with a clear divider between each source and its mode. A blue outline marks an active conversation or enabled Notes/Memory context; inactive modes stay muted. Conversation remains source-only. Source and mode buttons remain individually focusable with visible hover and focus indicators. The header stays on one row on desktop and wraps on narrow screens; source details use a small dark surface without changing layout.

### Notes and History actions

- Notes and History use the shared button hierarchy: primary for save/submit, subtle for navigation and selection tools, danger for delete, and fixed-size icon buttons for compact actions.
- History includes new conversation, selection, title save, and single/bulk delete actions. Notes includes add/import, selection, save, and single/bulk delete actions. Selection-mode cards support click and Enter/Space; action buttons expose names/labels where icons alone would be unclear.

---

## Layout and pages

| Layer | Structure |
|-------|-----------|
| **Unauthenticated** | Full viewport flex center (`.login-page`) → centered `.login-card` |
| **Authenticated** | `.app-fullpage`: header, compact Ask/Manage/Settings navigation, and one route-selected page in `<main>` |
| **Ask selectors** | `.ask-selector` panels render Notes or History workflows beneath Ask without navigating away or unmounting it |
| **Panels** | Repeated pattern: `.section`, `.card.app-panel`, `.form--compact`, `.app-panel__title` |
| **Grids** | `.form-row` — `grid-template-columns: 1fr 1fr` (available for forms; used where applicable in CSS) |
| **Notes / History lists** | `.notes-list-header` — flex wrap: search or title left, toolbar right; `.notes-list` — vertical flex list of `.note-card` |

**Route-based pages:** `/ask`, `/manage`, `/debug`, `/settings`, `/admin/users`, and `/admin/diagnostics` are authenticated pages. Manage reuses Notes and History for saved-content CRUD; Ask's Notes/History workflows remain selectors. Admin pages are UI-gated by role from `/auth/me`; API authorization remains on the server.

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
