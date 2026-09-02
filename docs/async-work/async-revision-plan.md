# Agent Col Async Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public-safe job report boundary that reconciles terminal agent work without exposing internal IDs, then use it as the next foundation for decoupling Agent Col chat from durable background work.

**Architecture:** Agent Col remains the conversational orchestrator. Agent jobs own lifecycle, durable resources own persisted outputs/proposals, and job reports own public-safe result explanation. Public surfaces must use display ordinals such as `001`, not backend identifiers.

**Tech Stack:** FastAPI, Pydantic, Firestore via `google.cloud.firestore`, vanilla JavaScript frontend modules, Node test runner, pytest.

**Spec:** `docs/async-work/async-work-notes.md`

## Current Plan Update: Full Background Ownership Split

Manual verification after memory queueing showed that partial decoupling is not enough. Chat can still create contradictory user experience if it narrates background task completion or failure while the Agents panel and durable resource UIs show a different state.

The direction remains full separation:

- Agent Col owns conversation, intent recognition, and task delegation.
- Background agents own task execution.
- Durable resource surfaces own artifacts, notes, memory proposals, and approvals.
- Job reports own completed, failed, and cancelled task explanations.
- Chat may acknowledge queued work but must not be the authoritative reporter for background completion, failure, proposal status, approval status, or artifact persistence.

The next implementation passes should stay on that path:

1. Finish the public job-report inspection surface so users can inspect terminal background outcomes without relying on chat.
2. Move artifact creation behind the same queued job/report boundary so chat no longer waits on artifact generation.
3. Move note proposal/reporting behavior behind the same boundary.
4. Revisit memory policy expansion, including multiple pending proposals per category and richer memory categories, only after the async ownership boundary is stable.

### Recently Completed Boundary Hardening

Queued memory work must now be labeled as a memory request until the worker creates a real proposal or terminal report. Agent Col must not describe queued memory work as a pending proposal, created proposal, submitted proposal, saved preference, approved memory, or failed memory outcome. The supervisor also sanitizes canonical final response text when a queued memory receipt exists without a completed memory proposal.

## Current Plan Update: Memory Intent Decoupling

Manual verification after the public report-boundary work showed that memory was still partially coupled to the live chat tool. The chat path still used the strict `ProviderNaturalMemoryDecision` union as the tool argument type, so ADK could reject a loose provider category before the memory request reached the queue/report boundary.

The immediate approved pass therefore superseded artifact decoupling as the next implementation step.

### Goal

Move profile-candidate memory proposal execution behind the AgentJob/report boundary so the live chat tool queues memory intent quickly and the Memory Analyst worker owns validation, normalization, proposal creation, and sanitized failure reporting.

### Required Behavior

- The chat tool must not reject profile-candidate memory requests only because the model used a loose provider category such as `collaboration_preferences`.
- When an `AgentJobRepository` exists, profile-candidate memory requests must enqueue as raw intent and return a queued receipt.
- The memory service must not be called directly from the live tool for queued profile-candidate memory requests.
- The worker must convert queued payloads into governed memory commands.
- The worker must normalize `collaboration_preferences` into the governed `user_requested_memory` category.
- Private chat-turn lease and owner-token values must not be serialized into the job payload.
- Existing no-repository direct governed behavior must remain available for local/test paths.
- Memory clarifications remain direct for now and require a separate design pass before being moved fully behind jobs.

### TDD Plan

- RED: add a tool test proving `collaboration_preferences` profile candidates queue instead of being rejected by ADK/tool validation.
- RED: add a worker test proving a queued `collaboration_preferences` payload becomes a `user_requested_memory` command.
- GREEN: broaden the tool input boundary to raw decision objects for live queueing.
- GREEN: add worker/provider normalization for the loose category.
- REFACTOR: replace strict model-facing category schema tests with raw-intent queue-boundary tests.

### Verification

