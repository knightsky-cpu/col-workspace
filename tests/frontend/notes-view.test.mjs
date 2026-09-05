import test from "node:test";
import assert from "node:assert/strict";

import { createNotesView, renderNotesPanel } from "../../frontend/notes-view.mjs";

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

function notesState(overrides = {}) {
  return {
    notes: {
      status: "ready",
      statusFilter: "active",
      pendingProposals: [],
      notes: [activeNote],
      selectedNoteId: null,
      detail: { status: "idle", note: null, events: [], error: null },
      pendingRequest: null,
      error: null,
      ...overrides,
    },
    disclosure: {
      notes: {
        proposalIds: [],
        detailNoteIds: [],
      },
    },
  };
}

function noteProposalForm(container) {
  return findTree(container, (child) => (
    child.attributes["data-note-proposal-form"] === "true"
  ));
}

function noteCorrectionForm(container) {
  return findTree(container, (child) => (
    child.classList?.values?.includes("notes-correction-form")
  ));
}

function namedField(form, name) {
  return findTree(form, (child) => child.attributes.name === name);
}

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
  assert.doesNotMatch(text, /Use API version 2\./);
  assert.doesNotMatch(text, /Saved note/);
  assert.doesNotMatch(text, /note-proposal-1/);

  const proposalCard = findTree(container, (child) => (
    child.attributes["data-note-proposal"] === "note-proposal-1"
  ));
  assert.notEqual(proposalCard, null);
  const collapsedToggle = findTree(proposalCard, (child) => (
    child.attributes["data-disclosure-toggle"] === "note-proposal"
  ));
  assert.notEqual(collapsedToggle, null);
  assert.equal(collapsedToggle.attributes["aria-expanded"], "false");
  assert.equal(
    findTree(proposalCard, (child) => child.attributes["data-note-decision"]),
    null,
  );

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
  }, {
    proposalIds: ["note-proposal-1"],
    detailNoteIds: [],
  });

  const approve = findTree(container, (child) => (
    child.attributes["data-note-decision"] === "approve"
  ));
  const reject = findTree(container, (child) => (
    child.attributes["data-note-decision"] === "reject"
  ));
  assert.match(textTree(container), /Use API version 2\./);
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
    onToggleDetailDisclosure: (noteId) => events.push(["toggle", noteId]),
  }, {
    proposalIds: [],
    detailNoteIds: ["note-1"],
  });

  assert.match(textTree(container), /Saved note/);
  const noteButton = findTree(container, (child) => (
    child.attributes["data-note-id"] === "note-1"
  ));
  const detailCard = findTree(container, (child) => (
    child.attributes["data-note-detail"] === "note-1"
  ));
  assert.notEqual(detailCard, null);
  assert.equal(detailCard, noteButton);
  const collapsedToggle = findTree(detailCard, (child) => (
    child.attributes["data-disclosure-toggle"] === "note-detail"
  ));
  assert.notEqual(collapsedToggle, null);
  assert.equal(collapsedToggle.attributes["aria-expanded"], "true");
  assert.notEqual(
    findTree(detailCard, (child) => child.attributes["data-note-action"] === "delete"),
    null,
  );

  detailCard.onclick({ target: detailCard });
  assert.deepEqual(events, [["toggle", "note-1"]]);

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
  }, {
    proposalIds: [],
    detailNoteIds: ["note-1"],
  });

  const archiveButton = findTree(container, (child) => (
    child.attributes["data-note-action"] === "archive"
  ));
  const deleteButton = findTree(container, (child) => (
    child.attributes["data-note-action"] === "delete"
  ));
  const expandedDetailCard = findTree(container, (child) => (
    child.attributes["data-note-detail"] === "note-1"
  ));
  const formIndex = container.children.findIndex((child) => (
    child.attributes["data-note-proposal-form"] === "true"
  ));
  const detailIndex = container.children.indexOf(expandedDetailCard);
  assert.ok(detailIndex >= 0);
  assert.ok(formIndex > detailIndex);
  assert.equal(findTree(expandedDetailCard, (child) => (
    child.attributes["data-note-action"] === "archive"
  )), archiveButton);

  archiveButton.onclick();
  deleteButton.onclick();

  assert.deepEqual(events, [
    ["toggle", "note-1"],
    ["archive", "note-1", 2],
    ["delete", "note-1", 2],
  ]);
});

