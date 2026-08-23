import test from "node:test";
import assert from "node:assert/strict";

import {
  acceptContext,
  beginPendingTurn,
  completePendingTurn,
  createInitialState,
  failPendingTurn,
  startNewConversation,
} from "../../frontend/state.mjs";

const cryptoStub = {
  randomUUID() {
    return "123e4567-e89b-12d3-a456-426614174000";
  },
};

test("acceptContext stores local locators and creates a session", () => {
  const state = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );

  assert.equal(state.context.user_id, "wifiknight");
  assert.equal(state.context.project_id, "agent-col");
  assert.equal(
    state.context.session_id,
    "session--123e4567-e89b-12d3-a456-426614174000",
  );
  assert.equal(state.mode, "workspace");
});

test("pending turn lifecycle preserves exact retry envelope on failure", () => {
  const request = Object.freeze({
    key: "chat--1",
    body: Object.freeze({ message: "hello" }),
  });
  const pending = beginPendingTurn(createInitialState(), request);
  const failed = failPendingTurn(
    pending,
    { message: "network failed", status: 0 },
  );

  assert.equal(failed.pendingTurn, null);
  assert.equal(failed.lastFailure.request, request);
  assert.equal(failed.lastFailure.message, "network failed");
});

test("completed turn records response and clears pending failure", () => {
  const request = Object.freeze({
    key: "chat--1",
    body: Object.freeze({ message: "hello" }),
  });
  const pending = beginPendingTurn(createInitialState(), request);
  const completed = completePendingTurn(
    pending,
    { response: "ok", actions: [] },
  );

  assert.equal(completed.pendingTurn, null);
  assert.equal(completed.lastFailure, null);
  assert.equal(completed.transcript.length, 1);
  assert.deepEqual(
    completed.transcript[0].response,
    { response: "ok", actions: [] },
  );
});

test("new conversation keeps user and project but replaces session and clears page state", () => {
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const withTranscript = completePendingTurn(
    beginPendingTurn(
      accepted,
      { key: "chat--1", body: { message: "hello" } },
    ),
    { response: "ok" },
  );

  const next = startNewConversation(withTranscript, cryptoStub);

  assert.equal(next.context.user_id, "wifiknight");
  assert.equal(next.context.project_id, "agent-col");
  assert.equal(next.transcript.length, 0);
  assert.equal(next.lastFailure, null);
});
