import { element, humanLabel, humanValue, setText } from "./render.mjs";

function appendReceipt(container, label, value) {
  const item = element("li", "receipt-item contain-text");
  item.textContent = value ? `${label}: ${value}` : label;
  container.append(item);
}

export function renderReceipts(container, response) {
  container.replaceChildren();
  const list = element("ul", "receipt-list");
  for (const action of response.actions ?? []) {
    appendReceipt(list, "Action", `${humanLabel(action.action_name)} ${humanLabel(action.status)}`);
  }
  for (const citation of response.citations ?? []) {
    appendReceipt(list, "Citation", citation.label);
  }
  for (const artifact of response.artifacts ?? []) {
    appendReceipt(list, "Artifact", artifact.display_label);
  }
  for (const feedback of response.artifact_feedback ?? []) {
    appendReceipt(
      list,
      "Feedback",
      humanLabel(feedback.decision),
    );
  }
  for (const proposal of response.memory_proposals ?? []) {
    appendReceipt(list, "Memory proposal", humanLabel(proposal.category));
  }
  for (const proposal of response.collaborative_note_proposals ?? []) {
    appendReceipt(list, "Note proposal", proposal.title);
  }
  for (const event of response.collaborative_note_events ?? []) {
    appendReceipt(
      list,
      "Note updated",
      event.title ?? humanLabel(event.event_type),
    );
  }
  for (const receipt of response.continuity_receipts ?? []) {
    appendReceipt(
      list,
      receipt.source_kind === "chat_session" ? "Used prior chat" : "Used note",
      String(receipt.display_label ?? "").replace(/^Used note:\s*/i, ""),
    );
  }
  for (const adaptation of response.adaptations ?? []) {
    if (
      !adaptation
      || typeof adaptation !== "object"
      || typeof adaptation.category !== "string"
    ) {
      continue;
    }
    appendReceipt(
      list,
      "Adaptation",
      [humanLabel(adaptation.category), humanValue(adaptation.value)]
        .filter(Boolean)
        .join(" · "),
    );
  }
  if (list.children.length > 0) {
    container.append(list);
  }
}

export function renderTranscript(container, transcript) {
  container.replaceChildren();
  for (const turn of transcript) {
    const article = element("article", "turn");
    const user = element("p", "turn-user");
    const model = element("p", "turn-model");
    setText(user, turn.request?.body?.message ?? "");
    setText(model, turn.response?.response ?? "");
    article.append(user, model);
    const receipts = element("div", "turn-receipts");
    renderReceipts(receipts, turn.response ?? {});
    article.append(receipts);
    container.append(article);
  }
}

function isClarificationExpired(clarification) {
  const expiresAt = Date.parse(clarification?.expires_at ?? "");
  return Number.isNaN(expiresAt) || expiresAt <= Date.now();
}

function renderMemoryClarificationChoices(container, clarification, disabled, onSelect) {
  if (!container) {
    return;
  }
  container.replaceChildren();
  if (!clarification) {
    container.hidden = true;
    return;
  }

  const buttonsDisabled = disabled || isClarificationExpired(clarification);
  for (const choice of clarification.choices ?? []) {
    const label = `${choice.category_label}: ${choice.value_label}`;
    const button = element("button", "memory-clarification-choice contain-text", label);
    button.setAttribute("type", "button");
    button.disabled = buttonsDisabled;
    button.addEventListener("click", () => {
      if (button.disabled) {
        return;
      }
      onSelect({
        ...choice,
        clarification_id: clarification.clarification_id,
      });
    });
    container.append(button);
  }
  container.hidden = container.children.length === 0;
}

function renderContinuityChoices(container, choices, disabled, onSelect) {
  if (!container) {
    return;
  }
  container.replaceChildren();
  for (const choice of Array.isArray(choices) ? choices : []) {
    const label = String(choice.display_label ?? "").trim();
    if (!label) {
      continue;
    }
    const button = element("button", "continuity-choice contain-text", label);
    button.setAttribute("type", "button");
    button.disabled = disabled;
    button.addEventListener("click", () => {
      if (button.disabled) {
        return;
      }
      onSelect(choice);
    });
    container.append(button);
  }
  container.hidden = container.children.length === 0;
}

export function createChatView(elements, handlers) {
  function updateCharacterCount() {
    if (!elements.characterCount) {
      return;
    }
    const count = String(elements.input.value ?? "").length;
    elements.characterCount.textContent = `${count} / 10000`;
  }

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    handlers.onSubmit(elements.input.value);
  });
  elements.input.addEventListener("keydown", (event) => {
    if ((event.key !== "Enter" && event.key !== "Return") || event.shiftKey) {
      return;
    }
    event.preventDefault();
    elements.form.requestSubmit();
  });
  elements.input.addEventListener("input", updateCharacterCount);
  elements.retryButton.addEventListener("click", () => {
    handlers.onRetry();
  });
  updateCharacterCount();
  return {
    render(state) {
      renderTranscript(elements.transcript, state.transcript);
      elements.transcript.scrollTop = elements.transcript.scrollHeight;
      elements.retryButton.hidden = state.lastFailure === null;
      elements.submitButton.disabled = state.pendingTurn !== null;
      renderMemoryClarificationChoices(
        elements.clarificationChoices,
        state.activeMemoryClarification ?? null,
        state.pendingTurn !== null,
        handlers.onSelectMemoryClarification ?? (() => {}),
      );
      renderContinuityChoices(
        elements.continuityChoices,
        state.activeContinuityChoices ?? [],
        state.pendingTurn !== null,
        handlers.onSelectContinuityChoice ?? (() => {}),
      );
      updateCharacterCount();
    },
  };
}
