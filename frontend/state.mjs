import { generateSessionId } from "./requests.mjs";
import { humanLabel, humanValue } from "./render.mjs";

export function createInitialState() {
  return {
    mode: "context",
    context: null,
    transcript: [],
    pendingTurn: null,
    pendingResponseText: "",
    lastFailure: null,
    activeMemoryClarification: null,
    activeContinuityChoices: [],
    workspaces: {
      status: "idle",
      items: [],
      selectedWorkspaceId: null,
      error: null,
    },
    work: {
      list: {
        status: "idle",
        lifecycleStatus: "active",
        items: [],
        next_before: null,
        error: null,
      },
      selectedArtifactId: null,
      detail: {
        status: "idle",
        item: null,
        error: null,
      },
      feedback: {
        status: "idle",
        events: [],
        next_before: null,
        error: null,
      },
    },
    memory: {
      status: "idle",
      profile: null,
      unresolvedProposals: [],
      events: [],
      next_event_id: null,
      error: null,
    },
    notes: emptyNotesState(),
    chats: {
      status: "idle",
      sessions: [],
      selectedSessionId: null,
      detailStatus: "idle",
      error: null,
    },
    activity: {
      entries: [],
    },
    disclosure: emptyDisclosureState(),
  };
}

function emptyDisclosureState() {
  return {
    notes: {
      proposalIds: [],
      detailNoteIds: [],
    },
    memory: {
      proposalIds: [],
      signalIds: [],
    },
    chats: {
      sessionIds: [],
    },
    work: {
      artifactIds: [],
    },
  };
}

export function acceptContext(state, context) {
  return {
    ...state,
    mode: "workspace",
    context: {
      user_id: context.user_id,
      project_id: context.project_id,
      auth_token: context.auth_token ?? null,
      session_id: generateSessionId(context.crypto),
    },
    workspaces: {
      ...state.workspaces,
      selectedWorkspaceId: context.project_id,
    },
  };
}

function emptyWorkState() {
  return {
    list: {
      status: "idle",
      lifecycleStatus: "active",
      items: [],
      next_before: null,
      error: null,
    },
    selectedArtifactId: null,
    detail: {
      status: "idle",
      item: null,
      error: null,
    },
    feedback: {
      status: "idle",
      events: [],
      next_before: null,
      error: null,
    },
  };
}

function emptyChatSessionState() {
  return {
    status: "idle",
    sessions: [],
    selectedSessionId: null,
    detailStatus: "idle",
    error: null,
  };
}

function emptyNotesState() {
  return {
    status: "idle",
    statusFilter: "active",
    notes: [],
    next_note_id: null,
    pendingProposals: [],
    selectedNoteId: null,
    detail: {
      status: "idle",
      note: null,
      events: [],
      error: null,
    },
    pendingRequest: null,
    error: null,
  };
}

export function beginWorkspaceListLoad(state) {
  return {
    ...state,
    workspaces: {
      ...state.workspaces,
      status: "loading",
      error: null,
    },
  };
}

export function completeWorkspaceListLoad(
  state,
  response,
  cryptoLike = globalThis.crypto,
) {
  const items = Array.isArray(response.workspaces) ? response.workspaces : [];
  const currentWorkspaceId = (
    state.workspaces.selectedWorkspaceId
    ?? state.context?.project_id
    ?? null
  );
  const currentWorkspace = items.find((item) => (
    item.workspace_id === currentWorkspaceId
  ));
  if (!currentWorkspace && items.length && state.context) {
    return {
      ...selectWorkspace(state, items[0], cryptoLike),
      workspaces: {
        ...state.workspaces,
        status: "ready",
        items,
        selectedWorkspaceId: items[0].workspace_id,
        error: null,
      },
    };
  }
  return {
    ...state,
    workspaces: {
      ...state.workspaces,
      status: "ready",
      items,
      selectedWorkspaceId: (
        currentWorkspace?.workspace_id
        ?? items[0]?.workspace_id
        ?? null
      ),
      error: null,
    },
  };
}

export function failWorkspaceListLoad(state, error) {
  return {
    ...state,
    workspaces: {
      ...state.workspaces,
      status: "error",
      error: errorMessage(error),
    },
  };
}

