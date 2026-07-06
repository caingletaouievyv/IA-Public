// IA/frontend/src/components/FloatingWindow.jsx
// Draggable, resizable window; position and size persisted (see docs/ui.md).

import { useState, useCallback } from "react";

const STORAGE_KEY = "ia-floating-window";
const DEFAULT_X = 40;
const DEFAULT_Y = 40;
const MIN_WIDTH = 280;
const MIN_HEIGHT = 200;
const COLLAPSED_MARGIN = 16;
const COLLAPSED_GAP = 24;
const COLLAPSED_BAR_ESTIMATE = 86;
const COLLAPSED_STEP = COLLAPSED_BAR_ESTIMATE + COLLAPSED_GAP;

function isDesktopViewport() {
  if (typeof window === "undefined") return true;
  return window.innerWidth >= 768;
}

function getDefaultSize() {
  if (isDesktopViewport()) {
    const maxH = getMaxHeightPx();
    const maxW = getMaxWidthPx();
    return { width: Math.min(640, maxW), height: Math.min(520, maxH) };
  }
  return { width: MIN_WIDTH, height: Math.min(420, getMaxHeightPx()) };
}

function loadState(id, initialPosition) {
  const key = id ? `${STORAGE_KEY}-${id}` : STORAGE_KEY;
  const defaultSize = getDefaultSize();
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw);
      const x = typeof parsed.x === "number" ? parsed.x : DEFAULT_X;
      const y = typeof parsed.y === "number" ? parsed.y : DEFAULT_Y;
      const width = typeof parsed.width === "number" ? Math.min(Math.max(parsed.width, MIN_WIDTH), getMaxWidthPx()) : defaultSize.width;
      const height = typeof parsed.height === "number" ? Math.min(Math.max(parsed.height, MIN_HEIGHT), getMaxHeightPx()) : defaultSize.height;
      return { x, y, width, height };
    }
  } catch (_) {}
  if (initialPosition && typeof initialPosition.x === "number" && typeof initialPosition.y === "number") {
    return {
      x: initialPosition.x,
      y: initialPosition.y,
      width: defaultSize.width,
      height: defaultSize.height,
    };
  }
  return { x: DEFAULT_X, y: DEFAULT_Y, width: defaultSize.width, height: defaultSize.height };
}

function getMaxWidthPx() {
  if (typeof window === "undefined") return 900;
  return Math.max(MIN_WIDTH, window.innerWidth - 40);
}

function getMaxHeightPx() {
  if (typeof window === "undefined") return 800;
  return Math.max(MIN_HEIGHT, window.innerHeight - 48);
}

function saveState(state, id) {
  const key = id ? `${STORAGE_KEY}-${id}` : STORAGE_KEY;
  try {
    localStorage.setItem(key, JSON.stringify(state));
  } catch (_) {}
}

export default function FloatingWindow({ title = "IA", id, initialPosition, onClose, onBringToFront, isFront, stackIndex = 0, collapsedStackIndex = 0, onCollapsedChange, children }) {
  const [state, setState] = useState(() => loadState(id, initialPosition));
  const [collapsed, setCollapsed] = useState(false);
  const { x, y, width, height } = state;

  const setCollapsedAndNotify = useCallback(
    (valueOrUpdater) => {
      setCollapsed((prev) => {
        const next = typeof valueOrUpdater === "function" ? valueOrUpdater(prev) : valueOrUpdater;
        onCollapsedChange?.(id, next);
        return next;
      });
    },
    [id, onCollapsedChange]
  );

  const bringToFront = useCallback(() => {
    onBringToFront?.();
  }, [onBringToFront]);

  const handleTitleMouseDown = useCallback((e) => {
    if (e.button !== 0 || e.target.closest("button")) return;
    bringToFront();
    const startX = e.clientX - x;
    const startY = e.clientY - y;
    const onMove = (e2) => {
      setState((s) => ({
        ...s,
        x: Math.max(0, e2.clientX - startX),
        y: Math.max(0, e2.clientY - startY),
      }));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      setState((s) => {
        saveState(s, id);
        return s;
      });
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.userSelect = "none";
    document.body.style.cursor = "grabbing";
  }, [x, y, id, bringToFront]);

  const handleResizeMouseDown = useCallback((e) => {
    e.stopPropagation();
    if (e.button !== 0) return;
    bringToFront();
    const startX = e.clientX;
    const startY = e.clientY;
    const startW = width;
    const startH = height;
    const maxW = getMaxWidthPx();
    const maxH = getMaxHeightPx();
    const onMove = (e2) => {
      const dX = e2.clientX - startX;
      const dY = e2.clientY - startY;
      setState((s) => ({
        ...s,
        width: Math.min(maxW, Math.max(MIN_WIDTH, startW + dX)),
        height: Math.min(maxH, Math.max(MIN_HEIGHT, startH + dY)),
      }));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      setState((s) => {
        saveState(s, id);
        return s;
      });
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.userSelect = "none";
    document.body.style.cursor = "nwse-resize";
  }, [width, height, id, bringToFront]);

  const handleResizeHandleDoubleClick = useCallback(() => {
    const defaultSize = getDefaultSize();
    setState((s) => {
      const next = { ...s, width: defaultSize.width, height: defaultSize.height };
      saveState(next, id);
      return next;
    });
  }, [id]);

  return (
    <div
      className={`floating-window${collapsed ? " floating-window--collapsed" : ""}`}
      style={{
        ...(collapsed
          ? { left: COLLAPSED_MARGIN + collapsedStackIndex * COLLAPSED_STEP, bottom: COLLAPSED_MARGIN, top: "auto", width: "auto", minWidth: "min-content" }
          : { left: x, top: y, bottom: "auto", width, height, maxWidth: "calc(100vw - 2rem)", maxHeight: "calc(100vh - 2rem)" }),
        zIndex: isFront ? 10000 : 9999,
      }}
      onMouseDown={bringToFront}
    >
      <header
        className="floating-titlebar"
        onMouseDown={handleTitleMouseDown}
        onDoubleClick={(e) => { if (!e.target.closest("button")) setCollapsedAndNotify((c) => !c); }}
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        aria-label={collapsed ? "Collapsed window. Double-click to expand." : "Drag window. Double-click to minimize."}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setCollapsedAndNotify((c) => !c);
          }
        }}
      >
        <span className="floating-title">{title}</span>
        <div className="floating-titlebar-actions">
          <button
            type="button"
            className="floating-toggle"
            onClick={(e) => { e.stopPropagation(); setCollapsedAndNotify((c) => !c); }}
            aria-label={collapsed ? "Expand window" : "Collapse window"}
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? "▶" : "−"}
          </button>
          {onClose && (
            <button
              type="button"
              className="floating-close"
              onClick={(e) => { e.stopPropagation(); onClose(); }}
              aria-label="Close window"
              title="Close"
            >
              ×
            </button>
          )}
        </div>
      </header>
      {!collapsed && (
        <>
          <div className="floating-body">{children}</div>
          <div
            className="floating-resize-handle"
            onMouseDown={handleResizeMouseDown}
            onDoubleClick={handleResizeHandleDoubleClick}
            aria-label="Resize window"
            title="Resize (double-click for default size)"
          />
        </>
      )}
    </div>
  );
}
