// IA/frontend/src/api.js
// API layer: auth, ask, listNotes, debugContext, settings. Token from localStorage (login); 401 → clear and notify.

const BASE = (import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/+$/, "");
const TOKEN_KEY = "ia_token";
const UNAUTH_EVENT = "ia:unauthorized";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function clearToken() {
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

export async function ask(question, noteIds = null, messages = null) {
  const body = { question: (question || "hello").trim() };
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
  const res = await fetch(`${BASE}/settings/`, { headers: authHeaders() });
  const data = await res.json();
  return handleResponse(res, data);
}

export async function putSettings(data) {
  const res = await fetch(`${BASE}/settings/`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(data),
  });
  const out = await res.json();
  return handleResponse(res, out);
}

export async function createNoteFromImages(formData) {
  const res = await fetch(`${BASE}/notes/from-images`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  const data = await res.json();
  return handleResponse(res, data);
}

export async function createNote(note) {
  const token = requireToken();
  const res = await fetch(`${BASE}/notes/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(note),
  });
  const data = await res.json();
  return handleResponse(res, data);
}

export async function updateNote(noteId, data) {
  const res = await fetch(`${BASE}/notes/${noteId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(data),
  });
  const out = await res.json();
  return handleResponse(res, out);
}

export async function deleteNote(noteId) {
  const res = await fetch(`${BASE}/notes/${noteId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (res.status === 204 || res.status === 200) return;
  const data = await res.json().catch(() => ({}));
  return handleResponse(res, data);
}
