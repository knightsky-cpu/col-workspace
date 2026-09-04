const IDENTIFIER_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const ARTIFACT_FEEDBACK_DECISIONS = new Set([
  "accepted",
  "rejected",
  "edited",
]);
const MEMORY_DECISIONS = new Set(["approve", "reject"]);
const CONTINUITY_SOURCE_KINDS = new Set(["collaborative_note", "chat_session"]);

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
  const structuredDecisionCount = [
    input.memory_decision,
    input.artifact_feedback_decision,
    input.memory_clarification_selection,
    input.collaborative_note_decision,
    input.continuity_selection,
  ].filter(Boolean).length;
  if (structuredDecisionCount > 1) {
    throw new Error(
      "Structured memory, artifact, note, and clarification decisions are mutually exclusive.",
    );
  }
  if (input.memory_decision) {
    body.memory_decision = input.memory_decision;
  }
  if (input.artifact_feedback_decision) {
    body.artifact_feedback_decision = input.artifact_feedback_decision;
  }
  if (input.memory_clarification_selection) {
    body.memory_clarification_selection = input.memory_clarification_selection;
  }
  if (input.collaborative_note_decision) {
    body.collaborative_note_decision = input.collaborative_note_decision;
  }
  if (input.continuity_selection) {
    body.continuity_selection = input.continuity_selection;
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
  const body = request?.body ?? {};
  const structuredFields = [
    "artifact_feedback_decision",
  ];
  return structuredFields.some((field) => body[field] != null)
    ? "/api/chat"
    : "/api/chat/stream";
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

export function buildCollaborativeNoteDecisionChatRequest(
  context,
  message,
  decision,
  cryptoLike = globalThis.crypto,
) {
  const noteDecision = {
    proposal_id: String(decision.proposal_id ?? "").trim(),
    decision: String(decision.decision ?? "").trim(),
  };

  if (!isValidIdentifier(noteDecision.proposal_id)) {
    throw new Error("proposal_id is invalid.");
  }
  if (!MEMORY_DECISIONS.has(noteDecision.decision)) {
    throw new Error("Collaborative note decision is invalid.");
  }

  return buildChatRequest({
    project_id: context.project_id,
    session_id: context.session_id,
    user_id: context.user_id,
    message,
    collaborative_note_decision: noteDecision,
    crypto: cryptoLike,
  });
}

export function buildContinuitySelectionChatRequest(
  context,
  choice,
  cryptoLike = globalThis.crypto,
) {
  const selection = {
    choice_id: String(choice.choice_id ?? "").trim(),
    source_kind: String(choice.source_kind ?? "").trim(),
    source_id: String(choice.source_id ?? "").trim(),
  };
  const label = String(choice.display_label ?? "").trim();

  if (!isValidIdentifier(selection.choice_id)) {
    throw new Error("choice_id is invalid.");
  }
  if (!CONTINUITY_SOURCE_KINDS.has(selection.source_kind)) {
    throw new Error("Continuity source kind is invalid.");
  }
  if (!isValidIdentifier(selection.source_id)) {
    throw new Error("source_id is invalid.");
  }
  if (!label) {
    throw new Error("choice label is required.");
  }

  return buildChatRequest({
    project_id: context.project_id,
    session_id: context.session_id,
    user_id: context.user_id,
    message: `Use note: ${label}.`,
    continuity_selection: selection,
    crypto: cryptoLike,
  });
}

export function buildMemoryClarificationSelectionChatRequest(
  context,
  choice,
  cryptoLike = globalThis.crypto,
) {
  const clarificationId = String(choice.clarification_id ?? "").trim();
  const candidateIndex = choice.candidate_index;
  const categoryLabel = String(choice.category_label ?? "").trim();
  const valueLabel = String(choice.value_label ?? "").trim();

  if (!isValidIdentifier(clarificationId)) {
    throw new Error("clarification_id is invalid.");
  }
  if (
    typeof candidateIndex !== "number"
    || !Number.isInteger(candidateIndex)
    || candidateIndex < 0
    || candidateIndex > 4
  ) {
    throw new Error("candidate index is invalid.");
  }
  if (!categoryLabel || !valueLabel) {
    throw new Error("choice label is required.");
  }

  return buildChatRequest({
    project_id: context.project_id,
    session_id: context.session_id,
    user_id: context.user_id,
    message: `Select ${categoryLabel}: ${valueLabel}.`,
    memory_clarification_selection: {
      clarification_id: clarificationId,
      selected_candidate_index: candidateIndex,
    },
    crypto: cryptoLike,
  });
}
