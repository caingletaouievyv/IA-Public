// IA/frontend/src/components/Ask.jsx
// Ask: question → POST /ai/ask; optional note context; optional conversation history (same notes table).
// No authenticated API calls without token; surface auth errors in UI.

import { useState, useEffect, useLayoutEffect, useRef, useId } from "react";
import { ask, getNote, createHistory, updateNote, getToken } from "../api";

const CONTEXT_MODES = ["off", "selected", "automatic"];

function nextContextMode(mode) {
  return CONTEXT_MODES[(CONTEXT_MODES.indexOf(mode) + 1) % CONTEXT_MODES.length];
}

function parseMessages(content) {
  if (!content || !content.trim()) return [];
  try {
    const arr = JSON.parse(content);
    return Array.isArray(arr) ? arr.filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string") : [];
  } catch {
    return [];
  }
}

const CONTEXT_ICON_PATHS = {
  conversation: (
    <>
      <path d="M4 5.75A2.25 2.25 0 0 1 6.25 3.5h7.5A2.25 2.25 0 0 1 16 5.75v5.5a2.25 2.25 0 0 1-2.25 2.25H9l-4 3v-3.75a2.25 2.25 0 0 1-1-1.85Z" />
      <path d="M7 7.5h6M7 10h4" />
    </>
  ),
  notes: (
    <>
      <path d="M5.5 2.75h6l3.75 3.75v10a.75.75 0 0 1-.75.75h-9a.75.75 0 0 1-.75-.75V3.5a.75.75 0 0 1 .75-.75Z" />
      <path d="M11.5 3v4h4M7.5 10h5M7.5 12.75h5" />
    </>
  ),
  files: (
    <path d="M2.75 5.5a1.5 1.5 0 0 1 1.5-1.5h4l1.75 2h5.75a1.5 1.5 0 0 1 1.5 1.5v7a1.5 1.5 0 0 1-1.5 1.5h-11a1.5 1.5 0 0 1-1.5-1.5Z" />
  ),
  github: (
    <>
      <circle cx="10" cy="10" r="7.25" />
      <path d="M7 15.7v-1.2a2 2 0 0 1 .65-1.5c-1.55-.2-2.4-1.05-2.4-2.65 0-.8.3-1.4.85-1.9-.2-.65-.15-1.15.1-1.7.75 0 1.25.25 1.7.65a6.3 6.3 0 0 1 4.2 0c.45-.4.95-.65 1.7-.65.25.55.3 1.05.1 1.7.55.5.85 1.1.85 1.9 0 1.6-.85 2.45-2.4 2.65a2 2 0 0 1 .65 1.5v1.2" />
    </>
  ),
  memory: (
    <>
      <path d="M9.75 4.5a2.75 2.75 0 0 0-5.2 1.2 2.5 2.5 0 0 0-.8 4.45 2.5 2.5 0 0 0 1.75 4.1A2.75 2.75 0 0 0 9.75 15Z" />
      <path d="M10.25 4.5a2.75 2.75 0 0 1 5.2 1.2 2.5 2.5 0 0 1 .8 4.45 2.5 2.5 0 0 1-1.75 4.1 2.75 2.75 0 0 1-4.25.75ZM6.5 7.25a1.75 1.75 0 0 1 2 1.5m-3.5 2a1.75 1.75 0 0 1 3 1.25m6-4.75a1.75 1.75 0 0 0-2 1.5m3.5 2a1.75 1.75 0 0 0-3 1.25M10 4.5v11" />
    </>
  ),
  drive: (
    <>
      <path d="m7 4.25-4 7 2.5 4.5h9L17.25 12l-4-7Z" />
      <path d="m7 4.25 4.25 7.5M5.5 15.75 9.75 8.5m1.5 3h6" />
    </>
  ),
  web: (
    <>
      <circle cx="10" cy="10" r="7.25" />
      <path d="M2.9 10h14.2M10 2.75a11.5 11.5 0 0 1 0 14.5 11.5 11.5 0 0 1 0-14.5Z" />
    </>
  ),
};

function ContextIcon({ name }) {
  return (
    <svg className="ask-shortcut-icon__svg" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      {CONTEXT_ICON_PATHS[name]}
    </svg>
  );
}

