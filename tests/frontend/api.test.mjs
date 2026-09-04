import test from "node:test";
import assert from "node:assert/strict";

import {
  apiFetchJson,
  apiFetchSse,
  archiveArtifact,
  createArtifact,
  createArtifactVersion,
  deleteArtifact,
  createNoteProposal,
  getAuthConfig,
  getAuthSession,
  getArtifact,
  getBlueprint,
  getChatSession,
  decideMemoryProposal,
  decideNoteProposal,
  inspectMemory,
  listAgentJobs,
  listAgentJobReports,
  listArtifacts,
  listChatSessions,
  listBlueprintFeedback,
  listBlueprints,
  recordBlueprintFeedback,
  createWorkspace,
  archiveNote,
  createNoteCorrection,
  deleteNote,
  deleteWorkspace,
  getNote,
  listWorkspaces,
  listNotes,
  deleteMemorySignal,
  restoreNote,
  restoreArtifact,
  revokeMemorySignal,
  selectMemoryClarification,
  streamAgentJobs,
  synthesizeSpeechAudio,
  transcribeSpeechAudio,
  updateArtifactMetadata,
} from "../../frontend/api.mjs";

function jsonResponse(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

function sseResponse(chunks) {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  }), {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

test("apiFetchSse parses split delta frames and returns canonical final", async () => {
  const calls = [];
  const deltas = [];
  const result = await apiFetchSse(
    "/api/chat/stream",
    {
      method: "POST",
      idempotencyKey: "chat--123",
      authToken: "google-id-token",
      body: { message: "hello" },
      onDelta(text) {
        deltas.push(text);
      },
    },
    async (path, init) => {
      calls.push([path, init]);
      return sseResponse([
        "event: delta\ndata: {\"text\":\"Agent \"}\n",
        "\nevent: delta\ndata: {\"text\":\"C",
        "ol\"}\n\nevent: fin",
        "al\ndata: {\"response\":\"Agent Col\",\"actions\":[]}\n\n",
      ]);
    },
  );

  assert.deepEqual(deltas, ["Agent ", "Col"]);
  assert.deepEqual(result, { response: "Agent Col", actions: [] });
  assert.equal(calls[0][0], "/api/chat/stream");
  assert.equal(calls[0][1].headers["Idempotency-Key"], "chat--123");
  assert.equal(calls[0][1].headers.Authorization, "Bearer google-id-token");
  assert.equal(calls[0][1].body, JSON.stringify({ message: "hello" }));
});

test("apiFetchSse surfaces sanitized backend errors after provisional text", async () => {
  await assert.rejects(
    () => apiFetchSse(
      "/api/chat/stream",
      { body: { message: "hello" }, onDelta() {} },
      async () => sseResponse([
        "event: delta\ndata: {\"text\":\"Draft\"}\n\n",
        "event: error\ndata: {\"detail\":\"Database operation failed.\",",
        "\"status\":500,\"provisional\":true}\n\n",
      ]),
    ),
    (error) => {
      assert.equal(error.status, 500);
      assert.equal(error.message, "Database operation failed.");
      assert.equal(error.provisional, true);
      return true;
    },
  );
});

test("apiFetchSse rejects an interrupted stream without canonical final", async () => {
  const deltas = [];
  await assert.rejects(
    () => apiFetchSse(
      "/api/chat/stream",
      { onDelta(text) { deltas.push(text); } },
      async () => sseResponse([
        "event: delta\ndata: {\"text\":\"Incomplete\"}\n\n",
      ]),
    ),
    (error) => {
      assert.equal(error.status, 0);
      assert.equal(error.provisional, true);
      assert.match(error.message, /before completion/);
      return true;
    },
  );
  assert.deepEqual(deltas, ["Incomplete"]);
});

test("apiFetchSse batches delta frames from one network chunk", async () => {
  const deltas = [];
  const result = await apiFetchSse(
    "/api/chat/stream",
    { onDelta(text) { deltas.push(text); } },
    async () => sseResponse([
      "event: delta\ndata: {\"text\":\"Agent \"}\n\n"
      + "event: delta\ndata: {\"text\":\"Col\"}\n\n"
      + "event: final\ndata: {\"response\":\"Agent Col\"}\n\n",
    ]),
  );

  assert.deepEqual(deltas, ["Agent Col"]);
  assert.equal(result.response, "Agent Col");
});

test("apiFetchJson sends same-origin JSON with idempotency key", async () => {
  const calls = [];
  const result = await apiFetchJson(
    "/api/chat",
    {
      method: "POST",
      idempotencyKey: "chat--123",
      body: { message: "hello" },
    },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { response: "ok", actions: [] });
    },
  );

  assert.deepEqual(result, { response: "ok", actions: [] });
  assert.equal(calls[0][0], "/api/chat");
  assert.equal(calls[0][1].headers["Content-Type"], "application/json");
  assert.equal(calls[0][1].headers["Idempotency-Key"], "chat--123");
  assert.equal(calls[0][1].body, JSON.stringify({ message: "hello" }));
});

