// IA/frontend/src/components/Ask.jsx
// Ask: question → POST /ai/ask; optional note context; optional conversation history (same notes table).
// No authenticated API calls without token; surface auth errors in UI.

import { useState, useEffect } from "react";
import { ask, getNote, createHistory, updateNote, getToken } from "../api";

function parseMessages(content) {
  if (!content || !content.trim()) return [];
  try {
    const arr = JSON.parse(content);
    return Array.isArray(arr) ? arr.filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string") : [];
  } catch {
    return [];
  }
}

export default function Ask({ onHistoryPicker = null, onNotesPicker = null }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState([]);
  const [notesLoaded, setNotesLoaded] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [currentHistoryId, setCurrentHistoryId] = useState(null);
  const [currentHistoryTitle, setCurrentHistoryTitle] = useState("");
  const [messages, setMessages] = useState([]);
  const [conversationExpanded, setConversationExpanded] = useState(false);
  const [chatContextExpanded, setChatContextExpanded] = useState(false);

  const handleNoteSelection = (note) => {
    if (!note?.id) return;
    setNotes([note]);
    setSelectedIds(new Set([note.id]));
    setNotesLoaded(true);
  };

  useEffect(() => {
    if (!currentHistoryId) {
      setCurrentHistoryTitle("");
      setMessages([]);
      return;
    }
    let cancelled = false;
    getNote(currentHistoryId)
      .then((n) => {
        if (!cancelled && n) {
          setCurrentHistoryTitle(n.title || "Untitled");
          setMessages(parseMessages(n.content || ""));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCurrentHistoryTitle("");
          setMessages([]);
        }
      });
    return () => { cancelled = true; };
  }, [currentHistoryId]);

  const toggleNote = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleNewConversation = async () => {
    setError(null);
    if (!getToken()) {
      setError("Session expired. Please sign in again.");
      return;
    }
    try {
      const created = await createHistory("New conversation");
      setCurrentHistoryId(created.id);
      setMessages([]);
    } catch (e) {
      setError(e.message || "Failed to create conversation");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const noteIds = selectedIds.size ? Array.from(selectedIds) : null;
      const historyMessages = currentHistoryId && messages.length > 0 ? messages : null;
      const data = await ask(question, noteIds, historyMessages);
      setResult({ answer: data.answer, tokens: data.tokens_estimated });
      const userContent = (question || "").trim();
      const assistantContent = (data.answer || "").trim();
      if (currentHistoryId && (userContent || assistantContent)) {
        const nextMessages = [...messages, { role: "user", content: userContent }, { role: "assistant", content: assistantContent }];
        setMessages(nextMessages);
        await updateNote(currentHistoryId, { content: JSON.stringify(nextMessages) });
      }
      setQuestion("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="section section--ask">
      <h2 className="app-panel__title">Ask</h2>
      <form onSubmit={handleSubmit} className={`card app-panel form--compact ${loading ? "loading" : ""}`}>
        <section className="ask-section">
          <button
            type="button"
            className="ask-section-toggle"
            onClick={() => setConversationExpanded((expanded) => !expanded)}
            aria-expanded={conversationExpanded}
          >
            <span>Conversation</span>
            <span aria-hidden="true">{conversationExpanded ? "−" : "+"}</span>
          </button>
          {conversationExpanded ? (
            <div className="ask-section-content">
              <p className="card-desc">
                Choose a history to continue, or start a new one. Messages are saved to the selected conversation.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
                <button type="button" onClick={handleNewConversation} disabled={loading}>
                  New conversation
                </button>
                <button
                  type="button"
                  onClick={() => onHistoryPicker?.((id) => setCurrentHistoryId(id))}
                  disabled={loading}
                >
                  Select conversation
                </button>
              </div>
              {currentHistoryId && (
                <p className="card-desc" style={{ marginTop: "0.75rem" }}>
                  Current conversation: <strong>{currentHistoryTitle || "Loading…"}</strong>
                </p>
              )}
            </div>
          ) : (
            <p className="card-desc ask-section-summary">
              Current conversation: <strong>{currentHistoryId ? currentHistoryTitle || "Loading…" : "None"}</strong>
            </p>
          )}
        </section>
      {currentHistoryId && messages.length > 0 && (
        <div className="ask-previous-messages">
          <p className="card-title">Previous messages</p>
          <div className="out" style={{ maxHeight: "12rem", overflowY: "auto" }}>
            {messages.map((m, i) => (
              <div key={i} style={{ marginBottom: "0.5rem" }}>
                <strong>{m.role === "user" ? "You" : "AI"}:</strong> {m.content}
              </div>
            ))}
          </div>
        </div>
      )}
      <section className="ask-section">
        <button
          type="button"
          className="ask-section-toggle"
          onClick={() => setChatContextExpanded((expanded) => !expanded)}
          aria-expanded={chatContextExpanded}
        >
          <span>Chat Context (optional)</span>
          <span aria-hidden="true">{chatContextExpanded ? "−" : "+"}</span>
        </button>
        {chatContextExpanded ? (
          <div className="ask-section-content">
            <p className="card-desc">
              Include specific notes so the AI answers only from them (e.g. “make a reviewer from these notes”).
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
              <button type="button" onClick={() => onNotesPicker?.(handleNoteSelection)} disabled={loading}>
                Load notes
              </button>
            </div>
            {notesLoaded && notes.length > 0 && (
              <>
                <span className="card-title ask-section-label">Select notes to include</span>
                <ul className="check-list">
                  {notes.map((n) => (
                    <li key={n.id}>
                      <label>
                        <input
                          type="checkbox"
                          checked={selectedIds.has(n.id)}
                          onChange={() => toggleNote(n.id)}
                        />
                        <span>{n.title || n.id}</span>
                      </label>
                    </li>
                  ))}
                </ul>
                {selectedIds.size > 0 && (
                  <span className="badge ask-section-badge">{selectedIds.size} selected</span>
                )}
              </>
            )}
          </div>
        ) : (
          <p className="card-desc ask-section-summary">
            {selectedIds.size === 0 ? "No notes selected" : `${selectedIds.size} note${selectedIds.size === 1 ? "" : "s"} selected`}
          </p>
        )}
      </section>
      <section className="ask-question">
        <p className="card-title">Question</p>
        {selectedIds.size > 0 && (
          <p className="card-desc" style={{ marginBottom: "0.5rem", marginTop: 0 }}>
            Using {selectedIds.size} note{selectedIds.size !== 1 ? "s" : ""}: {notes.filter((n) => selectedIds.has(n.id)).map((n) => n.title || "Untitled").join(", ")}
          </p>
        )}
        <label htmlFor="question">Question</label>
        <textarea
          id="question"
          placeholder="e.g. make a reviewer from the notes included"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          {loading ? "…" : "Ask"}
        </button>
      </section>
      </form>
      {error && <div className="out err">{error}</div>}
      {result && (
        <div className="out">
          {result.answer}
          {result.tokens != null && (
            <div className="meta">tokens: {result.tokens}</div>
          )}
        </div>
      )}
    </section>
  );
}
