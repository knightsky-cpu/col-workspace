import {
  apiFetchJson,
  createWorkspace,
  deleteMemorySignal,
  getAuthConfig,
  getAuthSession,
  getChatSession,
  getBlueprint,
  inspectMemory,
  listChatSessions,
  listWorkspaces,
  listBlueprintFeedback,
  listBlueprints,
  revokeMemorySignal,
} from "./api.mjs";
import {
  authRequiresGoogleSignIn,
  googleSessionDisplayLabel,
  googleSessionToContext,
  googleWorkspaceDisplayLabel,
  initializeGoogleSignIn,
  loadGoogleIdentityScript,
} from "./auth-view.mjs";
import { createChatsView } from "./chats-view.mjs";
import { createChatView } from "./chat-view.mjs";
import { createMemoryView } from "./memory-view.mjs";
import { createWorkView } from "./work-view.mjs";
import { createWorkspaceView } from "./workspace-view.mjs";
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
  beginWorkspaceListLoad,
  beginChatSessionDetailLoad,
  beginChatSessionListLoad,
  beginMemoryLoad,
  beginPendingTurn,
  beginWorkDetailLoad,
  beginWorkListLoad,
  completeMemoryLoad,
  completeChatSessionDetailLoad,
  completeChatSessionListLoad,
  completeWorkspaceCreate,
  completeWorkspaceListLoad,
  completeWorkDetailLoad,
  completeWorkListLoad,
  completePendingTurn,
  createInitialState,
  failMemoryLoad,
  failChatSessionDetailLoad,
  failChatSessionListLoad,
  failWorkspaceListLoad,
  failPendingTurn,
  failWorkDetailLoad,
  failWorkListLoad,
  selectCanSubmit,
  selectNeedsReceiptRefresh,
  selectWorkspace,
  selectWorkRefreshPlan,
  startNewConversation,
} from "./state.mjs";
import { setText } from "./render.mjs";

let state = createInitialState();
let chatView = null;
let workView = null;
let memoryView = null;
let chatsView = null;
let workspaceView = null;
let layoutState = createInitialLayoutState();
let authConfig = null;
let verifiedGoogleContext = null;

function showAuthError(message) {
  const error = document.querySelector("[data-auth-error]");
  setText(error, message);
  error.hidden = false;
}

function clearAuthError() {
  const error = document.querySelector("[data-auth-error]");
  setText(error, "");
  error.hidden = true;
}

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

function showWorkspaceError(message) {
  const error = document.querySelector("[data-workspace-error]");
  setText(error, message);
  error.hidden = false;
}

function clearWorkspaceError() {
  const error = document.querySelector("[data-workspace-error]");
  setText(error, "");
  error.hidden = true;
}

function clearMemoryError() {
  const error = document.querySelector("[data-memory-error]");
  setText(error, "");
  error.hidden = true;
}

function authOptions(options = {}) {
  return {
    ...options,
    authToken: state.context?.auth_token ?? null,
  };
}

function setAuthModeLabel(text) {
  setText(document.querySelector("[data-auth-mode-label]"), text);
}

function setContextFormEnabled(enabled) {
  for (const input of document.querySelectorAll("[data-context-form] input")) {
    input.disabled = !enabled;
  }
  document.querySelector('[data-context-form] button[type="submit"]').disabled = !enabled;
}

function populateGoogleContext(session, authToken) {
  const projectInput = document.querySelector('[name="project_id"]');
  verifiedGoogleContext = googleSessionToContext(
    session,
    projectInput.value.trim() || "agent-col",
    authToken,
  );
  projectInput.value = googleWorkspaceDisplayLabel();
  projectInput.readOnly = true;
  const userInput = document.querySelector('[name="user_id"]');
  userInput.value = googleSessionDisplayLabel(session);
  userInput.readOnly = true;
  const accountStatus = document.querySelector("[data-google-account-status]");
  setText(accountStatus, googleSessionDisplayLabel(session));
  accountStatus.hidden = false;
  setContextFormEnabled(true);
  setAuthModeLabel(googleSessionDisplayLabel(session));
}

