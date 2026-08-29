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
  createTextNode(text) {
    const textNode = node("#text");
    textNode.textContent = String(text);
    return textNode;
  },
};

function textTree(item) {
  return [
    item.textContent,
    ...item.children.flatMap((child) => textTree(child)),
  ].join(" ");
}

test("renderTranscript keeps user text literal and renders model Markdown structure", () => {
  const container = node();
  renderTranscript(container, [{
    request: { body: { message: "<img src=x onerror=alert(1)>" } },
    response: { response: "### Root cause\n\nUse **bounded context** and `git diff --check`." },
  }]);

  assert.equal(container.children.length, 1);
  const user = container.children[0].children[0];
  const model = container.children[0].children[1];
  assert.equal(user.tagName, "div");
  assert.equal(model.tagName, "div");
  assert.equal(user.children.length, 2);
  assert.equal(model.children.length, 2);
  assert.equal(user.children[0].tagName, "span");
  assert.equal(model.children[0].tagName, "span");
  assert.equal(user.children[0].attributes["aria-hidden"], "true");
  assert.equal(model.children[0].attributes["aria-hidden"], "true");
  assert.equal(user.children[0].classList.values.includes("turn-author-icon"), true);
  assert.equal(user.children[0].classList.values.includes("turn-author-icon--user"), true);
  assert.equal(model.children[0].classList.values.includes("turn-author-icon"), true);
  assert.equal(model.children[0].classList.values.includes("turn-author-icon--model"), true);
  assert.equal(
    user.children[1].textContent,
    "<img src=x onerror=alert(1)>",
  );
  assert.equal(model.children[1].children[0].tagName, "h3");
  assert.equal(textTree(model.children[1].children[0]).trim(), "Root cause");
  assert.equal(model.children[1].children[1].tagName, "p");
  assert.equal(
    model.children[1].children[1].children.some((child) => child.tagName === "strong"),
    true,
  );
  assert.equal(
    model.children[1].children[1].children.some((child) => child.tagName === "code"),
    true,
  );
  assert.doesNotMatch(textTree(model), /###|\*\*/);
  assert.equal(user.textContent, "");
  assert.equal(model.textContent, "");
});

test("renderTranscript shows an empty conversation title inside the transcript", () => {
  const container = node();

  renderTranscript(container, []);

  assert.equal(container.children.length, 1);
  assert.equal(container.children[0].tagName, "section");
  assert.equal(container.children[0].attributes["aria-labelledby"], "empty-conversation-title");
  assert.match(textTree(container), /Start a conversation/);
  assert.doesNotMatch(textTree(container), /Ask Agent Col for help/);
});

test("renderTranscript renders pending assistant text as safe Markdown", () => {
  const container = node();
  renderTranscript(
    container,
    [],
    { body: { message: "<img src=x onerror=alert(1)>" } },
    "### Draft\n\nUse **bounded context**.",
    null,
  );

  assert.equal(container.children.length, 1);
  const turn = container.children[0];
  const user = turn.children[0];
  const model = turn.children[1];
  assert.equal(turn.classList.values.includes("chat-turn--pending"), true);
  assert.equal(user.children[1].textContent, "<img src=x onerror=alert(1)>");
  assert.equal(model.children[1].children[0].tagName, "h3");
  assert.equal(textTree(model).includes("bounded context"), true);
  assert.doesNotMatch(textTree(model), /<img|###|\*\*/);
  assert.equal(turn.children.length, 2);
});

test("renderTranscript marks failed provisional text as incomplete", () => {
  const container = node();
  renderTranscript(
    container,
    [],
    null,
    "",
    {
      request: { body: { message: "hello" } },
      provisionalResponseText: "Incomplete **answer**",
    },
  );

  assert.equal(container.children.length, 1);
  const turn = container.children[0];
  assert.equal(turn.classList.values.includes("chat-turn--incomplete"), true);
  assert.equal(turn.attributes["aria-label"], "Incomplete assistant response");
  assert.match(textTree(turn), /Incomplete/);
  assert.match(textTree(turn), /answer/);
  assert.doesNotMatch(textTree(turn), /\*\*/);
  assert.equal(turn.children.length, 2);
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
  const receiptList = container.children[0];
  const adaptationDisclosure = container.children[1];
  assert.equal(container.children.length, 2);
  assert.match(text, /Url context/);
  assert.match(text, /Example Domain/);
  assert.match(text, /Blueprint/);
  assert.match(text, /Response length/);
  assert.equal(receiptList.tagName, "ul");
  assert.equal(adaptationDisclosure.tagName, "details");
  assert.equal(adaptationDisclosure.attributes.open, undefined);
  assert.equal(adaptationDisclosure.children[0].tagName, "summary");
  assert.equal(adaptationDisclosure.children[0].textContent, "Verified adaptations (1)");
  assert.doesNotMatch(textTree(receiptList), /Adaptation: Planning granularity/);
  assert.match(textTree(adaptationDisclosure), /Planning granularity/);
  assert.match(text, /Short plan first/);
  assert.doesNotMatch(text, /response_length--1/);
  assert.doesNotMatch(text, /planning_granularity--1/);
  assert.doesNotMatch(text, /planning_granularity--1--approved/);
  assert.doesNotMatch(text, /google_search/);
  assert.equal(
    receiptList.children.every((receipt) => (
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
  assert.equal(container.children.length, 1);
  assert.equal(container.children[0].tagName, "details");
  assert.equal(container.children[0].attributes.open, undefined);
  assert.equal(container.children[0].children[0].textContent, "Verified adaptations (1)");
  assert.match(text, /Development environments/);
  assert.match(text, /Macos, Linux/);
  assert.doesNotMatch(text, /development_environments--active-v2/);
  assert.doesNotMatch(text, /development_environments--active-v2--approved/);
  assert.doesNotMatch(text, /missing-category--1/);
});

test("renderReceipts labels collaborative note and continuity receipts distinctly", () => {
  const container = node();
  renderReceipts(container, {
    response: "I used note-1 in prose.",
    collaborative_note_proposals: [{
      proposal_id: "note-proposal-1",
      note_kind: "constraint",
      title: "API version",
      body: "Use API version 2.",
    }],
    collaborative_note_events: [{
      event_id: "note-1--approved",
      event_type: "approved",
      note_id: "note-1",
      title: "API version",
    }],
    continuity_receipts: [{
      receipt_id: "continuity--note-1--rev-2",
      source_kind: "collaborative_note",
      source_id: "note-1",
      display_label: "Used note: API version",
      match_reason: "exact_title",
    }],
  });

  const text = textTree(container);
  assert.match(text, /Note proposal: API version/);
  assert.match(text, /Note updated: API version/);
  assert.match(text, /Used note: API version/);
  assert.doesNotMatch(text, /note-proposal-1/);
  assert.doesNotMatch(text, /note-1--approved/);
  assert.doesNotMatch(text, /continuity--note-1/);
});

test("createChatView renders continuity choices as buttons without bodies or raw ids", () => {
  const form = node("form");
  const input = node("textarea");
  const submitButton = node("button");
  const retryButton = node("button");
  const transcript = node();
  const counter = node("span");
  const clarificationChoices = node("div");
  const continuityChoices = node("div");
  const selections = [];

  const view = createChatView({
    form,
    input,
    submitButton,
    retryButton,
    transcript,
    characterCount: counter,
    clarificationChoices,
    continuityChoices,
  }, {
    onSubmit: () => {},
    onRetry: () => {},
    onSelectContinuityChoice(choice) {
      selections.push(choice);
    },
  });

  view.render({
    transcript: [],
    lastFailure: null,
    pendingTurn: null,
    activeMemoryClarification: null,
    activeContinuityChoices: [
      {
        choice_id: "choice-1",
        source_kind: "collaborative_note",
        source_id: "note-1",
        display_label: "API version",
        match_reason: "bounded_relevance",
      },
    ],
  });

  assert.equal(continuityChoices.hidden, false);
  assert.equal(continuityChoices.children[0].tagName, "button");
  assert.equal(continuityChoices.children[0].attributes.type, "button");
  assert.equal(continuityChoices.children[0].textContent, "API version");
  assert.doesNotMatch(textTree(continuityChoices), /choice-1|note-1|Use API version/);

  continuityChoices.children[0].onclick();

  assert.deepEqual(selections, [{
    choice_id: "choice-1",
    source_kind: "collaborative_note",
    source_id: "note-1",
    display_label: "API version",
    match_reason: "bounded_relevance",
  }]);
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
  assert.equal(counter.attributes["data-character-count-level"], "safe");
});

test("createChatView sets character counter severity levels", () => {
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

  assert.equal(counter.textContent, "0 / 10000");
  assert.equal(counter.attributes["data-character-count-level"], "safe");

  input.value = "x".repeat(4999);
  input.oninput();
  assert.equal(counter.textContent, "4999 / 10000");
  assert.equal(counter.attributes["data-character-count-level"], "safe");

  input.value = "x".repeat(5000);
  input.oninput();
  assert.equal(counter.textContent, "5000 / 10000");
  assert.equal(counter.attributes["data-character-count-level"], "warn");

  input.value = "x".repeat(9000);
  input.oninput();
  assert.equal(counter.textContent, "9000 / 10000");
  assert.equal(counter.attributes["data-character-count-level"], "danger");
});

test("createChatView submits the existing form path once on Enter", () => {
  const form = node("form");
  const input = node("textarea");
  const submitButton = node("button");
  const retryButton = node("button");
  const transcript = node();
  const counter = node("span");
  const submitted = [];
  let requestSubmitCount = 0;

  form.requestSubmit = () => {
    requestSubmitCount += 1;
    form.onsubmit({ preventDefault() {} });
  };

  createChatView({
    form,
    input,
    submitButton,
    retryButton,
    transcript,
    characterCount: counter,
  }, {
    onSubmit: (message) => submitted.push(message),
    onRetry: () => {},
  });

  input.value = "Explain the current workspace.";
  let defaultPrevented = false;
  input.onkeydown({
    key: "Enter",
    shiftKey: false,
    preventDefault() {
      defaultPrevented = true;
    },
  });

  assert.equal(defaultPrevented, true);
  assert.equal(requestSubmitCount, 1);
  assert.deepEqual(submitted, ["Explain the current workspace."]);
});

test("createChatView leaves Shift+Enter to the textarea newline behavior", () => {
  const form = node("form");
  const input = node("textarea");
  const submitButton = node("button");
  const retryButton = node("button");
  const transcript = node();
  const counter = node("span");
  let requestSubmitCount = 0;
  let defaultPrevented = false;

  form.requestSubmit = () => {
    requestSubmitCount += 1;
  };

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

  input.value = "line one\n";
  input.onkeydown({
    key: "Enter",
    shiftKey: true,
    preventDefault() {
      defaultPrevented = true;
    },
  });

  assert.equal(defaultPrevented, false);
  assert.equal(requestSubmitCount, 0);
  assert.equal(input.value, "line one\n");
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
