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
      selectedSessionId: null,
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
  assert.equal(textTree(container).includes("session--1"), false);
  const sessionCard = container.children[0];
  assert.equal(sessionCard.attributes["data-session-id"], "session--1");
  assert.equal(sessionCard.attributes["aria-current"], undefined);
  assert.equal(sessionCard.tagName, "button");
  assert.equal(sessionCard.attributes["data-disclosure-toggle"], "chat-session");
  assert.equal(sessionCard.attributes["data-session-open"], "session--1");
  assert.equal(sessionCard.attributes["aria-expanded"], "false");
  assert.equal(
    sessionCard.children.some((child) => (
      child.attributes["data-disclosure-toggle"] === "chat-session"
      && child !== sessionCard
    )),
    false,
  );
  assert.equal(textTree(sessionCard).includes("last: model"), false);

  sessionCard.onclick();
  assert.deepEqual(selected, ["session--1"]);
});

test("renderChatsPanel collapses selected session metadata without reopening the chat", () => {
  const container = node();
  const selected = [];
  const toggled = [];

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
      onToggleSessionDisclosure(sessionId) {
        toggled.push(sessionId);
      },
    },
    {
      sessionIds: ["session--1"],
    },
  );

  const sessionCard = container.children[0];
  assert.equal(sessionCard.tagName, "button");
  assert.equal(sessionCard.attributes["data-disclosure-toggle"], "chat-session");
  assert.equal(sessionCard.attributes["aria-expanded"], "true");
  assert.equal(textTree(sessionCard).includes("last: model"), true);
  sessionCard.onclick();
  assert.deepEqual(toggled, ["session--1"]);
  assert.deepEqual(selected, []);
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