- `venv/bin/python -m pytest tests/test_memory_proposal_tool.py tests/test_memory_proposal_job_worker.py -q`
- `venv/bin/python -m pytest tests/test_memory_proposal_tool.py tests/test_memory_proposal_job_worker.py tests/test_memory_candidate_decisions.py -q`
- `venv/bin/python -m pytest tests/test_agent_job_reports.py tests/test_agent_job_repository.py tests/test_memory_proposal_job_worker.py tests/test_memory_proposal_tool.py tests/test_memory_candidate_decisions.py tests/test_main.py -k "report or agent_job or memory_proposal or collaboration_preferences" -q`
- `node --test tests/frontend/api.test.mjs tests/frontend/agents-view.test.mjs tests/frontend/app-runtime.test.mjs`
- `venv/bin/python -m py_compile memory_candidate_decisions.py memory_proposal_tool.py memory_proposal_job_worker.py agent_col_agent_jobs.py agent_job_repository.py main.py`

### Next Target After Acceptance

After this memory-intent boundary is manually accepted, resume the broader decoupling path: artifact creation should move behind the queued job/report boundary so chat can acknowledge queued artifact work quickly while the artifact viewer refreshes from authoritative artifact/job state.

## Global Constraints

- No public API response or UI for agent jobs/reports may expose internal `job_id`, `session_id`, `source_turn_id`, or `source_message_id`.
- No public API response or UI for agent jobs/reports may expose private payloads, tool payloads, owner tokens, credentials, raw prompts, internal model reasoning, or raw agent IDs.
- The visible job number is an ordinal display value only, formatted as three digits in chronological order within the current public list.
- The display ordinal must not be accepted as a backend lookup key in this pass.
- Artifact labels, note titles, memory preference summaries, action kinds, lifecycle states, public summaries, and public timestamps are allowed.
- Memory, notes, and artifacts remain governed by existing application policy and approval contracts.
- Relevant conversation context retrieval remains in the chat path for now because it directly affects answer relevance.
- Do not implement full artifact decoupling, note approval reporting, memory category expansion, or multiple pending memory proposals per category in this pass.

---

## Source Evidence

- `main.py` currently defines `AgentJobPublic` with `job_id`, `session_id`, and `source_turn_id`, so the public projection leaks internal identifiers that should not be user-visible.
- `_public_agent_job` currently copies `job.job_id`, `job.session_id`, `job.source_turn_id`, and `job.result_refs` directly into the public API response.
- `/api/users/{user_id}/projects/{project_id}/agent/jobs` and `/api/users/{user_id}/projects/{project_id}/agent/jobs/stream` both use `_public_agent_job_list_response`, so fixing the projection protects both ordinary polling and stream snapshots.
- `AgentJobRepository.list_jobs` already orders jobs by `created_at`, which is the right source for deriving chronological display ordinals.
- `memory_proposal_job_worker.py` currently completes memory proposal jobs with private-ish `result_refs={"proposal_id": ...}` and fails conflicts with the generic summary `Memory proposal could not be created.`
- Manual verification showed the exact unresolved mismatch: the Memory UI displayed a pending memory proposal while the Agents panel showed the Memory Analyst job as failed.

## Task 1: Public Job Projection Sanitization

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`
- Modify: `tests/frontend/api.test.mjs`
- Modify: `tests/frontend/agents-view.test.mjs`
- Modify: `tests/frontend/app-runtime.test.mjs`
- Modify: `frontend/agents-view.mjs`

**Interfaces:**
- Consumes: existing `AgentJob` objects from `agent_col_agent_jobs.py`
- Produces: public job objects with `job_number`, `action_kind`, `status`, `display_label`, `agent_label`, `created_at`, `updated_at`, `attempt_count`, `failure_summary`, and no internal IDs

- [ ] **Step 1: Write the failing backend projection test**

Add or update a test in `tests/test_main.py` that calls the agent jobs list helper or endpoint and asserts each public job omits:

```python
for forbidden_key in (
    "job_id",
    "session_id",
    "source_turn_id",
    "source_message_id",
    "workspace_id",
    "result_refs",
    "retry_of_job_id",
):
    assert forbidden_key not in public_job
