// IA/frontend/src/manageNoteFocus.test.jsx
// Deep-link focus: /manage?note=<id> opens the matching note by id.

// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App.jsx";
import { setToken } from "./api.js";

const USER_ID = "user-focus";
const NOTE_A = { id: "id-alpha", title: "dup", category: "general", content: "A", tags: [] };
const NOTE_B = { id: "id-beta", title: "dup", category: "work", content: "B", tags: [] };

function tokenFor(userId) {
  const payload = btoa(JSON.stringify({ sub: userId }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `header.${payload}.signature`;
}

function jsonResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    json: async () => structuredClone(data),
  };
}

describe("Manage note focus by id", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (url) => {
      const path = typeof url === "string" ? url : url.url;
      if (path.includes("/auth/me")) {
        return jsonResponse({ user_id: USER_ID, username: "u", role: "user" });
      }
      if (path.includes("/notes/meta")) {
        return jsonResponse({ categories: ["general", "work"], tags: [] });
      }
      if (/\/notes\/?(\?|$)/.test(path) && !path.includes("/notes/meta") && !path.includes("from-")) {
        return jsonResponse([NOTE_A, NOTE_B]);
      }
      if (path.includes("/settings")) {
        return jsonResponse({});
      }
      if (path.includes("/activity")) {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({});
    }));
    setToken(tokenFor(USER_ID));
    window.history.replaceState(null, "", `/manage?note=${encodeURIComponent(NOTE_B.id)}`);
  });

  it("opens the note matching query id when duplicate titles exist", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Notes" }).getAttribute("aria-pressed")).toBe("true"));
    await waitFor(() => expect(screen.getByLabelText(/^Title$/i).value).toBe("dup"));
    await waitFor(() => expect(screen.getByLabelText(/^Category$/i).value).toBe("work"));
    expect(screen.getByLabelText(/^Content/i).value).toBe("B");
  });

  it("shows a message and clears the query when the note id is missing", async () => {
    window.history.replaceState(null, "", "/manage?note=missing-note-id");
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Notes" }).getAttribute("aria-pressed")).toBe("true"));
    expect(await screen.findByText(/could not be found/i)).toBeTruthy();
    expect(window.location.pathname).toBe("/manage");
    expect(window.location.search).toBe("");
  });
});