test("apiFetchJson attaches bearer token when supplied", async () => {
  const calls = [];
  await apiFetchJson(
    "/api/chat",
    {
      method: "POST",
      authToken: "google-id-token",
      body: { message: "hello" },
    },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { response: "ok", actions: [] });
    },
  );

  assert.equal(calls[0][1].headers.Authorization, "Bearer google-id-token");
});

test("listAgentJobs fetches the public agent job projection for a workspace", async () => {
  const calls = [];
  const response = await listAgentJobs(
    "user-1",
    "project-1",
    {
      authToken: "google-id-token",
      limit: 30,
      session_id: "session-1",
    },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        agent_job_contract_version: "1.0",
        jobs: [],
      });
    },
  );

  assert.deepEqual(response, {
    agent_job_contract_version: "1.0",
    jobs: [],
  });
  assert.equal(
    calls[0][0],
    "/api/users/user-1/projects/project-1/agent/jobs?limit=30&session_id=session-1",
  );
  assert.equal(calls[0][1].method, "GET");
  assert.equal(calls[0][1].headers.Authorization, "Bearer google-id-token");
});

test("streamAgentJobs reads public snapshot events", async () => {
  const calls = [];
  const snapshots = [];

  await streamAgentJobs(
    "user-1",
    "project-1",
    {
      authToken: "google-id-token",
      limit: 50,
      session_id: "session-1",
    },
    {
      onSnapshot(payload) {
        snapshots.push(payload);
      },
    },
    async (path, init) => {
      calls.push([path, init]);
      return sseResponse([
        "event: snapshot\n",
        'data: {"agent_job_contract_version":"1.0","jobs":[{"job_ref":"jobref_abc123","job_number":"001","status":"running"}]}\n\n',
      ]);
    },
  );

  assert.deepEqual(snapshots, [{
    agent_job_contract_version: "1.0",
    jobs: [{ job_ref: "jobref_abc123", job_number: "001", status: "running" }],
  }]);
  assert.equal(
    calls[0][0],
    "/api/users/user-1/projects/project-1/agent/jobs/stream?limit=50&session_id=session-1",
  );
  assert.equal(calls[0][1].method, "GET");
  assert.equal(calls[0][1].headers.Authorization, "Bearer google-id-token");
});

test("listAgentJobReports fetches public report projection without internal identifiers", async () => {
  const calls = [];
  const response = await listAgentJobReports(
    "user-1",
    "project-1",
    {
      authToken: "google-id-token",
      limit: 30,
      session_id: "session-1",
    },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        agent_job_report_contract_version: "1.0",
        reports: [{
          report_number: "001",
          job_ref: "jobref_abc123",
          job_number: "001",
          action_kind: "propose_memory_signal",
          agent_label: "Memory Analyst",
          status: "completed",
          title: "Memory proposal pending review",
          summary: "A memory proposal was created and is pending your review.",
          public_resource_label: "Prefers C over Python",
          created_at: "2026-09-02T10:00:00Z",
        }],
      });
    },
  );

  assert.deepEqual(response.reports[0], {
    report_number: "001",
    job_ref: "jobref_abc123",
    job_number: "001",
    action_kind: "propose_memory_signal",
    agent_label: "Memory Analyst",
    status: "completed",
    title: "Memory proposal pending review",
    summary: "A memory proposal was created and is pending your review.",
    public_resource_label: "Prefers C over Python",
    created_at: "2026-09-02T10:00:00Z",
  });
  assert.equal(
    calls[0][0],
    "/api/users/user-1/projects/project-1/agent/reports?limit=30&session_id=session-1",
  );
  assert.equal(calls[0][1].method, "GET");
  assert.equal(calls[0][1].headers.Authorization, "Bearer google-id-token");
  assert.equal(JSON.stringify(response).includes("job-"), false);
  assert.equal(JSON.stringify(response).includes("session-"), false);
});

