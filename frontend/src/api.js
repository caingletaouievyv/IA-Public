// IA/frontend/src/api.js
// API layer: auth, ask, listNotes, debugContext, settings. Token from localStorage (login); 401 → clear and notify.

const BASE = (import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/+$/, "");
const TOKEN_KEY = "ia_token";
const UNAUTH_EVENT = "ia:unauthorized";
const settingsCache = new Map();
const pendingSettingsWrites = new Map();

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getTokenUserId(token = getToken()) {
  if (!token) return null;
  try {
    const payloadSegment = token.split(".")[1];
    if (!payloadSegment) return null;
    const base64 = payloadSegment.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "=")));
    return typeof payload.sub === "string" && payload.sub ? payload.sub : null;
  } catch {
    return null;
  }
}

export function setToken(token) {
  const previousUserId = getTokenUserId();
  const nextUserId = getTokenUserId(token);
  if (previousUserId !== nextUserId) {
    if (previousUserId) settingsCache.delete(previousUserId);
    if (nextUserId) settingsCache.delete(nextUserId);
  }
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function clearToken() {
  const userId = getTokenUserId();
  if (userId) settingsCache.delete(userId);
  localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event(UNAUTH_EVENT));
}

function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/** Capture token once for a request; throw if missing. Use this so a parallel 401 cannot clear token before this request is sent. */
function requireToken() {
  const t = getToken();
  if (!t) throw new Error("Not authenticated");
  return t;
}

function handleResponse(res, data) {
  // Only sign out on 401 when we had a token (server is rejecting it); avoid signing out when request had no token (e.g. race).
  if (res.status === 401 && getToken()) {
    clearToken();
    throw new Error("Session expired. Please sign in again.");
  }
  if (!res.ok) throw new Error(data?.error || data?.message || res.statusText);
  return data;
}

function notifyActivityMutation() {
  window.dispatchEvent(new Event("ia:activity-updated"));
}

async function readJsonResponse(res) {
  try {
    return await res.json();
  } catch {
    if (res.status === 401 && getToken()) clearToken();
    throw new Error(`Server error ${res.status}: response was not JSON`);
  }
}

export async function login(username, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: (username || "").trim(), password: password || "" }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

