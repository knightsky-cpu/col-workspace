import test from "node:test";
import assert from "node:assert/strict";

import { renderReceipts, renderTranscript } from "../../frontend/chat-view.mjs";

function node(tagName = "div") {
  return {
    tagName,
    children: [],
    attributes: {},
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
    }],
  });

  const text = textTree(container);
  assert.match(text, /url_context/);
  assert.match(text, /Example Domain/);
  assert.match(text, /Blueprint/);
  assert.match(text, /response_length--1/);
  assert.match(text, /planning_granularity--1/);
  assert.doesNotMatch(text, /google_search/);
  assert.equal(
    container.children[0].children.every((receipt) => (
      receipt.classList.values.includes("contain-text")
    )),
    true,
  );
});
