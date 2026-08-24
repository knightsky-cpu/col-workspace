import { appendTextElement, element } from "./render.mjs";

function compactText(parts) {
  return parts.filter((part) => part !== undefined && part !== null && part !== "")
    .map((part) => String(part))
    .join(" · ");
}

function stringValue(value) {
  if (value === undefined || value === null) {
    return "";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function activePreferences(profile) {
  if (!profile || typeof profile.active_preferences !== "object") {
    return [];
  }
  return Object.entries(profile.active_preferences ?? {})
    .filter(([, signal]) => signal && typeof signal === "object")
    .map(([category, signal]) => ({
      category,
      signal_id: signal.signal_id,
      value: signal.value,
      source_event_id: signal.source_event_id,
    }));
}

function renderActivePreferences(container, preferences) {
  appendTextElement(container, "h3", "work-heading contain-text", "Active preferences");
  if (preferences.length === 0) {
    appendTextElement(container, "p", "muted contain-text", "No active preferences.");
    return;
  }
  for (const preference of preferences) {
    appendTextElement(container, "p", "memory-card contain-text", compactText([
      preference.category,
      stringValue(preference.value),
      preference.signal_id,
      preference.source_event_id,
    ]));
  }
}

function renderProposal(container, proposal, handlers) {
  const card = element("div", "memory-card contain-text");
  card.setAttribute("data-memory-proposal", proposal.proposal_id);
  appendTextElement(card, "p", "work-heading contain-text", compactText([
    proposal.category,
    stringValue(proposal.proposed_value),
  ]));
  appendTextElement(card, "p", "muted contain-text", compactText([
    proposal.proposal_id,
    proposal.status,
    proposal.expires_at,
  ]));

  const actions = element("div", "memory-actions contain-text");
  const approve = element("button", "", "Approve");
  approve.setAttribute("type", "button");
  approve.setAttribute("data-memory-decision", "approve");
  approve.addEventListener("click", () => {
    handlers.onSubmitDecision({
      proposal_id: proposal.proposal_id,
      decision: "approve",
    });
  });
  const reject = element("button", "", "Reject");
  reject.setAttribute("type", "button");
  reject.setAttribute("data-memory-decision", "reject");
  reject.addEventListener("click", () => {
    handlers.onSubmitDecision({
      proposal_id: proposal.proposal_id,
      decision: "reject",
    });
  });
  actions.append(approve, reject);
  card.append(actions);
  container.append(card);
}

function renderProposals(container, proposals, handlers) {
  appendTextElement(container, "h3", "work-heading contain-text", "Pending proposals");
  if (proposals.length === 0) {
    appendTextElement(container, "p", "muted contain-text", "No pending memory proposals.");
    return;
  }
  for (const proposal of proposals) {
    renderProposal(container, proposal, handlers);
  }
}

function renderEvents(container, events) {
  appendTextElement(container, "h3", "work-heading contain-text", "Recent memory events");
  if (events.length === 0) {
    appendTextElement(container, "p", "muted contain-text", "No memory events loaded.");
    return;
  }
  for (const event of events) {
    appendTextElement(container, "p", "memory-event contain-text", compactText([
      event.event_id,
      event.event_type,
      event.category,
      stringValue(event.value),
    ]));
  }
}

export function renderMemoryPanel(container, memory, handlers) {
  container.replaceChildren();

  if (memory.status === "loading") {
    appendTextElement(container, "p", "muted contain-text", "Loading memory…");
    return;
  }
  if (memory.status === "error") {
    appendTextElement(
      container,
      "p",
      "form-error contain-text",
      memory.error ?? "Memory unavailable.",
    );
    return;
  }
  if (memory.status === "idle") {
    appendTextElement(container, "p", "muted contain-text", "No memory loaded yet.");
    return;
  }

  renderProposals(container, memory.unresolvedProposals ?? [], handlers);
  renderActivePreferences(container, activePreferences(memory.profile));
  renderEvents(container, memory.events ?? []);
}

export function createMemoryView(elements, handlers) {
  return {
    render(state) {
      renderMemoryPanel(elements.panel, state.memory, handlers);
    },
  };
}
