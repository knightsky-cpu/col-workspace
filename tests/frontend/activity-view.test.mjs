import test from "node:test";
import assert from "node:assert/strict";

import { renderActivityPanel } from "../../frontend/activity-view.mjs";

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

test("renderActivityPanel renders structured activity safely", () => {
  const container = node();

  renderActivityPanel(container, {
    entries: [
      {
        kind: "action",
        label: "propose_memory_signal",
        detail: "completed",
      },
      {
        kind: "memory",
        label: "preferred_name",
        detail: "preferred_name--proposal-1",
      },
      {
        kind: "error",
        label: "Request failed",
        detail: "<strong>not html</strong>",
      },
    ],
  });

  const text = textTree(container);
  assert.equal(text.includes("propose_memory_signal"), true);
  assert.equal(text.includes("preferred_name--proposal-1"), true);
  assert.equal(text.includes("<strong>not html</strong>"), true);
  assert.equal(
    container.children.every((child) => (
      child.classList.values.includes("contain-text")
    )),
    true,
  );
});

test("renderActivityPanel exposes an empty state", () => {
  const container = node();

  renderActivityPanel(container, { entries: [] });

  assert.equal(container.children.length, 1);
  assert.equal(container.children[0].textContent, "No activity yet.");
});
