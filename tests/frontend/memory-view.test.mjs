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

function withConfirm(confirmHandler, callback) {
  const previousConfirm = globalThis.confirm;
  globalThis.confirm = confirmHandler;
  try {
    callback();
  } finally {
    if (previousConfirm === undefined) {
      delete globalThis.confirm;
    } else {
      globalThis.confirm = previousConfirm;
    }
  }
}

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
    identity_context: {
      preferred_name: {
        signal_id: "preferred_name--signal-1",
        value: "wifiknight",
        source_event_id: "preferred_name--signal-1--approved",
      },
    },
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
  assert.equal(text.includes("Response length"), true);
  assert.equal(text.includes("concise"), true);
  assert.equal(text.includes("Preferred name"), true);
  assert.equal(text.includes("wifiknight"), true);
  assert.equal(text.includes("Planning granularity"), true);
  assert.equal(text.includes("Micro steps"), true);
  assert.equal(text.includes("response_length"), false);
  assert.equal(text.includes("preferred_name"), false);
  assert.equal(text.includes("planning_granularity"), false);
  assert.equal(text.includes("micro_steps"), false);
  assert.equal(text.includes("response_length--signal-1--approved"), false);
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

test("renderMemoryPanel renders and approves list-valued V2 memory", () => {
  const approvals = [];
  const container = node();
  const v2Memory = {
    status: "ready",
    profile: {
      memory_schema_version: "2.0",
      memory_revision: 1,
      identity_context: {},
      active_preferences: {
        development_environments: {
          signal_id: "development_environments--active-v2",
          value: ["macos", "linux"],
          policy_version: "2.0",
          source_event_id: "development_environments--active-v2--approved",
        },
      },
    },
    unresolvedProposals: [{
      proposal_id: "development_environments--proposal-v2",
      category: "development_environments",
      proposed_value: ["macos", "linux"],
      policy_version: "2.0",
      status: "pending",
    }],
    events: [{
      event_id: "development_environments--active-v2--approved",
      event_type: "approved",
      category: "development_environments",
      value: ["macos", "linux"],
      policy_version: "2.0",
    }],
    next_event_id: null,
    error: null,
  };

  renderMemoryPanel(container, v2Memory, {
    onSubmitDecision: (decision) => approvals.push(decision),
    onRevokeSignal: () => {},
    onDeleteSignal: () => {},
  });

  const text = textTree(container);
  assert.equal(text.includes("Development environments"), true);
  assert.equal(text.includes("macos, linux"), true);
  assert.equal(text.includes("development_environments"), false);
  const proposalCard = findTree(container, (child) => (
    child.attributes["data-memory-proposal"] === (
      "development_environments--proposal-v2"
    )
  ));
  const approveButton = findTree(proposalCard, (child) => (
    child.attributes["data-memory-decision"] === "approve"
  ));
  approveButton.onclick();

  assert.deepEqual(approvals, [{
    proposal_id: "development_environments--proposal-v2",
    decision: "approve",
  }]);
});

test("renderMemoryPanel orders pending proposals before active preferences and events", () => {
  const container = node();

  renderMemoryPanel(container, memory, {
    onSubmitDecision: () => {},
  });

  const text = textTree(container);
  const pendingIndex = text.indexOf("Pending proposals");
  const activeIndex = text.indexOf("Active preferences");
  const recentIndex = text.indexOf("Recent memory events");

  assert.notEqual(pendingIndex, -1);
  assert.notEqual(activeIndex, -1);
  assert.notEqual(recentIndex, -1);
  assert.equal(pendingIndex < activeIndex, true);
  assert.equal(activeIndex < recentIndex, true);
});

