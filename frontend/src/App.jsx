// IA/frontend/src/App.jsx
// Public routes, auth gate, and lightweight authenticated page navigation.

import { useCallback, useEffect, useState } from "react";
import { getAuthMe, getToken, getTokenUserId, setToken } from "./api";
import {
  canShowDiagnosticsNav,
  canShowUserManagementNav,
} from "./authRoles";
import AdminDiagnostics from "./components/AdminDiagnostics";
import AdminUsers from "./components/AdminUsers";
import { clearActiveConversation, clearSelectedNoteIds } from "./activeConversation";
import Login from "./components/Login";
import Ask from "./components/Ask";
import AskOverlay from "./components/AskOverlay";
import AISuggestion from "./components/AISuggestion";
import DebugContext from "./components/DebugContext";
import History from "./components/History";
import Manage from "./components/Manage";
import Notes from "./components/Notes";
import Settings from "./components/Settings";
import PublicSite from "./components/PublicSite";

const UNAUTH_EVENT = "ia:unauthorized";
const PUBLIC_PATHS = new Set(["/", "/privacy", "/terms", "/contact"]);
const AUTH_PATHS = new Set(["/login", "/register"]);
const APP_PATHS = new Set([
  "/ask",
  "/manage",
  "/debug",
  "/settings",
  "/admin/users",
  "/admin/diagnostics",
]);

