import {
  apiFetchJson,
  getBlueprint,
  listBlueprintFeedback,
  listBlueprints,
} from "./api.mjs";
import { createChatView } from "./chat-view.mjs";
import { createWorkView } from "./work-view.mjs";
import {
  buildArtifactFeedbackChatRequest,
  buildExactRetryRequest,
  buildOrdinaryChatRequest,
  readContextForm,
} from "./requests.mjs";
import {
  acceptContext,
  beginPendingTurn,
  beginWorkDetailLoad,
  beginWorkListLoad,
  completeWorkDetailLoad,
  completeWorkListLoad,
  completePendingTurn,
  createInitialState,
  failPendingTurn,
  failWorkDetailLoad,
  failWorkListLoad,
  selectCanSubmit,
  selectWorkRefreshPlan,
  startNewConversation,
} from "./state.mjs";
import { setText } from "./render.mjs";

let state = createInitialState();
let chatView = null;
let workView = null;

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

function showWorkError(message) {
  const error = document.querySelector("[data-work-error]");
  setText(error, message);
  error.hidden = false;
}

function clearWorkError() {
  const error = document.querySelector("[data-work-error]");
  setText(error, "");
  error.hidden = true;
}

function renderWorkspace() {
  ensureChatView().render(state);
  ensureWorkView().render(state);
}

async function loadWorkList() {
  if (!state.context) {
    return;
  }
  clearWorkError();
  state = beginWorkListLoad(state);
  ensureWorkView().render(state);
  try {
    const response = await listBlueprints(state.context.project_id, { limit: 20 });
    state = completeWorkListLoad(state, response);
  } catch (error) {
    state = failWorkListLoad(state, error);
    showWorkError(error.message);
  }
  ensureWorkView().render(state);
}

async function loadWorkDetail(artifactId) {
  if (!state.context) {
    return;
  }
  clearWorkError();
  state = beginWorkDetailLoad(state, artifactId);
  ensureWorkView().render(state);
  try {
    const [detail, feedback] = await Promise.all([
      getBlueprint(state.context.project_id, artifactId),
      listBlueprintFeedback(state.context.project_id, artifactId, { limit: 20 }),
    ]);
    state = completeWorkDetailLoad(state, detail, feedback);
  } catch (error) {
    state = failWorkDetailLoad(state, error);
    showWorkError(error.message);
  }
  ensureWorkView().render(state);
}

async function submitRequest(request) {
  state = beginPendingTurn(state, request);
  renderWorkspace();
  document.querySelector("[data-chat-error]").hidden = true;
  setText(document.querySelector("[data-chat-status]"), "Waiting for Agent Col");
  try {
    const response = await apiFetchJson("/api/chat", {
      method: "POST",
      idempotencyKey: request.key,
      body: request.body,
    });
    state = completePendingTurn(state, response);
    setText(document.querySelector("[data-chat-status]"), "");
    document.querySelector("[data-chat-input]").value = "";
    const refreshPlan = selectWorkRefreshPlan(response);
    if (refreshPlan.reloadList) {
      await loadWorkList();
    }
    if (refreshPlan.selectArtifactId !== null) {
      await loadWorkDetail(refreshPlan.selectArtifactId);
    }
  } catch (error) {
    state = failPendingTurn(state, error);
    setText(document.querySelector("[data-chat-error]"), error.message);
    document.querySelector("[data-chat-error]").hidden = false;
  }
  renderWorkspace();
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

function ensureWorkView() {
  if (workView !== null) {
    return workView;
  }
  workView = createWorkView(
    {
      list: document.querySelector("[data-work-list]"),
      detail: document.querySelector("[data-work-detail]"),
    },
    {
      onSelectArtifact(artifactId) {
        loadWorkDetail(artifactId);
      },
      onSubmitFeedback(decision) {
        submitArtifactFeedback(decision);
      },
    },
  );
  return workView;
}

async function submitArtifactFeedback(decision) {
  if (!selectCanSubmit(state)) {
    return;
  }
  const request = buildArtifactFeedbackChatRequest(
    state.context,
    `Record ${decision.decision} feedback for Work artifact ${decision.artifact_id}.`,
    decision,
  );
  await submitRequest(request);
}

document.querySelector("[data-context-form]").addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    state = acceptContext(
      state,
      readContextForm(new FormData(event.currentTarget)),
    );
    ensureChatView();
    ensureWorkView();
    showWorkspace();
    loadWorkList();
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
  renderWorkspace();
  document.querySelector("#conversation-workspace").focus();
});

document.querySelector("[data-work-refresh]").addEventListener("click", () => {
  loadWorkList();
});
