// IA/frontend/src/components/FloatingWindow.jsx
// Draggable, resizable window; position and size persisted (see docs/ui.md).

import { useState, useCallback, useRef } from "react";

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
  return { width: Math.min(MIN_WIDTH, getMaxWidthPx()), height: Math.min(420, getMaxHeightPx()) };
}

function clampPosition(x, y, width, height) {
  if (isDesktopViewport()) return { x, y };
  return {
    x: Math.min(Math.max(0, x), Math.max(0, window.innerWidth - width)),
    y: Math.min(Math.max(0, y), Math.max(0, window.innerHeight - height)),
  };
}

function getCollapsedLeft(collapsedStackIndex) {
  const left = COLLAPSED_MARGIN + collapsedStackIndex * COLLAPSED_STEP;
  if (isDesktopViewport()) return left;
  return Math.min(left, Math.max(COLLAPSED_MARGIN, window.innerWidth - COLLAPSED_BAR_ESTIMATE - COLLAPSED_MARGIN));
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
      return { ...clampPosition(x, y, width, height), width, height };
    }
  } catch (_) {}
  if (initialPosition && typeof initialPosition.x === "number" && typeof initialPosition.y === "number") {
    return {
      ...clampPosition(initialPosition.x, initialPosition.y, defaultSize.width, defaultSize.height),
      width: defaultSize.width,
      height: defaultSize.height,
    };
  }
  return {
    ...clampPosition(DEFAULT_X, DEFAULT_Y, defaultSize.width, defaultSize.height),
    width: defaultSize.width,
    height: defaultSize.height,
  };
}

function getMaxWidthPx() {
  if (typeof window === "undefined") return 900;
  return isDesktopViewport() ? Math.max(MIN_WIDTH, window.innerWidth - 40) : Math.max(0, window.innerWidth - 32);
}

function getMaxHeightPx() {
  if (typeof window === "undefined") return 800;
  return isDesktopViewport() ? Math.max(MIN_HEIGHT, window.innerHeight - 48) : Math.max(0, window.innerHeight - 32);
}

function saveState(state, id) {
  const key = id ? `${STORAGE_KEY}-${id}` : STORAGE_KEY;
  try {
    localStorage.setItem(key, JSON.stringify(state));
  } catch (_) {}
}

function getInitialWindowState(id, initialPosition) {
  const normalState = loadState(id, initialPosition);
  const isMobile = !isDesktopViewport();

  if (!isMobile) {
    return {
      state: normalState,
      maximized: false,
      savedNormalState: null,
      contentSizeEnabled: false,
    };
  }

  return {
    state: {
      x: 16,
      y: 16,
      width: getMaxWidthPx(),
      height: getMaxHeightPx(),
    },
    maximized: true,
    savedNormalState: normalState,
    contentSizeEnabled: false,
  };
}

