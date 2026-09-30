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
import PublicSite from "./components/PublicSite";

const FLOAT_OFFSET = 32;
const UNAUTH_EVENT = "ia:unauthorized";
const FLOAT_MIN_WIDTH = 280;
const FLOAT_MIN_HEIGHT = 200;
const FLOAT_PAIR_GAP = 16;
const PUBLIC_PATHS = new Set(["/", "/privacy", "/terms", "/contact"]);

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

function getAskNotesLayout(askLayout) {
  if (window.innerWidth < 768 || !askLayout) return null;
  const width = Math.min(640, Math.floor((window.innerWidth - FLOAT_PAIR_GAP * 3) / 2));
  const height = Math.min(520, Math.max(FLOAT_MIN_HEIGHT, window.innerHeight - 48));
  const y = Math.max(FLOAT_PAIR_GAP, Math.min(askLayout.state.y, window.innerHeight - height - FLOAT_PAIR_GAP));
  const ask = {
    ...askLayout,
    state: { x: FLOAT_PAIR_GAP, y, width, height },
    maximized: false,
    contentSizeEnabled: false,
  };
  const notes = {
    x: FLOAT_PAIR_GAP * 2 + width,
    y,
    width,
    height,
  };
  return { ask, notes };
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
          <button type="button" className="app-header__logout button-subtle link-button" onClick={onLogout}>
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
  const floatingWindowRefs = useRef(new Map());
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

  const path = window.location.pathname.replace(/\/$/, "") || "/";
  if (PUBLIC_PATHS.has(path) && (path !== "/" || !token)) {
    return <PublicSite path={path} />;
  }

  if (!token) {
    return <Login onLogin={setAuthToken} />;
  }

  const openFloating = (type) => {
    const offset = nextOffsetRef.current;
    nextOffsetRef.current += FLOAT_OFFSET;
    const id = newFloatId();
    setFloatingWindows((wins) => [...wins, {
      id,
      type,
      ...(type === "ask" ? { noteContextMode: "off" } : {}),
      initialPosition: { x: 40 + offset, y: 40 + offset },
    }]);
    setFrontWindowId(id);
  };

  const closeFloating = (id) => {
    const closingWindow = floatingWindows.find((window) => window.id === id);
    if (closingWindow?.previousAskLayout) {
      floatingWindowRefs.current.get(closingWindow.parentAskId)?.setLayoutState(closingWindow.previousAskLayout);
    }
    setFloatingWindows((wins) => wins.filter((w) => w.id !== id));
    setFrontWindowId((front) => (front === id ? null : front));
    setCollapsedWindowIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const updateAskNoteContextMode = (askId, mode) => {
    if (mode !== "off" && mode !== "automatic" && mode !== "focused") return;
    setFloatingWindows((wins) => wins.map((window) => (
      window.id === askId && window.type === "ask"
        ? { ...window, noteContextMode: mode }
        : window
    )));
  };

  const openHistoryForSelection = (parentAskId, callback, activeHistoryId = null) => {
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
        activeHistoryId,
        initialPosition: centeredInitialPosition(),
      }];
    });
  };

  const openNotesForSelection = (parentAskId, callback, selectedIds = new Set()) => {
    const existing = floatingWindows.find((window) => window.type === "notes" && window.selectionMode && window.parentAskId === parentAskId);
    if (existing) {
      setFrontWindowId(existing.id);
      return;
    }

    const id = newFloatId();
    const askWindow = floatingWindowRefs.current.get(parentAskId);
    const previousAskLayout = askWindow?.getLayoutState() || null;
    const pairedLayout = getAskNotesLayout(previousAskLayout);
    if (pairedLayout) askWindow.setLayoutState(pairedLayout.ask);

    setFloatingWindows((wins) => {
      setFrontWindowId(id);
      return [...wins, {
        id,
        type: "notes",
        selectionMode: true,
        parentAskId,
        selectionCallback: callback,
        selectionIds: Array.from(selectedIds),
        previousAskLayout: pairedLayout ? previousAskLayout : null,
        initialPosition: pairedLayout?.notes || centeredInitialPosition(),
        initialSize: pairedLayout ? { width: pairedLayout.notes.width, height: pairedLayout.notes.height } : null,
      }];
    });
  };

  const floatingTitle = (type) => ({ ask: "Ask", notes: "Notes", history: "History", debug: "Debug", settings: "Settings" }[type] || type);
  const floatingContent = ({ id, type, selectionMode = false, selectionCallback = null, selectionIds = [], activeHistoryId = null, parentAskId = null, noteContextMode = "off" }) => {
    if (type === "ask") {
      return (
        <Ask
          onHistoryPicker={(callback, currentHistoryId) => openHistoryForSelection(id, callback, currentHistoryId)}
          onNotesPicker={(callback, selectedIds) => openNotesForSelection(id, callback, selectedIds)}
          noteContextMode={noteContextMode}
          onNoteContextModeChange={(mode) => updateAskNoteContextMode(id, mode)}
        />
      );
    }
    if (type === "notes") {
      if (selectionMode) {
        return (
          <Notes
            isSelectionMode={true}
            selectedIds={selectionIds}
            onSelect={selectionCallback}
            onCloseSelection={() => closeFloating(id)}
          />
        );
      }
      return <Notes />;
    }
    if (type === "history") {
      if (selectionMode) {
        return <History isSelectionMode={true} activeId={activeHistoryId} onSelect={selectionCallback} onCloseSelection={() => closeFloating(id)} />;
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
        <button type="button" className="button-subtle link-button" onClick={() => openFloating("ask")}>
          Ask
        </button>
        <span className="float-triggers-sep"> · </span>
        <button type="button" className="button-subtle link-button" onClick={() => openFloating("notes")}>
          Notes
        </button>
        <span className="float-triggers-sep"> · </span>
        <button type="button" className="button-subtle link-button" onClick={() => openFloating("history")}>
          History
        </button>
        <span className="float-triggers-sep"> · </span>
        <button type="button" className="button-subtle link-button" onClick={() => openFloating("debug")}>
          Debug
        </button>
        <span className="float-triggers-sep"> · </span>
        <button type="button" className="button-subtle link-button" onClick={() => openFloating("settings")}>
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
            ref={(instance) => {
              if (instance) floatingWindowRefs.current.set(id, instance);
              else floatingWindowRefs.current.delete(id);
            }}
            id={id}
            title={floatingTitle(type)}
            initialPosition={initialPosition}
            initialSize={window.initialSize}
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
            contentSized={type === "ask"}
          >
            {floatingContent(window)}
          </FloatingWindow>
        );
      })}
    </div>
  );
}
