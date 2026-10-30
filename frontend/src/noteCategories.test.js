// IA/frontend/src/noteCategories.test.js

import assert from "node:assert/strict";
import test from "node:test";
import {
  FLASHCARD_DECK_CATEGORY,
  isFlashcardDeckCategory,
  isManageNotesExcludedCategory,
} from "./noteCategories.js";

test("recognizes _flashcards and legacy flashcards deck categories", () => {
  assert.equal(isFlashcardDeckCategory(FLASHCARD_DECK_CATEGORY), true);
  assert.equal(isFlashcardDeckCategory("flashcards"), true);
  assert.equal(isFlashcardDeckCategory("study"), false);
});

test("excludes history and flashcard decks from Manage Notes", () => {
  assert.equal(isManageNotesExcludedCategory("_history"), true);
  assert.equal(isManageNotesExcludedCategory("_flashcards"), true);
  assert.equal(isManageNotesExcludedCategory("flashcards"), true);
  assert.equal(isManageNotesExcludedCategory("work"), false);
});
