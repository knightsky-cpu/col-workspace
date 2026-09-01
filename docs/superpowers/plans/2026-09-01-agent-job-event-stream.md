# Agent Job Event Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated public AgentJob SSE stream so the Agents panel can receive job lifecycle updates without relying on aggressive REST polling or mixing orchestration events into `/api/chat/stream`.

**Architecture:** The REST `/agent/jobs` list remains the authoritative snapshot and fallback path. The new stream is a public projection layer that emits sanitized job snapshots at connection start and then emits public lifecycle updates from job/event changes. The first pass may use bounded server polling internally against the existing repository; it must expose a stable stream contract so later Firestore watch/subagent worker upgrades do not change the frontend API.

**Tech Stack:** FastAPI `StreamingResponse`, Server-Sent Events, existing `AgentJobRepository`, existing frontend Fetch/ReadableStream SSE parser patterns, vanilla JS Agents panel renderer, pytest, Node test runner.

**Spec:** User-approved Agent Panel concept and accepted AgentJob note-lifecycle pass at checkpoint `eb641a24daafaa25981d8bbe5ddcf7e50d66b68c`.

## Global Constraints

- Do not route agent/job events through `/api/chat` or `/api/chat/stream`.
- Backend job state remains authoritative; frontend renders the public projection only.
- Do not expose internal prompts, reasoning, raw agent IDs, credentials, lease owners, idempotency keys, or tool payloads.
- Preserve current REST job list/detail/events/cancel/retry endpoints.
- Preserve note and memory approval gates; streaming visibility must not activate proposals.
- Preserve the existing `300ms` polling fallback for stream failure or unsupported browsers.
- Keep this pass to stream transport and frontend subscription; do not implement new memory/artifact background job execution here.

---

## Source-Backed Current State

- `main.py` already exposes `/api/users/{user_id}/projects/{project_id}/agent/jobs` and returns sanitized `AgentJobListResponse`.
- `main.py` already exposes `/agent/jobs/{job_id}/events` and filters to public events.
- `main.py` keeps public projection local through `AgentJobPublic`, `AgentJobEventPublic`, `_public_agent_job(...)`, and `_public_agent_job_event(...)`.
- `frontend/api.mjs` already has a generic `apiFetchSse(...)` parser for chat streams.
- `frontend/api.mjs` only has `listAgentJobs(...)` for agent job data; there is no dedicated stream wrapper yet.
- `frontend/app.mjs` currently schedules `300ms` refreshes while chat is pending or jobs are active.
- `agent_job_repository.py` can list jobs and list public events, but it does not provide a stream/watch API.

## Task 1: Backend Stream Endpoint

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Produces: `GET /api/users/{user_id}/projects/{project_id}/agent/jobs/stream?session_id=...&limit=50`
- Produces SSE events:
  - `event: snapshot`
  - `data: {"agent_job_contract_version":"1.0","jobs":[...]}`
  - `event: heartbeat`
  - `data: {"agent_job_contract_version":"1.0"}`
  - `event: error`
  - `data: {"detail":"Agent job stream failed.","status":500}`

- [ ] **Step 1: Write the failing route test**

```python
@pytest.mark.asyncio
async def test_agent_job_stream_emits_public_snapshot(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.agent_job_repository.jobs = [
        make_agent_job(
            status="running",
            lease_owner="worker-private",
            result_refs={"artifact_id": "artifact-1"},
        )
    ]

    response = await client.get(
        "/api/users/user-1/projects/project-1/agent/jobs/stream",
        params={"session_id": "session-1", "limit": 50},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: snapshot" in response.text
    assert '"status":"running"' in response.text
    assert "worker-private" not in response.text
```

- [ ] **Step 2: Run RED**

Run: `venv/bin/python -m pytest tests/test_main.py::test_agent_job_stream_emits_public_snapshot -q`

Expected: fail with `404 Not Found` because the endpoint does not exist.

- [ ] **Step 3: Implement minimal endpoint**

