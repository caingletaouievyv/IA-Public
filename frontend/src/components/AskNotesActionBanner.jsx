// IA/frontend/src/components/AskNotesActionBanner.jsx
// Compact Notes action status above the assistant message body.

import {
  createdNoteIdFromAction,
  normalizeNotesAction,
  notesActionDisplayMessage,
  notesActionHeadline,
  notesActionVariant,
} from "../notesActionUi";

export default function AskNotesActionBanner({
  notesAction,
  fallbackContent = "",
  onApplySuggestionDraft,
  onOpenCreatedNote,
}) {
  const normalized = normalizeNotesAction(notesAction);
  if (!normalized) return null;

  const variant = notesActionVariant(normalized);
  const headline = notesActionHeadline(normalized);
  const body = notesActionDisplayMessage(normalized, fallbackContent);

  return (
    <div
      className={`ask-notes-action ask-notes-action--${variant}`}
      role="status"
      aria-live="polite"
    >
      <div className="ask-notes-action__headline">{headline}</div>
      {body ? <p className="ask-notes-action__message">{body}</p> : null}
      {normalized.status === "confirm_required" && normalized.confirmTitle ? (
        <p className="ask-notes-action__hint">
          Type the exact title to confirm: <strong>{normalized.confirmTitle}</strong>
        </p>
      ) : null}
      {createdNoteIdFromAction(notesAction) ? (
        <p className="ask-notes-action__open-note">
          <button
            type="button"
            className="link-button ask-notes-action__open-note-link"
            onClick={() => onOpenCreatedNote?.(createdNoteIdFromAction(notesAction))}
          >
            Open created note →
          </button>
        </p>
      ) : null}
      {normalized.status === "clarify" && normalized.suggestions?.length ? (
        <div className="ai-suggestion__actions ask-notes-action__suggestions">
          {normalized.suggestions.map((item) => (
            <button
              key={item.label}
              type="button"
              className="button-secondary"
              onClick={() => onApplySuggestionDraft?.(item.draft)}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
