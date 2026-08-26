import test from "node:test";
import assert from "node:assert/strict";

import { renderNotesPanel } from "../../frontend/notes-view.mjs";

function node(tagName = "div") {
  return {
    tagName,
    children: [],
    attributes: {},
    value: "",
    disabled: false,
    textContent: "",
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
  ].join(" ");
}

function findTree(item, predicate) {
  if (predicate(item)) {
    return item;
  }
  for (const child of item.children) {
    const match = findTree(child, predicate);
    if (match) {
      return match;
    }
  }
  return null;
}

const pendingProposal = {
  proposal_id: "note-proposal-1",
  note_kind: "constraint",
  title: "API version",
  body: "Use API version 2.",
  status: "pending",
  source_session_id: "session-1",
  source_message_ids: ["message-1"],
  expires_at: "2099-01-01T00:00:00Z",
};

const activeNote = {
  note_id: "note-1",
  note_kind: "constraint",
  title: "API version",
  body: "Use API version 2.",
  status: "active",
  revision: 2,
  source_session_id: "session-1",
  source_message_ids: ["message-1"],
  source_event_id: "note-1--approved",
  updated_at: "2026-08-26T18:30:00Z",
};

test("renderNotesPanel shows pending proposals with approve and reject controls", () => {
  const container = node();
  const decisions = [];

  renderNotesPanel(container, {
    status: "ready",
    statusFilter: "active",
    pendingProposals: [pendingProposal],
    notes: [],
    selectedNoteId: null,
    detail: { status: "idle", note: null, events: [], error: null },
    pendingRequest: null,
    error: null,
  }, {
    onSubmitDecision: (decision) => decisions.push(decision),
  });

  const text = textTree(container);
  assert.match(text, /Pending note proposal/);
  assert.match(text, /Constraint/);
  assert.match(text, /API version/);
  assert.match(text, /Use API version 2\./);
  assert.doesNotMatch(text, /Saved note/);
  assert.doesNotMatch(text, /note-proposal-1/);

  const approve = findTree(container, (child) => (
    child.attributes["data-note-decision"] === "approve"
  ));
  const reject = findTree(container, (child) => (
    child.attributes["data-note-decision"] === "reject"
  ));
  approve.onclick();
  reject.onclick();

  assert.deepEqual(decisions, [
    { proposal_id: "note-proposal-1", decision: "approve" },
    { proposal_id: "note-proposal-1", decision: "reject" },
  ]);
});

test("renderNotesPanel shows active note detail and lifecycle controls", () => {
  const container = node();
  const events = [];

  renderNotesPanel(container, {
    status: "ready",
    statusFilter: "active",
    pendingProposals: [],
    notes: [activeNote],
    selectedNoteId: "note-1",
    detail: {
      status: "ready",
      note: activeNote,
      events: [{ event_id: "note-1--approved", event_type: "approved" }],
      error: null,
    },
    pendingRequest: null,
    error: null,
  }, {
    onSelectNote: (noteId) => events.push(["select", noteId]),
    onArchiveNote: (note) => events.push(["archive", note.note_id, note.revision]),
    onDeleteNote: (note) => events.push(["delete", note.note_id, note.revision]),
  });

  assert.match(textTree(container), /Saved note/);
  const noteButton = findTree(container, (child) => (
    child.attributes["data-note-id"] === "note-1"
  ));
  const archiveButton = findTree(container, (child) => (
    child.attributes["data-note-action"] === "archive"
  ));
  const deleteButton = findTree(container, (child) => (
    child.attributes["data-note-action"] === "delete"
  ));

  noteButton.onclick();
  archiveButton.onclick();
  deleteButton.onclick();

  assert.deepEqual(events, [
    ["select", "note-1"],
    ["archive", "note-1", 2],
    ["delete", "note-1", 2],
  ]);
});
