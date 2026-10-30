// IA/frontend/src/askCommands.js
// Registry and helpers for Ask message-prefix commands (IntelliSense autocomplete).

/** @typedef {{ name: string, description: string, isEnabled?: (settings: object) => boolean }} AskCommand */

/** @type {AskCommand[]} */
export const ASK_COMMANDS = [
  {
    name: "!remember",
    description: "Save the following text to Memory.",
    isEnabled: (settings) => settings?.remember_command_enabled !== false,
  },
];

/**
 * When the caret is typing a message-prefix command token, return its bounds and query.
 * @returns {{ query: string, tokenStart: number, tokenEnd: number } | null}
 */
export function getActiveCommandToken(value, caretIndex) {
  if (typeof value !== "string" || caretIndex < 0) return null;
  const before = value.slice(0, caretIndex);
  if (before.includes("\n")) return null;
  const match = before.match(/^(\s*)(![^\s]*)$/);
  if (!match) return null;
  const [, leading, token] = match;
  if (!token.startsWith("!")) return null;
  return {
    query: token,
    tokenStart: leading.length,
    tokenEnd: caretIndex,
  };
}

/** @param {AskCommand[]} [commands] */
export function filterAskCommands(query, commands = ASK_COMMANDS) {
  if (!query || !query.startsWith("!")) return [];
  const lower = query.toLowerCase();
  return commands.filter((command) => command.name.toLowerCase().startsWith(lower));
}

/** @param {object} [settings] */
export function listAvailableAskCommands(settings = {}) {
  return ASK_COMMANDS.filter((command) => {
    if (typeof command.isEnabled === "function") {
      return command.isEnabled(settings);
    }
    return true;
  });
}

export function acceptAskCommand(value, caretIndex, commandName, tokenStart, tokenEnd) {
  const before = value.slice(0, tokenStart);
  const after = value.slice(caretIndex);
  const nextValue = `${before}${commandName} ${after}`;
  const nextCaret = tokenStart + commandName.length + 1;
  return { value: nextValue, caret: nextCaret };
}
