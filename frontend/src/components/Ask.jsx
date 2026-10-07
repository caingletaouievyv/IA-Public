// IA/frontend/src/components/Ask.jsx
// Ask: question → POST /ai/ask; optional note context; optional conversation history (same notes table).
// No authenticated API calls without token; surface auth errors in UI.

import { useState, useEffect, useLayoutEffect, useRef, useId } from "react";
import { ask, getNote, createHistory, updateNote, getToken } from "../api";

const NOTE_CONTEXT_MODE_DETAILS = {
  off: {
    label: "Off",
    ariaLabel: "Note context mode: Off. Notes are not used.",
    title: "Off: Notes are not used.",
  },
  automatic: {
    label: "Automatic",
    ariaLabel: "Note context mode: Automatic. AI can search your notes when relevant.",
    title: "Automatic: AI can search your notes when relevant.",
  },
  focused: {
    label: "Focused",
    ariaLabel: "Note context mode: Focused. AI uses selected notes only.",
    title: "Focused: AI uses selected notes only.",
  },
};

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

export default function Ask({ onHistoryPicker, onNotesPicker }) {
  const editMessageInputId = useId();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [noteContextMode, setNoteContextMode] = useState("off");
  const [currentHistoryId, setCurrentHistoryId] = useState(null);
  const [currentHistoryTitle, setCurrentHistoryTitle] = useState("");
  const [currentHistoryUpdatedAt, setCurrentHistoryUpdatedAt] = useState(null);
  const [messages, setMessages] = useState([]);
  const [editingMessageIndex, setEditingMessageIndex] = useState(null);
  const [editedMessage, setEditedMessage] = useState("");
  const [historyExpanded, setHistoryExpanded] = useState(true);
  const historyRef = useRef(null);
  const submissionInFlightRef = useRef(false);
  const skipNextHistoryLoadRef = useRef(null);
  const modeDetails = NOTE_CONTEXT_MODE_DETAILS[noteContextMode] || NOTE_CONTEXT_MODE_DETAILS.off;

  const handleNoteSelection = (selectedNotes) => {
    const nextNotes = Array.isArray(selectedNotes) ? selectedNotes.filter((note) => note?.id) : [];
    setNotes(nextNotes);
    setSelectedIds(new Set(nextNotes.map((note) => note.id)));
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

  const openNotesPicker = () => onNotesPicker?.(handleNoteSelection, Array.from(selectedIds));

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
  };

  const openHistoryPicker = () => onHistoryPicker?.(handleHistorySelection, currentHistoryId);

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

  const sendQuestion = async (prompt, previousMessages) => {
    const historyId = currentHistoryId || (await createNewConversation()).id;
    const activeMessages = currentHistoryId ? previousMessages : [];
    const noteIds = selectedIds.size ? Array.from(selectedIds) : null;
    const historyMessages = activeMessages.length > 0 ? activeMessages : null;
    const data = await ask(prompt, noteIds, historyMessages, noteContextMode);
    const userContent = (prompt || "").trim();
    const assistantContent = (data.answer || "").trim();
    if (historyId && (userContent || assistantContent)) {
      const nextMessages = [...activeMessages, { role: "user", content: userContent }, { role: "assistant", content: assistantContent }];
      setMessages(nextMessages);
      await updateNote(historyId, { content: JSON.stringify(nextMessages) });
    }
  };

  const handleEditSave = async () => {
    const targetMessage = messages[editingMessageIndex];
    const editedContent = editedMessage.trim();
    if (!targetMessage || targetMessage.role !== "user" || !editedContent || loading || submissionInFlightRef.current) return;
    submissionInFlightRef.current = true;
    setError(null);
    setLoading(true);
    try {
      await sendQuestion(editedContent, messages.slice(0, editingMessageIndex));
      setEditingMessageIndex(null);
      setEditedMessage("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      submissionInFlightRef.current = false;
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading || submissionInFlightRef.current) return;
    submissionInFlightRef.current = true;
    setError(null);
    setLoading(true);
    try {
      await sendQuestion(question, currentHistoryId ? messages : []);
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
              className="button-subtle ask-shortcut"
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
              className="button-subtle ask-shortcut"
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
            <button
              type="button"
              className={`button-subtle button-toggle ask-shortcut${noteContextMode !== "off" ? " ask-shortcut--active" : ""}`}
              onClick={() => setNoteContextMode(
                noteContextMode === "off" ? "focused" : noteContextMode === "focused" ? "automatic" : "off"
              )}
              aria-label={modeDetails.ariaLabel}
              aria-pressed={noteContextMode !== "off"}
              title={modeDetails.title}
            >
              <span className="ask-shortcut-icon" aria-hidden="true"><NotesIcon /></span>
              <span>{modeDetails.label}</span>
              <span
                className={`ask-context-mode-indicator${noteContextMode === "automatic" ? " ask-context-mode-indicator--automatic" : noteContextMode === "focused" ? " ask-context-mode-indicator--focused" : ""}`}
                aria-hidden="true"
              />
            </button>
          </div>
        </header>

        {currentHistoryId && (
          <div className="ask-previous-messages">
            <h3 className="ask-section-heading ask-history-heading">
              <button
                type="button"
                className="button-subtle ask-history-toggle"
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
                {messages.map((message, index) => {
                  if (message.role === "user") {
                    const isEditing = editingMessageIndex === index;
                    return (
                      <div key={index} className="ask-history-message ask-history-message--user">
                        <div className={`ask-user-message-wrap${isEditing ? " ask-user-message-wrap--editing" : ""}`}>
                          {isEditing ? (
                            <div className="ask-user-message-editor">
                              <label htmlFor={editMessageInputId}>Edit your message</label>
                              <textarea
                                id={editMessageInputId}
                                value={editedMessage}
                                onChange={(event) => setEditedMessage(event.target.value)}
                                onKeyDown={(event) => {
                                  if (event.key === "Escape") {
                                    event.preventDefault();
                                    setEditingMessageIndex(null);
                                    setEditedMessage("");
                                  }
                                }}
                                autoFocus
                                disabled={loading}
                              />
                              <div className="ask-user-message-actions">
                                <button
                                  type="button"
                                  className="button-subtle"
                                  onClick={() => { setEditingMessageIndex(null); setEditedMessage(""); }}
                                  disabled={loading}
                                >
                                  Cancel
                                </button>
                                <button
                                  type="button"
                                  className="button-primary"
                                  onClick={handleEditSave}
                                  disabled={loading || !editedMessage.trim()}
                                >
                                  Save
                                </button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div className="ask-user-message-bubble">{message.content}</div>
                              <button
                                type="button"
                                className="button-subtle ask-user-message-edit"
                                onClick={() => { setEditedMessage(message.content); setEditingMessageIndex(index); }}
                                aria-label="Edit your message"
                                title="Edit your message"
                                disabled={loading}
                              >
                                Edit
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div key={index} className="ask-history-message">
                      <strong>AI:</strong> {message.content}
                    </div>
                  );
                })}
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
        <button type="submit" className="button-primary ask-submit" aria-label={loading ? "Sending question" : "Ask"} disabled={loading}>
          {loading ? "…" : "Ask"}
        </button>
        </section>

      </form>
      {error && <div className="out err">{error}</div>}
    </section>
  );
}
