import test from "node:test";
import assert from "node:assert/strict";

import { renderMemoryPanel } from "../../frontend/memory-view.mjs";

function node(tagName = "div") {
  return {
    tagName,
    children: [],
    attributes: {},
    dataset: {},
    value: "",
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

const memory = {
  status: "ready",
  profile: {
    memory_schema_version: "1.0",
    memory_revision: 1,
    identity_context: {},
    active_preferences: {
      response_length: {
        signal_id: "response_length--signal-1",
        value: "concise",
        source_event_id: "response_length--signal-1--approved",
      },
    },
  },
  unresolvedProposals: [
    {
      proposal_id: "planning_granularity--proposal-1",
      category: "planning_granularity",
      proposed_value: "micro_steps",
      status: "pending",
    },
  ],
  events: [
    {
      event_id: "response_length--signal-1--approved",
      event_type: "approved",
      category: "response_length",
      value: "concise",
    },
  ],
  next_event_id: "response_length--signal-1--approved",
  error: null,
};

test("renderMemoryPanel renders active preferences, proposals, and events safely", () => {
  const approvals = [];
  const container = node();

  renderMemoryPanel(container, memory, {
    onSubmitDecision: (decision) => approvals.push(decision),
  });

  const text = textTree(container);
  assert.equal(text.includes("response_length"), true);
  assert.equal(text.includes("concise"), true);
  assert.equal(text.includes("planning_granularity"), true);
  assert.equal(text.includes("micro_steps"), true);
  assert.equal(text.includes("response_length--signal-1--approved"), true);
  assert.equal(
    container.children.every((child) => (
      child.classList.values.includes("contain-text")
    )),
    true,
  );

  const proposalCard = container.children.find((child) => (
    child.attributes["data-memory-proposal"] === "planning_granularity--proposal-1"
  ));
  const approveButton = findTree(proposalCard, (child) => (
    child.attributes["data-memory-decision"] === "approve"
  ));
  approveButton.onclick();

  assert.deepEqual(approvals, [{
    proposal_id: "planning_granularity--proposal-1",
    decision: "approve",
  }]);
});

test("renderMemoryPanel exposes useful empty, loading, and error states", () => {
  const container = node();

  renderMemoryPanel(container, {
    status: "idle",
    profile: null,
    unresolvedProposals: [],
    events: [],
    error: null,
  }, { onSubmitDecision: () => {} });
  assert.equal(container.children[0].textContent, "No memory loaded yet.");

  renderMemoryPanel(container, {
    status: "loading",
    profile: null,
    unresolvedProposals: [],
    events: [],
    error: null,
  }, { onSubmitDecision: () => {} });
  assert.equal(container.children[0].textContent, "Loading memory…");

  renderMemoryPanel(container, {
    status: "error",
    profile: null,
    unresolvedProposals: [],
    events: [],
    error: "Memory unavailable.",
  }, { onSubmitDecision: () => {} });
  assert.equal(container.children[0].textContent, "Memory unavailable.");
});
