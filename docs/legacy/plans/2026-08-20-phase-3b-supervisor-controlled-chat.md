# Phase 3B Supervisor-Controlled Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `POST /api/chat` project-aware and delegate every chat turn to
the tool-free ADK `SupervisorRuntime` while preserving Firestore as the sole
durable memory source.

**Architecture:** FastAPI continues to own validation, Firestore reads and
writes, and HTTP error mapping. The route creates one immutable pre-message
context snapshot from a bounded profile/history read, persists the user
message, and passes the snapshot plus the current message to the invocation-
scoped supervisor runtime. The runtime returns the final answer and empty
receipt collections because Task 3 enables no tools.

**Tech Stack:** Python 3.14, FastAPI 0.141.1, Google ADK 2.7.0, Google GenAI
2.18.1, Pydantic 2.13.4, Firestore 2.28.1, pytest 9.1.1

**Spec:**
`docs/superpowers/specs/2026-08-19-hybrid-adk-supervisor-contract-design.md`

## Global Constraints

- Execute inline without subagents.
- Keep Firestore as the only durable memory and artifact source.
- Create one fresh ADK session per turn; do not persist ADK session state.
- Read profile and at most 20 historical messages concurrently.
- Build transient context only from the pre-message snapshot.
- Pass the current user message exactly once through `SupervisorTurnContext`.
- Persist the incoming user message before invoking ADK.
- Persist a model message only after one successful final response.
- Require `project_id`, `session_id`, `user_id`, and `message` as strict,
  validated identifiers/text.
- Return empty `actions`, `artifacts`, and `citations` in this tool-free pass.
- Map Firestore failures to 500, runtime/provider failures to 502, and whole-
  turn timeouts to 504.
- Preserve `GET /` and `POST /api/synthesize` behavior.
- Add no tools, specialists, artifact reads, feedback, Vertex configuration,
  streaming, authentication, or frontend behavior.
- Do not commit or push until manual verification succeeds and the user
  explicitly authorizes the checkpoint.

---

### Task 1: Add strict project-aware chat and receipt schemas

**Files:**

- Modify: `schemas.py`
- Modify: `tests/test_schemas.py`

**Interfaces:**

- Produces `ChatRequest`, `ChatResponse`, `AgentActionReceipt`,
  `ArtifactReference`, and `CitationReference`.
- `ChatRequest` uses existing `IdentifierStr` and `NonEmptyStr` constraints.
- `ChatResponse` defaults each receipt collection to a new empty list.

- [ ] **Step 1: Write the failing schema tests**

Add tests that import the five new schemas and prove:

```python
request = ChatRequest.model_validate(
    {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "message": "Help me plan this.",
    }
)
assert request.project_id == "project-1"

response = ChatResponse(response="Answer")
assert response.model_dump(mode="json") == {
    "response": "Answer",
    "actions": [],
    "artifacts": [],
    "citations": [],
}
```

