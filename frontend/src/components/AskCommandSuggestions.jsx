// IA/frontend/src/components/AskCommandSuggestions.jsx
// IntelliSense-style listbox for Ask message-prefix commands (fixed to composer width).

import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

function computeLayout(anchor, list) {
  const rect = anchor.getBoundingClientRect();
  list.style.boxSizing = "border-box";
  list.style.width = `${rect.width}px`;
  const listHeight = list.offsetHeight;
  const gap = 1;
  const viewportPad = 8;
  let top = rect.top - listHeight - gap;
  let placement = "above";
  if (top < viewportPad) {
    top = rect.bottom + gap;
    placement = "below";
  }
  return {
    left: rect.left,
    width: rect.width,
    top,
    placement,
  };
}

export default function AskCommandSuggestions({
  listId,
  suggestions,
  selectedIndex,
  onHighlight,
  onSelect,
  anchorRef,
}) {
  const listRef = useRef(null);
  const [layout, setLayout] = useState(null);

  useLayoutEffect(() => {
    if (!suggestions.length || !anchorRef?.current) {
      setLayout(null);
      return undefined;
    }

    const anchor = anchorRef.current;
    if (!anchor) return undefined;

    const syncLayout = () => {
      const list = listRef.current;
      const currentAnchor = anchorRef.current;
      if (!currentAnchor || !list) return;
      setLayout(computeLayout(currentAnchor, list));
    };

    syncLayout();
    const raf = requestAnimationFrame(syncLayout);
    const resizeObserver = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(syncLayout)
      : null;
    resizeObserver?.observe(anchor);
    window.addEventListener("resize", syncLayout);
    window.addEventListener("scroll", syncLayout, true);
    return () => {
      cancelAnimationFrame(raf);
      resizeObserver?.disconnect();
      window.removeEventListener("resize", syncLayout);
      window.removeEventListener("scroll", syncLayout, true);
    };
  }, [suggestions, selectedIndex, anchorRef]);

  if (!suggestions.length || typeof document === "undefined") return null;

  const list = (
    <ul
      ref={listRef}
      id={listId}
      className={`ask-command-suggestions${layout ? ` ask-command-suggestions--ready ask-command-suggestions--${layout.placement}` : ""}`}
      role="listbox"
      aria-label="Ask commands"
      style={layout ? {
        position: "fixed",
        left: `${layout.left}px`,
        width: `${layout.width}px`,
        top: `${layout.top}px`,
      } : undefined}
    >
      {suggestions.map((command, index) => (
        <li
          key={command.name}
          role="option"
          id={`${listId}-option-${index}`}
          className={`ask-command-suggestions__item${index === selectedIndex ? " ask-command-suggestions__item--active" : ""}`}
          aria-selected={index === selectedIndex}
          onMouseDown={(event) => event.preventDefault()}
          onMouseEnter={() => onHighlight(index)}
          onClick={() => onSelect(command)}
        >
          <span className="ask-command-suggestions__name">{command.name}</span>
          <span className="ask-command-suggestions__description">{command.description}</span>
        </li>
      ))}
    </ul>
  );

  return createPortal(list, document.body);
}
