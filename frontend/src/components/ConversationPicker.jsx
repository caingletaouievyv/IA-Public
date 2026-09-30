// IA/frontend/src/components/ConversationPicker.jsx
// Conversation picker for Ask: select an existing history or create a new conversation.
// Uses the shared API layer; surfaces authentication/API errors in the picker UI.

import { useEffect, useState } from "react";
import { listHistories, createHistory, getToken } from "../api";

export default function ConversationPicker({ value, onChange, disabled = false }) {
  const [histories, setHistories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadHistories = async () => {
    setLoading(true);
    setError(null);

    try {
      const list = await listHistories();
      setHistories(Array.isArray(list) ? list : []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!getToken()) return;
    loadHistories();
  }, []);

  const handleNew = async () => {
    setError(null);

    if (!getToken()) {
      setError("Session expired. Please sign in again.");
      return;
    }

    setLoading(true);

    try {
      const created = await createHistory("New conversation");
      await loadHistories();
      onChange(created.id);
    } catch (e) {
      setError(e.message || "Failed to create conversation");
    } finally {
      setLoading(false);
    }
  };

  const selected = value
    ? histories.find((history) => history.id === value)
    : null;

  return (
    <div className="ask-conversation">
      <div className="ask-conversation__header">
        <div>
          <span className="ask-label">Conversation</span>
          <span className="ask-conversation__name">
            {selected?.title || "One-off question"}
          </span>
        </div>

        <div className="ask-conversation__actions">
          <button
            type="button"
            className="button-primary"
            onClick={handleNew}
            aria-label={loading ? "Creating conversation" : "New conversation"}
            disabled={disabled || loading}
          >
            {loading ? "…" : "New conversation"}
          </button>

          <button
            type="button"
            className="button-icon button-subtle"
            onClick={loadHistories}
            disabled={disabled || loading}
            title="Refresh conversations"
            aria-label="Refresh conversations"
          >
            ↻
          </button>
        </div>
      </div>

      <label htmlFor="ask-conversation-select">Conversation</label>

      <select
        id="ask-conversation-select"
        value={value || ""}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={disabled || loading}
      >
        <option value="">One-off question</option>

        {histories.map((history) => (
          <option key={history.id} value={history.id}>
            {history.title || "Untitled"}
          </option>
        ))}
      </select>

      {error && <div className="out out--compact err">{error}</div>}
    </div>
  );
}
