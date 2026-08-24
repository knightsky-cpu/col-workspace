import { element, setText } from "./render.mjs";

function appendReceipt(container, label, value) {
  const item = element("li", "receipt-item contain-text");
  item.textContent = `${label}: ${value}`;
  container.append(item);
}

export function renderReceipts(container, response) {
  container.replaceChildren();
  const list = element("ul", "receipt-list");
  for (const action of response.actions ?? []) {
    appendReceipt(list, "Action", `${action.action_name} ${action.status}`);
  }
  for (const citation of response.citations ?? []) {
    appendReceipt(list, "Citation", citation.label);
  }
  for (const artifact of response.artifacts ?? []) {
    appendReceipt(list, "Work", artifact.display_label);
  }
  for (const feedback of response.artifact_feedback ?? []) {
    appendReceipt(
      list,
      "Feedback",
      `${feedback.decision} ${feedback.feedback_id}`,
    );
  }
  for (const proposal of response.memory_proposals ?? []) {
    appendReceipt(list, "Memory proposal", proposal.proposal_id);
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
      updateCharacterCount();
    },
  };
}
