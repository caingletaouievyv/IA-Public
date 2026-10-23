// IA/frontend/src/askReportAnswer.test.jsx
// Ask answer feedback submits allow-listed metadata only.

// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { reportAiFeedback, setToken } from "./api.js";
import { parseMessages } from "./components/Ask.jsx";

function tokenFor(userId) {
  const payload = btoa(JSON.stringify({ sub: userId }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `header.${payload}.signature`;
}

describe("Ask history message parsing", () => {
  it("preserves operationId from saved operation_id values", () => {
    const messages = parseMessages(JSON.stringify([
      { role: "user", content: "Question" },
      { role: "assistant", content: "Answer", operation_id: "ask-op-99" },
    ]));
    expect(messages[1].operationId).toBe("ask-op-99");
  });
});

describe("Ask report answer API", () => {
  beforeEach(() => {
    setToken(tokenFor("user-1"));
  });

  it("submits the selected reason with the completed Ask operation_id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ status: "recorded", event_id: "evt-1" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await reportAiFeedback("ask-op-42", "unhelpful");

    expect(result).toEqual({ status: "recorded", event_id: "evt-1" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/diagnostics/feedback");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({
      operation_id: "ask-op-42",
      feature: "ask",
      reason: "unhelpful",
    });
  });

  it("surfaces server errors without echoing conversation content", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: async () => ({ error: "Unknown or incomplete Ask operation" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(reportAiFeedback("missing-op", "wrong")).rejects.toThrow(
      "Unknown or incomplete Ask operation",
    );
  });
});
