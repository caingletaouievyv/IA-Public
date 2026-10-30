// IA/frontend/src/components/Ask.jsx
// Ask: question → POST /ai/ask; optional Notes/Memory context and conversation history.
// No authenticated API calls without token; surface auth errors in UI.

import { useState, useEffect, useLayoutEffect, useRef, useId, useMemo } from "react";
import { ask, getNote, createHistory, updateNote, getToken, getSettings, getCachedSettings, putSettings, reportAiFeedback } from "../api";
import {
  getActiveConversation,
  getSelectedNoteIds,
  setActiveConversation,
  setSelectedNoteIds,
} from "../activeConversation";
import AskContextIcon from "./AskContextIcon";
import AskOverlay from "./AskOverlay";
import FlashcardsPanel from "./FlashcardsPanel";
import ReportAnswerDialog from "./ReportAnswerDialog";
import {
  DEFAULT_CONTEXT_MODES,
  DEFAULT_VISIBLE_CONTEXT_SOURCES,
  getFocusActiveContextSources,
  getContextSourceOnLabel,
  getVisibleContextSources,
  normalizeContextModes,
  normalizeShowContextSourceLabels,
} from "../askContextSources";
import {
  acceptAskCommand,
  filterAskCommands,
  getActiveCommandToken,
  listAvailableAskCommands,
} from "../askCommands";
import AskCommandSuggestions from "./AskCommandSuggestions";
import AskNotesActionBanner from "./AskNotesActionBanner";

const CONTEXT_MODES = ["off", "selected", "automatic"];

function nextContextMode(mode, options = CONTEXT_MODES) {
  return options[(options.indexOf(mode) + 1) % options.length];
}

