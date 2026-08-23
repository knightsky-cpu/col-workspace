import {
  createInitialState,
  acceptContext,
  startNewConversation,
} from "./state.mjs";
import { readContextForm } from "./requests.mjs";
import { setText } from "./render.mjs";

let state = createInitialState();

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

document.querySelector("[data-context-form]").addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    state = acceptContext(
      state,
      readContextForm(new FormData(event.currentTarget)),
    );
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
  document.querySelector("#conversation-workspace").focus();
});
