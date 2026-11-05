// IA/frontend/src/components/FlashcardsPanel.jsx
// Deck library, study mode, and edit/generate flows for flashcard decks stored as Notes.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  createNote,
  deleteNote,
  FlashcardPollTimeoutError,
  generateFlashcards,
  listNotes,
  updateNote,
} from "../api";
import {
  FLASHCARD_DECK_CATEGORY,
  HISTORY_CATEGORY,
  isFlashcardDeckCategory,
} from "../noteCategories.js";

const MAX_CARDS = 99;
const MAX_SELECTED_NOTES = 20;

function isFlashcardDeck(note) {
  return isFlashcardDeckCategory(note?.category);
}

function parseDeckCards(note) {
  try {
    const data = JSON.parse(note.content);
    if (
      data
      && Array.isArray(data.cards)
      && data.cards.length > 0
      && data.cards.every((card) => (
        card
        && typeof card.question === "string"
        && typeof card.answer === "string"
      ))
    ) {
      return data.cards.map((card, index) => ({
        id: `${note.id}-${index}`,
        question: card.question,
        answer: card.answer,
      }));
    }
  } catch {
    return null;
  }
  return null;
}

export default function FlashcardsPanel({ onClose, onBusyChange }) {
  const [notes, setNotes] = useState([]);
  const [notesLoading, setNotesLoading] = useState(true);
  const [notesError, setNotesError] = useState(null);
  const [stage, setStage] = useState("decks");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNoteIds, setSelectedNoteIds] = useState(() => new Set());
  const [cardCount, setCardCount] = useState("10");
  const [difficulty, setDifficulty] = useState("Mixed");
  const [questionStyle, setQuestionStyle] = useState("Mixed");
  const [language, setLanguage] = useState("Same as notes");
  const [additionalInstructions, setAdditionalInstructions] = useState("");
  const [deckTitle, setDeckTitle] = useState("Flashcards");
  const [draft, setDraft] = useState([]);
  const [currentCardIndex, setCurrentCardIndex] = useState(0);
  const [activeDeckId, setActiveDeckId] = useState(null);
  const [editingDeck, setEditingDeck] = useState(false);
  const [answerRevealed, setAnswerRevealed] = useState(false);
  const [deleteConfirmationId, setDeleteConfirmationId] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState(null);
  const [resumeOperationId, setResumeOperationId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const generatingRef = useRef(false);
  const busyRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    listNotes({ limit: 500 })
      .then((result) => {
        if (!cancelled) {
          setNotes(Array.isArray(result)
            ? result.filter((note) => note?.id && (note.category || "") !== HISTORY_CATEGORY)
            : []);
        }
      })
      .catch((loadError) => {
        if (!cancelled) setNotesError(loadError.message || "Could not load notes.");
      })
      .finally(() => {
        if (!cancelled) setNotesLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const decks = useMemo(() => notes.filter(isFlashcardDeck), [notes]);
  const sourceNotes = useMemo(
    () => notes.filter((note) => !isFlashcardDeck(note)),
    [notes],
  );
  const filteredSourceNotes = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return sourceNotes;
    return sourceNotes.filter((note) => (
      [note.title, note.category, ...(note.tags || [])]
        .some((value) => typeof value === "string" && value.toLowerCase().includes(query))
    ));
  }, [searchQuery, sourceNotes]);

  const setMutationBusy = (value) => {
    busyRef.current = value;
    setBusy(value);
    onBusyChange?.(value);
  };

  const close = () => {
    if (!busyRef.current) onClose();
  };

  const goToCardIndex = (nextIndex) => {
    setCurrentCardIndex(nextIndex);
    setAnswerRevealed(false);
  };

  const startNewDeck = () => {
    setSelectedNoteIds(new Set());
    setSearchQuery("");
    setCardCount("10");
    setDifficulty("Mixed");
    setQuestionStyle("Mixed");
    setLanguage("Same as notes");
    setAdditionalInstructions("");
    setDeckTitle("Flashcards");
    setDraft([]);
    setCurrentCardIndex(0);
    setActiveDeckId(null);
    setEditingDeck(true);
    setAnswerRevealed(false);
    setError(null);
    setSuccess(null);
    setStage("sources");
  };

  const toggleNote = (noteId) => {
    setSelectedNoteIds((current) => {
      if (!current.has(noteId) && current.size >= MAX_SELECTED_NOTES) return current;
      const next = new Set(current);
      if (next.has(noteId)) next.delete(noteId);
      else next.add(noteId);
      return next;
    });
    setError(null);
  };

  const cancelNewDeck = () => {
    setStage("decks");
    setError(null);
    setSuccess(null);
  };

  const applyGenerationResult = (result, count) => {
    if (!Array.isArray(result.cards) || result.cards.length !== count) {
      throw new Error("The generated cards did not match the requested count.");
    }
    setDraft(result.cards.map((card, index) => ({
      id: `${Date.now()}-${index}`,
      question: card.question,
      answer: card.answer,
    })));
    const firstTitle = sourceNotes.find((note) => selectedNoteIds.has(note.id))?.title?.trim();
    setDeckTitle(firstTitle ? `${firstTitle} flashcards` : "Flashcards");
    setCurrentCardIndex(0);
    setActiveDeckId(null);
    setEditingDeck(true);
    setAnswerRevealed(false);
    setStage("review");
    setResumeOperationId(null);
  };

  const generate = async () => {
    if (generatingRef.current) return;
    const count = Number(cardCount);
    if (!selectedNoteIds.size) {
      setError("Select at least one source note.");
      return;
    }
    if (!Number.isInteger(count) || count < 1 || count > MAX_CARDS) {
      setError(`Choose between 1 and ${MAX_CARDS} cards.`);
      return;
    }
    setError(null);
    setSuccess(null);
    setResumeOperationId(null);
    generatingRef.current = true;
    setGenerating(true);
    setGenerationProgress(null);
    try {
      const result = await generateFlashcards({
        note_ids: [...selectedNoteIds],
        card_count: count,
        difficulty,
        question_style: questionStyle,
        language,
        additional_instructions: additionalInstructions,
      }, {
        onProgress: (progress) => setGenerationProgress(progress || null),
      });
      applyGenerationResult(result, count);
    } catch (generationError) {
      if (generationError instanceof FlashcardPollTimeoutError) {
        setResumeOperationId(generationError.operationId);
        setError(generationError.message);
      } else {
        setResumeOperationId(null);
        setError(generationError.message || "Could not generate flashcards.");
      }
    } finally {
      generatingRef.current = false;
      setGenerating(false);
      setGenerationProgress(null);
    }
  };

  const continueWaiting = async () => {
    if (!resumeOperationId || generatingRef.current) return;
    const count = Number(cardCount);
    setError(null);
    setSuccess(null);
    generatingRef.current = true;
    setGenerating(true);
    setGenerationProgress(null);
    try {
      const result = await generateFlashcards(
        { operation_id: resumeOperationId },
        { onProgress: (progress) => setGenerationProgress(progress || null) },
      );
      applyGenerationResult(result, count);
    } catch (generationError) {
      if (generationError instanceof FlashcardPollTimeoutError) {
        setResumeOperationId(generationError.operationId);
        setError(generationError.message);
      } else {
        setResumeOperationId(null);
        setError(generationError.message || "Could not generate flashcards.");
      }
    } finally {
      generatingRef.current = false;
      setGenerating(false);
      setGenerationProgress(null);
    }
  };

  const openDeckForStudy = (note) => {
    const cards = parseDeckCards(note);
    if (!cards) {
      setError("This saved deck has invalid card data and cannot be opened.");
      return;
    }
    setDraft(cards);
    setCurrentCardIndex(0);
    setDeckTitle(note.title || "Flashcards");
    setActiveDeckId(note.id);
    setEditingDeck(false);
    setAnswerRevealed(false);
    setDeleteConfirmationId(null);
    setError(null);
    setSuccess(null);
    setStage("study");
  };

  const openDeckForEdit = (note) => {
    const cards = parseDeckCards(note);
    if (!cards) {
      setError("This saved deck has invalid card data and cannot be opened.");
      return;
    }
    setDraft(cards);
    setCurrentCardIndex(0);
    setDeckTitle(note.title || "Flashcards");
    setActiveDeckId(note.id);
    setEditingDeck(true);
    setAnswerRevealed(false);
    setDeleteConfirmationId(null);
    setError(null);
    setSuccess(null);
    setStage("review");
  };

  const cancelEditingSavedDeck = () => {
    const note = decks.find((deck) => deck.id === activeDeckId);
    if (!note) {
      setStage("decks");
      setEditingDeck(false);
      return;
    }
    openDeckForStudy(note);
  };

  const updateCard = (cardId, field, value) => {
    setDraft((cards) => cards.map((card) => (
      card.id === cardId ? { ...card, [field]: value } : card
    )));
    setSuccess(null);
  };

  const removeCard = (cardId) => {
    const next = draft.filter((card) => card.id !== cardId);
    setDraft(next);
    setCurrentCardIndex((index) => Math.min(index, Math.max(0, next.length - 1)));
    setSuccess(null);
  };

  const saveDeck = async () => {
    if (busyRef.current || !draft.length) return;
    if (!deckTitle.trim() || draft.some((card) => !card.question.trim() || !card.answer.trim())) {
      setError("Add a deck title and complete every question and answer before saving.");
      return;
    }
    const wasUpdate = Boolean(activeDeckId);
    setMutationBusy(true);
    setError(null);
    setSuccess(null);
    const noteData = {
      title: deckTitle.trim().slice(0, 100),
      category: FLASHCARD_DECK_CATEGORY,
      tags: ["flashcards"],
      content: JSON.stringify({
        version: 1,
        cards: draft.map(({ question, answer }) => ({
          question: question.trim(),
          answer: answer.trim(),
        })),
      }),
    };
    try {
      const savedNote = activeDeckId
        ? await updateNote(activeDeckId, noteData)
        : await createNote(noteData);
      setNotes((current) => [
        savedNote,
        ...current.filter((note) => note.id !== savedNote.id),
      ]);
      setActiveDeckId(savedNote.id);
      setEditingDeck(false);
      setAnswerRevealed(false);
      setSuccess(wasUpdate ? "Deck changes saved." : "Approved deck saved to Notes.");
      setStage("study");
    } catch (saveError) {
      setError(saveError.message || "Could not save the deck.");
    } finally {
      setMutationBusy(false);
    }
  };

  const deleteDeck = async (note) => {
    if (busyRef.current) return;
    setMutationBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await deleteNote(note.id);
      setNotes((current) => current.filter((item) => item.id !== note.id));
      setDeleteConfirmationId(null);
      setSuccess(`Deleted "${note.title || "Flashcards"}".`);
    } catch (deleteError) {
      setError(deleteError.message || "Could not delete the deck.");
    } finally {
      setMutationBusy(false);
    }
  };

  const currentCard = draft[currentCardIndex];
  const isSavedDeck = Boolean(activeDeckId);
  const canEdit = !isSavedDeck || editingDeck;

  const addCard = () => {
    if (!canEdit || busyRef.current) return;
    const newCard = { id: `${Date.now()}-${draft.length}`, question: "", answer: "" };
    setDraft((cards) => {
      const next = [...cards, newCard];
      setCurrentCardIndex(next.length - 1);
      return next;
    });
    setSuccess(null);
  };

  const generationProgressLabel = () => {
    if (!generationProgress?.total_batches) return "Generating…";
    const batch = Math.max(1, generationProgress.current_batch || 1);
    return `Generating batch ${batch} of ${generationProgress.total_batches}…`;
  };

  return (
    <div className="flashcards-panel">
      {stage === "decks" && (
        <>
          <div className="flashcards-library-header">
            <h3 className="flashcards-library-header__title">Decks</h3>
            <button type="button" className="button-primary" onClick={startNewDeck} disabled={busy}>
              New Flashcard
            </button>
          </div>
          {notesLoading ? (
            <p role="status">Loading saved decks…</p>
          ) : notesError ? (
            <p className="out err" role="alert">{notesError}</p>
          ) : decks.length === 0 ? (
            <p className="notes-list-empty">No saved flashcard decks yet. Create one from your notes.</p>
          ) : (
            <ul className="flashcards-deck-grid">
              {decks.map((deck) => {
                const cardCountLabel = parseDeckCards(deck)?.length ?? null;
                return (
                  <li className="flashcards-deck-card" key={deck.id}>
                    <div className="flashcards-deck-card__body">
                      <p className="flashcards-deck-card__title">{deck.title || "Untitled deck"}</p>
                      <p className="flashcards-deck-card__meta">
                        {cardCountLabel == null ? "Unavailable" : `${cardCountLabel} ${cardCountLabel === 1 ? "card" : "cards"}`}
                      </p>
                    </div>
                    <div className="flashcards-deck-card__actions">
                      <button
                        type="button"
                        className="button-subtle"
                        onClick={() => openDeckForStudy(deck)}
                        disabled={busy}
                        aria-label={`Open deck: ${deck.title || "Untitled deck"}`}
                      >
                        Open
                      </button>
                      <button
                        type="button"
                        className="button-subtle"
                        onClick={() => openDeckForEdit(deck)}
                        disabled={busy}
                        aria-label={`Edit deck: ${deck.title || "Untitled deck"}`}
                      >
                        Edit
                      </button>
                      {deleteConfirmationId === deck.id ? (
                        <div className="flashcards-deck-card__delete-confirm" role="group" aria-label="Confirm delete">
                          <span className="flashcards-delete-prompt">Delete this deck?</span>
                          <button type="button" className="button-danger" onClick={() => deleteDeck(deck)} disabled={busy}>
                            {busy ? "Deleting…" : "Confirm delete"}
                          </button>
                          <button type="button" className="button-subtle" onClick={() => setDeleteConfirmationId(null)} disabled={busy}>
                            Keep
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="button-danger"
                          onClick={() => setDeleteConfirmationId(deck.id)}
                          disabled={busy}
                          aria-label={`Delete deck: ${deck.title || "Untitled deck"}`}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          {success && <p className="out success-msg" role="status">{success}</p>}
          {error && <p className="out err" role="alert">{error}</p>}
        </>
      )}

      {stage === "study" && (
        <>
          <div className="flashcards-study__deck-title-block">
            <span className="flashcards-study__deck-label">Deck Title:</span>
            <span className="flashcards-study__deck-name">{deckTitle || "Untitled deck"}</span>
          </div>
          {currentCard ? (
            <section className="flashcards-study" aria-label="Flashcard study">
              <h4 className="flashcards-study__heading">Question</h4>
              <div className="flashcards-study__question-card">
                <p className="flashcards-study__question-text">{currentCard.question}</p>
              </div>
              <div className="flashcards-study__nav">
                <button
                  type="button"
                  className="button-subtle flashcards-study__nav-btn"
                  aria-label="Previous card"
                  onClick={() => goToCardIndex(Math.max(0, currentCardIndex - 1))}
                  disabled={currentCardIndex === 0}
                >
                  ←
                </button>
                <span className="flashcards-study__nav-count" aria-live="polite">
                  Card {currentCardIndex + 1} of {draft.length}
                </span>
                <button
                  type="button"
                  className="button-subtle flashcards-study__nav-btn"
                  aria-label="Next card"
                  onClick={() => goToCardIndex(Math.min(draft.length - 1, currentCardIndex + 1))}
                  disabled={currentCardIndex >= draft.length - 1}
                >
                  →
                </button>
              </div>
              <h4 className="flashcards-study__heading">Answer</h4>
              <button
                type="button"
                className={`flashcards-study__answer-reveal${answerRevealed ? " is-revealed" : ""}`}
                aria-expanded={answerRevealed}
                aria-controls="flashcards-study-answer-region"
                aria-label={answerRevealed ? "Hide answer" : "Reveal answer"}
                onClick={() => setAnswerRevealed((revealed) => !revealed)}
              >
                {answerRevealed ? (
                  <span id="flashcards-study-answer-region" className="flashcards-study__answer-text">
                    {currentCard.answer}
                  </span>
                ) : (
                  <span id="flashcards-study-answer-region" className="flashcards-study__answer-placeholder">
                    Click to reveal answer
                  </span>
                )}
              </button>
            </section>
          ) : (
            <p className="notes-list-empty">This deck has no cards.</p>
          )}
          {error && <p className="out err" role="alert">{error}</p>}
          {success && <p className="out success-msg" role="status">{success}</p>}
          <div className="flashcards-actions flashcards-actions--footer flashcards-actions--footer-split">
            <button
              type="button"
              className="button-subtle"
              onClick={() => {
                setStage("decks");
                setError(null);
                setSuccess(null);
              }}
              disabled={busy}
            >
              Back to decks
            </button>
            <div className="flashcards-actions__right">
              <button
                type="button"
                className="button-subtle"
                onClick={() => {
                  const note = notes.find((item) => item.id === activeDeckId);
                  if (note) openDeckForEdit(note);
                }}
                disabled={busy || !activeDeckId}
              >
                Edit deck
              </button>
            </div>
          </div>
        </>
      )}

      {stage === "sources" && (
        <>
          <div className="flashcards-stage-heading">
            <div>
              <h3>Step 1 — Select source notes</h3>
              <p className="flashcards-help">{selectedNoteIds.size} of {MAX_SELECTED_NOTES} notes selected</p>
            </div>
          </div>
          {notesLoading ? (
            <p role="status">Loading notes…</p>
          ) : notesError ? (
            <p className="out err" role="alert">{notesError}</p>
          ) : sourceNotes.length === 0 ? (
            <p className="notes-list-empty">No saved notes are available. Create notes before generating flashcards.</p>
          ) : (
            <>
              <label className="flashcards-field-label" htmlFor="flashcards-note-search">Search notes</label>
              <input
                id="flashcards-note-search"
                className="notes-search-input flashcards-search"
                type="search"
                placeholder="Search by title, category, or tag"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
              {filteredSourceNotes.length === 0 ? (
                <p className="notes-list-empty">No notes match that search.</p>
              ) : (
                <ul className="flashcards-note-list">
                  {filteredSourceNotes.map((note) => {
                    const selected = selectedNoteIds.has(note.id);
                    return (
                      <li key={note.id}>
                        <label className="flashcards-note-row">
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={() => toggleNote(note.id)}
                            disabled={busy || generating || (!selected && selectedNoteIds.size >= MAX_SELECTED_NOTES)}
                          />
                          <span className="flashcards-note-row__title">{note.title || "Untitled note"}</span>
                          {note.category && <span className="badge">{note.category}</span>}
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
              {selectedNoteIds.size >= MAX_SELECTED_NOTES && (
                <p className="flashcards-help" role="status">
                  You can select up to 20 notes. Remove a selected note to choose another.
                </p>
              )}
            </>
          )}
          <div className="flashcards-actions flashcards-actions--footer">
            <button type="button" className="button-subtle" onClick={cancelNewDeck}>Cancel</button>
            <div className="flashcards-actions__right">
              <button type="button" className="button-subtle" onClick={() => setStage("decks")}>Back</button>
              <button
                type="button"
                className="button-primary"
                onClick={() => { setError(null); setStage("options"); }}
                disabled={!selectedNoteIds.size || notesLoading || Boolean(notesError)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}

      {stage === "options" && (
        <>
          <div className="flashcards-stage-heading">
            <div>
              <h3>Step 2 — Generation options</h3>
              <p className="flashcards-help">{selectedNoteIds.size} source {selectedNoteIds.size === 1 ? "note" : "notes"} selected</p>
            </div>
          </div>
          <section className="flashcards-options" aria-label="Generation options">
            <div>
              <label htmlFor="flashcards-count">Number of cards</label>
              <input
                id="flashcards-count"
                type="number"
                min="1"
                max={MAX_CARDS}
                value={cardCount}
                onChange={(event) => setCardCount(event.target.value)}
                disabled={generating}
              />
            </div>
            <div>
              <label htmlFor="flashcards-difficulty">Difficulty</label>
              <select id="flashcards-difficulty" value={difficulty} onChange={(event) => setDifficulty(event.target.value)} disabled={generating}>
                {["Easy", "Mixed", "Hard"].map((value) => <option key={value}>{value}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="flashcards-style">Question style</label>
              <select id="flashcards-style" value={questionStyle} onChange={(event) => setQuestionStyle(event.target.value)} disabled={generating}>
                {["Definitions", "Understanding", "Practical", "Mixed"].map((value) => <option key={value}>{value}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="flashcards-language">Language</label>
              <select id="flashcards-language" value={language} onChange={(event) => setLanguage(event.target.value)} disabled={generating}>
                {["Same as notes", "English", "Filipino"].map((value) => <option key={value}>{value}</option>)}
              </select>
            </div>
            <div className="flashcards-options__instructions">
              <label htmlFor="flashcards-instructions">Additional instructions (optional)</label>
              <textarea
                id="flashcards-instructions"
                maxLength={1000}
                value={additionalInstructions}
                onChange={(event) => setAdditionalInstructions(event.target.value)}
                disabled={generating}
              />
            </div>
          </section>
          {error && <p className="out err" role="alert">{error}</p>}
          {resumeOperationId && !generating && (
            <button type="button" className="button-subtle" onClick={continueWaiting}>
              Keep waiting
            </button>
          )}
          {generating && generationProgress?.total_batches > 0 && (
            <p className="flashcards-help" role="status">{generationProgressLabel()}</p>
          )}
          <div className="flashcards-actions flashcards-actions--footer">
            <button type="button" className="button-subtle" onClick={cancelNewDeck} disabled={generating}>Cancel</button>
            <div className="flashcards-actions__right">
              <button type="button" className="button-subtle" onClick={() => setStage("sources")} disabled={generating}>Back</button>
              {draft.length > 0 && !activeDeckId && (
                <button type="button" className="button-subtle" onClick={() => setStage("review")} disabled={generating}>
                  Review draft
                </button>
              )}
              <button type="button" className="button-primary" onClick={generate} disabled={generating}>
                {generating ? generationProgressLabel() : draft.length > 0 && !activeDeckId ? "Generate new cards" : "Generate"}
              </button>
            </div>
          </div>
        </>
      )}

      {stage === "review" && (
        <>
          <div className="flashcards-stage-heading">
            <div>
              <h3>{isSavedDeck ? "Edit saved deck" : "Step 3 — Review generated cards"}</h3>
              {!isSavedDeck && <p className="flashcards-help">This draft is not saved until you approve it.</p>}
            </div>
          </div>
          <label htmlFor="flashcards-deck-title">Deck title</label>
          <input
            id="flashcards-deck-title"
            maxLength={100}
            value={deckTitle}
            onChange={(event) => { setDeckTitle(event.target.value); setSuccess(null); }}
            disabled={!canEdit || busy}
          />
          {currentCard ? (
            <section className="flashcards-review" aria-label="Flashcard review">
              <div className="flashcards-review__navigation">
                <button
                  type="button"
                  className="button-subtle"
                  aria-label="Previous card"
                  onClick={() => setCurrentCardIndex((index) => Math.max(0, index - 1))}
                  disabled={currentCardIndex === 0}
                >
                  ←
                </button>
                <span aria-live="polite">Card {currentCardIndex + 1} of {draft.length}</span>
                <button
                  type="button"
                  className="button-subtle"
                  aria-label="Next card"
                  onClick={() => setCurrentCardIndex((index) => Math.min(draft.length - 1, index + 1))}
                  disabled={currentCardIndex >= draft.length - 1}
                >
                  →
                </button>
              </div>
              <article className="flashcards-review__card">
                <h4>Card front — question</h4>
                <label htmlFor={`flashcard-question-${currentCard.id}`}>Question / front</label>
                <textarea
                  id={`flashcard-question-${currentCard.id}`}
                  value={currentCard.question}
                  onChange={(event) => updateCard(currentCard.id, "question", event.target.value)}
                  readOnly={!canEdit || busy}
                />
                <h4>Card back — answer</h4>
                <label htmlFor={`flashcard-answer-${currentCard.id}`}>Answer / back</label>
                <textarea
                  id={`flashcard-answer-${currentCard.id}`}
                  value={currentCard.answer}
                  onChange={(event) => updateCard(currentCard.id, "answer", event.target.value)}
                  readOnly={!canEdit || busy}
                />
                {canEdit && (
                  <button
                    type="button"
                    className="button-danger"
                    onClick={() => removeCard(currentCard.id)}
                    disabled={busy}
                  >
                    Remove this card
                  </button>
                )}
                {canEdit && (
                  <button
                    type="button"
                    className="button-subtle"
                    onClick={addCard}
                    disabled={busy}
                  >
                    Add card
                  </button>
                )}
              </article>
            </section>
          ) : (
            <p className="notes-list-empty">No cards remain. Go back to the generation options to create a new draft.</p>
          )}
          {error && <p className="out err" role="alert">{error}</p>}
          {success && <p className="out success-msg" role="status">{success}</p>}
          <div
            className={`flashcards-actions flashcards-actions--footer${
              isSavedDeck ? " flashcards-actions--footer-cluster" : ""
            }`}
          >
            {isSavedDeck ? (
              <button
                type="button"
                className="button-subtle"
                onClick={cancelEditingSavedDeck}
                disabled={busy}
              >
                Back to study
              </button>
            ) : (
              <button type="button" className="button-subtle" onClick={() => setStage("options")} disabled={busy}>
                Back
              </button>
            )}
            <div className="flashcards-actions__right">
              {canEdit && isSavedDeck && editingDeck && (
                <button type="button" className="button-subtle" onClick={cancelEditingSavedDeck} disabled={busy}>
                  Cancel editing
                </button>
              )}
              {canEdit && (
                <button
                  type="button"
                  className="button-primary"
                  onClick={saveDeck}
                  disabled={busy || !draft.length || Boolean(success)}
                >
                  {busy ? "Saving…" : isSavedDeck ? "Save changes" : "Save approved deck"}
                </button>
              )}
              {!isSavedDeck && (
                <button type="button" className="button-subtle" onClick={close} disabled={busy}>
                  Cancel
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
