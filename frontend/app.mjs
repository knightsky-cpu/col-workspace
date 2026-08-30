import {
  apiFetchJson,
  apiFetchSse,
  archiveNote,
  archiveArtifact,
  createArtifactVersion,
  createNoteCorrection,
  createNoteProposal,
  createWorkspace,
  deleteNote,
  deleteArtifact,
  deleteMemorySignal,
  deleteWorkspace,
  getArtifact,
  getAuthConfig,
  getAuthSession,
  getChatSession,
  getBlueprint,
  getNote,
  inspectMemory,
  listNotes,
  listChatSessions,
  listArtifacts,
  listWorkspaces,
  listBlueprintFeedback,
  listBlueprints,
  restoreNote,
  restoreArtifact,
  revokeMemorySignal,
  updateArtifactMetadata,
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
import {
  clearOrdinaryChatRequest,
  loadOrdinaryChatRequest,
  storeOrdinaryChatRequest,
} from "./chat-request-recovery.mjs";
import { createMemoryView } from "./memory-view.mjs";
import { createNotesView } from "./notes-view.mjs";
import { createWorkView } from "./work-view.mjs";
import { createWorkspaceView } from "./workspace-view.mjs";
import { renderWorkspaceIndicator } from "./workspace-indicator.mjs";
import {
  buildArtifactFeedbackChatRequest,
  buildCollaborativeNoteDecisionChatRequest,
  buildContinuitySelectionChatRequest,
  buildExactRetryRequest,
  buildMemoryDecisionChatRequest,
  buildMemoryClarificationSelectionChatRequest,
  buildOrdinaryChatRequest,
  readContextForm,
  selectChatEndpoint,
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
  appendPendingResponseDelta,
  beginWorkspaceListLoad,
  beginChatSessionDetailLoad,
  beginChatSessionListLoad,
  beginMemoryLoad,
  beginNoteDetailLoad,
  beginNoteRequest,
  beginNotesLoad,
  beginPendingTurn,
  beginWorkDetailLoad,
  beginWorkListLoad,
  completeMemoryLoad,
  completeMemorySignalMutation,
  completeNoteDetailLoad,
  completeNoteRequest,
  completeNotesLoad,
  completeChatSessionDetailLoad,
  completeChatSessionListLoad,
  completeWorkspaceCreate,
  completeWorkspaceDelete,
  completeWorkspaceListLoad,
  completeWorkArchive,
  completeWorkDelete,
  completeWorkDetailLoad,
  completeWorkListLoad,
  completeWorkMetadataUpdate,
  completeWorkVersionCreate,
  completeWorkRestore,
  completePendingTurn,
  createInitialState,
  expandChatDisclosure,
  expandNoteDetailDisclosure,
  failMemoryLoad,
  failNoteDetailLoad,
  failNoteRequest,
  failNotesLoad,
  failChatSessionDetailLoad,
  failChatSessionListLoad,
  failWorkspaceListLoad,
  failPendingTurn,
  failWorkDetailLoad,
  failWorkListLoad,
  restoreRecoveredTurn,
  selectCanSubmit,
  selectNeedsReceiptRefresh,
  selectWorkspace,
  selectWorkRefreshPlan,
  setNotesStatusFilter,
  setWorkLifecycleStatus,
  storePendingNoteProposal,
  startNewConversation,
  toggleArtifactDisclosure,
  toggleChatDisclosure,
  toggleMemoryEventsDisclosure,
  toggleMemoryDisclosure,
  toggleNoteDetailDisclosure,
  toggleNoteProposalDisclosure,
} from "./state.mjs";
import { setText } from "./render.mjs";

let state = createInitialState();
let chatView = null;
let workView = null;
let memoryView = null;
let notesView = null;
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

function newestFirst(a, b) {
  const left = Date.parse(a.created_at ?? "");
  const right = Date.parse(b.created_at ?? "");
  if (Number.isNaN(left) && Number.isNaN(right)) {
    return 0;
  }
  if (Number.isNaN(left)) {
    return 1;
  }
  if (Number.isNaN(right)) {
    return -1;
  }
  return right - left;
}

function selectedArtifactMetadata(artifactId) {
  return state.work.list.items.find((item) => (
    item.reference?.artifact_id === artifactId
  )) ?? null;
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

function showNotesError(message) {
  const error = document.querySelector("[data-notes-error]");
  setText(error, message);
  error.hidden = false;
}

function clearNotesError() {
  const error = document.querySelector("[data-notes-error]");
  setText(error, "");
  error.hidden = true;
}

function renderChatStatusLetters(status, message) {
  status.replaceChildren();
  status.setAttribute("aria-label", message);
  [...message].forEach((character, index) => {
    const letter = document.createElement("span");
    letter.classList.add("chat-status__letter");
    letter.setAttribute("aria-hidden", "true");
    letter.style.setProperty("--chat-status-letter-index", String(index));
    setText(letter, character);
    status.append(letter);
  });
}

function setChatStatus(message, statusState = "") {
  const status = document.querySelector("[data-chat-status]");
  status.removeAttribute("aria-label");
  if (statusState) {
    renderChatStatusLetters(status, message);
    status.dataset.chatStatusState = statusState;
    return;
  }
  setText(status, message);
  delete status.dataset.chatStatusState;
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
  renderTopBarWorkspaceIndicator();
  document.querySelector("[data-new-conversation]").disabled = (
    state.pendingTurn !== null
    || state.lastFailure?.recovered === true
  );
  ensureWorkspaceView().render(state);
  ensureChatView().render(state);
  ensureWorkView().render(state);
  ensureNotesView().render(state);
  ensureMemoryView().render(state);
  ensureChatsView().render(state);
  renderLayout();
}

function renderTopBarWorkspaceIndicator() {
  renderWorkspaceIndicator(
    document.querySelector("[data-workspace-indicator]"),
    state,
  );
}

function setButtonLabel(button, label) {
  if (!button) {
    return;
  }
  if (button.matches("[data-section-toggle]")) {
    return;
  }
  setText(button, label);
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
    setButtonLabel(button, expanded ? "Hide" : "Show side panel");
    button.setAttribute("aria-expanded", String(expanded));
  }
  for (const button of document.querySelectorAll('[data-drawer-toggle="right"]')) {
    const expanded = isDrawerExpanded(layoutState, "right");
    setButtonLabel(button, expanded ? "Hide" : "Show Artifacts Viewer");
    button.setAttribute("aria-expanded", String(expanded));
  }

  const artifactExpandButton = document.querySelector("[data-artifacts-expand]");
  const artifactsExpanded = layoutState.artifactDrawerMode === "expanded";
  setButtonLabel(
    artifactExpandButton,
    artifactsExpanded ? "Normal Viewer" : "Expand Artifacts Viewer",
  );
  artifactExpandButton.setAttribute("aria-expanded", String(artifactsExpanded));

  for (const section of ["workspace", "work", "notes", "memory", "chats"]) {
    const expanded = isSectionExpanded(layoutState, section);
    const content = document.querySelector(`[data-section-content="${section}"]`);
    const toggle = document.querySelector(`[data-section-toggle="${section}"]`);
    content.hidden = !expanded;
    toggle.setAttribute("aria-expanded", String(expanded));
    setButtonLabel(toggle, expanded ? "Collapse" : "Expand");
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
  renderTopBarWorkspaceIndicator();
  ensureWorkspaceView().render(state);
}

async function loadWorkList() {
  if (!state.context) {
    return;
  }
  clearWorkError();
  const lifecycleStatus = state.work.list.lifecycleStatus ?? "active";
  state = beginWorkListLoad(state);
  ensureWorkView().render(state);
  try {
    const artifactOptions = authOptions({
      limit: 20,
      lifecycle_status: lifecycleStatus,
    });
    const [blueprints, artifacts] = lifecycleStatus === "archived"
      ? [
          { artifacts: [] },
          await listArtifacts(state.context.project_id, artifactOptions),
        ]
      : await Promise.all([
          listBlueprints(
            state.context.project_id,
            authOptions({ limit: 20 }),
          ),
          listArtifacts(
            state.context.project_id,
            artifactOptions,
          ),
        ]);
    state = completeWorkListLoad(state, {
      artifacts: [
        ...(Array.isArray(artifacts.artifacts) ? artifacts.artifacts : []),
        ...(Array.isArray(blueprints.artifacts) ? blueprints.artifacts : []),
      ].sort(newestFirst),
      next_before: null,
    });
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
    const metadata = selectedArtifactMetadata(artifactId);
    let detail = null;
    let feedback = { events: [], next_before: null };
    if (metadata?.reference?.artifact_type === "single_file_artifact") {
      detail = await getArtifact(
        state.context.project_id,
        artifactId,
        authOptions(),
      );
    } else {
      [detail, feedback] = await Promise.all([
        getBlueprint(state.context.project_id, artifactId, authOptions()),
        listBlueprintFeedback(
          state.context.project_id,
          artifactId,
          authOptions({ limit: 20 }),
        ),
      ]);
    }
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

async function loadNotes(statusFilter = state.notes.statusFilter ?? "active") {
  if (!state.context) {
    return;
  }
  clearNotesError();
  state = beginNotesLoad(state, statusFilter);
  ensureNotesView().render(state);
  try {
    const response = await listNotes(
      state.context.user_id,
      state.context.project_id,
      authOptions({ limit: 20, status_filter: statusFilter }),
    );
    state = completeNotesLoad(state, response);
  } catch (error) {
    state = failNotesLoad(state, error);
    showNotesError(error.message);
  }
  ensureNotesView().render(state);
}

async function loadNoteDetail(noteId) {
  if (!state.context) {
    return;
  }
  clearNotesError();
  state = beginNoteDetailLoad(state, noteId);
  ensureNotesView().render(state);
  try {
    const response = await getNote(
      state.context.user_id,
      state.context.project_id,
      noteId,
      authOptions({ limit: 20 }),
    );
    state = completeNoteDetailLoad(state, response);
    state = expandNoteDetailDisclosure(state, response.note?.note_id ?? noteId);
  } catch (error) {
    state = failNoteDetailLoad(state, error);
    showNotesError(error.message);
  }
  ensureNotesView().render(state);
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
    setChatStatus("");
  } catch (error) {
    state = failChatSessionDetailLoad(state, error);
  }
  renderWorkspace();
}

async function refreshAuthoritativeEffects(response) {
  const refreshPlan = selectWorkRefreshPlan(response);
  if (refreshPlan.reloadList) {
    await loadWorkList();
  }
  if (refreshPlan.selectArtifactId !== null) {
    await loadWorkDetail(refreshPlan.selectArtifactId);
  }
  const receiptRefresh = selectNeedsReceiptRefresh(response);
  if (receiptRefresh.memory) {
    await loadMemory();
  }
  if (receiptRefresh.notes) {
    await loadNotes();
  }
}

async function submitRequest(request) {
  state = beginPendingTurn(state, request);
  renderWorkspace();
  document.querySelector("[data-chat-error]").hidden = true;
  setChatStatus("Waiting for Agent Col", "pending");
  try {
    const endpoint = selectChatEndpoint(request);
    const options = {
      method: "POST",
      idempotencyKey: request.key,
      authToken: state.context?.auth_token ?? null,
      body: request.body,
    };
    const response = endpoint === "/api/chat/stream"
      ? await apiFetchSse(endpoint, {
        ...options,
        onDelta(text) {
          const firstDelta = state.pendingResponseText.length === 0;
          state = appendPendingResponseDelta(state, text);
          if (firstDelta) {
            setChatStatus("");
          }
          renderWorkspace();
        },
      })
      : await apiFetchJson(endpoint, options);
    state = completePendingTurn(state, response);
    clearOrdinaryChatRequest(request);
    setChatStatus("");
    renderWorkspace();
    await refreshAuthoritativeEffects(response);
    await loadChatSessions();
  } catch (error) {
    state = failPendingTurn(state, error);
    setChatStatus("");
    setText(document.querySelector("[data-chat-error]"), error.message);
    document.querySelector("[data-chat-error]").hidden = false;
    renderWorkspace();
    if (error.partialFailure) {
      await refreshAuthoritativeEffects(error.partialFailure);
    }
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
      clarificationChoices: document.querySelector("[data-memory-clarification-choices]"),
      continuityChoices: document.querySelector("[data-continuity-choices]"),
    },
    {
      onSubmit(message) {
        if (!selectCanSubmit(state)) {
          return;
        }
        const request = buildOrdinaryChatRequest(state.context, message);
        try {
          storeOrdinaryChatRequest(request);
        } catch {
          setText(
            document.querySelector("[data-chat-error]"),
            "The prompt was not sent because this browser could not safely retain it.",
          );
          document.querySelector("[data-chat-error]").hidden = false;
          return;
        }
        chatView.clearComposer();
        submitRequest(request);
      },
      onRetry() {
        if (state.lastFailure === null) {
          return;
        }
        submitRequest(buildExactRetryRequest(state.lastFailure.request));
      },
      onSelectMemoryClarification(choice) {
        if (!selectCanSubmit(state)) {
          return;
        }
        const request = buildMemoryClarificationSelectionChatRequest(
          state.context,
          choice,
        );
        submitRequest(request);
      },
      onSelectContinuityChoice(choice) {
        if (!selectCanSubmit(state)) {
          return;
        }
        const request = buildContinuitySelectionChatRequest(
          state.context,
          choice,
        );
        submitRequest(request);
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
        await loadNotes();
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
          await loadNotes();
          await loadMemory();
          await loadChatSessions();
        } catch (error) {
          showWorkspaceError(error.message);
        }
      },
      async onDeleteWorkspace(workspace) {
        if (!state.context || state.pendingTurn !== null) {
          return;
        }
        clearWorkspaceError();
        const deletedSelected = (
          workspace.workspace_id === state.workspaces.selectedWorkspaceId
        );
        try {
          await deleteWorkspace(
            state.context.user_id,
            workspace.workspace_id,
            authOptions(),
          );
          state = completeWorkspaceDelete(state, workspace.workspace_id);
          renderWorkspace();
          await loadWorkspaces();
          if (deletedSelected) {
            await loadWorkList();
            await loadNotes();
            await loadMemory();
            await loadChatSessions();
          }
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
      onArchiveArtifact(artifactId) {
        archiveGenericArtifact(artifactId);
      },
      onRestoreArtifact(artifactId) {
        restoreGenericArtifact(artifactId);
      },
      onDeleteArtifact(artifactId) {
        deleteGenericArtifact(artifactId);
      },
      onToggleArtifactDisclosure(artifactId) {
        state = toggleArtifactDisclosure(state, artifactId);
        ensureWorkView().render(state);
      },
      onUpdateArtifactMetadata(artifactId, metadata) {
        updateGenericArtifactMetadata(artifactId, metadata);
      },
      onCreateArtifactVersion(artifactId, request) {
        createGenericArtifactVersion(artifactId, request);
      },
      onSetArtifactLifecycleStatus(lifecycleStatus) {
        setArtifactLifecycleStatus(lifecycleStatus);
      },
    },
  );
  return workView;
}

async function archiveGenericArtifact(artifactId) {
  if (!state.context || state.pendingTurn !== null) {
    return;
  }
  clearWorkError();
  try {
    await archiveArtifact(
      state.context.project_id,
      artifactId,
      authOptions(),
    );
    state = completeWorkArchive(state, artifactId);
    ensureWorkView().render(state);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function restoreGenericArtifact(artifactId) {
  if (!state.context || state.pendingTurn !== null) {
    return;
  }
  clearWorkError();
  try {
    await restoreArtifact(
      state.context.project_id,
      artifactId,
      authOptions(),
    );
    state = completeWorkRestore(state, artifactId);
    ensureWorkView().render(state);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function deleteGenericArtifact(artifactId) {
  if (!state.context || state.pendingTurn !== null) {
    return;
  }
  const confirmed = globalThis.confirm?.(
    "Delete this artifact?\n\nThe artifact is removed from active views, while existing chat history remains unchanged.",
  ) ?? true;
  if (!confirmed) {
    return;
  }
  clearWorkError();
  try {
    await deleteArtifact(
      state.context.project_id,
      artifactId,
      authOptions(),
    );
    state = completeWorkDelete(state, artifactId);
    ensureWorkView().render(state);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function updateGenericArtifactMetadata(artifactId, metadata) {
  if (!state.context || state.pendingTurn !== null) {
    return;
  }
  clearWorkError();
  try {
    const response = await updateArtifactMetadata(
      state.context.project_id,
      artifactId,
      {
        display_label: metadata.display_label,
        filename: metadata.filename,
      },
      authOptions(),
    );
    state = completeWorkMetadataUpdate(state, response.metadata);
    ensureWorkView().render(state);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function createGenericArtifactVersion(artifactId, versionRequest) {
  if (!state.context || state.pendingTurn !== null) {
    return;
  }
  clearWorkError();
  try {
    const response = await createArtifactVersion(
      state.context.project_id,
      artifactId,
      {
        session_id: state.context.session_id,
        user_id: state.context.user_id,
        content: versionRequest.content,
        filename: versionRequest.filename || undefined,
        display_label: versionRequest.display_label || undefined,
        summary: versionRequest.summary || undefined,
      },
      authOptions(),
    );
    state = completeWorkVersionCreate(state, response);
    ensureWorkView().render(state);
    await loadWorkList();
  } catch (error) {
    showWorkError(error.message);
  }
}

async function setArtifactLifecycleStatus(lifecycleStatus) {
  if (!state.context || state.pendingTurn !== null) {
    return;
  }
  state = setWorkLifecycleStatus(state, lifecycleStatus);
  ensureWorkView().render(state);
  await loadWorkList();
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
      onToggleProposalDisclosure(proposalId) {
        state = toggleMemoryDisclosure(state, proposalId, "proposal");
        ensureMemoryView().render(state);
      },
      onToggleSignalDisclosure(signalId) {
        state = toggleMemoryDisclosure(state, signalId, "signal");
        ensureMemoryView().render(state);
      },
      onToggleEventsDisclosure() {
        state = toggleMemoryEventsDisclosure(state);
        ensureMemoryView().render(state);
      },
    },
  );
  return memoryView;
}

function ensureNotesView() {
  if (notesView !== null) {
    return notesView;
  }
  notesView = createNotesView(
    {
      panel: document.querySelector("[data-notes-panel]"),
    },
    {
      onSubmitDecision(decision) {
        submitCollaborativeNoteDecision(decision);
      },
      onSelectNote(noteId) {
        loadNoteDetail(noteId);
      },
      async onSetStatusFilter(statusFilter) {
        state = setNotesStatusFilter(state, statusFilter);
        ensureNotesView().render(state);
        await loadNotes(statusFilter);
      },
      onCreateCorrection(note, request) {
        createCollaborativeNoteCorrection(note, request);
      },
      onCreateNoteProposal(request) {
        createCollaborativeNoteProposal(request);
      },
      onToggleProposalDisclosure(proposalId) {
        state = toggleNoteProposalDisclosure(state, proposalId);
        ensureNotesView().render(state);
      },
      onToggleDetailDisclosure(noteId) {
        state = toggleNoteDetailDisclosure(state, noteId);
        ensureNotesView().render(state);
      },
      onArchiveNote(note) {
        changeCollaborativeNoteLifecycle("archive", note);
      },
      onRestoreNote(note) {
        changeCollaborativeNoteLifecycle("restore", note);
      },
      onDeleteNote(note) {
        changeCollaborativeNoteLifecycle("delete", note);
      },
    },
  );
  return notesView;
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
        state = expandChatDisclosure(state, sessionId);
        loadChatSession(sessionId);
      },
      onToggleSessionDisclosure(sessionId) {
        state = toggleChatDisclosure(state, sessionId);
        ensureChatsView().render(state);
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
    "Record artifact feedback.",
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
    `${decision.decision === "reject" ? "Reject" : "Approve"} this memory proposal.`,
    decision,
  );
  await submitRequest(request);
}

async function submitCollaborativeNoteDecision(decision) {
  if (!selectCanSubmit(state)) {
    return;
  }
  const request = buildCollaborativeNoteDecisionChatRequest(
    state.context,
    `${decision.decision === "reject" ? "Reject" : "Approve"} this workspace note.`,
    decision,
  );
  await submitRequest(request);
}

async function createCollaborativeNoteCorrection(note, request) {
  if (!state.context || !selectCanSubmit(state)) {
    return;
  }
  clearNotesError();
  state = beginNoteRequest(state, `correction:${note.note_id}`);
  ensureNotesView().render(state);
  try {
    const response = await createNoteCorrection(
      state.context.user_id,
      state.context.project_id,
      note.note_id,
      request,
      {
        ...authOptions(),
        idempotencyKey: `note-correction--${crypto.randomUUID()}`,
      },
    );
    state = completeNoteRequest(storePendingNoteProposal(state, response.proposal));
    await loadNotes();
  } catch (error) {
    state = failNoteRequest(state, error);
    showNotesError(error.message);
  }
  renderWorkspace();
}

async function createCollaborativeNoteProposal(request) {
  if (!state.context || !selectCanSubmit(state)) {
    return;
  }
  clearNotesError();
  state = beginNoteRequest(state, "proposal:create");
  ensureNotesView().render(state);
  try {
    const response = await createNoteProposal(
      state.context.user_id,
      state.context.project_id,
      {
        ...request,
        session_id: state.context.session_id,
      },
      {
        ...authOptions(),
        idempotencyKey: `note-proposal--${crypto.randomUUID()}`,
      },
    );
    state = completeNoteRequest(storePendingNoteProposal(state, response.proposal));
    await loadNotes();
  } catch (error) {
    state = failNoteRequest(state, error);
    showNotesError(error.message);
  }
  renderWorkspace();
}

async function changeCollaborativeNoteLifecycle(action, note) {
  if (!state.context || !selectCanSubmit(state)) {
    return;
  }
  clearNotesError();
  state = beginNoteRequest(state, `${action}:${note.note_id}`);
  ensureNotesView().render(state);
  try {
    const request = { expected_revision: note.revision };
    if (action === "archive") {
      await archiveNote(
        state.context.user_id,
        state.context.project_id,
        note.note_id,
        request,
        authOptions(),
      );
    } else if (action === "restore") {
      await restoreNote(
        state.context.user_id,
        state.context.project_id,
        note.note_id,
        request,
        authOptions(),
      );
    } else {
      await deleteNote(
        state.context.user_id,
        state.context.project_id,
        note.note_id,
        request,
        authOptions(),
      );
    }
    state = completeNoteRequest(state);
    await loadNotes(state.notes.statusFilter);
  } catch (error) {
    state = failNoteRequest(state, error);
    showNotesError(error.message);
  }
  renderWorkspace();
}

async function revokeActiveMemorySignal(signal) {
  if (!state.context) {
    return;
  }
  clearMemoryError();
  try {
    const response = await revokeMemorySignal(
      state.context.user_id,
      signal.signal_id,
      authOptions(),
    );
    state = completeMemorySignalMutation(
      state,
      signal.signal_id,
      response.profile,
    );
  } catch (error) {
    showMemoryError(error.message);
  }
  renderWorkspace();
}

async function deleteActiveMemorySignal(signal) {
  if (!state.context) {
    return;
  }
  clearMemoryError();
  try {
    await deleteMemorySignal(
      state.context.user_id,
      signal.signal_id,
      authOptions(),
    );
    state = completeMemorySignalMutation(state, signal.signal_id);
  } catch (error) {
    showMemoryError(error.message);
  }
  renderWorkspace();
}

document.querySelector("[data-context-form]").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    state = acceptContext(
      state,
      contextForSubmit(event.currentTarget),
    );
    const recoveredRequest = loadOrdinaryChatRequest(state.context);
    ensureChatView();
    ensureWorkView();
    ensureNotesView();
    ensureMemoryView();
    ensureChatsView();
    ensureWorkspaceView();
    showWorkspace();
    renderWorkspace();
    await loadWorkspaces();
    const canRestoreRequest = (
      recoveredRequest !== null
      && recoveredRequest.body.user_id === state.context?.user_id
      && recoveredRequest.body.project_id === state.context?.project_id
      && selectCanSubmit(state)
    );
    if (canRestoreRequest) {
      state = restoreRecoveredTurn(state, recoveredRequest);
      renderWorkspace();
      setText(
        document.querySelector("[data-chat-error]"),
        state.lastFailure.message,
      );
      document.querySelector("[data-chat-error]").hidden = false;
    }
    loadWorkList();
    loadNotes();
    loadMemory();
    loadChatSessions();
  } catch (error) {
    showContextError(error.message);
  }
});

document.querySelector("[data-new-conversation]").addEventListener("click", () => {
  if (state.pendingTurn !== null || state.lastFailure?.recovered === true) {
    return;
  }
  state = startNewConversation(state);
  document.querySelector("[data-chat-error]").hidden = true;
  setChatStatus("");
  renderWorkspace();
  loadNotes();
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
  loadNotes();
  loadMemory();
  loadChatSessions();
});

bootstrapAuth();
