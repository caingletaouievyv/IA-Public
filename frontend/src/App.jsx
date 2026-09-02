// IA/frontend/src/App.jsx
// Root: login when no token; else header + Ask · Notes · Debug · Settings (JWT auth, no API secret in UI).

import { useState, useEffect, useRef } from "react";
import { getToken, setToken } from "./api";
import Login from "./components/Login";
import FloatingWindow from "./components/FloatingWindow";
import Ask from "./components/Ask";
import Notes from "./components/Notes";
import History from "./components/History";
import DebugContext from "./components/DebugContext";
import Settings from "./components/Settings";

const FLOAT_OFFSET = 32;
const UNAUTH_EVENT = "ia:unauthorized";

function newFloatId() {
  return crypto.randomUUID ? crypto.randomUUID() : `float-${Date.now()}`;
}

function Header({ onLogout }) {
  return (
    <header className="app-header app-header--main">
      <div className="app-header__brand">
        <h1 className="app-header__title">IA</h1>
        <p className="app-header__tagline">Notes &amp; memory — ask with context</p>
      </div>
      {onLogout && (
        <div className="app-header__actions">
          <button type="button" className="app-header__logout link-button" onClick={onLogout}>
            Sign out
          </button>
        </div>
      )}
    </header>
  );
}

export default function App() {
  const [token, setTokenState] = useState(() => getToken());
  const [floatingWindows, setFloatingWindows] = useState([]);
  const [frontWindowId, setFrontWindowId] = useState(null);
  const [collapsedWindowIds, setCollapsedWindowIds] = useState(() => new Set());
  const [historySelectionCallback, setHistorySelectionCallback] = useState(null);
  const [historySelectionWindowId, setHistorySelectionWindowId] = useState(null);
  const nextOffsetRef = useRef(0);

  const setAuthToken = (t) => {
    setTokenState(t);
    setToken(t);
  };

  useEffect(() => {
    const onUnauth = () => setTokenState(null);
    window.addEventListener(UNAUTH_EVENT, onUnauth);
    return () => window.removeEventListener(UNAUTH_EVENT, onUnauth);
  }, []);

  if (!token) {
    return <Login onLogin={setAuthToken} />;
  }

  const openFloating = (type) => {
    const offset = nextOffsetRef.current;
    nextOffsetRef.current += FLOAT_OFFSET;
    const id = newFloatId();
    setFloatingWindows((wins) => [...wins, { id, type, initialPosition: { x: 40 + offset, y: 40 + offset } }]);
    setFrontWindowId(id);
  };

  const closeFloating = (id) => {
    setFloatingWindows((wins) => wins.filter((w) => w.id !== id));
    setFrontWindowId((front) => (front === id ? null : front));
    if (id === historySelectionWindowId) {
      setHistorySelectionCallback(null);
      setHistorySelectionWindowId(null);
    }
    setCollapsedWindowIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const openHistoryForSelection = (callback) => {
    const offset = nextOffsetRef.current;
    nextOffsetRef.current += FLOAT_OFFSET;
    const id = newFloatId();
    setHistorySelectionCallback(() => callback);
    setHistorySelectionWindowId(id);
    setFloatingWindows((wins) => [...wins, { id, type: "history", initialPosition: { x: 40 + offset, y: 40 + offset } }]);
    setFrontWindowId(id);
  };

  const closeHistorySelection = () => {
    if (historySelectionWindowId) closeFloating(historySelectionWindowId);
    setHistorySelectionCallback(null);
    setHistorySelectionWindowId(null);
  };

  const floatingTitle = (type) => ({ ask: "Ask", notes: "Notes", history: "History", debug: "Debug", settings: "Settings" }[type] || type);
  const floatingContent = (type) => {
    if (type === "ask") return <Ask onHistoryPicker={openHistoryForSelection} />;
    if (type === "notes") return <Notes />;
    if (type === "history") {
      if (historySelectionCallback !== null) {
        return <History isSelectionMode={true} onSelect={historySelectionCallback} onCloseSelection={closeHistorySelection} />;
      }
      return <History />;
    }
    if (type === "debug") return <DebugContext />;
    if (type === "settings") return <Settings />;
    return null;
  };

  return (
    <div className="app-fullpage">
      <Header onLogout={() => setAuthToken(null)} />
      <p className="float-triggers">
        <button type="button" className="link-button" onClick={() => openFloating("ask")}>
          Ask
        </button>
        <span className="float-triggers-sep"> · </span>
        <button type="button" className="link-button" onClick={() => openFloating("notes")}>
          Notes
        </button>
        <span className="float-triggers-sep"> · </span>
        <button type="button" className="link-button" onClick={() => openFloating("history")}>
          History
        </button>
        <span className="float-triggers-sep"> · </span>
        <button type="button" className="link-button" onClick={() => openFloating("debug")}>
          Debug
        </button>
        <span className="float-triggers-sep"> · </span>
        <button type="button" className="link-button" onClick={() => openFloating("settings")}>
          Settings
        </button>
      </p>
      {floatingWindows.map(({ id, type, initialPosition }, index) => {
        const collapsedOrder = floatingWindows.filter((w) => collapsedWindowIds.has(w.id));
        const collapsedStackIndex = collapsedOrder.findIndex((w) => w.id === id);
        return (
          <FloatingWindow
            key={id}
            id={id}
            title={floatingTitle(type)}
            initialPosition={initialPosition}
            stackIndex={index}
            collapsedStackIndex={collapsedStackIndex >= 0 ? collapsedStackIndex : 0}
            onCollapsedChange={(windowId, isCollapsed) => {
              setCollapsedWindowIds((prev) => {
                const next = new Set(prev);
                if (isCollapsed) next.add(windowId);
                else next.delete(windowId);
                return next;
              });
            }}
            onClose={() => {
              if (id === historySelectionWindowId) closeHistorySelection();
              else closeFloating(id);
            }}
            onBringToFront={() => setFrontWindowId(id)}
            isFront={frontWindowId === id}
          >
            {floatingContent(type)}
          </FloatingWindow>
        );
      })}
    </div>
  );
}
