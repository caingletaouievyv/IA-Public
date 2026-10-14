import { useEffect, useState } from "react";
import {
  clearMemories,
  deleteMemory,
  getSettings,
  listMemories,
  putSettings,
  updateMemory,
} from "../api";

export default function MemoryManager() {
  const [memories, setMemories] = useState([]);
  const [memoryEnabled, setMemoryEnabled] = useState(null);
  const [loading, setLoading] = useState(true);
  const [savingSetting, setSavingSetting] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [items, settings] = await Promise.all([listMemories(), getSettings()]);
      setMemories(Array.isArray(items) ? items : []);
      setMemoryEnabled(settings?.memory_enabled === true);
    } catch (loadError) {
      setError(`Could not load Memory: ${loadError.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const toggleMemory = async (event) => {
    const enabled = event.target.checked;
    setSavingSetting(true);
    setError("");
    setStatus("");
    try {
      const updated = await putSettings({ memory_enabled: enabled });
      setMemoryEnabled(updated.memory_enabled === true);
      setStatus(`Memory is ${enabled ? "on" : "off"}.`);
    } catch (saveError) {
      setError(`Could not save Memory setting: ${saveError.message}`);
    } finally {
      setSavingSetting(false);
    }
  };

  const startEditing = (memory) => {
    setEditingId(memory.id);
    setDraft(memory.text);
    setError("");
    setStatus("");
  };

  const saveEdit = async (memoryId) => {
    setSavingId(memoryId);
    setError("");
    setStatus("");
    try {
      const updated = await updateMemory(memoryId, draft);
      setMemories((current) => current.map((item) => item.id === memoryId ? updated : item));
      setEditingId(null);
      setDraft("");
      setStatus("Memory updated.");
    } catch (saveError) {
      setError(`Could not update Memory: ${saveError.message}`);
    } finally {
      setSavingId(null);
    }
  };

  const removeMemory = async (memoryId) => {
    setSavingId(memoryId);
    setError("");
    setStatus("");
    try {
      await deleteMemory(memoryId);
      setMemories((current) => current.filter((item) => item.id !== memoryId));
      if (editingId === memoryId) setEditingId(null);
      setStatus("Memory deleted.");
    } catch (deleteError) {
      setError(`Could not delete Memory: ${deleteError.message}`);
    } finally {
      setSavingId(null);
    }
  };

  const removeAllMemories = async () => {
    if (!window.confirm("Delete all saved memories? This cannot be undone.")) return;
    setSavingId("all");
    setError("");
    setStatus("");
    try {
      const result = await clearMemories();
      setMemories([]);
      setEditingId(null);
      setDraft("");
      setStatus(`${result.deleted} ${result.deleted === 1 ? "memory" : "memories"} deleted.`);
    } catch (clearError) {
      setError(`Could not clear Memory: ${clearError.message}`);
    } finally {
      setSavingId(null);
    }
  };

  return (
    <section className="card app-panel manage-memory" aria-labelledby="manage-memory-title">
      <header className="manage-memory__header">
        <div>
          <h3 className="manage-memory__title" id="manage-memory-title">Your saved Memory</h3>
          <p className="manage-memory__description">
            When enabled, IA may save useful, lasting details from your messages and use relevant saved
            memories in future answers. Memory is separate from Notes and Conversation History. You can
            review, edit, or delete every saved item here.
          </p>
        </div>
        <button
          type="button"
          className="button-subtle"
          onClick={load}
          disabled={loading || savingId === "all"}
        >
          Refresh
        </button>
      </header>

      <label className="manage-memory__setting">
        <input
          type="checkbox"
          checked={memoryEnabled === true}
          onChange={toggleMemory}
          disabled={loading || savingSetting || memoryEnabled === null}
        />
        <span>
          <strong>{memoryEnabled === null ? "Memory status unavailable" : `Memory ${memoryEnabled ? "On" : "Off"}`}</strong>
          <span className="manage-memory__description">
            {memoryEnabled === null
              ? loading ? "Loading saved Memory setting…" : "Refresh to load your saved Memory setting."
              : savingSetting ? "Saving setting…" : "Controls both automatic saving and use of relevant memories in Ask."}
          </span>
        </span>
      </label>

      {error && <p className="out err" role="alert">{error}</p>}
      {status && <p className="manage-memory__status" role="status" aria-live="polite">{status}</p>}
      {loading ? (
        <p className="manage-memory__description" role="status">Loading saved memories…</p>
      ) : error ? null : memories.length === 0 ? (
        <p className="manage-memory__empty">
          No memories are saved. Turn Memory on, then tell IA something useful to remember in Ask.
        </p>
      ) : (
        <>
          <ul className="manage-memory__list">
            {memories.map((memory, index) => (
              <li className="manage-memory__item" key={memory.id}>
                {editingId === memory.id ? (
                  <div className="manage-memory__edit">
                    <label htmlFor={`memory-edit-${index}`}>Edit memory {index + 1}</label>
                    <textarea
                      id={`memory-edit-${index}`}
                      value={draft}
                      maxLength={500}
                      onChange={(event) => setDraft(event.target.value)}
                      disabled={savingId === memory.id}
                    />
                    <div className="manage-memory__actions">
                      <button
                        type="button"
                        className="button-subtle"
                        onClick={() => { setEditingId(null); setDraft(""); }}
                        disabled={savingId === memory.id}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="button-primary"
                        onClick={() => saveEdit(memory.id)}
                        disabled={savingId === memory.id || !draft.trim()}
                      >
                        {savingId === memory.id ? "Saving…" : "Save"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="manage-memory__text">{memory.text}</p>
                    <div className="manage-memory__actions">
                      <button type="button" className="button-subtle" onClick={() => startEditing(memory)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="button-subtle"
                        onClick={() => removeMemory(memory.id)}
                        disabled={savingId === memory.id || savingId === "all"}
                        aria-label={`Delete memory ${index + 1}`}
                      >
                        {savingId === memory.id ? "Deleting…" : "Delete"}
                      </button>
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="button-subtle manage-memory__clear"
            onClick={removeAllMemories}
            disabled={savingId !== null}
          >
            {savingId === "all" ? "Deleting…" : "Clear all memories"}
          </button>
        </>
      )}
    </section>
  );
}
