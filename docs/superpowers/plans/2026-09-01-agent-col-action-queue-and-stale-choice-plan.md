# Agent Col Action Queue And Stale Choice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix stale continuity-choice UI state and introduce a server-owned queued action architecture so one user request can reliably coordinate multiple governed effects.

**Architecture:** Apply the narrow stale-choice cleanup first because it is already root-caused in frontend state. Then design and implement queued action records as server-owned durable work items with receipts, idempotency, status, and approval-gated outcomes instead of letting one chat turn directly own multiple competing durable effects.

**Tech Stack:** FastAPI, Firestore-backed `MemoryEngine`, Pydantic schemas, JavaScript frontend state/view modules, Node test runner, pytest.

**Spec:** Source evidence from `docs/current-state.md`, `docs/repo-map.md`, `docs/debug-logging/2026-09-01-chat-routing-diagnostic-logging.md`, and `docs/legacy/backend/artifacts/2026-08-25-winning-core-phase-3-async-artifact-work.md`.

## Global Constraints

- Preserve existing chat turn idempotency, replay, ownership, and approval gates.
- Do not make pending memory or note proposals active until the user approves them.
- Do not let continuity context authorize tools, memory, notes, artifacts, or identity changes.
- `/api/chat/stream` remains ordinary-turn SSE; structured decisions stay on `/api/chat`.
- Queued work must have its own idempotency, ownership, status, retry, and failure state.
- Chat replay must return the original queued receipt, not re-run or rewrite the assistant response.
- No broad Cloud Tasks or private worker deployment in the first implementation slice.

---

### Task 1: Clear Stale Continuity Choices After A Later Ordinary Completion

**Files:**
- Modify: `frontend/state.mjs`
- Test: `tests/frontend/state.test.mjs`

**Interfaces:**
- Consumes: `completePendingTurn(state, response)`, `nextActiveContinuityChoices(current, response, completedSelection)`
- Produces: completed ordinary turns without new `continuity_choices` clear stale active continuity choices.

- [ ] **Step 1: Write the failing state test**

```javascript
test("ordinary completed turn without new continuity choices clears stale continuity choices", () => {
  const withChoices = {
    ...createInitialState(),
    activeContinuityChoices: [{
      choice_id: "choice-1",
      source_kind: "chat_session",
      source_id: "session-1",
      display_label: "Old shell helper chat",
      match_reason: "previous_chat",
    }],
  };
  const pending = beginPendingTurn(withChoices, {
    key: "chat--after-choice",
    body: { message: "Create a bash script artifact." },
  });

  const completed = completePendingTurn(pending, {
    response: "I created the artifact.",
    actions: [{ action_name: "create_artifact", status: "completed" }],
    artifacts: [{
      artifact_type: "single_file_artifact",
      project_id: "project-1",
      artifact_id: "artifact-1",
      schema_version: "1.0",
      display_label: "repo_helper.sh",
    }],
    continuity_choices: [],
  });

  assert.deepEqual(completed.activeContinuityChoices, []);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/frontend/state.test.mjs --test-name-pattern "ordinary completed turn without new continuity choices clears stale continuity choices"`

Expected: FAIL because `activeContinuityChoices` still contains `choice-1`.

- [ ] **Step 3: Implement the minimal state policy**

```javascript
function nextActiveContinuityChoices(current, response, completedSelection) {
  const choices = Array.isArray(response.continuity_choices)
    ? response.continuity_choices
    : [];
  if (choices.length > 0) {
    return choices;
  }
  if (completedSelection) {
    return [];
  }
  return [];
}
```

- [ ] **Step 4: Run focused frontend state tests**

Run: `node --test tests/frontend/state.test.mjs --test-name-pattern "continuity|choice|completed turn stores active continuity choices"`

Expected: PASS; existing failed-turn behavior still keeps authoritative partial choices.

- [ ] **Step 5: Run related frontend checks**

Run: `node --test tests/frontend/state.test.mjs tests/frontend/chat-view.test.mjs tests/frontend/requests.test.mjs`

Expected: PASS.

---

### Task 2: Define Queued Action Contract Without Executing Background Work

**Files:**
- Modify: `schemas.py`
- Modify: `frontend/state.mjs`
- Modify: `frontend/chat-view.mjs`
- Test: `tests/test_schemas.py` or nearest existing schema test file
- Test: `tests/frontend/state.test.mjs`
- Test: `tests/frontend/chat-view.test.mjs`

