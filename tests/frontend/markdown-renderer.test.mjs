import test from "node:test";
import assert from "node:assert/strict";

import { renderSafeMarkdown } from "../../frontend/markdown-renderer.mjs";

function node(tagName = "div") {
  return {
    tagName,
    localName: tagName,
    children: [],
    attributes: {},
    textContent: "",
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

function browserLikeNode(tagName = "div") {
  const created = node(tagName.toUpperCase());
  created.localName = tagName.toLowerCase();
  return created;
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

function useBasicDocument() {
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
}

function useBrowserLikeDocument() {
  globalThis.document = {
    createElement(tagName) {
      return browserLikeNode(tagName);
    },
    createTextNode(text) {
      const textNode = browserLikeNode("#text");
      textNode.textContent = String(text);
      return textNode;
    },
  };
}

function textTree(item) {
  return [
    item.textContent,
    ...item.children.flatMap((child) => textTree(child)),
  ].join(" ");
}

test("renderSafeMarkdown renders common model response structure without raw Markdown clutter", () => {
  useBasicDocument();
  const container = node();

  renderSafeMarkdown(container, [
    "### Root cause",
    "",
    "Use **bounded context** and `git diff --check`.",
    "",
    "- Read the docs",
    "- Run the tests",
    "",
    "```bash",
    "node --test tests/frontend/chat-view.test.mjs",
    "```",
    "",
    "| Time | Event |",
    "| --- | --- |",
    "| 09:00 | Fixed |",
  ].join("\n"));

  assert.equal(container.children[0].tagName, "h3");
  assert.equal(textTree(container.children[0]).trim(), "Root cause");
  assert.equal(container.children[1].tagName, "p");
  assert.equal(
    container.children[1].children.some((child) => child.tagName === "strong"),
    true,
  );
  assert.equal(
    container.children[1].children.some((child) => child.tagName === "code"),
    true,
  );
  assert.equal(container.children[2].tagName, "ul");
  assert.equal(container.children[2].children[0].tagName, "li");
  assert.equal(container.children[3].tagName, "pre");
  assert.equal(container.children[3].children[0].tagName, "code");
  assert.equal(container.children[4].tagName, "table");
  assert.doesNotMatch(textTree(container), /###|\*\*|```|\| --- \|/);
});

test("renderSafeMarkdown keeps raw HTML inert and link URLs bounded", () => {
  useBasicDocument();
  const container = node();

  renderSafeMarkdown(container, [
    "<img src=x onerror=alert(1)>",
    "",
    "[docs](https://example.com/path) [bad](javascript:alert(1))",
  ].join("\n"));

  const text = textTree(container);
  const paragraph = container.children[1];
  const safeLink = paragraph.children[0];

  assert.match(text, /<img src=x onerror=alert\(1\)>/);
  assert.equal(safeLink.tagName, "a");
  assert.equal(safeLink.attributes.href, "https://example.com/path");
  assert.equal(safeLink.attributes.rel, "noopener noreferrer");
  assert.equal(safeLink.attributes.target, "_blank");
  assert.doesNotMatch(JSON.stringify(container), /javascript:alert/);
});

test("renderSafeMarkdown renders ATX headings through level six", () => {
  useBasicDocument();
  const container = node();

  renderSafeMarkdown(container, [
    "#### Sources",
    "##### Level Five",
    "###### Level Six",
  ].join("\n"));

  assert.deepEqual(
    container.children.map((child) => child.tagName),
    ["h4", "h5", "h6"],
  );
  assert.equal(textTree(container.children[0]).trim(), "Sources");
  assert.equal(textTree(container.children[1]).trim(), "Level Five");
  assert.equal(textTree(container.children[2]).trim(), "Level Six");
  assert.doesNotMatch(textTree(container), /####|#####|######/);
});

test("renderSafeMarkdown renders standalone horizontal rules", () => {
  useBasicDocument();
  const container = node();

  renderSafeMarkdown(container, [
    "***",
    "---",
    "___",
    "- list item",
  ].join("\n"));

  assert.deepEqual(
    container.children.map((child) => child.tagName),
    ["hr", "hr", "hr", "ul"],
  );
  assert.equal(container.children[3].children[0].tagName, "li");
  assert.equal(textTree(container.children[3]).trim(), "list item");
  assert.doesNotMatch(textTree(container), /\*\*\*|---|___/);
});

test("renderSafeMarkdown keeps blocks when browser tagName values are uppercase", () => {
  useBrowserLikeDocument();
  const container = browserLikeNode();

  renderSafeMarkdown(container, "### Root cause\n\nRendered response text.");

  assert.equal(container.children.length, 2);
  assert.equal(container.children[0].tagName, "H3");
  assert.equal(textTree(container.children[0]).trim(), "Root cause");
  assert.equal(container.children[1].tagName, "P");
  assert.equal(textTree(container.children[1]).trim(), "Rendered response text.");
});

test("renderSafeMarkdown appends all rendered blocks from a stable snapshot", () => {
  useBasicDocument();
  const container = node();

  renderSafeMarkdown(container, [
    "### One",
    "",
    "Paragraph one.",
    "",
    "- First",
    "- Second",
  ].join("\n"));

  assert.deepEqual(
    container.children.map((child) => child.tagName),
    ["h3", "p", "ul"],
  );
});
