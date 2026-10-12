// IA/frontend/src/App.jsx
// Public routes, auth gate, and lightweight authenticated page navigation.

import { useCallback, useEffect, useState } from "react";
import { getToken, setToken } from "./api";
import Login from "./components/Login";
import Ask from "./components/Ask";
import AskOverlay from "./components/AskOverlay";
import DebugContext from "./components/DebugContext";
import History from "./components/History";
import Manage from "./components/Manage";
import Notes from "./components/Notes";
import Settings from "./components/Settings";
import PublicSite from "./components/PublicSite";

const UNAUTH_EVENT = "ia:unauthorized";
const PUBLIC_PATHS = new Set(["/", "/privacy", "/terms", "/contact"]);
const AUTH_PATHS = new Set(["/login", "/register"]);
const APP_PATHS = new Set(["/ask", "/manage", "/debug", "/settings"]);

function currentPath() {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

function Header({ onLogout, activePath, onNavigate }) {
  return (
    <header className="app-header app-header--main">
      <div className="app-header__brand">
        <h1 className="app-header__title">IA</h1>
        <p className="app-header__tagline">Notes &amp; memory — ask with context</p>
      </div>
      <div className="app-header__actions">
        <nav className="app-navigation" aria-label="Application navigation">
          {[
            ["/ask", "Ask"],
            ["/manage", "Manage"],
            ["/debug", "Debug"],
            ["/settings", "Settings"],
          ].map(([href, label]) => (
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
  const [path, setPath] = useState(currentPath);
  const [askOverlay, setAskOverlay] = useState(null);
  const [askHistoryFocused, setAskHistoryFocused] = useState(false);

  const navigate = (nextPath, replace = false) => {
    if (window.location.pathname !== nextPath) {
      if (replace) window.history.replaceState(null, "", nextPath);
      else window.history.pushState(null, "", nextPath);
    }
    setAskHistoryFocused(false);
    setPath(nextPath);
  };

  const setAuthToken = (nextToken) => {
    setTokenState(nextToken);
    setToken(nextToken);
    navigate(nextToken ? "/ask" : "/login", true);
  };

  const openHistoryOverlay = useCallback((onSelect, activeId) => {
    setAskOverlay({ type: "history", onSelect, activeId });
  }, []);
  const openNotesOverlay = useCallback((onSelect, selectedIds) => {
    setAskOverlay({ type: "notes", onSelect, selectedIds: [...selectedIds] });
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
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const onUnauth = () => setAuthToken(null);
    window.addEventListener(UNAUTH_EVENT, onUnauth);
    return () => window.removeEventListener(UNAUTH_EVENT, onUnauth);
  }, []);

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
  const handleNavigation = (event, nextPath) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(nextPath);
  };

  return (
    <div className={`app-fullpage${askHistoryFocused && activePath === "/ask" ? " app-fullpage--ask-history-focused" : ""}`}>
      <Header
        onLogout={() => setAuthToken(null)}
        activePath={activePath}
        onNavigate={handleNavigation}
      />
      <main className="app-main">
        {activePath === "/ask" ? (
          <Ask
            onHistoryPicker={openHistoryOverlay}
            onNotesPicker={openNotesOverlay}
            onUserMessageDetail={openUserMessageOverlay}
            onHistoryFocusChange={setAskHistoryFocused}
          />
        ) : activePath === "/manage" ? (
          <Manage />
        ) : activePath === "/debug" ? (
          <DebugContext />
        ) : (
          <Settings />
        )}
      </main>
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
