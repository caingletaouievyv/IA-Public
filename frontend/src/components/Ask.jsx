// IA/frontend/src/components/Ask.jsx
// Ask: question → POST /ai/ask; optional note context; optional conversation history (same notes table).
// No authenticated API calls without token; surface auth errors in UI.

import { useState, useEffect, useLayoutEffect, useRef } from "react";
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [currentHistoryId, setCurrentHistoryId] = useState(null);
  const [currentHistoryTitle, setCurrentHistoryTitle] = useState("");
  const [messages, setMessages] = useState([]);
  const [conversationExpanded, setConversationExpanded] = useState(false);
  const [chatContextExpanded, setChatContextExpanded] = useState(false);
  const [optionsExpanded, setOptionsExpanded] = useState(false);
  const historyRef = useRef(null);
  const submissionInFlightRef = useRef(false);
  const skipNextHistoryLoadRef = useRef(null);

  const handleNoteSelection = (selectedNotes) => {
    const nextNotes = Array.isArray(selectedNotes) ? selectedNotes.filter((note) => note?.id) : [];
    setNotes(nextNotes);
    setSelectedIds(new Set(nextNotes.map((note) => note.id)));
  };

  useEffect(() => {
    if (!currentHistoryId) {
      setCurrentHistoryTitle("");
      setMessages([]);
      return;
    }
    if (skipNextHistoryLoadRef.current === currentHistoryId) {
      skipNextHistoryLoadRef.current = null;
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

  useLayoutEffect(() => {
    if (historyRef.current && messages.length > 0) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  }, [currentHistoryId, messages]);

  const handleHistorySelection = (id) => {
    setCurrentHistoryId(id);
    setOptionsExpanded(false);
  };

  const createNewConversation = async () => {
    if (!getToken()) {
      throw new Error("Session expired. Please sign in again.");
    }
    const created = await createHistory("New conversation");
    if (!created?.id) {
      throw new Error("Failed to create conversation");
    }
    skipNextHistoryLoadRef.current = created.id;
    setCurrentHistoryId(created.id);
    setCurrentHistoryTitle(created.title || "New conversation");
    setMessages([]);
    setOptionsExpanded(false);
    return created;
  };

  const handleNewConversation = async () => {
    setError(null);
    try {
      await createNewConversation();
    } catch (e) {
      setError(e.message || "Failed to create conversation");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading || submissionInFlightRef.current) return;
    submissionInFlightRef.current = true;
    setError(null);
    setLoading(true);
    try {
      const historyId = currentHistoryId || (await createNewConversation()).id;
      const activeMessages = currentHistoryId ? messages : [];
      const noteIds = selectedIds.size ? Array.from(selectedIds) : null;
      const historyMessages = activeMessages.length > 0 ? activeMessages : null;
      const data = await ask(question, noteIds, historyMessages);
      const userContent = (question || "").trim();
      const assistantContent = (data.answer || "").trim();
      if (historyId && (userContent || assistantContent)) {
        const nextMessages = [...activeMessages, { role: "user", content: userContent }, { role: "assistant", content: assistantContent }];
        setMessages(nextMessages);
        await updateNote(historyId, { content: JSON.stringify(nextMessages) });
      }
      setQuestion("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      submissionInFlightRef.current = false;
    }
  };

  return (
    <section className="section section--ask">
      <form onSubmit={handleSubmit} className={`card app-panel form--compact ${loading ? "loading" : ""}`}>
        <header className="ask-header">
          <p className="ask-question__eyebrow">Ask anything</p>
          <button
            type="button"
            className="ask-options-button"
            onClick={() => setOptionsExpanded((expanded) => !expanded)}
            aria-expanded={optionsExpanded}
            aria-controls="ask-options"
            aria-label="Ask options"
            title="Ask options"
          >
            <span aria-hidden="true">⚙</span>
          </button>
        </header>

        {currentHistoryId && messages.length > 0 && (
          <div className="ask-previous-messages">
            <p className="card-title">Conversation history</p>
            <div ref={historyRef} className="ask-history-scroll">
              {messages.map((m, i) => (
                <div key={i} className="ask-history-message">
                  <strong>{m.role === "user" ? "You" : "AI"}:</strong> {m.content}
                </div>
              ))}
            </div>
          </div>
        )}

        <section className="ask-question">
        <label htmlFor="question" className="ask-question__label">Question</label>
        <textarea
          id="question"
          className="ask-question__input"
          placeholder="Ask a question or describe what you need…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          disabled={loading}
        />
        <button type="submit" className="ask-submit" disabled={loading}>
          {loading ? "…" : "Ask"}
        </button>
        </section>

        {optionsExpanded && (
          <div id="ask-options" className="ask-options" aria-label="Ask options">
            <section className="ask-section ask-section--conversation">
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
                  <p className="card-desc">Continue a saved conversation or start fresh.</p>
                  <div className="ask-options-actions">
                    <button type="button" onClick={handleNewConversation} disabled={loading}>New</button>
                    <button
                      type="button"
                      onClick={() => onHistoryPicker?.(handleHistorySelection)}
                      disabled={loading}
                    >
                      Choose conversation
                    </button>
                  </div>
                  {currentHistoryId && (
                    <p className="card-desc ask-current-conversation">
                      Current: <strong>{currentHistoryTitle || "Loading…"}</strong>
                    </p>
                  )}
                </div>
              ) : (
                <p className="card-desc ask-section-summary">
                  {currentHistoryId ? <>Current: <strong>{currentHistoryTitle || "Loading…"}</strong></> : "No conversation selected"}
                </p>
              )}
            </section>

            <section className="ask-section ask-section--context">
              <button
                type="button"
                className="ask-section-toggle"
                onClick={() => setChatContextExpanded((expanded) => !expanded)}
                aria-expanded={chatContextExpanded}
              >
                <span>Context</span>
                <span aria-hidden="true">{chatContextExpanded ? "−" : "+"}</span>
              </button>
              {chatContextExpanded ? (
                <div className="ask-section-content">
                  <p className="card-desc">Optional notes to help shape the answer.</p>
                  <div className="ask-context-row">
                    <span className="ask-context-count">
                      {selectedIds.size ? `${selectedIds.size} note${selectedIds.size === 1 ? "" : "s"} selected` : "No notes selected"}
                    </span>
                    <button
                      type="button"
                      className="ask-context-action"
                      onClick={() => onNotesPicker?.(handleNoteSelection, selectedIds)}
                      disabled={loading}
                    >
                      {notes.length > 0 ? "Edit notes" : "Add notes"}
                    </button>
                  </div>
                  {notes.length > 0 && (
                    <>
                      <ul className="check-list ask-context-notes" aria-label="Selected context notes">
                        {notes.map((n) => (
                          <li key={n.id}><span>{n.title || n.id}</span></li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              ) : (
                <p className="card-desc ask-section-summary">
                  {selectedIds.size === 0 ? "Optional · no notes added" : `Notes added · ${selectedIds.size}`}
                </p>
              )}
            </section>
          </div>
        )}
      </form>
      {error && <div className="out err">{error}</div>}
    </section>
  );
}