export function selectWorkspace(
  state,
  workspace,
  cryptoLike = globalThis.crypto,
) {
  if (!state.context) {
    throw new Error("Context is required before selecting a workspace.");
  }
  return {
    ...state,
    context: {
      ...state.context,
      project_id: workspace.workspace_id,
      session_id: generateSessionId(cryptoLike),
    },
    transcript: [],
    pendingTurn: null,
    pendingResponseText: "",
    lastFailure: null,
    activeMemoryClarification: null,
    activeContinuityChoices: [],
    work: emptyWorkState(),
    notes: emptyNotesState(),
    chats: emptyChatSessionState(),
    disclosure: emptyDisclosureState(),
    workspaces: {
      ...state.workspaces,
      selectedWorkspaceId: workspace.workspace_id,
      error: null,
    },
  };
}

export function completeWorkspaceCreate(
  state,
  response,
  cryptoLike = globalThis.crypto,
) {
  const workspace = response.workspace;
  const withoutDuplicate = state.workspaces.items.filter(
    (item) => item.workspace_id !== workspace.workspace_id,
  );
  const selected = selectWorkspace(
    {
      ...state,
      workspaces: {
        ...state.workspaces,
        status: "ready",
        items: [workspace, ...withoutDuplicate],
      },
    },
    workspace,
    cryptoLike,
  );
  return {
    ...selected,
    workspaces: {
      ...selected.workspaces,
      items: [workspace, ...withoutDuplicate],
    },
  };
}

export function completeWorkspaceDelete(
  state,
  workspaceId,
  cryptoLike = globalThis.crypto,
) {
  const remainingItems = state.workspaces.items.filter(
    (item) => item.workspace_id !== workspaceId,
  );
  if (state.workspaces.selectedWorkspaceId !== workspaceId) {
    return {
      ...state,
      workspaces: {
        ...state.workspaces,
        items: remainingItems,
        error: null,
      },
    };
  }
  const nextWorkspace = remainingItems[0] ?? null;
  if (nextWorkspace === null) {
    return {
      ...state,
      workspaces: {
        ...state.workspaces,
        items: remainingItems,
        selectedWorkspaceId: null,
        error: null,
      },
    };
  }
  const selected = selectWorkspace(
    {
      ...state,
      workspaces: {
        ...state.workspaces,
        items: remainingItems,
      },
    },
    nextWorkspace,
    cryptoLike,
  );
  return {
    ...selected,
    workspaces: {
      ...selected.workspaces,
      items: remainingItems,
    },
  };
}

export function beginPendingTurn(state, request) {
  if (state.pendingTurn !== null) {
    throw new Error("A turn is already pending.");
  }
  return {
    ...state,
    pendingTurn: request,
    pendingResponseText: "",
    lastFailure: null,
  };
}

export function appendPendingResponseDelta(state, text) {
  if (state.pendingTurn === null) {
    throw new Error("A streamed response requires a pending turn.");
  }
  if (typeof text !== "string" || text.length === 0) {
    return state;
  }
  return {
    ...state,
    pendingResponseText: `${state.pendingResponseText}${text}`,
  };
}

export function failPendingTurn(state, error) {
  const partialFailure = error.partialFailure ?? null;
  const partialEffects = objectOrEmpty(partialFailure);
  return {
    ...state,
    lastFailure: {
      request: state.pendingTurn,
      message: error.message,
      status: error.status ?? null,
      retryAfterSeconds: error.retryAfterSeconds ?? null,
      provisionalResponseText: state.pendingResponseText,
      partialFailure,
    },
    activity: appendActivityEntries(state.activity, [{
      kind: "error",
      label: errorActivityLabel(error),
      detail: errorMessage(error),
    }]),
    pendingTurn: null,
    pendingResponseText: "",
    activeMemoryClarification: nextActiveMemoryClarification(
      state.activeMemoryClarification,
      partialEffects,
      false,
    ),
    activeContinuityChoices: nextActiveContinuityChoices(
      state.activeContinuityChoices,
      partialEffects,
      false,
    ),
    notes: storePendingNoteProposalsFromResponse(state.notes, partialEffects),
  };
}

export function completePendingTurn(state, response) {
  const completedSelection = isMemoryClarificationSelectionRequest(
    state.pendingTurn,
  );
  const nextClarification = nextActiveMemoryClarification(
    state.activeMemoryClarification,
    response,
    completedSelection,
  );
  const nextContinuityChoices = nextActiveContinuityChoices(
    state.activeContinuityChoices,
    response,
    isContinuitySelectionRequest(state.pendingTurn),
  );
  return {
    ...state,
    transcript: [
      ...state.transcript,
      {
        request: state.pendingTurn,
        response,
      },
    ],
    activity: appendActivityEntries(
      state.activity,
      activityEntriesFromResponse(response),
    ),
    chats: {
      ...state.chats,
      selectedSessionId: state.context?.session_id ?? null,
      detailStatus: "loaded",
      error: null,
    },
    pendingTurn: null,
    pendingResponseText: "",
    lastFailure: null,
    activeMemoryClarification: nextClarification,
    activeContinuityChoices: nextContinuityChoices,
    notes: storePendingNoteProposalsFromResponse(state.notes, response),
  };
}

