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
    container.append(button);
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
