// IA/frontend/src/components/AISuggestion.jsx
// Non-blocking suggestions based on authenticated, content-free activity metadata.

import { useEffect, useState } from "react";
import { getSettings, listActivity, requestAiSuggestion } from "../api";

const DISMISSED_LIMIT = 100;
const ACTION_LABELS = {
  prepare_ask: "Prepare Ask",
  open_flashcards: "Open Flashcards",
  review_activity: "Review Notes",
};

function recentContextKey(events) {
  const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const recent = (Array.isArray(events) ? events : []).filter((event) => {
    const timestamp = Date.parse(event?.timestamp);
    return Number.isFinite(timestamp)
      && timestamp >= cutoff
      && typeof event?.event_id === "string";
  }).slice(0, 5);
  return recent.length >= 2 ? recent.map((event) => event.event_id).join("|") : null;
}

function dismissedSuggestions(userId) {
  try {
    const value = JSON.parse(localStorage.getItem(`ia_ai_suggestions_dismissed_${userId}`) || "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function actionDismissalKey(action) {
  return `action:${action}:${new Date().toISOString().slice(0, 10)}`;
}

function rememberDismissal(userId, suggestionId, action) {
  const dismissed = dismissedSuggestions(userId);
  const ids = [suggestionId, actionDismissalKey(action)];
  if (ids.every((id) => dismissed.includes(id))) return;
  try {
    localStorage.setItem(
      `ia_ai_suggestions_dismissed_${userId}`,
      JSON.stringify([...new Set([...dismissed, ...ids])].slice(-DISMISSED_LIMIT)),
    );
  } catch {
    // The current render still suppresses this suggestion if browser storage is unavailable.
  }
}

export default function AISuggestion({ userId, onAccept }) {
  const [suggestion, setSuggestion] = useState(null);

  useEffect(() => {
    let active = true;
    let requestVersion = 0;
    let timer = null;
    let enabled = true;
    let lastContextKey = null;

    const refresh = async () => {
      const version = ++requestVersion;
      try {
        const settings = await getSettings();
        if (!active || version !== requestVersion) return;
        enabled = settings?.ai_suggestions_enabled !== false;
        if (!enabled) {
          lastContextKey = null;
          setSuggestion(null);
          return;
        }

        const events = await listActivity(50);
        if (!active || version !== requestVersion) return;
        const contextKey = recentContextKey(events);
        if (!contextKey) {
          lastContextKey = null;
          setSuggestion(null);
          return;
        }
        if (contextKey === lastContextKey) return;
        lastContextKey = contextKey;
        if (dismissedSuggestions(userId).includes(contextKey)) {
          setSuggestion(null);
          return;
        }

        const result = await requestAiSuggestion();
        if (!active || version !== requestVersion || !enabled) return;
        const candidate = result?.suggestion;
        if (
          !candidate
          || candidate.suggestion_id !== contextKey
          || !ACTION_LABELS[candidate.action]
          || typeof candidate.text !== "string"
        ) {
          setSuggestion(null);
          return;
        }
        if (dismissedSuggestions(userId).includes(actionDismissalKey(candidate.action))) {
          setSuggestion(null);
          return;
        }
        setSuggestion(candidate);
      } catch {
        if (active && version === requestVersion) setSuggestion(null);
      }
    };

    const scheduleRefresh = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(refresh, 250);
    };
    const onActivityUpdated = () => scheduleRefresh();
    const onSettingsUpdated = (event) => {
      if (event.detail?.ai_suggestions_enabled === false) {
        enabled = false;
        requestVersion += 1;
        lastContextKey = null;
        setSuggestion(null);
      } else {
        scheduleRefresh();
      }
    };

    refresh();
    window.addEventListener("ia:activity-updated", onActivityUpdated);
    window.addEventListener("ia:settings-updated", onSettingsUpdated);
    return () => {
      active = false;
      window.clearTimeout(timer);
      window.removeEventListener("ia:activity-updated", onActivityUpdated);
      window.removeEventListener("ia:settings-updated", onSettingsUpdated);
    };
  }, [userId]);

  if (!suggestion) return null;

  const finishSuggestion = () => {
    rememberDismissal(userId, suggestion.suggestion_id, suggestion.action);
    setSuggestion(null);
  };

  return (
    <aside className="ai-suggestion" role="region" aria-label="AI suggestion" aria-live="polite">
      <div className="ai-suggestion__card">
        <p className="ai-suggestion__label">A suggestion based on your recent activity</p>
        <p className="ai-suggestion__text">{suggestion.text}</p>
        <div className="ai-suggestion__actions">
          <button
            type="button"
            className="button-primary"
            onClick={() => {
              finishSuggestion();
              onAccept(suggestion.action);
            }}
          >
            {ACTION_LABELS[suggestion.action]}
          </button>
          <button type="button" className="button-secondary" onClick={finishSuggestion}>
            Dismiss
          </button>
        </div>
      </div>
    </aside>
  );
}

export { recentContextKey };
