import { setText } from "./render.mjs";

function selectedWorkspaceDisplayName(state) {
  const workspaces = state?.workspaces ?? {};
  const selectedWorkspaceId = workspaces.selectedWorkspaceId;
  const items = Array.isArray(workspaces.items) ? workspaces.items : [];
  const selected = items.find((workspace) => (
    workspace.workspace_id === selectedWorkspaceId
  ));
  return String(selected?.display_name ?? "").trim();
}

export function renderWorkspaceIndicator(element, state) {
  const displayName = selectedWorkspaceDisplayName(state);
  setText(element, displayName ? ` | ${displayName}` : "");
  element.hidden = !displayName;
}
