// IA/frontend/src/components/ReportAnswerDialog.jsx
// Modal for allow-listed Ask answer feedback; metadata only, no conversation text.

import AskOverlay from "./AskOverlay";

export const REPORT_ANSWER_REASONS = [
  { value: "wrong", label: "Wrong answer", description: "The answer was incorrect or misleading." },
  { value: "unhelpful", label: "Unhelpful", description: "The answer did not address what I needed." },
  { value: "harmful", label: "Harmful or unsafe", description: "The answer felt unsafe or inappropriate." },
  { value: "other", label: "Other issue", description: "Something else went wrong with this response." },
];

export default function ReportAnswerDialog({
  reason,
  status,
  message,
  operationId,
  onReasonChange,
  onSubmit,
  onClose,
}) {
  const submitting = status === "submitting";
  const succeeded = status === "success";
  const canSubmit = Boolean(operationId) && !submitting && !succeeded;

  return (
    <AskOverlay
      title="Report answer"
      onClose={onClose}
      showManage={false}
      canClose={!submitting}
      closeText="Cancel"
    >
      <p className="notes-delete-confirm__desc">
        Tell us what went wrong. IA stores only the report reason and Ask reference, not your message text.
      </p>
      {!operationId ? (
        <div className="out out--compact err" role="alert">
          This answer cannot be reported yet. Ask a new question in this conversation, then try again.
        </div>
      ) : null}
      <div role="radiogroup" aria-label="Report reason" className="ask-shortcuts-section__content">
        {REPORT_ANSWER_REASONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`button-subtle flashcards-shortcut${reason === option.value ? " ask-shortcut--active" : ""}`}
            aria-pressed={reason === option.value}
            onClick={() => onReasonChange(option.value)}
            disabled={submitting || succeeded}
          >
            <strong>{option.label}</strong>
            <span>{option.description}</span>
          </button>
        ))}
      </div>
      {status === "error" && message ? (
        <div className="out out--compact err" role="alert">{message}</div>
      ) : null}
      {succeeded && message ? (
        <div className="out out--compact success-msg" role="status">{message}</div>
      ) : null}
      <div className="notes-delete-confirm__actions">
        <button type="button" className="button-subtle" onClick={onClose} disabled={submitting}>
          {succeeded ? "Close" : "Cancel"}
        </button>
        <button
          type="button"
          className="button-primary"
          onClick={onSubmit}
          disabled={!canSubmit}
        >
          {submitting ? "Sending…" : succeeded ? "Sent" : "Send report"}
        </button>
      </div>
    </AskOverlay>
  );
}