function contextForSubmit(form) {
  if (!authRequiresGoogleSignIn(authConfig)) {
    return readContextForm(new FormData(form));
  }
  if (verifiedGoogleContext === null) {
    throw new Error("Sign in with Google before entering the workspace.");
  }
  const formData = new FormData(form);
  return googleSessionToContext(
    {
      authenticated: true,
      user_id: verifiedGoogleContext.user_id,
      workspace_project_id: verifiedGoogleContext.project_id,
    },
    formData.get("project_id"),
    verifiedGoogleContext.auth_token,
  );
}

async function bootstrapAuth() {
  const form = document.querySelector("[data-context-form]");
  const googleSignIn = document.querySelector("[data-google-signin]");
  try {
    authConfig = await getAuthConfig();
  } catch (error) {
    showContextError(error.message);
    setAuthModeLabel("Authentication unavailable");
    setContextFormEnabled(false);
    return;
  }

  if (!authRequiresGoogleSignIn(authConfig)) {
    setAuthModeLabel("Local development mode");
    googleSignIn.hidden = true;
    form.hidden = false;
    setContextFormEnabled(true);
    return;
  }

  setAuthModeLabel("Google authentication required");
  googleSignIn.hidden = false;
  form.hidden = false;
  setContextFormEnabled(false);
  try {
    await loadGoogleIdentityScript();
    initializeGoogleSignIn({
      clientId: authConfig.google_client_id,
      buttonContainer: document.querySelector("[data-google-button]"),
      async onCredential(authToken) {
        clearAuthError();
        try {
          const session = await getAuthSession(authToken);
          populateGoogleContext(session, authToken);
        } catch (error) {
          showAuthError(error.message);
        }
      },
    });
  } catch (error) {
    showAuthError(error.message);
  }
}

function renderWorkspace() {
  ensureWorkspaceView().render(state);
  ensureChatView().render(state);
  ensureWorkView().render(state);
  ensureMemoryView().render(state);
  ensureChatsView().render(state);
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
    setText(button, expanded ? "Hide" : "Show Artifacts Viewer");
    button.setAttribute("aria-expanded", String(expanded));
  }

  const artifactExpandButton = document.querySelector("[data-artifacts-expand]");
  const artifactsExpanded = layoutState.artifactDrawerMode === "expanded";
  setText(
    artifactExpandButton,
    artifactsExpanded ? "Normal Viewer" : "Expand Artifacts Viewer",
  );
  artifactExpandButton.setAttribute("aria-expanded", String(artifactsExpanded));

  for (const section of ["workspace", "work", "memory", "chats"]) {
    const expanded = isSectionExpanded(layoutState, section);
    const content = document.querySelector(`[data-section-content="${section}"]`);
    const toggle = document.querySelector(`[data-section-toggle="${section}"]`);
    content.hidden = !expanded;
    toggle.setAttribute("aria-expanded", String(expanded));
    setText(toggle, expanded ? "Collapse" : "Expand");
  }
}

async function loadWorkspaces() {
  if (!state.context) {
    return;
  }
  clearWorkspaceError();
  state = beginWorkspaceListLoad(state);
  ensureWorkspaceView().render(state);
  try {
    const response = await listWorkspaces(
      state.context.user_id,
      authOptions({ limit: 20 }),
    );
    state = completeWorkspaceListLoad(state, response);
  } catch (error) {
    state = failWorkspaceListLoad(state, error);
    showWorkspaceError(error.message);
  }
  ensureWorkspaceView().render(state);
}

async function loadWorkList() {
  if (!state.context) {
    return;
  }
  clearWorkError();
  state = beginWorkListLoad(state);
  ensureWorkView().render(state);
  try {
    const response = await listBlueprints(
      state.context.project_id,
      authOptions({ limit: 20 }),
    );
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
      getBlueprint(state.context.project_id, artifactId, authOptions()),
      listBlueprintFeedback(
        state.context.project_id,
        artifactId,
        authOptions({ limit: 20 }),
      ),
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
    const response = await inspectMemory(
      state.context.user_id,
      authOptions(),
    );
    state = completeMemoryLoad(state, response);
  } catch (error) {
    state = failMemoryLoad(state, error);
    showMemoryError(error.message);
  }
  ensureMemoryView().render(state);
}

