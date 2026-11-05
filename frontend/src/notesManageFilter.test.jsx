// IA/frontend/src/notesManageFilter.test.jsx
// Manage → Notes excludes internal categories from the list.

// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import Notes from "./components/Notes.jsx";

vi.mock("./api.js", () => ({
  listNotes: vi.fn(),
  getNotesMeta: vi.fn(() => Promise.resolve({ categories: [], tags: [] })),
  createNote: vi.fn(),
  extractPdfText: vi.fn(),
  extractPptxText: vi.fn(),
  extractImageText: vi.fn(),
  updateNote: vi.fn(),
  deleteNote: vi.fn(),
}));

import { listNotes } from "./api.js";

describe("Manage Notes list filtering", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows ordinary notes but hides _history and flashcard deck categories", async () => {
    listNotes.mockResolvedValue([
      { id: "n1", title: "Visible note", category: "study", content: "x", tags: [] },
      { id: "h1", title: "Hidden history", category: "_history", content: "[]", tags: [] },
      { id: "d1", title: "Legacy deck", category: "flashcards", content: "{}", tags: ["flashcards"] },
      { id: "d2", title: "New deck", category: "_flashcards", content: "{}", tags: ["flashcards"] },
    ]);
    render(<Notes />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    expect(await screen.findByText("Visible note")).toBeTruthy();
    expect(screen.queryByText("Hidden history")).toBeNull();
    expect(screen.queryByText("Legacy deck")).toBeNull();
    expect(screen.queryByText("New deck")).toBeNull();
  });
});