export function startNewConversation(state, cryptoLike = globalThis.crypto) {
  if (!state.context) {
    throw new Error(
      "Context is required before starting a new conversation.",
    );
  }
  return {
    ...state,
    context: {
      ...state.context,
      session_id: generateSessionId(cryptoLike),
    },
    transcript: [],
    pendingTurn: null,
    pendingResponseText: "",
    lastFailure: null,
    activeMemoryClarification: null,
    activeContinuityChoices: [],
    chats: {
      ...state.chats,
      selectedSessionId: null,
      detailStatus: "idle",
      error: null,
    },
    disclosure: {
      ...state.disclosure,
      chats: { sessionIds: [] },
    },
  };
}

function toggleStableId(ids, id) {
  const textId = String(id ?? "");
  if (!textId) {
    return ids;
  }
  return ids.includes(textId)
    ? ids.filter((item) => item !== textId)
    : [...ids, textId];
}

function expandStableId(ids, id) {
  const textId = String(id ?? "");
  if (!textId || ids.includes(textId)) {
    return ids;
  }
  return [...ids, textId];
}

export function toggleNoteProposalDisclosure(state, proposalId) {
  return {
    ...state,
    disclosure: {
      ...state.disclosure,
      notes: {
        ...state.disclosure.notes,
        proposalIds: toggleStableId(
          state.disclosure.notes.proposalIds,
          proposalId,
        ),
      },
    },
  };
}

export function toggleNoteDetailDisclosure(state, noteId) {
  return {
    ...state,
    disclosure: {
      ...state.disclosure,
      notes: {
        ...state.disclosure.notes,
        detailNoteIds: toggleStableId(
          state.disclosure.notes.detailNoteIds,
          noteId,
        ),
      },
    },
  };
}

export function expandNoteDetailDisclosure(state, noteId) {
  return {
    ...state,
    disclosure: {
      ...state.disclosure,
      notes: {
        ...state.disclosure.notes,
        detailNoteIds: expandStableId(
          state.disclosure.notes.detailNoteIds,
          noteId,
        ),
      },
    },
  };
}

export function toggleMemoryDisclosure(state, id, kind) {
  const key = kind === "proposal" ? "proposalIds" : "signalIds";
  return {
    ...state,
    disclosure: {
      ...state.disclosure,
      memory: {
        ...state.disclosure.memory,
        [key]: toggleStableId(state.disclosure.memory[key], id),
      },
    },
  };
}

export function toggleArtifactDisclosure(state, artifactId) {
  return {
    ...state,
    disclosure: {
      ...state.disclosure,
      work: {
        ...state.disclosure.work,
        artifactIds: toggleStableId(
          state.disclosure.work.artifactIds,
          artifactId,
        ),
      },
    },
  };
}

export function toggleChatDisclosure(state, sessionId) {
  return {
    ...state,
    disclosure: {
      ...state.disclosure,
      chats: {
        ...state.disclosure.chats,
        sessionIds: toggleStableId(
          state.disclosure.chats.sessionIds,
          sessionId,
        ),
      },
    },
  };
}

export function expandChatDisclosure(state, sessionId) {
  return {
    ...state,
    disclosure: {
      ...state.disclosure,
      chats: {
        ...state.disclosure.chats,
        sessionIds: expandStableId(
          state.disclosure.chats.sessionIds,
          sessionId,
        ),
      },
    },
  };
}

export function beginChatSessionListLoad(state) {
  return {
    ...state,
    chats: {
      ...state.chats,
      status: "loading",
      error: null,
    },
  };
}

export function completeChatSessionListLoad(state, response) {
  return {
    ...state,
    chats: {
      ...state.chats,
      status: "loaded",
      sessions: Array.isArray(response.sessions) ? response.sessions : [],
      error: null,
    },
  };
}

export function failChatSessionListLoad(state, error) {
  return {
    ...state,
    chats: {
      ...state.chats,
      status: "error",
      error: errorMessage(error),
    },
  };
}

