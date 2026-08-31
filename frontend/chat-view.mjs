import { renderSafeMarkdown } from "./markdown-renderer.mjs";
import { element, humanLabel, humanValue, setText } from "./render.mjs";

function appendReceipt(container, label, value) {
  const item = element("li", "receipt-item contain-text");
  item.textContent = value ? `${label}: ${value}` : label;
  container.append(item);
}

function adaptationReceiptValue(adaptation) {
  if (
    !adaptation
    || typeof adaptation !== "object"
    || typeof adaptation.category !== "string"
  ) {
    return "";
  }
  return [humanLabel(adaptation.category), humanValue(adaptation.value)]
    .filter(Boolean)
    .join(" · ");
}

function appendAdaptationReceipts(container, adaptations) {
  const values = (adaptations ?? [])
    .map(adaptationReceiptValue)
    .filter(Boolean);
  if (values.length === 0) {
    return;
  }

  const disclosure = element("details", "receipt-disclosure");
  const summary = element("summary", "receipt-disclosure__summary contain-text");
  summary.textContent = `Verified adaptations (${values.length})`;
  const list = element("ul", "receipt-list receipt-list--disclosure");
  for (const value of values) {
    appendReceipt(list, "Adaptation", value);
  }
  disclosure.append(summary, list);
  container.append(disclosure);
}

function turnAuthorIcon(kind) {
  const iconClass = kind === "model" ? "turn-author-icon--model" : "turn-author-icon--user";
  const icon = element("span", `turn-author-icon ${iconClass}`);
  icon.setAttribute("aria-hidden", "true");
  return icon;
}

function appendTurnMessage(container, kind, message) {
  const messageText = element("span", "turn-message-text");
  if (kind === "model") {
    renderSafeMarkdown(messageText, message);
  } else {
    setText(messageText, message);
  }
  container.append(turnAuthorIcon(kind), messageText);
}

function appendEmptyConversationIntro(container) {
  const section = element("section", "conversation-intro");
  section.setAttribute("aria-labelledby", "empty-conversation-title");
  const title = element("h2", "", "Start a conversation");
  title.setAttribute("id", "empty-conversation-title");
  section.append(title);
  container.append(section);
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
  if (list.children.length > 0) {
    container.append(list);
  }
  appendAdaptationReceipts(container, response.adaptations);
}

function appendTranscriptTurn(
  container,
  turn,
  { className = "", includeReceipts = true } = {},
) {
  const article = element("article", `turn ${className}`.trim());
  if (className === "chat-turn--incomplete") {
    article.setAttribute("aria-label", "Incomplete assistant response");
  }
  const user = element("div", "turn-user");
  const model = element("div", "turn-model");
  appendTurnMessage(user, "user", turn.request?.body?.message ?? "");
  appendTurnMessage(model, "model", turn.response?.response ?? "");
  article.append(user, model);
  if (includeReceipts) {
    const receipts = element("div", "turn-receipts");
    renderReceipts(receipts, turn.response ?? {});
    article.append(receipts);
  }
  container.append(article);
}

export function renderTranscript(
  container,
  transcript,
  pendingTurn = null,
  pendingResponseText = "",
  lastFailure = null,
) {
  container.replaceChildren();
  if (transcript.length === 0 && pendingTurn === null && lastFailure === null) {
    appendEmptyConversationIntro(container);
    return;
  }
  for (const turn of transcript) {
    appendTranscriptTurn(container, turn);
  }
  if (pendingTurn !== null) {
    appendTranscriptTurn(
      container,
      {
        request: pendingTurn,
        response: { response: pendingResponseText },
      },
      { className: "chat-turn--pending", includeReceipts: false },
    );
  } else if (lastFailure !== null) {
    appendTranscriptTurn(
      container,
      {
        request: lastFailure.request,
        response: { response: lastFailure.provisionalResponseText },
      },
      { className: "chat-turn--incomplete", includeReceipts: false },
    );
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
    const level = count >= 9000 ? "danger" : count >= 5000 ? "warn" : "safe";
    elements.characterCount.textContent = `${count} / 10000`;
    elements.characterCount.setAttribute("data-character-count-level", level);
  }

  function insertComposerText(text) {
    const transcript = String(text ?? "").trim();
    if (!transcript) {
      return;
    }
    const current = String(elements.input.value ?? "");
    elements.input.value = current.trim()
      ? `${current}\n${transcript}`
      : transcript;
    updateCharacterCount();
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
    clearComposer() {
      elements.input.value = "";
      updateCharacterCount();
    },
    insertComposerText,
    render(state) {
      renderTranscript(
        elements.transcript,
        state.transcript,
        state.pendingTurn,
        state.pendingResponseText,
        state.lastFailure,
      );
      elements.transcript.scrollTop = elements.transcript.scrollHeight;
      elements.retryButton.hidden = state.lastFailure === null;
      elements.submitButton.disabled = (
        state.pendingTurn !== null
        || state.lastFailure?.recovered === true
      );
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
