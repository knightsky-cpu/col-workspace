import { generateSessionId } from "./requests.mjs";

export function createInitialState() {
  return {
    mode: "context",
    context: null,
    transcript: [],
    pendingTurn: null,
    lastFailure: null,
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
