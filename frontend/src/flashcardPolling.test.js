import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  FlashcardPollTimeoutError,
  generateFlashcards,
  pollFlashcardGeneration,
} from "./api.js";

const pendingPayload = {
  status: "pending",
  operation_id: "pending-op",
  progress: { current_batch: 1, total_batches: 3, card_count: 10 },
};

describe("flashcard polling", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("poll timeout throws without starting a new POST generation", async () => {
    const requests = [];
    vi.stubGlobal("fetch", vi.fn(async (url, options = {}) => {
      requests.push({ url: String(url), method: options.method || "GET" });
      return {
        status: 202,
        ok: true,
        json: async () => pendingPayload,
      };
    }));
    await expect(
      pollFlashcardGeneration("pending-op", { maxDurationMs: 0 }),
    ).rejects.toMatchObject({
      name: "FlashcardPollTimeoutError",
      operationId: "pending-op",
    });
    expect(requests.every((item) => item.method === "GET")).toBe(true);
  });

  it("resume polling uses GET only and does not POST", async () => {
    const requests = [];
    let polls = 0;
    vi.stubGlobal("fetch", vi.fn(async (url, options = {}) => {
      requests.push({ url: String(url), method: options.method || "GET" });
      if (options.method === "POST") {
        throw new Error("resume should not POST");
      }
      polls += 1;
      if (polls >= 2) {
        return {
          status: 200,
          ok: true,
          json: async () => ({
            status: "completed",
            operation_id: "pending-op",
            cards: [{ question: "Q?", answer: "A." }],
          }),
        };
      }
      return {
        status: 202,
        ok: true,
        json: async () => pendingPayload,
      };
    }));
    const result = await generateFlashcards(
      { operation_id: "pending-op" },
      { maxDurationMs: 60_000 },
    );
    expect(result.cards).toHaveLength(1);
    expect(requests.some((item) => item.method === "POST")).toBe(false);
  });
});