assert public_job["job_number"] == "001"
```

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m pytest tests/test_main.py -k "agent_job" -q
```

Expected: the new/updated test fails because `AgentJobPublic` still exposes internal identifiers and does not provide `job_number`.

- [ ] **Step 3: Implement the minimal backend projection change**

Update `AgentJobPublic` and `_public_agent_job` in `main.py` so public list/stream responses expose a display-only `job_number` and remove internal identifiers from the response model. Generate `job_number` from the already chronologically ordered list in `_public_agent_job_list_response`, starting at `001`.

Keep private backend methods and route path parameters unchanged in this task. Do not remove internal job IDs from repository storage.

- [ ] **Step 4: Verify GREEN for backend projection**

Run:

```bash
venv/bin/python -m pytest tests/test_main.py -k "agent_job" -q
```

Expected: public job projection tests pass and no forbidden keys appear in list or stream payloads.

- [ ] **Step 5: Update frontend tests for `job_number`**

Change frontend fixtures to stop depending on `job_id` in public job objects. Assertions should use:

```javascript
job_number: "001"
```

and should verify that rendered text does not include raw backend IDs.

- [ ] **Step 6: Update frontend rendering**

Render `job.job_number` only as a short display ordinal when useful. Keep the panel visually aligned with the accepted concept. Do not turn the ordinal into a link or lookup key.

- [ ] **Step 7: Verify frontend GREEN**

Run:

```bash
node --test tests/frontend/api.test.mjs tests/frontend/agents-view.test.mjs tests/frontend/app-runtime.test.mjs
```

Expected: API, panel rendering, and runtime agent panel tests pass with sanitized public jobs.

## Task 2: Agent Job Report Model And Repository

**Files:**
- Modify: `agent_col_agent_jobs.py`
- Modify: `agent_job_repository.py`
- Create: `tests/test_agent_job_reports.py`
- Modify: `tests/test_agent_job_repository.py`

**Interfaces:**
- Consumes: terminal `AgentJob` records
- Produces: `AgentJobReport` records with public-safe fields only

Define the report shape:

```python
class AgentJobReport(StrictModel):
    report_id: IdentifierStr
    job_id: IdentifierStr
    user_id: IdentifierStr
    project_id: IdentifierStr
    workspace_id: IdentifierStr
    session_id: IdentifierStr
    action_kind: AgentJobKind
    agent_label: DisplayLabelStr
    status: Literal["completed", "failed", "cancelled"]
    title: DisplayLabelStr
    summary: DisplayLabelStr
    public_resource_label: DisplayLabelStr | None = None
    created_at: datetime
```

The stored report may contain backend IDs for ownership and joining. Public projections must not expose those IDs.

- [ ] **Step 1: Write RED model tests**

