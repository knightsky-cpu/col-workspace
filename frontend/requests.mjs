const IDENTIFIER_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) {
      deepFreeze(child);
    }
  }
  return value;
}

export function isValidIdentifier(value) {
  return typeof value === "string" && IDENTIFIER_PATTERN.test(value);
}

export function generateSessionId(cryptoLike = globalThis.crypto) {
  return `session--${cryptoLike.randomUUID()}`;
}

export function generateIdempotencyKey(prefix, cryptoLike = globalThis.crypto) {
  if (!isValidIdentifier(prefix)) {
    throw new Error("Idempotency prefix is invalid.");
  }
  return `${prefix}--${cryptoLike.randomUUID()}`;
}

export function readContextForm(formData) {
  const user_id = String(formData.get("user_id") ?? "").trim();
  const project_id = String(formData.get("project_id") ?? "").trim();
  if (formData.has("auth_token")) {
    throw new Error("Raw Google ID tokens must not be entered.");
  }
  if (!isValidIdentifier(user_id)) {
    throw new Error(
      "User ID must use letters, numbers, underscores, or hyphens.",
    );
  }
  if (!isValidIdentifier(project_id)) {
    throw new Error(
      "Project ID must use letters, numbers, underscores, or hyphens.",
    );
  }
  return { user_id, project_id };
}

export function buildChatRequest(input) {
  const body = {
    project_id: input.project_id,
    session_id: input.session_id,
    user_id: input.user_id,
    message: String(input.message ?? ""),
  };

  if (!body.message.trim()) {
    throw new Error("Message is required.");
  }
  for (const key of ["project_id", "session_id", "user_id"]) {
    if (!isValidIdentifier(body[key])) {
      throw new Error(`${key} is invalid.`);
    }
  }
  const hasStructuredResourceDecision = [
    input.memory_decision,
    input.artifact_feedback_decision,
    input.memory_clarification_selection,
    input.collaborative_note_decision,
    input.continuity_selection,
  ].some(Boolean);
  if (hasStructuredResourceDecision) {
    throw new Error(
      "Structured chat resource decisions must use direct resource APIs.",
    );
  }

  return deepFreeze({
    key: generateIdempotencyKey("chat", input.crypto),
    body,
  });
}

export function buildExactRetryRequest(turn) {
  return {
    key: turn.key,
    body: turn.body,
  };
}

export function selectChatEndpoint(request) {
  void request;
  return "/api/chat/stream";
}

export function buildOrdinaryChatRequest(
  context,
  message,
  cryptoLike = globalThis.crypto,
) {
  return buildChatRequest({
    project_id: context.project_id,
    session_id: context.session_id,
    user_id: context.user_id,
    message,
    crypto: cryptoLike,
  });
}
