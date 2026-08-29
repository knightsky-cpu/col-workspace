import test from "node:test";
import assert from "node:assert/strict";

import {
  acceptContext,
  appendPendingResponseDelta,
  beginWorkspaceListLoad,
  beginChatSessionDetailLoad,
  beginChatSessionListLoad,
  beginNoteDetailLoad,
  beginNotesLoad,
  beginWorkDetailLoad,
  beginWorkListLoad,
  beginMemoryLoad,
  beginPendingTurn,
  completeWorkDetailLoad,
  completeWorkMetadataUpdate,
  completeWorkVersionCreate,
  completeWorkArchive,
  completeWorkDelete,
  completeWorkRestore,
  completeWorkspaceCreate,
  completeWorkspaceDelete,
  completeWorkspaceListLoad,
  completeWorkListLoad,
  completeMemoryLoad,
  completeMemorySignalMutation,
  completeNoteDetailLoad,
  completeNotesLoad,
  completePendingTurn,
  completeChatSessionDetailLoad,
  completeChatSessionListLoad,
  createInitialState,
  expandChatDisclosure,
  expandNoteDetailDisclosure,
  failWorkDetailLoad,
  failWorkspaceListLoad,
  failWorkListLoad,
  failMemoryLoad,
  failPendingTurn,
  failChatSessionDetailLoad,
  failChatSessionListLoad,
  selectCanSubmit,
  selectFirstSupportedArtifact,
  selectNeedsReceiptRefresh,
  selectWorkRefreshPlan,
  selectWorkspace,
  setWorkLifecycleStatus,
  storePendingNoteProposal,
  startNewConversation,
  toggleArtifactDisclosure,
  toggleChatDisclosure,
  toggleMemoryDisclosure,
  toggleNoteDetailDisclosure,
  toggleNoteProposalDisclosure,
} from "../../frontend/state.mjs";

const cryptoStub = {
  randomUUID() {
    return "123e4567-e89b-12d3-a456-426614174000";
  },
};

function clarificationReceipt() {
  return {
    clarification_id: "memory-clarification--clarify-1",
    expires_at: "2026-08-25T12:00:00Z",
    choices: [
      {
        candidate_index: 0,
        category_label: "Response length",
        value_label: "Detailed",
      },
      {
        candidate_index: 1,
        category_label: "Explanation structure",
        value_label: "Step by step",
      },
    ],
  };
}

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

test("initial subcard disclosure state is empty and toggles stable child ids", () => {
  const initial = createInitialState();
  assert.deepEqual(initial.disclosure, {
    notes: { proposalIds: [], detailNoteIds: [] },
    memory: { proposalIds: [], signalIds: [] },
    chats: { sessionIds: [] },
    work: { artifactIds: [] },
  });

  const withNoteProposal = toggleNoteProposalDisclosure(initial, "proposal-1");
  assert.deepEqual(withNoteProposal.disclosure.notes.proposalIds, ["proposal-1"]);
  assert.deepEqual(
    toggleNoteProposalDisclosure(withNoteProposal, "proposal-1")
      .disclosure.notes.proposalIds,
    [],
  );

  const withNoteDetail = toggleNoteDetailDisclosure(initial, "note-1");
  assert.deepEqual(withNoteDetail.disclosure.notes.detailNoteIds, ["note-1"]);
  const expandedNoteDetail = expandNoteDetailDisclosure(initial, "note-1");
  assert.deepEqual(expandedNoteDetail.disclosure.notes.detailNoteIds, ["note-1"]);
  assert.deepEqual(
    expandNoteDetailDisclosure(expandedNoteDetail, "note-1")
      .disclosure.notes.detailNoteIds,
    ["note-1"],
  );
  const withMemoryProposal = toggleMemoryDisclosure(initial, "proposal-1", "proposal");
  assert.deepEqual(withMemoryProposal.disclosure.memory.proposalIds, ["proposal-1"]);
  const withSignal = toggleMemoryDisclosure(initial, "signal-1", "signal");
  assert.deepEqual(withSignal.disclosure.memory.signalIds, ["signal-1"]);
  const withChat = toggleChatDisclosure(initial, "session-1");
  assert.deepEqual(withChat.disclosure.chats.sessionIds, ["session-1"]);
  const withArtifact = toggleArtifactDisclosure(initial, "artifact--1");
  assert.deepEqual(withArtifact.disclosure.work.artifactIds, ["artifact--1"]);
  assert.deepEqual(
    toggleArtifactDisclosure(withArtifact, "artifact--1")
      .disclosure.work.artifactIds,
    [],
  );
  const expandedChat = expandChatDisclosure(initial, "session-1");
  assert.deepEqual(expandedChat.disclosure.chats.sessionIds, ["session-1"]);
  assert.deepEqual(
    expandChatDisclosure(expandedChat, "session-1").disclosure.chats.sessionIds,
    ["session-1"],
  );
});

