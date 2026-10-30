// IA/frontend/src/AskNotesActionBanner.test.jsx
// Ask Notes action banner: created-note shortcut uses note id.

// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AskNotesActionBanner from "./components/AskNotesActionBanner.jsx";

describe("AskNotesActionBanner", () => {
  afterEach(() => cleanup());

  it("shows Open created note when create_note executed with note id", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(
      <AskNotesActionBanner
        notesAction={{
          status: "executed",
          action: "create_note",
          message: "Created note \"test\" in category general with an empty body.",
          note: { id: "note-abc-123", title: "test", category: "general", content: "" },
        }}
        onOpenCreatedNote={onOpen}
      />,
    );
    const link = screen.getByRole("button", { name: "Open created note →" });
    await user.click(link);
    expect(onOpen).toHaveBeenCalledWith("note-abc-123");
  });

  it("uses note id for shortcut when duplicate titles exist", () => {
    render(
      <AskNotesActionBanner
        notesAction={{
          status: "executed",
          action: "create_note",
          message: "Created.",
          note: { id: "unique-id-2", title: "test", category: "general", content: "" },
        }}
        onOpenCreatedNote={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Open created note →" })).toBeTruthy();
  });

  it("does not show Open created note without executed create or note id", () => {
    render(
      <AskNotesActionBanner
        notesAction={{
          status: "clarify",
          action: "create_note",
          message: "Need a title.",
        }}
        onOpenCreatedNote={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "Open created note →" })).toBeNull();
  });
});
