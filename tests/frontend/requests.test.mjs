import test from "node:test";
import assert from "node:assert/strict";

import {
  buildArtifactFeedbackChatRequest,
  buildChatRequest,
  buildExactRetryRequest,
  buildMemoryClarificationSelectionChatRequest,
  buildMemoryDecisionChatRequest,
  buildCollaborativeNoteDecisionChatRequest,
  buildContinuitySelectionChatRequest,
  buildOrdinaryChatRequest,
  generateIdempotencyKey,
  generateSessionId,
  isValidIdentifier,
  readContextForm,
  selectChatEndpoint,
} from "../../frontend/requests.mjs";

const cryptoStub = {
  randomUUID() {
    return "123e4567-e89b-12d3-a456-426614174000";
  },
};

test("identifier validation mirrors the backend locator shape", () => {
  assert.equal(isValidIdentifier("agent-col"), true);
  assert.equal(isValidIdentifier("wifiknight_01"), true);
  assert.equal(isValidIdentifier(""), false);
  assert.equal(isValidIdentifier("bad id"), false);
  assert.equal(isValidIdentifier("bad/slash"), false);
  assert.equal(isValidIdentifier("x".repeat(129)), false);
});

test("context form rejects raw Google token fields", () => {
  const formData = new FormData();
  formData.set("user_id", "user--fbea9ffc3b3e25366ddfd4fe47be9bc5");
  formData.set("project_id", "agent-col");
  formData.set("auth_token", "  google-id-token  ");

  assert.throws(
    () => readContextForm(formData),
    /Raw Google ID tokens must not be entered/,
  );
});

test("session and idempotency identifiers are generated locally", () => {
  assert.equal(
    generateSessionId(cryptoStub),
    "session--123e4567-e89b-12d3-a456-426614174000",
  );
  assert.equal(
    generateIdempotencyKey("chat", cryptoStub),
    "chat--123e4567-e89b-12d3-a456-426614174000",
  );
});

test("chat request construction freezes exact body and key", () => {
  const request = buildChatRequest({
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
    message: "Hello Agent_Col",
    crypto: cryptoStub,
  });

  assert.equal(request.key, "chat--123e4567-e89b-12d3-a456-426614174000");
  assert.deepEqual(request.body, {
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
    message: "Hello Agent_Col",
  });
  assert.throws(() => {
    request.body.message = "mutated";
  }, TypeError);
});

test("exact retry preserves the original key and body", () => {
  const original = buildChatRequest({
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
    message: "Hello Agent_Col",
    crypto: cryptoStub,
  });

  const retry = buildExactRetryRequest(original);

  assert.equal(retry.key, original.key);
  assert.equal(retry.body, original.body);
});

test("chat endpoint selection streams only ordinary requests", () => {
  const ordinary = buildOrdinaryChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    "Hello Agent Col",
    cryptoStub,
  );
  assert.equal(selectChatEndpoint(ordinary), "/api/chat/stream");
  assert.equal(
    selectChatEndpoint(buildExactRetryRequest(ordinary)),
    "/api/chat/stream",
  );

  for (const field of [
    "memory_decision",
    "memory_clarification_selection",
    "artifact_feedback_decision",
    "collaborative_note_decision",
    "continuity_selection",
  ]) {
    assert.equal(
      selectChatEndpoint({ body: { ...ordinary.body, [field]: {} } }),
      "/api/chat",
    );
  }
});

test("ordinary multi-intent request does not inherit stale continuity payload", () => {
  const staleContinuityChoice = {
    choice_id: "choice-stale",
    source_kind: "collaborative_note",
    source_id: "note-stale",
    display_label: "Old project note",
  };
  const message = [
    "create a workspace note that we are going to build project zero for",
    "macOS and we are using a zsh shell environment.",
    "also remember that i prefer pancakes on saturday mornings for breakfast.",
    "then write me a C program that prints, 'hello! i love pancakes!'",
  ].join(" ");

  const ordinary = buildOrdinaryChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    message,
    cryptoStub,
  );
  const continuitySelection = buildContinuitySelectionChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    staleContinuityChoice,
    cryptoStub,
  );

  assert.equal(ordinary.body.message, message);
  assert.equal(ordinary.body.continuity_selection, undefined);
  assert.equal(selectChatEndpoint(ordinary), "/api/chat/stream");
  assert.equal(selectChatEndpoint(continuitySelection), "/api/chat");
  assert.deepEqual(continuitySelection.body.continuity_selection, {
    choice_id: "choice-stale",
    source_kind: "collaborative_note",
    source_id: "note-stale",
  });
});