test("acceptContext stores verified auth token separately from request locators", () => {
  const state = acceptContext(
    createInitialState(),
    {
      user_id: "user--fbea9ffc3b3e25366ddfd4fe47be9bc5",
      project_id: "agent-col",
      auth_token: "google-id-token",
      crypto: cryptoStub,
    },
  );

  assert.equal(
    state.context.user_id,
    "user--fbea9ffc3b3e25366ddfd4fe47be9bc5",
  );
  assert.equal(state.context.auth_token, "google-id-token");
});

test("workspace list lifecycle stores selectable user containers", () => {
  const loading = beginWorkspaceListLoad(createInitialState());
  assert.equal(loading.workspaces.status, "loading");

  const loaded = completeWorkspaceListLoad(loading, {
    workspace_contract_version: "1.0",
    workspaces: [{
      workspace_id: "agent-col",
      display_name: "Agent Col",
      is_default: true,
    }],
  });

  assert.equal(loaded.workspaces.status, "ready");
  assert.equal(loaded.workspaces.items[0].display_name, "Agent Col");
  assert.equal(
    failWorkspaceListLoad(loading, { message: "workspace unavailable" })
      .workspaces.error,
    "workspace unavailable",
  );
});

test("workspace list load selects first visible workspace when seeded context is hidden", () => {
  const state = acceptContext(
    createInitialState(),
    {
      user_id: "google--user",
      project_id: "project--deleted-default",
      crypto: cryptoStub,
    },
  );
  const populated = {
    ...state,
    transcript: [{ request: {}, response: {} }],
    activeMemoryClarification: clarificationReceipt(),
    work: {
      ...state.work,
      list: {
        status: "ready",
        items: [{ reference: { artifact_id: "artifact--stale" } }],
        next_before: null,
        error: null,
      },
    },
    chats: {
      ...state.chats,
      sessions: [{ session_id: "session--stale" }],
    },
  };

  const loaded = completeWorkspaceListLoad(populated, {
    workspace_contract_version: "1.0",
    workspaces: [
      {
        workspace_id: "project--visible-one",
        display_name: "Visible One",
        is_default: false,
      },
      {
        workspace_id: "project--visible-two",
        display_name: "Visible Two",
        is_default: false,
      },
    ],
  }, cryptoStub);

  assert.equal(loaded.context.project_id, "project--visible-one");
  assert.equal(loaded.context.session_id, "session--123e4567-e89b-12d3-a456-426614174000");
  assert.equal(loaded.workspaces.selectedWorkspaceId, "project--visible-one");
  assert.equal(loaded.transcript.length, 0);
  assert.equal(loaded.work.list.items.length, 0);
  assert.equal(loaded.chats.sessions.length, 0);
});

test("workspace list load preserves a visible selected workspace", () => {
  const state = acceptContext(
    createInitialState(),
    {
      user_id: "google--user",
      project_id: "project--visible-two",
      crypto: cryptoStub,
    },
  );

  const loaded = completeWorkspaceListLoad(state, {
    workspace_contract_version: "1.0",
    workspaces: [
      {
        workspace_id: "project--visible-one",
        display_name: "Visible One",
        is_default: false,
      },
      {
        workspace_id: "project--visible-two",
        display_name: "Visible Two",
        is_default: false,
      },
    ],
  }, cryptoStub);

  assert.equal(loaded.context.project_id, "project--visible-two");
  assert.equal(loaded.workspaces.selectedWorkspaceId, "project--visible-two");
});

test("workspace selection updates context and clears workspace-scoped panels", () => {
  const state = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const populated = {
    ...state,
    transcript: [{ request: {}, response: {} }],
    activeMemoryClarification: clarificationReceipt(),
    work: {
      ...state.work,
      list: {
        status: "ready",
        items: [{ reference: { artifact_id: "blueprint--1" } }],
        next_before: null,
        error: null,
      },
    },
    chats: {
      ...state.chats,
      sessions: [{ session_id: "session-1" }],
    },
  };

  const selected = selectWorkspace(
    populated,
    { workspace_id: "project--abc--study-plans", display_name: "Study Plans" },
    cryptoStub,
  );

  assert.equal(selected.context.project_id, "project--abc--study-plans");
  assert.equal(
    selected.workspaces.selectedWorkspaceId,
    "project--abc--study-plans",
  );
  assert.equal(selected.transcript.length, 0);
  assert.equal(selected.activeMemoryClarification, null);
  assert.equal(selected.work.list.items.length, 0);
  assert.equal(selected.chats.sessions.length, 0);
});

test("created workspace is selected without exposing project id as the label", () => {
  const state = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const selected = completeWorkspaceCreate(
    state,
    {
      workspace_contract_version: "1.0",
      workspace: {
        workspace_id: "project--abc--study-plans",
        display_name: "Study Plans",
        is_default: false,
      },
    },
    cryptoStub,
  );

  assert.equal(selected.context.project_id, "project--abc--study-plans");
  assert.equal(selected.workspaces.items[0].display_name, "Study Plans");
});

