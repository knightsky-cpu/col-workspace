import test from "node:test";
import assert from "node:assert/strict";

import { createChatView, renderReceipts, renderTranscript } from "../../frontend/chat-view.mjs";

function node(tagName = "div") {
  return {
    tagName,
    children: [],
    attributes: {},
    value: "",
    disabled: false,
    scrollHeight: 0,
    scrollTop: 0,
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

test("renderTranscript uses textContent for user and model text", () => {
  const container = node();
  renderTranscript(container, [{
    request: { body: { message: "<img src=x onerror=alert(1)>" } },
    response: { response: "<strong>not html</strong>" },
  }]);

  assert.equal(container.children.length, 1);
  assert.equal(
    container.children[0].children[0].textContent,
    "<img src=x onerror=alert(1)>",
  );
  assert.equal(
    container.children[0].children[1].textContent,
    "<strong>not html</strong>",
  );
});

test("renderReceipts renders structured fields and ignores prose claims", () => {
  const container = node();
  renderReceipts(container, {
    response: "I used google_search in prose.",
    actions: [{ action_name: "url_context", status: "completed" }],
    citations: [{ uri: "https://example.com/", label: "Example Domain" }],
    artifacts: [{
      artifact_type: "synthesis_blueprint",
      project_id: "agent-col",
      artifact_id: "blueprint--1",
      schema_version: "2.0",
      display_label: "Blueprint",
    }],
    memory_proposals: [{
      proposal_id: "response_length--1",
      category: "response_length",
    }],
    adaptations: [{
      signal_id: "planning_granularity--1",
      category: "planning_granularity",
      value: "short_plan_first",
      source_event_id: "planning_granularity--1--approved",
      status: "provided_to_model",
    }],
  });

  const text = textTree(container);
  assert.match(text, /Url context/);
  assert.match(text, /Example Domain/);
  assert.match(text, /Blueprint/);
  assert.match(text, /Response length/);
  assert.match(text, /Adaptation: Planning granularity/);
  assert.match(text, /Short plan first/);
  assert.doesNotMatch(text, /response_length--1/);
  assert.doesNotMatch(text, /planning_granularity--1/);
  assert.doesNotMatch(text, /planning_granularity--1--approved/);
  assert.doesNotMatch(text, /google_search/);
  assert.equal(
    container.children[0].children.every((receipt) => (
      receipt.classList.values.includes("contain-text")
    )),
    true,
  );
});

test("renderReceipts renders list-valued adaptation proof without raw ids", () => {
  const container = node();
  renderReceipts(container, {
    response: "I used memory in prose from development_environments--active-v2.",
    adaptations: [
      {
        signal_id: "development_environments--active-v2",
        category: "development_environments",
        value: ["macos", "linux"],
        policy_version: "2.0",
        source_event_id: "development_environments--active-v2--approved",
        status: "provided_to_model",
      },
      null,
      {
        signal_id: "missing-category--1",
        source_event_id: "missing-category--1--approved",
      },
    ],
  });

  const text = textTree(container);
  assert.match(text, /Adaptation: Development environments/);
  assert.match(text, /Macos, Linux/);
  assert.doesNotMatch(text, /development_environments--active-v2/);
  assert.doesNotMatch(text, /development_environments--active-v2--approved/);
  assert.doesNotMatch(text, /missing-category--1/);
});

test("createChatView updates the character counter from prompt input", () => {
  const form = node("form");
  const input = node("textarea");
  const submitButton = node("button");
  const retryButton = node("button");
  const transcript = node();
  const counter = node("span");

  createChatView({
    form,
    input,
    submitButton,
    retryButton,
    transcript,
    characterCount: counter,
  }, {
    onSubmit: () => {},
    onRetry: () => {},
  });

  input.value = "hello";
  input.oninput();

  assert.equal(counter.textContent, "5 / 10000");
});

test("createChatView scrolls the transcript to the latest rendered turn", () => {
  const form = node("form");
  const input = node("textarea");
  const submitButton = node("button");
  const retryButton = node("button");
  const transcript = node();
  const counter = node("span");
  transcript.scrollHeight = 1200;

  const view = createChatView({
    form,
    input,
    submitButton,
    retryButton,
    transcript,
    characterCount: counter,
  }, {
    onSubmit: () => {},
    onRetry: () => {},
  });

  view.render({
    transcript: [{
      request: { body: { message: "question" } },
      response: { response: "answer" },
    }],
    lastFailure: null,
    pendingTurn: null,
  });

  assert.equal(transcript.scrollTop, 1200);
});

test("createChatView renders active memory clarification choices without internal ids", () => {
  const form = node("form");
  const input = node("textarea");
  const submitButton = node("button");
  const retryButton = node("button");
  const transcript = node();
  const counter = node("span");
  const clarificationChoices = node("div");
  const selections = [];

  const view = createChatView({
    form,
    input,
    submitButton,
    retryButton,
    transcript,
    characterCount: counter,
    clarificationChoices,
  }, {
    onSubmit: () => {},
    onRetry: () => {},
    onSelectMemoryClarification(choice) {
      selections.push(choice);
    },
  });

  view.render({
    transcript: [],
    lastFailure: null,
    pendingTurn: null,
    activeMemoryClarification: {
      clarification_id: "memory-clarification--clarify-1",
      expires_at: "2099-01-01T00:00:00Z",
      choices: [
        {
          candidate_index: 0,
          category_label: "Response length",
          value_label: "Detailed",
        },
        {
          candidate_index: 1,
          category_label: "Explanation structure",
          value_label: "Step by step",
        },
      ],
    },
  });

  assert.equal(clarificationChoices.hidden, false);
  assert.equal(clarificationChoices.children.length, 2);
  assert.equal(
    clarificationChoices.children[0].textContent,
    "Response length: Detailed",
  );
  assert.equal(clarificationChoices.children[0].attributes.type, "button");
  assert.equal(clarificationChoices.children[0].disabled, false);
  assert.doesNotMatch(textTree(clarificationChoices), /memory-clarification--/);

  clarificationChoices.children[0].onclick();

  assert.equal(selections.length, 1);
  assert.equal(selections[0].candidate_index, 0);
  assert.equal(
    selections[0].clarification_id,
    "memory-clarification--clarify-1",
  );
});

test("createChatView disables clarification choices while pending or expired", () => {
  const form = node("form");
  const input = node("textarea");
  const submitButton = node("button");
  const retryButton = node("button");
  const transcript = node();
  const counter = node("span");
  const clarificationChoices = node("div");
  let calls = 0;

  const view = createChatView({
    form,
    input,
    submitButton,
    retryButton,
    transcript,
    characterCount: counter,
    clarificationChoices,
  }, {
    onSubmit: () => {},
    onRetry: () => {},
    onSelectMemoryClarification() {
      calls += 1;
    },
  });

  view.render({
    transcript: [],
    lastFailure: null,
    pendingTurn: { key: "chat--pending", body: { message: "pending" } },
    activeMemoryClarification: {
      clarification_id: "memory-clarification--clarify-1",
      expires_at: "2099-01-01T00:00:00Z",
      choices: [{
        candidate_index: 0,
        category_label: "Response length",
        value_label: "Detailed",
      }],
    },
  });

  assert.equal(clarificationChoices.children[0].disabled, true);
  clarificationChoices.children[0].onclick();
  assert.equal(calls, 0);

  view.render({
    transcript: [],
    lastFailure: null,
    pendingTurn: null,
    activeMemoryClarification: {
      clarification_id: "memory-clarification--clarify-1",
      expires_at: "2000-01-01T00:00:00Z",
      choices: [{
        candidate_index: 0,
        category_label: "Response length",
        value_label: "Detailed",
      }],
    },
  });

  assert.equal(clarificationChoices.children[0].disabled, true);
});
