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

function ConversationIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <path d="M5 5.25A2.25 2.25 0 0 1 7.25 3h5.5A2.25 2.25 0 0 1 15 5.25v4.5A2.25 2.25 0 0 1 12.75 12H9.25L6 14.5V12H7.25A2.25 2.25 0 0 1 5 9.75v-4.5Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7.25 7.5h5.5M7.25 9.75h3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function NotesIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <path d="M6 3.5h5.25L15 8.25V14a1.5 1.5 0 0 1-1.5 1.5h-7A1.5 1.5 0 0 1 5 14V5A1.5 1.5 0 0 1 6.5 3.5h-.5Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M11.25 3.5V8.25H15" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7.25 10.25h5.5M7.25 12.75h4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AskBadgeInfo({ text, children, ariaLabel }) {
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  if (!text) return null;

  const toggle = (event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsOpen((open) => !open);
  };

  return (
    <span ref={wrapperRef} className="ask-badge" aria-live="polite">
      <span
        className={`ask-shortcut-count ask-shortcut-count--interactive${isOpen ? " ask-shortcut-count--open" : ""}`}
        title={text}
        tabIndex={0}
        aria-label={ariaLabel}
        aria-expanded={isOpen}
        onMouseEnter={() => setIsOpen(true)}
        onMouseLeave={() => setIsOpen(false)}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        onClick={toggle}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            event.stopPropagation();
            setIsOpen((open) => !open);
          }
        }}
      >
        {children}
      </span>
      {isOpen && (
        <span role="tooltip" className="ask-badge-info">
          {text.split("\n").map((line, index) => (
            <span key={`${line}-${index}`}>{line}</span>
          ))}
        </span>
      )}
    </span>
  );
}

