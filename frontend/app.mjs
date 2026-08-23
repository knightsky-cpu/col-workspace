import { apiFetchJson } from "./api.mjs";
import { createChatView } from "./chat-view.mjs";
import {
  buildExactRetryRequest,
  buildOrdinaryChatRequest,
  readContextForm,
} from "./requests.mjs";
import {
  acceptContext,
  beginPendingTurn,
  completePendingTurn,
  createInitialState,
  failPendingTurn,
  selectCanSubmit,
  startNewConversation,
} from "./state.mjs";
import { setText } from "./render.mjs";

let state = createInitialState();
let chatView = null;

function showWorkspace() {
  document.querySelector("[data-context-error]").hidden = true;
  document.querySelector("[data-workspace]").hidden = false;
  document.querySelector(".context-gate").hidden = true;
  document.querySelector("[data-new-conversation]").disabled = false;
  document.querySelector("#conversation-workspace").focus();
}

function showContextError(message) {
  const error = document.querySelector("[data-context-error]");
  setText(error, message);
  error.hidden = false;
}

async function submitRequest(request) {
  state = beginPendingTurn(state, request);
  chatView.render(state);
  document.querySelector("[data-chat-error]").hidden = true;
  setText(document.querySelector("[data-chat-status]"), "Waiting for Agent_Col");
  try {
    const response = await apiFetchJson("/api/chat", {
      method: "POST",
      idempotencyKey: request.key,
      body: request.body,
    });
    state = completePendingTurn(state, response);
    setText(document.querySelector("[data-chat-status]"), "");
    document.querySelector("[data-chat-input]").value = "";
  } catch (error) {
    state = failPendingTurn(state, error);
    setText(document.querySelector("[data-chat-error]"), error.message);
    document.querySelector("[data-chat-error]").hidden = false;
  }
  chatView.render(state);
}

function ensureChatView() {
  if (chatView !== null) {
    return chatView;
  }
  chatView = createChatView(
    {
      form: document.querySelector("[data-chat-form]"),
      input: document.querySelector("[data-chat-input]"),
      submitButton: document.querySelector("[data-chat-submit]"),
      retryButton: document.querySelector("[data-retry-turn]"),
      transcript: document.querySelector("[data-chat-transcript]"),
    },
    {
      onSubmit(message) {
        if (!selectCanSubmit(state)) {
          return;
        }
        const request = buildOrdinaryChatRequest(state.context, message);
        submitRequest(request);
      },
      onRetry() {
        if (state.lastFailure === null) {
          return;
        }
        submitRequest(buildExactRetryRequest(state.lastFailure.request));
      },
    },
  );
  return chatView;
}

document.querySelector("[data-context-form]").addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    state = acceptContext(
      state,
      readContextForm(new FormData(event.currentTarget)),
    );
    ensureChatView();
    showWorkspace();
  } catch (error) {
    showContextError(error.message);
  }
});

document.querySelector("[data-new-conversation]").addEventListener("click", () => {
  if (state.pendingTurn !== null) {
    return;
  }
  state = startNewConversation(state);
  document.querySelector("[data-chat-error]").hidden = true;
  setText(document.querySelector("[data-chat-status]"), "");
  ensureChatView().render(state);
  document.querySelector("#conversation-workspace").focus();
});