In `tests/test_agent_job_reports.py`, assert that report metadata rejects forbidden public keys such as `job_id`, `session_id`, `source_turn_id`, `source_message_id`, `tool_payload`, `raw_prompt`, and `owner_token` when placed in any public metadata field.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m pytest tests/test_agent_job_reports.py -q
```

Expected: fails because `AgentJobReport` does not exist.

- [ ] **Step 3: Implement report models**

Add `AgentJobReport` and terminal report status aliases in `agent_col_agent_jobs.py`. Reuse existing strict model and public metadata rejection patterns.

- [ ] **Step 4: Verify report model GREEN**

Run:

```bash
venv/bin/python -m pytest tests/test_agent_job_reports.py -q
```

Expected: report model tests pass.

- [ ] **Step 5: Write RED repository tests**

In `tests/test_agent_job_repository.py`, add tests for:

```python
await repository.create_report(report)
listed = [item async for item in repository.list_reports(...)]
assert listed == [report]
```

Also assert reports are listed chronologically and filtered by `project_id` and `session_id` internally.

- [ ] **Step 6: Verify repository RED**

Run:

```bash
venv/bin/python -m pytest tests/test_agent_job_repository.py -k "report" -q
```

Expected: fails because repository report methods do not exist.

- [ ] **Step 7: Implement repository methods**

Add:

```python
async def create_report(self, report: AgentJobReport) -> AgentJobReport
async def list_reports(..., project_id: str | None = None, session_id: str | None = None, limit: int = 50) -> AsyncIterator[AgentJobReport]
```

Store reports under the workspace owner scope so they can be listed without requiring public job IDs:

```text
users/{user_id}/workspaces/{workspace_id}/agent_job_reports/{report_id}
```

- [ ] **Step 8: Verify repository GREEN**

Run:

```bash
venv/bin/python -m pytest tests/test_agent_job_repository.py -k "report" -q
```

Expected: report persistence tests pass.

## Task 3: Memory Worker Report Truthfulness

**Files:**
- Modify: `memory_proposal_job_worker.py`
- Modify: `tests/test_memory_proposal_job_worker.py`

**Interfaces:**
- Consumes: `NaturalMemoryProposalResult`, `NaturalMemoryNoEffectResult`, and known memory proposal exceptions
- Produces: terminal `AgentJobReport` records matching the actual terminal job outcome

- [ ] **Step 1: Write RED tests for completed memory reports**

Update `tests/test_memory_proposal_job_worker.py` so a successful proposal creates a report with:

```python
assert report.status == "completed"
assert report.agent_label == "Memory Analyst"
assert report.title == "Memory proposal pending review"
assert report.summary == "A memory proposal was created and is pending your review."
assert report.public_resource_label == "Prefers C over Python"
```

- [ ] **Step 2: Write RED tests for conflict reports**

Add a conflict test that raises `MemoryProposalConflictError` and expects:

```python
assert report.status == "failed"
assert report.title == "Memory proposal not created"
assert report.summary == "A pending memory proposal already exists for this category."
```

- [ ] **Step 3: Verify RED**

Run:

```bash
venv/bin/python -m pytest tests/test_memory_proposal_job_worker.py -q
```

Expected: fails because the worker does not write reports and still uses a generic conflict summary.

- [ ] **Step 4: Implement memory worker reports**

After `complete_job` succeeds, create a completed report. After `fail_job` succeeds for a known failure, create a failed report with a precise public-safe summary.

Important ordering:

```text
memory service result
  -> terminal job transition
  -> terminal public report
```

Do not report completion if job completion fails. Log completion failures with content-safe diagnostics and leave the job state authoritative.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
venv/bin/python -m pytest tests/test_memory_proposal_job_worker.py -q
```

Expected: memory worker report tests pass, with precise failure summaries.

## Task 4: Public Report API

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`
- Modify: `frontend/api.mjs`
- Modify: `tests/frontend/api.test.mjs`

**Interfaces:**
- Consumes: stored `AgentJobReport`
- Produces: public report list objects with display ordinals and no internal IDs

Public report shape:

```json
{
  "report_number": "001",
  "job_number": "001",
  "action_kind": "propose_memory_signal",
  "agent_label": "Memory Analyst",
  "status": "completed",
  "title": "Memory proposal pending review",
  "summary": "A memory proposal was created and is pending your review.",
  "public_resource_label": "Prefers C over Python",
  "created_at": "2026-09-02T..."
}
```

- [ ] **Step 1: Write RED backend API tests**

Add tests asserting:

```python
for forbidden_key in (
    "report_id",
    "job_id",
    "session_id",
    "source_turn_id",
    "source_message_id",
    "workspace_id",
):
    assert forbidden_key not in report
assert report["report_number"] == "001"
assert report["job_number"] == "001"
```

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m pytest tests/test_main.py -k "agent_report" -q
```

Expected: fails because the report endpoint does not exist.

- [ ] **Step 3: Implement public report endpoint**

Add:

```text
GET /api/users/{user_id}/projects/{project_id}/agent/reports
```

Support `session_id` as a query filter because the frontend already has that internal context, but do not echo it in the response.