function AskContextControl({ label, icon, details, mode, status, onModeChange, onOpen }) {
  const [longPressOpen, setLongPressOpen] = useState(false);
  const [detailsPinned, setDetailsPinned] = useState(false);
  const [detailsPosition, setDetailsPosition] = useState({ left: 8, top: 8 });
  const sourceRef = useRef(null);
  const pressTimerRef = useRef(null);
  const pointerStartRef = useRef(null);
  const suppressClickRef = useRef(false);
  const longPressTriggeredRef = useRef(false);
  const detailsId = useId();

  const updateDetailsAlignment = () => {
    const bounds = sourceRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const detailsWidth = Math.min(224, window.innerWidth - 16);
    setDetailsPosition({
      left: Math.max(8, Math.min(bounds.left, window.innerWidth - detailsWidth - 8)),
      top: bounds.bottom + 6,
    });
  };

  const clearPressTimer = () => {
    if (pressTimerRef.current !== null) {
      window.clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
  };

  useEffect(() => {
    if (!longPressOpen && !detailsPinned) return undefined;

    const handlePointerDown = (event) => {
      if (!sourceRef.current?.contains(event.target)) {
        setLongPressOpen(false);
        setDetailsPinned(false);
      }
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setLongPressOpen(false);
        setDetailsPinned(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [detailsPinned, longPressOpen]);

  useLayoutEffect(() => {
    updateDetailsAlignment();
    window.addEventListener("resize", updateDetailsAlignment);
    window.addEventListener("scroll", updateDetailsAlignment, true);
    return () => {
      window.removeEventListener("resize", updateDetailsAlignment);
      window.removeEventListener("scroll", updateDetailsAlignment, true);
    };
  }, []);

  useEffect(() => () => clearPressTimer(), []);

  const handlePointerDown = (event) => {
    if (event.pointerType === "mouse" || event.button !== 0) return;
    suppressClickRef.current = false;
    longPressTriggeredRef.current = false;
    updateDetailsAlignment();
    pointerStartRef.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
    };
    clearPressTimer();
    pressTimerRef.current = window.setTimeout(() => {
      setLongPressOpen(true);
      longPressTriggeredRef.current = true;
      suppressClickRef.current = true;
      pressTimerRef.current = null;
    }, 550);
  };

  const handlePointerMove = (event) => {
    const start = pointerStartRef.current;
    if (!start || start.pointerId !== event.pointerId) return;
    if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > 10) {
      clearPressTimer();
      pointerStartRef.current = null;
    }
  };

  const handlePointerUp = () => {
    clearPressTimer();
    pointerStartRef.current = null;
  };

  const handlePointerCancel = () => {
    handlePointerUp();
    if (!longPressTriggeredRef.current) suppressClickRef.current = false;
  };

  const handleClick = (event) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      longPressTriggeredRef.current = false;
      event.preventDefault();
      return;
    }
    setLongPressOpen(false);
    if (onOpen) {
      setDetailsPinned(false);
      onOpen();
    } else {
      setDetailsPinned((open) => !open);
    }
  };

  return (
    <div className={`ask-context-control${mode === null ? " ask-context-control--source-only" : ""}`}>
      <div
        ref={sourceRef}
        className={`ask-context-source-wrap${longPressOpen ? " ask-context-source-wrap--pressed" : ""}${detailsPinned ? " ask-context-source-wrap--pinned" : ""}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onPointerEnter={updateDetailsAlignment}
        onFocus={updateDetailsAlignment}
        onContextMenu={(event) => event.preventDefault()}
      >
        <button
          type="button"
          className="button-subtle ask-shortcut ask-context-source"
          onClick={handleClick}
          aria-describedby={detailsId}
        >
          <span className="ask-shortcut-icon" aria-hidden="true"><ContextIcon name={icon} /></span>
          <span>{label}</span>
          {status !== null && status !== undefined && (
            <span className="ask-context-count" aria-hidden="true">{status}</span>
          )}
        </button>
        <span
          id={detailsId}
          role="tooltip"
          className="ask-context-details"
          style={{
            position: "fixed",
            left: `${detailsPosition.left}px`,
            top: `${detailsPosition.top}px`,
            ...(longPressOpen || detailsPinned ? { visibility: "visible", opacity: 1 } : {}),
          }}
        >
          <strong>{label}</strong>
          {details.split("\n").map((line) => <span key={line}>{line}</span>)}
        </span>
      </div>
      {mode !== null && (
        <button
          type="button"
          className={`button-subtle button-toggle ask-shortcut ask-context-mode${mode !== "off" ? " ask-shortcut--active" : ""}`}
          onClick={() => onModeChange(nextContextMode(mode))}
          aria-label={`${label} context mode: ${mode.toUpperCase()}. Activate to change mode.`}
          aria-pressed={mode !== "off"}
        >
          [{mode.toUpperCase()}]
        </button>
      )}
    </div>
  );
}

export default function Ask({ onHistoryPicker, onNotesPicker, onUserMessageDetail }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [contextModes, setContextModes] = useState({
    notes: "off",
    files: "off",
    github: "off",
    memory: "off",
    drive: "off",
    web: "off",
  });
  const [currentHistoryId, setCurrentHistoryId] = useState(null);
  const [currentHistoryTitle, setCurrentHistoryTitle] = useState("");
  const [currentHistoryUpdatedAt, setCurrentHistoryUpdatedAt] = useState(null);
  const [messages, setMessages] = useState([]);
  const [historyExpanded, setHistoryExpanded] = useState(true);
  const [activeHistoryUserIndex, setActiveHistoryUserIndex] = useState(null);
  const historyRef = useRef(null);
  const historyUserMessageRefs = useRef([]);
  const submissionInFlightRef = useRef(false);
  const skipNextHistoryLoadRef = useRef(null);
  const setContextMode = (source, mode) => {
    setContextModes((current) => ({ ...current, [source]: mode }));
  };
  const handleNoteSelection = (selectedNotes) => {
    const nextNotes = Array.isArray(selectedNotes) ? selectedNotes.filter((note) => note?.id) : [];
    setNotes(nextNotes);
    setSelectedIds(new Set(nextNotes.map((note) => note.id)));
  };

  const openNotesPicker = () => onNotesPicker?.(handleNoteSelection, Array.from(selectedIds));
  const selectedNoteTitles = notes.filter((note) => selectedIds.has(note.id));
  const notesDetails = [
    "Your saved notes.",
    "Select notes to provide as context to the AI.",
    ...(selectedNoteTitles.length
      ? [
          `Selected: ${selectedNoteTitles
            .slice(0, 3)
            .map((note) => (note.title || "Untitled note").trim())
            .join(", ")}${selectedNoteTitles.length > 3 ? `, +${selectedNoteTitles.length - 3} more` : ""}`,
        ]
      : []),
  ].join("\n");
  const formatConversationMetaDate = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  };
  const conversationDetails = [
    "The active conversation and its saved messages.",
    "Choose or start a conversation.",
    ...(currentHistoryId
      ? [
          currentHistoryTitle || "Untitled",
          `${messages.length} messages`,
          `Updated ${formatConversationMetaDate(currentHistoryUpdatedAt)}`,
        ]
      : []),
  ].join("\n");
  const historyUserIndices = messages.reduce((indices, message, index) => {
    if (message.role === "user") indices.push(index);
    return indices;
  }, []);
  const activeHistoryUserPosition = historyUserIndices.indexOf(activeHistoryUserIndex);

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
          const nextMessages = parseMessages(n.content || "");
          setCurrentHistoryTitle(n.title || "Untitled");
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

  useEffect(() => {
    setActiveHistoryUserIndex(historyUserIndices.length ? historyUserIndices[historyUserIndices.length - 1] : null);
  }, [currentHistoryId, messages]);

  useLayoutEffect(() => {
    if (historyRef.current && messages.length > 0) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  }, [currentHistoryId, historyExpanded, messages]);

  const handleHistorySelection = (id) => {
    setCurrentHistoryId(id);
  };

  const openHistoryPicker = () => onHistoryPicker?.(handleHistorySelection, currentHistoryId);

  const navigateHistoryUserMessage = (direction) => {
    if (!historyUserIndices.length) return;
    const currentPosition = activeHistoryUserPosition < 0
      ? direction > 0 ? -1 : historyUserIndices.length
      : activeHistoryUserPosition;
    const targetPosition = Math.max(0, Math.min(historyUserIndices.length - 1, currentPosition + direction));
    const targetIndex = historyUserIndices[targetPosition];
    const target = historyUserMessageRefs.current[targetIndex];
    if (!target) return;
    setActiveHistoryUserIndex(targetIndex);
    target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    target.focus({ preventScroll: true });
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
    const noteIds = contextModes.notes !== "off" && selectedIds.size ? Array.from(selectedIds) : null;
    const historyMessages = activeMessages.length > 0 ? activeMessages : null;
    const noteApiMode = contextModes.notes === "selected" ? "focused" : contextModes.notes;
    const data = await ask(prompt, noteIds, historyMessages, noteApiMode);
    const userContent = (prompt || "").trim();
    const assistantContent = (data.answer || "").trim();
    if (historyId && (userContent || assistantContent)) {
      const nextMessages = [...activeMessages, { role: "user", content: userContent }, { role: "assistant", content: assistantContent }];
      setMessages(nextMessages);
      await updateNote(historyId, { content: JSON.stringify(nextMessages) });
    }
  };

  const saveUserMessage = async (messageIndex, content) => {
    const targetMessage = messages[messageIndex];
    const editedContent = content.trim();
    if (!targetMessage || targetMessage.role !== "user" || !editedContent) {
      return { success: false, error: "Enter a message before saving." };
    }
    if (loading || submissionInFlightRef.current) {
      return { success: false, error: "A request is already in progress." };
    }
    submissionInFlightRef.current = true;
    setError(null);
    setLoading(true);
    try {
      await sendQuestion(editedContent, messages.slice(0, messageIndex));
      return { success: true, content: editedContent };
    } catch (err) {
      setError(err.message);
      return { success: false, error: err.message };
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
            <AskContextControl
              label="Conversation"
              icon="conversation"
              details={conversationDetails}
              mode={null}
              status={currentHistoryId ? messages.length : null}
              onOpen={openHistoryPicker}
            />
            <AskContextControl
              label="Notes"
              icon="notes"
              details={notesDetails}
              mode={contextModes.notes}
              status={selectedIds.size || null}
              onModeChange={(mode) => setContextMode("notes", mode)}
              onOpen={openNotesPicker}
            />
            <AskContextControl
              label="Files"
              icon="files"
              details="Files are unavailable as Ask context: the file tree endpoint exists, but Ask has no file-selection or file-context flow."
              mode={contextModes.files}
              onModeChange={(mode) => setContextMode("files", mode)}
            />
            <AskContextControl
              label="GitHub"
              icon="github"
              details="GitHub context is not connected yet."
              mode={contextModes.github}
              onModeChange={(mode) => setContextMode("github", mode)}
            />
            <AskContextControl
              label="Memory"
              icon="memory"
              details="Separate Memory context is not connected yet. Notes automatic retrieval remains available."
              mode={contextModes.memory}
              onModeChange={(mode) => setContextMode("memory", mode)}
            />
            <AskContextControl
              label="Drive"
              icon="drive"
              details="Google Drive context is not connected yet."
              mode={contextModes.drive}
              onModeChange={(mode) => setContextMode("drive", mode)}
            />
            <AskContextControl
              label="Web"
              icon="web"
              details="Web context is not connected yet."
              mode={contextModes.web}
              onModeChange={(mode) => setContextMode("web", mode)}
            />
          </div>
        </header>

        {currentHistoryId && (
          <div className="ask-previous-messages">
            <h3 className="ask-section-heading ask-history-heading">
              <button
                type="button"
                className="button-subtle ask-history-toggle"
                onClick={() => {
                  setHistoryExpanded((expanded) => !expanded);
                }}
                aria-expanded={historyExpanded}
                aria-controls="ask-history-content"
              >
                <span>Conversation History</span>
                <span aria-hidden="true">{historyExpanded ? "−" : "+"}</span>
              </button>
              <div className="ask-history-navigation" role="group" aria-label="Navigate conversation messages">
                <button
                  type="button"
                  className="button-subtle button-icon ask-history-navigation__button"
                  onClick={() => navigateHistoryUserMessage(-1)}
                  disabled={!historyExpanded || historyUserIndices.length === 0 || activeHistoryUserPosition <= 0}
                  aria-label="Previous user message"
                  title="Previous user message"
                >
                  <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                    <path d="M10 15.5V4.5M5.5 9l4.5-4.5L14.5 9" />
                  </svg>
                </button>
                <button
                  type="button"
                  className="button-subtle button-icon ask-history-navigation__button"
                  onClick={() => navigateHistoryUserMessage(1)}
                  disabled={!historyExpanded || historyUserIndices.length === 0 || activeHistoryUserPosition === -1 || activeHistoryUserPosition >= historyUserIndices.length - 1}
                  aria-label="Next user message"
                  title="Next user message"
                >
                  <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                    <path d="M10 4.5v11M14.5 11 10 15.5 5.5 11" />
                  </svg>
                </button>
              </div>
            </h3>
            {historyExpanded && (
              <div id="ask-history-content" ref={historyRef} className="ask-history-scroll">
                {messages.map((message, index) => {
                  const isUserMessage = message.role === "user";
                  const isActiveMessage = isUserMessage && activeHistoryUserIndex === index;
                  const messageClassName = `ask-history-message${isActiveMessage ? " ask-history-message--navigation-active" : ""}`;
                  if (message.role === "user") {
                    return (
                      <div
                        key={index}
                        ref={(element) => { historyUserMessageRefs.current[index] = element; }}
                        className={`${messageClassName} ask-history-message--user`}
                        tabIndex={-1}
                        aria-label={`User message ${index + 1} of ${messages.length}`}
                        aria-current={isActiveMessage ? "location" : undefined}
                      >
                        <div className="ask-user-message-bubble">
                          <button
                            type="button"
                            className="ask-user-message-toggle"
                            onClick={() => onUserMessageDetail?.(
                              message.content,
                              (editedContent) => saveUserMessage(index, editedContent)
                            )}
                            aria-haspopup="dialog"
                            aria-label={`View user message ${index + 1}: ${message.content}`}
                          >
                            <span className="ask-user-message-toggle__text" aria-hidden="true">
                              <strong>User:</strong> {message.content}
                            </span>
                          </button>
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div
                      key={index}
                      className={messageClassName}
                    >
                      <div className="ask-history-message__content">
                        <strong>AI:</strong> {message.content}
                      </div>
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
