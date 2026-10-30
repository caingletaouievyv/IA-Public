// IA/frontend/src/FlashcardsPanel.test.jsx
// Deck library and study mode behavior.

// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FlashcardsPanel from "./components/FlashcardsPanel.jsx";

vi.mock("./api.js", () => ({
  listNotes: vi.fn(),
  createNote: vi.fn(),
  updateNote: vi.fn(),
  deleteNote: vi.fn(),
  generateFlashcards: vi.fn(),
}));

import { listNotes } from "./api.js";

const deckCardsJson = JSON.stringify({
  version: 1,
  cards: [
    { question: "What is an API?", answer: "Application Programming Interface" },
    { question: "Q2", answer: "A2" },
  ],
});

const legacyDeckNote = {
  id: "deck-legacy",
  title: "Legacy deck",
  category: "flashcards",
  tags: ["flashcards"],
  content: deckCardsJson,
};

const newDeckNote = {
  id: "deck-1",
  title: "First deck",
  category: "_flashcards",
  tags: ["flashcards"],
  content: deckCardsJson,
};

describe("FlashcardsPanel deck library and study mode", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    listNotes.mockResolvedValue([newDeckNote]);
  });

  it("renders Deck Library with deck cards and New Flashcard", async () => {
    render(<FlashcardsPanel onClose={() => {}} />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    expect(screen.getByRole("heading", { name: "Decks" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "New Flashcard" })).toBeTruthy();
    expect(screen.getByText("First deck")).toBeTruthy();
    expect(screen.getByText("2 cards")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open deck: First deck" })).toBeTruthy();
  });

  it("shows question, hides answer until reveal, toggles, and resets on navigation", async () => {
    const user = userEvent.setup();
    render(<FlashcardsPanel onClose={() => {}} />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Open deck: First deck" }));

    expect(screen.getByText("Deck Title:")).toBeTruthy();
    expect(screen.getByText("First deck")).toBeTruthy();
    expect(screen.getByText("What is an API?")).toBeTruthy();
    expect(screen.queryByText("Application Programming Interface")).toBeNull();

    const reveal = screen.getByText("Click to reveal answer").closest("button");
    expect(reveal).toBeTruthy();
    expect(reveal.getAttribute("aria-expanded")).toBe("false");
    await user.click(reveal);
    expect(screen.getByText("Application Programming Interface")).toBeTruthy();
    expect(reveal.getAttribute("aria-expanded")).toBe("true");

    await user.click(reveal);
    expect(screen.queryByText("Application Programming Interface")).toBeNull();

    await user.click(reveal);
    expect(screen.getByText("Application Programming Interface")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Next card" }));
    expect(screen.getByText("Card 2 of 2")).toBeTruthy();
    expect(screen.queryByText("Application Programming Interface")).toBeNull();
    expect(screen.getByText("Click to reveal answer")).toBeTruthy();
  });

  it("lists legacy flashcards category decks alongside _flashcards", async () => {
    listNotes.mockResolvedValue([legacyDeckNote, newDeckNote]);
    render(<FlashcardsPanel onClose={() => {}} />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    expect(screen.getByText("Legacy deck")).toBeTruthy();
    expect(screen.getByText("First deck")).toBeTruthy();
  });

  it("Back to decks returns to library; Edit deck opens edit mode", async () => {
    const user = userEvent.setup();
    render(<FlashcardsPanel onClose={() => {}} />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Open deck: First deck" }));
    await user.click(screen.getByRole("button", { name: "Edit deck" }));
    expect(screen.getByRole("heading", { name: "Edit saved deck" })).toBeTruthy();
    expect(screen.getByLabelText("Question / front").value).toBe("What is an API?");

    await user.click(screen.getByRole("button", { name: "Back to study" }));
    expect(screen.getByText("What is an API?")).toBeTruthy();
    expect(screen.queryByLabelText("Question / front")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Back to decks" }));
    expect(screen.getByRole("heading", { name: "Decks" })).toBeTruthy();
  });
});