export function beginChatSessionDetailLoad(state, sessionId) {
  return {
    ...state,
    chats: {
      ...state.chats,
      selectedSessionId: sessionId,
      detailStatus: "loading",
      error: null,
    },
  };
}

export function completeChatSessionDetailLoad(state, response) {
  return {
    ...state,
    context: {
      ...state.context,
      session_id: response.session_id,
    },
    transcript: transcriptFromMessages(response.messages),
    pendingTurn: null,
    pendingResponseText: "",
    lastFailure: null,
    activeMemoryClarification: (
      response.active_memory_clarification ?? null
    ),
    activeContinuityChoices: [],
    chats: {
      ...state.chats,
      selectedSessionId: response.session_id,
      detailStatus: "loaded",
      error: null,
    },
  };
}

export function failChatSessionDetailLoad(state, error) {
  return {
    ...state,
    chats: {
      ...state.chats,
      detailStatus: "error",
      error: errorMessage(error),
    },
  };
}

export function selectCanSubmit(state) {
  if (
    state.mode !== "workspace"
    || state.context === null
    || state.pendingTurn !== null
  ) {
    return false;
  }
  if (state.workspaces.status !== "ready" || !state.workspaces.items.length) {
    return false;
  }
  return state.workspaces.items.some((workspace) => (
    workspace.workspace_id === state.context.project_id
  ));
}

export function selectNeedsReceiptRefresh(response) {
  const actions = Array.isArray(response.actions) ? response.actions : [];
  const hasSuccessfulChatResponse = (
    response !== null
    && typeof response === "object"
    && typeof response.response === "string"
  );
  return {
    work: Array.isArray(response.artifacts) && response.artifacts.length > 0,
    memory: (
      hasSuccessfulChatResponse
      || (
        Array.isArray(response.memory_proposals)
        && response.memory_proposals.length > 0
      )
      || (
        Array.isArray(response.adaptations)
        && response.adaptations.length > 0
      )
      || actions.some((action) => (
        action !== null
        && typeof action === "object"
        && typeof action.action_name === "string"
        && action.action_name.includes("memory")
      ))
    ),
    notes: (
      (
        Array.isArray(response.collaborative_note_proposals)
        && response.collaborative_note_proposals.length > 0
      )
      || (
        Array.isArray(response.collaborative_note_events)
        && response.collaborative_note_events.length > 0
      )
      || (
        Array.isArray(response.continuity_receipts)
        && response.continuity_receipts.some((receipt) => (
          objectOrEmpty(receipt).source_kind === "collaborative_note"
        ))
      )
      || actions.some((action) => (
        action !== null
        && typeof action === "object"
        && typeof action.action_name === "string"
        && action.action_name.includes("collaborative_note")
      ))
    ),
  };
}

function errorMessage(error) {
  return error && typeof error.message === "string"
    ? error.message
    : "Request failed.";
}

function errorActivityLabel(error) {
  return error?.status === 504 ? "Timed out" : "Request failed";
}

function compactText(parts) {
  return parts.filter((part) => (
    part !== undefined
    && part !== null
    && part !== ""
  )).map((part) => String(part)).join(" · ");
}

function transcriptFromMessages(messages) {
  const transcript = [];
  let pendingUser = null;
  for (const rawMessage of Array.isArray(messages) ? messages : []) {
    const message = objectOrEmpty(rawMessage);
    if (message.role === "user" && typeof message.text === "string") {
      pendingUser = {
        key: `reopened--${message.message_id ?? transcript.length}`,
        body: { message: message.text },
      };
      continue;
    }
    if (
      message.role === "model"
      && typeof message.text === "string"
      && pendingUser !== null
    ) {
      transcript.push({
        request: pendingUser,
        response: {
          response: message.text,
          actions: [],
          artifacts: [],
          artifact_feedback: [],
            citations: [],
            memory_proposals: [],
            memory_clarifications: [],
            collaborative_note_proposals: [],
            collaborative_note_events: [],
            continuity_receipts: [],
            continuity_choices: [],
            adaptations: [],
          },
      });
      pendingUser = null;
    }
  }
  if (pendingUser !== null) {
    transcript.push({
      request: pendingUser,
      response: {
        response: "",
        actions: [],
        artifacts: [],
        artifact_feedback: [],
        citations: [],
        memory_proposals: [],
        memory_clarifications: [],
        collaborative_note_proposals: [],
        collaborative_note_events: [],
        continuity_receipts: [],
        continuity_choices: [],
        adaptations: [],
      },
    });
  }
  return transcript;
}

