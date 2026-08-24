import test from "node:test";
import assert from "node:assert/strict";

import {
  acceptContext,
  beginChatSessionDetailLoad,
  beginChatSessionListLoad,
  beginWorkDetailLoad,
  beginWorkListLoad,
  beginMemoryLoad,
  beginPendingTurn,
  completeWorkDetailLoad,
  completeWorkListLoad,
  completeMemoryLoad,
  completePendingTurn,
  completeChatSessionDetailLoad,
  completeChatSessionListLoad,
  createInitialState,
  failWorkDetailLoad,
  failWorkListLoad,
  failMemoryLoad,
  failPendingTurn,
  failChatSessionDetailLoad,
  failChatSessionListLoad,
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

test("acceptContext stores verified auth token separately from request locators", () => {
  const state = acceptContext(
    createInitialState(),
    {
      user_id: "google--109876543210",
      project_id: "agent-col",
      auth_token: "google-id-token",
      crypto: cryptoStub,
    },
  );

  assert.equal(state.context.user_id, "google--109876543210");
  assert.equal(state.context.auth_token, "google-id-token");
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
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const request = Object.freeze({
    key: "chat--1",
    body: Object.freeze({ message: "hello" }),
  });
  const pending = beginPendingTurn(accepted, request);
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
  assert.equal(
    completed.chats.selectedSessionId,
    "session--123e4567-e89b-12d3-a456-426614174000",
  );
});

test("completed turn projects authoritative receipts into activity", () => {
  const request = Object.freeze({
    key: "chat--1",
    body: Object.freeze({ message: "create and remember" }),
  });
  const pending = beginPendingTurn(createInitialState(), request);
  const completed = completePendingTurn(
    pending,
    {
      response: "ok",
      actions: [{ action_name: "synthesize_project", status: "completed" }],
      citations: [{ label: "Example Domain", uri: "https://example.com/" }],
      artifacts: [{
        artifact_id: "blueprint--1",
        display_label: "Blueprint",
      }],
      artifact_feedback: [{
        feedback_id: "feedback--1",
        decision: "accepted",
      }],
      memory_proposals: [{
        proposal_id: "preferred_name--proposal-1",
        category: "preferred_name",
      }],
      adaptations: [{
        signal_id: "preferred_name--signal-1",
        category: "preferred_name",
      }],
    },
  );

  assert.deepEqual(
    completed.activity.entries.map((entry) => entry.kind),
    ["action", "citation", "work", "feedback", "memory", "adaptation"],
  );
  assert.equal(completed.activity.entries[0].label, "synthesize_project");
  assert.equal(completed.activity.entries[2].detail, "blueprint--1");
  assert.equal(completed.activity.entries[5].detail, "preferred_name--signal-1");
});

test("failed turns add a bounded error activity entry", () => {
  const request = Object.freeze({
    key: "chat--1",
    body: Object.freeze({ message: "hello" }),
  });
  const failed = failPendingTurn(
    beginPendingTurn(createInitialState(), request),
    { message: "network failed", status: 0 },
  );

  assert.equal(failed.activity.entries.length, 1);
  assert.equal(failed.activity.entries[0].kind, "error");
  assert.equal(failed.activity.entries[0].label, "Request failed");
  assert.equal(failed.activity.entries[0].detail, "network failed");
});

test("timeout failures preserve retry envelope and add timeout activity", () => {
  const request = Object.freeze({
    key: "chat--timeout",
    body: Object.freeze({
      message: "can you write me a python secrets password script?",
    }),
  });
  const error = Object.freeze({
    message: "Agent Col timed out before completing this response. No completed action was recorded.",
    status: 504,
    retryAfterSeconds: null,
  });

  const failed = failPendingTurn(
    beginPendingTurn(createInitialState(), request),
    error,
  );

  assert.equal(failed.pendingTurn, null);
  assert.equal(failed.lastFailure.request, request);
  assert.equal(failed.lastFailure.status, 504);
  assert.equal(failed.lastFailure.message, error.message);
  assert.equal(failed.activity.entries.length, 1);
  assert.equal(failed.activity.entries[0].kind, "error");
  assert.equal(failed.activity.entries[0].label, "Timed out");
  assert.equal(failed.activity.entries[0].detail, error.message);
});

test("activity projection tolerates malformed receipt entries", () => {
  const request = Object.freeze({
    key: "chat--1",
    body: Object.freeze({ message: "hello" }),
  });

  const completed = completePendingTurn(
    beginPendingTurn(createInitialState(), request),
    {
      response: "ok",
      actions: [null],
      citations: [null],
      artifacts: [null],
      artifact_feedback: [null],
      memory_proposals: [null],
      adaptations: [null],
    },
  );

  assert.deepEqual(
    completed.activity.entries.map((entry) => entry.label),
    [
      "Action",
      "Citation",
      "Artifact",
      "Feedback",
      "Memory proposal",
      "Adaptation",
    ],
  );
});

test("new conversation preserves activity because it is workspace scoped", () => {
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const withActivity = completePendingTurn(
    beginPendingTurn(accepted, {
      key: "chat--1",
      body: { message: "hello" },
    }),
    {
      response: "ok",
      actions: [{ action_name: "propose_memory_signal", status: "completed" }],
    },
  );

  const next = startNewConversation(withActivity, cryptoStub);

  assert.equal(next.transcript.length, 0);
  assert.equal(next.activity.entries[0].label, "propose_memory_signal");
});

test("chat session list load stores bounded session summaries", () => {
  const state = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );

  const loaded = completeChatSessionListLoad(
    beginChatSessionListLoad(state),
    {
      chat_contract_version: "1.0",
      sessions: [
        {
          session_id: "session--1",
          project_id: "agent-col",
          user_id: "wifiknight",
          last_message_preview: "hello world",
          last_message_role: "user",
          updated_at: "2026-08-24T10:00:00Z",
        },
      ],
    },
  );

  assert.equal(loaded.chats.status, "loaded");
  assert.equal(loaded.chats.sessions.length, 1);
  assert.equal(loaded.chats.sessions[0].session_id, "session--1");
});