function currentPath() {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

function Header({ onLogout, activePath, onNavigate, role }) {
  const navItems = [
    ["/ask", "Ask"],
    ["/manage", "Manage"],
    ["/settings", "Settings"],
  ];
  if (canShowUserManagementNav(role)) {
    navItems.push(["/admin/users", "Users"]);
  }
  if (canShowDiagnosticsNav(role)) {
    navItems.push(["/admin/diagnostics", "Diagnostics"]);
  }

  return (
    <header className="app-header app-header--main">
      <div className="app-header__brand">
        <h1 className="app-header__title">IA</h1>
        <p className="app-header__tagline">Notes &amp; memory — ask with context</p>
      </div>
      <div className="app-header__actions">
        <nav className="app-navigation" aria-label="Application navigation">
          {navItems.map(([href, label]) => (
            <a
              key={href}
              href={href}
              className={`app-navigation__link button-subtle${activePath === href ? " active" : ""}`}
              aria-current={activePath === href ? "page" : undefined}
              onClick={(event) => onNavigate(event, href)}
            >
              {label}
            </a>
          ))}
        </nav>
        <button type="button" className="app-header__logout button-subtle link-button" onClick={onLogout}>
          Sign out
        </button>
      </div>
    </header>
  );
}

export default function App() {
  const [token, setTokenState] = useState(() => getToken());
  const [userId, setUserId] = useState(() => getTokenUserId());
  const [path, setPath] = useState(currentPath);
  const [askOverlay, setAskOverlay] = useState(null);
  const [askHistoryFocused, setAskHistoryFocused] = useState(false);
  const [manageInitialSection, setManageInitialSection] = useState("notes");
  const [managePageKey, setManagePageKey] = useState(0);
  const [manageFocusNoteId, setManageFocusNoteId] = useState(() => {
    if (currentPath() !== "/manage") return null;
    const params = new URLSearchParams(window.location.search);
    const noteId = (params.get("note") || "").trim();
    return noteId || null;
  });
  const [suggestionAction, setSuggestionAction] = useState(null);
  const [session, setSession] = useState(null);
  const [sessionLoading, setSessionLoading] = useState(() => Boolean(getToken()));

  const navigate = (nextPath, replace = false) => {
    if (window.location.pathname !== nextPath) {
      if (replace) window.history.replaceState(null, "", nextPath);
      else window.history.pushState(null, "", nextPath);
    }
    setAskHistoryFocused(false);
    setPath(nextPath);
  };

  const setAuthToken = (nextToken, nextUserId = getTokenUserId(nextToken)) => {
    if (!nextToken || (userId && nextUserId && userId !== nextUserId)) {
      clearActiveConversation(userId);
      clearSelectedNoteIds(userId);
    }
    setTokenState(nextToken);
    setUserId(nextToken ? nextUserId : null);
    setToken(nextToken);
    if (!nextToken) {
      setSession(null);
      setSessionLoading(false);
      setSuggestionAction(null);
    } else {
      setSessionLoading(true);
    }
    navigate(nextToken ? "/ask" : "/login", true);
  };

  const openHistoryOverlay = useCallback((onSelect, activeId) => {
    setAskOverlay({ type: "history", onSelect, activeId });
  }, []);
  const openNotesOverlay = useCallback((onSelect, selectedIds) => {
    setAskOverlay({ type: "notes", onSelect, selectedIds: [...selectedIds] });
  }, []);
  const openMemoryManager = () => {
    setManageInitialSection("memory");
    navigate("/manage");
  };
  const openCreatedNote = useCallback((noteId) => {
    const id = (noteId || "").trim();
    if (!id) return;
    setManageFocusNoteId(id);
    setManageInitialSection("notes");
    const nextPath = `/manage?note=${encodeURIComponent(id)}`;
    if (window.location.pathname + window.location.search !== nextPath) {
      window.history.pushState(null, "", nextPath);
    }
    setAskHistoryFocused(false);
    setPath("/manage");
  }, []);
  const clearManageNoteFocus = useCallback(() => {
    setManageFocusNoteId(null);
    if (window.location.pathname === "/manage" && window.location.search) {
      window.history.replaceState(null, "", "/manage");
    }
  }, []);
  const openUserMessageOverlay = useCallback((content, onSave) => {
    setAskOverlay({
      type: "userMessage",
      mode: "detail",
      content,
      draft: content,
      onSave,
    });
  }, []);
  const closeAskOverlay = useCallback(() => setAskOverlay(null), []);
  const consumeSuggestionAction = useCallback(() => setSuggestionAction(null), []);
  const acceptSuggestion = (action) => {
    if (action === "review_activity") {
      setManageInitialSection("notes");
      setManagePageKey((key) => key + 1);
      navigate("/manage");
      return;
    }
    if (action === "prepare_ask" || action === "open_flashcards") {
      setSuggestionAction({ action, requestId: Date.now() });
      navigate("/ask");
    }
  };
  const handleOverlayEscape = useCallback(() => {
    if (askOverlay?.type !== "userMessage" || askOverlay.mode !== "edit") return false;
    if (askOverlay.saving) return true;
    setAskOverlay((current) => current && {
      ...current,
      mode: "detail",
      draft: current.content,
      error: null,
    });
    return true;
  }, [askOverlay]);
  const saveUserMessageEdit = async () => {
    if (askOverlay?.type !== "userMessage" || askOverlay.saving) return;
    const activeOverlay = askOverlay;
    setAskOverlay((current) => current && { ...current, saving: true, error: null });
    let result;
    try {
      result = await activeOverlay.onSave(activeOverlay.draft);
    } catch (error) {
      result = { success: false, error: error.message || "Failed to save message." };
    }
    setAskOverlay((current) => {
      if (!current || current.type !== "userMessage") return current;
      if (!result.success) return { ...current, saving: false, error: result.error };
      return {
        ...current,
        mode: "detail",
        content: result.content,
        draft: result.content,
        saving: false,
        error: null,
      };
    });
  };

  useEffect(() => {
    const onPopState = () => {
      setAskHistoryFocused(false);
      setPath(currentPath());
      if (currentPath() === "/manage") {
        const params = new URLSearchParams(window.location.search);
        const noteId = (params.get("note") || "").trim();
        setManageFocusNoteId(noteId || null);
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (path !== "/manage") return;
    const params = new URLSearchParams(window.location.search);
    const noteId = (params.get("note") || "").trim();
    if (noteId) setManageFocusNoteId(noteId);
  }, [path]);

  useEffect(() => {
    const onUnauth = () => setAuthToken(null);
    window.addEventListener(UNAUTH_EVENT, onUnauth);
    return () => window.removeEventListener(UNAUTH_EVENT, onUnauth);
  }, [userId]);

  useEffect(() => {
    if (!token) {
      setSession(null);
      setSessionLoading(false);
      return undefined;
    }
    let cancelled = false;
    setSessionLoading(true);
    getAuthMe()
      .then((data) => {
        if (!cancelled) {
          setSession({
            user_id: data.user_id,
            username: data.username,
            role: data.role,
          });
        }
      })
      .catch(() => {
        if (!cancelled) setSession(null);
      })
      .finally(() => {
        if (!cancelled) setSessionLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, userId]);

  useEffect(() => {
    if (!token || sessionLoading) return;
    if (path === "/admin/users" && !canShowUserManagementNav(session?.role)) {
      navigate("/ask", true);
    } else if (path === "/admin/diagnostics" && !canShowDiagnosticsNav(session?.role)) {
      navigate("/ask", true);
    }
  }, [path, token, sessionLoading, session?.role]);

  useEffect(() => {
    if (path === "/app") {
      navigate(token ? "/ask" : "/login", true);
    } else if (!token && APP_PATHS.has(path)) {
      navigate("/login", true);
    } else if (token && AUTH_PATHS.has(path)) {
      navigate("/ask", true);
    } else if (!PUBLIC_PATHS.has(path) && !AUTH_PATHS.has(path) && !APP_PATHS.has(path)) {
      navigate(token ? "/ask" : "/login", true);
    }
  }, [path, token]);

  useEffect(() => {
    if (!token || path !== "/ask") setAskOverlay(null);
  }, [path, token]);

  if (PUBLIC_PATHS.has(path)) {
    return <PublicSite path={path} />;
  }

  if (!token) {
    return (
      <Login
        initialIsRegister={path === "/register"}
        onModeChange={(isRegister) => navigate(isRegister ? "/register" : "/login")}
        onLogin={setAuthToken}
      />
    );
  }

  const activePath = APP_PATHS.has(path) ? path : "/ask";
  const adminPathPendingRole = sessionLoading && (activePath === "/admin/users" || activePath === "/admin/diagnostics");
  const handleNavigation = (event, nextPath) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (nextPath === "/manage") setManageInitialSection("notes");
    navigate(nextPath);
  };

  return (
    <div className={`app-fullpage${askHistoryFocused && activePath === "/ask" ? " app-fullpage--ask-history-focused" : ""}`}>
      <Header
        onLogout={() => setAuthToken(null)}
        activePath={activePath}
        onNavigate={handleNavigation}
        role={session?.role}
      />
      <main className="app-main">
        {activePath === "/ask" ? (
          <Ask
            key={userId}
            userId={userId}
            onHistoryPicker={openHistoryOverlay}
            onNotesPicker={openNotesOverlay}
            onMemoryManage={openMemoryManager}
            onUserMessageDetail={openUserMessageOverlay}
            onHistoryFocusChange={setAskHistoryFocused}
            suggestionAction={suggestionAction}
            onSuggestionActionConsumed={consumeSuggestionAction}
            onOpenCreatedNote={openCreatedNote}
          />
        ) : activePath === "/manage" ? (
          <Manage
            key={managePageKey}
            initialSection={manageInitialSection}
            focusNoteId={manageFocusNoteId}
            onFocusNoteHandled={clearManageNoteFocus}
          />
        ) : activePath === "/debug" ? (
          <DebugContext />
        ) : adminPathPendingRole ? (
          <p role="status">Loading session…</p>
        ) : activePath === "/admin/users" ? (
          <AdminUsers />
        ) : activePath === "/admin/diagnostics" ? (
          <AdminDiagnostics />
        ) : (
          <Settings />
        )}
      </main>
      <AISuggestion key={userId} userId={userId} onAccept={acceptSuggestion} />
      {activePath === "/ask" && askOverlay && (
        <AskOverlay
          title={
            askOverlay.type === "history"
              ? "Conversations"
              : askOverlay.type === "notes"
                ? "Notes"
                : askOverlay.mode === "edit"
                  ? "Edit Message"
                  : "User Message"
          }
          onClose={closeAskOverlay}
          onEscape={handleOverlayEscape}
          showManage={false}
          closeText={askOverlay.type === "userMessage" ? "×" : "Close"}
        >
          {askOverlay.type === "history" ? (
            <History
              isSelectionMode
              activeId={askOverlay.activeId}
              onSelect={askOverlay.onSelect}
              onCloseSelection={closeAskOverlay}
            />
          ) : askOverlay.type === "notes" ? (
            <Notes
              isSelectionMode
              selectedIds={askOverlay.selectedIds}
              onSelect={askOverlay.onSelect}
              onCloseSelection={closeAskOverlay}
            />
          ) : askOverlay.mode === "edit" ? (
            <div className="ask-user-message-editor ask-user-message-editor--overlay">
              <label htmlFor="ask-user-message-edit-input">Edit your message</label>
              <textarea
                id="ask-user-message-edit-input"
                value={askOverlay.draft}
                onChange={(event) => setAskOverlay((current) => current && ({
                  ...current,
                  draft: event.target.value,
                  error: null,
                }))}
                autoFocus
                disabled={askOverlay.saving}
              />
              {askOverlay.error && <div className="out err" role="alert">{askOverlay.error}</div>}
              <div className="ask-user-message-actions">
                <button
                  type="button"
                  className="button-subtle"
                  onClick={() => setAskOverlay((current) => current && ({
                    ...current,
                    mode: "detail",
                    draft: current.content,
                    error: null,
                  }))}
                  disabled={askOverlay.saving}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="button-primary"
                  onClick={saveUserMessageEdit}
                  disabled={askOverlay.saving || !askOverlay.draft.trim()}
                >
                  {askOverlay.saving ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          ) : (
            <div className="ask-user-message-detail">
              <p className="ask-user-message-detail__text">{askOverlay.content}</p>
              <button
                type="button"
                className="button-subtle ask-user-message-detail__edit"
                onClick={() => setAskOverlay((current) => current && ({
                  ...current,
                  mode: "edit",
                  draft: current.content,
                  error: null,
                }))}
                autoFocus
              >
                Edit
              </button>
            </div>
          )}
        </AskOverlay>
      )}
    </div>
  );
}