export async function register(username, password) {
  const res = await fetch(`${BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: (username || "").trim(), password: password || "" }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

export async function ask(question, noteIds = null, messages = null, noteContextMode = "off") {
  const body = {
    question: (question || "hello").trim(),
    note_context_mode: noteContextMode,
  };
  if (Array.isArray(noteIds) && noteIds.length) body.note_ids = noteIds;
  if (Array.isArray(messages) && messages.length) body.messages = messages;
  const res = await fetch(`${BASE}/ai/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return handleResponse(res, data);
}

export async function generateFlashcards(options) {
  const body = {
    ...options,
    request_id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
  };
  const res = await fetch(`${BASE}/ai/flashcards/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  const data = await readJsonResponse(res);
  return handleResponse(res, data);
}

export async function listMemories() {
  const res = await fetch(`${BASE}/memories/`, { headers: { Authorization: `Bearer ${requireToken()}` } });
  const data = await readJsonResponse(res);
  return handleResponse(res, data);
}

export async function updateMemory(memoryId, text) {
  const res = await fetch(`${BASE}/memories/${encodeURIComponent(memoryId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${requireToken()}` },
    body: JSON.stringify({ text }),
  });
  const data = await readJsonResponse(res);
  return handleResponse(res, data);
}

export async function deleteMemory(memoryId) {
  const res = await fetch(`${BASE}/memories/${encodeURIComponent(memoryId)}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${requireToken()}` },
  });
  const data = await readJsonResponse(res);
  return handleResponse(res, data);
}

export async function clearMemories() {
  const res = await fetch(`${BASE}/memories/clear`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${requireToken()}` },
  });
  const data = await readJsonResponse(res);
  return handleResponse(res, data);
}

export async function listActivity(limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${BASE}/activity/?${params}`, { headers: authHeaders() });
  const data = await readJsonResponse(res);
  return handleResponse(res, data);
}

export async function requestAiSuggestion() {
  const res = await fetch(`${BASE}/ai/suggestions`, {
    method: "POST",
    headers: authHeaders(),
  });
  const data = await readJsonResponse(res);
  return handleResponse(res, data);
}

export async function listNotes(params = {}) {
  const token = requireToken();
  const q = new URLSearchParams(params).toString();
  const url = `${BASE}/notes/${q ? `?${q}` : ""}`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  let data;
  try {
    data = await res.json();
  } catch {
    if (res.status === 401 && getToken()) clearToken();
    throw new Error(`Server error ${res.status}: response was not JSON`);
  }
  return handleResponse(res, data);
}

/** Conversation histories (notes with category _history). Same table as notes. */
const HISTORY_CATEGORY = "_history";

export async function listHistories() {
  return listNotes({ category: HISTORY_CATEGORY, limit: 200 });
}

export async function createHistory(title = "New conversation") {
  return createNote({
    title: (title || "New conversation").trim(),
    category: HISTORY_CATEGORY,
    content: "[]",
    tags: [],
  });
}

export async function getNote(noteId) {
  const res = await fetch(`${BASE}/notes/${noteId}`, { headers: authHeaders() });
  const data = await res.json();
  return handleResponse(res, data);
}

/** Categories and tags from user's notes for category dropdown and tag autocomplete. */
export async function getNotesMeta() {
  const res = await fetch(`${BASE}/notes/meta`, { headers: authHeaders() });
  const data = await res.json();
  return handleResponse(res, data);
}

export async function checkNotesAuth() {
  const res = await fetch(`${BASE}/notes/auth-check`, { headers: authHeaders() });
  const data = await res.json();
  return data;
}

export async function debugContext(question, noteIds = null) {
  const body = { question: (question || "find note about FAISS").trim() };
  if (Array.isArray(noteIds) && noteIds.length) body.note_ids = noteIds;
  const res = await fetch(`${BASE}/ai/debug/context`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return handleResponse(res, data);
}

export async function getSettings() {
  const token = getToken();
  const userId = getTokenUserId(token);
  let waitedForWrite = false;
  if (userId) {
    while (pendingSettingsWrites.has(userId)) {
      waitedForWrite = true;
      await Promise.allSettled([...pendingSettingsWrites.get(userId)]);
    }
    if (getToken() !== token) return getSettings();
    const cached = settingsCache.get(userId);
    if (waitedForWrite && cached) return cached;
  }

  const res = await fetch(`${BASE}/settings/`, { headers: authHeaders() });
  const data = await res.json();
  if (getToken() !== token) {
    if (!res.ok) throw new Error(data?.error || data?.message || res.statusText);
    return data;
  }
  const settings = handleResponse(res, data);
  if (userId && settings && typeof settings === "object" && !Array.isArray(settings)) {
    settingsCache.set(userId, settings);
  }
  return settings;
}

export function getCachedSettings() {
  const userId = getTokenUserId();
  if (!userId || pendingSettingsWrites.has(userId)) return null;
  return settingsCache.get(userId) || null;
}

export async function putSettings(data) {
  const userId = getTokenUserId();
  const request = (async () => {
    const res = await fetch(`${BASE}/settings/`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(data),
    });
    const out = await res.json();
    const settings = handleResponse(res, out);
    if (userId && settings && typeof settings === "object" && !Array.isArray(settings)) {
      settingsCache.set(userId, { ...settingsCache.get(userId), ...settings });
    }
    window.dispatchEvent(new CustomEvent("ia:settings-updated", { detail: settings }));
    return settings;
  })();

  if (userId) {
    let writes = pendingSettingsWrites.get(userId);
    if (!writes) {
      writes = new Set();
      pendingSettingsWrites.set(userId, writes);
    }
    writes.add(request);
    const cleanup = () => {
      writes.delete(request);
      if (writes.size === 0) pendingSettingsWrites.delete(userId);
    };
    request.then(cleanup, cleanup);
  }

  return request;
}

export async function createNoteFromImages(formData) {
  const res = await fetch(`${BASE}/notes/from-images`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  const data = await res.json();
  const result = handleResponse(res, data);
  notifyActivityMutation();
  return result;
}

export async function createNote(note) {
  const token = requireToken();
  const res = await fetch(`${BASE}/notes/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(note),
  });
  const data = await res.json();
  const result = handleResponse(res, data);
  if (note?.category !== "_history") notifyActivityMutation();
  return result;
}

export async function updateNote(noteId, data, { activityRelevant = true } = {}) {
  const res = await fetch(`${BASE}/notes/${noteId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(data),
  });
  const out = await res.json();
  const result = handleResponse(res, out);
  if (activityRelevant) notifyActivityMutation();
  return result;
}

export async function deleteNote(noteId, { activityRelevant = true } = {}) {
  const res = await fetch(`${BASE}/notes/${noteId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (res.status === 204 || res.status === 200) {
    if (activityRelevant) notifyActivityMutation();
    return;
  }
  const data = await res.json().catch(() => ({}));
  return handleResponse(res, data);
}