export default function FloatingWindow({ title = "IA", id, initialPosition, onClose, onBringToFront, isFront, stackIndex = 0, collapsedStackIndex = 0, onCollapsedChange, contentSized = false, children }) {
  const initialWindowStateRef = useRef(getInitialWindowState(id, initialPosition));
  const [state, setState] = useState(() => initialWindowStateRef.current.state);
  const [collapsed, setCollapsed] = useState(false);
  const [maximized, setMaximized] = useState(() => initialWindowStateRef.current.maximized);
  const [savedNormalState, setSavedNormalState] = useState(() => initialWindowStateRef.current.savedNormalState);
  const [contentSizeEnabled, setContentSizeEnabled] = useState(() => initialWindowStateRef.current.contentSizeEnabled);
  const windowRef = useRef(null);
  const { x, y, width, height } = state;

  const getMaximizedGeometry = useCallback(() => {
    const width = getMaxWidthPx();
    const height = getMaxHeightPx();
    return {
      x: isDesktopViewport() ? 20 : 16,
      y: isDesktopViewport() ? 24 : 16,
      width,
      height,
    };
  }, []);

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

  const handleMaximize = useCallback(() => {
    if (!maximized) {
      setSavedNormalState(state);
      setContentSizeEnabled(false);
      setState(getMaximizedGeometry());
      setMaximized(true);
    }
  }, [maximized, state, getMaximizedGeometry]);

  const handleRestore = useCallback(() => {
    if (maximized && savedNormalState) {
      setState(savedNormalState);
      setContentSizeEnabled(contentSized);
      setMaximized(false);
      setSavedNormalState(null);
    }
  }, [contentSized, maximized, savedNormalState]);

  const startDrag = useCallback((startClientX, startClientY) => {
    if (maximized) return;
    bringToFront();
    const startX = startClientX - x;
    const startY = startClientY - y;
    const onMove = (moveClientX, moveClientY) => {
      const nextX = Math.max(0, moveClientX - startX);
      const nextY = Math.max(0, moveClientY - startY);
      setState((s) => ({
        ...s,
        x: isDesktopViewport() ? nextX : Math.min(nextX, Math.max(0, window.innerWidth - width)),
        y: isDesktopViewport() ? nextY : Math.min(nextY, Math.max(0, window.innerHeight - height)),
      }));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.removeEventListener("touchmove", handleTouchMove);
      document.removeEventListener("touchend", handleTouchEnd);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      setState((s) => {
        saveState(s, id);
        return s;
      });
    };
    const handleMouseMove = (e2) => onMove(e2.clientX, e2.clientY);
    const handleMouseUp = onUp;
    const handleTouchMove = (e2) => {
      if (e2.touches.length > 0) {
        onMove(e2.touches[0].clientX, e2.touches[0].clientY);
      }
    };
    const handleTouchEnd = onUp;
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.addEventListener("touchmove", handleTouchMove, { passive: false });
    document.addEventListener("touchend", handleTouchEnd);
    document.body.style.userSelect = "none";
    document.body.style.cursor = "grabbing";
  }, [x, y, width, height, id, maximized, bringToFront]);

  const handleTitleMouseDown = useCallback((e) => {
    if (e.button !== 0 || e.target.closest("button")) return;
    startDrag(e.clientX, e.clientY);
  }, [startDrag]);

  const handleTitleTouchStart = useCallback((e) => {
    if (e.target.closest("button")) return;
    if (e.touches.length > 0) {
      startDrag(e.touches[0].clientX, e.touches[0].clientY);
    }
  }, [startDrag]);

  const startResize = useCallback((startClientX, startClientY) => {
    if (maximized) return;
    bringToFront();
    setContentSizeEnabled(false);
    const startX = startClientX;
    const startY = startClientY;
    const measuredSize = windowRef.current?.getBoundingClientRect();
    const startW = measuredSize?.width || width;
    const startH = measuredSize?.height || height;
    const maxW = getMaxWidthPx();
    const maxH = getMaxHeightPx();
    const onMove = (moveClientX, moveClientY) => {
      const dX = moveClientX - startX;
      const dY = moveClientY - startY;
      setState((s) => ({
        ...s,
        width: Math.min(maxW, Math.max(MIN_WIDTH, startW + dX)),
        height: Math.min(maxH, Math.max(MIN_HEIGHT, startH + dY)),
      }));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.removeEventListener("touchmove", handleTouchMove);
      document.removeEventListener("touchend", handleTouchEnd);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      setState((s) => {
        saveState(s, id);
        return s;
      });
    };
    const handleMouseMove = (e2) => onMove(e2.clientX, e2.clientY);
    const handleMouseUp = onUp;
    const handleTouchMove = (e2) => {
      if (e2.touches.length > 0) {
        onMove(e2.touches[0].clientX, e2.touches[0].clientY);
      }
    };
    const handleTouchEnd = onUp;
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.addEventListener("touchmove", handleTouchMove, { passive: false });
    document.addEventListener("touchend", handleTouchEnd);
    document.body.style.userSelect = "none";
    document.body.style.cursor = "nwse-resize";
  }, [width, height, id, maximized, bringToFront]);

  const handleResizeMouseDown = useCallback((e) => {
    e.stopPropagation();
    if (e.button !== 0) return;
    startResize(e.clientX, e.clientY);
  }, [startResize]);

  const handleResizeTouchStart = useCallback((e) => {
    e.stopPropagation();
    if (e.touches.length > 0) {
      startResize(e.touches[0].clientX, e.touches[0].clientY);
    }
  }, [startResize]);

  const handleResizeHandleDoubleClick = useCallback(() => {
    const defaultSize = getDefaultSize();
    setContentSizeEnabled(contentSized);
    setState((s) => {
      const next = { ...s, width: defaultSize.width, height: defaultSize.height };
      saveState(next, id);
      return next;
    });
  }, [contentSized, id]);

  return (
    <div
      className={`floating-window${collapsed ? " floating-window--collapsed" : ""}${maximized ? " floating-window--maximized" : ""}${contentSizeEnabled && !maximized ? " floating-window--content-sized" : ""}`}
      ref={windowRef}
      style={{
        ...(collapsed
          ? { left: getCollapsedLeft(collapsedStackIndex), bottom: COLLAPSED_MARGIN, top: "auto", width: "auto", minWidth: "min-content" }
          : { left: x, top: y, bottom: "auto", width, ...(contentSizeEnabled && !maximized ? { height: "auto" } : { height }), maxWidth: "calc(100vw - 2rem)", maxHeight: "calc(100vh - 2rem)" }),
        zIndex: isFront ? 10000 : 9999,
      }}
      onMouseDown={bringToFront}
    >
      <header
        className="floating-titlebar"
        onMouseDown={handleTitleMouseDown}
        onTouchStart={handleTitleTouchStart}
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
          {!collapsed && (
            <>
              <button
                type="button"
                className="floating-maximize"
                onClick={(e) => { e.stopPropagation(); handleMaximize(); }}
                aria-label="Maximize window"
                title="Maximize"
                style={{ display: maximized ? "none" : "flex" }}
              >
                <span className="floating-window-icon floating-maximize-icon" aria-hidden="true" />
              </button>
              <button
                type="button"
                className="floating-restore"
                onClick={(e) => { e.stopPropagation(); handleRestore(); }}
                aria-label="Restore window"
                title="Restore"
                style={{ display: maximized ? "flex" : "none" }}
              >
                ◧
              </button>
            </>
          )}
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
          {!maximized && (
            <div
              className="floating-resize-handle"
              onMouseDown={handleResizeMouseDown}
              onTouchStart={handleResizeTouchStart}
              onDoubleClick={handleResizeHandleDoubleClick}
              aria-label="Resize window"
              title="Resize (double-click for default size)"
            />
          )}
        </>
      )}
    </div>
  );
}
