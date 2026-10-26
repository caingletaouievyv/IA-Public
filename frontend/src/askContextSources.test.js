// IA/frontend/src/askContextSources.test.js

import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_CONTEXT_MODES,
  DEFAULT_VISIBLE_CONTEXT_SOURCES,
  getActiveContextSources,
  getFocusActiveContextSources,
  getContextSourceOnLabel,
  getVisibleContextSources,
  isContextSourceActive,
  normalizeContextModes,
  normalizeShowContextSourceLabels,
  normalizeVisibleContextSources,
} from "./askContextSources.js";

test("defaults to Conversation, Notes, and Memory", () => {
  assert.deepEqual(DEFAULT_VISIBLE_CONTEXT_SOURCES, ["conversation", "notes", "memory"]);
  assert.deepEqual(
    getVisibleContextSources(undefined).map((source) => source.id),
    DEFAULT_VISIBLE_CONTEXT_SOURCES,
  );
});

test("retains only configured sources while keeping toolbar order", () => {
  assert.deepEqual(
    getVisibleContextSources(["web", "notes", "drive"]).map((source) => source.id),
    ["conversation", "notes", "drive", "web"],
  );
});

test("Conversation cannot be hidden and invalid preferences fall back safely", () => {
  assert.deepEqual(normalizeVisibleContextSources(["notes"]), ["conversation", "notes"]);
  assert.deepEqual(normalizeVisibleContextSources(["retired-source"]), DEFAULT_VISIBLE_CONTEXT_SOURCES);
  assert.deepEqual(normalizeVisibleContextSources(["notes", "retired-source"]), DEFAULT_VISIBLE_CONTEXT_SOURCES);
  assert.deepEqual(normalizeVisibleContextSources("notes"), DEFAULT_VISIBLE_CONTEXT_SOURCES);
});

test("source modes remain independent of visibility preferences", () => {
  const modes = normalizeContextModes({ notes: "selected", memory: "automatic" });
  const visible = getVisibleContextSources(["conversation"]).map((source) => source.id);

  assert.deepEqual(visible, ["conversation"]);
  assert.deepEqual(modes, { ...DEFAULT_CONTEXT_MODES, notes: "selected", memory: "automatic" });
  assert.deepEqual(normalizeContextModes({ notes: "invalid" }), DEFAULT_CONTEXT_MODES);
});

test("Ask labels default on while preserving an explicit off preference", () => {
  assert.equal(normalizeShowContextSourceLabels(undefined), true);
  assert.equal(normalizeShowContextSourceLabels(false), false);
  assert.equal(normalizeShowContextSourceLabels(true), true);
});

test("active context sources mirror Ask toolbar active state", () => {
  const modes = normalizeContextModes({ notes: "selected", memory: "off", files: "automatic" });
  const state = { currentHistoryId: "hist-1", contextModes: modes };
  assert.equal(isContextSourceActive("conversation", state), true);
  assert.equal(isContextSourceActive("notes", state), true);
  assert.equal(isContextSourceActive("memory", state), false);
  assert.equal(isContextSourceActive("files", state), true);
  assert.equal(isContextSourceActive("conversation", { currentHistoryId: null, contextModes: modes }), false);

  const active = getActiveContextSources(
    ["conversation", "notes", "memory", "files"],
    state,
  ).map((source) => source.id);
  assert.deepEqual(active, ["conversation", "notes", "files"]);

  const focusActive = getFocusActiveContextSources(
    ["conversation", "notes", "memory", "files"],
    state,
  ).map((source) => source.id);
  assert.deepEqual(focusActive, ["notes", "files"]);
  assert.equal(getContextSourceOnLabel("Memory"), "Memory: ON");
});
