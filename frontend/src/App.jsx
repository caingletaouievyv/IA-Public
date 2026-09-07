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
const FLOAT_MIN_WIDTH = 280;
const FLOAT_MIN_HEIGHT = 200;

function newFloatId() {
  return crypto.randomUUID ? crypto.randomUUID() : `float-${Date.now()}`;
}

function centeredInitialPosition() {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const isDesktop = viewportWidth >= 768;
  const width = isDesktop ? Math.min(640, Math.max(FLOAT_MIN_WIDTH, viewportWidth - 40)) : FLOAT_MIN_WIDTH;
  const height = isDesktop
    ? Math.min(520, Math.max(FLOAT_MIN_HEIGHT, viewportHeight - 48))
    : Math.min(420, Math.max(FLOAT_MIN_HEIGHT, viewportHeight - 48));
  return {
    x: Math.max(0, (viewportWidth - width) / 2),
    y: Math.max(0, (viewportHeight - height) / 2),
  };
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
    setCollapsedWindowIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const openHistoryForSelection = (parentAskId, callback) => {
    const id = newFloatId();
    setFloatingWindows((wins) => {
      const existing = wins.find((window) => window.type === "history" && window.selectionMode && window.parentAskId === parentAskId);
      if (existing) {
        setFrontWindowId(existing.id);
        return wins;
      }
      setFrontWindowId(id);
      return [...wins, {
        id,
        type: "history",
        selectionMode: true,
        parentAskId,
        selectionCallback: callback,
        initialPosition: centeredInitialPosition(),
      }];
    });
  };

  const openNotesForSelection = (parentAskId, callback) => {
    const id = newFloatId();
    setFloatingWindows((wins) => {
      const existing = wins.find((window) => window.type === "notes" && window.selectionMode && window.parentAskId === parentAskId);
      if (existing) {
        setFrontWindowId(existing.id);
        return wins;
      }
      setFrontWindowId(id);
      return [...wins, {
        id,
        type: "notes",
        selectionMode: true,
        parentAskId,
        selectionCallback: callback,
        initialPosition: centeredInitialPosition(),
      }];
    });
  };

  const floatingTitle = (type) => ({ ask: "Ask", notes: "Notes", history: "History", debug: "Debug", settings: "Settings" }[type] || type);
  const floatingContent = ({ id, type, selectionMode = false, selectionCallback = null }) => {
    if (type === "ask") {
      return (
        <Ask
          onHistoryPicker={(callback) => openHistoryForSelection(id, callback)}
          onNotesPicker={(callback) => openNotesForSelection(id, callback)}
        />
      );
    }
    if (type === "notes") {
      if (selectionMode) {
        return <Notes isSelectionMode={true} onSelect={selectionCallback} onCloseSelection={() => closeFloating(id)} />;
      }
      return <Notes />;
    }
    if (type === "history") {
      if (selectionMode) {
        return <History isSelectionMode={true} onSelect={selectionCallback} onCloseSelection={() => closeFloating(id)} />;
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
      {floatingWindows.map((window, index) => {
        const { id, type, initialPosition } = window;
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
            onClose={() => closeFloating(id)}
            onBringToFront={() => setFrontWindowId(id)}
            isFront={frontWindowId === id}
          >
            {floatingContent(window)}
          </FloatingWindow>
        );
      })}
    </div>
  );
}
