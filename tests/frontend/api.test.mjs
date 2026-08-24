import test from "node:test";
import assert from "node:assert/strict";

import {
  apiFetchJson,
  archiveArtifact,
  createArtifact,
  getAuthConfig,
  getAuthSession,
  getArtifact,
  getBlueprint,
  getChatSession,
  inspectMemory,
  listArtifacts,
  listChatSessions,
  listBlueprintFeedback,
  listBlueprints,
  createWorkspace,
  listWorkspaces,
  deleteMemorySignal,
  revokeMemorySignal,
} from "../../frontend/api.mjs";

function jsonResponse(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

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

test("getAuthSession calls the canonical auth session path", async () => {
  const calls = [];
  const result = await getAuthSession("google-id-token", async (path, init) => {
    calls.push([path, init]);
    return jsonResponse(200, {
      auth_contract_version: "1.0",
      auth_mode: "google_oidc",
      authenticated: true,
      local_development: false,
      user_id: "google--123",
    });
  });

  assert.equal(result.user_id, "google--123");
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
