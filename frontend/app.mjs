import {
  apiFetchJson,
  getBlueprint,
  inspectMemory,
  listBlueprintFeedback,
  listBlueprints,
} from "./api.mjs";
import { createActivityView } from "./activity-view.mjs";
import { createChatView } from "./chat-view.mjs";
import { createMemoryView } from "./memory-view.mjs";
import { createWorkView } from "./work-view.mjs";
import {
  buildArtifactFeedbackChatRequest,
  buildExactRetryRequest,
  buildMemoryDecisionChatRequest,
  buildOrdinaryChatRequest,
  readContextForm,
} from "./requests.mjs";
import {
  createInitialLayoutState,
  isDrawerExpanded,
  isSectionExpanded,
  setArtifactDrawerMode,
  setDrawerCollapsed,
  setSectionExpanded,
} from "./workspace-layout.mjs";
import {
  acceptContext,
  beginMemoryLoad,
  beginPendingTurn,
  beginWorkDetailLoad,
  beginWorkListLoad,
  completeMemoryLoad,
  completeWorkDetailLoad,
  completeWorkListLoad,
  completePendingTurn,
  createInitialState,
  failMemoryLoad,
  failPendingTurn,
  failWorkDetailLoad,
  failWorkListLoad,
  selectCanSubmit,
  selectNeedsReceiptRefresh,
  selectWorkRefreshPlan,
  startNewConversation,
} from "./state.mjs";
import { setText } from "./render.mjs";

let state = createInitialState();
let chatView = null;
let workView = null;
let memoryView = null;
let activityView = null;
let layoutState = createInitialLayoutState();

function showWorkspace() {
  document.querySelector("[data-context-error]").hidden = true;
  document.querySelector("[data-workspace]").hidden = false;
  document.querySelector(".context-gate").hidden = true;
  document.querySelector("[data-new-conversation]").disabled = false;
  for (const button of document.querySelectorAll("[data-drawer-toggle]")) {
    button.disabled = false;
  }
  const artifactExpandButton = document.querySelector("[data-artifacts-expand]");
  artifactExpandButton.disabled = false;
  const leftRefreshButton = document.querySelector("[data-left-refresh]");
  leftRefreshButton.disabled = false;
  renderLayout();
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

function showMemoryError(message) {
  const error = document.querySelector("[data-memory-error]");
  setText(error, message);
  error.hidden = false;
}

function clearMemoryError() {
  const error = document.querySelector("[data-memory-error]");
  setText(error, "");
  error.hidden = true;
}

function renderWorkspace() {
  ensureChatView().render(state);
  ensureWorkView().render(state);
  ensureMemoryView().render(state);
  ensureActivityView().render(state);
  renderLayout();
}

function renderLayout() {
  const workspace = document.querySelector("[data-workspace]");
  workspace.classList.toggle(
    "workspace-grid--left-collapsed",
    !isDrawerExpanded(layoutState, "left"),
  );
  workspace.classList.toggle(
    "workspace-grid--right-collapsed",
    !isDrawerExpanded(layoutState, "right"),
  );
  workspace.classList.toggle(
    "workspace-grid--artifacts-expanded",
    layoutState.artifactDrawerMode === "expanded",
  );

  for (const button of document.querySelectorAll('[data-drawer-toggle="left"]')) {
    const expanded = isDrawerExpanded(layoutState, "left");
    setText(button, expanded ? "Hide" : "Show side panel");
    button.setAttribute("aria-expanded", String(expanded));
  }
  for (const button of document.querySelectorAll('[data-drawer-toggle="right"]')) {
    const expanded = isDrawerExpanded(layoutState, "right");
    setText(button, expanded ? "Hide" : "Show Artifacts");
    button.setAttribute("aria-expanded", String(expanded));
  }

  const artifactExpandButton = document.querySelector("[data-artifacts-expand]");
  const artifactsExpanded = layoutState.artifactDrawerMode === "expanded";
  setText(
    artifactExpandButton,
    artifactsExpanded ? "Normal Artifacts" : "Expand Artifacts",
  );
  artifactExpandButton.setAttribute("aria-expanded", String(artifactsExpanded));

  for (const section of ["work", "memory", "chats"]) {
    const expanded = isSectionExpanded(layoutState, section);
    const content = document.querySelector(`[data-section-content="${section}"]`);
    const toggle = document.querySelector(`[data-section-toggle="${section}"]`);
    content.hidden = !expanded;
    toggle.setAttribute("aria-expanded", String(expanded));
    setText(toggle, expanded ? "Collapse" : "Expand");
  }
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

async function loadMemory() {
  if (!state.context) {
    return;
  }
  clearMemoryError();
  state = beginMemoryLoad(state);
  ensureMemoryView().render(state);
  try {
    const response = await inspectMemory(state.context.user_id);
    state = completeMemoryLoad(state, response);
  } catch (error) {
    state = failMemoryLoad(state, error);
    showMemoryError(error.message);
  }
  ensureMemoryView().render(state);
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
    if (selectNeedsReceiptRefresh(response).memory) {
      await loadMemory();
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
      characterCount: document.querySelector("[data-character-count]"),
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
      onPrintWork() {
        window.print();
      },
    },
  );
  return workView;
}

function ensureMemoryView() {
  if (memoryView !== null) {
    return memoryView;
  }
  memoryView = createMemoryView(
    {
      panel: document.querySelector("[data-memory-panel]"),
    },
    {
      onSubmitDecision(decision) {
        submitMemoryDecision(decision);
      },
    },
  );
  return memoryView;
}

function ensureActivityView() {
  if (activityView !== null) {
    return activityView;
  }
  activityView = createActivityView({
    list: document.querySelector("[data-chats-list]"),
  });
  return activityView;
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

async function submitMemoryDecision(decision) {
  if (!selectCanSubmit(state)) {
    return;
  }
  const request = buildMemoryDecisionChatRequest(
    state.context,
    `Record ${decision.decision} decision for memory proposal ${decision.proposal_id}.`,
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
    ensureMemoryView();
    ensureActivityView();
    showWorkspace();
    loadWorkList();
    loadMemory();
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

for (const button of document.querySelectorAll("[data-drawer-toggle]")) {
  button.addEventListener("click", () => {
    const drawer = button.getAttribute("data-drawer-toggle");
    if (drawer === "right") {
      layoutState = setArtifactDrawerMode(
        layoutState,
        isDrawerExpanded(layoutState, "right") ? "hidden" : "normal",
      );
      renderLayout();
      return;
    }
    layoutState = setDrawerCollapsed(
      layoutState,
      drawer,
      isDrawerExpanded(layoutState, drawer),
    );
    renderLayout();
  });
}

for (const button of document.querySelectorAll("[data-section-toggle]")) {
  button.addEventListener("click", () => {
    const section = button.getAttribute("data-section-toggle");
    layoutState = setSectionExpanded(
      layoutState,
      section,
      !isSectionExpanded(layoutState, section),
    );
    renderLayout();
  });
}

document.querySelector("[data-artifacts-expand]").addEventListener("click", () => {
  layoutState = setArtifactDrawerMode(
    layoutState,
    layoutState.artifactDrawerMode === "expanded" ? "normal" : "expanded",
  );
  renderLayout();
});

document.querySelector("[data-left-refresh]").addEventListener("click", () => {
  loadWorkList();
  loadMemory();
});
