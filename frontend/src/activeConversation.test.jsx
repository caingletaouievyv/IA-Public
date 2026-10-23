// IA/frontend/src/activeConversation.test.jsx
// Authenticated App and Ask conversation restoration regressions.

// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App.jsx";
import Login from "./components/Login.jsx";
import { getCachedSettings, getSettings, putSettings, setToken } from "./api";

const USER_ID = "user-1";
const STORAGE_KEY = `ia:active-conversation:${USER_ID}`;
const NOTE_SELECTION_KEY = `ia:selected-note-ids:${USER_ID}`;

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
    statusText: status === 404 ? "Not Found" : "OK",
    json: async () => structuredClone(data),
  };
}

function makeHistory(id, title, messages = []) {
  return {
    id,
    title,
    category: "_history",
    tags: [],
    content: JSON.stringify(messages),
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

let notes;
let settings;
let fetchMock;
let settingsGetGate;
let settingsPutGate;
let notesListGate;
let historyListGate;
let historyRequestError;
let memoriesRequestError;
let activityEvents;
let suggestionResponse;
let noteGetDelays;
let delayedNoteResolves;
let nextId;
let aiRequests;
let flashcardRequests;
let flashcardResponse;
let flashcardRequestGate;
let flashcardRequestError;
let noteSaveGate;
let createdNotes;

function installApiMock() {
  fetchMock = vi.fn(async (input, options = {}) => {
    const url = new URL(input, window.location.origin);
    const method = options.method || "GET";

    if (url.pathname === "/settings/" && method === "GET") {
      if (settingsGetGate) await settingsGetGate.promise;
      return jsonResponse(settings);
    }
    if (url.pathname === "/settings/" && method === "PUT") {
      if (settingsPutGate) await settingsPutGate.promise;
      settings = { ...settings, ...JSON.parse(options.body) };
      return jsonResponse(settings);
    }
    if (url.pathname === "/notes/meta") {
      return jsonResponse({ categories: [], tags: [] });
    }
    if (url.pathname === "/notes/" && method === "GET") {
      const category = url.searchParams.get("category");
      if (category === "_history" && historyListGate) await historyListGate.promise;
      if (category === "_history" && historyRequestError) {
        return jsonResponse({ error: "History unavailable" }, 500);
      }
      if (!category && notesListGate) await notesListGate.promise;
      const list = [...notes.values()].filter((note) => !category || note.category === category);
      return jsonResponse(list);
    }
    if (url.pathname === "/memories/" && method === "GET") {
      if (memoriesRequestError) return jsonResponse({ error: "Memory unavailable" }, 500);
      return jsonResponse([]);
    }
    if (url.pathname === "/activity/" && method === "GET") {
      return jsonResponse(activityEvents);
    }
    if (url.pathname === "/ai/suggestions" && method === "POST") {
      return jsonResponse({ suggestion: suggestionResponse });
    }
    if (url.pathname === "/notes/" && method === "POST") {
      if (noteSaveGate) await noteSaveGate.promise;
      const note = { ...JSON.parse(options.body), id: `new-${nextId++}` };
      notes.set(note.id, note);
      createdNotes.push(note);
      return jsonResponse(note, 201);
    }
    if (url.pathname.startsWith("/notes/")) {
      const noteId = decodeURIComponent(url.pathname.slice("/notes/".length));
      if (method === "GET") {
        if (noteGetDelays.has(noteId)) {
          const gate = deferred();
          delayedNoteResolves.set(noteId, gate);
          await gate.promise;
        }
        const note = notes.get(noteId);
        return note ? jsonResponse(note) : jsonResponse({ error: "Note not found" }, 404);
      }
      if (method === "PUT") {
        const note = notes.get(noteId);
        if (!note) return jsonResponse({ error: "Note not found" }, 404);
        Object.assign(note, JSON.parse(options.body));
        note.updated_at = "2026-10-14T00:00:00Z";
        return jsonResponse(note);
      }
      if (method === "DELETE") {
        notes.delete(noteId);
        return jsonResponse({ message: "Note deleted" });
      }
    }
    if (url.pathname === "/ai/ask" && method === "POST") {
      const request = JSON.parse(options.body);
      aiRequests.push(request);
      return jsonResponse({ answer: `Answer to ${request.question}`, memory_status: "disabled" });
    }
    if (url.pathname === "/ai/flashcards/generate" && method === "POST") {
      flashcardRequests.push(JSON.parse(options.body));
      if (flashcardRequestGate) await flashcardRequestGate.promise;
      if (flashcardRequestError) {
        return jsonResponse({ error: "Flashcard generation failed" }, 502);
      }
      return jsonResponse(flashcardResponse);
    }
    if (url.pathname === "/auth/login" && method === "POST") {
      return jsonResponse({ token: tokenFor("user-2"), user_id: "user-2" });
    }
    if (url.pathname === "/auth/me" && method === "GET") {
      return jsonResponse({ user_id: USER_ID, username: "testuser", role: "user" });
    }
    throw new Error(`Unexpected API request: ${method} ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function renderApp(userId = USER_ID, path = "/ask") {
  window.history.replaceState(null, "", path);
  setToken(tokenFor(userId));
  return render(<App />);
}

async function openConversationPicker(user) {
  await user.click(await screen.findByRole("button", { name: /^Conversation:/ }));
  return screen.findByRole("dialog", { name: "Conversations" });
}

async function selectConversation(user, title) {
  await openConversationPicker(user);
  await user.click(await screen.findByRole("button", { name: `Select conversation: ${title}` }));
}

async function navigateBetweenPages(user) {
  await user.click(screen.getByRole("link", { name: "Manage" }));
  expect(await screen.findByRole("heading", { name: "Manage saved content" })).toBeTruthy();
  await user.click(screen.getByRole("link", { name: "Ask" }));
}

async function openFlashcards(user) {
  await user.click(screen.getByText("Shortcuts"));
  await user.click(screen.getByRole("button", { name: /Flashcards/ }));
  return screen.findByRole("dialog", { name: "Flashcards" });
}

async function startNewFlashcards(user) {
  await openFlashcards(user);
  await user.click(await screen.findByRole("button", { name: "New Flashcards" }));
}

function getNotesModeButton(mode) {
  return screen.getByRole("button", {
    name: new RegExp(`^Notes context mode: ${mode}\\. Activate to change mode\\.$`),
  });
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  notes = new Map([
    ["note-a", {
      id: "note-a",
      title: "Study note",
      category: "study",
      content: "Selected note content",
      tags: [],
    }],
    ["first", makeHistory("first", "First conversation", [
      { role: "user", content: "First saved question" },
      { role: "assistant", content: "First saved answer" },
    ])],
    ["second", makeHistory("second", "Second conversation", [
      { role: "user", content: "Second saved question" },
      { role: "assistant", content: "Second saved answer" },
    ])],
  ]);
  settings = {
    ask_context_sources: ["conversation", "notes", "memory"],
    ask_context_modes: { notes: "off", memory: "off" },
    memory_enabled: false,
  };
  settingsGetGate = null;
  settingsPutGate = null;
  notesListGate = null;
  historyListGate = null;
  historyRequestError = false;
  memoriesRequestError = false;
  activityEvents = [];
  suggestionResponse = null;
  noteGetDelays = new Set();
  delayedNoteResolves = new Map();
  nextId = 1;
  aiRequests = [];
  flashcardRequests = [];
  flashcardResponse = {
    cards: [
      { question: "What is photosynthesis?", answer: "The process plants use to make food." },
      { question: "What does chlorophyll do?", answer: "It absorbs light for photosynthesis." },
    ],
  };
  flashcardRequestGate = null;
  flashcardRequestError = false;
  noteSaveGate = null;
  createdNotes = [];
  installApiMock();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("active conversation restoration", () => {
  it("keeps AI suggestions off unauthenticated routes", () => {
    setToken(null);
    window.history.replaceState(null, "", "/login");
    render(<App />);

    expect(screen.queryByRole("region", { name: "AI suggestion" })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the default-on AI Suggestions setting and persists user changes", async () => {
    const user = userEvent.setup();
    renderApp(USER_ID, "/settings");

    const enabled = await screen.findByRole("checkbox", { name: /Enable AI Suggestions/ });
    expect(enabled.checked).toBe(true);
    await user.click(enabled);
    await waitFor(() => expect(settings.ai_suggestions_enabled).toBe(false));
    expect(enabled.checked).toBe(false);
  });

  it("resumes suggestion generation when a saved-off preference is turned on", async () => {
    const user = userEvent.setup();
    settings.ai_suggestions_enabled = false;
    activityEvents = [
      { event_id: "event-b", event_type: "note.updated", description: "Note updated", timestamp: new Date().toISOString() },
      { event_id: "event-a", event_type: "note.created", description: "Note created", timestamp: new Date(Date.now() - 1000).toISOString() },
    ];
    suggestionResponse = {
      suggestion_id: "event-b|event-a",
      action: "prepare_ask",
      text: "Want to ask IA to summarize your recent note changes and suggest next steps?",
    };
    renderApp(USER_ID, "/settings");

    const enabled = await screen.findByRole("checkbox", { name: /Enable AI Suggestions/ });
    expect(enabled.checked).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) =>
      new URL(input, window.location.origin).pathname === "/ai/suggestions",
    )).toBe(false);

    await user.click(enabled);
    expect(await screen.findByRole("region", { name: "AI suggestion" })).toBeTruthy();
    expect(settings.ai_suggestions_enabled).toBe(true);
  });

  it("uses recent note activity to offer an actionable Flashcards shortcut", async () => {
    const user = userEvent.setup();
    activityEvents = [
      { event_id: "event-b", event_type: "note.updated", description: "Note updated", timestamp: new Date().toISOString() },
      { event_id: "event-a", event_type: "note.created", description: "Note created", timestamp: new Date(Date.now() - 1000).toISOString() },
    ];
    suggestionResponse = {
      suggestion_id: "event-b|event-a",
      action: "open_flashcards",
      text: "Turn your recent note activity into a focused flashcard session.",
    };
    renderApp();

    expect(await screen.findByRole("region", { name: "AI suggestion" })).toBeTruthy();
    expect(fetchMock.mock.calls.some(([input, options]) =>
      new URL(input, window.location.origin).pathname === "/ai/suggestions"
      && options.method === "POST",
    )).toBe(true);
    await user.click(screen.getByRole("button", { name: "Open Flashcards" }));
    expect(await screen.findByRole("dialog", { name: "Flashcards" })).toBeTruthy();
  });

  it("prepares an Ask draft when the user accepts a note-summary suggestion", async () => {
    const user = userEvent.setup();
    activityEvents = [
      { event_id: "event-b", event_type: "note.updated", description: "Note updated", timestamp: new Date().toISOString() },
      { event_id: "event-a", event_type: "note.created", description: "Note created", timestamp: new Date(Date.now() - 1000).toISOString() },
    ];
    suggestionResponse = {
      suggestion_id: "event-b|event-a",
      action: "prepare_ask",
      text: "Want to ask IA to summarize your recent note changes and suggest next steps?",
    };
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Prepare Ask" }));
    expect(screen.getByRole("textbox", { name: "Question" }).value)
      .toBe("Summarize my recent note changes and suggest practical next steps.");
    await waitFor(() => expect(settings.ask_context_modes.notes).toBe("automatic"));
  });

  it("opens Manage Notes when the user accepts a review suggestion", async () => {
    const user = userEvent.setup();
    activityEvents = [
      { event_id: "event-b", event_type: "note.deleted", description: "Note deleted", timestamp: new Date().toISOString() },
      { event_id: "event-a", event_type: "flashcard_deck.updated", description: "Flashcard deck updated", timestamp: new Date(Date.now() - 1000).toISOString() },
    ];
    suggestionResponse = {
      suggestion_id: "event-b|event-a",
      action: "review_activity",
      text: "Review your notes and decide what to organize next.",
    };
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Review Notes" }));
    expect(await screen.findByRole("heading", { name: "Manage saved content" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Notes" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("selects Notes when accepting a review suggestion from another Manage section", async () => {
    const user = userEvent.setup();
    activityEvents = [
      { event_id: "event-b", event_type: "note.updated", description: "Note updated", timestamp: new Date().toISOString() },
      { event_id: "event-a", event_type: "note.created", description: "Note created", timestamp: new Date(Date.now() - 1000).toISOString() },
    ];
    suggestionResponse = {
      suggestion_id: "event-b|event-a",
      action: "review_activity",
      text: "Review your notes and decide what to organize next.",
    };
    renderApp(USER_ID, "/manage");
    await user.click(screen.getByRole("button", { name: "Conversations" }));
    await user.click(await screen.findByRole("button", { name: "Review Notes" }));

    expect(screen.getByRole("button", { name: "Notes" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("dismisses a suggestion for its context and isolates dismissal by user", async () => {
    const user = userEvent.setup();
    activityEvents = [
      { event_id: "event-b", event_type: "note.updated", description: "Note updated", timestamp: new Date().toISOString() },
      { event_id: "event-a", event_type: "note.created", description: "Note created", timestamp: new Date(Date.now() - 1000).toISOString() },
    ];
    suggestionResponse = {
      suggestion_id: "event-b|event-a",
      action: "review_activity",
      text: "Review your notes and decide what to organize next.",
    };
    renderApp();
    await user.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("region", { name: "AI suggestion" })).toBeNull();

    activityEvents.unshift({
      event_id: "event-c",
      event_type: "note.updated",
      description: "Note updated",
      timestamp: new Date().toISOString(),
    });
    suggestionResponse.suggestion_id = "event-c|event-b|event-a";
    await act(async () => {
      window.dispatchEvent(new Event("ia:activity-updated"));
      await new Promise((resolve) => setTimeout(resolve, 300));
    });
    expect(screen.queryByRole("region", { name: "AI suggestion" })).toBeNull();

    cleanup();
    renderApp(USER_ID);
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) =>
      new URL(input, window.location.origin).pathname === "/activity/",
    )).toBe(true));
    await act(async () => new Promise((resolve) => setTimeout(resolve, 25)));
    expect(screen.queryByRole("region", { name: "AI suggestion" })).toBeNull();

    cleanup();
    renderApp("another-user");
    expect(await screen.findByRole("region", { name: "AI suggestion" })).toBeTruthy();
  });

  it("keeps Activity History out of navigation and redirects its old route", async () => {
    const user = userEvent.setup();
    renderApp();
    expect(screen.queryByRole("link", { name: "Activity History" })).toBeNull();

    window.history.pushState(null, "", "/activity");
    await act(async () => window.dispatchEvent(new PopStateEvent("popstate")));
    expect(await screen.findByRole("textbox", { name: "Question" })).toBeTruthy();
    expect(window.location.pathname).toBe("/ask");
  });

  it("renders the route-controlled Login/Register mode in the first updated render", () => {
    const onModeChange = vi.fn();
    const { rerender } = render(<Login initialIsRegister={false} onModeChange={onModeChange} />);
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeTruthy();

    rerender(<Login initialIsRegister onModeChange={onModeChange} />);
    expect(screen.getByRole("heading", { name: "Create account" })).toBeTruthy();
    expect(screen.getByText("Register and sign in")).toBeTruthy();
  });

  it("waits for saved Settings before displaying preference controls", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByLabelText("Ask shortcuts");

    const gate = deferred();
    settingsGetGate = gate;
    await user.click(screen.getByRole("link", { name: "Settings" }));
    expect(await screen.findByText("Loading saved sources…")).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: /Show Ask labels/ })).toBeNull();
    expect(screen.queryByLabelText("prefTheme")).toBeNull();

    settingsGetGate = null;
    gate.resolve();
    expect((await screen.findByRole("checkbox", { name: /Show Ask labels/ })).checked).toBe(true);
    expect(document.getElementById("prefTheme").value).toBe("dark");
  });

  it("shows list loading states immediately instead of transient empty states", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByLabelText("Ask shortcuts");

    const notesGate = deferred();
    notesListGate = notesGate;
    await user.click(screen.getByRole("link", { name: "Manage" }));
    await screen.findByRole("heading", { name: "Manage saved content" });
    expect(await screen.findByText("Loading…")).toBeTruthy();
    expect(screen.queryByText(/No notes yet/)).toBeNull();
    notesListGate = null;
    notesGate.resolve();

    const historyGate = deferred();
    historyListGate = historyGate;
    await user.click(screen.getByRole("button", { name: "Conversations" }));
    expect(await screen.findByText("Loading…")).toBeTruthy();
    expect(screen.queryByText("No conversations yet. Create one, then select it in Ask to continue that chat.")).toBeNull();
    historyListGate = null;
    historyGate.resolve();
  });

  it("does not show empty states when History or Memory failed to load", async () => {
    const user = userEvent.setup();
    historyRequestError = true;
    memoriesRequestError = true;
    renderApp();
    await screen.findByLabelText("Ask shortcuts");

    await user.click(screen.getByRole("link", { name: "Manage" }));
    await screen.findByRole("heading", { name: "Manage saved content" });
    await user.click(screen.getByRole("button", { name: "Conversations" }));
    expect(await screen.findByText("History unavailable")).toBeTruthy();
    expect(screen.queryByText(/No conversations yet/)).toBeNull();

    await user.click(screen.getByRole("button", { name: "Memory" }));
    expect(await screen.findByText("Could not load Memory: Memory unavailable")).toBeTruthy();
    expect(screen.queryByText(/No memories are saved/)).toBeNull();
  });

  it("does not show Memory Off until its saved setting has loaded", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByLabelText("Ask shortcuts");

    const gate = deferred();
    settingsGetGate = gate;
    await user.click(await screen.findByRole("button", { name: "Memory: Memory is off" }));
    expect(await screen.findByText("Loading saved Memory setting…")).toBeTruthy();
    expect(screen.queryByText("Memory Off")).toBeNull();
    expect(screen.getByRole("checkbox", { name: /Memory status unavailable/ }).disabled).toBe(true);

    settingsGetGate = null;
    gate.resolve();
    expect(await screen.findByText("Memory Off")).toBeTruthy();
  });

  it("shows every configured source with its current state accessibly", async () => {
    settings.ask_context_sources = ["conversation", "notes", "memory", "files", "github", "drive", "web"];
    const user = userEvent.setup();
    renderApp();

    const expectedStates = {
      Conversation: "No active conversation",
      Notes: "OFF",
      Memory: "Memory is off",
      Files: "OFF",
      GitHub: "OFF",
      Drive: "OFF",
      Web: "OFF",
    };
    for (const [label, state] of Object.entries(expectedStates)) {
      const control = await screen.findByRole("button", { name: `${label}: ${state}` });
      expect(control.getAttribute("title")).toBe(`${label}: ${state}`);
      const tooltip = document.getElementById(control.getAttribute("aria-describedby"));
      expect(tooltip.textContent).toContain(label);
      expect(tooltip.textContent).toContain(state);
    }
  });

  it("orders Conversation, Notes, and Memory icon controls for compact layouts", async () => {
    sessionStorage.setItem(NOTE_SELECTION_KEY, JSON.stringify(["note-a"]));
    renderApp();

    const conversation = await screen.findByRole("button", { name: "Conversation: No active conversation" });
    const conversationChildren = Array.from(conversation.children);
    expect(conversationChildren.map((element) => element.className)).toEqual([
      "ask-shortcut-icon",
      "ask-context-source__label",
    ]);

    const notes = screen.getByRole("button", { name: "Notes: OFF, 1 selected" });
    expect(Array.from(notes.children).map((element) => element.className)).toEqual([
      "ask-shortcut-icon",
      "ask-context-source__label",
      "ask-context-count",
    ]);

    const memory = screen.getByRole("button", { name: "Memory: Memory is off" });
    expect(Array.from(memory.children).map((element) => element.className)).toEqual([
      "ask-shortcut-icon",
      "ask-context-source__label",
    ]);
    expect(memory.querySelector(".ask-context-status-dot")).toBeNull();
    expect(conversation.querySelector(".ask-context-status-dot")).toBeNull();
    const memoryToggle = screen.getByRole("button", { name: "Memory is OFF. Activate to turn Memory on." });
    expect(memoryToggle.querySelector(".ask-context-status-dot")).toBeNull();
    expect(memoryToggle.textContent).toContain("OFF");
    expect(memoryToggle.getAttribute("aria-pressed")).toBe("false");
  });

  it("cycles Notes modes and preserves a hidden source's saved mode", async () => {
    const user = userEvent.setup();
    renderApp();

    await screen.findByRole("button", {
      name: /^Notes context mode: OFF\. Activate to change mode\.$/,
    });
    const notesControl = getNotesModeButton("OFF");
    const notesGroup = notesControl.closest(".ask-context-control");
    expect(notesGroup.className).not.toContain("--active");
    await user.click(notesControl);

    const selectedMode = getNotesModeButton("SELECTED");
    expect(selectedMode.getAttribute("aria-pressed")).toBe("true");
    expect(selectedMode.className).toContain("ask-shortcut--active");
    expect(selectedMode.closest(".ask-context-control").className).toContain("--active");
    await waitFor(() => expect(settings.ask_context_modes.notes).toBe("selected"));

    await user.click(selectedMode);
    expect(getNotesModeButton("AUTOMATIC")).toBeTruthy();
    await user.click(getNotesModeButton("AUTOMATIC"));
    const offMode = getNotesModeButton("OFF");
    expect(offMode.getAttribute("aria-pressed")).toBe("false");
    expect(offMode.className).not.toContain("ask-shortcut--active");
    expect(offMode.closest(".ask-context-control").className).not.toContain("--active");
    await waitFor(() => expect(settings.ask_context_modes.notes).toBe("off"));

    await user.click(offMode);
    await waitFor(() => expect(settings.ask_context_modes.notes).toBe("selected"));
    await user.click(screen.getByRole("link", { name: "Settings" }));
    const notesVisibility = await screen.findByRole("checkbox", {
      name: /^Notes Select saved notes to provide as AI context\./,
    });
    expect(notesVisibility.checked).toBe(true);
    await user.click(notesVisibility);
    await waitFor(() => expect(settings.ask_context_sources).not.toContain("notes"));

    await user.click(screen.getByRole("link", { name: "Ask" }));
    await screen.findByLabelText("Ask shortcuts");
    expect(screen.queryByRole("button", { name: /^Notes:/ })).toBeNull();
    expect(settings.ask_context_modes.notes).toBe("selected");

    await user.click(screen.getByRole("link", { name: "Settings" }));
    await user.click(await screen.findByRole("checkbox", {
      name: /^Notes Select saved notes to provide as AI context\./,
    }));
    await waitFor(() => expect(settings.ask_context_sources).toContain("notes"));
    await user.click(screen.getByRole("link", { name: "Ask" }));
    expect(await screen.findByRole("button", {
      name: /^Notes context mode: SELECTED\. Activate to change mode\.$/,
    })).toBeTruthy();
  });

  it("shows Memory status on hover or long press and preserves tap-to-toggle", async () => {
    const user = userEvent.setup();
    renderApp();

    const memory = await screen.findByRole("button", { name: "Memory: Memory is off" });
    const tooltip = document.getElementById(memory.getAttribute("aria-describedby"));
    expect(tooltip.textContent).toContain("Memory is off");
    expect(memory.closest(".ask-context-source-wrap").className).not.toContain("--pressed");
    expect(screen.queryByText(/Memory (saved|updated|is off)\./)).toBeNull();

    const pointerDown = new MouseEvent("pointerdown", {
      bubbles: true,
      button: 0,
      clientX: 10,
      clientY: 10,
    });
    Object.defineProperty(pointerDown, "pointerId", { value: 1 });
    Object.defineProperty(pointerDown, "pointerType", { value: "touch" });
    memory.dispatchEvent(pointerDown);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 600));
    });
    expect(memory.closest(".ask-context-source-wrap").className).toContain("--pressed");
    expect(tooltip.textContent).toContain("Memory is off");
    fireEvent.pointerUp(memory, { pointerId: 1, pointerType: "touch", button: 0 });
    fireEvent.click(memory);
    expect(window.location.pathname).toBe("/ask");
    expect(settings.memory_enabled).toBe(false);

    const memoryToggle = screen.getByRole("button", { name: "Memory is OFF. Activate to turn Memory on." });
    expect(memoryToggle.textContent).toContain("OFF");
    await user.click(memoryToggle);
    await waitFor(() => expect(settings.memory_enabled).toBe(true));
    const enabledSource = await screen.findByRole("button", { name: "Memory: Memory is on" });
    expect(enabledSource.children[1].className).toBe("ask-context-source__label");
    expect(enabledSource.querySelector(".ask-context-status-dot")).toBeNull();
    const enabledToggle = screen.getByRole("button", { name: "Memory is ON. Activate to turn Memory off." });
    expect(enabledToggle.textContent).toContain("ON");
    expect(enabledToggle.querySelector(".ask-context-status-dot")).toBeNull();
    expect(enabledToggle.getAttribute("aria-pressed")).toBe("true");
    expect(enabledToggle.className).toContain("ask-shortcut--active");
    expect(enabledToggle.title).toContain("Memory is on");
    expect(enabledToggle.closest(".ask-context-control").className).toContain("--active");
    await user.click(enabledToggle);
    await waitFor(() => expect(settings.memory_enabled).toBe(false));
    expect(screen.getByRole("button", { name: "Memory is OFF. Activate to turn Memory on." }).textContent).toContain("OFF");
    expect(screen.getByRole("button", { name: "Memory is OFF. Activate to turn Memory on." }).className)
      .not.toContain("ask-shortcut--active");
    expect(screen.getByRole("button", { name: "Memory is OFF. Activate to turn Memory on." }).closest(".ask-context-control").className).not.toContain("--active");
  });

  it("defaults Show Ask labels on, keeps the checkbox synchronized, and persists user changes", async () => {
    const user = userEvent.setup();
    renderApp();

    let controls = await screen.findByLabelText("Ask shortcuts");
    expect(controls.className).toContain("ask-shortcuts--labels-visible");
    expect(screen.getByText("Conversation", { selector: ".ask-context-source__label" })).toBeTruthy();
    expect(settings.show_context_source_labels).toBeUndefined();

    expect(screen.queryByRole("checkbox", { name: "Show Ask labels" })).toBeNull();
    await user.click(screen.getByRole("link", { name: "Settings" }));
    const preference = await screen.findByRole("checkbox", { name: /Show Ask labels/ });
    expect(preference.checked).toBe(true);
    expect(settings.show_context_source_labels).toBeUndefined();
    await user.click(preference);
    expect(preference.checked).toBe(false);
    await waitFor(() => expect(settings.show_context_source_labels).toBe(false));

    await user.click(screen.getByRole("link", { name: "Ask" }));
    controls = await screen.findByLabelText("Ask shortcuts");
    expect(controls.className).toContain("ask-shortcuts--labels-hidden");
    expect(screen.getByRole("button", { name: "Conversation: No active conversation" })).toBeTruthy();
    expect(screen.getByText("Conversation", { selector: ".ask-context-source__label" })).toBeTruthy();
    const memorySource = screen.getByRole("button", { name: "Memory: Memory is off" });
    expect(memorySource.querySelector(".ask-context-status-dot")).toBeNull();
    expect(screen.getByRole("button", { name: "Memory is OFF. Activate to turn Memory on." }).textContent).toContain("OFF");

    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    expect(controls.className).toContain("ask-shortcuts--labels-hidden");
    await user.click(screen.getByRole("link", { name: "Settings" }));
    const hiddenPreference = await screen.findByRole("checkbox", { name: /Show Ask labels/ });
    expect(hiddenPreference.checked).toBe(false);
    await user.click(hiddenPreference);
    expect(hiddenPreference.checked).toBe(true);
    await waitFor(() => expect(settings.show_context_source_labels).toBe(true));
    await user.click(screen.getByRole("link", { name: "Ask" }));
    controls = await screen.findByLabelText("Ask shortcuts");
    expect(controls.className).toContain("ask-shortcuts--labels-visible");
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1280 });
    expect(controls.className).toContain("ask-shortcuts--labels-visible");
  });

  it("uses the loaded hidden-label preference immediately when navigating back to Ask", async () => {
    const user = userEvent.setup();
    settings.show_context_source_labels = false;
    renderApp();

    await screen.findByLabelText("Ask shortcuts");
    await user.click(screen.getByRole("link", { name: "Settings" }));
    const preference = await screen.findByRole("checkbox", { name: /Show Ask labels/ });
    expect(preference.checked).toBe(false);

    const settingsRequestCount = fetchMock.mock.calls.filter(([input]) =>
      new URL(input, window.location.origin).pathname === "/settings/",
    ).length;
    await user.click(screen.getByRole("link", { name: "Ask" }));
    const toolbar = screen.getByLabelText("Ask shortcuts");
    expect(toolbar.className).toContain("ask-shortcuts--labels-hidden");
    expect(toolbar.className).not.toContain("ask-shortcuts--labels-visible");
    expect(fetchMock.mock.calls.filter(([input]) =>
      new URL(input, window.location.origin).pathname === "/settings/",
    )).toHaveLength(settingsRequestCount);
    expect(screen.getByRole("button", { name: "Conversation: No active conversation" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Conversation: No active conversation" }).querySelector(".ask-context-status-dot")).toBeNull();
    expect(screen.getByRole("button", { name: "Memory: Memory is off" }).querySelector(".ask-context-status-dot")).toBeNull();
    expect(screen.getByRole("button", { name: "Memory is OFF. Activate to turn Memory on." }).textContent).toContain("OFF");
  });

  it("keeps labels hidden on the first Ask render when navigation interrupts saving the disabled preference", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByLabelText("Ask shortcuts");

    await user.click(screen.getByRole("link", { name: "Settings" }));
    const preference = screen.getByRole("checkbox", { name: /Show Ask labels/ });
    const saveGate = deferred();
    settingsPutGate = saveGate;
    await user.click(preference);
    expect(preference.checked).toBe(false);

    await user.click(screen.getByRole("link", { name: "Ask" }));
    expect(screen.queryByLabelText("Ask shortcuts")).toBeNull();
    expect(screen.queryByText("Conversation", { selector: ".ask-context-source__label" })).toBeNull();

    settingsPutGate = null;
    saveGate.resolve();
    const toolbar = await screen.findByLabelText("Ask shortcuts");
    expect(toolbar.className).toContain("ask-shortcuts--labels-hidden");
    expect(toolbar.className).not.toContain("ask-shortcuts--labels-visible");
    expect(await screen.findByRole("button", { name: "Conversation: No active conversation" })).toBeTruthy();
  });

  it("keeps the saved label preference unchanged when using Focus", async () => {
    const user = userEvent.setup();
    settings.show_context_source_labels = false;
    renderApp();
    await selectConversation(user, "First conversation");

    const toolbar = await screen.findByLabelText("Ask shortcuts");
    expect(toolbar.className).toContain("ask-shortcuts--labels-hidden");
    const conversationButton = screen.getByRole("button", { name: "Conversation: Active conversation" });
    expect(conversationButton).toBeTruthy();
    expect(conversationButton.querySelector(".ask-context-source__label").textContent).toBe("Conversation");

    const settingsWritesBeforeFocus = fetchMock.mock.calls.filter(([input, options]) =>
      new URL(input, window.location.origin).pathname === "/settings/" && options?.method === "PUT",
    ).length;
    await user.click(screen.getByRole("button", { name: "Focus Conversation History" }));
    expect(screen.queryByLabelText("Ask shortcuts")).toBeNull();
    expect(settings.show_context_source_labels).toBe(false);
    await user.click(screen.getByRole("button", { name: "Exit Conversation History focus" }));

    const restoredToolbar = screen.getByLabelText("Ask shortcuts");
    expect(restoredToolbar.className).toContain("ask-shortcuts--labels-hidden");
    expect(restoredToolbar.className).not.toContain("ask-shortcuts--labels-visible");
    expect(fetchMock.mock.calls.filter(([input, options]) =>
      new URL(input, window.location.origin).pathname === "/settings/" && options?.method === "PUT",
    )).toHaveLength(settingsWritesBeforeFocus);
  });

  it("hides Debug from navigation while keeping its authenticated route available", async () => {
    renderApp(USER_ID, "/debug");

    expect(screen.queryByRole("link", { name: "Debug" })).toBeNull();
    expect(screen.getByLabelText("Question")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Get context" })).toBeTruthy();
  });

  it("does not cache a pending Settings read under a different account after an account switch", async () => {
    setToken(tokenFor(USER_ID));
    const saveGate = deferred();
    settingsPutGate = saveGate;
    const save = putSettings({ show_context_source_labels: false });
    const read = getSettings();

    setToken(tokenFor("user-2"));
    settingsPutGate = null;
    saveGate.resolve();
    await save;
    const loadedSettings = await read;

    expect(getCachedSettings()).toEqual(loadedSettings);
    const settingsGets = fetchMock.mock.calls.filter(([input, options = {}]) =>
      new URL(input, window.location.origin).pathname === "/settings/" && (options.method || "GET") === "GET",
    );
    expect(settingsGets).toHaveLength(1);
  });

  it("restores the selected conversation and its latest saved messages after Ask remounts", async () => {
    const user = userEvent.setup();
    renderApp();
    await selectConversation(user, "First conversation");
    expect(await screen.findByText("First saved question")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Conversation: Active conversation" })
      .closest(".ask-context-control").className).toContain("--active");
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe("first");

    await user.type(screen.getByRole("textbox", { name: "Question" }), "Latest turn");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Latest turn")).toBeTruthy();
    await waitFor(() => {
      const saved = JSON.parse(notes.get("first").content);
      expect(saved.at(-2)).toEqual({ role: "user", content: "Latest turn" });
    });

    await navigateBetweenPages(user);
    expect(await screen.findByText("Latest turn")).toBeTruthy();
    expect(screen.getByText("Answer to Latest turn")).toBeTruthy();
    expect(screen.getByText("First saved question")).toBeTruthy();
    expect(screen.getByText("First conversation")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/notes/first"))).toBe(true);
  });

  it("starts a new conversation explicitly and does not reopen the previous one", async () => {
    const user = userEvent.setup();
    renderApp();
    await selectConversation(user, "First conversation");
    expect(await screen.findByText("First saved question")).toBeTruthy();

    await openConversationPicker(user);
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    await waitFor(() => expect(sessionStorage.getItem(STORAGE_KEY)).toBe("new-1"));
    expect(screen.queryByText("First saved question")).toBeNull();

    await navigateBetweenPages(user);
    expect(await screen.findByText("Conversation History", { selector: ".ask-history-title" })).toBeTruthy();
    expect(screen.queryByText("First saved question")).toBeNull();
    expect(screen.getByText("New conversation")).toBeTruthy();
  });

  it("restores another conversation after it is selected", async () => {
    const user = userEvent.setup();
    renderApp();
    await selectConversation(user, "First conversation");
    expect(await screen.findByText("First saved question")).toBeTruthy();

    await selectConversation(user, "Second conversation");
    expect(await screen.findByText("Second saved question")).toBeTruthy();
    expect(screen.queryByText("First saved question")).toBeNull();
    await navigateBetweenPages(user);
    expect(await screen.findByText("Second saved question")).toBeTruthy();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe("second");
  });

  it("clears a deleted active conversation and presents a safe empty state", async () => {
    sessionStorage.setItem(STORAGE_KEY, "deleted");
    renderApp();

    expect(await screen.findByText(/This conversation is unavailable/)).toBeTruthy();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(screen.queryByRole("heading", { name: "Conversation History" })).toBeNull();
    expect(screen.getByRole("textbox", { name: "Question" })).toBeTruthy();
  });

  it("ignores a delayed note response after a different conversation becomes active", async () => {
    noteGetDelays.add("first");
    const user = userEvent.setup();
    renderApp();
    await selectConversation(user, "First conversation");
    await waitFor(() => expect(delayedNoteResolves.has("first")).toBe(true));

    await selectConversation(user, "Second conversation");
    expect(await screen.findByText("Second saved question")).toBeTruthy();
    delayedNoteResolves.get("first").resolve();
    await waitFor(() => expect(screen.queryByText("First saved question")).toBeNull());
    expect(screen.getByText("Second saved answer")).toBeTruthy();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe("second");
  });

  it("clears the previous user's selection on logout and does not restore it for another account", async () => {
    const user = userEvent.setup();
    renderApp("user-1");
    await selectConversation(user, "First conversation");
    expect(await screen.findByText("First saved question")).toBeTruthy();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe("first");
    sessionStorage.setItem(NOTE_SELECTION_KEY, JSON.stringify(["note-a"]));

    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(sessionStorage.getItem(NOTE_SELECTION_KEY)).toBeNull();
    await user.type(screen.getByRole("textbox", { name: "Username" }), "user-2");
    await user.type(screen.getByLabelText("Password"), "password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(screen.getByRole("textbox", { name: "Question" })).toBeTruthy());
    expect(screen.queryByText("First saved question")).toBeNull();
    expect(sessionStorage.getItem("ia:active-conversation:user-2")).toBeNull();
  });

  it("keeps editing and resending a user turn in the selected history note", async () => {
    const user = userEvent.setup();
    renderApp();
    await selectConversation(user, "First conversation");
    const original = await screen.findByRole("button", { name: "View user message 1: First saved question" });
    await user.click(original);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const editor = screen.getByRole("textbox", { name: "Edit your message" });
    await user.clear(editor);
    await user.type(editor, "Revised question");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("button", { name: "View user message 1: Revised question" })).toBeTruthy();
    await waitFor(() => {
      expect(JSON.parse(notes.get("first").content)).toEqual([
        { role: "user", content: "Revised question" },
        { role: "assistant", content: "Answer to Revised question" },
      ]);
    });
    expect(aiRequests.at(-1).question).toBe("Revised question");
  });

  it("restores selected Notes and their saved context mode after Ask remounts", async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(await screen.findByRole("button", { name: /^Notes:/ }));
    await user.click(await screen.findByRole("button", { name: "Select note: Study note" }));
    await user.click(screen.getByRole("button", { name: "Add selected (1)" }));
    await user.click(screen.getByRole("button", { name: "Notes context mode: OFF. Activate to change mode." }));

    await waitFor(() => {
      expect(settings.ask_context_modes.notes).toBe("selected");
      expect(sessionStorage.getItem(NOTE_SELECTION_KEY)).toBe(JSON.stringify(["note-a"]));
    });

    await navigateBetweenPages(user);
    expect(screen.getByRole("button", { name: "Notes: SELECTED, 1 selected" })).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Notes context mode: SELECTED. Activate to change mode." })).toBeTruthy();
    expect(screen.getByText("1", { selector: ".ask-context-count" })).toBeTruthy();

    await user.type(screen.getByRole("textbox", { name: "Question" }), "Use my selected note");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(aiRequests).toHaveLength(1));
    expect(aiRequests[0].note_ids).toEqual(["note-a"]);
    expect(aiRequests[0].note_context_mode).toBe("focused");

    await user.click(await screen.findByRole("button", { name: /^Notes:/ }));
    const selectedNote = await screen.findByRole("button", { name: "Select note: Study note" });
    expect(selectedNote.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Add selected (1)" })).toBeTruthy();
  });

  it("does not restore selected Note IDs for another account", async () => {
    sessionStorage.setItem(NOTE_SELECTION_KEY, JSON.stringify(["note-a"]));
    renderApp("user-2");

    expect(await screen.findByRole("textbox", { name: "Question" })).toBeTruthy();
    expect(sessionStorage.getItem("ia:selected-note-ids:user-2")).toBeNull();
    expect(sessionStorage.getItem(NOTE_SELECTION_KEY)).toBe(JSON.stringify(["note-a"]));
  });

  it("opens saved decks from Shortcuts and creates a deck through explicit review approval", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByRole("textbox", { name: "Question" });

    const shortcuts = screen.getByText("Shortcuts");
    const shortcutsSection = shortcuts.closest("details");
    expect(shortcutsSection.open).toBe(false);
    expect(shortcutsSection.previousElementSibling).toBe(screen.getByRole("button", { name: "Ask" }).closest("form"));
    await user.click(shortcuts);
    expect(shortcutsSection.open).toBe(true);
    await user.click(screen.getByRole("button", { name: /Flashcards/ }));
    const dialog = await screen.findByRole("dialog", { name: "Flashcards" });
    expect(dialog).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Saved decks" })).toBeTruthy();
    expect(screen.getByText(/No saved flashcard decks yet/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "New Flashcards" }));
    expect(screen.getByRole("heading", { name: /Step 1 — Select source notes/ })).toBeTruthy();

    const noteCheckbox = await screen.findByRole("checkbox", { name: /Study note/ });
    await user.click(noteCheckbox);
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading", { name: /Step 2 — Generation options/ })).toBeTruthy();
    await user.clear(screen.getByLabelText("Number of cards"));
    await user.type(screen.getByLabelText("Number of cards"), "2");
    await user.selectOptions(screen.getByLabelText("Difficulty"), "Hard");
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("checkbox", { name: /Study note/ }).checked).toBe(true);
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByLabelText("Number of cards").value).toBe("2");
    expect(screen.getByLabelText("Difficulty").value).toBe("Hard");

    const generationGate = deferred();
    flashcardRequestGate = generationGate;
    await user.click(screen.getByRole("button", { name: "Generate" }));
    expect(screen.getByRole("button", { name: "Generating…" }).disabled).toBe(true);
    await act(async () => {
      generationGate.resolve();
    });

    expect(await screen.findByRole("heading", { name: /Step 3 — Review generated cards/ })).toBeTruthy();
    expect(screen.getByText("Card 1 of 2")).toBeTruthy();
    expect(flashcardRequests).toHaveLength(1);
    expect(flashcardRequests[0].note_ids).toEqual(["note-a"]);
    expect(flashcardRequests[0].card_count).toBe(2);
    expect(flashcardRequests[0].difficulty).toBe("Hard");
    expect(createdNotes).toHaveLength(0);

    await user.clear(screen.getByLabelText("Question / front"));
    await user.type(screen.getByLabelText("Question / front"), "Edited question");
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByLabelText("Number of cards").value).toBe("2");
    expect(screen.getByLabelText("Difficulty").value).toBe("Hard");
    await user.click(screen.getByRole("button", { name: "Review draft" }));
    expect(screen.getByLabelText("Question / front").value).toBe("Edited question");
    await user.click(screen.getByRole("button", { name: "Next card" }));
    expect(screen.getByText("Card 2 of 2")).toBeTruthy();
    await user.clear(screen.getByLabelText("Answer / back"));
    await user.type(screen.getByLabelText("Answer / back"), "Edited answer");
    await user.click(screen.getByRole("button", { name: "Previous card" }));
    expect(screen.getByLabelText("Question / front").value).toBe("Edited question");
    await user.click(screen.getByRole("button", { name: "Next card" }));
    await user.click(screen.getByRole("button", { name: "Remove this card" }));
    expect(screen.getByText("Card 1 of 1")).toBeTruthy();
    expect(screen.getByLabelText("Question / front").value).toBe("Edited question");
    expect(createdNotes).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Save approved deck" }));
    await screen.findByText("Approved deck saved to Notes.");
    expect(createdNotes).toHaveLength(1);
    expect(createdNotes[0].category).toBe("flashcards");
    expect(JSON.parse(createdNotes[0].content).cards).toEqual([
      {
        question: "Edited question",
        answer: "The process plants use to make food.",
      },
    ]);
    expect(screen.getByText("Approved deck saved to Notes.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
  });

  it("searches source notes and enforces the 20-note selection limit", async () => {
    const user = userEvent.setup();
    for (let index = 1; index <= 21; index += 1) {
      const id = `limit-note-${index}`;
      notes.set(id, {
        id,
        title: `Limit note ${index}`,
        category: "study",
        content: `Source ${index}`,
        tags: [],
      });
    }
    renderApp();
    await screen.findByRole("textbox", { name: "Question" });
    await startNewFlashcards(user);

    await user.type(screen.getByRole("searchbox", { name: "Search notes" }), "Limit note");
    for (let index = 1; index <= 20; index += 1) {
      await user.click(await screen.findByRole("checkbox", {
        name: new RegExp(`^Limit note ${index}(?:$|\\s)`),
      }));
    }

    expect(screen.getByRole("status").textContent).toMatch(/select up to 20 notes/i);
    const twentyFirst = screen.getByRole("checkbox", { name: /Limit note 21/ });
    expect(twentyFirst.disabled).toBe(true);
    await user.click(twentyFirst);
    expect(twentyFirst.checked).toBe(false);

    await user.click(screen.getByRole("checkbox", { name: /^Limit note 1(?:$|\s)/ }));
    expect(screen.getByRole("checkbox", { name: /Limit note 21/ }).disabled).toBe(false);
    expect(screen.getByRole("checkbox", { name: /^Limit note 2(?:$|\s)/ }).checked).toBe(true);
  }, 10_000);

  it("opens, edits, and deletes only the selected saved flashcard deck", async () => {
    const user = userEvent.setup();
    const deckA = {
      id: "deck-a",
      title: "Biology cards",
      category: "flashcards",
      tags: ["flashcards"],
      content: JSON.stringify({ version: 1, cards: [{ question: "Q1", answer: "A1" }] }),
    };
    const deckB = {
      id: "deck-b",
      title: "History cards",
      category: "flashcards",
      tags: ["flashcards"],
      content: JSON.stringify({ version: 1, cards: [{ question: "Q2", answer: "A2" }] }),
    };
    const taggedNote = {
      id: "ordinary-tagged-note",
      title: "Ordinary tagged note",
      category: "study",
      tags: ["flashcards"],
      content: "This is a regular note, not a deck.",
    };
    notes.set(deckA.id, deckA);
    notes.set(deckB.id, deckB);
    notes.set(taggedNote.id, taggedNote);
    renderApp();
    await screen.findByRole("textbox", { name: "Question" });
    await openFlashcards(user);

    expect(screen.queryByText("Ordinary tagged note")).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit deck: Ordinary tagged note" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete deck: Ordinary tagged note" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Open deck: Biology cards" }));
    expect(screen.getByRole("heading", { name: "Saved deck" })).toBeTruthy();
    expect(screen.getByLabelText("Question / front").value).toBe("Q1");
    expect(screen.getByLabelText("Question / front").readOnly).toBe(true);
    await user.click(screen.getByRole("button", { name: "Edit deck" }));
    await user.clear(screen.getByLabelText("Deck title"));
    await user.type(screen.getByLabelText("Deck title"), "Biology review");
    await user.clear(screen.getByLabelText("Question / front"));
    await user.type(screen.getByLabelText("Question / front"), "Updated question");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Deck changes saved.")).toBeTruthy();
    expect(notes.get("deck-a").title).toBe("Biology review");
    expect(JSON.parse(notes.get("deck-a").content).cards[0].question).toBe("Updated question");

    await user.click(screen.getByRole("button", { name: "Back to decks" }));
    await user.click(screen.getByRole("button", { name: "Delete deck: Biology review" }));
    expect(screen.getByText("Delete this deck?")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(notes.has("deck-a")).toBe(false));
    expect(notes.has("deck-b")).toBe(true);
    expect(notes.has(taggedNote.id)).toBe(true);
  });

  it("blocks every panel close path while saving, then permits closing after save completes", async () => {
    const user = userEvent.setup();
    const saveGate = deferred();
    noteSaveGate = saveGate;
    renderApp();
    await screen.findByRole("textbox", { name: "Question" });
    await startNewFlashcards(user);
    await user.click(await screen.findByRole("checkbox", { name: /Study note/ }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.clear(screen.getByLabelText("Number of cards"));
    await user.type(screen.getByLabelText("Number of cards"), "2");
    await user.click(screen.getByRole("button", { name: "Generate" }));
    await screen.findByText("Card 1 of 2");

    await user.click(screen.getByRole("button", { name: "Save approved deck" }));
    expect(screen.getByRole("button", { name: "Saving…" }).disabled).toBe(true);
    const closeButton = screen.getByRole("button", { name: "Close Flashcards" });
    expect(closeButton.disabled).toBe(true);
    await user.click(closeButton);
    await user.click(document.querySelector(".ask-overlay__backdrop"));
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "Flashcards" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel" }).disabled).toBe(true);
    expect(createdNotes).toHaveLength(0);

    await act(async () => {
      saveGate.resolve();
    });
    expect(await screen.findByText("Approved deck saved to Notes.")).toBeTruthy();
    expect(createdNotes).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Close Flashcards" }).disabled).toBe(false);
    await user.click(screen.getByRole("button", { name: "Back to decks" }));
    await user.click(screen.getByRole("button", { name: "Close Flashcards" }));
    expect(screen.queryByRole("dialog", { name: "Flashcards" })).toBeNull();
  });

  it("shows an empty saved-deck state and permits canceling source selection", async () => {
    const user = userEvent.setup();
    notes = new Map([...notes].filter(([, note]) => note.category === "_history"));
    renderApp();
    await screen.findByRole("textbox", { name: "Question" });
    await openFlashcards(user);
    expect(await screen.findByText(/No saved flashcard decks yet/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "New Flashcards" }));
    expect(await screen.findByText(/No saved notes are available/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Next" }).disabled).toBe(true);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("heading", { name: "Saved decks" })).toBeTruthy();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Flashcards" })).toBeNull();
    expect(createdNotes).toHaveLength(0);
  });

  it("shows a loading state while saved decks are being fetched", async () => {
    const user = userEvent.setup();
    const notesGate = deferred();
    notesListGate = notesGate;
    renderApp();
    await screen.findByRole("textbox", { name: "Question" });
    await openFlashcards(user);
    expect((await screen.findByRole("status")).textContent).toBe("Loading saved decks…");

    await act(async () => {
      notesGate.resolve();
    });
    expect(await screen.findByRole("button", { name: "New Flashcards" })).toBeTruthy();
  });

  it("shows generation errors without saving a deck", async () => {
    const user = userEvent.setup();
    flashcardRequestError = true;
    renderApp();
    await screen.findByRole("textbox", { name: "Question" });
    await startNewFlashcards(user);
    await user.click(await screen.findByRole("checkbox", { name: /Study note/ }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.clear(screen.getByLabelText("Number of cards"));
    await user.type(screen.getByLabelText("Number of cards"), "2");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(createdNotes).toHaveLength(0);
    expect(screen.queryByText(/Unsaved draft/)).toBeNull();
  });

  it("discards a generated draft when the Flashcards panel is canceled", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByRole("textbox", { name: "Question" });
    await startNewFlashcards(user);
    await user.click(await screen.findByRole("checkbox", { name: /Study note/ }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.clear(screen.getByLabelText("Number of cards"));
    await user.type(screen.getByLabelText("Number of cards"), "2");
    await user.click(screen.getByRole("button", { name: "Generate" }));
    expect(await screen.findByText("Card 1 of 2")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Flashcards" })).toBeNull();
    expect(createdNotes).toHaveLength(0);

    await user.click(screen.getByText("Shortcuts"));
    await user.click(screen.getByRole("button", { name: /Flashcards/ }));
    expect(await screen.findByRole("dialog", { name: "Flashcards" })).toBeTruthy();
    expect(screen.queryByText(/Unsaved draft/)).toBeNull();
    expect(createdNotes).toHaveLength(0);
  });
});