Also prove missing/invalid identifiers, whitespace messages, extra fields,
invalid action names/statuses, malformed artifact references, and non-HTTP(S)
citations fail Pydantic validation.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m pytest tests/test_schemas.py -q
```

Expected: collection fails because the new schema classes do not exist.

- [ ] **Step 3: Implement the schema contracts**

Use `StrictModel`, existing constrained aliases, `HttpUrl`, `Literal`, and
`Field(default_factory=list)`. Allowlisted public actions are
`synthesize_project`, `google_search`, `url_context`, and
`record_blueprint_feedback`; only status `completed` is public.

- [ ] **Step 4: Verify GREEN**

Run the schema tests and confirm all pass.

---

### Task 2: Make supervisor results receipt-ready without enabling tools

**Files:**

- Modify: `supervisor_runtime.py`
- Modify: `tests/test_supervisor_runtime.py`

**Interfaces:**

- `SupervisorTurnResult` produces `response`, `actions`, `artifacts`, and
  `citations` as immutable tuples.
- Task 3 runtime execution always returns empty receipt tuples.

- [ ] **Step 1: Write the failing result test**

Extend the real happy-path test to assert:

```python
assert result.actions == ()
assert result.artifacts == ()
assert result.citations == ()
```

- [ ] **Step 2: Verify RED**

Run the named happy-path test. Expected: `SupervisorTurnResult` has no
`actions` attribute.

- [ ] **Step 3: Add typed empty receipt tuples**

Import the receipt schemas and add default empty tuple fields to the frozen
result dataclass. Do not parse ADK events for tools in this pass.

- [ ] **Step 4: Verify GREEN**

Run `tests/test_supervisor_runtime.py` and confirm all runtime tests pass.

---

### Task 3: Construct the supervisor in FastAPI lifespan

**Files:**

- Modify: `main.py`
- Modify: `tests/test_main.py`

**Interfaces:**

- Lifespan consumes `create_supervisor_app()` and
  `SupervisorRuntime.from_app(app)`.
- Lifespan publishes the immutable runtime as `app.state.supervisor`.
- ADK exposes no close operation in this design; existing GenAI and Firestore
  shutdown behavior remains unchanged.

- [ ] **Step 1: Add a fake supervisor boundary and failing lifecycle test**

Create `FakeSupervisorRuntime` with a recorded `run_turn` method, patch the
supervisor factory in the service fixture, and assert the active lifespan
stores the fake runtime on `main.app.state.supervisor`.

- [ ] **Step 2: Verify RED**

Run the named lifespan test. Expected: `app.state.supervisor` is absent.

- [ ] **Step 3: Implement lifespan construction**

Create the supervisor app/runtime after Firestore initialization and before
yield. If construction fails, close the already-created Firestore and GenAI
resources before re-raising. Do not change `/api/synthesize` ownership.

- [ ] **Step 4: Verify GREEN**

Run the lifecycle and synthesis tests. Expected: supervisor state exists and
all existing resources still close.

---

### Task 4: Replace direct chat generation with the supervisor

**Files:**

- Modify: `main.py`
- Modify: `tests/test_main.py`

**Interfaces:**

- Chat consumes `ChatRequest` from `schemas.py`.
- `_build_model_input_context(profile, history)` returns a tuple containing
  one user-role `types.Content` data envelope or an empty tuple.
- Chat calls `SupervisorRuntime.run_turn(SupervisorTurnContext(...))`.
- Chat returns `ChatResponse` with runtime-derived receipt collections.

- [ ] **Step 1: Rewrite the success test for the approved public behavior**

Send `project_id` in the request and assert:

```python
assert response.json() == {
    "response": "Generated answer",
    "actions": [],
    "artifacts": [],
    "citations": [],
}
```

Prove profile/history reads use `asyncio.gather`, history uses `limit=20`, the
user write precedes supervisor execution, the model write follows it, server-
owned identifiers reach `SupervisorTurnContext`, historical/profile data are
wrapped as untrusted transient data, and the current message does not appear
inside `model_input_context`.

- [ ] **Step 2: Verify RED**

Run the named chat success test. Expected: response lacks receipt fields and
the fake supervisor is never called.

- [ ] **Step 3: Implement the minimal route**

Remove the direct-chat model constants and helpers. Serialize validated
profile/history into delimited untrusted-data context, invoke the supervisor,
persist only its successful final response, and return its receipts.

- [ ] **Step 4: Verify GREEN**

Run the chat success and validation tests. Expected: project-aware response
passes and direct `client.aio.chats` is not used.

---

### Task 5: Lock down concurrency, failures, and persistence invariants

**Files:**

- Modify: `tests/test_main.py`
- Modify: `main.py` only when a new RED test identifies missing behavior.

**Interfaces:**

- 422: invalid request before any service access.
- 500: Firestore read/write or malformed stored history.
- 502: `SupervisorRuntimeError`, including missing final response.
- 504: `SupervisorTimeoutError`.

- [ ] **Step 1: Add one failing behavior test at a time**

Add focused tests for concurrent reads, required/valid `project_id`, 502
runtime translation, 504 timeout translation, no model write on supervisor
failure, and retained user write on supervisor failure.

- [ ] **Step 2: Verify each RED before production edits**

Run each named test and confirm the failure is the intended missing branch,
not fixture setup.

- [ ] **Step 3: Implement only the missing branch**

Catch typed runtime exceptions before the general runtime exception, use safe
class-only logs, and preserve the user-write/model-write ordering.

- [ ] **Step 4: Verify focused GREEN**

Run:

```bash
venv/bin/python -m pytest tests/test_schemas.py \
  tests/test_supervisor_runtime.py tests/test_main.py -v
```

- [ ] **Step 5: Run cross-cutting verification**

The public chat contract and shared lifespan are cross-cutting, so run:

```bash
venv/bin/python -m pip check
venv/bin/python -m pytest
venv/bin/python -m compileall -q main.py schemas.py supervisor_runtime.py \
  tests/test_main.py tests/test_schemas.py tests/test_supervisor_runtime.py
git diff --check
git status --short --branch
```

- [ ] **Step 6: Stop for manual verification**

Provide health, project-aware chat, direct synthesis regression, invalid-
request, and Firestore persistence checks. Do not checkpoint.

## Pass Acceptance Criteria

- Chat requires strict `project_id`, `session_id`, `user_id`, and `message`.
- Chat response always contains response/actions/artifacts/citations.
- Tool-free turns return empty receipt arrays derived from runtime results.
- Profile and bounded history reads start concurrently.
- Historical/profile context is transient and current input appears once.
- The user message persists before ADK invocation.
- Only a successful final Agent_Col response persists as model output.
- Firestore, runtime, and timeout errors map to 500, 502, and 504.
- Existing health and direct synthesis routes do not regress.
- No tools or future Task 4 behavior are introduced.
- Focused and full tests, compilation, dependency integrity, and whitespace
  validation pass.
- No commit or push occurs before manual acceptance and authorization.
