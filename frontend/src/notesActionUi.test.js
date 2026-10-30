// IA/frontend/src/notesActionUi.test.js
// Notes action UI mapping for Ask responses.

import { describe, expect, it } from "vitest";
import {
  createdNoteIdFromAction,
  normalizeNotesAction,
  notesActionHeadline,
  notesActionVariant,
} from "./notesActionUi.js";

describe("notesActionUi", () => {
  it("maps executed create to success variant", () => {
    const normalized = normalizeNotesAction({
      status: "executed",
      action: "create_note",
      message: 'Created note "Todo".',
    });
    expect(notesActionVariant(normalized)).toBe("success");
    expect(notesActionHeadline(normalized)).toContain("created");
  });

  it("maps confirm_required with pending title", () => {
    const normalized = normalizeNotesAction({
      status: "confirm_required",
      action: "delete_note",
      message: 'Are you sure? Type the exact title to confirm.',
      pending: { title: "Budget" },
    });
    expect(notesActionVariant(normalized)).toBe("pending");
    expect(normalized.confirmTitle).toBe("Budget");
    expect(notesActionHeadline(normalized)).toContain("confirm");
  });

  it("keeps clarify suggestions from notes_action", () => {
    const normalized = normalizeNotesAction({
      status: "clarify",
      action: "create_note",
      message: "Need a title.",
      suggestions: [{ label: "Blank body", draft: "Title: X. Leave blank." }],
    });
    expect(normalized.suggestions).toHaveLength(1);
    expect(normalized.suggestions[0].label).toBe("Blank body");
  });

  it("returns note id for executed create_note only", () => {
    expect(
      createdNoteIdFromAction({
        status: "executed",
        action: "create_note",
        note: { id: "id-a", title: "dup" },
      }),
    ).toBe("id-a");
    expect(
      createdNoteIdFromAction({
        status: "executed",
        action: "create_note",
        note: { id: "id-b", title: "dup" },
      }),
    ).toBe("id-b");
    expect(
      createdNoteIdFromAction({
        status: "executed",
        action: "update_note",
        note: { id: "id-c" },
      }),
    ).toBeNull();
    expect(createdNoteIdFromAction({ status: "failed", action: "create_note" })).toBeNull();
  });

  it("maps failed status to error variant", () => {
    const normalized = normalizeNotesAction({
      status: "failed",
      action: "update_note",
      message: "The note could not be updated.",
    });
    expect(notesActionVariant(normalized)).toBe("error");
  });
});