test("transcribeSpeechAudio posts raw audio with the recording MIME type", async () => {
  const calls = [];
  const audio = new Blob(["webm audio"], { type: "audio/webm;codecs=opus" });

  const result = await transcribeSpeechAudio(
    audio,
    { authToken: "google-id-token" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { transcript: "recognized text" });
    },
  );

  assert.deepEqual(result, { transcript: "recognized text" });
  assert.equal(calls[0][0], "/api/speech/transcribe");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].headers.Authorization, "Bearer google-id-token");
  assert.equal(calls[0][1].headers["Content-Type"], "audio/webm;codecs=opus");
  assert.equal(calls[0][1].body, audio);
});

test("synthesizeSpeechAudio posts canonical locator and returns audio metadata", async () => {
  const calls = [];
  const result = await synthesizeSpeechAudio(
    "wifiknight",
    {
      project_id: "agent-col",
      session_id: "session--1",
      message_id: "turn--abc--model",
      chunk_index: 1,
      voice_id: "male",
    },
    { authToken: "google-id-token" },
    async (path, init) => {
      calls.push([path, init]);
      return new Response(new Blob(["audio chunk"], { type: "audio/mpeg" }), {
        status: 200,
        headers: {
          "Content-Type": "audio/mpeg",
          "X-Speech-Chunk-Index": "1",
          "X-Speech-Chunk-Count": "3",
        },
      });
    },
  );

  assert.equal(calls[0][0], "/api/users/wifiknight/speech/synthesize");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].headers.Authorization, "Bearer google-id-token");
  assert.equal(calls[0][1].headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    project_id: "agent-col",
    session_id: "session--1",
    message_id: "turn--abc--model",
    chunk_index: 1,
    voice_id: "male",
  });
  assert.equal(calls[0][1].body.includes("Agent response"), false);
  assert.equal(result.audio instanceof Blob, true);
  assert.equal(result.contentType, "audio/mpeg");
  assert.equal(result.chunkIndex, 1);
  assert.equal(result.chunkCount, 3);
});

test("getAuthSession calls the canonical auth session path", async () => {
  const calls = [];
  const result = await getAuthSession("google-id-token", async (path, init) => {
    calls.push([path, init]);
    return jsonResponse(200, {
      auth_contract_version: "1.0",
      auth_mode: "google_oidc",
      authenticated: true,
      local_development: false,
      user_id: "user--opaque123",
    });
  });

  assert.equal(result.user_id, "user--opaque123");
  assert.equal(calls[0][0], "/api/auth/session");
  assert.equal(calls[0][1].method, "GET");
  assert.equal(calls[0][1].headers.Authorization, "Bearer google-id-token");
});

test("getAuthConfig calls the public auth config path", async () => {
  const calls = [];
  const result = await getAuthConfig(async (path, init) => {
    calls.push([path, init]);
    return jsonResponse(200, {
      auth_contract_version: "1.0",
      auth_mode: "google_oidc",
      google_client_id: "client-123",
      google_signin_required: true,
      local_development: false,
    });
  });

  assert.equal(result.google_client_id, "client-123");
  assert.equal(calls[0][0], "/api/auth/config");
  assert.equal(calls[0][1].method, "GET");
  assert.equal("Authorization" in calls[0][1].headers, false);
});

test("apiFetchJson rejects remote URLs", async () => {
  await assert.rejects(
    () => apiFetchJson("https://example.com/api/chat", {}, async () => {
      throw new Error("fetch should not run");
    }),
    /same-origin/,
  );
});

test("apiFetchJson normalizes FastAPI validation arrays", async () => {
  await assert.rejects(
    () => apiFetchJson("/api/chat", {}, async () => jsonResponse(422, {
      detail: [
        {
          loc: ["body", "message"],
          msg: "String should have at most 10000 characters",
        },
      ],
    })),
    (error) => {
      assert.equal(error.status, 422);
      assert.equal(
        error.message,
        "body.message: String should have at most 10000 characters",
      );
      return true;
    },
  );
});

test("apiFetchJson includes retry-after seconds when supplied", async () => {
  await assert.rejects(
    () => apiFetchJson("/api/chat", {}, async () => jsonResponse(
      409,
      { detail: "Chat turn is still in progress." },
      { "retry-after": "3" },
    )),
    (error) => {
      assert.equal(error.status, 409);
      assert.equal(error.retryAfterSeconds, 3);
      assert.equal(error.message, "Chat turn is still in progress.");
      return true;
    },
  );
});

test("apiFetchJson maps Agent Col turn timeouts to user-facing copy", async () => {
  await assert.rejects(
    () => apiFetchJson("/api/chat", {}, async () => jsonResponse(
      504,
      { detail: "Agent_Col response timed out." },
    )),
    (error) => {
      assert.equal(error.status, 504);
      assert.equal(error.detail, "Agent_Col response timed out.");
      assert.equal(
        error.message,
        "Agent Col timed out before completing this response. No completed action was recorded.",
      );
      return true;
    },
  );
});

