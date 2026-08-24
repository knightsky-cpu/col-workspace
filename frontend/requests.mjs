const IDENTIFIER_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const ARTIFACT_FEEDBACK_DECISIONS = new Set([
  "accepted",
  "rejected",
  "edited",
]);
const MEMORY_DECISIONS = new Set(["approve", "reject"]);

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
  const auth_token = String(formData.get("auth_token") ?? "").trim();
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
  return auth_token
    ? { user_id, project_id, auth_token }
    : { user_id, project_id };
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

function normalizeOptionalText(value) {
  if (value === undefined || value === null) {
    return undefined;
  }
  const text = String(value).trim();
  return text ? text : undefined;
}

export function buildArtifactFeedbackChatRequest(
  context,
  message,
  decision,
  cryptoLike = globalThis.crypto,
) {
  const artifactDecision = {
    artifact_id: String(decision.artifact_id ?? "").trim(),
    target_id: String(decision.target_id ?? "").trim(),
    decision: String(decision.decision ?? "").trim(),
    feedback_text: String(decision.feedback_text ?? "").trim(),
    expected_schema_version: String(
      decision.expected_schema_version ?? "2.0",
    ).trim(),
  };

  const correctionText = normalizeOptionalText(decision.correction_text);
  const supersedesFeedbackId = normalizeOptionalText(
    decision.supersedes_feedback_id,
  );

  if (!isValidIdentifier(artifactDecision.artifact_id)) {
    throw new Error("artifact_id is invalid.");
  }
  if (!isValidIdentifier(artifactDecision.target_id)) {
    throw new Error("target_id is invalid.");
  }
  if (!ARTIFACT_FEEDBACK_DECISIONS.has(artifactDecision.decision)) {
    throw new Error("Artifact feedback decision is invalid.");
  }
  if (!artifactDecision.feedback_text) {
    throw new Error("Feedback text is required.");
  }
  if (
    artifactDecision.decision === "edited"
    && correctionText === undefined
  ) {
    throw new Error("Correction text is required for edited feedback.");
  }
  if (correctionText !== undefined) {
    artifactDecision.correction_text = correctionText;
  }
  if (supersedesFeedbackId !== undefined) {
    if (!isValidIdentifier(supersedesFeedbackId)) {
      throw new Error("supersedes_feedback_id is invalid.");
    }
    artifactDecision.supersedes_feedback_id = supersedesFeedbackId;
  }

  return buildChatRequest({
    project_id: context.project_id,
    session_id: context.session_id,
    user_id: context.user_id,
    message,
    artifact_feedback_decision: artifactDecision,
    crypto: cryptoLike,
  });
}

export function buildMemoryDecisionChatRequest(
  context,
  message,
  decision,
  cryptoLike = globalThis.crypto,
) {
  const memoryDecision = {
    proposal_id: String(decision.proposal_id ?? "").trim(),
    decision: String(decision.decision ?? "").trim(),
  };

  if (!isValidIdentifier(memoryDecision.proposal_id)) {
    throw new Error("proposal_id is invalid.");
  }
  if (!MEMORY_DECISIONS.has(memoryDecision.decision)) {
    throw new Error("Memory decision is invalid.");
  }

  return buildChatRequest({
    project_id: context.project_id,
    session_id: context.session_id,
    user_id: context.user_id,
    message,
    memory_decision: memoryDecision,
    crypto: cryptoLike,
  });
}