**Interfaces:**
- Consumes: `ChatResponse`, activity receipt rendering.
- Produces: `QueuedActionReceipt` schema and frontend storage/rendering for queued work receipts.

- [ ] **Step 1: Write failing schema test for queued action receipts**

```python
def test_chat_response_accepts_bounded_queued_action_receipts() -> None:
    response = ChatResponse(
        response="I queued the requested work.",
        queued_actions=[
            QueuedActionReceipt(
                job_id="job-1",
                action_kind="create_artifact",
                status="queued",
                display_label="Create repo_helper.sh",
                created_at=datetime(2026, 9, 1, tzinfo=UTC),
            ),
            QueuedActionReceipt(
                job_id="job-2",
                action_kind="propose_collaborative_note",
                status="queued",
                display_label="Remember Bash-only constraint",
                created_at=datetime(2026, 9, 1, tzinfo=UTC),
            ),
        ],
    )

    assert [item.action_kind for item in response.queued_actions] == [
        "create_artifact",
        "propose_collaborative_note",
    ]
```

- [ ] **Step 2: Run schema test to verify it fails**

Run: `venv/bin/python -m pytest <schema-test-file>::test_chat_response_accepts_bounded_queued_action_receipts -q`

Expected: FAIL because `QueuedActionReceipt` and `ChatResponse.queued_actions` do not exist.

- [ ] **Step 3: Implement receipt schema only**

Add:

```python
QueuedActionKind = Literal[
    "create_artifact",
    "propose_collaborative_note",
    "propose_memory_signal",
]
QueuedActionStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]

class QueuedActionReceipt(StrictModel):
    job_id: IdentifierStr
    action_kind: QueuedActionKind
    status: QueuedActionStatus
    display_label: DisplayLabelStr
    created_at: datetime
```

Extend `ChatResponse` and `ChatPartialFailureResponse` with:

```python
queued_actions: list[QueuedActionReceipt] = Field(default_factory=list, max_length=10)
```

- [ ] **Step 4: Add frontend state/render tests for queued receipts**

Add a state test proving queued receipts become activity entries with no raw internal payload. Add a chat-view test proving the visible receipt label and status render without exposing raw IDs as primary copy.

- [ ] **Step 5: Implement frontend receipt rendering**

Update `activityEntriesFromResponse(response)` to append `queued_action` entries from `response.queued_actions`. Update chat receipt rendering only if the current receipt component ignores activity entries.

- [ ] **Step 6: Run focused checks**

Run:

```bash
venv/bin/python -m pytest <schema-test-file>::test_chat_response_accepts_bounded_queued_action_receipts -q
node --test tests/frontend/state.test.mjs tests/frontend/chat-view.test.mjs
git diff --check
```

Expected: PASS.

---

### Task 3: Add Durable Action Job Domain And Repository

**Files:**
- Create: `agent_col_action_jobs.py`
- Create: `action_job_repository.py`
- Modify: `database.py`
- Test: `tests/test_agent_col_action_jobs.py`
- Test: `tests/test_action_job_repository.py`

**Interfaces:**
- Consumes: effective `user_id`, `project_id`, `session_id`, source turn/message IDs, requested action kind, display label, idempotency key.
- Produces: immutable queued action records with explicit owner/workspace scope and lifecycle transitions.

- [ ] **Step 1: Write failing domain tests**

Test five valid statuses, terminal immutability, retry linkage, owner/project/session preservation, and no prompt body in public projection.

- [ ] **Step 2: Implement domain models**

Define `ActionJob`, `ActionJobSnapshot`, `ActionJobStatus`, `ActionJobKind`, `ActionJobFailure`.

- [ ] **Step 3: Write failing repository tests**

Test idempotent enqueue replay, key conflict, list/detail ownership, queued-to-running lease, completion fencing, failure fencing, cancellation intent, and terminal immutability.

- [ ] **Step 4: Implement repository methods on `MemoryEngine`**

Use a new Firestore collection under the existing owner/workspace path:

```text
users/{user_id}/workspaces/{workspace_id}/action_jobs/{job_id}
```

- [ ] **Step 5: Run focused repository checks**

Run:

```bash
venv/bin/python -m pytest tests/test_agent_col_action_jobs.py tests/test_action_job_repository.py -q
git diff --check
```

Expected: PASS.

---

### Task 4: Enqueue Multi-Action Work From Chat Without Running It Yet

