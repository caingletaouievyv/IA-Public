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
  extractPptxText: vi.fn(),
  extractImageText: vi.fn(),
  updateNote: vi.fn(),
  deleteNote: vi.fn(),
}));

import { createNote, extractImageText, extractPdfText, extractPptxText, listNotes } from "./api.js";

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
    expect(screen.getByRole("button", { name: "Import PPTX" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Import screenshots" })).toBeTruthy();
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
    expect(createNote).not.toHaveBeenCalled();
  });

  it("appends PDF text after content the user already typed", async () => {
    extractPdfText.mockResolvedValue({ text: "Hello PDF", char_count: 9, page_count: 1 });
    const user = userEvent.setup();
    render(<Notes />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    await clickAddNoteEntry(user);
    await user.type(screen.getByLabelText(/^Content/i), "Already here");
    await user.click(screen.getByRole("button", { name: "Import PDF" }));
    const dialog = screen.getByRole("dialog", { name: /Import PDF/i });
    await user.upload(within(dialog).getByLabelText(/^PDF file$/i), new File(["%PDF"], "sample.pdf", { type: "application/pdf" }));
    await user.click(within(dialog).getByRole("button", { name: "Extract PDF text" }));
    await waitFor(() => expect(screen.getByLabelText(/^Content/i).value).toBe("Already here\n\nHello PDF"));
  });

  it("shows Extracting while a PDF import is running", async () => {
    let finish;
    extractPdfText.mockReturnValue(new Promise((resolve) => {
      finish = resolve;
    }));
    const user = userEvent.setup();
    render(<Notes />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    await clickAddNoteEntry(user);
    await user.click(screen.getByRole("button", { name: "Import PDF" }));
    const dialog = screen.getByRole("dialog", { name: /Import PDF/i });
    await user.upload(within(dialog).getByLabelText(/^PDF file$/i), new File(["%PDF"], "sample.pdf", { type: "application/pdf" }));
    await user.click(within(dialog).getByRole("button", { name: "Extract PDF text" }));
    expect(within(dialog).getByRole("button", { name: "Extracting…" }).disabled).toBe(true);
    finish({ text: "Hello PDF", page_count: 1 });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /Import PDF/i })).toBeNull());
  });

  it("imports PPTX text into content and shows an error without saving", async () => {
    extractPptxText.mockResolvedValue({ text: "--- Slide 1 ---\nMitosis", slide_count: 1, char_count: 20 });
    const user = userEvent.setup();
    render(<Notes />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    await clickAddNoteEntry(user);
    await user.type(screen.getByLabelText(/^Content/i), "Notes");
    await user.click(screen.getByRole("button", { name: "Import PPTX" }));
    const dialog = screen.getByRole("dialog", { name: /Import PPTX/i });
    await user.upload(within(dialog).getByLabelText(/^PPTX file$/i), new File(["PK"], "lesson.pptx"));
    await user.click(within(dialog).getByRole("button", { name: "Extract PPTX text" }));
    await waitFor(() => expect(screen.getByLabelText(/^Content/i).value).toBe("Notes\n\n--- Slide 1 ---\nMitosis"));
    expect(screen.getByText(/PPTX text imported — 1 slide/i)).toBeTruthy();
    expect(createNote).not.toHaveBeenCalled();

    extractPptxText.mockRejectedValue(new Error("Bad PPTX"));
    await user.click(screen.getByRole("button", { name: "Import PPTX" }));
    const failed = screen.getByRole("dialog", { name: /Import PPTX/i });
    await user.upload(within(failed).getByLabelText(/^PPTX file$/i), new File(["PK"], "bad.pptx"));
    await user.click(within(failed).getByRole("button", { name: "Extract PPTX text" }));
    await waitFor(() => expect(screen.getByText("Bad PPTX")).toBeTruthy());
    expect(screen.getByLabelText(/^Content/i).value).toBe("Notes\n\n--- Slide 1 ---\nMitosis");
  });

  it("imports screenshots in selected order and shows an error without saving", async () => {
    extractImageText.mockResolvedValue({ text: "Alpha\n\nBeta", image_count: 2, char_count: 10 });
    const user = userEvent.setup();
    render(<Notes />);
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    await clickAddNoteEntry(user);
    await user.click(screen.getByRole("button", { name: "Import screenshots" }));
    const dialog = screen.getByRole("dialog", { name: /Import screenshots/i });
    const input = within(dialog).getByLabelText(/^Screenshot files$/i);
    await user.upload(input, [
      new File(["a"], "first.png", { type: "image/png" }),
      new File(["b"], "second.png", { type: "image/png" }),
    ]);
    await user.click(within(dialog).getByRole("button", { name: "Extract screenshot text" }));
    await waitFor(() => expect(extractImageText).toHaveBeenCalled());
    const form = extractImageText.mock.calls[0][0];
    expect(form.getAll("files").map((file) => file.name)).toEqual(["first.png", "second.png"]);
    expect(screen.getByLabelText(/^Content/i).value).toBe("Alpha\n\nBeta");
    expect(screen.getByText(/Screenshot text imported — 2 images/i)).toBeTruthy();
    expect(createNote).not.toHaveBeenCalled();

    extractImageText.mockRejectedValue(new Error("OCR unavailable"));
    await user.click(screen.getByRole("button", { name: "Import screenshots" }));
    const failed = screen.getByRole("dialog", { name: /Import screenshots/i });
    await user.upload(within(failed).getByLabelText(/^Screenshot files$/i), new File(["a"], "scan.png", { type: "image/png" }));
    await user.click(within(failed).getByRole("button", { name: "Extract screenshot text" }));
    await waitFor(() => expect(screen.getByText("OCR unavailable")).toBeTruthy());
    expect(screen.getByLabelText(/^Content/i).value).toBe("Alpha\n\nBeta");
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