test("renderNotesPanel places direct note proposal form after saved notes", () => {
  const container = node();
  const submissions = [];

  renderNotesPanel(container, {
    status: "ready",
    statusFilter: "active",
    pendingProposals: [],
    notes: [activeNote],
    selectedNoteId: null,
    detail: { status: "idle", note: null, events: [], error: null },
    pendingRequest: null,
    error: null,
  }, {
    onCreateNoteProposal: (request) => submissions.push(request),
  });

  const noteIndex = container.children.findIndex((child) => (
    child.attributes["data-note-id"] === "note-1"
  ));
  const formIndex = container.children.findIndex((child) => (
    child.attributes["data-note-proposal-form"] === "true"
  ));
  assert.ok(noteIndex >= 0);
  assert.ok(formIndex > noteIndex);

  const kind = findTree(container, (child) => child.attributes.name === "note_kind");
  const title = findTree(container, (child) => child.attributes.name === "title");
  const body = findTree(container, (child) => child.attributes.name === "body");
  const submit = findTree(container, (child) => child.attributes.type === "submit");

  assert.deepEqual(
    kind.children.map((child) => child.value),
    ["decision", "requirement", "constraint", "task_state", "working_context"],
  );
  assert.equal(title.attributes.maxlength, "120");

  kind.value = "constraint";
  title.value = "API version";
  body.value = "Use API version 2.";
  container.children[formIndex].onsubmit({ preventDefault() {} });

  assert.equal(submit.textContent, "Create note proposal");
  assert.deepEqual(submissions, [{
    note_kind: "constraint",
    title: "API version",
    body: "Use API version 2.",
  }]);
});

test("createNotesView preserves create-note draft across rerender and clears on submit success", async () => {
  const panel = node();
  const submissions = [];
  const view = createNotesView({ panel }, {
    onCreateNoteProposal: async (request) => {
      submissions.push(request);
    },
  });

  view.render(notesState());
  let form = noteProposalForm(panel);
  let kind = namedField(form, "note_kind");
  let title = namedField(form, "title");
  let body = namedField(form, "body");
  kind.value = "working_context";
  kind.onchange?.();
  title.value = "Frontend draft";
  title.oninput?.();
  body.value = "Keep this local draft while chat completes.";
  body.oninput?.();

  view.render(notesState({
    notes: [{
      ...activeNote,
      title: "API version refreshed",
    }],
  }));

  form = noteProposalForm(panel);
  kind = namedField(form, "note_kind");
  title = namedField(form, "title");
  body = namedField(form, "body");
  assert.equal(kind.value, "working_context");
  assert.equal(title.value, "Frontend draft");
  assert.equal(body.value, "Keep this local draft while chat completes.");

  await form.onsubmit({ preventDefault() {} });
  assert.deepEqual(submissions, [{
    note_kind: "working_context",
    title: "Frontend draft",
    body: "Keep this local draft while chat completes.",
  }]);

  view.render(notesState());
  form = noteProposalForm(panel);
  assert.equal(namedField(form, "note_kind").value, "decision");
  assert.equal(namedField(form, "title").value, "");
  assert.equal(namedField(form, "body").value, "");
});

test("createNotesView preserves correction draft by note revision without leaking to another identity", async () => {
  const panel = node();
  const corrections = [];
  const view = createNotesView({ panel }, {
    onCreateCorrection: async (note, request) => {
      corrections.push([note.note_id, request]);
    },
  });
  const expanded = {
    notes: {
      proposalIds: [],
      detailNoteIds: ["note-1"],
    },
  };

  view.render({
    ...notesState({
      selectedNoteId: "note-1",
      detail: { status: "ready", note: activeNote, events: [], error: null },
    }),
    disclosure: expanded,
  });
  let form = noteCorrectionForm(panel);
  let title = namedField(form, "title");
  let body = namedField(form, "body");
  title.value = "Draft correction";
  title.oninput?.();
  body.value = "Keep correction text through refresh.";
  body.oninput?.();

  view.render({
    ...notesState({
      selectedNoteId: "note-1",
      detail: { status: "ready", note: activeNote, events: [], error: null },
    }),
    disclosure: expanded,
  });
  form = noteCorrectionForm(panel);
  assert.equal(namedField(form, "title").value, "Draft correction");
  assert.equal(namedField(form, "body").value, "Keep correction text through refresh.");

  view.render({
    ...notesState({
      notes: [{ ...activeNote, revision: 3 }],
      selectedNoteId: "note-1",
      detail: {
        status: "ready",
        note: { ...activeNote, revision: 3 },
        events: [],
        error: null,
      },
    }),
    disclosure: expanded,
  });
  form = noteCorrectionForm(panel);
  assert.equal(namedField(form, "title").value, "API version");
  assert.equal(namedField(form, "body").value, "Use API version 2.");

  title = namedField(form, "title");
  body = namedField(form, "body");
  title.value = "Submitted correction";
  title.oninput?.();
  body.value = "Submit this correction.";
  body.oninput?.();
  await form.onsubmit({ preventDefault() {} });

  assert.equal(corrections.length, 1);
  assert.equal(corrections[0][0], "note-1");
  assert.equal(corrections[0][1].title, "Submitted correction");
  view.render({
    ...notesState({
      notes: [{ ...activeNote, revision: 3 }],
      selectedNoteId: "note-1",
      detail: {
        status: "ready",
        note: { ...activeNote, revision: 3 },
        events: [],
        error: null,
      },
    }),
    disclosure: expanded,
  });
  form = noteCorrectionForm(panel);
  assert.equal(namedField(form, "title").value, "API version");
  assert.equal(namedField(form, "body").value, "Use API version 2.");
});
