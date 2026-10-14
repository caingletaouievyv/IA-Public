// IA/frontend/src/activeConversation.js
// Per-tab active conversation selection, scoped to the authenticated user.

const STORAGE_PREFIX = "ia:active-conversation:";
const SELECTED_NOTE_IDS_PREFIX = "ia:selected-note-ids:";

function storageKey(userId) {
  return userId ? `${STORAGE_PREFIX}${encodeURIComponent(userId)}` : null;
}

export function getActiveConversation(userId) {
  const key = storageKey(userId);
  return key ? sessionStorage.getItem(key) : null;
}

export function setActiveConversation(userId, conversationId) {
  const key = storageKey(userId);
  if (!key) return;
  if (conversationId) sessionStorage.setItem(key, conversationId);
  else sessionStorage.removeItem(key);
}

export function clearActiveConversation(userId) {
  setActiveConversation(userId, null);
}

export function getSelectedNoteIds(userId) {
  if (!userId) return [];
  const saved = sessionStorage.getItem(`${SELECTED_NOTE_IDS_PREFIX}${encodeURIComponent(userId)}`);
  if (!saved) return [];
  try {
    const ids = JSON.parse(saved);
    return Array.isArray(ids)
      ? [...new Set(ids.filter((id) => typeof id === "string" && id))]
      : [];
  } catch {
    return [];
  }
}

export function setSelectedNoteIds(userId, noteIds) {
  if (!userId) return;
  const key = `${SELECTED_NOTE_IDS_PREFIX}${encodeURIComponent(userId)}`;
  const ids = Array.isArray(noteIds)
    ? [...new Set(noteIds.filter((id) => typeof id === "string" && id))]
    : [];
  if (ids.length) sessionStorage.setItem(key, JSON.stringify(ids));
  else sessionStorage.removeItem(key);
}

export function clearSelectedNoteIds(userId) {
  setSelectedNoteIds(userId, []);
}
