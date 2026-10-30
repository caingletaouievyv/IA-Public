// IA/frontend/src/askCommands.test.js

import assert from "node:assert/strict";
import test from "node:test";
import {
  acceptAskCommand,
  filterAskCommands,
  getActiveCommandToken,
  listAvailableAskCommands,
} from "./askCommands.js";

test("getActiveCommandToken matches only message-prefix command tokens", () => {
  assert.deepEqual(getActiveCommandToken("!", 1), { query: "!", tokenStart: 0, tokenEnd: 1 });
  assert.deepEqual(getActiveCommandToken("!rem", 4), { query: "!rem", tokenStart: 0, tokenEnd: 4 });
  assert.equal(getActiveCommandToken("hello !rem", 10), null);
  assert.equal(getActiveCommandToken("!remember saved", 15), null);
  assert.equal(getActiveCommandToken("line\n!", 6), null);
});

test("filterAskCommands narrows prefix matches", () => {
  const available = listAvailableAskCommands({ remember_command_enabled: true });
  assert.equal(filterAskCommands("!", available).length, 1);
  assert.equal(filterAskCommands("!rem", available)[0]?.name, "!remember");
  assert.deepEqual(filterAskCommands("!unknown", available), []);
});

test("listAvailableAskCommands respects settings gates", () => {
  assert.equal(listAvailableAskCommands({ remember_command_enabled: false }).length, 0);
  assert.equal(listAvailableAskCommands({ remember_command_enabled: true }).length, 1);
});

test("acceptAskCommand preserves trailing text and caret position", () => {
  const result = acceptAskCommand("!remdetail here", 4, "!remember", 0, 4);
  assert.equal(result.value, "!remember detail here");
  assert.equal(result.caret, 10);
});