Add a FastAPI `StreamingResponse` route next to the existing agent job routes. Reuse `_resolve_effective_user_id(...)`, `_resolve_effective_project_id(...)`, repository `list_jobs(...)`, and `_public_agent_job(...)`. For the first implementation, emit one `snapshot` event and close. This proves contract and projection safety before long-lived streaming behavior.

- [ ] **Step 4: Verify GREEN**

Run: `venv/bin/python -m pytest tests/test_main.py::test_agent_job_stream_emits_public_snapshot -q`

Expected: pass.

## Task 2: Backend Short-Lived Follow Stream

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: Task 1 route and projection.
- Produces: bounded repeated snapshots while non-terminal jobs exist or until a small max cycle count is reached.

- [ ] **Step 1: Write the failing follow test**

```python
@pytest.mark.asyncio
async def test_agent_job_stream_rechecks_until_job_reaches_terminal_state(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.agent_job_repository.job_batches = [
        [make_agent_job(status="running")],
        [make_agent_job(status="completed")],
    ]

    response = await client.get(
        "/api/users/user-1/projects/project-1/agent/jobs/stream",
        params={"session_id": "session-1", "limit": 50},
    )

    assert response.status_code == 200
    assert response.text.count("event: snapshot") >= 2
    assert '"status":"running"' in response.text
    assert '"status":"completed"' in response.text
```

- [ ] **Step 2: Run RED**

Run: `venv/bin/python -m pytest tests/test_main.py::test_agent_job_stream_rechecks_until_job_reaches_terminal_state -q`

Expected: fail because Task 1 only emits one snapshot.

- [ ] **Step 3: Implement bounded follow loop**

Inside the stream generator, poll the repository on a small backend interval and emit a new snapshot only when the public payload changes. Stop after terminal state or a conservative max cycle count in tests. In production, keep the connection alive with heartbeats and let disconnect end the loop.

- [ ] **Step 4: Verify GREEN**

Run: `venv/bin/python -m pytest tests/test_main.py::test_agent_job_stream_rechecks_until_job_reaches_terminal_state -q`

Expected: pass.

## Task 3: Frontend Stream Wrapper

**Files:**
- Modify: `frontend/api.mjs`
- Test: `tests/frontend/api.test.mjs`

**Interfaces:**
- Produces: `streamAgentJobs(userId, projectId, options, handlers, fetchLike)`
- Calls `handlers.onSnapshot(payload)` for `snapshot`.
- Calls `handlers.onHeartbeat(payload)` for `heartbeat`.
- Throws existing `ApiError` shape for stream failure.

- [ ] **Step 1: Write the failing API test**

```js
test("streamAgentJobs reads public snapshot events", async () => {
  const frames = [
    `event: snapshot\ndata: {"agent_job_contract_version":"1.0","jobs":[{"job_id":"job-1","status":"running"}]}\n\n`,
  ];
  const snapshots = [];

  await streamAgentJobs(
    "user-1",
    "project-1",
    { session_id: "session-1" },
    { onSnapshot(payload) { snapshots.push(payload); } },
    async (path) => new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frames.join("")));
        controller.close();
      },
    }), { status: 200, headers: { "Content-Type": "text/event-stream" } }),
  );

  assert.equal(snapshots[0].jobs[0].job_id, "job-1");
});
```

- [ ] **Step 2: Run RED**

Run: `node --test tests/frontend/api.test.mjs --test-name-pattern "streamAgentJobs reads public snapshot events"`

Expected: fail because `streamAgentJobs` is not exported.

- [ ] **Step 3: Implement wrapper**

Generalize or reuse the existing SSE parsing logic without duplicating unsafe URL handling. Keep same-origin validation, auth token support, and query validation consistent with `listAgentJobs(...)`.

- [ ] **Step 4: Verify GREEN**

Run: `node --test tests/frontend/api.test.mjs --test-name-pattern "streamAgentJobs reads public snapshot events"`

Expected: pass.

## Task 4: Agents Panel Subscription

