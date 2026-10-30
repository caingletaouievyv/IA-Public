// IA/frontend/src/noteCategories.js
// Internal note categories excluded from Manage → Notes (mirrors backend conventions).

export const HISTORY_CATEGORY = "_history";
export const FLASHCARD_DECK_CATEGORY = "_flashcards";
export const LEGACY_FLASHCARD_DECK_CATEGORY = "flashcards";

export function isFlashcardDeckCategory(category) {
  const value = (category || "").trim();
  return value === FLASHCARD_DECK_CATEGORY || value === LEGACY_FLASHCARD_DECK_CATEGORY;
}

/** Categories hidden from Manage → Notes (History panel / Flashcards own these). */
export function isManageNotesExcludedCategory(category) {
  const value = (category || "").trim();
  return value === HISTORY_CATEGORY || isFlashcardDeckCategory(value);
}
