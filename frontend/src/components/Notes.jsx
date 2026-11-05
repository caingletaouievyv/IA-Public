// IA/frontend/src/components/Notes.jsx
// Notes: list with search; Select All / Unselect All; bulk delete. Click card → view/edit. Single Add note form (optional PDF, PPTX, or screenshot text import). Excludes _history and flashcard decks. Auto-refresh when list visible (visibility + interval).

import { useState, useEffect, useRef } from "react";
import { listNotes, createNote, extractPdfText, extractPptxText, extractImageText, updateNote, deleteNote, getNotesMeta } from "../api";
import { isManageNotesExcludedCategory } from "../noteCategories.js";
import AskOverlay from "./AskOverlay.jsx";

/** Must match backend NOTES_MAX_CONTENT_CHARS (POST /notes/ and PDF extract). */
const NOTE_MAX_CONTENT_CHARS = 512_000;

function NotesFieldHint({ show, id, children }) {
  if (!show || !children) return null;
  return (
    <p id={id} className="flashcards-help" role="status">
      {children}
    </p>
  );
}

/** One-line reason the primary toolbar action is disabled (avoids repeating field-level hints). */
function missingForActionHint(parts, { minCount = 2 } = {}) {
  const need = parts.filter((p) => p.missing).map((p) => p.label);
  if (need.length < minCount) return null;
  if (need.length === 1) return `Add ${need[0]} to continue.`;
  return `Add ${need.slice(0, -1).join(", ")} and ${need.at(-1)} to continue.`;
}

function NotesToolbarHint({ text }) {
  if (!text) return null;
  return (
    <span className="flashcards-help" role="status">
      {text}
    </span>
  );
}

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

