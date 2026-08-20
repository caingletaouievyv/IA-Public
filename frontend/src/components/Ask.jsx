// IA/frontend/src/components/Ask.jsx
// Ask: question → POST /ai/ask; optional note context; optional conversation history (same notes table).
// No authenticated API calls without token; surface auth errors in UI.

import { useState, useEffect } from "react";
import { ask, listNotes, getNote, updateNote, getToken } from "../api";
import ConversationPicker from "./ConversationPicker";

function parseMessages(content) {
  if (!content || !content.trim()) return [];
  try {
    const arr = JSON.parse(content);
    return Array.isArray(arr)
      ? arr.filter(
          (m) =>
            m &&
            (m.role === "user" || m.role === "assistant") &&
            typeof m.content === "string"
        )
      : [];
  } catch {
    return [];
  }
}

export default function Ask() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState([]);
  const [notesLoaded, setNotesLoaded] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [currentHistoryId, setCurrentHistoryId] = useState(null);
  const [messages, setMessages] = useState([]);

  const loadNotes = async () => {
    setNotesLoaded(false);
    try {
      const list = await listNotes({ limit: 500 });
      const filtered = (Array.isArray(list) ? list : []).filter(
        (n) => (n.category || "") !== "_history"
      );
      setNotes(filtered);
      setNotesLoaded(true);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    if (!getToken()) return;

    if (!currentHistoryId) {
      setMessages([]);
      return;
    }

    let cancelled = false;

    getNote(currentHistoryId)
      .then((n) => {
        if (!cancelled && n) {
          setMessages(parseMessages(n.content || ""));
        }
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });

    return () => {
      cancelled = true;
    };
  }, [currentHistoryId]);

  const handleConversationChange = (id) => {
    setError(null);
    setResult(null);
    setCurrentHistoryId(id);
    if (!id) setMessages([]);
  };

  const toggleNote = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setLoading(true);

    try {
      const noteIds = selectedIds.size ? Array.from(selectedIds) : null;
      const historyMessages =
        currentHistoryId && messages.length > 0 ? messages : null;

      const data = await ask(question, noteIds, historyMessages);

      setResult({
        answer: data.answer,
        tokens: data.tokens_estimated,
      });

      const userContent = (question || "").trim();
      const assistantContent = (data.answer || "").trim();

      if (currentHistoryId && (userContent || assistantContent)) {
        const nextMessages = [
          ...messages,
          { role: "user", content: userContent },
          { role: "assistant", content: assistantContent },
        ];

        setMessages(nextMessages);

        await updateNote(currentHistoryId, {
          content: JSON.stringify(nextMessages),
        });
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

      <ConversationPicker
        value={currentHistoryId}
        onChange={handleConversationChange}
        disabled={loading}
      />

      <div className="ask-chat">
        {currentHistoryId && messages.length > 0 ? (
          <div className="ask-chat__messages">
            {messages.map((m, i) => (
              <div
                key={i}
                className={`ask-chat__message ask-chat__message--${m.role}`}
              >
                <span className="ask-chat__role">
                  {m.role === "user" ? "You" : "IA"}
                </span>

                <div className="ask-chat__content">{m.content}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="ask-chat__empty">
            {currentHistoryId
              ? "Start the conversation by sending a message."
              : "Ask a question, or start a conversation."}
          </div>
        )}

        {result && (
          <div className="ask-chat__message ask-chat__message--assistant">
            <span className="ask-chat__role">IA</span>

            <div className="ask-chat__content">
              {result.answer}

              {result.tokens != null && (
                <div className="meta">tokens: {result.tokens}</div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="card app-panel ask-context">
        <p className="card-title">Chat context (optional)</p>

        <p className="card-desc">
          Include specific notes so the AI answers using them as context.
        </p>

        <button type="button" onClick={loadNotes} disabled={loading}>
          {notesLoaded ? "Refresh notes" : "Select notes"}
        </button>

        {notesLoaded && notes.length > 0 && (
          <>
            <span
              className="card-title"
              style={{ display: "block", marginTop: "0.75rem" }}
            >
              Select notes to include
            </span>

            <ul className="check-list">
              {notes.map((n) => (
                <li key={n.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(n.id)}
                      onChange={() => toggleNote(n.id)}
                      disabled={loading}
                    />
                    <span>{n.title || n.id}</span>
                  </label>
                </li>
              ))}
            </ul>

            {selectedIds.size > 0 && (
              <span
                className="badge"
                style={{ display: "block", marginTop: "0.35rem" }}
              >
                {selectedIds.size} selected
              </span>
            )}
          </>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className={`card app-panel form--compact ask-composer ${
          loading ? "loading" : ""
        }`}
      >
        {selectedIds.size > 0 && (
          <p className="card-desc ask-composer__context">
            Using {selectedIds.size} note
            {selectedIds.size !== 1 ? "s" : ""}:{" "}
            {notes
              .filter((n) => selectedIds.has(n.id))
              .map((n) => n.title || "Untitled")
              .join(", ")}
          </p>
        )}

        <label htmlFor="question">Message</label>

        <textarea
          id="question"
          placeholder="Ask anything…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={loading}
        />

        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? "…" : "Ask"}
        </button>
      </form>

      {error && <div className="out err">{error}</div>}
    </section>
  );
}
