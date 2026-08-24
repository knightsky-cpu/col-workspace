import { generateSessionId } from "./requests.mjs";

export function createInitialState() {
  return {
    mode: "context",
    context: null,
    transcript: [],
    pendingTurn: null,
    lastFailure: null,
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
  };
}

export function acceptContext(state, context) {
  return {
    ...state,
    mode: "workspace",
    context: {
      user_id: context.user_id,
      project_id: context.project_id,
      session_id: generateSessionId(context.crypto),
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
    artifact.artifact_type === "synthesis_blueprint"
    && artifact.schema_version === "2.0"
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