- [ ] **Step 4: Verify backend API GREEN**

Run:

```bash
venv/bin/python -m pytest tests/test_main.py -k "agent_report or agent_job" -q
```

Expected: report and job public projection tests pass.

- [ ] **Step 5: Add frontend API client and tests**

Add `listAgentJobReports` in `frontend/api.mjs`. Tests should assert the request may include `session_id` in the query but response fixtures/rendering never expose it.

- [ ] **Step 6: Verify frontend API GREEN**

Run:

```bash
node --test tests/frontend/api.test.mjs
```

Expected: report API client tests pass.

## Task 5: Agents Panel Report Readiness

**Files:**
- Modify: `frontend/agents-view.mjs`
- Modify: `frontend/app.mjs`
- Modify: `frontend/state.mjs`
- Modify: `tests/frontend/agents-view.test.mjs`
- Modify: `tests/frontend/app-runtime.test.mjs`
- Modify: `tests/frontend/state.test.mjs`

**Interfaces:**
- Consumes: public jobs and public reports
- Produces: a panel that can display completed/failed task report briefs without requiring chat narration

This task may be split into a later UI pass if Task 1-4 already consume the implementation budget. If implemented in this plan, keep it bounded:

- completed/failed rows may expand inline to show the matching report brief;
- footer text becomes `View all job reports`;
- the arrow remains the visible control and keeps the existing appearance;
- the modal or pop-up lists reports as compact list text, not cards;
- no backend IDs appear.

- [ ] **Step 1: Write RED frontend rendering tests**

Assert:

```javascript
assert.match(output.textContent, /View all job reports/);
assert.doesNotMatch(output.textContent, /job--/);
assert.doesNotMatch(output.textContent, /session--/);
assert.match(output.textContent, /A memory proposal was created and is pending your review/);
```

- [ ] **Step 2: Verify RED**

Run:

```bash
node --test tests/frontend/agents-view.test.mjs tests/frontend/app-runtime.test.mjs tests/frontend/state.test.mjs
```

Expected: fails because report rendering and footer behavior do not exist.

- [x] **Step 3: Implement report rendering**

Add public report state and render the brief under completed/failed rows when available. Add the footer label and arrow-triggered modal without creating nested cards.

- [x] **Step 4: Verify GREEN**

Run:

```bash
node --test tests/frontend/agents-view.test.mjs tests/frontend/app-runtime.test.mjs tests/frontend/state.test.mjs
```

Expected: report UI tests pass and existing Agents panel layout remains visually unchanged except for the footer text and optional expanded report content.

Status: popup report inspection is implemented through the existing Agents footer arrow. Inline completed-row expansion remains deferred; the popup is the current authoritative report inspection surface.

## Focused Verification For The First Source Pass

Run these after the source-changing pass that implements Tasks 1-4:

```bash
venv/bin/python -m pytest tests/test_agent_job_reports.py tests/test_agent_job_repository.py -k "report or agent_job" tests/test_memory_proposal_job_worker.py tests/test_main.py -k "agent_report or agent_job or memory_proposal" -q
```

```bash
node --test tests/frontend/api.test.mjs tests/frontend/agents-view.test.mjs tests/frontend/app-runtime.test.mjs
```

```bash
venv/bin/python -m py_compile agent_col_agent_jobs.py agent_job_repository.py memory_proposal_job_worker.py main.py
```

```bash
git diff --check
```

Full suite is not required for the first source pass unless focused tests reveal shared-contract breakage outside the agent job/report boundary.

## Manual Verification Targets

1. Start `/workspace` in `google_oidc` mode and run:

```text
Create a reusable shell script artifact for safely checking Python HTTP server status on macOS, and remember that I prefer C over Python.
```

Expected:

- chat does not show `Chat turn state is invalid`;
- Agents panel shows display numbers only, such as `001`, not raw backend IDs;
- artifact appears in the artifact viewer;
- Memory Analyst terminal state has a report that truthfully matches the Memory UI state;
- if a memory conflict exists, the report says a pending memory proposal already exists for the category;
- if a memory proposal is created, the report says it is pending review.

