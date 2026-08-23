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
  if (input.memory_decision && input.artifact_feedback_decision) {
    throw new Error(
      "Structured memory and artifact decisions are mutually exclusive.",
    );
  }
  if (input.memory_decision) {
    body.memory_decision = input.memory_decision;
  }
  if (input.artifact_feedback_decision) {
    body.artifact_feedback_decision = input.artifact_feedback_decision;
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