function appendActivityEntries(activity, entries) {
  const existing = Array.isArray(activity?.entries) ? activity.entries : [];
  return {
    entries: [...existing, ...entries].slice(-50),
  };
}

function objectOrEmpty(value) {
  return value !== null && typeof value === "object" ? value : {};
}

function isMemoryClarificationSelectionRequest(request) {
  return Boolean(
    request
    && typeof request === "object"
    && request.body
    && typeof request.body === "object"
    && request.body.memory_clarification_selection,
  );
}

function firstMemoryClarification(response) {
  const clarifications = Array.isArray(response.memory_clarifications)
    ? response.memory_clarifications
    : [];
  return clarifications[0] ?? null;
}

function nextActiveMemoryClarification(current, response, completedSelection) {
  const clarification = firstMemoryClarification(response);
  if (clarification !== null) {
    return clarification;
  }
  if (completedSelection) {
    return null;
  }
  return current ?? null;
}

function nextActiveContinuityChoices(current, response, completedSelection) {
  const choices = Array.isArray(response.continuity_choices)
    ? response.continuity_choices
    : [];
  if (choices.length > 0) {
    return choices;
  }
  if (completedSelection) {
    return [];
  }
  return current ?? [];
}

function isContinuitySelectionRequest(request) {
  return Boolean(
    request
    && typeof request === "object"
    && request.body
    && typeof request.body === "object"
    && request.body.continuity_selection,
  );
}

function activityEntriesFromResponse(response) {
  const entries = [];
  for (const rawAction of Array.isArray(response.actions) ? response.actions : []) {
    const action = objectOrEmpty(rawAction);
    entries.push({
      kind: "action",
      label: action.action_name ?? "Action",
      detail: action.status ?? "",
    });
  }
  for (const rawCitation of Array.isArray(response.citations) ? response.citations : []) {
    const citation = objectOrEmpty(rawCitation);
    entries.push({
      kind: "citation",
      label: citation.label ?? "Citation",
      detail: citation.uri ?? "",
    });
  }
  for (const rawArtifact of Array.isArray(response.artifacts) ? response.artifacts : []) {
    const artifact = objectOrEmpty(rawArtifact);
    entries.push({
      kind: "work",
      label: artifact.display_label ?? "Artifact",
      detail: "created",
    });
  }
  for (
    const rawFeedback of Array.isArray(response.artifact_feedback)
      ? response.artifact_feedback
      : []
  ) {
    const feedback = objectOrEmpty(rawFeedback);
    entries.push({
      kind: "feedback",
      label: compactText(["Feedback", feedback.decision]),
      detail: feedback.status ?? "recorded",
    });
  }
  for (
    const rawProposal of Array.isArray(response.memory_proposals)
      ? response.memory_proposals
      : []
  ) {
    const proposal = objectOrEmpty(rawProposal);
    entries.push({
      kind: "memory",
      label: proposal.category ?? "Memory proposal",
      detail: proposal.status ?? "pending",
    });
  }
  for (
    const rawProposal of Array.isArray(response.collaborative_note_proposals)
      ? response.collaborative_note_proposals
      : []
  ) {
    const proposal = objectOrEmpty(rawProposal);
    entries.push({
      kind: "note",
      label: proposal.title ?? "Note proposal",
      detail: proposal.status ?? "pending",
    });
  }
  for (
    const rawEvent of Array.isArray(response.collaborative_note_events)
      ? response.collaborative_note_events
      : []
  ) {
    const event = objectOrEmpty(rawEvent);
    entries.push({
      kind: "note",
      label: compactText(["Note", event.event_type]),
      detail: event.title ?? "",
    });
  }
  for (
    const rawClarification of Array.isArray(response.memory_clarifications)
      ? response.memory_clarifications
      : []
  ) {
    const clarification = objectOrEmpty(rawClarification);
    const choices = Array.isArray(clarification.choices)
      ? clarification.choices
      : [];
    const firstChoice = objectOrEmpty(choices[0]);
    entries.push({
      kind: "memory_clarification",
      label: "Memory clarification",
      detail: compactText([
        firstChoice.category_label && firstChoice.value_label
          ? `${firstChoice.category_label}: ${firstChoice.value_label}`
          : "",
      ]),
    });
  }
  for (const rawAdaptation of Array.isArray(response.adaptations) ? response.adaptations : []) {
    const adaptation = objectOrEmpty(rawAdaptation);
    if (typeof adaptation.category !== "string") {
      continue;
    }
    entries.push({
      kind: "adaptation",
      label: humanLabel(adaptation.category),
      detail: humanValue(adaptation.value),
    });
  }
  return entries;
}

