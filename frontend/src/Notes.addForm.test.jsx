// IA/frontend/src/Notes.addForm.test.jsx
// Unified Add Note form: compact Import PDF overlay, optional extract into content.

// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Notes from "./components/Notes.jsx";

vi.mock("./api.js", () => ({
  listNotes: vi.fn(() => Promise.resolve([])),
  getNotesMeta: vi.fn(() => Promise.resolve({ categories: ["general"], tags: [] })),
  createNote: vi.fn(),
  extractPdfText: vi.fn(),
  updateNote: vi.fn(),
  deleteNote: vi.fn(),
}));

import { createNote, extractPdfText, listNotes } from "./api.js";

function clickAddNoteEntry(user) {
  return user.click(screen.getAllByRole("button", { name: "Add note" })[0]);
}

describe("Notes unified Add Note form", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    listNotes.mockResolvedValue([]);
  });

  it("exposes one Add note entry with Import PDF beside Content", async () => {
    const user = userEvent.setup();
    render(<Notes />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Add note" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add from images" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add from PDF" })).toBeNull();
    await clickAddNoteEntry(user);
    expect(screen.getByLabelText(/^Title$/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Import PDF" })).toBeTruthy();
    expect(screen.queryByText(/Import text \(optional\)/i)).toBeNull();
    expect(screen.queryByLabelText(/^Upload PDF$/i)).toBeNull();
    expect(screen.queryByRole("button", { name: "Extract image text" })).toBeNull();
  });

  it("allows saving with title and category only (empty content)", async () => {
    createNote.mockResolvedValue({ id: "n1", title: "Blank", category: "general", content: "" });
    const user = userEvent.setup();
    render(<Notes />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    await clickAddNoteEntry(user);
    await user.type(screen.getByLabelText(/^Title$/i), "Blank");
    await user.type(screen.getByLabelText(/^Category$/i), "general");
    const saveButtons = screen.getAllByRole("button", { name: "Add note" });
    await user.click(saveButtons[saveButtons.length - 1]);
    await waitFor(() => expect(createNote).toHaveBeenCalledWith({
      title: "Blank",
      category: "general",
      content: "",
      tags: [],
    }));
  });

  it("opens Import PDF dialog, extracts text into content, and shows success", async () => {
    extractPdfText.mockResolvedValue({ text: "Hello PDF", char_count: 9, page_count: 31 });
    const user = userEvent.setup();
    render(<Notes />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    await clickAddNoteEntry(user);
    await user.click(screen.getByRole("button", { name: "Import PDF" }));
    const dialog = screen.getByRole("dialog", { name: /Import PDF/i });
    const pdfInput = within(dialog).getByLabelText(/^PDF file$/i);
    const file = new File(["%PDF"], "sample.pdf", { type: "application/pdf" });
    await user.upload(pdfInput, file);
    expect(within(dialog).getByText("sample.pdf")).toBeTruthy();
    await user.click(within(dialog).getByRole("button", { name: "Extract PDF text" }));
    await waitFor(() => expect(extractPdfText).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /Import PDF/i })).toBeNull());
    expect(screen.getByLabelText(/^Content/i).value).toBe("Hello PDF");
    expect(screen.getByText(/PDF text imported — 31 pages/i)).toBeTruthy();
  });

  it("shows extract errors in the dialog and Cancel closes without changing content", async () => {
    extractPdfText.mockRejectedValue(new Error("Bad PDF"));
    const user = userEvent.setup();
    render(<Notes />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    await clickAddNoteEntry(user);
    await user.click(screen.getByRole("button", { name: "Import PDF" }));
    const dialog = screen.getByRole("dialog", { name: /Import PDF/i });
    const pdfInput = within(dialog).getByLabelText(/^PDF file$/i);
    await user.upload(pdfInput, new File(["%PDF"], "bad.pdf", { type: "application/pdf" }));
    await user.click(within(dialog).getByRole("button", { name: "Extract PDF text" }));
    await waitFor(() => expect(screen.getByText("Bad PDF")).toBeTruthy());
    expect(screen.getByLabelText(/^Content/i).value).toBe("");
    await user.click(within(dialog).getByRole("button", { name: "Close Import PDF" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /Import PDF/i })).toBeNull());
  });
});