2. In `local_dev`, call the public jobs endpoint:

```bash
curl -s http://127.0.0.1:8000/api/users/user-1/projects/project-1/agent/jobs
```

Expected:

- public job objects include `job_number`;
- public job objects do not include `job_id`, `session_id`, `source_turn_id`, `source_message_id`, `private_payload`, `payload`, `tool_payload`, or `result_refs`.

3. In `local_dev`, call the public reports endpoint:

```bash
curl -s http://127.0.0.1:8000/api/users/user-1/projects/project-1/agent/reports
```

Expected:

- public report objects include `report_number` and public summaries;
- public report objects do not include `report_id`, `job_id`, `session_id`, `source_turn_id`, `source_message_id`, private payloads, or raw resource IDs.

## Proposed First Implementation Pass

Implement Tasks 1-4 only.

Reason: Tasks 1-4 establish the security projection and public report contract before adding more UI. Task 5 should follow only after backend truthfulness and API shape are manually accepted.

Expected files/surfaces:

- `agent_col_agent_jobs.py`
- `agent_job_repository.py`
- `memory_proposal_job_worker.py`
- `main.py`
- `frontend/api.mjs`
- focused backend tests
- focused frontend API/projection tests

Expected user-visible result:

- public job surfaces stop leaking internal identifiers;
- Memory Analyst reports become truthful and inspectable through a public report endpoint;
- chat remains no more coupled than it is today, but the next decoupling layer gets a clean report boundary to build on.

Approval is required before implementation.

## Current Progress Notes

- Public job/report projections and report persistence are implemented.
- The Agents panel now exposes `View all job reports` through the existing
  arrow affordance and opens a popup report overlay with a top-right `x`.
- Memory proposal creation is queued to background work and reports through the
  agent/report boundary.
- Memory proposal approve/reject now uses a direct Memory API endpoint from the
  Memory UI. It no longer depends on chat submit readiness and does not create a
  chat turn when the user accepts or rejects a proposal.
- Artifact creation now enqueues a `create_artifact` AgentJob and returns a
  queued action from the chat path. Generation and persistence are owned by an
  artifact worker that writes terminal job state and a public report.

Remaining direction:

- workspace note proposal creation and approval still need the same ownership
  split;
- artifact/job/report/resource refresh behavior needs manual verification in
  the live UI after the queue-owned artifact pass;
- chat should keep conversational context retrieval and task delegation, but
  background work completion/failure/approval reporting belongs to resource UIs
  and job reports;
- public surfaces must continue to expose chronological display numbers and
  human labels only, never internal IDs or private routing fields.

## Approved Artifact Decoupling Pass

Implemented source boundary:

- `AgentColArtifactExecutor.queue(...)` creates an `AgentJob` plus private
  payload and dispatches the queued job without invoking generation, ledger
  writes, readers, or chat-turn artifact effects;
- `AgentColArtifactCreationJobWorker` leases `create_artifact` jobs and handles
  both blueprint and single-file artifact persistence behind the job boundary;
- `AgentColTurnService` uses queued artifact context for artifact routes and
  returns queued action receipts instead of completed artifact receipts;
- `SupervisorTurnContext.prequeued_actions` lets application-owned queued work
  flow through the existing responder result collection;
- `main.py` wires an in-process artifact worker and cancels outstanding
  artifact tasks on shutdown.

Focused verification used during this pass:

```bash
venv/bin/python -m pytest tests/test_agent_col_artifact_executor.py tests/test_agent_col_turn_service_artifacts.py tests/test_agent_col_turn_service.py -k "artifact or queued" -q
venv/bin/python -m pytest tests/test_agent_job_reports.py tests/test_agent_job_repository.py -k "report or agent_job" -q
venv/bin/python -m pytest tests/test_main.py -k "agent_report or agent_job or artifact" -q
```

Manual verification is still required before this pass is accepted.
