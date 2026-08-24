import { generateSessionId } from "./requests.mjs";

export function createInitialState() {
  return {
    mode: "context",
    context: null,
    transcript: [],
    pendingTurn: null,
    lastFailure: null,
    workspaces: {
      status: "idle",
      items: [],
      selectedWorkspaceId: null,
      error: null,
    },
    work: {
      list: {
        status: "idle",
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

export function completeWorkspaceListLoad(state, response) {
  const items = Array.isArray(response.workspaces) ? response.workspaces : [];
  return {
    ...state,
    workspaces: {
      ...state.workspaces,
      status: "ready",
      items,
      selectedWorkspaceId: (
        state.workspaces.selectedWorkspaceId
        ?? state.context?.project_id
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
    lastFailure: null,
    work: emptyWorkState(),
    chats: emptyChatSessionState(),
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

export function beginPendingTurn(state, request) {
  if (state.pendingTurn !== null) {
    throw new Error("A turn is already pending.");
  }
  return {
    ...state,
    pendingTurn: request,
    lastFailure: null,
  };
}

export function failPendingTurn(state, error) {
  return {
    ...state,
    lastFailure: {
      request: state.pendingTurn,
      message: error.message,
      status: error.status ?? null,
      retryAfterSeconds: error.retryAfterSeconds ?? null,
    },
    activity: appendActivityEntries(state.activity, [{
      kind: "error",
      label: errorActivityLabel(error),
      detail: errorMessage(error),
    }]),
    pendingTurn: null,
  };
}

export function completePendingTurn(state, response) {
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
    lastFailure: null,
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
    lastFailure: null,
    chats: {
      ...state.chats,
      selectedSessionId: null,
      detailStatus: "idle",
      error: null,
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
    lastFailure: null,
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
  return (
    state.mode === "workspace"
    && state.context !== null
    && state.pendingTurn === null
  );
}

export function selectNeedsReceiptRefresh(response) {
  const actions = Array.isArray(response.actions) ? response.actions : [];
  return {
    work: Array.isArray(response.artifacts) && response.artifacts.length > 0,
    memory: (
      (
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
      detail: artifact.artifact_id ?? "",
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
      detail: feedback.feedback_id ?? "",
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
      detail: proposal.proposal_id ?? "",
    });
  }
  for (const rawAdaptation of Array.isArray(response.adaptations) ? response.adaptations : []) {
    const adaptation = objectOrEmpty(rawAdaptation);
    entries.push({
      kind: "adaptation",
      label: adaptation.category ?? "Adaptation",
      detail: adaptation.signal_id ?? "",
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

export function completeWorkListLoad(state, response) {
  return {
    ...state,
    work: {
      ...state.work,
      list: {
        status: "ready",
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