test("apiFetchJson preserves JSON chat partial-failure response effects", async () => {
  await assert.rejects(
    () => apiFetchJson("/api/chat", {}, async () => jsonResponse(
      504,
      {
        detail: "Agent_Col response timed out after a completed action.",
        response: "",
        actions: [{ action_name: "approve_memory_signal", status: "completed" }],
        memory_proposals: [],
      },
    )),
    (error) => {
      assert.equal(error.status, 504);
      assert.equal(
        error.message,
        "Agent Col timed out after recording a completed action. Retry will reuse completed receipts.",
      );
      assert.deepEqual(error.partialFailure.actions, [
        { action_name: "approve_memory_signal", status: "completed" },
      ]);
      assert.equal("partial_failure" in error.partialFailure, false);
      return true;
    },
  );
});

test("listBlueprints calls the canonical project blueprint list path", async () => {
  const calls = [];
  const result = await listBlueprints(
    "agent-col",
    { limit: 5, before: "cursor--1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifacts: [], next_before: null });
    },
  );

  assert.deepEqual(result, { artifacts: [], next_before: null });
  assert.equal(
    calls[0][0],
    "/api/projects/agent-col/blueprints?limit=5&before=cursor--1",
  );
  assert.equal(calls[0][1].method, "GET");
});

test("getBlueprint calls the canonical blueprint detail path", async () => {
  const calls = [];
  await getBlueprint("agent-col", "blueprint--abc", async (path, init) => {
    calls.push([path, init]);
    return jsonResponse(200, { artifact_contract_version: "1.0" });
  });

  assert.equal(calls[0][0], "/api/projects/agent-col/blueprints/blueprint--abc");
  assert.equal(calls[0][1].method, "GET");
});

test("listBlueprintFeedback calls the canonical feedback history path", async () => {
  const calls = [];
  await listBlueprintFeedback(
    "agent-col",
    "blueprint--abc",
    { limit: 20 },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { events: [], next_before: null });
    },
  );

  assert.equal(
    calls[0][0],
    "/api/projects/agent-col/blueprints/blueprint--abc/feedback?limit=20",
  );
  assert.equal(calls[0][1].method, "GET");
});

test("recordBlueprintFeedback posts direct feedback with idempotency", async () => {
  const calls = [];
  await recordBlueprintFeedback(
    "agent-col",
    "blueprint--abc",
    {
      session_id: "session--1",
      user_id: "wifiknight",
      artifact_id: "blueprint--abc",
      target_id: "target--whole",
      decision: "accepted",
      feedback_text: "This boundary is correct.",
      expected_schema_version: "2.0",
    },
    { idempotencyKey: "artifact-feedback--1", authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        feedback_contract_version: "1.0",
        action: {
          action_name: "record_blueprint_feedback",
          status: "completed",
        },
        feedback: {
          feedback_id: "feedback--artifact-feedback--1",
          artifact_id: "blueprint--abc",
          target_id: "target--whole",
          target_kind: "whole_blueprint",
          decision: "accepted",
          schema_version: "2.0",
          created_at: "2026-09-02T12:00:00Z",
        },
      });
    },
  );

  assert.equal(
    calls[0][0],
    "/api/projects/agent-col/blueprints/blueprint--abc/feedback",
  );
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].headers.Authorization, "Bearer token-1");
  assert.equal(calls[0][1].headers["Idempotency-Key"], "artifact-feedback--1");
  assert.equal(calls[0][1].body, JSON.stringify({
    session_id: "session--1",
    user_id: "wifiknight",
    artifact_id: "blueprint--abc",
    target_id: "target--whole",
    decision: "accepted",
    feedback_text: "This boundary is correct.",
    expected_schema_version: "2.0",
  }));
});

