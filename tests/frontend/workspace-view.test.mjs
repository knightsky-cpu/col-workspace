import test from "node:test";
import assert from "node:assert/strict";

import { renderWorkspacePanel } from "../../frontend/workspace-view.mjs";

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

test("renderWorkspacePanel shows human labels without project ids", () => {
  const selected = [];
  const container = node();

  renderWorkspacePanel(
    container,
    {
      status: "ready",
      selectedWorkspaceId: "project--abc--study-plans",
      items: [
        {
          workspace_id: "project--abc--study-plans",
          display_name: "Study Plans",
        },
      ],
    },
    { onSelectWorkspace: (workspace) => selected.push(workspace) },
  );

  const text = textTree(container);
  assert.equal(text.includes("Study Plans"), true);
  assert.equal(text.includes("project--abc"), false);

  const button = findTree(container, (child) => (
    child.attributes["data-workspace-id"] === "project--abc--study-plans"
  ));
  assert.equal(button.attributes["aria-current"], "true");
  button.onclick();
  assert.equal(selected[0].display_name, "Study Plans");
});

test("renderWorkspacePanel shows delete action for non-final workspaces without archive", () => {
  const deleted = [];
  const container = node();

  renderWorkspacePanel(
    container,
    {
      status: "ready",
      selectedWorkspaceId: "agent-col",
      items: [
        {
          workspace_id: "agent-col",
          display_name: "Agent Col",
        },
        {
          workspace_id: "project--abc--study-plans",
          display_name: "Study Plans",
        },
      ],
    },
    { onDeleteWorkspace: (workspace) => deleted.push(workspace) },
  );

  const text = textTree(container);
  assert.equal(text.includes("Archive"), false);
  const deleteButton = findTree(container, (child) => (
    child.attributes["data-workspace-action"] === "delete"
    && child.attributes["data-workspace-id"] === "project--abc--study-plans"
  ));
  assert.ok(deleteButton);

  globalThis.confirm = () => true;
  deleteButton.onclick();
  assert.equal(deleted[0].workspace_id, "project--abc--study-plans");
  delete globalThis.confirm;
});

test("renderWorkspacePanel omits delete action for final remaining workspace", () => {
  const container = node();

  renderWorkspacePanel(
    container,
    {
      status: "ready",
      selectedWorkspaceId: "agent-col",
      items: [
        {
          workspace_id: "agent-col",
          display_name: "Agent Col",
        },
      ],
    },
  );

  const deleteButton = findTree(container, (child) => (
    child.attributes["data-workspace-action"] === "delete"
  ));
  assert.equal(deleteButton, null);
});

test("renderWorkspacePanel submits a bounded workspace display name", () => {
  const created = [];
  const container = node();

  renderWorkspacePanel(
    container,
    {
      status: "ready",
      selectedWorkspaceId: "agent-col",
      items: [],
    },
    { onCreateWorkspace: (displayName) => created.push(displayName) },
  );

  const form = findTree(container, (child) => child.tagName === "form");
  const input = findTree(form, (child) => child.tagName === "input");
  input.value = "Study Plans";
  form.onsubmit({ preventDefault() {} });

  assert.deepEqual(created, ["Study Plans"]);
});
