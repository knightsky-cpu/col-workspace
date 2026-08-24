import test from "node:test";
import assert from "node:assert/strict";

import {
  createInitialLayoutState,
  setDrawerCollapsed,
  setSectionExpanded,
} from "../../frontend/workspace-layout.mjs";

test("drawer collapse state is explicit and reversible", () => {
  const initial = createInitialLayoutState();

  const collapsed = setDrawerCollapsed(initial, "left", true);
  assert.equal(collapsed.drawers.left, false);
  assert.equal(collapsed.drawers.right, true);

  const expanded = setDrawerCollapsed(collapsed, "left", false);
  assert.equal(expanded.drawers.left, true);
});

test("left drawer sections can collapse without changing neighboring sections", () => {
  const initial = createInitialLayoutState();

  const collapsedMemory = setSectionExpanded(initial, "memory", false);
  assert.equal(collapsedMemory.sections.work, true);
  assert.equal(collapsedMemory.sections.memory, false);
  assert.equal(collapsedMemory.sections.activity, true);

  const expandedMemory = setSectionExpanded(collapsedMemory, "memory", true);
  assert.equal(expandedMemory.sections.memory, true);
});