test("generic artifact API wrappers use the canonical artifact paths", async () => {
  const calls = [];
  await listArtifacts(
    "agent-col",
    { limit: 5 },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifacts: [], next_before: null });
    },
  );
  await getArtifact(
    "agent-col",
    "artifact--abc",
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifact_contract_version: "1.0" });
    },
  );
  await createArtifact(
    "agent-col",
    {
      session_id: "session--1",
      user_id: "wifiknight",
      artifact_family: "code",
      format: "python",
      filename: "script.py",
      source_text: "Create a script.",
    },
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifact_contract_version: "1.0" });
    },
  );
  await archiveArtifact(
    "agent-col",
    "artifact--abc",
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifact_contract_version: "1.0" });
    },
  );
  await restoreArtifact(
    "agent-col",
    "artifact--abc",
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifact_contract_version: "1.0" });
    },
  );
  await deleteArtifact(
    "agent-col",
    "artifact--abc",
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifact_id: "artifact--abc", deleted: true });
    },
  );
  await updateArtifactMetadata(
    "agent-col",
    "artifact--abc",
    {
      display_label: "Renamed Script",
      filename: "renamed_script.py",
    },
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifact_contract_version: "1.0" });
    },
  );
  await createArtifactVersion(
    "agent-col",
    "artifact--abc",
    {
      session_id: "session--2",
      user_id: "wifiknight",
      content: "print('updated')\n",
      filename: "script_v2.py",
      display_label: "Script v2",
    },
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifact_contract_version: "1.0" });
    },
  );
  await listArtifacts(
    "agent-col",
    { lifecycle_status: "archived", authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { artifact_contract_version: "1.0" });
    },
  );

  assert.equal(calls[0][0], "/api/projects/agent-col/artifacts?limit=5");
  assert.equal(calls[0][1].method, "GET");
  assert.equal(calls[1][0], "/api/projects/agent-col/artifacts/artifact--abc");
  assert.equal(calls[1][1].method, "GET");
  assert.equal(calls[2][0], "/api/projects/agent-col/artifacts");
  assert.equal(calls[2][1].method, "POST");
  assert.equal(calls[2][1].headers.Authorization, "Bearer token-1");
  assert.equal(
    calls[3][0],
    "/api/projects/agent-col/artifacts/artifact--abc/archive",
  );
  assert.equal(calls[3][1].method, "POST");
  assert.equal(calls[3][1].headers.Authorization, "Bearer token-1");
  assert.equal(
    calls[4][0],
    "/api/projects/agent-col/artifacts/artifact--abc/restore",
  );
  assert.equal(calls[4][1].method, "POST");
  assert.equal(calls[4][1].headers.Authorization, "Bearer token-1");
  assert.equal(
    calls[5][0],
    "/api/projects/agent-col/artifacts/artifact--abc",
  );
  assert.equal(calls[5][1].method, "DELETE");
  assert.equal(calls[5][1].headers.Authorization, "Bearer token-1");
  assert.equal(
    calls[6][0],
    "/api/projects/agent-col/artifacts/artifact--abc/metadata",
  );
  assert.equal(calls[6][1].method, "PATCH");
  assert.equal(calls[6][1].headers.Authorization, "Bearer token-1");
  assert.equal(
    calls[6][1].body,
    JSON.stringify({
      display_label: "Renamed Script",
      filename: "renamed_script.py",
    }),
  );
  assert.equal(
    calls[7][0],
    "/api/projects/agent-col/artifacts/artifact--abc/versions",
  );
  assert.equal(calls[7][1].method, "POST");
  assert.equal(calls[7][1].headers.Authorization, "Bearer token-1");
  assert.equal(
    calls[7][1].body,
    JSON.stringify({
      session_id: "session--2",
      user_id: "wifiknight",
      content: "print('updated')\n",
      filename: "script_v2.py",
      display_label: "Script v2",
    }),
  );
  assert.equal(
    calls[8][0],
    "/api/projects/agent-col/artifacts?lifecycle_status=archived",
  );
  assert.equal(calls[8][1].method, "GET");
  assert.equal(
    calls[2][1].body,
    JSON.stringify({
      session_id: "session--1",
      user_id: "wifiknight",
      artifact_family: "code",
      format: "python",
      filename: "script.py",
      source_text: "Create a script.",
    }),
  );
});

test("artifact API wrappers reject invalid project and artifact identifiers", async () => {
  assert.throws(
    () => listBlueprints("bad/slash", {}, async () => jsonResponse(200, {})),
    /invalid/i,
  );
  assert.throws(
    () => getBlueprint(
      "agent-col",
      "bad/slash",
      async () => jsonResponse(200, {}),
    ),
    /invalid/i,
  );
  assert.throws(
    () => listArtifacts("bad/slash", {}, async () => jsonResponse(200, {})),
    /invalid/i,
  );
  assert.throws(
    () => getArtifact(
      "agent-col",
      "bad/slash",
      async () => jsonResponse(200, {}),
    ),
    /invalid/i,
  );
});

test("inspectMemory calls the canonical user memory inspection path", async () => {
  const calls = [];
  await inspectMemory(
    "wifiknight",
    { after_event_id: "response_length--cursor--approved" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        profile: { active_preferences: {} },
        unresolved_proposals: [],
        events: [],
        next_event_id: null,
      });
    },
  );

  assert.equal(
    calls[0][0],
    "/api/users/wifiknight/memory?after_event_id=response_length--cursor--approved",
  );
  assert.equal(calls[0][1].method, "GET");
});