test("chat session detail load switches context and rebuilds transcript", () => {
  const state = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );

  const loaded = completeChatSessionDetailLoad(
    beginChatSessionDetailLoad(state, "session--old"),
    {
      chat_contract_version: "1.0",
      session_id: "session--old",
      project_id: "agent-col",
      user_id: "wifiknight",
      messages: [
        {
          message_id: "message--1",
          role: "user",
          text: "hello",
          timestamp: "2026-08-24T10:00:00Z",
        },
        {
          message_id: "message--2",
          role: "model",
          text: "hi",
          timestamp: "2026-08-24T10:00:01Z",
        },
      ],
    },
  );

  assert.equal(loaded.context.session_id, "session--old");
  assert.equal(loaded.chats.selectedSessionId, "session--old");
  assert.equal(loaded.transcript.length, 1);
  assert.equal(loaded.transcript[0].request.body.message, "hello");
  assert.equal(loaded.transcript[0].response.response, "hi");
});

test("chat session load failures are bounded in state", () => {
  const state = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );

  const listFailed = failChatSessionListLoad(
    beginChatSessionListLoad(state),
    new Error("list failed"),
  );
  const detailFailed = failChatSessionDetailLoad(
    beginChatSessionDetailLoad(listFailed, "session--old"),
    new Error("detail failed"),
  );

  assert.equal(listFailed.chats.status, "error");
  assert.equal(listFailed.chats.error, "list failed");
  assert.equal(detailFailed.chats.detailStatus, "error");
  assert.equal(detailFailed.chats.error, "detail failed");
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

test("memory lifecycle stores profile, unresolved proposals, events, and cursor", () => {
  const loading = beginMemoryLoad(createInitialState());
  assert.equal(loading.memory.status, "loading");

  const completed = completeMemoryLoad(loading, {
    profile: {
      memory_schema_version: "1.0",
      memory_revision: 1,
      identity_context: {},
      active_preferences: {
        response_length: {
          signal_id: "response_length--signal-1",
          value: "concise",
        },
      },
    },
    unresolved_proposals: [
      {
        proposal_id: "response_length--proposal-1",
        category: "response_length",
        proposed_value: "concise",
        status: "pending",
      },
    ],
    events: [
      {
        event_id: "response_length--signal-1--approved",
        event_type: "approved",
        category: "response_length",
        value: "concise",
      },
    ],
    next_event_id: "response_length--signal-1--approved",
  });

  assert.equal(completed.memory.status, "ready");
  assert.equal(
    completed.memory.profile.active_preferences.response_length.value,
    "concise",
  );
  assert.equal(
    completed.memory.unresolvedProposals[0].proposal_id,
    "response_length--proposal-1",
  );
  assert.equal(
    completed.memory.events[0].event_id,
    "response_length--signal-1--approved",
  );
  assert.equal(
    completed.memory.next_event_id,
    "response_length--signal-1--approved",
  );
});

test("memory load failures store safe error messages", () => {
  assert.equal(
    failMemoryLoad(
      beginMemoryLoad(createInitialState()),
      { message: "memory unavailable" },
    ).memory.error,
    "memory unavailable",
  );
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
