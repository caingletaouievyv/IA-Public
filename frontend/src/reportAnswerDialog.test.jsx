// IA/frontend/src/reportAnswerDialog.test.jsx
// Report answer modal: reason selection, submit, and error states.

// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReportAnswerDialog, { REPORT_ANSWER_REASONS } from "./components/ReportAnswerDialog.jsx";

function renderDialog(overrides = {}) {
  const props = {
    reason: "wrong",
    status: "idle",
    message: "",
    operationId: "ask-op-1",
    onReasonChange: vi.fn(),
    onSubmit: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
  render(<ReportAnswerDialog {...props} />);
  return props;
}

describe("ReportAnswerDialog", () => {
  afterEach(() => cleanup());

  it("lists the four allow-listed report reasons", () => {
    renderDialog();
    expect(REPORT_ANSWER_REASONS).toHaveLength(4);
    for (const option of REPORT_ANSWER_REASONS) {
      expect(screen.getByRole("button", { name: new RegExp(option.label, "i") })).toBeTruthy();
    }
  });

  it("opens as an accessible dialog and closes on Cancel", async () => {
    const user = userEvent.setup();
    const props = renderDialog();
    const dialog = screen.getByRole("dialog", { name: /report answer/i });
    const footer = dialog.querySelector(".notes-delete-confirm__actions");
    await user.click(within(footer).getByRole("button", { name: /^cancel$/i }));
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("updates the selected reason", async () => {
    const user = userEvent.setup();
    const props = renderDialog();
    await user.click(screen.getByRole("button", { name: /unhelpful/i }));
    expect(props.onReasonChange).toHaveBeenCalledWith("unhelpful");
  });

  it("submits when Send report is clicked", async () => {
    const user = userEvent.setup();
    const props = renderDialog({ reason: "harmful" });
    const dialog = screen.getByRole("dialog", { name: /report answer/i });
    await user.click(within(dialog).getByRole("button", { name: /^send report$/i }));
    expect(props.onSubmit).toHaveBeenCalledTimes(1);
  });

  it("disables submit without a completed operation id", () => {
    renderDialog({ operationId: null });
    const dialog = screen.getByRole("dialog", { name: /report answer/i });
    expect(within(dialog).getByRole("button", { name: /^send report$/i }).disabled).toBe(true);
    expect(within(dialog).getByRole("alert").textContent).toMatch(/cannot be reported yet/i);
  });

  it("shows submitting, success, and error feedback", () => {
    const { rerender } = render(
      <ReportAnswerDialog
        reason="wrong"
        status="submitting"
        message=""
        operationId="ask-op-1"
        onReasonChange={vi.fn()}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const dialog = screen.getByRole("dialog", { name: /report answer/i });
    expect(within(dialog).getByRole("button", { name: /^sending/i }).disabled).toBe(true);

    rerender(
      <ReportAnswerDialog
        reason="wrong"
        status="success"
        message="Report received. Thank you."
        operationId="ask-op-1"
        onReasonChange={vi.fn()}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole("status").textContent).toMatch(/report received/i);

    rerender(
      <ReportAnswerDialog
        reason="wrong"
        status="error"
        message="Could not send report."
        operationId="ask-op-1"
        onReasonChange={vi.fn()}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert").textContent).toMatch(/could not send report/i);
  });
});