test("structured memory and artifact decisions are mutually exclusive", () => {
  assert.throws(
    () => buildChatRequest({
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
      message: "structured decision",
      memory_decision: {
        proposal_id: "response_length--1",
        decision: "approved",
      },
      artifact_feedback_decision: {
        artifact_id: "blueprint--1",
        target_id: "target--1",
        decision: "accepted",
        feedback_text: "accepted",
        expected_schema_version: "2.0",
      },
      crypto: cryptoStub,
    }),
    /mutually exclusive/,
  );
});

test("structured clarification selections are mutually exclusive with other decisions", () => {
  assert.throws(
    () => buildChatRequest({
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
      message: "Select Response length: Detailed.",
      memory_decision: {
        proposal_id: "response_length--proposal-1",
        decision: "approve",
      },
      memory_clarification_selection: {
        clarification_id: "memory-clarification--clarify-1",
        selected_candidate_index: 0,
      },
      crypto: cryptoStub,
    }),
    /mutually exclusive/,
  );
});

test("structured note decisions and continuity selections are mutually exclusive", () => {
  assert.throws(
    () => buildChatRequest({
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
      message: "Use the selected note.",
      collaborative_note_decision: {
        proposal_id: "note-proposal-1",
        decision: "approve",
      },
      continuity_selection: {
        choice_id: "choice-1",
        source_kind: "collaborative_note",
        source_id: "note-1",
      },
      crypto: cryptoStub,
    }),
    /mutually exclusive/,
  );
});

test("ordinary chat request uses context locators and one idempotency key", () => {
  const request = buildOrdinaryChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    "Explain receipt authority.",
    cryptoStub,
  );

  assert.equal(request.key, "chat--123e4567-e89b-12d3-a456-426614174000");
  assert.deepEqual(request.body, {
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
    message: "Explain receipt authority.",
  });
});

test("artifact feedback chat request includes the structured feedback decision", () => {
  const request = buildArtifactFeedbackChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    "I accept this blueprint.",
    {
      artifact_id: "blueprint--abc",
      target_id: "target--whole",
      decision: "accepted",
      feedback_text: "This is useful.",
      expected_schema_version: "2.0",
    },
    cryptoStub,
  );

  assert.equal(request.key, "chat--123e4567-e89b-12d3-a456-426614174000");
  assert.deepEqual(request.body.artifact_feedback_decision, {
    artifact_id: "blueprint--abc",
    target_id: "target--whole",
    decision: "accepted",
    feedback_text: "This is useful.",
    expected_schema_version: "2.0",
  });
  assert.equal(request.body.message, "I accept this blueprint.");
});

test("edited artifact feedback requires correction text", () => {
  assert.throws(
    () => buildArtifactFeedbackChatRequest(
      {
        project_id: "agent-col",
        session_id: "session-1",
        user_id: "wifiknight",
      },
      "I want to edit this target.",
      {
        artifact_id: "blueprint--abc",
        target_id: "target--whole",
        decision: "edited",
        feedback_text: "Needs a correction.",
        expected_schema_version: "2.0",
      },
      cryptoStub,
    ),
    /Correction text is required/,
  );
});

test("artifact feedback can supersede a previous feedback event", () => {
  const request = buildArtifactFeedbackChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    "I am reversing my earlier artifact feedback.",
    {
      artifact_id: "blueprint--abc",
      target_id: "target--whole",
      decision: "rejected",
      feedback_text: "I am reversing the acceptance.",
      expected_schema_version: "2.0",
      supersedes_feedback_id: "feedback--old",
    },
    cryptoStub,
  );

  assert.equal(
    request.body.artifact_feedback_decision.supersedes_feedback_id,
    "feedback--old",
  );
});

test("memory decision chat request includes the structured memory decision", () => {
  const request = buildMemoryDecisionChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    "Approve this memory proposal.",
    {
      proposal_id: "response_length--proposal-1",
      decision: "approve",
    },
    cryptoStub,
  );

  assert.equal(request.key, "chat--123e4567-e89b-12d3-a456-426614174000");
  assert.deepEqual(request.body.memory_decision, {
    proposal_id: "response_length--proposal-1",
    decision: "approve",
  });
  assert.equal(request.body.message, "Approve this memory proposal.");
});

test("memory decision chat request rejects invalid decisions", () => {
  assert.throws(
    () => buildMemoryDecisionChatRequest(
      {
        project_id: "agent-col",
        session_id: "session-1",
        user_id: "wifiknight",
      },
      "Approve this memory proposal.",
      {
        proposal_id: "response_length--proposal-1",
        decision: "approved",
      },
      cryptoStub,
    ),
    /Memory decision is invalid/,
  );
});