async function loadChatSessions() {
  if (!state.context) {
    return;
  }
  state = beginChatSessionListLoad(state);
  ensureChatsView().render(state);
  try {
    const response = await listChatSessions(
      state.context.user_id,
      state.context.project_id,
      authOptions({ limit: 20 }),
    );
    state = completeChatSessionListLoad(state, response);
  } catch (error) {
    state = failChatSessionListLoad(state, error);
  }
  ensureChatsView().render(state);
}

async function loadChatSession(sessionId) {
  if (!state.context || !selectCanSubmit(state)) {
    return;
  }
  state = beginChatSessionDetailLoad(state, sessionId);
  renderWorkspace();
  try {
    const response = await getChatSession(
      state.context.user_id,
      state.context.project_id,
      sessionId,
      authOptions({ limit: 100 }),
    );
    state = completeChatSessionDetailLoad(state, response);
    document.querySelector("[data-chat-error]").hidden = true;
    setText(document.querySelector("[data-chat-status]"), "");
  } catch (error) {
    state = failChatSessionDetailLoad(state, error);
  }
  renderWorkspace();
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
      authToken: state.context?.auth_token ?? null,
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
    await loadChatSessions();
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

function ensureWorkspaceView() {
  if (workspaceView !== null) {
    return workspaceView;
  }
  workspaceView = createWorkspaceView(
    {
      panel: document.querySelector("[data-workspace-list]"),
    },
    {
      async onSelectWorkspace(workspace) {
        if (!state.context || state.pendingTurn !== null) {
          return;
        }
        state = selectWorkspace(state, workspace);
        renderWorkspace();
        await loadWorkList();
        await loadMemory();
        await loadChatSessions();
      },
      async onCreateWorkspace(displayName) {
        if (!state.context || state.pendingTurn !== null) {
          return;
        }
        clearWorkspaceError();
        try {
          const response = await createWorkspace(
            state.context.user_id,
            { display_name: displayName },
            authOptions(),
          );
          state = completeWorkspaceCreate(state, response);
          renderWorkspace();
          await loadWorkspaces();
          await loadWorkList();
          await loadMemory();
          await loadChatSessions();
        } catch (error) {
          showWorkspaceError(error.message);
        }
      },
    },
  );
  return workspaceView;
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
      onRevokeSignal(signal) {
        revokeActiveMemorySignal(signal);
      },
      onDeleteSignal(signal) {
        deleteActiveMemorySignal(signal);
      },
    },
  );
  return memoryView;
}

function ensureChatsView() {
  if (chatsView !== null) {
    return chatsView;
  }
  chatsView = createChatsView(
    {
      list: document.querySelector("[data-chats-list]"),
    },
    {
      onSelectSession(sessionId) {
        loadChatSession(sessionId);
      },
    },
  );
  return chatsView;
}

async function submitArtifactFeedback(decision) {
  if (!selectCanSubmit(state)) {
    return;
  }
  const request = buildArtifactFeedbackChatRequest(
    state.context,
    `Record ${decision.decision} feedback for Artifact ${decision.artifact_id}.`,
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

async function revokeActiveMemorySignal(signal) {
  if (!state.context || !selectCanSubmit(state)) {
    return;
  }
  clearMemoryError();
  try {
    await revokeMemorySignal(
      state.context.user_id,
      signal.signal_id,
      authOptions(),
    );
    await loadMemory();
  } catch (error) {
    showMemoryError(error.message);
  }
  renderWorkspace();
}

async function deleteActiveMemorySignal(signal) {
  if (!state.context || !selectCanSubmit(state)) {
    return;
  }
  clearMemoryError();
  try {
    await deleteMemorySignal(
      state.context.user_id,
      signal.signal_id,
      authOptions(),
    );
    await loadMemory();
  } catch (error) {
    showMemoryError(error.message);
  }
  renderWorkspace();
}

document.querySelector("[data-context-form]").addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    state = acceptContext(
      state,
      contextForSubmit(event.currentTarget),
    );
    ensureChatView();
    ensureWorkView();
    ensureMemoryView();
    ensureChatsView();
    ensureWorkspaceView();
    showWorkspace();
    loadWorkspaces();
    loadWorkList();
    loadMemory();
    loadChatSessions();
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
  loadChatSessions();
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
  loadWorkspaces();
  loadWorkList();
  loadMemory();
  loadChatSessions();
});

bootstrapAuth();
