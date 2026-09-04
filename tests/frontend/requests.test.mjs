import test from "node:test";
import assert from "node:assert/strict";

import {
  buildChatRequest,
  buildExactRetryRequest,
  buildOrdinaryChatRequest,
  generateIdempotencyKey,
  generateSessionId,
  isValidIdentifier,
  readContextForm,
  selectChatEndpoint,
} from "../../frontend/requests.mjs";
import * as requestExports from "../../frontend/requests.mjs";

const cryptoStub = {
  randomUUID() {
    return "123e4567-e89b-12d3-a456-426614174000";
  },
};

test("structured chat resource builders are not exported", () => {
  for (const name of [
    "buildArtifactFeedbackChatRequest",
    "buildMemoryDecisionChatRequest",
    "buildMemoryClarificationSelectionChatRequest",
    "buildCollaborativeNoteDecisionChatRequest",
    "buildContinuitySelectionChatRequest",
  ]) {
    assert.equal(Object.hasOwn(requestExports, name), false);
  }
});

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

test("chat request construction rejects retired structured resource payloads", () => {
  for (const field of [
    "artifact_feedback_decision",
    "memory_decision",
    "memory_clarification_selection",
    "collaborative_note_decision",
    "continuity_selection",
  ]) {
    assert.throws(
      () => buildChatRequest({
        project_id: "agent-col",
        session_id: "session-1",
        user_id: "wifiknight",
        message: "structured decision",
        [field]: {},
        crypto: cryptoStub,
      }),
      /Structured chat resource decisions must use direct resource APIs/,
    );
  }
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

});

test("ordinary multi-intent request does not inherit stale continuity payload", () => {
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

  assert.equal(ordinary.body.message, message);
  assert.equal(ordinary.body.continuity_selection, undefined);
  assert.equal(selectChatEndpoint(ordinary), "/api/chat/stream");
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
