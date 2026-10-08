// IA/frontend/src/components/AskOverlay.jsx
// Accessible modal shell for Ask's conversation and note selectors.

import { useEffect, useId, useRef } from "react";

export default function AskOverlay({
  title,
  onClose,
  onEscape,
  isManaging,
  onManage,
  showManage = true,
  closeText = "Close",
  children,
}) {
  const titleId = useId();
  const panelRef = useRef(null);
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;

  useEffect(() => {
    const previouslyFocused = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (onEscapeRef.current?.()) return;
        onClose();
        return;
      }

      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll(
        'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (!first) {
        event.preventDefault();
      } else if (event.shiftKey && (document.activeElement === first || document.activeElement === panelRef.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panelRef.current)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, [onClose]);

  return (
    <div className="ask-overlay">
      <div className="ask-overlay__backdrop" onClick={onClose} aria-hidden="true" />
      <section
        ref={panelRef}
        className="ask-overlay__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="ask-overlay__header">
          <h2 id={titleId} className="ask-overlay__title">{title}</h2>
          <div className="ask-overlay__actions">
            {showManage && (
              <button type="button" className="button-subtle ask-overlay__close" onClick={onManage}>
                {isManaging ? "Choose" : "Manage"}
              </button>
            )}
            <button
              type="button"
              className="button-subtle ask-overlay__close"
              onClick={onClose}
              aria-label={`Close ${title}`}
            >
              {closeText}
            </button>
          </div>
        </header>
        <div className="ask-overlay__body">{children}</div>
      </section>
    </div>
  );
}
