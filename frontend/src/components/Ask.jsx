// IA/frontend/src/components/Ask.jsx
// Ask: question → POST /ai/ask; optional note context; optional conversation history (same notes table).
// No authenticated API calls without token; surface auth errors in UI.

import { useState, useEffect, useLayoutEffect, useRef, useId } from "react";
import { ask, getNote, createHistory, updateNote, getToken, getSettings, putSettings } from "../api";
import AskContextIcon from "./AskContextIcon";
import {
  DEFAULT_CONTEXT_MODES,
  DEFAULT_VISIBLE_CONTEXT_SOURCES,
  getVisibleContextSources,
  normalizeContextModes,
} from "../askContextSources";

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

function markdownToPlainText(content) {
  return content
    .replace(/```[^\r\n]*\r?\n?/g, "")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s{0,3}>\s?/gm, "")
    .replace(/^(\s*)[-*+]\s+/gm, "$1• ")
    .replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/(\*|_)(.*?)\1/g, "$2")
    .replace(/~~(.*?)~~/g, "$1");
}

function AskContextControl({ label, icon, details, mode, status, onModeChange, onOpen, modeDisabled = false }) {
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
          <span className="ask-shortcut-icon" aria-hidden="true"><AskContextIcon name={icon} /></span>
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
          disabled={modeDisabled}
          aria-label={`${label} context mode: ${mode.toUpperCase()}. Activate to change mode.`}
          aria-pressed={mode !== "off"}
        >
          [{mode.toUpperCase()}]
        </button>
      )}
    </div>
  );
}

export default function Ask({ onHistoryPicker, onNotesPicker, onUserMessageDetail, onHistoryFocusChange }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [visibleContextSources, setVisibleContextSources] = useState(DEFAULT_VISIBLE_CONTEXT_SOURCES);
  const [contextModes, setContextModes] = useState(DEFAULT_CONTEXT_MODES);
  const [contextSettingsLoaded, setContextSettingsLoaded] = useState(false);
  const [currentHistoryId, setCurrentHistoryId] = useState(null);
  const [currentHistoryTitle, setCurrentHistoryTitle] = useState("");
  const [currentHistoryUpdatedAt, setCurrentHistoryUpdatedAt] = useState(null);
  const [messages, setMessages] = useState([]);
  const [historyFocused, setHistoryFocused] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState(null);
  const [activeHistoryUserIndex, setActiveHistoryUserIndex] = useState(null);
  const historyRef = useRef(null);
  const historyUserMessageRefs = useRef([]);
  const copyFeedbackTimerRef = useRef(null);
  const submissionInFlightRef = useRef(false);
  const skipNextHistoryLoadRef = useRef(null);
  const contextModesRef = useRef(DEFAULT_CONTEXT_MODES);
  const modeSaveQueueRef = useRef(Promise.resolve());

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((settings) => {
        if (!cancelled) {
          setVisibleContextSources(getVisibleContextSources(settings?.ask_context_sources).map((source) => source.id));
          const savedModes = normalizeContextModes(settings?.ask_context_modes);
          contextModesRef.current = savedModes;
          setContextModes(savedModes);
        }
      })
      .catch((settingsError) => {
        if (!cancelled) setError(`Could not load Ask context source preferences: ${settingsError.message}`);
      })
      .finally(() => {
        if (!cancelled) setContextSettingsLoaded(true);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => () => window.clearTimeout(copyFeedbackTimerRef.current), []);

  const setContextMode = (source, mode) => {
    const nextModes = { ...contextModesRef.current, [source]: mode };
    contextModesRef.current = nextModes;
    setContextModes(nextModes);
    const save = modeSaveQueueRef.current
      .catch(() => {})
      .then(() => putSettings({ ask_context_modes: nextModes }));
    modeSaveQueueRef.current = save;
    save.catch((settingsError) => {
      setError(`Could not save context mode preference: ${settingsError.message}`);
    });
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
  }, [currentHistoryId, messages]);

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

  const toggleHistoryFocus = () => {
    const nextFocused = !historyFocused;
    setHistoryFocused(nextFocused);
    onHistoryFocusChange?.(nextFocused);
  };

  const copyAiResponse = async (index, content) => {
    window.clearTimeout(copyFeedbackTimerRef.current);
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard access is unavailable in this browser.");
      }
      await navigator.clipboard.writeText(markdownToPlainText(content));
      setCopyFeedback({ index, status: "copied", message: "AI response copied." });
    } catch (error) {
      setCopyFeedback({
        index,
        status: "failed",
        message: `${error.message || "Clipboard access failed."} Select and copy the response manually.`,
      });
    }
    copyFeedbackTimerRef.current = window.setTimeout(() => setCopyFeedback(null), 2500);
  };

  return (
    <section className={`section section--ask${historyFocused ? " section--ask-history-focused" : ""}`}>
      <form onSubmit={handleSubmit} className={`card app-panel form--compact ask-form ${loading ? "loading" : ""}`}>
        {!historyFocused && (
          <header className="ask-header">
            <div className="ask-shortcuts" aria-label="Ask shortcuts">
              {getVisibleContextSources(visibleContextSources).map((source) => (
                <AskContextControl
                  key={source.id}
                  label={source.label}
                  icon={source.id}
                  details={source.id === "conversation"
                    ? conversationDetails
                    : source.id === "notes" ? notesDetails : source.details}
                  mode={source.id === "conversation" ? null : contextModes[source.id]}
                  status={source.id === "conversation"
                    ? currentHistoryId ? messages.length : null
                    : source.id === "notes" ? selectedIds.size || null : null}
                  onModeChange={source.id === "conversation"
                    ? undefined
                    : (mode) => setContextMode(source.id, mode)}
                  modeDisabled={!contextSettingsLoaded}
                  onOpen={source.id === "conversation"
                    ? openHistoryPicker
                    : source.id === "notes" ? openNotesPicker : undefined}
                />
              ))}
            </div>
          </header>
        )}

        {currentHistoryId && (
          <div className="ask-previous-messages">
            <h3 className="ask-section-heading ask-history-heading">
              <span className="ask-history-title">Conversation History</span>
              <div className="ask-history-heading__controls">
                <button
                  type="button"
                  className="button-subtle ask-history-focus"
                  onClick={toggleHistoryFocus}
                  aria-pressed={historyFocused}
                  aria-label={historyFocused
                    ? "Exit Conversation History focus"
                    : "Focus Conversation History"}
                  title={historyFocused
                    ? "Exit Conversation History focus"
                    : "Focus Conversation History"}
                >
                  <svg className="ask-history-focus__icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                    {historyFocused ? (
                      <path d="M2.5 2.5 7.5 7.5M4.5 7.5h3v-3M17.5 2.5 12.5 7.5m0-3v3h3M2.5 17.5l5-5m-3 0h3v3M17.5 17.5l-5-5m0 3v-3h3" />
                    ) : (
                      <path d="M7.5 7.5 2.5 2.5m0 0v4m0-4h4M12.5 7.5l5-5m-5 0h5v5M7.5 12.5l-5 5m0-5v5h5m5-5 5 5m0-5v5h-5" />
                    )}
                  </svg>
                  <span>{historyFocused ? "Exit Focus" : "Focus"}</span>
                </button>
                <div className="ask-history-navigation" role="group" aria-label="Navigate conversation messages">
                  <button
                    type="button"
                    className="button-subtle button-icon ask-history-navigation__button"
                    onClick={() => navigateHistoryUserMessage(-1)}
                    disabled={historyUserIndices.length === 0 || activeHistoryUserPosition <= 0}
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
                    disabled={historyUserIndices.length === 0 || activeHistoryUserPosition === -1 || activeHistoryUserPosition >= historyUserIndices.length - 1}
                    aria-label="Next user message"
                    title="Next user message"
                  >
                    <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                      <path d="M10 4.5v11M14.5 11 10 15.5 5.5 11" />
                    </svg>
                  </button>
                </div>
              </div>
            </h3>
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
                    className={`${messageClassName} ask-history-message--assistant`}
                  >
                    <div className="ask-history-message__content">
                      <strong>AI:</strong> <span className="ask-history-message__text">{message.content}</span>
                    </div>
                    <button
                      type="button"
                      className="button-subtle button-icon ask-history-copy"
                      onClick={() => copyAiResponse(index, message.content)}
                      aria-label={`Copy AI response ${messages.slice(0, index).filter((priorMessage) => priorMessage.role === "assistant").length + 1}`}
                      title={copyFeedback?.index === index && copyFeedback.status === "failed"
                        ? copyFeedback.message
                        : "Copy AI response"}
                    >
                      <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                        <rect x="7" y="7" width="10" height="10" rx="1.5" />
                        <path d="M13 7V5.5A1.5 1.5 0 0 0 11.5 4h-7A1.5 1.5 0 0 0 3 5.5v7A1.5 1.5 0 0 0 4.5 14H7" />
                      </svg>
                    </button>
                    <span className="ask-history-copy-status" role="status" aria-live="polite">
                      {copyFeedback?.index === index ? copyFeedback.message : ""}
                    </span>
                  </div>
                );
              })}
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
        <button type="submit" className="button-primary ask-submit" aria-label={loading ? "Sending question" : "Ask"} disabled={loading}>
          {loading ? "…" : "Ask"}
        </button>
        </section>

      </form>
      {error && <div className="out err">{error}</div>}
    </section>
  );
}