test("inspectMemory rejects invalid user and event cursors", async () => {
  assert.throws(
    () => inspectMemory("bad/slash", {}, async () => jsonResponse(200, {})),
    /invalid/i,
  );
  assert.throws(
    () => inspectMemory(
      "wifiknight",
      { after_event_id: "bad/slash" },
      async () => jsonResponse(200, {}),
    ),
    /invalid/i,
  );
});

test("decideMemoryProposal calls the direct proposal decision path", async () => {
  const calls = [];
  const result = await decideMemoryProposal(
    "wifiknight",
    "response_length--proposal-1",
    "approve",
    { authToken: "google-id-token" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        action: { action_name: "approve_memory_signal", status: "completed" },
        profile: { active_preferences: {} },
      });
    },
  );

  assert.deepEqual(result.action, {
    action_name: "approve_memory_signal",
    status: "completed",
  });
  assert.equal(
    calls[0][0],
    "/api/users/wifiknight/memory/proposals/response_length--proposal-1/approve",
  );
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].headers.Authorization, "Bearer google-id-token");
  assert.equal(calls[0][1].body, undefined);
});


test("selectMemoryClarification calls the direct clarification selection path", async () => {
  const calls = [];
  const result = await selectMemoryClarification(
    "wifiknight",
    "agent-col",
    "memory-clarification--clarification-1",
    {
      session_id: "session-1",
      selected_candidate_index: 0,
    },
    {
      authToken: "google-id-token",
      idempotencyKey: "clarification-direct-key-1",
    },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        action: { action_name: "propose_memory_signal", status: "completed" },
        memory_proposal: {
          proposal_id: "response_length--proposal-1",
          category: "response_length",
          proposed_value: "detailed",
          policy_version: "2.0",
          expires_at: "2026-08-21T23:00:00Z",
        },
      });
    },
  );

  assert.deepEqual(result.memory_proposal, {
    proposal_id: "response_length--proposal-1",
    category: "response_length",
    proposed_value: "detailed",
    policy_version: "2.0",
    expires_at: "2026-08-21T23:00:00Z",
  });
  assert.equal(
    calls[0][0],
    "/api/users/wifiknight/projects/agent-col/memory/clarifications/memory-clarification--clarification-1/select",
  );
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].headers.Authorization, "Bearer google-id-token");
  assert.equal(calls[0][1].headers["Idempotency-Key"], "clarification-direct-key-1");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    session_id: "session-1",
    selected_candidate_index: 0,
  });
});


test("selectMemoryClarification rejects invalid direct selection input", async () => {
  await assert.rejects(
    () => selectMemoryClarification(
      "bad/slash",
      "agent-col",
      "memory-clarification--clarification-1",
      {
        session_id: "session-1",
        selected_candidate_index: 0,
      },
      { idempotencyKey: "clarification-direct-key-1" },
      async () => jsonResponse(200, {}),
    ),
    /invalid/i,
  );
  await assert.rejects(
    () => selectMemoryClarification(
      "wifiknight",
      "agent-col",
      "memory-clarification--clarification-1",
      {
        session_id: "session-1",
        selected_candidate_index: true,
      },
      { idempotencyKey: "clarification-direct-key-1" },
      async () => jsonResponse(200, {}),
    ),
    /candidate index/i,
  );
  await assert.rejects(
    () => selectMemoryClarification(
      "wifiknight",
      "agent-col",
      "memory-clarification--clarification-1",
      {
        session_id: "session-1",
        selected_candidate_index: 0,
      },
      {},
      async () => jsonResponse(200, {}),
    ),
    /idempotency/i,
  );
});

test("revokeMemorySignal calls the canonical active memory revoke path", async () => {
  const calls = [];
  const result = await revokeMemorySignal(
    "wifiknight",
    "response_length--signal-1",
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        action: { action_name: "revoke_memory_signal", status: "completed" },
        profile: { active_preferences: {} },
      });
    },
  );

  assert.deepEqual(result.action, {
    action_name: "revoke_memory_signal",
    status: "completed",
  });
  assert.equal(
    calls[0][0],
    "/api/users/wifiknight/memory/signals/response_length--signal-1/revoke",
  );
  assert.equal(calls[0][1].method, "POST");
});

