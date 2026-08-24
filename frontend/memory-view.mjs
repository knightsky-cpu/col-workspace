import { appendTextElement, element, humanLabel } from "./render.mjs";

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
  const text = String(value);
  return /[_-]/.test(text) ? humanLabel(text) : text;
}

function memorySignals(profile, key) {
  if (!profile || typeof profile[key] !== "object") {
    return [];
  }
  return Object.entries(profile[key] ?? {})
    .filter(([, signal]) => signal && typeof signal === "object")
    .map(([category, signal]) => ({
      category,
      signal_id: signal.signal_id,
      value: signal.value,
      source_event_id: signal.source_event_id,
    }));
}

function renderMemorySignals(container, title, emptyText, signals, handlers) {
  appendTextElement(container, "h3", "work-heading contain-text", title);
  if (signals.length === 0) {
    appendTextElement(container, "p", "muted contain-text", emptyText);
    return;
  }
  for (const signal of signals) {
    const card = element("div", "memory-card contain-text");
    card.setAttribute("data-memory-signal", signal.signal_id);
    appendTextElement(card, "p", "work-heading contain-text", compactText([
      humanLabel(signal.category),
      stringValue(signal.value),
    ]));
    appendTextElement(card, "p", "muted contain-text", compactText([
      "Saved memory",
    ]));
    const actions = element("div", "memory-actions contain-text");
    const revoke = element("button", "", "Revoke");
    revoke.setAttribute("type", "button");
    revoke.setAttribute("data-memory-signal-action", "revoke");
    revoke.addEventListener("click", () => {
      handlers.onRevokeSignal(signal);
    });
    const deleteButton = element("button", "", "Delete");
    deleteButton.setAttribute("type", "button");
    deleteButton.setAttribute("data-memory-signal-action", "delete");
    deleteButton.addEventListener("click", () => {
      handlers.onDeleteSignal(signal);
    });
    actions.append(revoke, deleteButton);
    card.append(actions);
    container.append(card);
  }
}

function renderProposal(container, proposal, handlers) {
  const card = element("div", "memory-card contain-text");
  card.setAttribute("data-memory-proposal", proposal.proposal_id);
  appendTextElement(card, "p", "work-heading contain-text", compactText([
    humanLabel(proposal.category),
    stringValue(proposal.proposed_value),
  ]));
  appendTextElement(card, "p", "muted contain-text", compactText([
    humanLabel(proposal.status),
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
      humanLabel(event.category),
      humanLabel(event.event_type),
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
  renderMemorySignals(
    container,
    "Identity context",
    "No identity context saved.",
    memorySignals(memory.profile, "identity_context"),
    handlers,
  );
  renderMemorySignals(
    container,
    "Active preferences",
    "No active preferences.",
    memorySignals(memory.profile, "active_preferences"),
    handlers,
  );
  renderEvents(container, memory.events ?? []);
}

export function createMemoryView(elements, handlers) {
  return {
    render(state) {
      renderMemoryPanel(elements.panel, state.memory, handlers);
    },
  };
}