function AskHistoryActiveSourceIndicator({ sourceId, label }) {
  const statusLabel = getContextSourceOnLabel(label);
  const [detailsPinned, setDetailsPinned] = useState(false);
  const wrapRef = useRef(null);
  const detailsId = useId();

  useEffect(() => {
    if (!detailsPinned) return undefined;
    const close = (event) => {
      if (!wrapRef.current?.contains(event.target)) setDetailsPinned(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [detailsPinned]);

  return (
    <span
      ref={wrapRef}
      className={`ask-history-active-source${detailsPinned ? " ask-history-active-source--pressed" : ""}`}
      role="listitem"
    >
      <button
        type="button"
        className="button-subtle button-icon ask-history-active-source__button"
        aria-label={statusLabel}
        aria-describedby={detailsId}
        title={statusLabel}
        onClick={() => setDetailsPinned((open) => !open)}
      >
        <span className="ask-shortcut-icon" aria-hidden="true">
          <AskContextIcon name={sourceId} />
        </span>
      </button>
      <span id={detailsId} className="ask-history-active-source__tooltip" role="tooltip">
        <strong>{label}</strong>
        <span className="ask-context-details__state">ON</span>
      </span>
    </span>
  );
}

export function parseMessages(content) {
  if (!content || !content.trim()) return [];
  try {
    const arr = JSON.parse(content);
    if (!Array.isArray(arr)) return [];
    return arr.map((message) => {
      if (!message || typeof message.content !== "string") return null;
      if (message.role !== "user" && message.role !== "assistant") return null;
      const parsed = { role: message.role, content: message.content };
      const operationId = message.operationId || message.operation_id;
      if (typeof operationId === "string" && operationId.trim()) {
        parsed.operationId = operationId.trim();
      }
      const notesAction = message.notesAction || message.notes_action;
      if (notesAction && typeof notesAction === "object") {
        parsed.notesAction = notesAction;
      }
      return parsed;
    }).filter(Boolean);
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

function AskContextControl({
  label,
  icon,
  details,
  mode,
  modeLabel,
  modeOptions,
  status,
  stateLabel,
  onModeChange,
  onOpen,
  active = false,
  modeDisabled = false,
}) {
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
  const shownMode = modeLabel || mode?.toUpperCase();

  return (
    <div className={`ask-context-control${mode === null ? " ask-context-control--source-only" : ""}${active ? " ask-context-control--active" : ""}`}>
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
          aria-label={`${label}: ${stateLabel}`}
          title={`${label}: ${stateLabel}`}
        >
          <span className="ask-shortcut-icon" aria-hidden="true"><AskContextIcon name={icon} /></span>
          <span className="ask-context-source__label">{label}</span>
          {label === "Notes" && status !== null && status !== undefined && (
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
          <span className="ask-context-details__state">{stateLabel}</span>
          {details.split("\n").map((line) => <span key={line}>{line}</span>)}
        </span>
      </div>
      {mode !== null && (
        <button
          type="button"
          onClick={() => onModeChange(nextContextMode(mode, modeOptions))}
          disabled={modeDisabled}
          aria-label={label === "Memory"
            ? `Memory is ${shownMode}. Activate to turn Memory ${mode === "off" ? "on" : "off"}.`
            : `${label} context mode: ${shownMode}. Activate to change mode.`}
          title={label === "Memory"
            ? `${stateLabel}. Activate to turn Memory ${mode === "off" ? "on" : "off"}.`
            : `${label} context mode: ${shownMode}`}
          aria-pressed={mode !== "off"}
          className={`button-subtle button-toggle ask-shortcut ask-context-mode${mode !== "off" ? " ask-shortcut--active" : ""}`}
        >
          <span className="ask-context-mode__label">{shownMode}</span>
        </button>
      )}
    </div>
  );
}

export default function Ask({
  userId,
  onHistoryPicker,
  onNotesPicker,
  onUserMessageDetail,
  onHistoryFocusChange,
  onMemoryManage,
  onOpenCreatedNote,
  suggestionAction,
  onSuggestionActionConsumed,
}) {
  const [initialContextSettings] = useState(() => getCachedSettings());
  const [initialContextModes] = useState(() => {
    const savedModes = normalizeContextModes(initialContextSettings?.ask_context_modes);
    savedModes.memory = initialContextSettings?.memory_enabled === true ? "automatic" : "off";
    return savedModes;
  });
  const [question, setQuestion] = useState("");
  const [questionCaretIndex, setQuestionCaretIndex] = useState(0);
  const [commandSuggestionIndex, setCommandSuggestionIndex] = useState(0);
  const [commandSuggestionsDismissed, setCommandSuggestionsDismissed] = useState(false);
  const questionInputRef = useRef(null);
  const commandListId = useId();
  const [flashcardsOpen, setFlashcardsOpen] = useState(false);
  const [flashcardsBusy, setFlashcardsBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [rememberMessage, setRememberMessage] = useState(null);
  const [notes, setNotes] = useState([]);
  const [selectedIds, setSelectedIds] = useState(() => new Set(getSelectedNoteIds(userId)));
  const [visibleContextSources, setVisibleContextSources] = useState(() => initialContextSettings
    ? getVisibleContextSources(initialContextSettings.ask_context_sources).map((source) => source.id)
    : DEFAULT_VISIBLE_CONTEXT_SOURCES);
  const [showContextSourceLabels, setShowContextSourceLabels] = useState(() => initialContextSettings
    ? normalizeShowContextSourceLabels(initialContextSettings.show_context_source_labels)
    : normalizeShowContextSourceLabels(undefined));
  const [contextModes, setContextModes] = useState(initialContextModes);
  const [contextSettingsLoaded, setContextSettingsLoaded] = useState(() => initialContextSettings !== null);
  const [memoryEnabled, setMemoryEnabled] = useState(() => initialContextSettings?.memory_enabled === true);
  const [rememberCommandEnabled, setRememberCommandEnabled] = useState(
    () => initialContextSettings?.remember_command_enabled !== false,
  );
  const [memorySettingSaving, setMemorySettingSaving] = useState(false);
  const [currentHistoryId, setCurrentHistoryId] = useState(() => getActiveConversation(userId));
  const [currentHistoryTitle, setCurrentHistoryTitle] = useState("");
  const [currentHistoryUpdatedAt, setCurrentHistoryUpdatedAt] = useState(null);
  const [messages, setMessages] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(() => Boolean(getActiveConversation(userId)));
  const [historyFocused, setHistoryFocused] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState(null);
  const [reportDialog, setReportDialog] = useState(null);
  const [activeHistoryUserIndex, setActiveHistoryUserIndex] = useState(null);
  const historyRef = useRef(null);
  const historyUserMessageRefs = useRef([]);
  const copyFeedbackTimerRef = useRef(null);
  const reportCloseTimerRef = useRef(null);
  const submissionInFlightRef = useRef(false);
  const skipNextHistoryLoadRef = useRef(null);
  const currentHistoryIdRef = useRef(currentHistoryId);
  const contextModesRef = useRef(initialContextModes);
  const modeSaveQueueRef = useRef(Promise.resolve());

  useEffect(() => {
    if (initialContextSettings) return undefined;
    let cancelled = false;
    getSettings()
      .then((settings) => {
        if (!cancelled) {
          setVisibleContextSources(getVisibleContextSources(settings?.ask_context_sources).map((source) => source.id));
          setShowContextSourceLabels(normalizeShowContextSourceLabels(settings?.show_context_source_labels));
          const savedModes = normalizeContextModes(settings?.ask_context_modes);
          const enabled = settings?.memory_enabled === true;
          savedModes.memory = enabled ? "automatic" : "off";
          setMemoryEnabled(enabled);
          setRememberCommandEnabled(settings?.remember_command_enabled !== false);
          contextModesRef.current = savedModes;
          setContextModes(savedModes);
          setContextSettingsLoaded(true);
        }
      })
      .catch((settingsError) => {
        if (!cancelled) setError(`Could not load Ask context source preferences: ${settingsError.message}`);
      });
    return () => { cancelled = true; };
  }, [initialContextSettings]);

  useEffect(() => () => {
    window.clearTimeout(copyFeedbackTimerRef.current);
    window.clearTimeout(reportCloseTimerRef.current);
  }, []);

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
  const toggleMemory = async () => {
    if (memorySettingSaving || !contextSettingsLoaded) return;
    const nextEnabled = !memoryEnabled;
    setError(null);
    setMemorySettingSaving(true);
    try {
      await putSettings({ memory_enabled: nextEnabled });
      setMemoryEnabled(nextEnabled);
      const nextModes = { ...contextModesRef.current, memory: nextEnabled ? "automatic" : "off" };
      contextModesRef.current = nextModes;
      setContextModes(nextModes);
    } catch (settingsError) {
      setError(`Could not save Memory setting: ${settingsError.message}`);
    } finally {
      setMemorySettingSaving(false);
    }
  };
  useEffect(() => {
    if (!suggestionAction || !contextSettingsLoaded) return;
    if (suggestionAction.action === "open_flashcards") {
      setFlashcardsOpen(true);
    } else if (suggestionAction.action === "prepare_ask") {
      setQuestion("Summarize my recent note changes and suggest practical next steps.");
      setContextMode("notes", "automatic");
    }
    onSuggestionActionConsumed?.();
  }, [suggestionAction, contextSettingsLoaded, onSuggestionActionConsumed]);

  const handleNoteSelection = (selectedNotes) => {
    const nextNotes = Array.isArray(selectedNotes) ? selectedNotes.filter((note) => note?.id) : [];
    const nextIds = nextNotes.map((note) => note.id);
    setNotes(nextNotes);
    setSelectedIds(new Set(nextIds));
    setSelectedNoteIds(userId, nextIds);
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
      setHistoryLoading(false);
      return;
    }
    if (skipNextHistoryLoadRef.current === currentHistoryId) {
      skipNextHistoryLoadRef.current = null;
      setHistoryLoading(false);
      return;
    }
    let cancelled = false;
    setHistoryLoading(true);
    getNote(currentHistoryId)
      .then((n) => {
        if (cancelled) return;
        if (!n || n.category !== "_history") {
          currentHistoryIdRef.current = null;
          setActiveConversation(userId, null);
          setCurrentHistoryId(null);
          setCurrentHistoryTitle("");
          setCurrentHistoryUpdatedAt(null);
          setMessages([]);
          setError("This conversation is unavailable. Choose another conversation or start a new one.");
          return;
        }
        const nextMessages = parseMessages(n.content || "");
        setCurrentHistoryTitle(n.title || "Untitled");
        setCurrentHistoryUpdatedAt(n.updated_at || null);
        setMessages(nextMessages);
      })
      .catch((loadError) => {
        if (cancelled) return;
        if (/not found|404/i.test(loadError.message || "")) {
          currentHistoryIdRef.current = null;
          setActiveConversation(userId, null);
          setCurrentHistoryId(null);
          setCurrentHistoryTitle("");
          setCurrentHistoryUpdatedAt(null);
          setMessages([]);
          setError("This conversation is unavailable. Choose another conversation or start a new one.");
        } else {
          setError(`Could not load conversation: ${loadError.message}`);
        }
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => { cancelled = true; };
  }, [currentHistoryId, userId]);

  useEffect(() => {
    setActiveHistoryUserIndex(historyUserIndices.length ? historyUserIndices[historyUserIndices.length - 1] : null);
  }, [currentHistoryId, messages]);

  useLayoutEffect(() => {
    if (historyRef.current && messages.length > 0) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  }, [currentHistoryId, messages]);

  const handleHistorySelection = (id) => {
    setActiveConversation(userId, id);
    if (id === currentHistoryId) return;
    currentHistoryIdRef.current = id;
    setCurrentHistoryId(id);
    setCurrentHistoryTitle("");
    setCurrentHistoryUpdatedAt(null);
    setMessages([]);
    setHistoryLoading(Boolean(id));
    setError(null);
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
    setActiveConversation(userId, created.id);
    currentHistoryIdRef.current = created.id;
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
    const noteIds = contextModes.notes !== "off" && selectedIds.size
      ? Array.from(selectedIds)
      : null;
    const historyMessages = activeMessages.length > 0 ? activeMessages : null;
    const noteApiMode = contextModes.notes === "selected" ? "focused" : contextModes.notes;
    const data = await ask(prompt, noteIds, historyMessages, noteApiMode);
    if (data.remember_command === true) {
      return { rememberCommand: true, message: data.message || "" };
    }
    const userContent = (prompt || "").trim();
    const assistantContent = (data.answer || "").trim();
    const operationId = typeof data.operation_id === "string" ? data.operation_id : null;
    const notesAction = data.notes_action && typeof data.notes_action === "object"
      ? data.notes_action
      : null;
    if (historyId && (userContent || assistantContent)) {
      const assistantMessage = { role: "assistant", content: assistantContent };
      if (operationId) assistantMessage.operationId = operationId;
      if (notesAction) assistantMessage.notesAction = notesAction;
      const nextMessages = [...activeMessages, { role: "user", content: userContent }, assistantMessage];
      const updatedHistory = await updateNote(
        historyId,
        { content: JSON.stringify(nextMessages) },
        { activityRelevant: false },
      );
      if (currentHistoryIdRef.current === historyId) {
        setMessages(nextMessages);
        setCurrentHistoryTitle(updatedHistory.title || "Untitled");
        setCurrentHistoryUpdatedAt(updatedHistory.updated_at || null);
      }
    }
  };

  const saveUserMessage = async (messageIndex, content) => {
    const targetMessage = messages[messageIndex];
    const editedContent = content.trim();
    if (!targetMessage || targetMessage.role !== "user" || !editedContent) {
      return { success: false, error: "Enter a message before saving." };
    }
    if (loading || historyLoading || submissionInFlightRef.current) {
      return { success: false, error: "A request is already in progress." };
    }
    submissionInFlightRef.current = true;
    setError(null);
    setRememberMessage(null);
    setLoading(true);
    try {
      const result = await sendQuestion(editedContent, messages.slice(0, messageIndex));
      if (result?.rememberCommand) {
        setRememberMessage(result.message);
        return { success: true, content: editedContent };
      }
      return { success: true, content: editedContent };
    } catch (err) {
      setError(err.message);
      return { success: false, error: err.message };
    } finally {
      setLoading(false);
      submissionInFlightRef.current = false;
    }
  };

  const commandSettings = useMemo(
    () => ({ remember_command_enabled: rememberCommandEnabled }),
    [rememberCommandEnabled],
  );
  const activeCommandToken = getActiveCommandToken(question, questionCaretIndex);
  const availableAskCommands = listAvailableAskCommands(commandSettings);
  const commandSuggestions = activeCommandToken
    ? filterAskCommands(activeCommandToken.query, availableAskCommands)
    : [];
  const commandAutocompleteOpen = !commandSuggestionsDismissed
    && Boolean(activeCommandToken)
    && commandSuggestions.length > 0;

  useEffect(() => {
    setCommandSuggestionIndex(0);
  }, [commandSuggestions.length, activeCommandToken?.query]);

  const focusQuestionCaret = (caret) => {
    requestAnimationFrame(() => {
      const input = questionInputRef.current;
      if (!input) return;
      input.focus();
      input.setSelectionRange(caret, caret);
    });
  };

  const acceptCommandSuggestion = (command) => {
    const token = getActiveCommandToken(question, questionCaretIndex);
    if (!token || !command?.name) return;
    const { value, caret } = acceptAskCommand(
      question,
      questionCaretIndex,
      command.name,
      token.tokenStart,
      token.tokenEnd,
    );
    setQuestion(value);
    setQuestionCaretIndex(caret);
    setCommandSuggestionsDismissed(true);
    focusQuestionCaret(caret);
  };

  const handleQuestionChange = (event) => {
    setCommandSuggestionsDismissed(false);
    setQuestion(event.target.value);
    setQuestionCaretIndex(event.target.selectionStart ?? event.target.value.length);
  };

  const handleQuestionKeyDown = (event) => {
    if (commandAutocompleteOpen) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setCommandSuggestionIndex((current) => (current + 1) % commandSuggestions.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setCommandSuggestionIndex((current) => (
          current <= 0 ? commandSuggestions.length - 1 : current - 1
        ));
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setCommandSuggestionsDismissed(true);
        return;
      }
      if (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey)) {
        event.preventDefault();
        acceptCommandSuggestion(commandSuggestions[commandSuggestionIndex]);
        return;
      }
    }
    if (event.key === "Enter" && event.shiftKey) {
      event.preventDefault();
      const { selectionStart, selectionEnd, value } = event.currentTarget;
      const start = selectionStart ?? value.length;
      const end = selectionEnd ?? value.length;
      const nextValue = `${value.slice(0, start)}\n${value.slice(end)}`;
      setQuestion(nextValue);
      const nextCaret = start + 1;
      setQuestionCaretIndex(nextCaret);
      focusQuestionCaret(nextCaret);
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading || historyLoading || submissionInFlightRef.current) return;
    submissionInFlightRef.current = true;
    setError(null);
    setRememberMessage(null);
    setLoading(true);
    try {
      const result = await sendQuestion(question, currentHistoryId ? messages : []);
      if (result?.rememberCommand) {
        setRememberMessage(result.message);
      }
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

  const openReportDialog = (index, operationId) => {
    window.clearTimeout(reportCloseTimerRef.current);
    setReportDialog({
      index,
      operationId: operationId || null,
      reason: "wrong",
      status: "idle",
      message: "",
    });
  };

  const closeReportDialog = () => {
    if (reportDialog?.status === "submitting") return;
    window.clearTimeout(reportCloseTimerRef.current);
    setReportDialog(null);
  };

  const setReportDialogReason = (reason) => {
    setReportDialog((current) => {
      if (!current) return current;
      return {
        ...current,
        reason,
        status: current.status === "error" ? "idle" : current.status,
        message: current.status === "error" ? "" : current.message,
      };
    });
  };

  const activeFocusContextSources = historyFocused
    ? getFocusActiveContextSources(visibleContextSources, { currentHistoryId, contextModes })
    : [];

  const submitReportDialog = async () => {
    if (!reportDialog || reportDialog.status === "submitting" || reportDialog.status === "success") return;
    if (!reportDialog.operationId) {
      setReportDialog((current) => ({
        ...current,
        status: "error",
        message: "This answer cannot be reported yet. Ask a new question first.",
      }));
      return;
    }
    setReportDialog((current) => ({ ...current, status: "submitting", message: "" }));
    try {
      await reportAiFeedback(reportDialog.operationId, reportDialog.reason);
      setReportDialog((current) => ({
        ...current,
        status: "success",
        message: "Report received. Thank you.",
      }));
      reportCloseTimerRef.current = window.setTimeout(() => setReportDialog(null), 2000);
    } catch (error) {
      setReportDialog((current) => ({
        ...current,
        status: "error",
        message: error.message || "Could not send report.",
      }));
    }
  };

  return (
    <section className={`section section--ask${historyFocused ? " section--ask-history-focused" : ""}`}>
      <form onSubmit={handleSubmit} className={`card app-panel form--compact ask-form ${loading ? "loading" : ""}`}>
        {!historyFocused && contextSettingsLoaded && (
          <header className="ask-header">
            <div className={`ask-shortcuts${showContextSourceLabels ? " ask-shortcuts--labels-visible" : " ask-shortcuts--labels-hidden"}`} aria-label="Ask shortcuts">
              {getVisibleContextSources(visibleContextSources).map((source) => (
                <AskContextControl
                  key={source.id}
                  label={source.label}
                  icon={source.id}
                  details={source.id === "conversation"
                    ? conversationDetails
                    : source.id === "notes" ? notesDetails : source.details}
                  mode={source.id === "conversation" ? null : contextModes[source.id]}
                  modeLabel={source.id === "memory" ? memoryEnabled ? "ON" : "OFF" : undefined}
                  modeOptions={source.id === "memory" ? ["off", "automatic"] : undefined}
                  status={source.id === "conversation"
                    ? null
                    : source.id === "notes" ? selectedIds.size || null : null}
                  stateLabel={source.id === "conversation"
                    ? currentHistoryId ? "Active conversation" : "No active conversation"
                    : source.id === "memory"
                      ? `Memory is ${memoryEnabled ? "on" : "off"}`
                      : `${contextModes[source.id]?.toUpperCase()}${source.id === "notes" && selectedIds.size
                        ? `, ${selectedIds.size} selected`
                        : ""}`}
                  active={source.id === "conversation"
                    ? Boolean(currentHistoryId)
                    : contextModes[source.id] !== "off"}
                  onModeChange={source.id === "conversation"
                    ? undefined
                    : source.id === "memory" ? toggleMemory : (mode) => setContextMode(source.id, mode)}
                  modeDisabled={!contextSettingsLoaded || (source.id === "memory" && memorySettingSaving)}
                  onOpen={source.id === "conversation"
                    ? openHistoryPicker
                    : source.id === "notes" ? openNotesPicker
                      : source.id === "memory" ? onMemoryManage : undefined}
                />
              ))}
            </div>
          </header>
        )}

        {currentHistoryId && (
          <div className="ask-previous-messages">
            <h3 className="ask-section-heading ask-history-heading">
              <span className="ask-history-title">Conversation History</span>
              {historyFocused && activeFocusContextSources.length > 0 ? (
                <div className="ask-history-active-sources" role="list" aria-label="Active context sources">
                  {activeFocusContextSources.map((source) => (
                    <AskHistoryActiveSourceIndicator
                      key={source.id}
                      sourceId={source.id}
                      label={source.label}
                    />
                  ))}
                </div>
              ) : null}
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
              {historyLoading && <p className="notes-list-empty">Loading conversation…</p>}
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
                      {message.notesAction ? (
                        <AskNotesActionBanner
                          notesAction={message.notesAction}
                          fallbackContent={message.content}
                          onOpenCreatedNote={onOpenCreatedNote}
                          onApplySuggestionDraft={(draft) => {
                            setQuestion(draft);
                            setQuestionCaretIndex(draft.length);
                            focusQuestionCaret(draft.length);
                          }}
                        />
                      ) : (
                        <>
                          <strong>AI:</strong>{" "}
                          <span className="ask-history-message__text">{message.content}</span>
                        </>
                      )}
                    </div>
                    <div
                      className="ask-shortcuts"
                      role="group"
                      aria-label={`Actions for AI response ${messages.slice(0, index).filter((priorMessage) => priorMessage.role === "assistant").length + 1}`}
                    >
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
                      <button
                        type="button"
                        className="button-subtle button-icon ask-history-copy"
                        onClick={() => openReportDialog(index, message.operationId)}
                        disabled={loading}
                        aria-haspopup="dialog"
                        aria-label={`Report AI response ${messages.slice(0, index).filter((priorMessage) => priorMessage.role === "assistant").length + 1}`}
                        title={
                          !message.operationId
                            ? "Report this answer (may require a newer Ask response with a reference id)."
                            : "Report answer"
                        }
                      >
                        <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                          <path d="M5 3v14" />
                          <path d="M5 3h9l-2 3 2 3H5" />
                        </svg>
                      </button>
                    </div>
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
        <div className="ask-question__composer">
        <textarea
          ref={questionInputRef}
          id="question"
          className="ask-question__input"
          placeholder="Ask a question or describe what you need…"
          value={question}
          onChange={handleQuestionChange}
          onClick={(event) => setQuestionCaretIndex(event.target.selectionStart ?? 0)}
          onKeyUp={(event) => setQuestionCaretIndex(event.target.selectionStart ?? 0)}
          onKeyDown={handleQuestionKeyDown}
          disabled={loading || historyLoading}
          aria-autocomplete={commandAutocompleteOpen ? "list" : undefined}
          aria-controls={commandAutocompleteOpen ? commandListId : undefined}
          aria-expanded={commandAutocompleteOpen}
          aria-activedescendant={
            commandAutocompleteOpen
              ? `${commandListId}-option-${commandSuggestionIndex}`
              : undefined
          }
        />
        <AskCommandSuggestions
          listId={commandListId}
          anchorRef={questionInputRef}
          suggestions={commandAutocompleteOpen ? commandSuggestions : []}
          selectedIndex={commandSuggestionIndex}
          onHighlight={setCommandSuggestionIndex}
          onSelect={acceptCommandSuggestion}
        />
        </div>
        <button type="submit" className="button-primary ask-submit" aria-label={loading ? "Sending question" : "Ask"} disabled={loading || historyLoading}>
          {loading ? "…" : "Ask"}
        </button>
        </section>

      </form>
      {!historyFocused && (
        <details className="ask-shortcuts-section">
          <summary>Shortcuts</summary>
          <div className="ask-shortcuts-section__content">
            <button
              type="button"
              className="button-subtle flashcards-shortcut"
              onClick={() => setFlashcardsOpen(true)}
            >
              <strong>Flashcards</strong>
              <span>Browse saved decks or create cards from notes.</span>
            </button>
          </div>
        </details>
      )}
      {rememberMessage && (
        <div className="out success-msg" role="status">{rememberMessage}</div>
      )}
      {error && <div className="out err">{error}</div>}
      {flashcardsOpen && (
        <AskOverlay
          title="Flashcards"
          onClose={() => setFlashcardsOpen(false)}
          showManage={false}
          canClose={!flashcardsBusy}
        >
          <FlashcardsPanel
            onClose={() => setFlashcardsOpen(false)}
            onBusyChange={setFlashcardsBusy}
          />
        </AskOverlay>
      )}
      {reportDialog ? (
        <ReportAnswerDialog
          reason={reportDialog.reason}
          status={reportDialog.status}
          message={reportDialog.message}
          operationId={reportDialog.operationId}
          onReasonChange={setReportDialogReason}
          onSubmit={submitReportDialog}
          onClose={closeReportDialog}
        />
      ) : null}
    </section>
  );
}