test("deleteMemorySignal calls the canonical active memory delete path", async () => {
  const calls = [];
  const result = await deleteMemorySignal(
    "wifiknight",
    "response_length--signal-1",
    async (path, init) => {
      calls.push([path, init]);
      return new Response(null, { status: 204 });
    },
  );

  assert.equal(result, null);
  assert.equal(
    calls[0][0],
    "/api/users/wifiknight/memory/signals/response_length--signal-1",
  );
  assert.equal(calls[0][1].method, "DELETE");
});

test("memory mutation wrappers reject invalid identifiers", async () => {
  assert.throws(
    () => decideMemoryProposal(
      "wifiknight",
      "response_length--proposal-1",
      "accepted",
      async () => jsonResponse(200, {}),
    ),
    /decision must be approve or reject/i,
  );
  assert.throws(
    () => decideMemoryProposal(
      "wifiknight",
      "bad/slash",
      "approve",
      async () => jsonResponse(200, {}),
    ),
    /invalid/i,
  );
  assert.throws(
    () => revokeMemorySignal(
      "bad/slash",
      "response_length--signal-1",
      async () => jsonResponse(200, {}),
    ),
    /invalid/i,
  );
  assert.throws(
    () => deleteMemorySignal(
      "wifiknight",
      "bad/slash",
      async () => new Response(null, { status: 204 }),
    ),
    /invalid/i,
  );
});

test("note API wrappers use canonical user workspace note paths", async () => {
  const calls = [];
  await listNotes(
    "wifiknight",
    "agent-col",
    { status_filter: "archived", limit: 10, cursor: "note--cursor", authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        note_contract_version: "1.0",
        notes: [],
        next_note_id: null,
      });
    },
  );
  await getNote(
    "wifiknight",
    "agent-col",
    "note--1",
    { limit: 20, authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { note_contract_version: "1.0" });
    },
  );
  await createNoteCorrection(
    "wifiknight",
    "agent-col",
    "note--1",
    {
      expected_revision: 2,
      note_kind: "constraint",
      title: "API version",
      body: "Use API version 3.",
      source_session_id: "session--1",
      source_message_ids: ["message--1"],
    },
    { idempotencyKey: "note-correction--1", authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { note_contract_version: "1.0" });
    },
  );
  await createNoteProposal(
    "wifiknight",
    "agent-col",
    {
      session_id: "session--1",
      note_kind: "constraint",
      title: "API version",
      body: "Use API version 2.",
    },
    { idempotencyKey: "note-proposal--1", authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { note_contract_version: "1.0" });
    },
  );
  await decideNoteProposal(
    "wifiknight",
    "agent-col",
    "note-proposal--1",
    "approve",
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        note_contract_version: "1.0",
        action: {
          action_name: "approve_collaborative_note",
          status: "completed",
        },
        event: { event_id: "note-event--1" },
      });
    },
  );
  await archiveNote(
    "wifiknight",
    "agent-col",
    "note--1",
    { expected_revision: 2 },
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { note_contract_version: "1.0" });
    },
  );
  await restoreNote(
    "wifiknight",
    "agent-col",
    "note--1",
    { expected_revision: 3 },
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { note_contract_version: "1.0" });
    },
  );
  await deleteNote(
    "wifiknight",
    "agent-col",
    "note--1",
    { expected_revision: 4 },
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return new Response(null, { status: 204 });
    },
  );

  assert.equal(
    calls[0][0],
    "/api/users/wifiknight/projects/agent-col/notes?limit=10&status_filter=archived&cursor=note--cursor",
  );
  assert.equal(calls[0][1].method, "GET");
  assert.equal(calls[0][1].headers.Authorization, "Bearer token-1");
  assert.equal(
    calls[1][0],
    "/api/users/wifiknight/projects/agent-col/notes/note--1?limit=20",
  );
  assert.equal(calls[1][1].method, "GET");
  assert.equal(
    calls[2][0],
    "/api/users/wifiknight/projects/agent-col/notes/note--1/corrections",
  );
  assert.equal(calls[2][1].method, "POST");
  assert.equal(calls[2][1].headers["Idempotency-Key"], "note-correction--1");
  assert.equal(calls[2][1].body, JSON.stringify({
    expected_revision: 2,
    note_kind: "constraint",
    title: "API version",
    body: "Use API version 3.",
    source_session_id: "session--1",
    source_message_ids: ["message--1"],
  }));
  assert.equal(
    calls[3][0],
    "/api/users/wifiknight/projects/agent-col/notes/proposals",
  );
  assert.equal(calls[3][1].method, "POST");
  assert.equal(calls[3][1].headers.Authorization, "Bearer token-1");
  assert.equal(calls[3][1].headers["Idempotency-Key"], "note-proposal--1");
  assert.equal(calls[3][1].body, JSON.stringify({
    session_id: "session--1",
    note_kind: "constraint",
    title: "API version",
    body: "Use API version 2.",
  }));
  assert.equal(
    calls[4][0],
    "/api/users/wifiknight/projects/agent-col/notes/proposals/note-proposal--1/approve",
  );
  assert.equal(calls[4][1].method, "POST");
  assert.equal(calls[4][1].headers.Authorization, "Bearer token-1");
  assert.equal(calls[4][1].body, undefined);
  assert.equal(
    calls[5][0],
    "/api/users/wifiknight/projects/agent-col/notes/note--1/archive",
  );
  assert.equal(calls[5][1].body, JSON.stringify({ expected_revision: 2 }));
  assert.equal(
    calls[6][0],
    "/api/users/wifiknight/projects/agent-col/notes/note--1/restore",
  );
  assert.equal(calls[6][1].body, JSON.stringify({ expected_revision: 3 }));
  assert.equal(
    calls[7][0],
    "/api/users/wifiknight/projects/agent-col/notes/note--1",
  );
  assert.equal(calls[7][1].method, "DELETE");
  assert.equal(calls[7][1].body, JSON.stringify({ expected_revision: 4 }));
});