**Files:**
- Modify: `frontend/app.mjs`
- Test: `tests/frontend/app-runtime.test.mjs`

**Interfaces:**
- Consumes: `streamAgentJobs(...)`.
- Preserves: existing `listAgentJobs(...)` fallback.
- Produces: live Agents panel updates from stream snapshots.

- [ ] **Step 1: Write the failing runtime test**

```js
test("agent panel updates from job stream before polling interval", async (t) => {
  const { contextForm, elements } = installOrdinaryChatRuntimeDom();
  const stream = createControlledSseResponse();
  const agentStream = createControlledSseResponse();
  let listCalls = 0;

  globalThis.fetch = async (path) => {
    if (path.includes("/agent/jobs/stream")) return agentStream.response;
    if (path.includes("/agent/jobs")) {
      listCalls += 1;
      return jsonResponse(200, { agent_job_contract_version: "1.0", jobs: [] });
    }
    if (path === "/api/chat/stream") return stream.response;
    return standardWorkspaceResponse(path);
  };

  await import(`../../frontend/app.mjs?agent-stream-${Date.now()}`);
  await contextForm.onsubmit({ preventDefault() {}, currentTarget: contextForm });
  agentStream.complete({
    agent_job_contract_version: "1.0",
    jobs: [{ job_id: "job-1", status: "running", agent_label: "Note Curator", display_label: "Workspace note" }],
  });

  assert.match(textTree(elements.get("[data-agents-panel]")), /Note Curator/);
  assert.equal(listCalls <= 1, true);
});
```

- [ ] **Step 2: Run RED**

Run: `node --test tests/frontend/app-runtime.test.mjs --test-name-pattern "agent panel updates from job stream before polling interval"`

Expected: fail because the frontend never opens an agent job stream.

- [ ] **Step 3: Implement subscription lifecycle**

Open a job stream after workspace context is selected. Reset/close the stream when context changes, user changes, session changes, or logout occurs. On stream snapshot, call the existing state reducer used by `loadAgentJobs`. If the stream errors or closes unexpectedly, fall back to the existing `300ms` burst polling while work is pending/active.

- [ ] **Step 4: Verify GREEN**

Run: `node --test tests/frontend/app-runtime.test.mjs --test-name-pattern "agent panel updates from job stream before polling interval"`

Expected: pass.

## Focused Verification For The Pass

- `venv/bin/python -m pytest tests/test_main.py::test_agent_job_stream_emits_public_snapshot tests/test_main.py::test_agent_job_stream_rechecks_until_job_reaches_terminal_state -q`
- `node --test tests/frontend/api.test.mjs --test-name-pattern "streamAgentJobs"`
- `node --test tests/frontend/app-runtime.test.mjs --test-name-pattern "agent panel"`
- `node --test tests/frontend/app-runtime.test.mjs tests/frontend/api.test.mjs`
- `venv/bin/python -m py_compile main.py`
- `git diff --check`

Broader tests should be added only if the implementation touches shared auth, general SSE parsing, global workspace/session state, or existing chat streaming behavior.

## Manual Verification Targets

1. Start local dev with `AGENT_COL_AUTH_MODE=local_dev venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000`.
2. Open the workspace and confirm the Agents panel remains collapsed by default and can expand.
3. Submit: `Make an artifact and save a workspace note about the decision.`
4. Expected: the Agents panel shows Note Curator queued/running/completed without waiting for the old polling cadence; chat stream remains conversational.
5. Confirm terminal logs do not contain private prompt/tool payloads for agent stream responses.
6. Confirm `/api/chat/stream` still returns only chat response events and not agent job lifecycle events.

## Scope Notes

- This pass does not add true Firestore watch listeners unless the source review shows they can be introduced narrowly and tested without destabilizing Cloud Run behavior.
- This pass does not add cancel/retry UI controls.
- This pass does not move memory/artifact execution to background workers.
- This pass does not remove REST polling; polling remains the fallback and recovery path.
