// IA/frontend/src/components/History.jsx
// Conversation histories CRUD: notes with category _history. List, edit title, delete. Same list UX as Notes.

import { useState, useEffect } from "react";
import { listHistories, createHistory, updateNote, deleteNote } from "../api";

function parseMessageCount(content) {
  if (!content || !String(content).trim()) return 0;
  try {
    const arr = JSON.parse(content);
    return Array.isArray(arr) ? arr.length : 0;
  } catch {
    return 0;
  }
}

function loadHistoryList(setList, setLoading, setError) {
  setError(null);
  setLoading(true);
  return listHistories()
    .then((data) => setList(Array.isArray(data) ? data : []))
    .catch((err) => setError(err.message))
    .finally(() => setLoading(false));
}

export default function History({ isSelectionMode = false, onSelect = null, onCloseSelection = null }) {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [viewingId, setViewingId] = useState(null);
  const [editTitle, setEditTitle] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editResult, setEditResult] = useState(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkDeleteConfirm, setBulkDeleteConfirm] = useState(false);
  const [bulkDeleteLoading, setBulkDeleteLoading] = useState(false);

  useEffect(() => {
    loadHistoryList(setList, setLoading, setError);
  }, []);

  // Auto-refresh when list is visible (same pattern as Notes).
  const showList = isSelectionMode || !viewingId;
  useEffect(() => {
    if (!showList) return;
    const refresh = () => loadHistoryList(setList, setLoading, setError);
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    const interval = setInterval(refresh, 30000);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      clearInterval(interval);
    };
  }, [showList]);

  const viewing = viewingId ? list.find((h) => h.id === viewingId) : null;
  useEffect(() => {
    if (viewing) {
      setEditTitle(viewing.title || "Untitled");
      setEditResult(null);
    }
  }, [viewingId, viewing?.id]);

  const searchLower = (searchQuery || "").trim().toLowerCase();
  const filteredList = searchLower
    ? list.filter((h) => (h.title || "").toLowerCase().includes(searchLower))
    : list;

  const handleNew = async () => {
    setCreating(true);
    setError(null);
    try {
      const created = await createHistory("New conversation");
      setList((prev) => [...prev, created]);
      setViewingId(created.id);
      await loadHistoryList(setList, setLoading, setError);
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleSaveTitle = async (e) => {
    e.preventDefault();
    if (!viewingId || !editTitle.trim()) return;
    setEditResult(null);
    setEditSaving(true);
    try {
      await updateNote(viewingId, { title: editTitle.trim() });
      setEditResult({ success: true });
      loadHistoryList(setList, setLoading, setError);
    } catch (err) {
      setEditResult({ error: err.message });
    } finally {
      setEditSaving(false);
    }
  };

  const handleDeleteOne = async (id) => {
    if (!id) return;
    setDeleteLoading(true);
    setDeleteConfirmId(null);
    try {
      await deleteNote(id);
      if (viewingId === id) setViewingId(null);
      setList((prev) => prev.filter((h) => h.id !== id));
    } catch (e) {
      setError(e.message);
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    setBulkDeleteLoading(true);
    setBulkDeleteConfirm(false);
    try {
      for (const id of selectedIds) {
        await deleteNote(id);
      }
      setSelectedIds(new Set());
      if (viewingId && selectedIds.has(viewingId)) setViewingId(null);
      loadHistoryList(setList, setLoading, setError);
    } catch (e) {
      setError(e.message);
    } finally {
      setBulkDeleteLoading(false);
    }
  };

  const toggleSelect = (id, e) => {
    e.stopPropagation();
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const selectAll = () => setSelectedIds(new Set(filteredList.map((h) => h.id)));
  const unselectAll = () => setSelectedIds(new Set());

  return (
    <section className="section section--history">
      <div className="notes-list-header">
        {showList ? (
          <input
            type="search"
            className="notes-search-input"
            placeholder="Search conversations…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search conversations"
          />
        ) : (
          <span className="notes-list-title">{viewing ? `Conversation: ${editTitle || "Untitled"}` : "Conversations"}</span>
        )}
        <div className="notes-list-toolbar">
          {!isSelectionMode && showList && filteredList.length > 0 && (
            <>
              {selectedIds.size === 0 && (
                <button type="button" className="notes-toolbar-btn" onClick={selectAll}>
                  Select All
                </button>
              )}
              {selectedIds.size > 0 && selectedIds.size < filteredList.length && (
                <>
                  <button type="button" className="notes-toolbar-btn" onClick={selectAll}>Select All</button>
                  <button type="button" className="notes-toolbar-btn" onClick={unselectAll}>Unselect All</button>
                </>
              )}
              {selectedIds.size === filteredList.length && filteredList.length > 0 && (
                <button type="button" className="notes-toolbar-btn" onClick={unselectAll}>Unselect All</button>
              )}
            </>
          )}
          {!isSelectionMode && <div className="notes-add-toggle" role="group">
            {showList && selectedIds.size > 0 ? (
              <button
                type="button"
                className="notes-back-btn notes-toolbar-btn--danger"
                onClick={() => setBulkDeleteConfirm(true)}
                disabled={bulkDeleteLoading}
              >
                {bulkDeleteLoading ? "Deleting…" : `Delete (${selectedIds.size})`}
              </button>
            ) : showList ? (
              <button
                type="button"
                className="notes-list-add-btn"
                onClick={handleNew}
                disabled={creating}
              >
                {creating ? "…" : "New conversation"}
              </button>
            ) : (
              <div className="notes-toolbar-actions">
                <button
                  type="button"
                  className="notes-back-btn"
                  onClick={() => { setViewingId(null); setEditResult(null); }}
                  aria-label="Back to list"
                >
                  Back to list
                </button>
                <button
                  type="submit"
                  form="history-edit-form"
                  className="notes-toolbar-btn"
                  disabled={editSaving || !editTitle.trim()}
                >
                  {editSaving ? "Saving…" : "Save"}
                </button>
                <button
                  type="button"
                  className="notes-toolbar-btn notes-toolbar-btn--danger"
                  onClick={() => setDeleteConfirmId(viewingId)}
                  aria-label="Delete conversation"
                >
                  Delete
                </button>
              </div>
            )}
          </div>}
        </div>
      </div>

      {showList && (
        <>
          {loading && list.length === 0 && <p className="notes-list-empty">Loading…</p>}
          {!loading && list.length === 0 && (
            <p className="notes-list-empty">No conversations yet. Create one, then select it in Ask to continue that chat.</p>
          )}
          {list.length > 0 && (
            <ul className="notes-list">
              {filteredList.map((h) => (
                <li
                  key={h.id}
                  className={`note-card ${!isSelectionMode && selectedIds.has(h.id) ? "note-card--selected" : ""} ${!isSelectionMode && viewingId === h.id ? "note-card--active" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    if (isSelectionMode && onSelect) {
                      onSelect(h.id);
                      onCloseSelection?.();
                    } else {
                      setViewingId(h.id);
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      if (isSelectionMode && onSelect) {
                        onSelect(h.id);
                        onCloseSelection?.();
                      } else {
                        setViewingId(h.id);
                      }
                    }
                  }}
                  aria-label={`${isSelectionMode ? "Select" : "View"} conversation: ${h.title || "Untitled"}`}
                >
                  {!isSelectionMode && (
                    <input
                      type="checkbox"
                      className="note-card__checkbox"
                      checked={selectedIds.has(h.id)}
                      onChange={(e) => toggleSelect(h.id, e)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Select ${h.title || "Untitled"}`}
                    />
                  )}
                    <div className="note-card__content">
                      <div className="note-card__row">
                        <span className="note-card__label" aria-hidden="true">Title</span>
                        <span className="note-card__title">{h.title || "Untitled"}</span>
                      </div>
                      <div className="note-card__row note-card__row--meta">
                        <span className="note-card__pair">
                          <span className="note-card__label" aria-hidden="true">Messages</span>
                          <span className="note-card__meta">{parseMessageCount(h.content)}</span>
                        </span>
                        <span className="note-card__pair">
                          <span className="note-card__label" aria-hidden="true">Updated</span>
                          <span className="note-card__meta">{h.updated_at ? new Date(h.updated_at).toLocaleDateString() : "—"}</span>
                        </span>
                      </div>
                    </div>
                </li>
              ))}
            </ul>
          )}
          {filteredList.length === 0 && list.length > 0 && (
            <p className="notes-list-empty">No conversations match your search.</p>
          )}
        </>
      )}

      {!isSelectionMode && viewing && !showList && (
        <div className="notes-add-panel">
          <form id="history-edit-form" onSubmit={handleSaveTitle} className={`form--compact ${editSaving ? "loading" : ""}`}>
            <label htmlFor="historyEditTitle">Title</label>
            <input
              id="historyEditTitle"
              type="text"
              placeholder="Conversation title"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              disabled={editSaving}
            />
          </form>
          {editResult && (
            <div className={`out out--compact ${editResult.error ? "err" : "success-msg"}`}>
              {editResult.error || "Saved."}
            </div>
          )}
        </div>
      )}

      {!isSelectionMode && deleteConfirmId && (
        <div className="notes-delete-confirm" role="dialog" aria-modal="true">
          <div className="notes-delete-confirm__backdrop" onClick={() => setDeleteConfirmId(null)} aria-hidden />
          <div className="notes-delete-confirm__box">
            <p className="notes-delete-confirm__title">Delete this conversation?</p>
            <p className="notes-delete-confirm__desc">Messages cannot be recovered.</p>
            <div className="notes-delete-confirm__actions">
              <button type="button" className="notes-toolbar-btn" onClick={() => setDeleteConfirmId(null)} disabled={deleteLoading}>
                Cancel
              </button>
              <button
                type="button"
                className="notes-toolbar-btn notes-toolbar-btn--danger"
                onClick={() => handleDeleteOne(deleteConfirmId)}
                disabled={deleteLoading}
              >
                {deleteLoading ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {!isSelectionMode && bulkDeleteConfirm && selectedIds.size > 0 && (
        <div className="notes-delete-confirm" role="dialog" aria-modal="true">
          <div className="notes-delete-confirm__backdrop" onClick={() => setBulkDeleteConfirm(false)} aria-hidden />
          <div className="notes-delete-confirm__box">
            <p className="notes-delete-confirm__title">Delete {selectedIds.size} conversation{selectedIds.size !== 1 ? "s" : ""}?</p>
            <p className="notes-delete-confirm__desc">This cannot be undone.</p>
            <div className="notes-delete-confirm__actions">
              <button type="button" className="notes-toolbar-btn" onClick={() => setBulkDeleteConfirm(false)} disabled={bulkDeleteLoading}>Cancel</button>
              <button type="button" className="notes-toolbar-btn notes-toolbar-btn--danger" onClick={handleBulkDelete} disabled={bulkDeleteLoading}>
                {bulkDeleteLoading ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {error && <div className="out out--compact err">{error}</div>}
    </section>
  );
}