test("note API wrappers reject invalid identifiers and filters", async () => {
  assert.throws(
    () => listNotes("bad/slash", "agent-col", {}, async () => jsonResponse(200, {})),
    /invalid/i,
  );
  assert.throws(
    () => listNotes("wifiknight", "agent-col", { status_filter: "pending" }, async () => jsonResponse(200, {})),
    /status_filter/i,
  );
  assert.throws(
    () => getNote("wifiknight", "agent-col", "bad/slash", {}, async () => jsonResponse(200, {})),
    /invalid/i,
  );
  assert.throws(
    () => decideNoteProposal("wifiknight", "agent-col", "bad/slash", "approve", async () => jsonResponse(200, {})),
    /invalid/i,
  );
  assert.throws(
    () => decideNoteProposal("wifiknight", "agent-col", "note--1", "accepted", async () => jsonResponse(200, {})),
    /decision must be approve or reject/i,
  );
});

test("listChatSessions calls the bounded user project sessions path", async () => {
  const calls = [];
  await listChatSessions(
    "wifiknight",
    "agent-col",
    { limit: 20 },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, { chat_contract_version: "1.0", sessions: [] });
    },
  );

  assert.equal(
    calls[0][0],
    "/api/users/wifiknight/projects/agent-col/chat-sessions?limit=20",
  );
  assert.equal(calls[0][1].method, "GET");
});

test("getChatSession calls the bounded chat transcript path", async () => {
  const calls = [];
  await getChatSession(
    "wifiknight",
    "agent-col",
    "session--123",
    { limit: 50 },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        chat_contract_version: "1.0",
        messages: [],
      });
    },
  );

  assert.equal(
    calls[0][0],
    "/api/users/wifiknight/projects/agent-col/chat-sessions/session--123?limit=50",
  );
  assert.equal(calls[0][1].method, "GET");
});

test("workspace wrappers list and create user workspace containers", async () => {
  const calls = [];
  await listWorkspaces(
    "wifiknight",
    { limit: 20, authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        workspace_contract_version: "1.0",
        workspaces: [],
      });
    },
  );
  await createWorkspace(
    "wifiknight",
    { display_name: "Study Plans" },
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return jsonResponse(200, {
        workspace_contract_version: "1.0",
        workspace: {
          workspace_id: "project--abc--study-plans",
          display_name: "Study Plans",
          is_default: false,
        },
      });
    },
  );

  assert.equal(
    calls[0][0],
    "/api/users/wifiknight/workspaces?limit=20",
  );
  assert.equal(calls[0][1].method, "GET");
  assert.equal(calls[0][1].headers.Authorization, "Bearer token-1");
  assert.equal(calls[1][0], "/api/users/wifiknight/workspaces");
  assert.equal(calls[1][1].method, "POST");
  assert.equal(calls[1][1].body, JSON.stringify({
    display_name: "Study Plans",
  }));
});

test("workspace wrapper deletes user workspace containers", async () => {
  const calls = [];
  await deleteWorkspace(
    "wifiknight",
    "project--abc--study-plans",
    { authToken: "token-1" },
    async (path, init) => {
      calls.push([path, init]);
      return new Response(null, { status: 204 });
    },
  );

  assert.equal(
    calls[0][0],
    "/api/users/wifiknight/workspaces/project--abc--study-plans",
  );
  assert.equal(calls[0][1].method, "DELETE");
  assert.equal(calls[0][1].headers.Authorization, "Bearer token-1");
});
