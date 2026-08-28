import test from "node:test";
import assert from "node:assert/strict";

import { renderWorkspaceIndicator } from "../../frontend/workspace-indicator.mjs";

function indicatorElement() {
  return {
    hidden: false,
    textContent: "",
  };
}

test("renderWorkspaceIndicator updates from the selected workspace display name", () => {
  const indicator = indicatorElement();
  const state = {
    workspaces: {
      selectedWorkspaceId: "project--abc--study-plans",
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
  };

  renderWorkspaceIndicator(indicator, state);

  assert.equal(indicator.hidden, false);
  assert.equal(indicator.textContent, " | Study Plans");

  renderWorkspaceIndicator(indicator, {
    workspaces: {
      ...state.workspaces,
      selectedWorkspaceId: "agent-col",
    },
  });

  assert.equal(indicator.hidden, false);
  assert.equal(indicator.textContent, " | Agent Col");
});

test("renderWorkspaceIndicator hides when the selected workspace is unknown", () => {
  const indicator = indicatorElement();

  renderWorkspaceIndicator(indicator, {
    workspaces: {
      selectedWorkspaceId: "project--missing",
      items: [],
    },
  });

  assert.equal(indicator.hidden, true);
  assert.equal(indicator.textContent, "");
});