**Files:**
- Modify: `agent_col_turn_service.py`
- Modify: `main.py`
- Modify: `chat_turns.py`
- Test: `tests/test_agent_col_turn_service_artifacts.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: routing result, responder/tool requested effects, durable turn claim.
- Produces: one chat response that can include multiple `queued_actions` receipts while preserving existing artifact/note/memory approval gates.

- [ ] **Step 1: Write failing test for artifact plus note request**

Test a request like `Create a bash script artifact for a git repo helper and save a workspace note that it must stay Bash-only.` returns two queued receipts:

```python
assert [job.action_kind for job in response.queued_actions] == [
    "create_artifact",
    "propose_collaborative_note",
]
assert response.artifacts == []
assert response.collaborative_note_proposals == []
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL because current routing can return only the directly executed route/effects.

- [ ] **Step 3: Add enqueue-only orchestration path**

When the model/router identifies multiple governed actions for one turn, enqueue those actions and return queued receipts. Do not execute artifact generation or note proposal in this pass.

- [ ] **Step 4: Preserve replay**

Add a replay test proving the same idempotency key returns the original queued receipts and does not enqueue duplicate jobs.

- [ ] **Step 5: Run focused backend checks**

Run:

```bash
venv/bin/python -m pytest tests/test_agent_col_turn_service_artifacts.py tests/test_main.py -k "queued_action or artifact or collaborative_note or replay" -q
git diff --check
```

Expected: PASS.

---

### Task 5: Add Job Status APIs And Frontend Status Surface

**Files:**
- Create: `action_job_routes.py`
- Modify: `main.py`
- Modify: `frontend/state.mjs`
- Modify: `frontend/workspace-layout.mjs`
- Modify: `frontend/index.html`
- Test: `tests/test_action_job_routes.py`
- Test: `tests/frontend/state.test.mjs`
- Test: `tests/frontend/workspace-static.test.mjs`

**Interfaces:**
- Consumes: durable action job repository.
- Produces: owner-scoped list/detail/cancel/retry routes and a Jobs UI section.

- [ ] **Step 1: Write failing route tests**

Cover:

```text
GET /api/projects/{project_id}/action-jobs
GET /api/projects/{project_id}/action-jobs/{job_id}
POST /api/projects/{project_id}/action-jobs/{job_id}/cancel
POST /api/projects/{project_id}/action-jobs/{job_id}/retry
```

- [ ] **Step 2: Implement routes with auth/project resolution**

Follow the existing artifact route ownership pattern. Do not expose queue internals, task names, service accounts, raw prompts, or private failure text.

- [ ] **Step 3: Add frontend Jobs section**

Render queued, running, completed, failed, cancelled, stale, and retry states. Terminal jobs stop polling. Completed artifact jobs expose `Open artifact`.

- [ ] **Step 4: Run focused route/frontend checks**

Run:

```bash
venv/bin/python -m pytest tests/test_action_job_routes.py -q
node --test tests/frontend/state.test.mjs tests/frontend/workspace-static.test.mjs
git diff --check
```

Expected: PASS.

---

### Task 6: Add Local In-Process Worker For One Action Kind

**Files:**
- Create: `action_job_worker.py`
- Modify: `main.py`
- Modify: `agent_col_artifact_executor.py` only if needed for a reusable command boundary
- Test: `tests/test_action_job_worker.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: queued action job snapshots.
- Produces: status transitions and canonical artifact/note/memory effects through existing services.

- [ ] **Step 1: Pick one action kind**

Start with `create_artifact` because artifact creation already has a request-bound service and public artifact receipts.

- [ ] **Step 2: Write failing worker tests**

Test queued-to-running, successful artifact completion, provider failure, cancellation-before-start, stale lease fencing, and no duplicate artifact on duplicate delivery.

- [ ] **Step 3: Implement local worker**

Use app-managed background tasks only for local/in-process execution. Do not introduce Cloud Tasks in this pass.

- [ ] **Step 4: Run focused checks**

Run:

```bash
venv/bin/python -m pytest tests/test_action_job_worker.py tests/test_action_job_repository.py -q
git diff --check
```

Expected: PASS.

---

## Recommended Execution Order

1. Implement Task 1 immediately. It is a confirmed UI-state bug with a small blast radius.
2. Review Task 2 before implementation because it changes public response schema.
3. Do not implement Tasks 3-6 until Task 2 receipts are accepted in browser testing.

## Stop Conditions

- Stop if clearing stale choices breaks failed-turn retry or continuity-selection behavior.
- Stop if queued receipts require changing existing approved memory/note proposal semantics.
- Stop if a design requires prompt bodies or private model context to appear in public job records.
- Stop if one chat turn must own multiple competing durable effects directly; that contradicts the queue architecture.
