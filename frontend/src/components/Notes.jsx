// IA/frontend/src/components/Notes.jsx
// Notes: list with search; Select All / Unselect All; bulk delete. Click card → view/edit. Add note menu. Excludes _history. Auto-refresh when list visible (visibility + interval).

import { useState, useEffect, useRef } from "react";
import { listNotes, createNote, createNoteFromImages, updateNote, deleteNote, getNotesMeta } from "../api";

function loadNotesList(setData, setLoading, setError) {
  setError(null);
  setLoading(true);
  listNotes({ limit: 500 })
    .then((list) => setData(Array.isArray(list) ? list : []))
    .catch((err) => setError(err.message))
    .finally(() => setLoading(false));
}

/** Resolve tag to add from input: first autocomplete match if prefix matches, else trimmed input. */
function resolveTagToAdd(inputVal, suggestions) {
  const t = (inputVal || "").trim();
  if (!t) return "";
  const first = suggestions[0];
  if (first && first.toLowerCase().startsWith(t.toLowerCase())) return first;
  return t;
}

export default function Notes({ isSelectionMode = false, selectedIds = [], onSelect = null, onCloseSelection = null }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [addFormMode, setAddFormMode] = useState(null);
  const [noteTitle, setNoteTitle] = useState("");
  const [noteCategory, setNoteCategory] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [noteTagsArray, setNoteTagsArray] = useState([]);
  const [noteTagInput, setNoteTagInput] = useState("");
  const [noteLoading, setNoteLoading] = useState(false);
  const [noteResult, setNoteResult] = useState(null);
  const [imgTitle, setImgTitle] = useState("");
  const [imgCategory, setImgCategory] = useState("math");
  const [imgFiles, setImgFiles] = useState([]);
  const [imgLoading, setImgLoading] = useState(false);
  const [imgResult, setImgResult] = useState(null);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [viewingNoteId, setViewingNoteId] = useState(null);
  const [editTitle, setEditTitle] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editTagsArray, setEditTagsArray] = useState([]);
  const [editTagInput, setEditTagInput] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editResult, setEditResult] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNoteIds, setSelectedNoteIds] = useState(() => new Set(selectedIds));
  const [bulkDeleteLoading, setBulkDeleteLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [meta, setMeta] = useState({ categories: [], tags: [] });
  const [tagsDropdown, setTagsDropdown] = useState({ open: false, index: 0, filter: "", inputId: null });
  const [categoryDropdown, setCategoryDropdown] = useState({ open: false, index: 0, inputId: null });
  const addMenuRef = useRef(null);

  useEffect(() => {
    loadNotesList(setData, setLoading, setError);
  }, []);

  useEffect(() => {
    getNotesMeta()
      .then((m) => setMeta({ categories: m?.categories || [], tags: m?.tags || [] }))
      .catch(() => setMeta({ categories: [], tags: [] }));
  }, [data]);

  useEffect(() => {
    if (!addMenuOpen) return;
    const close = (e) => {
      if (addMenuRef.current && !addMenuRef.current.contains(e.target)) setAddMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [addMenuOpen]);

  const notesArray = Array.isArray(data) ? data : [];
  /** Exclude _history notes; History panel owns those. */
  const notesForDisplay = notesArray.filter((n) => (n.category || "") !== "_history");
  const isFormOpen = addFormMode != null;
  const viewingNote = viewingNoteId ? notesArray.find((n) => n.id === viewingNoteId) : null;
  const isViewingNote = viewingNote != null;

  useEffect(() => {
    if (viewingNote) {
      setEditTitle(viewingNote.title || "");
      setEditCategory(viewingNote.category || "");
      setEditContent(viewingNote.content || "");
      setEditTagsArray(Array.isArray(viewingNote.tags) ? [...viewingNote.tags] : []);
      setEditTagInput("");
      setEditResult(null);
    }
  }, [viewingNoteId, viewingNote?.id]);

  const openNoteForm = () => {
    setAddFormMode((m) => (m === "note" ? null : "note"));
    setNoteResult(null);
    setNoteCategory("");
    setNoteTagsArray([]);
    setNoteTagInput("");
  };
  const openFromImagesForm = () => {
    setAddFormMode("from-images");
    setImgResult(null);
    setAddMenuOpen(false);
  };

  const openTagsDropdown = (inputId, value) => {
    const val = inputId === "noteTags" ? noteTagInput : editTagInput;
    setTagsDropdown({ open: true, index: 0, filter: (val || "").trim(), inputId });
  };
  const closeTagsDropdown = () => {
    setTimeout(() => setTagsDropdown((p) => ({ ...p, open: false })), 150);
  };
  const addTagNewNote = (tag) => {
    const t = (tag || "").trim();
    if (!t || noteTagsArray.includes(t)) return;
    setNoteTagsArray([...noteTagsArray, t]);
    setNoteTagInput("");
  };
  const addTagEdit = (tag) => {
    const t = (tag || "").trim();
    if (!t || editTagsArray.includes(t)) return;
    setEditTagsArray([...editTagsArray, t]);
    setEditTagInput("");
  };
  const commitTagInputNewNote = () => {
    const val = noteTagInput;
    const sugs = filteredTagSuggestionsForNewNote;
    setTimeout(() => {
      const tag = resolveTagToAdd(val, sugs);
      if (tag) addTagNewNote(tag);
      setTagsDropdown((p) => ({ ...p, open: false }));
    }, 150);
  };
  const commitTagInputEdit = () => {
    const val = editTagInput;
    const sugs = filteredTagSuggestionsForEdit;
    setTimeout(() => {
      const tag = resolveTagToAdd(val, sugs);
      if (tag) addTagEdit(tag);
      setTagsDropdown((p) => ({ ...p, open: false }));
    }, 150);
  };
  const applyTagSuggestion = (tag) => {
    if (tagsDropdown.inputId === "noteTags") addTagNewNote(tag);
    else if (tagsDropdown.inputId === "editTags") addTagEdit(tag);
    setTagsDropdown((p) => ({ ...p, open: false }));
  };
  const filteredTagSuggestionsForNewNote = (meta.tags || [])
    .filter((t) => t.toLowerCase().startsWith((noteTagInput || "").trim().toLowerCase()))
    .slice(0, 10);
  const filteredTagSuggestionsForEdit = (meta.tags || [])
    .filter((t) => t.toLowerCase().startsWith((editTagInput || "").trim().toLowerCase()))
    .slice(0, 10);
  const filteredTagSuggestions =
    tagsDropdown.inputId === "noteTags" ? filteredTagSuggestionsForNewNote : filteredTagSuggestionsForEdit;

  const openCategoryDropdown = (inputId) => {
    setCategoryDropdown({ open: true, index: 0, inputId });
  };
  const applyCategorySuggestion = (cat) => {
    if (categoryDropdown.inputId === "noteCategory") setNoteCategory(cat);
    else if (categoryDropdown.inputId === "imgCategory") setImgCategory(cat);
    else if (categoryDropdown.inputId === "editCategory") setEditCategory(cat);
    setCategoryDropdown((p) => ({ ...p, open: false }));
  };
  const filteredCategorySuggestionsNewNote = (meta.categories || [])
    .filter((c) => c.toLowerCase().startsWith((noteCategory || "").trim().toLowerCase()))
    .slice(0, 10);
  const filteredCategorySuggestionsImg = (meta.categories || [])
    .filter((c) => c.toLowerCase().startsWith((imgCategory || "").trim().toLowerCase()))
    .slice(0, 10);
  const filteredCategorySuggestionsEdit = (meta.categories || [])
    .filter((c) => c.toLowerCase().startsWith((editCategory || "").trim().toLowerCase()))
    .slice(0, 10);
  const filteredCategorySuggestions =
    categoryDropdown.inputId === "noteCategory"
      ? filteredCategorySuggestionsNewNote
      : categoryDropdown.inputId === "imgCategory"
        ? filteredCategorySuggestionsImg
        : filteredCategorySuggestionsEdit;

  const handleCreateNote = async (e) => {
    e.preventDefault();
    const title = (noteTitle || "").trim();
    const category = (noteCategory || "").trim();
    const content = (noteContent || "").trim();
    if (!title || !category || !content) {
      setNoteResult({ error: "Title, category, and content are required." });
      return;
    }
    let tags = [...noteTagsArray];
    const pending = (noteTagInput || "").trim();
    if (pending && !tags.includes(pending)) tags.push(pending);
    setNoteResult(null);
    setNoteLoading(true);
    try {
      await createNote({ title, category, content, tags });
      setNoteTitle("");
      setNoteCategory("");
      setNoteContent("");
      setNoteTagsArray([]);
      setNoteTagInput("");
      setAddFormMode(null);
      loadNotesList(setData, setLoading, setError);
    } catch (err) {
      setNoteResult({ error: err.message });
    } finally {
      setNoteLoading(false);
    }
  };

  const handleFromImages = async (e) => {
    e.preventDefault();
    if (!imgFiles.length) {
      setImgResult({ error: "Select at least one image." });
      return;
    }
    setImgResult(null);
    setImgLoading(true);
    try {
      const form = new FormData();
      form.append("title", imgTitle || "From images");
      form.append("category", (imgCategory || "").trim() || "general");
      imgFiles.forEach((f) => form.append("files", f));
      const res = await createNoteFromImages(form);
      const note = res.note || res;
      const appended = res.appended === true;
      setImgResult({ success: true, note, appended });
      setImgFiles([]);
      if (!appended) setImgTitle("");
      loadNotesList(setData, setLoading, setError);
    } catch (err) {
      setImgResult({ error: err.message });
    } finally {
      setImgLoading(false);
    }
  };

  const showList = isSelectionMode || (!isFormOpen && !isViewingNote);
  const showBackToList = isFormOpen || isViewingNote;

  // Auto-refresh when list view is visible: on tab focus (visibility) and every 30s (best practice for list UIs).
  useEffect(() => {
    if (!showList) return;
    const refresh = () => loadNotesList(setData, setLoading, setError);
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

  const headerTitle = showList
    ? "Your notes"
    : addFormMode === "note"
      ? "New note"
      : addFormMode === "from-images"
        ? "Add note from images"
        : isViewingNote
          ? (editTitle || viewingNote?.title || "Untitled")
          : "Your notes";
  const searchLower = (searchQuery || "").trim().toLowerCase();
  const filteredNotes = searchLower
    ? notesForDisplay.filter((n) => {
        const m = (s) => (s || "").toLowerCase().includes(searchLower);
        return m(n.title) || m(n.category) || m(n.content) || (Array.isArray(n.tags) && n.tags.some(m));
      })
    : notesForDisplay;
  const closeViewOrForm = () => {
    setAddFormMode(null);
    setViewingNoteId(null);
    setNoteResult(null);
    setImgResult(null);
    setSelectedNoteIds(new Set());
  };

  const handleSelectAll = () => {
    setSelectedNoteIds(new Set(filteredNotes.map((n) => n.id)));
  };
  const handleUnselectAll = () => {
    setSelectedNoteIds(new Set());
  };
  const toggleNoteSelection = (id, e) => {
    e?.stopPropagation();
    setSelectedNoteIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const handleBulkDelete = async () => {
    if (selectedNoteIds.size === 0) return;
    setBulkDeleteLoading(true);
    setShowDeleteConfirm(false);
    try {
      for (const id of selectedNoteIds) {
        await deleteNote(id);
      }
      setSelectedNoteIds(new Set());
      loadNotesList(setData, setLoading, setError);
    } catch (err) {
      setError(err.message);
    } finally {
      setBulkDeleteLoading(false);
    }
  };

  const handleSaveNote = async (e) => {
    e.preventDefault();
    if (!viewingNoteId) return;
    const title = (editTitle || "").trim();
    const category = (editCategory || "").trim();
    const content = (editContent || "").trim();
    if (!title || !category || !content) {
      setEditResult({ error: "Title, category, and content are required." });
      return;
    }
    let tags = [...editTagsArray];
    const pending = (editTagInput || "").trim();
    if (pending && !tags.includes(pending)) tags.push(pending);
    setEditResult(null);
    setEditSaving(true);
    try {
      await updateNote(viewingNoteId, { title, category, content, tags });
      setEditResult({ success: true });
      loadNotesList(setData, setLoading, setError);
    } catch (err) {
      setEditResult({ error: err.message });
    } finally {
      setEditSaving(false);
    }
  };

  return (
    <section className="section section--notes">
      <div className="notes-list-header">
          {showList ? (
            <input
              type="search"
              className="notes-search-input"
              placeholder="Search notes…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search notes"
            />
          ) : (
            <span className="notes-list-title">{headerTitle}</span>
          )}
          <div className="notes-list-toolbar">
            {isSelectionMode && showList && (
              <div className="notes-toolbar-actions" role="group" aria-label="Select notes for chat context">
                <button type="button" className="notes-toolbar-btn" onClick={onCloseSelection}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="notes-toolbar-btn"
                  onClick={() => {
                    onSelect?.(notesForDisplay.filter((note) => selectedNoteIds.has(note.id)));
                    onCloseSelection?.();
                  }}
                  disabled={loading}
                >
                  Add selected ({selectedNoteIds.size})
                </button>
              </div>
            )}
            {!isSelectionMode && showList && filteredNotes.length > 0 && (
              <>
                {selectedNoteIds.size === 0 && (
                  <button type="button" className="notes-toolbar-btn" onClick={handleSelectAll}>
                    Select All
                  </button>
                )}
                {selectedNoteIds.size > 0 && selectedNoteIds.size < filteredNotes.length && (
                  <>
                    <button type="button" className="notes-toolbar-btn" onClick={handleSelectAll}>
                      Select All
                    </button>
                    <button type="button" className="notes-toolbar-btn" onClick={handleUnselectAll}>
                      Unselect All
                    </button>
                  </>
                )}
                {selectedNoteIds.size === filteredNotes.length && filteredNotes.length > 0 && (
                  <button type="button" className="notes-toolbar-btn" onClick={handleUnselectAll}>
                    Unselect All
                  </button>
                )}
              </>
            )}
            {!isSelectionMode && <div className="notes-add-toggle" role="group" aria-label={showBackToList ? "Back to list" : selectedNoteIds.size > 0 ? "Delete selected" : "Add note"}>
              {showBackToList ? (
                <div className="notes-toolbar-actions">
                  <button
                    type="button"
                    className="notes-back-btn"
                    onClick={closeViewOrForm}
                    aria-label="Back to list"
                    title="Back to list"
                  >
                    Back to list
                  </button>
                  {isViewingNote && (
                    <button
                      type="submit"
                      form="notes-edit-form"
                      className="notes-toolbar-btn"
                      disabled={editSaving || !editTitle.trim() || !editCategory.trim() || !editContent.trim()}
                      aria-label="Save note"
                      title="Save changes"
                    >
                      {editSaving ? "Saving…" : "Save"}
                    </button>
                  )}
                  {addFormMode === "note" && (
                    <button
                      type="submit"
                      form="notes-new-note-form"
                      className="notes-toolbar-btn"
                      disabled={noteLoading || !noteTitle.trim() || !noteCategory.trim() || !noteContent.trim()}
                      aria-label="Add note"
                      title="Add note"
                    >
                      {noteLoading ? "…" : "Add note"}
                    </button>
                  )}
                  {addFormMode === "from-images" && (
                    <button
                      type="submit"
                      form="notes-from-images-form"
                      className="notes-toolbar-btn"
                      disabled={imgLoading || !imgFiles.length}
                      aria-label="Add note from images"
                      title="Add note from images"
                    >
                      {imgLoading ? "…" : "Add from images"}
                    </button>
                  )}
                </div>
              ) : showList && selectedNoteIds.size > 0 ? (
                <button
                  type="button"
                  className="notes-back-btn notes-toolbar-btn--danger"
                  onClick={() => setShowDeleteConfirm(true)}
                  disabled={bulkDeleteLoading}
                  aria-label={`Delete ${selectedNoteIds.size} selected`}
                  title="Delete selected notes"
                >
                  {bulkDeleteLoading ? "Deleting…" : `Delete (${selectedNoteIds.size})`}
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    className="notes-list-add-btn"
                    onClick={openNoteForm}
                    aria-expanded={false}
                  >
                    Add note
                  </button>
                  <div className="notes-add-dropdown" ref={addMenuRef}>
                    <button
                      type="button"
                      className="notes-add-chevron"
                      onClick={() => setAddMenuOpen((o) => !o)}
                      aria-expanded={addMenuOpen}
                      aria-haspopup="true"
                      aria-label="More add options"
                      title="More add options"
                    >
                      <span className="notes-add-chevron__icon" aria-hidden>▼</span>
                    </button>
                    {addMenuOpen && (
                      <div className="notes-add-menu" role="menu">
                        <button
                          type="button"
                          role="menuitem"
                          className="notes-add-menu__item"
                          onClick={openFromImagesForm}
                        >
                          Add from images
                        </button>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>}
          </div>
        </div>

        {showDeleteConfirm && selectedNoteIds.size > 0 && (
          <div className="notes-delete-confirm" role="dialog" aria-modal="true" aria-labelledby="notes-delete-confirm-title">
            <div className="notes-delete-confirm__backdrop" onClick={() => setShowDeleteConfirm(false)} aria-hidden="true" />
            <div className="notes-delete-confirm__box">
              <p id="notes-delete-confirm-title" className="notes-delete-confirm__title">
                Delete {selectedNoteIds.size} note{selectedNoteIds.size !== 1 ? "s" : ""}?
              </p>
              <p className="notes-delete-confirm__desc">This cannot be undone.</p>
              <div className="notes-delete-confirm__actions">
                <button
                  type="button"
                  className="notes-toolbar-btn"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={bulkDeleteLoading}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="notes-toolbar-btn notes-toolbar-btn--danger"
                  onClick={handleBulkDelete}
                  disabled={bulkDeleteLoading}
                >
                  {bulkDeleteLoading ? "Deleting…" : "Delete"}
                </button>
              </div>
            </div>
          </div>
        )}

        {addFormMode === "note" && (
          <div className="notes-add-panel">
            <form id="notes-new-note-form" onSubmit={handleCreateNote} className={`form--compact ${noteLoading ? "loading" : ""}`}>
              <label htmlFor="noteTitle">Title</label>
              <input
                id="noteTitle"
                type="text"
                placeholder="e.g. Meeting notes"
                value={noteTitle}
                onChange={(e) => setNoteTitle(e.target.value)}
                disabled={noteLoading}
              />
              <label htmlFor="noteCategory">Category</label>
              <div className="notes-category-wrap">
                <input
                  id="noteCategory"
                  type="text"
                  placeholder="e.g. work"
                  value={noteCategory}
                  onChange={(e) => {
                    setNoteCategory(e.target.value);
                    setCategoryDropdown((p) => ({ ...p, open: true, index: 0, inputId: "noteCategory" }));
                  }}
                  onFocus={() => openCategoryDropdown("noteCategory")}
                  onBlur={() => setTimeout(() => setCategoryDropdown((p) => ({ ...p, open: false })), 150)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setCategoryDropdown((p) => ({ ...p, open: false }));
                    if (e.key === "Enter" && categoryDropdown.open && categoryDropdown.inputId === "noteCategory" && filteredCategorySuggestionsNewNote[categoryDropdown.index]) {
                      e.preventDefault();
                      applyCategorySuggestion(filteredCategorySuggestionsNewNote[categoryDropdown.index]);
                    }
                    if (!categoryDropdown.open || categoryDropdown.inputId !== "noteCategory") return;
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setCategoryDropdown((p) => ({ ...p, index: Math.min(p.index + 1, filteredCategorySuggestionsNewNote.length - 1) }));
                    }
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setCategoryDropdown((p) => ({ ...p, index: Math.max(0, p.index - 1) }));
                    }
                  }}
                  disabled={noteLoading}
                  autoComplete="off"
                />
                {categoryDropdown.open && categoryDropdown.inputId === "noteCategory" && filteredCategorySuggestionsNewNote.length > 0 && (
                  <ul className="notes-category-suggestions" role="listbox">
                    {filteredCategorySuggestionsNewNote.map((c, i) => (
                      <li
                        key={c}
                        role="option"
                        aria-selected={i === categoryDropdown.index}
                        className={i === categoryDropdown.index ? "notes-category-suggestions__item is-selected" : "notes-category-suggestions__item"}
                        onMouseDown={(e) => { e.preventDefault(); applyCategorySuggestion(c); }}
                      >
                        {c}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <label htmlFor="noteContent">Content</label>
              <textarea
                id="noteContent"
                placeholder="Note content…"
                value={noteContent}
                onChange={(e) => setNoteContent(e.target.value)}
                disabled={noteLoading}
                rows={4}
              />
              <label htmlFor="noteTags">Tags</label>
              <div className="notes-tags-wrap">
                <div className="notes-tags-chips">
                  {noteTagsArray.map((t, i) => (
                    <span key={`${t}-${i}`} className="notes-tag-chip">
                      <span className="notes-tag-chip__label">{t}</span>
                      <button type="button" className="notes-tag-chip__remove" aria-label={`Remove ${t}`} onClick={() => setNoteTagsArray(noteTagsArray.filter((_, j) => j !== i))}>×</button>
                    </span>
                  ))}
                </div>
                <input
                  id="noteTags"
                  type="text"
                  placeholder="Type a tag and press Enter or blur"
                  value={noteTagInput}
                  onChange={(e) => setNoteTagInput(e.target.value)}
                  onFocus={() => openTagsDropdown("noteTags", noteTagInput)}
                  onBlur={commitTagInputNewNote}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setTagsDropdown((p) => ({ ...p, open: false }));
                    if (e.key === "Enter") {
                      e.preventDefault();
                      if (tagsDropdown.open && filteredTagSuggestions[tagsDropdown.index]) {
                        applyTagSuggestion(filteredTagSuggestions[tagsDropdown.index]);
                      } else {
                        commitTagInputNewNote();
                      }
                    }
                    if (!tagsDropdown.open || tagsDropdown.inputId !== "noteTags") return;
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setTagsDropdown((p) => ({ ...p, index: Math.min(p.index + 1, filteredTagSuggestions.length - 1) }));
                    }
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setTagsDropdown((p) => ({ ...p, index: Math.max(0, p.index - 1) }));
                    }
                  }}
                  disabled={noteLoading}
                  autoComplete="off"
                />
                {tagsDropdown.open && tagsDropdown.inputId === "noteTags" && filteredTagSuggestions.length > 0 && (
                  <ul className="notes-tags-suggestions" role="listbox">
                    {filteredTagSuggestions.map((t, i) => (
                      <li
                        key={t}
                        role="option"
                        aria-selected={i === tagsDropdown.index}
                        className={i === tagsDropdown.index ? "notes-tags-suggestions__item is-selected" : "notes-tags-suggestions__item"}
                        onMouseDown={(e) => { e.preventDefault(); applyTagSuggestion(t); }}
                      >
                        {t}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </form>
            {noteResult && (
              <div className={`out out--compact ${noteResult.error ? "err" : "success-msg"}`}>
                {noteResult.error || "Note added."}
              </div>
            )}
          </div>
        )}

        {addFormMode === "from-images" && (
          <div className="notes-add-panel">
            <form id="notes-from-images-form" onSubmit={handleFromImages} className={`form--compact ${imgLoading ? "loading" : ""}`}>
              <label htmlFor="imgTitle">Title</label>
              <input
                id="imgTitle"
                type="text"
                placeholder="e.g. Math"
                value={imgTitle}
                onChange={(e) => setImgTitle(e.target.value)}
                disabled={imgLoading}
              />
              <label htmlFor="imgCategory">Category</label>
              <div className="notes-category-wrap">
                <input
                  id="imgCategory"
                  type="text"
                  placeholder="e.g. math"
                  value={imgCategory}
                  onChange={(e) => {
                    setImgCategory(e.target.value);
                    setCategoryDropdown((p) => ({ ...p, open: true, index: 0, inputId: "imgCategory" }));
                  }}
                  onFocus={() => openCategoryDropdown("imgCategory")}
                  onBlur={() => setTimeout(() => setCategoryDropdown((p) => ({ ...p, open: false })), 150)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setCategoryDropdown((p) => ({ ...p, open: false }));
                    if (e.key === "Enter" && categoryDropdown.open && categoryDropdown.inputId === "imgCategory" && filteredCategorySuggestionsImg[categoryDropdown.index]) {
                      e.preventDefault();
                      applyCategorySuggestion(filteredCategorySuggestionsImg[categoryDropdown.index]);
                    }
                    if (!categoryDropdown.open || categoryDropdown.inputId !== "imgCategory") return;
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setCategoryDropdown((p) => ({ ...p, index: Math.min(p.index + 1, filteredCategorySuggestionsImg.length - 1) }));
                    }
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setCategoryDropdown((p) => ({ ...p, index: Math.max(0, p.index - 1) }));
                    }
                  }}
                  disabled={imgLoading}
                  autoComplete="off"
                />
                {categoryDropdown.open && categoryDropdown.inputId === "imgCategory" && filteredCategorySuggestionsImg.length > 0 && (
                  <ul className="notes-category-suggestions" role="listbox">
                    {filteredCategorySuggestionsImg.map((c, i) => (
                      <li
                        key={c}
                        role="option"
                        aria-selected={i === categoryDropdown.index}
                        className={i === categoryDropdown.index ? "notes-category-suggestions__item is-selected" : "notes-category-suggestions__item"}
                        onMouseDown={(e) => { e.preventDefault(); applyCategorySuggestion(c); }}
                      >
                        {c}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <label htmlFor="imgFiles">Images</label>
              <input
                id="imgFiles"
                type="file"
                accept="image/*"
                multiple
                onChange={(e) => setImgFiles(Array.from(e.target.files || []))}
                disabled={imgLoading}
              />
            </form>
            {imgResult && (
              <div className={`out out--compact ${imgResult.error ? "err" : "success-msg"}`}>
                {imgResult.error ||
                  (imgResult.success &&
                    (imgResult.appended
                      ? `Added to: ${imgResult.note?.title}`
                      : `Created: ${imgResult.note?.title}`))}
              </div>
            )}
          </div>
        )}

        {isViewingNote && (
          <div className="notes-add-panel">
            <form id="notes-edit-form" onSubmit={handleSaveNote} className={`form--compact ${editSaving ? "loading" : ""}`}>
              <label htmlFor="editTitle">Title</label>
              <input
                id="editTitle"
                type="text"
                placeholder="e.g. Meeting notes"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                disabled={editSaving}
              />
              <label htmlFor="editCategory">Category</label>
              <div className="notes-category-wrap">
                <input
                  id="editCategory"
                  type="text"
                  placeholder="e.g. work"
                  value={editCategory}
                  onChange={(e) => {
                    setEditCategory(e.target.value);
                    setCategoryDropdown((p) => ({ ...p, open: true, index: 0, inputId: "editCategory" }));
                  }}
                  onFocus={() => openCategoryDropdown("editCategory")}
                  onBlur={() => setTimeout(() => setCategoryDropdown((p) => ({ ...p, open: false })), 150)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setCategoryDropdown((p) => ({ ...p, open: false }));
                    if (e.key === "Enter" && categoryDropdown.open && categoryDropdown.inputId === "editCategory" && filteredCategorySuggestionsEdit[categoryDropdown.index]) {
                      e.preventDefault();
                      applyCategorySuggestion(filteredCategorySuggestionsEdit[categoryDropdown.index]);
                    }
                    if (!categoryDropdown.open || categoryDropdown.inputId !== "editCategory") return;
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setCategoryDropdown((p) => ({ ...p, index: Math.min(p.index + 1, filteredCategorySuggestionsEdit.length - 1) }));
                    }
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setCategoryDropdown((p) => ({ ...p, index: Math.max(0, p.index - 1) }));
                    }
                  }}
                  disabled={editSaving}
                  autoComplete="off"
                />
                {categoryDropdown.open && categoryDropdown.inputId === "editCategory" && filteredCategorySuggestionsEdit.length > 0 && (
                  <ul className="notes-category-suggestions" role="listbox">
                    {filteredCategorySuggestionsEdit.map((c, i) => (
                      <li
                        key={c}
                        role="option"
                        aria-selected={i === categoryDropdown.index}
                        className={i === categoryDropdown.index ? "notes-category-suggestions__item is-selected" : "notes-category-suggestions__item"}
                        onMouseDown={(e) => { e.preventDefault(); applyCategorySuggestion(c); }}
                      >
                        {c}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <label htmlFor="editContent">Content</label>
              <textarea
                id="editContent"
                placeholder="Note content…"
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                disabled={editSaving}
                rows={4}
              />
              <label htmlFor="editTags">Tags</label>
              <div className="notes-tags-wrap">
                <div className="notes-tags-chips">
                  {editTagsArray.map((t, i) => (
                    <span key={`${t}-${i}`} className="notes-tag-chip">
                      <span className="notes-tag-chip__label">{t}</span>
                      <button type="button" className="notes-tag-chip__remove" aria-label={`Remove ${t}`} onClick={() => setEditTagsArray(editTagsArray.filter((_, j) => j !== i))}>×</button>
                    </span>
                  ))}
                </div>
                <input
                  id="editTags"
                  type="text"
                  placeholder="Type a tag and press Enter or blur"
                  value={editTagInput}
                  onChange={(e) => setEditTagInput(e.target.value)}
                  onFocus={() => openTagsDropdown("editTags", editTagInput)}
                  onBlur={commitTagInputEdit}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setTagsDropdown((p) => ({ ...p, open: false }));
                    if (e.key === "Enter") {
                      e.preventDefault();
                      if (tagsDropdown.open && filteredTagSuggestions[tagsDropdown.index]) {
                        applyTagSuggestion(filteredTagSuggestions[tagsDropdown.index]);
                      } else {
                        commitTagInputEdit();
                      }
                    }
                    if (!tagsDropdown.open || tagsDropdown.inputId !== "editTags") return;
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setTagsDropdown((p) => ({ ...p, index: Math.min(p.index + 1, filteredTagSuggestions.length - 1) }));
                    }
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setTagsDropdown((p) => ({ ...p, index: Math.max(0, p.index - 1) }));
                    }
                  }}
                  disabled={editSaving}
                  autoComplete="off"
                />
                {tagsDropdown.open && tagsDropdown.inputId === "editTags" && filteredTagSuggestions.length > 0 && (
                  <ul className="notes-tags-suggestions" role="listbox">
                    {filteredTagSuggestions.map((t, i) => (
                      <li
                        key={t}
                        role="option"
                        aria-selected={i === tagsDropdown.index}
                        className={i === tagsDropdown.index ? "notes-tags-suggestions__item is-selected" : "notes-tags-suggestions__item"}
                        onMouseDown={(e) => { e.preventDefault(); applyTagSuggestion(t); }}
                      >
                        {t}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </form>
            {editResult && (
              <div className={`out out--compact ${editResult.error ? "err" : "success-msg"}`}>
                {editResult.error || "Saved."}
              </div>
            )}
          </div>
        )}

        {showList && (
          <>
            {loading && data === null && (
              <p className="notes-list-empty">Loading…</p>
            )}
            {!loading && notesForDisplay.length === 0 && data !== null && (
              <p className="notes-list-empty">{isSelectionMode ? "No notes yet." : "No notes yet. Click “Add note” or ▼ to add one."}</p>
            )}
            {notesForDisplay.length > 0 && (
              <ul className="notes-list">
                {filteredNotes.slice(0, 100).map((n) => (
                  <li
                    key={n.id}
                    className={`note-card ${selectedNoteIds.has(n.id) ? "note-card--selected" : ""}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      if (isSelectionMode) {
                        toggleNoteSelection(n.id);
                      } else {
                        setViewingNoteId(n.id);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        if (isSelectionMode) {
                          toggleNoteSelection(n.id);
                        } else {
                          setViewingNoteId(n.id);
                        }
                      }
                    }}
                    aria-label={`${isSelectionMode ? "Select" : "View"} note: ${n.title || "Untitled"}`}
                    aria-pressed={isSelectionMode ? selectedNoteIds.has(n.id) : undefined}
                  >
                    <input
                      type="checkbox"
                      className="note-card__checkbox"
                      checked={selectedNoteIds.has(n.id)}
                      onChange={(e) => toggleNoteSelection(n.id, e)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Select ${n.title || "Untitled"}`}
                    />
                    <div className="note-card__content">
                      <div className="note-card__row">
                        <span className="note-card__label" aria-hidden="true">Title</span>
                        <span className="note-card__title">{n.title || "Untitled"}</span>
                      </div>
                      <div className="note-card__row note-card__row--meta">
                        <span className="note-card__pair">
                          <span className="note-card__label" aria-hidden="true">Category</span>
                          <span className="note-card__meta">{(n.category || "").trim() || "—"}</span>
                        </span>
                        <span className="note-card__pair">
                          <span className="note-card__label" aria-hidden="true">Tags</span>
                          <span className="note-card__meta">{Array.isArray(n.tags) && n.tags.length ? n.tags.join(", ") : "—"}</span>
                        </span>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {filteredNotes.length > 100 && (
              <p className="notes-list-more">Showing first 100.</p>
            )}
            {notesForDisplay.length > 0 && filteredNotes.length === 0 && (
              <p className="notes-list-empty">No notes match your search.</p>
            )}
          </>
        )}

      {error && <div className="out out--compact err">{error}</div>}
    </section>
  );
}
