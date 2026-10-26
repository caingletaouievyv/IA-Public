// IA/frontend/src/adminFrontend.test.jsx
// Admin navigation, user management, and diagnostics dashboard.

// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App.jsx";
import AdminDiagnostics from "./components/AdminDiagnostics.jsx";
import AdminUsers from "./components/AdminUsers.jsx";
import { setToken } from "./api.js";

const USER_ID = "admin-user-1";

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
    json: async () => structuredClone(data),
  };
}

function installFetch({
  role = "user",
  users = [],
  events = [],
  usersError = null,
  eventsError = null,
  promoteError = null,
  demoteError = null,
} = {}) {
  const fetchMock = vi.fn(async (input, options = {}) => {
    const url = new URL(input, window.location.origin);
    const method = options.method || "GET";

    if (url.pathname === "/auth/me" && method === "GET") {
      return jsonResponse({ user_id: USER_ID, username: "operator", role });
    }
    if (url.pathname === "/settings/" && method === "GET") {
      return jsonResponse({ theme: "dark", ask_context_sources: ["conversation"] });
    }
    if (url.pathname === "/admin/users" && method === "GET") {
      if (usersError) return jsonResponse({ error: usersError }, 403);
      return jsonResponse({ users });
    }
    const promoteMatch = url.pathname.match(/^\/admin\/users\/([^/]+)\/promote$/);
    if (promoteMatch && method === "POST") {
      if (promoteError) return jsonResponse({ error: promoteError }, 400);
      const promotedId = decodeURIComponent(promoteMatch[1]);
      const user = users.find((item) => item.user_id === promotedId);
      return jsonResponse({ ...user, role: "admin" });
    }
    const demoteMatch = url.pathname.match(/^\/admin\/users\/([^/]+)\/demote$/);
    if (demoteMatch && method === "POST") {
      if (demoteError) return jsonResponse({ error: demoteError }, 400);
      const demotedId = decodeURIComponent(demoteMatch[1]);
      const user = users.find((item) => item.user_id === demotedId);
      return jsonResponse({ ...user, role: "user" });
    }
    if (url.pathname === "/diagnostics/events" && method === "GET") {
      if (eventsError) return jsonResponse({ error: eventsError }, 403);
      return jsonResponse({ events });
    }
    if (url.pathname === "/notes/meta") return jsonResponse({ categories: [], tags: [] });
    if (url.pathname === "/notes/" && method === "GET") return jsonResponse([]);
    if (url.pathname === "/memories/" && method === "GET") return jsonResponse([]);
    if (url.pathname === "/activity/" && method === "GET") return jsonResponse([]);
    if (url.pathname === "/ai/suggestions" && method === "POST") {
      return jsonResponse({ suggestion: null });
    }
    throw new Error(`Unexpected API request: ${method} ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderApp(path = "/ask") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

beforeEach(() => {
  localStorage.clear();
  setToken(tokenFor(USER_ID));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App admin navigation", () => {
  it("hides admin links for standard users", async () => {
    installFetch({ role: "user" });
    renderApp("/ask");
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Ask" })).toBeTruthy();
    });
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Diagnostics" })).toBeNull();
  });

  it("shows Diagnostics for admin and Users plus Diagnostics for main_admin", async () => {
    installFetch({ role: "admin" });
    renderApp("/ask");
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Diagnostics" })).toBeTruthy();
    });
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();

    cleanup();
    installFetch({ role: "main_admin" });
    renderApp("/ask");
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Users" })).toBeTruthy();
      expect(screen.getByRole("link", { name: "Diagnostics" })).toBeTruthy();
    });
  });

  it("redirects non-main_admin away from /admin/users", async () => {
    installFetch({ role: "admin" });
    renderApp("/admin/users");
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Ask" }).getAttribute("aria-current")).toBe("page");
    });
    expect(screen.queryByText(/Promote trusted users/i)).toBeNull();
  });
});

describe("AdminUsers", () => {
  it("lists users, confirms promotion, and refreshes", async () => {
    const users = [
      { user_id: "u1", username: "alice", role: "user" },
      { user_id: "u2", username: "bob", role: "admin" },
    ];
    const fetchMock = installFetch({ role: "main_admin", users });
    render(<AdminUsers />);

    await waitFor(() => {
      expect(screen.getByText("alice")).toBeTruthy();
      expect(screen.getByText("bob")).toBeTruthy();
    });
    expect(screen.getByRole("button", { name: /Promote to Admin/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Demote to User/i })).toBeTruthy();
    expect(screen.queryAllByRole("button", { name: /Promote to Admin/i })).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: /Promote to Admin/i }));
    let dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Promote" }));

    await waitFor(() => {
      expect(screen.getByText(/Promoted alice to admin/i)).toBeTruthy();
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/promote"))).toBe(true);
  });

  it("confirms demotion and updates the listed role", async () => {
    const users = [
      { user_id: "u1", username: "alice", role: "user" },
      { user_id: "u2", username: "bob", role: "admin" },
    ];
    installFetch({ role: "main_admin", users });
    render(<AdminUsers />);

    await waitFor(() => {
      expect(screen.getByText("bob")).toBeTruthy();
    });

    await userEvent.click(screen.getByRole("button", { name: /Demote to User/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Demote" }));

    await waitFor(() => {
      expect(screen.getByText(/Demoted bob to user/i)).toBeTruthy();
    });
    const bobRow = screen.getByText("bob").closest("tr");
    expect(within(bobRow).getByText("user")).toBeTruthy();
  });

  it("shows error when user list fails", async () => {
    installFetch({ role: "main_admin", usersError: "Forbidden" });
    render(<AdminUsers />);
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/Forbidden/i);
    });
  });

  it("shows empty state when no users", async () => {
    installFetch({ role: "main_admin", users: [] });
    render(<AdminUsers />);
    await waitFor(() => {
      expect(screen.getByText(/No users found/i)).toBeTruthy();
    });
  });
});

describe("AdminDiagnostics", () => {
  it("loads and displays safe event metadata", async () => {
    installFetch({
      role: "admin",
      events: [{
        event_id: "evt-1",
        timestamp: "2026-10-01T12:00:00Z",
        kind: "automatic",
        feature: "ask",
        code: "provider_error",
        category: "ai",
        fallback: true,
        error_type: "timeout",
        user_key_prefix: "abcd1234",
      }],
    });
    render(<AdminDiagnostics />);
    await waitFor(() => {
      expect(screen.getByText("provider_error")).toBeTruthy();
      expect(screen.getByText("abcd1234")).toBeTruthy();
    });
    expect(screen.queryByText(/password/i)).toBeNull();
  });

  it("shows empty and error states", async () => {
    installFetch({ role: "admin", events: [] });
    render(<AdminDiagnostics />);
    await waitFor(() => {
      expect(screen.getByText(/No diagnostic events yet/i)).toBeTruthy();
    });

    cleanup();
    installFetch({ role: "admin", eventsError: "Forbidden" });
    render(<AdminDiagnostics />);
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/Forbidden/i);
    });
  });
});
