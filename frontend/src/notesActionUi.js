// IA/frontend/src/notesActionUi.js
// Map Ask notes_action payloads to compact UI labels and status variants.

const ACTION_LABELS = {
  list_notes: "Listed notes",
  create_note: "Note created",
  update_note: "Note updated",
  delete_note: "Delete note",
  feature_question: "Notes help",
};

/** @param {Record<string, unknown> | null | undefined} notesAction */
export function normalizeNotesAction(notesAction) {
  if (!notesAction || typeof notesAction !== "object") return null;
  const status = typeof notesAction.status === "string" ? notesAction.status.trim() : "";
  if (!status) return null;
  const message = typeof notesAction.message === "string" ? notesAction.message.trim() : "";
  const action = typeof notesAction.action === "string" ? notesAction.action.trim() : "";
  const pending = notesAction.pending && typeof notesAction.pending === "object"
    ? notesAction.pending
    : null;
  const confirmTitle = pending && typeof pending.title === "string" ? pending.title.trim() : "";
  const suggestions = Array.isArray(notesAction.suggestions)
    ? notesAction.suggestions.filter(
      (item) => item && typeof item.label === "string" && typeof item.draft === "string",
    )
    : [];
  return { status, message, action, confirmTitle, suggestions };
}

/** @param {ReturnType<typeof normalizeNotesAction>} normalized */
export function notesActionVariant(normalized) {
  if (!normalized) return null;
  switch (normalized.status) {
    case "executed":
    case "answered":
      return "success";
    case "clarify":
    case "confirm_required":
      return "pending";
    case "cancelled":
      return "muted";
    case "confirm_failed":
    case "failed":
      return "error";
    default:
      return "muted";
  }
}

/** @param {ReturnType<typeof normalizeNotesAction>} normalized */
export function notesActionHeadline(normalized) {
  if (!normalized) return "";
  const { status, action } = normalized;
  if (status === "clarify") return "Notes — more detail needed";
  if (status === "confirm_required") return "Notes — confirm deletion";
  if (status === "confirm_failed") return "Notes — confirmation failed";
  if (status === "cancelled") return "Notes — deletion cancelled";
  if (status === "failed") return "Notes — action failed";
  if (action && ACTION_LABELS[action]) return `Notes — ${ACTION_LABELS[action]}`;
  if (status === "answered") return "Notes";
  if (status === "executed") return "Notes — done";
  return "Notes";
}

/** @param {ReturnType<typeof normalizeNotesAction>} normalized */
/** @param {Record<string, unknown> | null | undefined} notesAction */
export function createdNoteIdFromAction(notesAction) {
  if (!notesAction || typeof notesAction !== "object") return null;
  if (notesAction.action !== "create_note" || notesAction.status !== "executed") return null;
  const note = notesAction.note;
  if (!note || typeof note !== "object") return null;
  const id = note.id;
  return typeof id === "string" && id.trim() ? id.trim() : null;
}

export function notesActionDisplayMessage(normalized, fallbackContent = "") {
  if (!normalized) return fallbackContent;
  if (normalized.message) return normalized.message;
  return fallbackContent;
}