test("deleted unselected workspace is removed without changing context", () => {
  const state = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const loaded = completeWorkspaceListLoad(state, {
    workspace_contract_version: "1.0",
    workspaces: [
      {
        workspace_id: "agent-col",
        display_name: "Agent Col",
        is_default: true,
      },
      {
        workspace_id: "project--abc--study-plans",
        display_name: "Study Plans",
        is_default: false,
      },
    ],
  });

  const deleted = completeWorkspaceDelete(
    loaded,
    "project--abc--study-plans",
    cryptoStub,
  );

  assert.equal(deleted.context.project_id, "agent-col");
  assert.deepEqual(
    deleted.workspaces.items.map((workspace) => workspace.workspace_id),
    ["agent-col"],
  );
});

test("deleted selected workspace lands on surviving workspace and clears scoped panels", () => {
  const state = acceptContext(
    createInitialState(),
    {
      user_id: "wifiknight",
      project_id: "project--abc--study-plans",
      crypto: cryptoStub,
    },
  );
  const loaded = {
    ...completeWorkspaceListLoad(state, {
      workspace_contract_version: "1.0",
      workspaces: [
        {
          workspace_id: "agent-col",
          display_name: "Agent Col",
          is_default: true,
        },
        {
          workspace_id: "project--abc--study-plans",
          display_name: "Study Plans",
          is_default: false,
        },
      ],
    }),
    transcript: [{ request: {}, response: {} }],
    work: {
      ...state.work,
      list: {
        status: "ready",
        items: [{ reference: { artifact_id: "artifact--1" } }],
        next_before: null,
        error: null,
      },
    },
    notes: {
      ...state.notes,
      notes: [{ note_id: "note-1" }],
    },
    chats: {
      ...state.chats,
      sessions: [{ session_id: "session-1" }],
    },
  };

  const deleted = completeWorkspaceDelete(
    loaded,
    "project--abc--study-plans",
    cryptoStub,
  );

  assert.equal(deleted.context.project_id, "agent-col");
  assert.equal(deleted.context.session_id, "session--123e4567-e89b-12d3-a456-426614174000");
  assert.equal(deleted.workspaces.selectedWorkspaceId, "agent-col");
  assert.equal(deleted.transcript.length, 0);
  assert.equal(deleted.work.list.items.length, 0);
  assert.equal(deleted.notes.notes.length, 0);
  assert.equal(deleted.chats.sessions.length, 0);
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

test("submit is disabled when selected workspace is not visible after list load", () => {
  const accepted = acceptContext(
    createInitialState(),
    {
      user_id: "google--user",
      project_id: "project--hidden",
      crypto: cryptoStub,
    },
  );
  const loaded = {
    ...accepted,
    workspaces: {
      ...accepted.workspaces,
      status: "ready",
      selectedWorkspaceId: "project--hidden",
      items: [{
        workspace_id: "project--visible",
        display_name: "Visible",
      }],
    },
  };

  assert.equal(selectCanSubmit(loaded), false);
});

test("submit is disabled until an authoritative visible workspace is selected", () => {
  const accepted = acceptContext(
    createInitialState(),
    {
      user_id: "google--user",
      project_id: "project--visible",
      crypto: cryptoStub,
    },
  );
  const loading = beginWorkspaceListLoad(accepted);
  const failed = failWorkspaceListLoad(loading, new Error("workspace load failed"));
  const empty = completeWorkspaceListLoad(accepted, {
    workspace_contract_version: "1.0",
    workspaces: [],
  }, cryptoStub);

  assert.equal(selectCanSubmit(loading), false);
  assert.equal(selectCanSubmit(failed), false);
  assert.equal(selectCanSubmit(empty), false);
});

test("deleted artifact clears selected detail and current list item", () => {
  const state = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const loaded = {
    ...state,
    disclosure: {
      ...state.disclosure,
      work: { artifactIds: ["artifact--selected"] },
    },
    work: {
      ...state.work,
      selectedArtifactId: "artifact--selected",
      list: {
        status: "ready",
        items: [
          { reference: { artifact_id: "artifact--selected" } },
          { reference: { artifact_id: "artifact--other" } },
        ],
        next_before: null,
        error: null,
      },
      detail: {
        status: "ready",
        item: {
          metadata: {
            reference: { artifact_id: "artifact--selected" },
          },
        },
        error: null,
      },
    },
  };

  const deleted = completeWorkDelete(loaded, "artifact--selected");

  assert.equal(deleted.work.selectedArtifactId, null);
  assert.equal(deleted.work.detail.status, "idle");
  assert.deepEqual(
    deleted.work.list.items.map((item) => item.reference.artifact_id),
    ["artifact--other"],
  );
  assert.deepEqual(deleted.disclosure.work.artifactIds, []);
});

test("streamed response text accumulates and converges to canonical final", () => {
  const request = Object.freeze({
    key: "chat--stream",
    body: Object.freeze({ message: "hello" }),
  });
  const pending = appendPendingResponseDelta(
    appendPendingResponseDelta(
      beginPendingTurn(createInitialState(), request),
      "Agent ",
    ),
    "Col draft",
  );

  assert.equal(pending.pendingResponseText, "Agent Col draft");

  const completed = completePendingTurn(pending, {
    response: "Agent Col final",
    actions: [],
  });
  assert.equal(completed.pendingResponseText, "");
  assert.equal(completed.transcript.length, 1);
  assert.equal(completed.transcript[0].response.response, "Agent Col final");
});

test("failed streamed response remains explicitly provisional", () => {
  const request = Object.freeze({
    key: "chat--stream-failure",
    body: Object.freeze({ message: "hello" }),
  });
  const pending = appendPendingResponseDelta(
    beginPendingTurn(createInitialState(), request),
    "Incomplete answer",
  );
  const failed = failPendingTurn(
    pending,
    { message: "Stream interrupted", status: 0, provisional: true },
  );

  assert.equal(failed.pendingResponseText, "");
  assert.equal(failed.transcript.length, 0);
  assert.equal(failed.lastFailure.provisionalResponseText, "Incomplete answer");
});


test("failed streamed response retains authoritative partial effects", () => {
  const request = Object.freeze({
    key: "chat--stream-partial-failure",
    body: Object.freeze({ message: "create an artifact" }),
  });
  const partialFailure = Object.freeze({
    detail: "Agent_Col response failed after a completed action.",
    artifacts: [{
      artifact_id: "artifact-1",
      artifact_type: "single_file_artifact",
      schema_version: "1.0",
      display_label: "result.txt",
    }],
    memory_proposals: [],
    collaborative_note_events: [],
  });
  const failed = failPendingTurn(
    beginPendingTurn(createInitialState(), request),
    {
      message: "Agent Col could not complete this response.",
      status: 502,
      partialFailure,
    },
  );

  assert.equal(failed.lastFailure.partialFailure, partialFailure);
  assert.deepEqual(selectWorkRefreshPlan(failed.lastFailure.partialFailure), {
    reloadList: true,
    selectArtifactId: "artifact-1",
    reloadSelectedFeedback: false,
  });
});

test("failed streamed response activates an authoritative memory clarification", () => {
  const partialFailure = Object.freeze({
    detail: "Agent_Col response failed after a completed action.",
    memory_clarifications: [clarificationReceipt()],
  });
  const failed = failPendingTurn(
    beginPendingTurn(createInitialState(), {
      key: "chat--stream-memory-clarification",
      body: { message: "remember this" },
    }),
    {
      message: "Agent Col could not complete this response.",
      status: 502,
      partialFailure,
    },
  );

  assert.deepEqual(failed.activeMemoryClarification, clarificationReceipt());
});

test("failed streamed response stores authoritative note and continuity choices", () => {
  const partialFailure = Object.freeze({
    detail: "Agent_Col response failed after a completed action.",
    collaborative_note_proposals: [{
      proposal_id: "note-proposal-partial-1",
      title: "API version",
      body: "Use API version 2.",
      status: "pending",
    }],
    continuity_choices: [{
      choice_id: "choice-partial-1",
      source_kind: "collaborative_note",
      source_id: "note-1",
      display_label: "API version",
      match_reason: "bounded_relevance",
    }],
  });
  const failed = failPendingTurn(
    beginPendingTurn(createInitialState(), {
      key: "chat--stream-note-choice",
      body: { message: "use the API note" },
    }),
    {
      message: "Agent Col could not complete this response.",
      status: 502,
      partialFailure,
    },
  );

  assert.equal(
    failed.notes.pendingProposals[0].proposal_id,
    "note-proposal-partial-1",
  );
  assert.equal(
    failed.activeContinuityChoices[0].choice_id,
    "choice-partial-1",
  );
});

test("initial state has no active memory clarification", () => {
  assert.equal(createInitialState().activeMemoryClarification, null);
});

test("completed clarification response stores the active receipt and activity label", () => {
  const request = Object.freeze({
    key: "chat--clarify",
    body: Object.freeze({ message: "remember two things" }),
  });

  const completed = completePendingTurn(
    beginPendingTurn(createInitialState(), request),
    {
      response: "Which should I remember first?",
      memory_clarifications: [clarificationReceipt()],
      memory_proposals: [],
    },
  );

  assert.deepEqual(completed.activeMemoryClarification, clarificationReceipt());
  assert.equal(
    completed.activity.entries.at(-1).label,
    "Memory clarification",
  );
  assert.equal(
    completed.activity.entries.at(-1).detail,
    "Response length: Detailed",
  );
  assert.doesNotMatch(
    completed.activity.entries.at(-1).detail,
    /memory-clarification--/,
  );
});

test("failed clarification selection keeps the active receipt and exact retry", () => {
  const withClarification = {
    ...createInitialState(),
    activeMemoryClarification: clarificationReceipt(),
  };
  const selectionRequest = Object.freeze({
    key: "chat--select",
    body: Object.freeze({
      message: "Select Response length: Detailed.",
      memory_clarification_selection: Object.freeze({
        clarification_id: "memory-clarification--clarify-1",
        selected_candidate_index: 0,
      }),
    }),
  });

  const failed = failPendingTurn(
    beginPendingTurn(withClarification, selectionRequest),
    { message: "network failed", status: 0 },
  );

  assert.deepEqual(failed.activeMemoryClarification, clarificationReceipt());
  assert.equal(failed.lastFailure.request, selectionRequest);
});

test("successful clarification selection clears the consumed receipt", () => {
  const withClarification = {
    ...createInitialState(),
    activeMemoryClarification: clarificationReceipt(),
  };
  const selectionRequest = Object.freeze({
    key: "chat--select",
    body: Object.freeze({
      message: "Select Response length: Detailed.",
      memory_clarification_selection: Object.freeze({
        clarification_id: "memory-clarification--clarify-1",
        selected_candidate_index: 0,
      }),
    }),
  });

  const completed = completePendingTurn(
    beginPendingTurn(withClarification, selectionRequest),
    {
      response: "Proposal created.",
      memory_proposals: [{
        proposal_id: "response_length--proposal-1",
        category: "response_length",
      }],
    },
  );

  assert.equal(completed.activeMemoryClarification, null);
});

test("ordinary chat does not invent or consume a memory clarification", () => {
  const withClarification = {
    ...createInitialState(),
    activeMemoryClarification: clarificationReceipt(),
  };

  const completed = completePendingTurn(
    beginPendingTurn(withClarification, {
      key: "chat--ordinary",
      body: { message: "hello" },
    }),
    { response: "ok", memory_proposals: [] },
  );

  assert.deepEqual(completed.activeMemoryClarification, clarificationReceipt());
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
      collaborative_note_events: [{
        event_type: "approved",
        note_id: "note--1",
        title: "API decision",
      }],
      adaptations: [{
        signal_id: "preferred_name--signal-1",
        category: "preferred_name",
        value: "wifiknight",
        source_event_id: "preferred_name--signal-1--approved",
        status: "provided_to_model",
      }],
    },
  );

  assert.deepEqual(
    completed.activity.entries.map((entry) => entry.kind),
    ["action", "citation", "work", "feedback", "memory", "note", "adaptation"],
  );
  assert.equal(completed.activity.entries[0].label, "synthesize_project");
  assert.equal(completed.activity.entries[2].detail, "created");
  assert.equal(completed.activity.entries[3].detail, "recorded");
  assert.equal(completed.activity.entries[4].detail, "pending");
  assert.equal(completed.activity.entries[5].detail, "API decision");
  assert.equal(completed.activity.entries[6].label, "Preferred name");
  assert.equal(completed.activity.entries[6].detail, "Wifiknight");
  assert.equal(JSON.stringify(completed.activity.entries).includes("--"), false);
});

