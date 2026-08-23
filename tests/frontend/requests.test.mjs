import test from "node:test";
import assert from "node:assert/strict";

import {
  buildChatRequest,
  buildExactRetryRequest,
  buildOrdinaryChatRequest,
  generateIdempotencyKey,
  generateSessionId,
  isValidIdentifier,
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