export default function Ask({ onHistoryPicker = null, onNotesPicker = null }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [currentHistoryId, setCurrentHistoryId] = useState(null);
  const [currentHistoryTitle, setCurrentHistoryTitle] = useState("");
  const [currentHistoryUpdatedAt, setCurrentHistoryUpdatedAt] = useState(null);
  const [messages, setMessages] = useState([]);
  const [optionsMode, setOptionsMode] = useState(null);
  const [historyExpanded, setHistoryExpanded] = useState(true);
  const historyRef = useRef(null);
  const submissionInFlightRef = useRef(false);
  const skipNextHistoryLoadRef = useRef(null);

  const handleNoteSelection = (selectedNotes) => {
    const nextNotes = Array.isArray(selectedNotes) ? selectedNotes.filter((note) => note?.id) : [];
    setNotes(nextNotes);
    setSelectedIds(new Set(nextNotes.map((note) => note.id)));
  };

  const handleRemoveNote = (noteId) => {
    setNotes((previous) => previous.filter((note) => note.id !== noteId));
    setSelectedIds((previous) => {
      if (!previous.has(noteId)) return previous;
      const next = new Set(previous);
      next.delete(noteId);
      return next;
    });
  };

  const selectedNoteTitles = notes.filter((note) => selectedIds.has(note.id));

  const getNotesBadgeTooltip = () => {
    const count = selectedNoteTitles.length;
    if (count === 0) return "";
    if (count <= 9) {
      return selectedNoteTitles
        .slice(0, 9)
        .map((note) => {
          const label = (note?.title || "Untitled note").trim();
          return label.length > 36 ? `${label.slice(0, 33)}…` : label;
        })
        .join("\n");
    }
    return `${count} notes selected`;
  };

  const openNotesPicker = () => {
    if (onNotesPicker) {
      setOptionsMode(null);
      onNotesPicker(handleNoteSelection, selectedIds);
      return;
    }
    toggleOptionsMode("context");
  };

  const toggleOptionsMode = (mode) => {
    setOptionsMode((current) => (current === mode ? null : mode));
  };

  const formatConversationMetaDate = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  };

  const getConversationBadgeTooltip = () => {
    if (!currentHistoryId || !currentHistoryTitle) return "";
    const title = currentHistoryTitle.trim() || "Untitled";
    const summaryTitle = title.length > 36 ? `${title.slice(0, 33)}…` : title;
    return [
      summaryTitle,
      `Messages: ${messages.length}`,
      `Updated: ${formatConversationMetaDate(currentHistoryUpdatedAt)}`,
    ].join("\n");
  };

  useEffect(() => {
    if (!currentHistoryId) {
      setCurrentHistoryTitle("");
      setCurrentHistoryUpdatedAt(null);
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
          const nextTitle = n.title || "Untitled";
          const nextMessages = parseMessages(n.content || "");
          setCurrentHistoryTitle(nextTitle);
          setCurrentHistoryUpdatedAt(n.updated_at || null);
          setMessages(nextMessages);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCurrentHistoryTitle("");
          setCurrentHistoryUpdatedAt(null);
          setMessages([]);
        }
      });
    return () => { cancelled = true; };
  }, [currentHistoryId]);

  useLayoutEffect(() => {
    if (historyRef.current && messages.length > 0) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  }, [currentHistoryId, historyExpanded, messages]);

  const handleHistorySelection = (id) => {
    setCurrentHistoryId(id);
    setOptionsMode(null);
  };

  const openHistoryPicker = () => {
    setOptionsMode(null);
    onHistoryPicker?.(handleHistorySelection, currentHistoryId);
  };

  const selectedConversationTitle = currentHistoryTitle || "";

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
    setCurrentHistoryUpdatedAt(created.updated_at || new Date().toISOString());
    setMessages([]);
    setOptionsMode(null);
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
      <form onSubmit={handleSubmit} className={`card app-panel form--compact ask-form ${loading ? "loading" : ""}`}>
        <header className="ask-header">
          <div className="ask-shortcuts" aria-label="Ask shortcuts">
            <button
              type="button"
              className="ask-shortcut"
              onClick={openHistoryPicker}
              aria-label="Open conversation history to continue a saved conversation or start fresh."
              title="Continue a saved conversation or start fresh."
            >
              <span className="ask-shortcut-icon" aria-hidden="true"><ConversationIcon /></span>
              <span>Conversation</span>
              {currentHistoryId && (
                <AskBadgeInfo
                  text={getConversationBadgeTooltip()}
                  ariaLabel={`Active conversation: ${selectedConversationTitle || "Untitled"}. ${messages.length} messages. Updated ${formatConversationMetaDate(currentHistoryUpdatedAt)}.`}
                >
                  ●
                </AskBadgeInfo>
              )}
            </button>
            <button
              type="button"
              className={`ask-shortcut${optionsMode === "context" ? " ask-shortcut--active" : ""}`}
              onClick={openNotesPicker}
              aria-label="Open note picker to choose notes for this answer."
              title="Optional notes to help shape the answer."
            >
              <span className="ask-shortcut-icon" aria-hidden="true"><NotesIcon /></span>
              <span>Notes</span>
              {selectedIds.size > 0 && (
                <AskBadgeInfo
                  text={getNotesBadgeTooltip()}
                  ariaLabel={getNotesBadgeTooltip() || `${selectedIds.size} selected notes`}
                >
                  {selectedIds.size}
                </AskBadgeInfo>
              )}
            </button>
          </div>
        </header>

        {currentHistoryId && (
          <div className="ask-previous-messages">
            <h3 className="ask-section-heading ask-history-heading">
              <button
                type="button"
                className="ask-history-toggle"
                onClick={() => setHistoryExpanded((expanded) => !expanded)}
                aria-expanded={historyExpanded}
                aria-controls="ask-history-content"
              >
                <span>Conversation History</span>
                <span aria-hidden="true">{historyExpanded ? "−" : "+"}</span>
              </button>
            </h3>
            {historyExpanded && (
              <div id="ask-history-content" ref={historyRef} className="ask-history-scroll">
                {messages.map((m, i) => (
                  <div key={i} className="ask-history-message">
                    <strong>{m.role === "user" ? "You" : "AI"}:</strong> {m.content}
                  </div>
                ))}
              </div>
            )}
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

        {optionsMode && (
          <div id="ask-options" className="ask-options" aria-label="Ask options">
            {(optionsMode === "context" || optionsMode === "all") && (
              <section id="ask-context-section" className="ask-section ask-section--context">
                <div className="ask-context-action-row">
                  <button
                    type="button"
                    className="ask-action-button ask-context-action"
                    onClick={openNotesPicker}
                    disabled={loading}
                  >
                    {notes.length > 0 ? "Edit notes" : "Add notes"}
                  </button>
                </div>
                <div className="ask-section-content">
                  {notes.length > 0 && (
                    <ul className="check-list ask-context-notes" aria-label="Selected context notes">
                      {notes.map((n) => {
                        const noteLabel = n.title || n.id;
                        return (
                          <li key={n.id}>
                            <span>{noteLabel}</span>
                            <button
                              type="button"
                              className="ask-context-remove"
                              aria-label={`Remove "${noteLabel}" from context`}
                              onClick={() => handleRemoveNote(n.id)}
                              disabled={loading}
                            >
                              ×
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </section>
            )}

          </div>
        )}
      </form>
      {error && <div className="out err">{error}</div>}
    </section>
  );
}