test("completed turn projects adaptation activity with readable provenance", () => {
  const request = Object.freeze({
    key: "chat--adapted",
    body: Object.freeze({ message: "Compare two planning options." }),
  });
  const completed = completePendingTurn(
    beginPendingTurn(createInitialState(), request),
    {
      response: "ok",
      adaptations: [{
        signal_id: "development_environments--active-v2",
        category: "development_environments",
        value: ["macos", "linux"],
        policy_version: "2.0",
        source_event_id: "development_environments--active-v2--approved",
        status: "provided_to_model",
      }],
    },
  );

  assert.deepEqual(completed.activity.entries, [{
    kind: "adaptation",
    label: "Development environments",
    detail: "Macos, Linux",
  }]);
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

test("chat session detail restores an active memory clarification", () => {
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
      messages: [],
      active_memory_clarification: clarificationReceipt(),
    },
  );

  assert.deepEqual(loaded.activeMemoryClarification, clarificationReceipt());
});

test("chat session detail clears stale memory clarification when none remains active", () => {
  const state = acceptContext(
    {
      ...createInitialState(),
      activeMemoryClarification: clarificationReceipt(),
    },
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );

  const loaded = completeChatSessionDetailLoad(
    beginChatSessionDetailLoad(state, "session--old"),
    {
      chat_contract_version: "1.0",
      session_id: "session--old",
      project_id: "agent-col",
      user_id: "wifiknight",
      messages: [],
      active_memory_clarification: null,
    },
  );

  assert.equal(loaded.activeMemoryClarification, null);
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
  const withClarification = {
    ...withTranscript,
    activeMemoryClarification: clarificationReceipt(),
  };

  const next = startNewConversation(withClarification, cryptoStub);

  assert.equal(next.context.user_id, "wifiknight");
  assert.equal(next.context.project_id, "agent-col");
  assert.equal(next.transcript.length, 0);
  assert.equal(next.lastFailure, null);
  assert.equal(next.activeMemoryClarification, null);
});

