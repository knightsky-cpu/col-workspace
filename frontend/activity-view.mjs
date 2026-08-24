import { appendTextElement, humanLabel } from "./render.mjs";

function compactText(parts) {
  return parts.filter((part) => part !== undefined && part !== null && part !== "")
    .map((part) => String(part))
    .join(" · ");
}

export function renderActivityPanel(container, activity) {
  container.replaceChildren();
  const entries = Array.isArray(activity.entries) ? activity.entries : [];
  if (entries.length === 0) {
    appendTextElement(container, "p", "muted contain-text", "No activity yet.");
    return;
  }
  for (const entry of [...entries].reverse()) {
    appendTextElement(container, "p", "activity-event contain-text", compactText([
      humanLabel(entry.kind),
      humanLabel(entry.label),
      entry.detail && !String(entry.detail).includes("--") ? entry.detail : "",
    ]));
  }
}

export function createActivityView(elements) {
  return {
    render(state) {
      renderActivityPanel(elements.list, state.activity);
    },
  };
}
