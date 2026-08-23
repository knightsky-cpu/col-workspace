import test from "node:test";
import assert from "node:assert/strict";

import {
  acceptContext,
  beginWorkDetailLoad,
  beginWorkListLoad,
  beginPendingTurn,
  completeWorkDetailLoad,
  completeWorkListLoad,
  completePendingTurn,
  createInitialState,
  failWorkDetailLoad,
  failWorkListLoad,
  failPendingTurn,
  selectCanSubmit,
  selectFirstSupportedArtifact,
  selectNeedsReceiptRefresh,
  selectWorkRefreshPlan,
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

test("selectCanSubmit requires workspace context and no pending turn", () => {
  assert.equal(selectCanSubmit(createInitialState()), false);
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  assert.equal(selectCanSubmit(accepted), true);
  assert.equal(
    selectCanSubmit(beginPendingTurn(accepted, {
      key: "chat--1",
      body: { message: "hello" },
    })),
    false,
  );
});

test("receipt refresh selector is driven by structured fields", () => {
  assert.deepEqual(
    selectNeedsReceiptRefresh({
      response: "Created.",
      actions: [{ action_name: "synthesize_project", status: "completed" }],
      artifacts: [{ artifact_id: "blueprint--1" }],
      memory_proposals: [{ proposal_id: "response_length--1" }],
      adaptations: [{ signal_id: "planning_granularity--1" }],
    }),
    {
      work: true,
      memory: true,
    },
  );
  assert.deepEqual(
    selectNeedsReceiptRefresh({ response: "I created a blueprint in prose." }),
    {
      work: false,
      memory: false,
    },
  );
});

test("work list lifecycle stores newest-first metadata and cursor", () => {
  const loading = beginWorkListLoad(createInitialState());
  assert.equal(loading.work.list.status, "loading");

  const completed = completeWorkListLoad(loading, {
    artifacts: [
      {
        reference: {
          artifact_type: "synthesis_blueprint",
          artifact_id: "blueprint--abc",
          schema_version: "2.0",
          display_label: "Blueprint",
        },
        created_at: "2026-08-23T00:00:00Z",
        feedback_counts: { accepted: 0, rejected: 0, edited: 0 },
      },
    ],
    next_before: "cursor--1",
  });

  assert.equal(completed.work.list.status, "ready");
  assert.equal(
    completed.work.list.items[0].reference.artifact_id,
    "blueprint--abc",
  );
  assert.equal(completed.work.list.next_before, "cursor--1");
});

test("work detail lifecycle stores canonical detail and feedback history", () => {
  const loading = beginWorkDetailLoad(createInitialState(), "blueprint--abc");
  assert.equal(loading.work.detail.status, "loading");
  assert.equal(loading.work.selectedArtifactId, "blueprint--abc");

  const completed = completeWorkDetailLoad(
    loading,
    {
      metadata: {
        reference: {
          artifact_id: "blueprint--abc",
          schema_version: "2.0",
          display_label: "Blueprint",
        },
      },
      blueprint: {
        synthesized_conceptual_model: { project_name: "Blueprint" },
      },
      feedback_targets: [{ target_id: "target--whole" }],
      adaptations: [],
      applied_feedback_ids: [],
    },
    {
      events: [{ reference: { feedback_id: "feedback--1" }, status: "active" }],
      next_before: null,
    },
  );

  assert.equal(completed.work.detail.status, "ready");
  assert.equal(
    completed.work.detail.item.metadata.reference.artifact_id,
    "blueprint--abc",
  );
  assert.equal(
    completed.work.feedback.events[0].reference.feedback_id,
    "feedback--1",
  );
});

test("work load failures store safe error messages", () => {
  assert.equal(
    failWorkListLoad(
      beginWorkListLoad(createInitialState()),
      { message: "boom" },
    ).work.list.error,
    "boom",
  );
  assert.equal(
    failWorkDetailLoad(
      beginWorkDetailLoad(createInitialState(), "blueprint--abc"),
      { message: "missing" },
    ).work.detail.error,
    "missing",
  );
});

test("receipt refresh plan follows artifact and feedback response fields", () => {
  assert.deepEqual(
    selectFirstSupportedArtifact({
      artifacts: [
        {
          artifact_type: "synthesis_blueprint",
          artifact_id: "blueprint--abc",
          schema_version: "2.0",
        },
      ],
    }),
    {
      artifact_type: "synthesis_blueprint",
      artifact_id: "blueprint--abc",
      schema_version: "2.0",
    },
  );

  assert.deepEqual(
    selectWorkRefreshPlan({
      artifacts: [
        {
          artifact_type: "synthesis_blueprint",
          artifact_id: "blueprint--abc",
          schema_version: "2.0",
        },
      ],
      artifact_feedback: [],
    }),
    {
      reloadList: true,
      selectArtifactId: "blueprint--abc",
      reloadSelectedFeedback: false,
    },
  );

  assert.deepEqual(
    selectWorkRefreshPlan({
      artifact_feedback: [
        {
          artifact_id: "blueprint--abc",
          feedback_id: "feedback--1",
        },
      ],
    }),
    {
      reloadList: true,
      selectArtifactId: "blueprint--abc",
      reloadSelectedFeedback: true,
    },
  );
});

test("new conversation preserves loaded work because artifacts are project scoped", () => {
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const withWork = completeWorkListLoad(beginWorkListLoad(accepted), {
    artifacts: [{
      reference: {
        artifact_id: "blueprint--abc",
        artifact_type: "synthesis_blueprint",
        schema_version: "2.0",
        display_label: "Blueprint",
      },
    }],
    next_before: null,
  });

  const next = startNewConversation(withWork, cryptoStub);

  assert.equal(next.transcript.length, 0);
  assert.equal(next.work.list.items[0].reference.artifact_id, "blueprint--abc");
});