test("collaborative note decision chat request includes structured decision", () => {
  const request = buildCollaborativeNoteDecisionChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    "Approve this note proposal.",
    {
      proposal_id: "note-proposal-1",
      decision: "approve",
    },
    cryptoStub,
  );

  assert.equal(request.key, "chat--123e4567-e89b-12d3-a456-426614174000");
  assert.deepEqual(request.body.collaborative_note_decision, {
    proposal_id: "note-proposal-1",
    decision: "approve",
  });
  assert.equal(request.body.message, "Approve this note proposal.");
});

test("continuity selection chat request includes only server-owned source identity", () => {
  const request = buildContinuitySelectionChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    {
      choice_id: "choice-1",
      source_kind: "collaborative_note",
      source_id: "note-1",
      display_label: "API version",
    },
    cryptoStub,
  );

  assert.deepEqual(request.body, {
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
    message: "Use note: API version.",
    continuity_selection: {
      choice_id: "choice-1",
      source_kind: "collaborative_note",
      source_id: "note-1",
    },
  });
  assert.throws(() => {
    request.body.continuity_selection.source_id = "note-2";
  }, TypeError);
});

test("note decision and continuity selection requests validate bounded fields", () => {
  const context = {
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
  };

  assert.throws(
    () => buildCollaborativeNoteDecisionChatRequest(
      context,
      "Approve this note.",
      { proposal_id: "bad/slash", decision: "approve" },
      cryptoStub,
    ),
    /proposal_id is invalid/,
  );
  assert.throws(
    () => buildCollaborativeNoteDecisionChatRequest(
      context,
      "Approve this note.",
      { proposal_id: "note-proposal-1", decision: "approved" },
      cryptoStub,
    ),
    /Collaborative note decision is invalid/,
  );
  assert.throws(
    () => buildContinuitySelectionChatRequest(
      context,
      {
        choice_id: "bad/slash",
        source_kind: "collaborative_note",
        source_id: "note-1",
        display_label: "API version",
      },
      cryptoStub,
    ),
    /choice_id is invalid/,
  );
  assert.throws(
    () => buildContinuitySelectionChatRequest(
      context,
      {
        choice_id: "choice-1",
        source_kind: "memory",
        source_id: "note-1",
        display_label: "API version",
      },
      cryptoStub,
    ),
    /Continuity source kind is invalid/,
  );
});

test("memory clarification selection request includes only server-owned choice identity", () => {
  const request = buildMemoryClarificationSelectionChatRequest(
    {
      project_id: "agent-col",
      session_id: "session-1",
      user_id: "wifiknight",
    },
    {
      clarification_id: "memory-clarification--clarify-1",
      candidate_index: 0,
      category_label: "Response length",
      value_label: "Detailed",
    },
    cryptoStub,
  );

  assert.equal(request.key, "chat--123e4567-e89b-12d3-a456-426614174000");
  assert.deepEqual(request.body, {
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
    message: "Select Response length: Detailed.",
    memory_clarification_selection: {
      clarification_id: "memory-clarification--clarify-1",
      selected_candidate_index: 0,
    },
  });
  assert.throws(() => {
    request.body.memory_clarification_selection.selected_candidate_index = 1;
  }, TypeError);
});

test("memory clarification selection request validates bounded choices before network access", () => {
  const context = {
    project_id: "agent-col",
    session_id: "session-1",
    user_id: "wifiknight",
  };
  const valid = {
    clarification_id: "memory-clarification--clarify-1",
    candidate_index: 0,
    category_label: "Response length",
    value_label: "Detailed",
  };

  assert.throws(
    () => buildMemoryClarificationSelectionChatRequest(
      context,
      { ...valid, clarification_id: "memory clarification 1" },
      cryptoStub,
    ),
    /clarification_id is invalid/,
  );
  assert.throws(
    () => buildMemoryClarificationSelectionChatRequest(
      context,
      { ...valid, candidate_index: true },
      cryptoStub,
    ),
    /candidate index is invalid/,
  );
  assert.throws(
    () => buildMemoryClarificationSelectionChatRequest(
      context,
      { ...valid, candidate_index: 1.5 },
      cryptoStub,
    ),
    /candidate index is invalid/,
  );
  assert.throws(
    () => buildMemoryClarificationSelectionChatRequest(
      context,
      { ...valid, candidate_index: 5 },
      cryptoStub,
    ),
    /candidate index is invalid/,
  );
  assert.throws(
    () => buildMemoryClarificationSelectionChatRequest(
      context,
      { ...valid, value_label: " " },
      cryptoStub,
    ),
    /choice label is required/,
  );
});
