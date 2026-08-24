import test from "node:test";
import assert from "node:assert/strict";

import { renderChatsPanel } from "../../frontend/chats-view.mjs";

function node(tagName = "div") {
  return {
    tagName,
    children: [],
    attributes: {},
    textContent: "",
    type: "",
    hidden: false,
    append(...items) {
      this.children.push(...items);
    },
    replaceChildren(...items) {
      this.children = items;
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    addEventListener(name, handler) {
      this[`on${name}`] = handler;
    },
    classList: {
      values: [],
      add(...values) {
        this.values.push(...values);
      },
    },
  };
}

globalThis.document = {
  createElement(tagName) {
    return node(tagName);
  },
};

function textTree(item) {
  return [
    item.textContent,
    ...item.children.flatMap((child) => textTree(child)),
  ].join(" ").trim();
}

test("renderChatsPanel renders human-facing session cards", () => {
  const container = node();
  const selected = [];

  renderChatsPanel(
    container,
    {
      status: "loaded",
      selectedSessionId: "session--1",
      sessions: [
        {
          session_id: "session--1",
          last_message_preview: "Plan the artifact viewer",
          last_message_role: "model",
          updated_at: "2026-08-24T10:00:00Z",
        },
      ],
    },
    {
      onSelectSession(sessionId) {
        selected.push(sessionId);
      },
    },
  );

  assert.equal(textTree(container).includes("Plan the artifact viewer"), true);
  assert.equal(container.children[0].attributes["data-session-id"], "session--1");
  assert.equal(container.children[0].attributes["aria-current"], "true");
  container.children[0].onclick();
  assert.deepEqual(selected, ["session--1"]);
});

test("renderChatsPanel exposes loading, error, and empty states", () => {
  const container = node();

  renderChatsPanel(container, { status: "loading", sessions: [] });
  assert.equal(textTree(container), "Loading chats...");

  renderChatsPanel(container, {
    status: "error",
    error: "Session list failed.",
    sessions: [],
  });
  assert.equal(textTree(container), "Session list failed.");

  renderChatsPanel(container, { status: "loaded", sessions: [] });
  assert.equal(textTree(container), "No saved chats yet.");
});