export function beginWorkListLoad(state) {
  return {
    ...state,
    work: {
      ...state.work,
      list: { ...state.work.list, status: "loading", error: null },
    },
  };
}

export function setWorkLifecycleStatus(state, lifecycleStatus) {
  return {
    ...state,
    work: {
      ...state.work,
      selectedArtifactId: null,
      list: {
        ...state.work.list,
        lifecycleStatus,
        status: "idle",
        items: [],
        next_before: null,
        error: null,
      },
      detail: { status: "idle", item: null, error: null },
      feedback: { status: "idle", events: [], next_before: null, error: null },
    },
  };
}

export function completeWorkListLoad(state, response) {
  return {
    ...state,
    work: {
      ...state.work,
      list: {
        status: "ready",
        lifecycleStatus: state.work.list.lifecycleStatus ?? "active",
        items: Array.isArray(response.artifacts) ? response.artifacts : [],
        next_before: response.next_before ?? null,
        error: null,
      },
    },
  };
}

export function failWorkListLoad(state, error) {
  return {
    ...state,
    work: {
      ...state.work,
      list: {
        ...state.work.list,
        status: "error",
        error: errorMessage(error),
      },
    },
  };
}

export function beginWorkDetailLoad(state, artifactId) {
  return {
    ...state,
    work: {
      ...state.work,
      selectedArtifactId: artifactId,
      detail: { status: "loading", item: null, error: null },
      feedback: {
        status: "loading",
        events: [],
        next_before: null,
        error: null,
      },
    },
  };
}

export function completeWorkDetailLoad(state, detail, feedback) {
  return {
    ...state,
    work: {
      ...state.work,
      detail: { status: "ready", item: detail, error: null },
      feedback: {
        status: "ready",
        events: Array.isArray(feedback.events) ? feedback.events : [],
        next_before: feedback.next_before ?? null,
        error: null,
      },
    },
  };
}

export function completeWorkArchive(state, artifactId) {
  return removeWorkArtifactFromCurrentView(state, artifactId);
}

export function completeWorkRestore(state, artifactId) {
  return removeWorkArtifactFromCurrentView(state, artifactId);
}

export function completeWorkDelete(state, artifactId) {
  return removeWorkArtifactFromCurrentView(state, artifactId);
}

export function completeWorkMetadataUpdate(state, metadata) {
  const artifactId = metadata?.reference?.artifact_id ?? null;
  if (!artifactId) {
    return state;
  }
  const updateItem = (item) => {
    if (item.reference?.artifact_id !== artifactId) {
      return item;
    }
    return {
      ...item,
      ...metadata,
      reference: {
        ...item.reference,
        ...metadata.reference,
      },
    };
  };
  const loadedDetailArtifactId = (
    state.work.detail.item?.metadata?.reference?.artifact_id
    ?? state.work.detail.item?.reference?.artifact_id
  );
  const detail = loadedDetailArtifactId === artifactId
    ? {
        ...state.work.detail,
        item: {
          ...state.work.detail.item,
          metadata: {
            ...state.work.detail.item.metadata,
            ...metadata,
            reference: {
              ...state.work.detail.item.metadata.reference,
              ...metadata.reference,
            },
          },
          artifact: {
            ...state.work.detail.item.artifact,
            filename: metadata.filename
              ?? state.work.detail.item.artifact?.filename,
          },
        },
      }
    : state.work.detail;
  return {
    ...state,
    work: {
      ...state.work,
      list: {
        ...state.work.list,
        items: state.work.list.items.map(updateItem),
      },
      detail,
    },
  };
}

export function completeWorkVersionCreate(state, response) {
  const reference = response?.reference ?? null;
  const artifact = response?.artifact ?? null;
  if (!reference?.artifact_id || !artifact) {
    return state;
  }
  const parentArtifactId = (
    state.work.selectedArtifactId
    ?? state.work.detail.item?.metadata?.reference?.artifact_id
    ?? state.work.detail.item?.reference?.artifact_id
    ?? null
  );
  const metadata = {
    reference,
    filename: artifact.filename,
    artifact_family: artifact.artifact_family,
    format: artifact.format,
    byte_size: new TextEncoder().encode(artifact.content ?? "").length,
    parent_artifact_id: parentArtifactId,
    lifecycle_status: "active",
  };
  return {
    ...state,
    work: {
      ...state.work,
      selectedArtifactId: reference.artifact_id,
      list: {
        ...state.work.list,
        items: [
          metadata,
          ...state.work.list.items.filter((item) => (
            item.reference?.artifact_id !== reference.artifact_id
          )),
        ],
      },
      detail: {
        status: "ready",
        item: { metadata, artifact },
        error: null,
      },
      feedback: {
        status: "idle",
        events: [],
        next_before: null,
        error: null,
      },
    },
  };
}

