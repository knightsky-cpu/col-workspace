import { appendTextElement, element, setText } from "./render.mjs";

export function renderWorkspacePanel(container, workspaces, handlers = {}) {
  container.replaceChildren();
  if (workspaces.status === "loading") {
    appendTextElement(container, "p", "muted contain-text", "Loading Workspaces...");
    return;
  }
  if (workspaces.status === "error") {
    appendTextElement(
      container,
      "p",
      "form-error contain-text",
      workspaces.error ?? "Workspaces unavailable.",
    );
    return;
  }

  const items = Array.isArray(workspaces.items) ? workspaces.items : [];
  if (items.length === 0) {
    appendTextElement(container, "p", "muted contain-text", "No Workspaces loaded yet.");
  }
  for (const workspace of items) {
    const row = element("div", "workspace-list-row contain-text");
    const button = element("button", "work-list-item contain-text");
    button.type = "button";
    button.setAttribute("data-workspace-id", workspace.workspace_id);
    if (workspace.workspace_id === workspaces.selectedWorkspaceId) {
      button.setAttribute("aria-current", "true");
    }
    setText(button, workspace.display_name ?? "Workspace");
    button.addEventListener("click", () => {
      handlers.onSelectWorkspace?.(workspace);
    });
    row.append(button);
    if (items.length > 1) {
      const actions = element("div", "workspace-actions contain-text");
      const deleteButton = element("button", "", "Delete");
      deleteButton.type = "button";
      deleteButton.setAttribute("data-workspace-action", "delete");
      deleteButton.setAttribute("data-workspace-id", workspace.workspace_id);
      deleteButton.addEventListener("click", () => {
        if (globalThis.confirm?.(`Delete workspace: ${workspace.display_name ?? "Workspace"}?`) === false) {
          return;
        }
        handlers.onDeleteWorkspace?.(workspace);
      });
      actions.append(deleteButton);
      row.append(actions);
    }
    container.append(row);
  }

  const form = element("form", "workspace-create-form contain-text");
  const label = element("label", "", "New Workspace");
  const input = element("input");
  input.name = "display_name";
  input.autocomplete = "off";
  input.required = true;
  input.maxLength = 120;
  label.append(input);
  const button = element("button", "", "Create");
  button.type = "submit";
  form.append(label, button);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const displayName = input.value.trim();
    if (displayName) {
      handlers.onCreateWorkspace?.(displayName);
      input.value = "";
    }
  });
  container.append(form);
}

export function createWorkspaceView(elements, handlers = {}) {
  return {
    render(state) {
      renderWorkspacePanel(elements.panel, state.workspaces, handlers);
    },
  };
}
