import test from "node:test";
import assert from "node:assert/strict";

import {
  createInitialLayoutState,
  isDrawerExpanded,
  setArtifactDrawerMode,
  setDrawerCollapsed,
  setSectionExpanded,
} from "../../frontend/workspace-layout.mjs";

test("drawer sections are collapsed by default", () => {
  const initial = createInitialLayoutState();

  assert.equal(initial.sections.work, false);
  assert.equal(initial.sections.memory, false);
  assert.equal(initial.sections.chats, false);
});

test("drawer collapse state is explicit and reversible", () => {
  const initial = createInitialLayoutState();

  const collapsed = setDrawerCollapsed(initial, "left", true);
  assert.equal(collapsed.drawers.left, false);
  assert.equal(collapsed.drawers.right, true);

  const expanded = setDrawerCollapsed(collapsed, "left", false);
  assert.equal(expanded.drawers.left, true);
});

test("artifact drawer mode supports hidden normal and expanded states", () => {
  const initial = createInitialLayoutState();

  assert.equal(initial.artifactDrawerMode, "normal");
  assert.equal(isDrawerExpanded(initial, "right"), true);

  const expanded = setArtifactDrawerMode(initial, "expanded");
  assert.equal(expanded.artifactDrawerMode, "expanded");
  assert.equal(isDrawerExpanded(expanded, "right"), true);

  const hidden = setArtifactDrawerMode(expanded, "hidden");
  assert.equal(hidden.artifactDrawerMode, "hidden");
  assert.equal(isDrawerExpanded(hidden, "right"), false);

  const normal = setArtifactDrawerMode(hidden, "normal");
  assert.equal(normal.artifactDrawerMode, "normal");
  assert.equal(isDrawerExpanded(normal, "right"), true);
});

test("left drawer sections can collapse without changing neighboring sections", () => {
  const initial = createInitialLayoutState();

  const expandedMemory = setSectionExpanded(initial, "memory", true);
  assert.equal(expandedMemory.sections.work, false);
  assert.equal(expandedMemory.sections.memory, true);
  assert.equal(expandedMemory.sections.chats, false);

  const collapsedMemory = setSectionExpanded(expandedMemory, "memory", false);
  assert.equal(collapsedMemory.sections.memory, false);

  assert.throws(
    () => setSectionExpanded(initial, "activity", true),
    /Unsupported section/,
  );
});