test("selectCanSubmit requires workspace context and no pending turn", () => {
  assert.equal(selectCanSubmit(createInitialState()), false);
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const loaded = completeWorkspaceListLoad(accepted, {
    workspace_contract_version: "1.0",
    workspaces: [{
      workspace_id: "agent-col",
      display_name: "Agent Col",
      is_default: true,
    }],
  }, cryptoStub);
  assert.equal(selectCanSubmit(loaded), true);
  assert.equal(
    selectCanSubmit(beginPendingTurn(loaded, {
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
      collaborative_note_proposals: [{ proposal_id: "note-proposal-1" }],
      collaborative_note_events: [{ event_id: "note-1--approved" }],
      continuity_receipts: [{ source_kind: "collaborative_note", source_id: "note-1" }],
    }),
    {
      work: true,
      memory: true,
      notes: true,
    },
  );
  assert.deepEqual(
    selectNeedsReceiptRefresh({ response: "I created a blueprint in prose." }),
    {
      work: false,
      memory: true,
      notes: false,
    },
  );
});

test("note lifecycle stores pending proposals, notes, detail, and clears on workspace switch", () => {
  const loading = beginNotesLoad(createInitialState(), "active");
  assert.equal(loading.notes.status, "loading");
  assert.equal(loading.notes.statusFilter, "active");

  const completed = completeNotesLoad(loading, {
    notes: [{
      note_id: "note-1",
      title: "API version",
      body: "Use API version 2.",
      status: "active",
      revision: 2,
    }],
    next_note_id: "note-2",
  });
  assert.equal(completed.notes.status, "ready");
  assert.equal(completed.notes.notes[0].note_id, "note-1");
  assert.equal(completed.notes.next_note_id, "note-2");

  const withProposal = storePendingNoteProposal(completed, {
    proposal_id: "note-proposal-1",
    title: "API version",
    body: "Use API version 2.",
    status: "pending",
  });
  assert.equal(withProposal.notes.pendingProposals[0].proposal_id, "note-proposal-1");

  const withDetail = completeNoteDetailLoad(
    beginNoteDetailLoad(withProposal, "note-1"),
    {
      note: completed.notes.notes[0],
      events: [{ event_id: "note-1--approved", event_type: "approved" }],
    },
  );
  assert.equal(withDetail.notes.selectedNoteId, "note-1");
  assert.equal(withDetail.notes.detail.events[0].event_type, "approved");

  const selected = selectWorkspace(
    {
      ...withDetail,
      context: { user_id: "wifiknight", project_id: "agent-col", session_id: "session-1" },
    },
    { workspace_id: "project--abc--study-plans", display_name: "Study Plans" },
    cryptoStub,
  );
  assert.equal(selected.notes.notes.length, 0);
  assert.equal(selected.notes.pendingProposals.length, 0);
  assert.equal(selected.notes.detail.status, "idle");
});

test("completed turn stores active continuity choices and pending note proposals", () => {
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const pending = beginPendingTurn(accepted, {
    key: "chat--1",
    body: { message: "Remember this workspace note." },
  });

  const completed = completePendingTurn(pending, {
    response: "Which note should I use?",
    collaborative_note_proposals: [{
      proposal_id: "note-proposal-1",
      title: "API version",
      body: "Use API version 2.",
      status: "pending",
    }],
    continuity_choices: [{
      choice_id: "choice-1",
      source_kind: "collaborative_note",
      source_id: "note-1",
      display_label: "API version",
      match_reason: "bounded_relevance",
    }],
  });

  assert.equal(completed.notes.pendingProposals[0].proposal_id, "note-proposal-1");
  assert.equal(completed.activeContinuityChoices[0].choice_id, "choice-1");
});

test("completed note event removes matching pending note proposal", () => {
  const accepted = acceptContext(
    createInitialState(),
    { user_id: "wifiknight", project_id: "agent-col", crypto: cryptoStub },
  );
  const withFirstProposal = storePendingNoteProposal(accepted, {
    proposal_id: "note-proposal-1",
    title: "API version",
    body: "Use API version 2.",
    status: "pending",
  });
  const withSecondProposal = storePendingNoteProposal(withFirstProposal, {
    proposal_id: "note-proposal-2",
    title: "Build target",
    body: "Use the browser target.",
    status: "pending",
  });
  const pending = beginPendingTurn(withSecondProposal, {
    key: "chat--approve-note",
    body: { message: "Record approve decision for note proposal note-proposal-1." },
  });

  const completed = completePendingTurn(pending, {
    response: "Approved.",
    collaborative_note_events: [{
      event_id: "note-1--approved",
      event_type: "approved",
      note_id: "note-1",
      proposal_id: "note-proposal-1",
      title: "API version",
    }],
  });

  assert.deepEqual(
    completed.notes.pendingProposals.map((proposal) => proposal.proposal_id),
    ["note-proposal-2"],
  );
});

test("notes list refresh updates selected active note detail", () => {
  const loading = beginNotesLoad(createInitialState(), "active");
  const staleNote = {
    note_id: "note-1",
    title: "Workspace Environment",
    body: "Using a macOS environment for this workspace.",
    status: "active",
    revision: 2,
  };
  const loaded = completeNotesLoad(loading, {
    notes: [staleNote],
    next_note_id: null,
  });
  const withDetail = completeNoteDetailLoad(
    beginNoteDetailLoad(loaded, "note-1"),
    {
      note: staleNote,
      events: [{ event_id: "note-1--approved", event_type: "approved" }],
    },
  );

  const refreshed = completeNotesLoad(withDetail, {
    notes: [{
      ...staleNote,
      body: "Using a Linux environment for this workspace.",
      revision: 3,
    }],
    next_note_id: null,
  });

  assert.equal(
    refreshed.notes.detail.note.body,
    "Using a Linux environment for this workspace.",
  );
  assert.equal(refreshed.notes.detail.note.revision, 3);
  assert.deepEqual(refreshed.notes.detail.events, withDetail.notes.detail.events);
});

test("notes list refresh clears selected detail when note leaves current filter", () => {
  const note = {
    note_id: "note-1",
    title: "Workspace Environment",
    body: "Using a Linux environment for this workspace.",
    status: "active",
    revision: 3,
  };
  const withActiveDetail = completeNoteDetailLoad(
    beginNoteDetailLoad(
      completeNotesLoad(beginNotesLoad(createInitialState(), "active"), {
        notes: [note],
        next_note_id: null,
      }),
      "note-1",
    ),
    {
      note,
      events: [{ event_id: "note-1--approved", event_type: "approved" }],
    },
  );

  const afterArchive = completeNotesLoad(withActiveDetail, {
    notes: [],
    next_note_id: null,
  });

  assert.equal(afterArchive.notes.selectedNoteId, null);
  assert.equal(afterArchive.notes.detail.status, "idle");
  assert.equal(afterArchive.notes.detail.note, null);
  assert.deepEqual(afterArchive.notes.detail.events, []);

  const archivedNote = { ...note, status: "archived", revision: 4 };
  const withArchivedDetail = completeNoteDetailLoad(
    beginNoteDetailLoad(
      completeNotesLoad(beginNotesLoad(createInitialState(), "archived"), {
        notes: [archivedNote],
        next_note_id: null,
      }),
      "note-1",
    ),
    {
      note: archivedNote,
      events: [{ event_id: "note-1--archived", event_type: "archived" }],
    },
  );

  const afterRestore = completeNotesLoad(withArchivedDetail, {
    notes: [],
    next_note_id: null,
  });

  assert.equal(afterRestore.notes.selectedNoteId, null);
  assert.equal(afterRestore.notes.detail.status, "idle");
  assert.equal(afterRestore.notes.detail.note, null);
  assert.deepEqual(afterRestore.notes.detail.events, []);
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

test("memory signal mutation removes a saved memory and disclosure state", () => {
  const loaded = completeMemoryLoad(createInitialState(), {
    profile: {
      memory_schema_version: "1.0",
      memory_revision: 1,
      identity_context: {
        preferred_name: {
          signal_id: "preferred_name--signal-1",
          value: "wifiknight",
        },
      },
      active_preferences: {
        response_length: {
          signal_id: "response_length--signal-1",
          value: "concise",
        },
      },
    },
    unresolved_proposals: [{ proposal_id: "response_length--proposal-2" }],
    events: [{ event_id: "event-1" }],
  });
  const expanded = toggleMemoryDisclosure(
    loaded,
    "response_length--signal-1",
    "signal",
  );

  const updated = completeMemorySignalMutation(
    expanded,
    "response_length--signal-1",
  );

  assert.equal(
    updated.memory.profile.active_preferences.response_length,
    undefined,
  );
  assert.equal(
    updated.memory.profile.identity_context.preferred_name.signal_id,
    "preferred_name--signal-1",
  );
  assert.deepEqual(updated.memory.unresolvedProposals, [{
    proposal_id: "response_length--proposal-2",
  }]);
  assert.deepEqual(updated.memory.events, [{ event_id: "event-1" }]);
  assert.deepEqual(updated.disclosure.memory.signalIds, []);
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
    selectFirstSupportedArtifact({
      artifacts: [
        {
          artifact_type: "single_file_artifact",
          artifact_id: "artifact--abc",
          schema_version: "1.0",
        },
      ],
    }),
    {
      artifact_type: "single_file_artifact",
      artifact_id: "artifact--abc",
      schema_version: "1.0",
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

test("archiving selected work removes it from the visible list and clears detail", () => {
  const loaded = completeWorkDetailLoad(
    completeWorkListLoad(beginWorkListLoad(createInitialState()), {
      artifacts: [
        {
          reference: {
            artifact_id: "artifact--abc",
            artifact_type: "single_file_artifact",
            schema_version: "1.0",
            display_label: "Script",
          },
        },
        {
          reference: {
            artifact_id: "blueprint--abc",
            artifact_type: "synthesis_blueprint",
            schema_version: "2.0",
            display_label: "Blueprint",
          },
        },
      ],
      next_before: null,
    }),
    {
      metadata: {
        reference: {
          artifact_id: "artifact--abc",
          artifact_type: "single_file_artifact",
          schema_version: "1.0",
          display_label: "Script",
        },
      },
      artifact: {
        artifact_family: "code",
        format: "python",
        filename: "script.py",
        content: "print('hi')\n",
      },
    },
    { events: [], next_before: null },
  );

  const expanded = toggleArtifactDisclosure(loaded, "artifact--abc");
  const archived = completeWorkArchive(expanded, "artifact--abc");

  assert.deepEqual(
    archived.work.list.items.map((item) => item.reference.artifact_id),
    ["blueprint--abc"],
  );
  assert.equal(archived.work.selectedArtifactId, null);
  assert.equal(archived.work.detail.status, "idle");
  assert.deepEqual(archived.disclosure.work.artifactIds, []);
});

test("work lifecycle mode can switch to archived and restores selected work out of view", () => {
  const active = completeWorkListLoad(createInitialState(), {
    artifacts: [{
      reference: {
        artifact_id: "artifact--abc",
        artifact_type: "single_file_artifact",
        schema_version: "1.0",
        display_label: "Script",
      },
    }],
  });

  const archivedMode = setWorkLifecycleStatus(active, "archived");
  assert.equal(archivedMode.work.list.lifecycleStatus, "archived");
  assert.equal(archivedMode.work.list.items.length, 0);

  const archivedDetail = completeWorkDetailLoad(
    completeWorkListLoad(archivedMode, {
      artifacts: [{
        reference: {
          artifact_id: "artifact--abc",
          artifact_type: "single_file_artifact",
          schema_version: "1.0",
          display_label: "Script",
        },
      }],
    }),
    {
      metadata: {
        reference: {
          artifact_id: "artifact--abc",
          artifact_type: "single_file_artifact",
          schema_version: "1.0",
          display_label: "Script",
        },
        lifecycle_status: "archived",
      },
      artifact: {
        artifact_family: "code",
        format: "python",
        filename: "script.py",
        content: "print('hi')\n",
      },
    },
    { events: [], next_before: null },
  );

  const restored = completeWorkRestore(archivedDetail, "artifact--abc");
  assert.equal(restored.work.list.items.length, 0);
  assert.equal(restored.work.selectedArtifactId, null);
  assert.equal(restored.work.detail.status, "idle");
});

test("work metadata update refreshes list and selected generic detail labels", () => {
  const loaded = completeWorkDetailLoad(
    completeWorkListLoad(createInitialState(), {
      artifacts: [{
        reference: {
          artifact_id: "artifact--abc",
          artifact_type: "single_file_artifact",
          schema_version: "1.0",
          display_label: "Old Script",
        },
        filename: "old.py",
      }],
    }),
    {
      metadata: {
        reference: {
          artifact_id: "artifact--abc",
          artifact_type: "single_file_artifact",
          schema_version: "1.0",
          display_label: "Old Script",
        },
        filename: "old.py",
      },
      artifact: {
        artifact_family: "code",
        format: "python",
        filename: "old.py",
        content: "print('unchanged')\n",
      },
    },
    { events: [], next_before: null },
  );

  const updated = completeWorkMetadataUpdate(loaded, {
    reference: {
      artifact_id: "artifact--abc",
      artifact_type: "single_file_artifact",
      schema_version: "1.0",
      display_label: "Renamed Script",
    },
    filename: "renamed.py",
  });

  assert.equal(
    updated.work.list.items[0].reference.display_label,
    "Renamed Script",
  );
  assert.equal(updated.work.list.items[0].filename, "renamed.py");
  assert.equal(
    updated.work.detail.item.metadata.reference.display_label,
    "Renamed Script",
  );
  assert.equal(updated.work.detail.item.metadata.filename, "renamed.py");
  assert.equal(
    updated.work.detail.item.artifact.content,
    "print('unchanged')\n",
  );
});

test("work version creation prepends and selects replacement artifact", () => {
  const loaded = completeWorkDetailLoad(
    completeWorkListLoad(
      beginWorkListLoad(createInitialState()),
      {
        artifacts: [{
          reference: {
            artifact_id: "artifact--abc",
            artifact_type: "single_file_artifact",
            schema_version: "1.0",
            display_label: "Old Script",
          },
          filename: "old.py",
        }],
        next_before: null,
      },
    ),
    {
      metadata: {
        reference: {
          artifact_id: "artifact--abc",
          artifact_type: "single_file_artifact",
          schema_version: "1.0",
          display_label: "Old Script",
        },
        filename: "old.py",
      },
      artifact: {
        artifact_family: "code",
        format: "python",
        filename: "old.py",
        content: "print('old')\n",
      },
    },
    { events: [], next_before: null },
  );

  const updated = completeWorkVersionCreate(loaded, {
    reference: {
      artifact_id: "artifact--v2",
      artifact_type: "single_file_artifact",
      schema_version: "1.0",
      display_label: "Updated Script",
    },
    artifact: {
      artifact_family: "code",
      format: "python",
      filename: "updated.py",
      content: "print('updated')\n",
      summary: "Updated script.",
    },
  });

  assert.equal(updated.work.selectedArtifactId, "artifact--v2");
  assert.equal(
    updated.work.list.items[0].reference.display_label,
    "Updated Script",
  );
  assert.equal(updated.work.list.items[0].filename, "updated.py");
  assert.equal(updated.work.list.items[0].parent_artifact_id, "artifact--abc");
  assert.equal(
    updated.work.list.items[1].reference.display_label,
    "Old Script",
  );
  assert.equal(
    updated.work.detail.item.artifact.content,
    "print('updated')\n",
  );
  assert.equal(
    updated.work.detail.item.metadata.parent_artifact_id,
    "artifact--abc",
  );
});