function removeWorkArtifactFromCurrentView(state, artifactId) {
  const remainingItems = state.work.list.items.filter((item) => (
    item.reference?.artifact_id !== artifactId
  ));
  const loadedDetailArtifactId = (
    state.work.detail.item?.metadata?.reference?.artifact_id
    ?? state.work.detail.item?.reference?.artifact_id
  );
  const selected = (
    state.work.selectedArtifactId === artifactId
    || loadedDetailArtifactId === artifactId
  );
  return {
    ...state,
    disclosure: {
      ...state.disclosure,
      work: {
        ...state.disclosure.work,
        artifactIds: state.disclosure.work.artifactIds.filter((id) => (
          id !== artifactId
        )),
      },
    },
    work: {
      ...state.work,
      selectedArtifactId: selected ? null : state.work.selectedArtifactId,
      list: {
        ...state.work.list,
        items: remainingItems,
      },
      detail: selected
        ? { status: "idle", item: null, error: null }
        : state.work.detail,
      feedback: selected
        ? { status: "idle", events: [], next_before: null, error: null }
        : state.work.feedback,
    },
  };
}

export function failWorkDetailLoad(state, error) {
  return {
    ...state,
    work: {
      ...state.work,
      detail: {
        ...state.work.detail,
        status: "error",
        error: errorMessage(error),
      },
      feedback: {
        ...state.work.feedback,
        status: "error",
        error: errorMessage(error),
      },
    },
  };
}

export function beginMemoryLoad(state) {
  return {
    ...state,
    memory: {
      ...state.memory,
      status: "loading",
      error: null,
    },
  };
}

export function completeMemoryLoad(state, response) {
  return {
    ...state,
    memory: {
      status: "ready",
      profile: response.profile ?? null,
      unresolvedProposals: Array.isArray(response.unresolved_proposals)
        ? response.unresolved_proposals
        : [],
      events: Array.isArray(response.events) ? response.events : [],
      next_event_id: response.next_event_id ?? null,
      error: null,
    },
  };
}

function profileWithoutMemorySignal(profile, signalId) {
  if (!profile || typeof profile !== "object") {
    return profile ?? null;
  }
  const nextProfile = { ...profile };
  for (const key of ["identity_context", "active_preferences"]) {
    const entries = profile[key];
    if (!entries || typeof entries !== "object") {
      continue;
    }
    nextProfile[key] = Object.fromEntries(
      Object.entries(entries).filter(([, signal]) => (
        signal?.signal_id !== signalId
      )),
    );
  }
  return nextProfile;
}

export function completeMemorySignalMutation(state, signalId, profile = null) {
  return {
    ...state,
    disclosure: {
      ...state.disclosure,
      memory: {
        ...state.disclosure.memory,
        signalIds: state.disclosure.memory.signalIds.filter((id) => (
          id !== signalId
        )),
      },
    },
    memory: {
      ...state.memory,
      status: "ready",
      profile: profile ?? profileWithoutMemorySignal(state.memory.profile, signalId),
      error: null,
    },
  };
}

export function failMemoryLoad(state, error) {
  return {
    ...state,
    memory: {
      ...state.memory,
      status: "error",
      error: errorMessage(error),
    },
  };
}

export function beginNotesLoad(state, statusFilter = state.notes.statusFilter) {
  return {
    ...state,
    notes: {
      ...state.notes,
      status: "loading",
      statusFilter,
      error: null,
    },
  };
}

export function completeNotesLoad(state, response) {
  const notes = Array.isArray(response.notes) ? response.notes : [];
  const hasSelectedNote = Boolean(state.notes.selectedNoteId);
  const refreshedSelectedNote = notes.find((note) => (
    note?.note_id === state.notes.selectedNoteId
  ));
  const shouldClearSelectedNote = hasSelectedNote && !refreshedSelectedNote;
  return {
    ...state,
    notes: {
      ...state.notes,
      status: "ready",
      notes,
      next_note_id: response.next_note_id ?? null,
      selectedNoteId: shouldClearSelectedNote ? null : state.notes.selectedNoteId,
      detail: refreshedSelectedNote
        ? {
          ...state.notes.detail,
          note: refreshedSelectedNote,
        }
        : shouldClearSelectedNote
          ? {
            status: "idle",
            note: null,
            events: [],
            error: null,
          }
          : state.notes.detail,
      error: null,
    },
  };
}