export default function Notes({
  isSelectionMode = false,
  selectedIds = [],
  onSelect = null,
  onCloseSelection = null,
  focusNoteId = null,
  onFocusNoteHandled = null,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [addFormMode, setAddFormMode] = useState(null);
  const [noteTitle, setNoteTitle] = useState("");
  const [noteCategory, setNoteCategory] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [noteTagsArray, setNoteTagsArray] = useState([]);
  const [noteTagInput, setNoteTagInput] = useState("");
  const [noteLoading, setNoteLoading] = useState(false);
  const [noteResult, setNoteResult] = useState(null);
  const [showPdfImportDialog, setShowPdfImportDialog] = useState(false);
  const [pendingPdfFile, setPendingPdfFile] = useState(null);
  const [pdfImportDialogError, setPdfImportDialogError] = useState(null);
  const [showPptxImportDialog, setShowPptxImportDialog] = useState(false);
  const [pendingPptxFile, setPendingPptxFile] = useState(null);
  const [pptxImportDialogError, setPptxImportDialogError] = useState(null);
  const [showImageImportDialog, setShowImageImportDialog] = useState(false);
  const [pendingImageFiles, setPendingImageFiles] = useState([]);
  const [imageImportDialogError, setImageImportDialogError] = useState(null);
  const [contentImportMessage, setContentImportMessage] = useState(null);
  const [importLoading, setImportLoading] = useState(false);
  const pdfFileInputRef = useRef(null);
  const pptxFileInputRef = useRef(null);
  const imageFileInputRef = useRef(null);
  const [focusNoteMissMessage, setFocusNoteMissMessage] = useState(null);
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

  useEffect(() => {
    loadNotesList(setData, setLoading, setError);
  }, []);

  useEffect(() => {
    if (!focusNoteId) return;
    loadNotesList(setData, setLoading, setError);
  }, [focusNoteId]);

  useEffect(() => {
    if (!focusNoteId || data === null || loading) return;
    const match = (Array.isArray(data) ? data : []).find((note) => note.id === focusNoteId);
    if (!match) {
      setFocusNoteMissMessage("That note could not be found. It may have been deleted or is not in your list.");
      onFocusNoteHandled?.();
      return;
    }
    setFocusNoteMissMessage(null);
    setViewingNoteId(focusNoteId);
    setAddFormMode(null);
    onFocusNoteHandled?.();
    requestAnimationFrame(() => {
      document.getElementById(`note-card-${focusNoteId}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }, [focusNoteId, data, loading, onFocusNoteHandled]);

  useEffect(() => {
    if (isSelectionMode) setSelectedNoteIds(new Set(selectedIds));
  }, [isSelectionMode]);

  useEffect(() => {
    getNotesMeta()
      .then((m) => setMeta({ categories: m?.categories || [], tags: m?.tags || [] }))
      .catch(() => setMeta({ categories: [], tags: [] }));
  }, [data]);

  const notesArray = Array.isArray(data) ? data : [];
  /** Exclude internal categories (_history, flashcard decks); History / Flashcards own those. */
  const notesForDisplay = notesArray.filter((n) => !isManageNotesExcludedCategory(n.category));
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
    setContentImportMessage(null);
    setPdfImportDialogError(null);
    setPptxImportDialogError(null);
    setImageImportDialogError(null);
    setShowPdfImportDialog(false);
    setShowPptxImportDialog(false);
    setShowImageImportDialog(false);
    setNoteCategory("");
    setNoteTagsArray([]);
    setNoteTagInput("");
    setPendingPdfFile(null);
    setPendingPptxFile(null);
    setPendingImageFiles([]);
  };

  const closePdfImportDialog = () => {
    if (importLoading) return;
    setShowPdfImportDialog(false);
    setPdfImportDialogError(null);
    setPendingPdfFile(null);
    if (pdfFileInputRef.current) pdfFileInputRef.current.value = "";
  };

  const closePptxImportDialog = () => {
    if (importLoading) return;
    setShowPptxImportDialog(false);
    setPptxImportDialogError(null);
    setPendingPptxFile(null);
    if (pptxFileInputRef.current) pptxFileInputRef.current.value = "";
  };

  const closeImageImportDialog = () => {
    if (importLoading) return;
    setShowImageImportDialog(false);
    setImageImportDialogError(null);
    setPendingImageFiles([]);
    if (imageFileInputRef.current) imageFileInputRef.current.value = "";
  };

  const openPdfImportDialog = () => {
    setPdfImportDialogError(null);
    setShowPptxImportDialog(false);
    setShowImageImportDialog(false);
    setShowPdfImportDialog(true);
  };

  const openPptxImportDialog = () => {
    setPptxImportDialogError(null);
    setShowPdfImportDialog(false);
    setShowImageImportDialog(false);
    setShowPptxImportDialog(true);
  };

  const openImageImportDialog = () => {
    setImageImportDialogError(null);
    setShowPdfImportDialog(false);
    setShowPptxImportDialog(false);
    setShowImageImportDialog(true);
  };

  const appendImportedText = (text) => {
    const chunk = (text || "").trim();
    if (!chunk) return;
    setNoteContent((previous) => {
      const base = (previous || "").trim();
      return base ? `${base}\n\n${chunk}` : chunk;
    });
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
    else if (categoryDropdown.inputId === "editCategory") setEditCategory(cat);
    setCategoryDropdown((p) => ({ ...p, open: false }));
  };
  const filteredCategorySuggestionsNewNote = (meta.categories || [])
    .filter((c) => c.toLowerCase().startsWith((noteCategory || "").trim().toLowerCase()))
    .slice(0, 10);
  const filteredCategorySuggestionsEdit = (meta.categories || [])
    .filter((c) => c.toLowerCase().startsWith((editCategory || "").trim().toLowerCase()))
    .slice(0, 10);
  const filteredCategorySuggestions =
    categoryDropdown.inputId === "noteCategory"
      ? filteredCategorySuggestionsNewNote
      : filteredCategorySuggestionsEdit;

  const handleCreateNote = async (e) => {
    e.preventDefault();
    const title = (noteTitle || "").trim();
    const category = (noteCategory || "").trim();
    const content = (noteContent || "").trim();
    if (!title || !category) {
      setNoteResult({ error: "Title and category are required." });
      return;
    }
    if (content.length > NOTE_MAX_CONTENT_CHARS) {
      setNoteResult({
        error: `Note content exceeds the ${NOTE_MAX_CONTENT_CHARS.toLocaleString()} character limit.`,
      });
      return;
    }
    let tags = [...noteTagsArray];
    const pending = (noteTagInput || "").trim();
    if (pending && !tags.includes(pending)) tags.push(pending);
    setNoteResult(null);
    setNoteLoading(true);
    try {
      const created = await createNote({ title, category, content, tags });
      if (isSelectionMode && created?.id) {
        setSelectedNoteIds((previous) => new Set([...previous, created.id]));
      }
      setNoteTitle("");
      setNoteCategory("");
      setNoteContent("");
      setNoteTagsArray([]);
      setNoteTagInput("");
      setPendingPdfFile(null);
      setPendingPptxFile(null);
      setPendingImageFiles([]);
      setContentImportMessage(null);
      setShowPdfImportDialog(false);
      setShowPptxImportDialog(false);
      setShowImageImportDialog(false);
      setAddFormMode(null);
      loadNotesList(setData, setLoading, setError);
    } catch (err) {
      setNoteResult({ error: err.message });
    } finally {
      setNoteLoading(false);
    }
  };

  const handleExtractPdfIntoContent = async (e) => {
    e?.preventDefault?.();
    if (importLoading) return;
    if (!pendingPdfFile) {
      setPdfImportDialogError("Select a PDF file first.");
      return;
    }
    setPdfImportDialogError(null);
    setImportLoading(true);
    try {
      const form = new FormData();
      form.append("file", pendingPdfFile);
      const res = await extractPdfText(form);
      const text = (res.text || "").trim();
      if (!text) {
        setPdfImportDialogError("No text was extracted from this PDF.");
        return;
      }
      appendImportedText(text);
      const pageCount = res.page_count ?? 1;
      const pageLabel = pageCount === 1 ? "1 page" : `${pageCount} pages`;
      setContentImportMessage(`PDF text imported — ${pageLabel}.`);
      setShowPdfImportDialog(false);
      setPendingPdfFile(null);
      setPdfImportDialogError(null);
      if (pdfFileInputRef.current) pdfFileInputRef.current.value = "";
    } catch (err) {
      setPdfImportDialogError(err.message);
    } finally {
      setImportLoading(false);
    }
  };

  const handleExtractPptxIntoContent = async (e) => {
    e?.preventDefault?.();
    if (importLoading) return;
    if (!pendingPptxFile) {
      setPptxImportDialogError("Select a PowerPoint file first.");
      return;
    }
    setPptxImportDialogError(null);
    setImportLoading(true);
    try {
      const form = new FormData();
      form.append("file", pendingPptxFile);
      const res = await extractPptxText(form);
      const text = (res.text || "").trim();
      if (!text) {
        setPptxImportDialogError("No text was extracted from this PowerPoint.");
        return;
      }
      appendImportedText(text);
      const slideCount = res.slide_count ?? 1;
      const slideLabel = slideCount === 1 ? "1 slide" : `${slideCount} slides`;
      setContentImportMessage(`PPTX text imported — ${slideLabel}.`);
      setShowPptxImportDialog(false);
      setPendingPptxFile(null);
      setPptxImportDialogError(null);
      if (pptxFileInputRef.current) pptxFileInputRef.current.value = "";
    } catch (err) {
      setPptxImportDialogError(err.message);
    } finally {
      setImportLoading(false);
    }
  };

  const handleExtractImagesIntoContent = async (e) => {
    e?.preventDefault?.();
    if (importLoading) return;
    if (!pendingImageFiles.length) {
      setImageImportDialogError("Select one or more screenshots first.");
      return;
    }
    setImageImportDialogError(null);
    setImportLoading(true);
    try {
      const form = new FormData();
      pendingImageFiles.forEach((file) => form.append("files", file));
      const res = await extractImageText(form);
      const text = (res.text || "").trim();
      if (!text) {
        setImageImportDialogError("No text was extracted from these screenshots.");
        return;
      }
      appendImportedText(text);
      const imageCount = res.image_count ?? pendingImageFiles.length;
      const imageLabel = imageCount === 1 ? "1 image" : `${imageCount} images`;
      setContentImportMessage(`Screenshot text imported — ${imageLabel}.`);
      setShowImageImportDialog(false);
      setPendingImageFiles([]);
      setImageImportDialogError(null);
      if (imageFileInputRef.current) imageFileInputRef.current.value = "";
    } catch (err) {
      setImageImportDialogError(err.message);
    } finally {
      setImportLoading(false);
    }
  };

  const noteContentCharCount = (noteContent || "").length;
  const noteContentOverLimit = noteContentCharCount > NOTE_MAX_CONTENT_CHARS;
  const formBusy = noteLoading || importLoading;
  const noteSubmitDisabled =
    formBusy
    || !noteTitle.trim()
    || !noteCategory.trim()
    || noteContentOverLimit;
  const showNoteTitleHint = !formBusy && !noteTitle.trim();
  const showNoteCategoryHint = !formBusy && !noteCategory.trim();
  const showNoteContentLimitErr = !formBusy && noteContentOverLimit;

  const noteToolbarHint = noteSubmitDisabled && !formBusy
    ? (noteContentOverLimit
      ? `Shorten content to ${NOTE_MAX_CONTENT_CHARS.toLocaleString()} characters or fewer.`
      : missingForActionHint([
          { missing: !noteTitle.trim(), label: "title" },
          { missing: !noteCategory.trim(), label: "category" },
        ], { minCount: 1 }))
    : null;

  const showList = !isFormOpen && !isViewingNote;
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
    setContentImportMessage(null);
    setShowPdfImportDialog(false);
    setPendingPdfFile(null);
    if (!isSelectionMode) setSelectedNoteIds(new Set());
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
            {isSelectionMode && (
              <div className="notes-toolbar-actions" role="group" aria-label="Select notes for chat context">
                {showList ? (
                  <>
                    <button type="button" className="button-subtle" onClick={onCloseSelection}>
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="button-primary"
                      onClick={() => {
                        onSelect?.(notesForDisplay.filter((note) => selectedNoteIds.has(note.id)));
                        onCloseSelection?.();
                      }}
                      disabled={loading}
                    >
                      Add selected ({selectedNoteIds.size})
                    </button>
                  </>
                ) : (
                  <>
                    <button type="button" className="button-subtle notes-back-btn" onClick={closeViewOrForm}>
                      Back to list
                    </button>
                    {addFormMode === "note" && (
                      <>
                        <button
                          type="submit"
                          form="notes-new-note-form"
                          className="button-primary"
                          disabled={noteSubmitDisabled}
                        >
                          {noteLoading ? "…" : "Add note"}
                        </button>
                        <NotesToolbarHint text={noteToolbarHint} />
                      </>
                    )}
                  </>
                )}
              </div>
            )}
            {!isSelectionMode && showList && filteredNotes.length > 0 && (
              <>
                {selectedNoteIds.size === 0 && (
                  <button type="button" className="button-subtle ask-shortcut" onClick={handleSelectAll}>
                    Select All
                  </button>
                )}
                {selectedNoteIds.size > 0 && selectedNoteIds.size < filteredNotes.length && (
                  <>
                    <button type="button" className="button-subtle ask-shortcut" onClick={handleSelectAll}>
                      Select All
                    </button>
                    <button type="button" className="button-subtle ask-shortcut" onClick={handleUnselectAll}>
                      Unselect All
                    </button>
                  </>
                )}
                {selectedNoteIds.size === filteredNotes.length && filteredNotes.length > 0 && (
                  <button type="button" className="button-subtle ask-shortcut" onClick={handleUnselectAll}>
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
                    className="button-subtle notes-back-btn"
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
                      className="button-primary"
                      disabled={editSaving || !editTitle.trim() || !editCategory.trim() || !editContent.trim()}
                      aria-label="Save note"
                      title="Save changes"
                    >
                      {editSaving ? "Saving…" : "Save"}
                    </button>
                  )}
                  {addFormMode === "note" && (
                    <>
                      <button
                        type="submit"
                        form="notes-new-note-form"
                        className="button-primary"
                        disabled={noteSubmitDisabled}
                        aria-label="Add note"
                        title="Add note"
                      >
                        {noteLoading ? "…" : "Add note"}
                      </button>
                      <NotesToolbarHint text={noteToolbarHint} />
                    </>
                  )}
                </div>
              ) : showList && selectedNoteIds.size > 0 ? (
                <button
                  type="button"
                  className="button-danger notes-back-btn"
                  onClick={() => setShowDeleteConfirm(true)}
                  disabled={bulkDeleteLoading}
                  aria-label={`Delete ${selectedNoteIds.size} selected`}
                  title="Delete selected notes"
                >
                  {bulkDeleteLoading ? "Deleting…" : `Delete (${selectedNoteIds.size})`}
                </button>
              ) : (
                <button
                  type="button"
                  className="button-subtle ask-shortcut notes-list-add-btn"
                  onClick={openNoteForm}
                  aria-expanded={addFormMode === "note"}
                >
                  Add note
                </button>
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
                  className="button-subtle"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={bulkDeleteLoading}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="button-danger"
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
            <form id="notes-new-note-form" onSubmit={handleCreateNote} className={`form--compact ${formBusy ? "loading" : ""}`}>
              <label htmlFor="noteTitle">Title</label>
              <input
                id="noteTitle"
                type="text"
                placeholder="e.g. Meeting notes"
                value={noteTitle}
                onChange={(e) => setNoteTitle(e.target.value)}
                disabled={formBusy}
                aria-invalid={showNoteTitleHint || undefined}
                aria-describedby={showNoteTitleHint ? "noteTitle-hint" : undefined}
              />
              <NotesFieldHint show={showNoteTitleHint} id="noteTitle-hint">
                Title is required.
              </NotesFieldHint>
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
                  disabled={formBusy}
                  autoComplete="off"
                  aria-invalid={showNoteCategoryHint || undefined}
                  aria-describedby={showNoteCategoryHint ? "noteCategory-hint" : undefined}
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
              <NotesFieldHint show={showNoteCategoryHint} id="noteCategory-hint">
                Category is required.
              </NotesFieldHint>
              <div className="notes-field-label-row">
                <label htmlFor="noteContent" id="noteContent-label">
                  Content
                  {" — "}
                  {noteContentCharCount.toLocaleString()} / {NOTE_MAX_CONTENT_CHARS.toLocaleString()} characters
                </label>
                <div className="notes-import-triggers">
                  <button
                    type="button"
                    className="button-subtle ask-shortcut notes-import-pdf-trigger"
                    aria-haspopup="dialog"
                    aria-expanded={showPdfImportDialog}
                    disabled={formBusy}
                    onClick={openPdfImportDialog}
                  >
                    <svg className="notes-import-pdf-trigger__icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                      <path fill="currentColor" d="M6 2a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7.414a2 2 0 0 0-.586-1.414l-3.414-3.414A2 2 0 0 0 11.586 2H6zm4 1.414L14.586 8H11a1 1 0 0 1-1-1V3.414zM6 3h4v4a2 2 0 0 0 2 2h4v9a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3z" />
                    </svg>
                    Import PDF
                  </button>
                  <button
                    type="button"
                    className="button-subtle ask-shortcut notes-import-pdf-trigger"
                    aria-haspopup="dialog"
                    aria-expanded={showPptxImportDialog}
                    disabled={formBusy}
                    onClick={openPptxImportDialog}
                  >
                    Import PPTX
                  </button>
                  <button
                    type="button"
                    className="button-subtle ask-shortcut notes-import-pdf-trigger"
                    aria-haspopup="dialog"
                    aria-expanded={showImageImportDialog}
                    disabled={formBusy}
                    onClick={openImageImportDialog}
                  >
                    Import screenshots
                  </button>
                </div>
              </div>
              {contentImportMessage ? (
                <p id="noteContent-import-msg" className="notes-content-import-msg success-msg" role="status">
                  {contentImportMessage}
                </p>
              ) : null}
              <textarea
                id="noteContent"
                placeholder="Note content…"
                value={noteContent}
                onChange={(e) => {
                  setNoteContent(e.target.value);
                  if (contentImportMessage) setContentImportMessage(null);
                }}
                disabled={formBusy}
                rows={8}
                aria-labelledby="noteContent-label"
                aria-invalid={showNoteContentLimitErr || undefined}
                aria-describedby={
                  showNoteContentLimitErr
                    ? "noteContent-limit"
                    : contentImportMessage
                      ? "noteContent-import-msg"
                      : undefined
                }
              />
              {showNoteContentLimitErr && (
                <p id="noteContent-limit" className="out out--compact err" role="alert">
                  Note content exceeds the {NOTE_MAX_CONTENT_CHARS.toLocaleString()} character limit. Shorten the text before saving.
                </p>
              )}
              <label htmlFor="noteTags">Tags</label>
              <div className="notes-tags-wrap">
                <div className="notes-tags-chips">
                  {noteTagsArray.map((t, i) => (
                    <span key={`${t}-${i}`} className="notes-tag-chip">
                      <span className="notes-tag-chip__label">{t}</span>
                      <button type="button" className="button-icon button-subtle notes-tag-chip__remove" aria-label={`Remove ${t}`} title={`Remove ${t}`} onClick={() => setNoteTagsArray(noteTagsArray.filter((_, j) => j !== i))}>×</button>
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
                  disabled={formBusy}
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
                      <button type="button" className="button-icon button-subtle notes-tag-chip__remove" aria-label={`Remove ${t}`} title={`Remove ${t}`} onClick={() => setEditTagsArray(editTagsArray.filter((_, j) => j !== i))}>×</button>
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
            {focusNoteMissMessage ? (
              <div className="out out--compact err" role="alert">
                {focusNoteMissMessage}
              </div>
            ) : null}
            {loading && data === null && (
              <p className="notes-list-empty">Loading…</p>
            )}
            {!loading && notesForDisplay.length === 0 && data !== null && (
              <p className="notes-list-empty">{isSelectionMode ? "No notes yet." : "No notes yet. Click “Add note” to create one."}</p>
            )}
            {notesForDisplay.length > 0 && (
              <ul className="notes-list">
                {filteredNotes.slice(0, 100).map((n) => (
                  <li
                    key={n.id}
                    id={`note-card-${n.id}`}
                    className={`note-card ${selectedNoteIds.has(n.id) ? "note-card--selected" : ""}${viewingNoteId === n.id ? " note-card--active" : ""}`}
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

      {showPdfImportDialog && (
        <AskOverlay
          title="Import PDF"
          onClose={closePdfImportDialog}
          showManage={false}
          canClose={!importLoading}
          closeText="Cancel"
        >
          <div className="notes-pdf-import-dialog">
            <p className="flashcards-help">
              Choose a PDF to extract text into Content. The original file is not stored with the note.
            </p>
            <input
              ref={pdfFileInputRef}
              id="notePdfFilePick"
              type="file"
              accept="application/pdf,.pdf"
              className="notes-pdf-import-dialog__file-input"
              disabled={importLoading}
              aria-label="PDF file"
              onChange={(e) => {
                const file = (e.target.files || [])[0] || null;
                setPendingPdfFile(file);
                setPdfImportDialogError(null);
              }}
            />
            {!pendingPdfFile ? (
              <button
                type="button"
                className="button-secondary"
                disabled={importLoading}
                onClick={() => pdfFileInputRef.current?.click()}
              >
                Choose PDF file
              </button>
            ) : (
              <div className="notes-import-file" role="group" aria-label="Selected PDF">
                <span className="notes-import-file__name">{pendingPdfFile.name}</span>
                <button
                  type="button"
                  className="button-subtle notes-import-file__remove"
                  disabled={importLoading}
                  onClick={() => {
                    setPendingPdfFile(null);
                    setPdfImportDialogError(null);
                    if (pdfFileInputRef.current) pdfFileInputRef.current.value = "";
                  }}
                >
                  Remove
                </button>
                <button
                  type="button"
                  className="button-subtle"
                  disabled={importLoading}
                  onClick={() => pdfFileInputRef.current?.click()}
                >
                  Change
                </button>
              </div>
            )}
            {pdfImportDialogError ? (
              <div className="out out--compact err" role="alert">
                {pdfImportDialogError}
              </div>
            ) : null}
            <div className="notes-pdf-import-dialog__actions">
              <button
                type="button"
                className="button-primary"
                disabled={importLoading || !pendingPdfFile}
                onClick={handleExtractPdfIntoContent}
              >
                {importLoading ? "Extracting…" : "Extract PDF text"}
              </button>
            </div>
          </div>
        </AskOverlay>
      )}

      {showPptxImportDialog && (
        <AskOverlay
          title="Import PPTX"
          onClose={closePptxImportDialog}
          showManage={false}
          canClose={!importLoading}
          closeText="Cancel"
        >
          <div className="notes-pdf-import-dialog">
            <p className="flashcards-help">
              Choose a PowerPoint to extract slide text into Content. The original file is not stored with the note.
            </p>
            <input
              ref={pptxFileInputRef}
              id="notePptxFilePick"
              type="file"
              accept="application/vnd.openxmlformats-officedocument.presentationml.presentation,.pptx"
              className="notes-pdf-import-dialog__file-input"
              disabled={importLoading}
              aria-label="PPTX file"
              onChange={(e) => {
                const file = (e.target.files || [])[0] || null;
                setPendingPptxFile(file);
                setPptxImportDialogError(null);
              }}
            />
            {!pendingPptxFile ? (
              <button
                type="button"
                className="button-secondary"
                disabled={importLoading}
                onClick={() => pptxFileInputRef.current?.click()}
              >
                Choose PPTX file
              </button>
            ) : (
              <div className="notes-import-file" role="group" aria-label="Selected PPTX">
                <span className="notes-import-file__name">{pendingPptxFile.name}</span>
                <button
                  type="button"
                  className="button-subtle notes-import-file__remove"
                  disabled={importLoading}
                  onClick={() => {
                    setPendingPptxFile(null);
                    setPptxImportDialogError(null);
                    if (pptxFileInputRef.current) pptxFileInputRef.current.value = "";
                  }}
                >
                  Remove
                </button>
                <button
                  type="button"
                  className="button-subtle"
                  disabled={importLoading}
                  onClick={() => pptxFileInputRef.current?.click()}
                >
                  Change
                </button>
              </div>
            )}
            {pptxImportDialogError ? (
              <div className="out out--compact err" role="alert">
                {pptxImportDialogError}
              </div>
            ) : null}
            <div className="notes-pdf-import-dialog__actions">
              <button
                type="button"
                className="button-primary"
                disabled={importLoading || !pendingPptxFile}
                onClick={handleExtractPptxIntoContent}
              >
                {importLoading ? "Extracting…" : "Extract PPTX text"}
              </button>
            </div>
          </div>
        </AskOverlay>
      )}

      {showImageImportDialog && (
        <AskOverlay
          title="Import screenshots"
          onClose={closeImageImportDialog}
          showManage={false}
          canClose={!importLoading}
          closeText="Cancel"
        >
          <div className="notes-pdf-import-dialog">
            <p className="flashcards-help">
              Choose one or more screenshots to extract text into Content. The original images are not stored with the note.
            </p>
            <input
              ref={imageFileInputRef}
              id="noteImageFilePick"
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif,image/bmp,.png,.jpg,.jpeg,.webp,.gif,.bmp"
              multiple
              className="notes-pdf-import-dialog__file-input"
              disabled={importLoading}
              aria-label="Screenshot files"
              onChange={(e) => {
                setPendingImageFiles(Array.from(e.target.files || []));
                setImageImportDialogError(null);
              }}
            />
            {pendingImageFiles.length === 0 ? (
              <button
                type="button"
                className="button-secondary"
                disabled={importLoading}
                onClick={() => imageFileInputRef.current?.click()}
              >
                Choose screenshots
              </button>
            ) : (
              <div className="notes-import-file" role="group" aria-label="Selected screenshots">
                <span className="notes-import-file__name">
                  {pendingImageFiles.map((file) => file.name).join(", ")}
                </span>
                <button
                  type="button"
                  className="button-subtle notes-import-file__remove"
                  disabled={importLoading}
                  onClick={() => {
                    setPendingImageFiles([]);
                    setImageImportDialogError(null);
                    if (imageFileInputRef.current) imageFileInputRef.current.value = "";
                  }}
                >
                  Remove
                </button>
                <button
                  type="button"
                  className="button-subtle"
                  disabled={importLoading}
                  onClick={() => imageFileInputRef.current?.click()}
                >
                  Change
                </button>
              </div>
            )}
            {imageImportDialogError ? (
              <div className="out out--compact err" role="alert">
                {imageImportDialogError}
              </div>
            ) : null}
            <div className="notes-pdf-import-dialog__actions">
              <button
                type="button"
                className="button-primary"
                disabled={importLoading || pendingImageFiles.length === 0}
                onClick={handleExtractImagesIntoContent}
              >
                {importLoading ? "Extracting…" : "Extract screenshot text"}
              </button>
            </div>
          </div>
        </AskOverlay>
      )}
    </section>
  );
}