test("renderMemoryPanel requires confirmation before revoking active preferences", () => {
  const revoked = [];
  const confirmMessages = [];
  const container = node();

  renderMemoryPanel(container, memory, {
    onSubmitDecision: () => {},
    onRevokeSignal: (signal) => revoked.push(signal),
    onDeleteSignal: () => {},
  });

  const signalCard = findTree(container, (child) => (
    child.attributes["data-memory-signal"] === "response_length--signal-1"
  ));
  assert.notEqual(signalCard, null);

  const revokeButton = findTree(signalCard, (child) => (
    child.attributes["data-memory-signal-action"] === "revoke"
  ));
  assert.notEqual(revokeButton, null);

  withConfirm((message) => {
    confirmMessages.push(message);
    return false;
  }, () => {
    revokeButton.onclick();
  });
  assert.deepEqual(revoked, []);

  withConfirm((message) => {
    confirmMessages.push(message);
    return true;
  }, () => {
    revokeButton.onclick();
  });
  assert.deepEqual(revoked, [{
    category: "response_length",
    signal_id: "response_length--signal-1",
    value: "concise",
    source_event_id: "response_length--signal-1--approved",
  }]);
  assert.equal(confirmMessages.length, 2);
  assert.equal(confirmMessages[0].includes("Revoke saved memory"), true);
  assert.equal(confirmMessages[0].includes("Response length · concise"), true);
  assert.equal(confirmMessages[0].includes("stops being active"), true);
  assert.equal(confirmMessages[0].includes("response_length--signal-1"), false);
  assert.equal(confirmMessages[0].includes("response_length--signal-1--approved"), false);
});

test("renderMemoryPanel requires confirmation before deleting identity context", () => {
  const deleted = [];
  const confirmMessages = [];
  const container = node();

  renderMemoryPanel(container, memory, {
    onSubmitDecision: () => {},
    onRevokeSignal: () => {},
    onDeleteSignal: (signal) => deleted.push(signal),
  });

  const signalCard = findTree(container, (child) => (
    child.attributes["data-memory-signal"] === "preferred_name--signal-1"
  ));
  assert.notEqual(signalCard, null);

  const deleteButton = findTree(signalCard, (child) => (
    child.attributes["data-memory-signal-action"] === "delete"
  ));
  assert.notEqual(deleteButton, null);

  withConfirm((message) => {
    confirmMessages.push(message);
    return false;
  }, () => {
    deleteButton.onclick();
  });
  assert.deepEqual(deleted, []);

  withConfirm((message) => {
    confirmMessages.push(message);
    return true;
  }, () => {
    deleteButton.onclick();
  });
  assert.deepEqual(deleted, [{
    category: "preferred_name",
    signal_id: "preferred_name--signal-1",
    value: "wifiknight",
    source_event_id: "preferred_name--signal-1--approved",
  }]);
  assert.equal(confirmMessages.length, 2);
  assert.equal(confirmMessages[0].includes("Delete saved memory"), true);
  assert.equal(confirmMessages[0].includes("Preferred name · wifiknight"), true);
  assert.equal(confirmMessages[0].includes("removed from inspection"), true);
  assert.equal(confirmMessages[0].includes("preferred_name--signal-1"), false);
  assert.equal(confirmMessages[0].includes("preferred_name--signal-1--approved"), false);
});

test("renderMemoryPanel renders list-valued destructive confirmations cleanly", () => {
  const deleted = [];
  const confirmMessages = [];
  const container = node();
  const listMemory = {
    status: "ready",
    profile: {
      identity_context: {},
      active_preferences: {
        development_environments: {
          signal_id: "development_environments--active-v2",
          value: ["macos", "linux"],
          source_event_id: "development_environments--active-v2--approved",
        },
      },
    },
    unresolvedProposals: [],
    events: [],
  };

  renderMemoryPanel(container, listMemory, {
    onSubmitDecision: () => {},
    onRevokeSignal: () => {},
    onDeleteSignal: (signal) => deleted.push(signal),
  });

  const signalCard = findTree(container, (child) => (
    child.attributes["data-memory-signal"] === "development_environments--active-v2"
  ));
  const deleteButton = findTree(signalCard, (child) => (
    child.attributes["data-memory-signal-action"] === "delete"
  ));

  withConfirm((message) => {
    confirmMessages.push(message);
    return true;
  }, () => {
    deleteButton.onclick();
  });

  assert.equal(confirmMessages[0].includes(
    "Development environments · macos, linux",
  ), true);
  assert.equal(confirmMessages[0].includes("development_environments--active-v2"), false);
  assert.equal(deleted.length, 1);
});

test("renderMemoryPanel keeps active preference IDs secondary to human labels", () => {
  const container = node();

  renderMemoryPanel(container, memory, {
    onSubmitDecision: () => {},
    onRevokeSignal: () => {},
    onDeleteSignal: () => {},
  });

  const signalCard = findTree(container, (child) => (
    child.attributes["data-memory-signal"] === "response_length--signal-1"
  ));
  assert.equal(signalCard.children[0].textContent, "Response length · concise");
  assert.equal(signalCard.children[1].textContent, "Saved memory");
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