export function failNotesLoad(state, error) {
  return {
    ...state,
    notes: {
      ...state.notes,
      status: "error",
      error: errorMessage(error),
    },
  };
}

export function setNotesStatusFilter(state, statusFilter) {
  return {
    ...state,
    notes: {
      ...state.notes,
      status: "idle",
      statusFilter,
      notes: [],
      next_note_id: null,
      selectedNoteId: null,
      detail: {
        status: "idle",
        note: null,
        events: [],
        error: null,
      },
      error: null,
    },
  };
}

export function beginNoteDetailLoad(state, noteId) {
  return {
    ...state,
    notes: {
      ...state.notes,
      selectedNoteId: noteId,
      detail: {
        status: "loading",
        note: null,
        events: [],
        error: null,
      },
      error: null,
    },
  };
}

export function completeNoteDetailLoad(state, response) {
  return {
    ...state,
    notes: {
      ...state.notes,
      selectedNoteId: response.note?.note_id ?? state.notes.selectedNoteId,
      detail: {
        status: "ready",
        note: response.note ?? null,
        events: Array.isArray(response.events) ? response.events : [],
        error: null,
      },
    },
  };
}

export function failNoteDetailLoad(state, error) {
  return {
    ...state,
    notes: {
      ...state.notes,
      detail: {
        ...state.notes.detail,
        status: "error",
        error: errorMessage(error),
      },
    },
  };
}

export function beginNoteRequest(state, requestId) {
  return {
    ...state,
    notes: {
      ...state.notes,
      pendingRequest: requestId,
      error: null,
    },
  };
}

export function completeNoteRequest(state) {
  return {
    ...state,
    notes: {
      ...state.notes,
      pendingRequest: null,
      error: null,
    },
  };
}

export function failNoteRequest(state, error) {
  return {
    ...state,
    notes: {
      ...state.notes,
      pendingRequest: null,
      error: errorMessage(error),
    },
  };
}

export function storePendingNoteProposal(state, proposal) {
  return {
    ...state,
    notes: storeOnePendingNoteProposal(state.notes, proposal),
  };
}

function storePendingNoteProposalsFromResponse(notes, response) {
  const proposals = Array.isArray(response.collaborative_note_proposals)
    ? response.collaborative_note_proposals
    : [];
  const resolvedProposalIds = new Set(
    (Array.isArray(response.collaborative_note_events)
      ? response.collaborative_note_events
      : [])
      .map((event) => event?.proposal_id)
      .filter((proposalId) => typeof proposalId === "string" && proposalId),
  );
  const reconciledNotes = resolvedProposalIds.size === 0
    ? notes
    : {
      ...notes,
      pendingProposals: notes.pendingProposals.filter((proposal) => (
        !resolvedProposalIds.has(proposal.proposal_id)
      )),
    };
  return proposals.reduce(storeOnePendingNoteProposal, reconciledNotes);
}

function storeOnePendingNoteProposal(notes, proposal) {
  if (!proposal || typeof proposal !== "object" || !proposal.proposal_id) {
    return notes;
  }
  return {
    ...notes,
    pendingProposals: [
      proposal,
      ...notes.pendingProposals.filter((item) => (
        item.proposal_id !== proposal.proposal_id
      )),
    ].slice(0, 20),
  };
}

export function selectFirstSupportedArtifact(response) {
  const artifacts = Array.isArray(response.artifacts) ? response.artifacts : [];
  return artifacts.find((artifact) => (
    (
      (
        artifact.artifact_type === "synthesis_blueprint"
        && artifact.schema_version === "2.0"
      )
      || (
        artifact.artifact_type === "single_file_artifact"
        && artifact.schema_version === "1.0"
      )
    )
    && typeof artifact.artifact_id === "string"
  )) ?? null;
}

export function selectWorkRefreshPlan(response) {
  const artifact = selectFirstSupportedArtifact(response);
  const feedback = (
    Array.isArray(response.artifact_feedback)
    && response.artifact_feedback.length > 0
  )
    ? response.artifact_feedback[0]
    : null;
  return {
    reloadList: artifact !== null || feedback !== null,
    selectArtifactId: artifact?.artifact_id ?? feedback?.artifact_id ?? null,
    reloadSelectedFeedback: feedback !== null,
  };
}
