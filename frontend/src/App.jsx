// IA/frontend/src/App.jsx
// Public routes, auth gate, and lightweight authenticated page navigation.

import { useCallback, useEffect, useState } from "react";
import { getToken, setToken } from "./api";
import Login from "./components/Login";
import Ask from "./components/Ask";
import AskOverlay from "./components/AskOverlay";
import DebugContext from "./components/DebugContext";
import History from "./components/History";
import Notes from "./components/Notes";
import Settings from "./components/Settings";
import PublicSite from "./components/PublicSite";

const UNAUTH_EVENT = "ia:unauthorized";
const PUBLIC_PATHS = new Set(["/", "/privacy", "/terms", "/contact"]);
const AUTH_PATHS = new Set(["/login", "/register"]);
const APP_PATHS = new Set(["/ask", "/debug", "/settings"]);

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

  const navigate = (nextPath, replace = false) => {
    if (window.location.pathname !== nextPath) {
      if (replace) window.history.replaceState(null, "", nextPath);
      else window.history.pushState(null, "", nextPath);
    }
    setPath(nextPath);
  };

  const setAuthToken = (nextToken) => {
    setTokenState(nextToken);
    setToken(nextToken);
    navigate(nextToken ? "/ask" : "/login", true);
  };

  const openHistoryOverlay = useCallback((onSelect, activeId) => {
    setAskOverlay({ type: "history", onSelect, activeId, manage: false });
  }, []);
  const openNotesOverlay = useCallback((onSelect, selectedIds) => {
    setAskOverlay({ type: "notes", onSelect, selectedIds: [...selectedIds], manage: false });
  }, []);
  const toggleAskOverlayMode = useCallback(() => {
    setAskOverlay((current) => current && { ...current, manage: !current.manage });
  }, []);
  const closeAskOverlay = useCallback(() => setAskOverlay(null), []);

  useEffect(() => {
    const onPopState = () => setPath(currentPath());
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
    <div className="app-fullpage">
      <Header
        onLogout={() => setAuthToken(null)}
        activePath={activePath}
        onNavigate={handleNavigation}
      />
      <main className="app-main">
        {activePath === "/ask" ? (
          <Ask onHistoryPicker={openHistoryOverlay} onNotesPicker={openNotesOverlay} />
        ) : activePath === "/debug" ? <DebugContext /> : <Settings />}
      </main>
      {activePath === "/ask" && askOverlay && (
        <AskOverlay
          title={askOverlay.type === "history" ? "Conversations" : "Notes"}
          onClose={closeAskOverlay}
          isManaging={askOverlay.manage}
          onManage={toggleAskOverlayMode}
        >
          {askOverlay.type === "history" ? (
            <History
              isSelectionMode={!askOverlay.manage}
              activeId={askOverlay.activeId}
              onSelect={askOverlay.manage ? null : askOverlay.onSelect}
              onCloseSelection={closeAskOverlay}
            />
          ) : (
            <Notes
              isSelectionMode={!askOverlay.manage}
              selectedIds={askOverlay.manage ? [] : askOverlay.selectedIds}
              onSelect={askOverlay.manage ? null : askOverlay.onSelect}
              onCloseSelection={closeAskOverlay}
            />
          )}
        </AskOverlay>
      )}
    </div>
  );
}
