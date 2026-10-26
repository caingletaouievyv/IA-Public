// IA/frontend/src/askContextSources.js

export const ASK_CONTEXT_SOURCES = [
  {
    id: "conversation",
    label: "Conversation",
    description: "Choose or start a conversation.",
    details: "The active conversation and its saved messages.\nChoose or start a conversation.",
  },
  {
    id: "notes",
    label: "Notes",
    description: "Select saved notes to provide as AI context.",
    details: "Your saved notes.\nSelect notes to provide as context to the AI.",
  },
  {
    id: "files",
    label: "Files",
    description: "File selection and AI context are not available yet.",
    details: "Files are unavailable as Ask context: the file tree endpoint exists, but Ask has no file-selection or file-context flow.",
  },
  {
    id: "github",
    label: "GitHub",
    description: "GitHub context is not connected yet.",
    details: "GitHub context is not connected yet.",
  },
  {
    id: "memory",
    label: "Memory",
    description: "When on, IA can save useful information and use relevant saved memories.",
    details: "Your private saved Memory, separate from Notes and conversation history.\nWhen on, IA can remember useful details and use relevant saved memories in answers.\nClick to review or manage saved memories.",
  },
  {
    id: "drive",
    label: "Drive",
    description: "Google Drive context is not connected yet.",
    details: "Google Drive context is not connected yet.",
  },
  {
    id: "web",
    label: "Web",
    description: "Web context is not connected yet.",
    details: "Web context is not connected yet.",
  },
];

export const DEFAULT_VISIBLE_CONTEXT_SOURCES = ["conversation", "notes", "memory"];
export const DEFAULT_SHOW_CONTEXT_SOURCE_LABELS = true;
export function normalizeShowContextSourceLabels(value) {
  return value === false ? false : DEFAULT_SHOW_CONTEXT_SOURCE_LABELS;
}
export const DEFAULT_CONTEXT_MODES = {
  notes: "off",
  files: "off",
  github: "off",
  memory: "off",
  drive: "off",
  web: "off",
};

const validSourceIds = new Set(ASK_CONTEXT_SOURCES.map((source) => source.id));
const validContextModes = new Set(["off", "selected", "automatic"]);

export function normalizeVisibleContextSources(value) {
  if (!Array.isArray(value) || value.some((id) => typeof id !== "string" || !validSourceIds.has(id))) {
    return [...DEFAULT_VISIBLE_CONTEXT_SOURCES];
  }

  const selected = [...new Set(value)];
  if (!selected.includes("conversation")) selected.unshift("conversation");
  return selected;
}

export function getVisibleContextSources(value) {
  const visibleIds = new Set(normalizeVisibleContextSources(value));
  return ASK_CONTEXT_SOURCES.filter((source) => visibleIds.has(source.id));
}

export function normalizeContextModes(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { ...DEFAULT_CONTEXT_MODES };
  }
  return Object.fromEntries(
    Object.entries(DEFAULT_CONTEXT_MODES).map(([source, defaultMode]) => [
      source,
      validContextModes.has(value[source]) ? value[source] : defaultMode,
    ]),
  );
}

/** Matches Ask toolbar `active` state for each context source. */
export function isContextSourceActive(sourceId, { currentHistoryId, contextModes }) {
  if (sourceId === "conversation") {
    return Boolean(currentHistoryId);
  }
  return contextModes?.[sourceId] !== "off";
}

export function getActiveContextSources(visibleSources, state) {
  return getVisibleContextSources(visibleSources).filter((source) => isContextSourceActive(source.id, state));
}

/** Focus indicators: toggleable sources only (Conversation is history navigation, not an ON/OFF context mode). */
export function getFocusActiveContextSources(visibleSources, state) {
  return getActiveContextSources(visibleSources, state).filter((source) => source.id !== "conversation");
}

export function getContextSourceOnLabel(sourceLabel) {
  return `${sourceLabel}: ON`;
}
