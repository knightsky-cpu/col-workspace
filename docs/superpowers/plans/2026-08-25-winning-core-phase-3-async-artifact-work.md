# Winning Core Phase 3 Durable Asynchronous Artifact Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan one approved pass at a
> time. Steps use checkbox (`- [ ]`) syntax for tracking. Repository
> `AGENTS.md` approval, TDD, manual-verification, and checkpoint gates remain
> controlling.

**Status:** Pending approval. Planning this phase does not authorize source,
dependency, Google Cloud, IAM, queue, worker, or deployment changes.

**Goal:** Convert structured blueprint synthesis into one inspectable durable
workflow that is accepted through chat, executes through Google Cloud Tasks in
a private Cloud Run worker, survives duplicate delivery and worker failure,
and exposes truthful queued, running, completed, failed, and cancelled states
without changing generic single-file artifacts.

**Architecture:** Preserve the existing authenticated routing and exact-source
boundary, then replace only the synchronous `create_blueprint` executor call
with job submission. Store a canonical Firestore job before dispatch, send
only an opaque job locator and contract version through Cloud Tasks, and let a
separately authenticated worker claim a fenced lease, generate the blueprint,
and atomically commit the canonical artifact and terminal job result. The
browser polls application-owned APIs; it never calls Cloud Tasks or the worker.

**Tech Stack:** Python 3.14, FastAPI, Pydantic 2, Google ADK, Google GenAI SDK,
Gemini 3.6 Flash through Vertex AI, Firestore, `google-cloud-tasks==2.24.0`,
Cloud Tasks, private Cloud Run, Google OIDC/IAM, vanilla JavaScript ES modules,
Node test runner, pytest.

**Spec and research input:**

- `docs/research/2026-08-25-phase-3-durable-artifact-cloud-tasks-audit.md`

**Governing repository references:**

- `AGENTS.md`
- `AGENT_COL_IDENTITY_AND_ALIGNMENT.md`
- `DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`
- `docs/aug-25-2026-final-checklist.md`

No other `docs/research/*.md` file exists at the planning baseline. Phase 3
uses the dedicated research audit as requested and reconciles every unresolved
decision below against executable source and the actual Google Cloud project.

## Planning baseline and prerequisites

The original source audit used commit
`f7d20e05ed6f1850fc4a7f2a864bdfd3d41044e5` on `main` before Phase 2 was
implemented. This revision re-audits the plan against accepted Phase 2 commit
`a1cf67e9a3359115583c290d08ae1624f977df12`, with `origin/main` matching that
checkpoint after the Phase 2 closure evidence push.

Phase 3 implementation must not start until:

1. this revised Phase 3 plan is reviewed and approved;
2. this documentation-only revision is checkpointed if the repository owner
   wants the plan baseline fixed before implementation;
3. Pass 3A is separately approved for implementation.

Before each implementation pass, the implementer must still inspect current
source for drift from this baseline. That pass-local re-audit must specifically
confirm that the artifact dispatch seam, current-message authority,
continuity-source snapshot, chat response fields, note contracts, and frontend
workspace state still match the assumptions below.

## Verified current source state

At the Phase 2 checkpoint baseline:

- `POST /api/chat` authenticates the user/workspace, claims a retry-safe
  Firestore turn, loads bounded history and governed memory, resolves
  receipt-backed continuity over active workspace notes or bounded prior chat
  sessions, routes with the Gemini/ADK stack, executes an artifact
  synchronously, runs the final responder, and completes the turn before
  returning.
- `agent_col_turn_service.py` distinguishes `create_blueprint` from
  `create_single_file_artifact` only after the validated V4 artifact route.
  `_complete_artifact_turn()` is the exact conversion seam.
- `build_artifact_source_text()` already creates a bounded, server-owned source
  from the current message and at most three recent user messages.
- `AgentColArtifactExecutor` is intentionally synchronous and coupled to
  `ChatTurnClaim`; blueprint generation calls
  `SynthesisApplicationService.generate_governed_blueprint()` and then
  `MemoryEngine.record_chat_turn_blueprint_effect()`.
- Blueprint persistence already writes a deterministic
  `blueprint--{turn_id}` artifact, action receipt, artifact reference,
  adaptation receipts, and precompleted chat effect atomically.
- Exact chat replay and changed-request conflict handling already work, but
  the 120-second `ChatTurnClaim` lease is an HTTP owner lease, not a durable
  worker lease.
- `synthesis.py` bounds one Gemini generation attempt group to 60 seconds and
  performs SDK-level retries for 408, 429, and selected 5xx responses.
- Canonical blueprint list/detail APIs, feedback targets, feedback history,
  artifact receipts, exports, and the artifact viewer already exist.
- Generic single-file artifact creation and versions are separate synchronous
  flows and remain synchronous in Phase 3.
- Phase 2 added workspace notes and continuity to the public chat contracts:
  `ChatRequest` now has mutually exclusive `collaborative_note_decision` and
  `continuity_selection`; `ChatResponse` now carries
  `collaborative_note_proposals`, `collaborative_note_events`,
  `continuity_receipts`, and `continuity_choices`.
- Phase 2 added authenticated workspace, notes, and chat-session inspection
  routes under the existing single-user Google OIDC boundary. These are not
  multi-user workspace membership or sharing features.
- The browser now has Workspace, Work, Notes, Memory, and Chats drawer
  sections, including frontend API/state/view coverage for notes,
  chat-session summaries, continuity receipts, and continuity choice buttons.
- The browser still has no durable artifact job state, polling controller, job
  status controls, cancellation, retry UI, or Jobs section.
- Runtime dependencies include Firestore and GenAI clients but not the Cloud
  Tasks client. There is no worker app, queue adapter, deployment source, or
  job index.

## Google Cloud planning input

The original planning audit read the configured project without changing it:

- project: `project-e1e2a890-4566-48a8-a32`;
- Firestore database location: `us-east4`;
- Vertex AI model location remains `global` under the existing provider
  contract;
- Cloud Tasks API is disabled;
- Cloud Run, Cloud Build, Artifact Registry, and Cloud Scheduler were not
  listed as enabled;
- both Cloud Tasks and Cloud Run currently support `us-east4`.

This source-code re-audit did not re-query Google Cloud. Pass 3G must verify
current API/IAM/resource state before any cloud mutation. Phase 3 still selects
`us-east4` for the queue and private worker to align with Firestore unless the
Pass 3G cloud re-check proves that assumption has drifted. Enabling APIs,
creating IAM identities, creating a queue, and deploying a private worker
belong only to separately approved Pass 3G.

## Resolved architecture decisions

These decisions close the open questions in the research audit.

### One asynchronous workflow

Only chat-routed `create_blueprint` synthesis becomes asynchronous. Direct
`POST /api/synthesize`, generic single-file creation, generic versions,
artifact feedback, memory, workspace notes, receipt-backed continuity, chat
session inspection, and expert routes retain current behavior.

### Immediate chat response

After validated routing and exact source construction, `/api/chat` persists a
job, obtains durable Cloud Tasks acceptance, and runs the existing responder
with a server-owned queued-job projection. The response contains:

- a truthful acknowledgement that work is queued;
- one `ArtifactJobReceipt` in `artifact_jobs`;
- one completed `queue_blueprint` action receipt;
- no artifact reference and no `synthesize_project` completion claim.

The chat turn then completes normally. Exact replay returns that original
queued response even if the job later completes; current status comes from the
job API.

### Completion communication

The worker never appends a delayed assistant message and never rewrites the
completed chat response. Completion is shown through the durable Jobs surface,
an authoritative completed-job receipt, and the existing canonical artifact
viewer. A later user turn may discuss the completed artifact through existing
authorized reads, but background completion does not impersonate a new user or
Agent Col turn.

### Job-first, task-second recovery

Submission uses this sequence:

1. derive one opaque deterministic job ID and task name from server-owned turn
   identity and operation;
2. idempotently persist the job with public status `queued` and internal
   dispatch state `pending`;
3. atomically attach the queued-job effect to the still-owned chat turn;
4. call Cloud Tasks with the deterministic task name;
5. treat matching `AlreadyExists` as successful recovery;
6. mark dispatch `enqueued` without overwriting a worker-updated job state;
7. only then run the queued-response responder and complete the chat turn.

If dispatch fails, preserve the durable job and turn receipt, release the chat
lease, and return a bounded retryable failure carrying the job receipt. Exact
chat retry repeats dispatch safely. Startup reconciliation and explicit job
inspection also retry `dispatch=pending` with the same task name.

### Retry exhaustion and stale jobs

Every job has an application-owned `terminal_deadline` 15 minutes after
creation. Job inspection/list reconciliation marks a queued or stale-running
job failed with the bounded category `delivery_exhausted` after that deadline.
The worker also persists terminal failure when it receives the final allowed
attempt. Phase 3 does not claim proactive finalization while no application or
worker process is running; Phase 4 may add scheduled reconciliation only if
the hosted operational audit proves it necessary.

### User retry

Cloud Tasks redelivery is another attempt on the same job. Explicit user retry
requires a new idempotency key and creates a new job linked by
`retry_of_job_id`; it never resets or erases failed/cancelled history.

### Cancellation precedence

- Queued cancellation records intent first, requests task deletion, and
  reaches `cancelled` when no artifact has committed.
- Running cancellation is shown as `Cancellation requested`; worker code may
  continue until its next check.
- The worker checks cancellation at claim, before provider invocation, and in
  the completion transaction.
- If cancellation intent commits before artifact completion, completion is
  rejected and generated output is discarded; cancellation wins.
- If artifact completion commits first, the job is `completed` and later
  cancellation returns `409 Conflict`.
- Task deletion is never described as killing already running code.

### Lease and deadline values

- Gemini generation deadline: existing 60 seconds.
- Job worker lease: 90 seconds.
- Heartbeat interval: 20 seconds while provider work is active.
- Cloud Tasks dispatch deadline: 120 seconds.
- Cloud Run worker request timeout: 180 seconds.
- Browser polling: immediately, then every 2 seconds for 30 seconds, then every
  5 seconds while the Jobs section is visible; stop in terminal state,
  workspace change, sign-out, or page unload.

The required relation is `60 < 120 <= 180`. A heartbeat failure fences the
worker from completion rather than extending authority locally.

### Identity and payload

Job IDs and task names are SHA-256-derived opaque identifiers containing no
user, workspace, session, artifact, prompt, or title text. Task payload is
exactly `{job_contract_version, job_id}` and remains well below Cloud Tasks'
size limit. User/workspace/session/source authority comes only from the
canonical Firestore job.

### Region and initial cost controls

- Region: `us-east4`.
- Queue ID: `agent-col-blueprint-jobs`.
- Queue dispatch rate: 1 task per second.
- Queue maximum concurrent dispatches: 1.
- Queue maximum attempts: 3.
- Retry backoff: 5-second minimum, 30-second maximum, two doublings.
- Worker Cloud Run concurrency: 1.
- Worker minimum instances: 0.
- Worker maximum instances: 1.

Phase 4 may change these only from measured latency, quotas, and budget
evidence.

### Retention boundary

Phase 3 retains job records and their bounded generation-input snapshots so
status, retry lineage, and evidence remain inspectable. It does not introduce
automatic deletion or imply that deleting a chat deletes an independently
completed artifact. Phase 4 must define final job/source retention, workspace
deletion, and account deletion before public production readiness.

## Durable job contract

### Public states

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

Internal dispatch, lease, attempt, cancellation, and reconciliation metadata
must not create additional public status values.

### Required stored authority

One job stores:

- contract/policy version and operation `create_blueprint`;
- owner user, workspace, source session, source message, and originating turn;
- exact bounded source plus immutable history/personalization/continuity input
  snapshot accepted at submission;
- opaque job/task identity and dispatch state;
- status, timestamps, terminal deadline, and retry lineage;
- attempt count, worker generation, lease expiry, and cancellation intent;
- bounded failure category/retryability without raw exception text;
- completed action, adaptation, and artifact receipts when authoritative.

Task names, worker lease owners, IAM identities, internal Firestore paths,
provider responses, prompts, memory/note values, prior-chat bodies, and raw
errors are never part of the public job model. Continuity evidence stored for
a job must be the minimum source IDs, receipts, timestamps, match reasons, and
bounded generated input needed to reproduce the submitted blueprint request;
it must not turn Phase 3 into unrestricted chat-history or note-body search.

### Permitted state transitions

| Current | Next | Authority |
| --- | --- | --- |
| none | queued | authenticated submission service |
| queued | running | fenced private worker claim |
| queued | cancelled | authenticated owner cancellation |
| queued | failed | dispatch/deadline reconciliation |
| running | queued | retryable worker failure with lease release |
| running | running | stale-lease reclaim with new generation |
| running | completed | atomic artifact/job completion |
| running | failed | terminal worker failure |
| running | cancelled | worker observes committed cancellation |

Completed, failed, and cancelled are terminal. Explicit retry creates a new
linked job.

## Phase pass outline

Implement, verify, manually accept, and checkpoint each pass before requesting
approval for the next.

| Pass | Outcome | Primary boundary |
| --- | --- | --- |
| 3A | Strict job contracts and a dedicated Firestore state machine prove ownership, transitions, leases, fencing, and atomic artifact completion. | Domain and repository foundation. |
| 3B | Deterministic job submission, immutable generation snapshots, fake dispatch, and job-first/task-second recovery work without changing chat. | Submission and queue abstraction. |
| 3C | Chat-routed blueprints return one queued-job receipt while generic artifacts remain synchronous and replay-safe. | Production chat cutover. |
| 3D | A private-worker service claims, heartbeats, generates, retries, cancels, and completes one canonical artifact under fencing. | Worker execution. |
| 3E | Authenticated owners can list, inspect, cancel, retry, and reconcile jobs through bounded application APIs. | Public job lifecycle. |
| 3F | The browser displays durable job progress and controls, polls safely, and opens the canonical result. | Jobs UI. |
| 3G | The official Cloud Tasks dispatcher, private Cloud Run worker, IAM, queue, and controlled failure mode work in `us-east4`. | Real Google Cloud integration. |
| 3H | Live OIDC evidence proves asynchronous progress, duplicate restraint, controlled retry, cancellation truth, and phase closure. | Judge-grade verification. |

## Global constraints and preserved invariants

- Each pass requires separate explicit approval before source behavior changes.
- Every source-changing pass uses RED, verified RED, minimal GREEN, verified
  GREEN, then refactor.
- Stop at **implemented, pending manual verification** until user acceptance.
- Checkpoint only accepted work with explicit path staging to `origin/main`.
- This plan is re-audited against Phase 2 checkpoint
  `a1cf67e9a3359115583c290d08ae1624f977df12`; each pass must still re-check
  live source before editing because newer accepted work may exist.
- Agent Col remains the sole user-facing responder. The worker never writes
  conversational prose.
- Agent Col remains a single-user collaborative agent. Phase 3 must not add
  shared workspaces, teams, project sharing, or membership ACLs.
- Firestore completion, not Cloud Tasks HTTP 2xx, is authoritative.
- Cloud Tasks is at-least-once; application job/artifact idempotency and worker
  fencing are mandatory.
- The current `ChatTurnClaim` is never passed to the worker or extended into a
  worker lease.
- Only `create_blueprint` is queued. Generic artifacts remain synchronous.
- Existing direct synthesis, artifact reads, feedback, exports, memory,
  workspace notes, continuity selections/receipts, chat-session inspection,
  expert routes, and profile adaptation semantics must not regress.
- Phase 2's deterministic, receipt-backed continuity remains bounded. Phase 3
  must not add general unrestricted transcript search or a semantic transcript
  index.
- Phase 2 intentionally keeps the sensitive-storage policy strict. Phase 3 must
  not loosen password/key/credential-looking memory or note proposal handling
  while building artifact jobs.
- Current user text remains the action authority. Retrieved content may be
  bounded source only when the current message authorizes blueprint creation.
- Jobs, task names, session IDs, and artifact IDs are locators, never bearer
  authorization.
- Every public job operation derives user/workspace from the authenticated
  request and fails unavailable across scopes.
- The private worker accepts only an opaque job locator/version and trusts the
  canonical job, not task headers, retry counters, or payload identity fields.
- Queue/test failure injection is environment-gated on the private worker and
  never exposed through a public route or browser control.
- Task payloads and application logs contain no prompts, history, memory/note
  values, artifact content, provider output, tokens, subjects, or OIDC claims.
- No generalized planner, arbitrary job type, Pub/Sub, workflow engine,
  generic task runner, PDF upload, or semantic transcript index belongs here.

## Required pass handoff evidence

Every accepted pass must leave enough bounded evidence for the next pass to
reconcile against source without reconstructing prior work from chat:

- accepted checkpoint hash and exact implementation baseline;
- files created/modified and the responsibility of each;
- RED failure, minimal GREEN change, refactor summary, and exact verification
  commands with pass/fail/warning/skip counts;
- accepted public/internal contract versions and Firestore paths/indexes;
- manual test inputs, observed outputs, and privacy-reviewed screenshots where
  behavior is visual or provider/cloud dependent;
- cloud resources, settings, IAM bindings, and cleanup state changed by the
  pass, without tokens, subjects, prompts, or content;
- deferred limitations, source drift, and stop-condition findings;
- the next bounded pass proposal, still requiring separate approval.

Store durable evidence in the repository's established documentation/evidence
locations only after user acceptance. Runtime logs alone are not a handoff.

---

## Pass 3A - Durable Job Models and Firestore Repository

### Goal and reviewable outcome

Create the isolated job authority and prove every state transition,
owner/workspace check, worker fence, cancellation race, and canonical
artifact-completion transaction without routes, provider calls, queue calls,
or UI changes.

### Expected file boundary

- Create `artifact_jobs.py`.
- Create `artifact_job_repository.py`.
- Modify `firestore.indexes.json`.
- Create `tests/test_artifact_jobs.py`.
- Create `tests/test_artifact_job_repository.py`.
- Modify `tests/test_firestore_indexes.py`.
- Treat `schemas.py`, `database.py`, `chat_turns.py`, `main.py`, synthesis,
  and frontend files as untouched regression surfaces.

### Interfaces

- `ArtifactJob`, `ArtifactJobReceipt`, `ArtifactJobListResponse`, and strict
  internal generation/lease/dispatch records use contract version `1.0`.
- Pure ID helpers derive job, task, artifact, and generation identities.
- `ArtifactJobRepository` owns the global `artifact_jobs/{job_id}` collection
  and atomic writes to the existing
  `projects/{workspace_id}/blueprints/{artifact_id}` destination.
- Public list queries filter stored `owner_user_id` and `workspace_id`, order
  newest first, and return at most 50 records.
- Firestore index configuration exempts generation snapshot and failure detail
  payloads from indexing and adds only queries required by the repository.

### TDD tasks

- [ ] Write one RED model/state test at a time for strict versions, five public
      states, timestamps, source/snapshot bounds, public-field omission,
      transition table, terminal immutability, retry lineage, and deterministic
      opaque IDs.
- [ ] Run `venv/bin/pytest -q tests/test_artifact_jobs.py` after each cycle and
      inspect the intended failure.
- [ ] Implement the minimum pure contracts/transitions in `artifact_jobs.py`.
- [ ] Write RED repository tests using the established fake Firestore pattern
      for idempotent creation, changed submission conflict, owner/workspace
      isolation, bounded list/detail, claim, reclaim, heartbeat, stale
      generation denial, retryable release, terminal failure, cancellation,
      deadline reconciliation, and terminal replay.
- [ ] Add RED completion races proving cancellation-before-completion wins,
      completion-before-cancellation wins, stale workers cannot commit, and
      duplicate completion yields one canonical blueprint.
- [ ] Implement the dedicated repository and one transaction that writes the
      canonical blueprint, artifact receipt, adaptation receipts, completed
      action, and completed job together.
- [ ] Add and verify only the required Firestore indexes/exemptions.
- [ ] Refactor note-free/job-specific parsing only after focused GREEN.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_artifact_jobs.py \
  tests/test_artifact_job_repository.py \
  tests/test_artifact_database.py \
  tests/test_artifact_read_service.py \
  tests/test_firestore_indexes.py
venv/bin/python -m compileall -q artifact_jobs.py artifact_job_repository.py
git diff --check
```

The existing artifact database/read tests prove the new completion document
remains consumable by canonical readers. The full suite is unnecessary because
3A has no runtime consumer.

### Manual acceptance targets

1. Inspect one serialized queued, running, completed, failed, and cancelled job
   and confirm no internal worker/task/IAM fields are public.
2. Inspect focused evidence for worker A expiry, worker B reclaim, worker A
   rejection, and worker B's single authoritative artifact.
3. Confirm no route, provider call, queue, dependency, or browser behavior
   changed.

Stop after the 3A report and wait for acceptance/checkpoint approval.

---

## Pass 3B - Submission Service and Deterministic Dispatcher Boundary

### Goal and reviewable outcome

Create one job from a validated blueprint command, freeze its generation
inputs, and prove job-first/task-second dispatch recovery through a
deterministic fake dispatcher. Chat behavior remains synchronous until 3C.

### Expected file boundary

- Create `artifact_job_dispatcher.py`.
- Create `artifact_job_service.py`.
- Modify `artifact_jobs.py` and `artifact_job_repository.py` only for
  submission gaps exposed by RED tests.
- Modify `synthesis_service.py` to separate immutable input preparation from
  provider generation without changing existing synchronous semantics.
- Create `tests/test_artifact_job_dispatcher.py`.
- Create `tests/test_artifact_job_service.py`.
- Modify `tests/test_synthesis_service.py`.

Do not add `google-cloud-tasks` yet. The fake is explicit test/local wiring and
must fail configuration when selected in a production environment.

### Interfaces

- `ArtifactJobDispatcher.enqueue(job_id, task_name)` accepts only opaque IDs
  and contract version from canonical configuration.
- `ArtifactJobDispatcher.delete(task_name)` supports cancellation but does not
  claim process termination.
- `DeterministicFakeArtifactJobDispatcher` records calls and can simulate
  AlreadyExists, transient enqueue failure, deletion, duplicate delivery, and
  retry.
- `SynthesisApplicationService.prepare_governed_input()` returns one strict
  immutable snapshot containing exact source, bounded owned history,
  personalization projection, Phase 2 continuity receipts/source IDs when the
  current turn resolved continuity, model/schema versions, and source IDs. It
  performs no provider call.
- `ArtifactJobSubmissionService.submit()` persists job and dispatch metadata
  idempotently; `ensure_dispatched()` repairs pending dispatch.

### TDD tasks

- [ ] Write RED dispatcher contract tests for opaque payload, deterministic
      task identity, duplicate enqueue, transient failure, delete behavior,
      call recording, and production-fake denial.
- [ ] Implement the protocol and deterministic fake.
- [ ] Write RED synthesis input-preparation tests proving the snapshot uses the
      owned source session, exact bounded history/source, approved profile
      projection, and no provider generation.
- [ ] Refactor existing synchronous generation to call the same preparation
      boundary and confirm no response or receipt changes.
- [ ] Write RED submission tests for exact retry, changed request conflict,
      job-before-dispatch ordering, enqueue success, AlreadyExists recovery,
      enqueue failure preservation, crash-before-dispatch recovery,
      crash-after-dispatch recovery, and mark-enqueued not overwriting running
      or completed state.
- [ ] Implement minimal submission/reconciliation service.
- [ ] Refactor only after fake duplicate/recovery scenarios stay green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_artifact_jobs.py \
  tests/test_artifact_job_repository.py \
  tests/test_artifact_job_dispatcher.py \
  tests/test_artifact_job_service.py \
  tests/test_synthesis.py \
  tests/test_synthesis_personalization.py \
  tests/test_synthesis_service.py
venv/bin/python -m compileall -q \
  artifact_job_dispatcher.py artifact_job_service.py synthesis_service.py
git diff --check
```

### Manual acceptance targets

1. Inspect one fake-dispatched task body and confirm it contains only version
   and opaque job ID.
2. Simulate failure before enqueue, after enqueue, and duplicate enqueue;
   confirm one job/task identity and no generated artifact.
3. Confirm existing direct synthesis remains synchronous and unchanged.

Stop after the 3B report and wait for acceptance/checkpoint approval.

---

## Pass 3C - Chat Blueprint Queue Cutover

### Goal and user-visible outcome

A chat request routed to `create_blueprint` returns a truthful queued-job
receipt after durable dispatch instead of waiting for generation. Generic
single-file artifacts continue through the accepted synchronous executor.

### Expected file boundary

- Modify `schemas.py`.
- Modify `chat_turns.py`.
- Modify `database.py` only for queued-job chat-effect persistence/recovery.
- Modify `agent_col_turn_service.py`.
- Modify `agent_col_artifact_executor.py` only to retain the single-file path
  and reject accidental asynchronous blueprint execution through that class.
- Modify `agent_col_responder.py`, `supervisor.py`, and `supervisor_runtime.py`
  for queued-job projection and truthful receipts.
- Modify `main.py`.
- Modify `tests/test_schemas.py`.
- Modify `tests/test_chat_turns.py` and `tests/test_chat_turn_database.py`.
- Modify `tests/test_agent_col_turn_service_artifacts.py`.
- Modify `tests/test_agent_col_artifact_executor.py`.
- Modify responder/supervisor/runtime tests and `tests/test_main.py`.
- Modify `tests/test_continuity_service.py`,
  `tests/test_collaborative_note_service.py`, and
  `tests/test_collaborative_note_database.py` only if the queued-job contract
  directly touches their chat-turn receipts or replay behavior.
- Treat `continuity_service.py`, `collaborative_note_service.py`, note routes,
  chat-session routes, and frontend note/continuity modules as regression
  surfaces even when they are not modified.

### Required behavior

- `ChatResponse` and partial-failure contracts gain `artifact_jobs` with a
  maximum of one receipt while preserving existing artifacts,
  artifact-feedback, memory, collaborative-note, and continuity fields.
- `ChatTurnClaim` recovers at most one queued-job effect independently from
  completed artifact, artifact-feedback, memory, collaborative-note, and
  continuity effects.
- Blueprint routing invokes submission, confirms dispatch acceptance, and
  supplies `[SERVER_VALIDATED_ARTIFACT_JOB]` to the responder.
- The projection states the exact public status and forbids claims that the
  artifact exists or generation completed.
- The responder returns one acknowledgement, `queue_blueprint` action, and job
  receipt; `artifacts` remains empty.
- Chat completion persists that immutable response. Replay never regenerates,
  redispatches unnecessarily, or changes queued receipt to completed.
- Dispatch/responder timeout or failure preserves the completed queued effect
  in the partial response and exact retry.
- Structured decisions and other major capabilities remain mutually exclusive:
  memory decisions, memory clarification selections, artifact feedback
  decisions, collaborative note decisions, continuity selections, and queued
  blueprint submission must not be combined into one turn effect.
- Single-file artifact creation retains current `create_artifact` action,
  artifact receipt, canonical viewer behavior, and responder projection.

### TDD tasks

- [ ] RED public schema tests for one bounded job receipt in success and
      partial-failure responses, strict unknown fields, and no artifact
      reference before completion.
- [ ] GREEN minimal response contracts.
- [ ] RED turn-ledger tests for queued effect, reclaim, lease renewal, release,
      completed replay, changed request, partial response, and prohibition of
      job plus artifact/memory/note/feedback effects.
- [ ] GREEN queued-effect persistence and claim recovery.
- [ ] RED turn-service tests for blueprint submission versus unchanged
      single-file execution, exact source, queued responder context, dispatch
      failure, responder failure, timeout, and no completion claim.
- [ ] GREEN the narrow `create_blueprint` branch before the current executor.
- [ ] RED FastAPI tests for success, replay, changed key, partial failure, auth,
      and response projection.
- [ ] GREEN wiring through `main.py` and lifespan fake/local configuration.
- [ ] Refactor stable job receipt merging only after blueprint and generic
      artifact suites stay green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_schemas.py \
  tests/test_chat_turns.py \
  tests/test_chat_turn_database.py \
  tests/test_artifact_job_service.py \
  tests/test_agent_col_artifact_executor.py \
  tests/test_agent_col_turn_service_artifacts.py \
  tests/test_agent_col_responder.py \
  tests/test_supervisor.py \
  tests/test_supervisor_runtime.py \
  tests/test_main.py \
  tests/test_continuity_service.py \
  tests/test_collaborative_note_service.py \
  tests/test_collaborative_note_database.py \
  tests/test_generic_artifact_creation_service.py \
  tests/test_generic_artifact_service.py
venv/bin/python -m compileall -q \
  schemas.py chat_turns.py database.py agent_col_turn_service.py \
  agent_col_artifact_executor.py agent_col_responder.py supervisor.py \
  supervisor_runtime.py main.py
git diff --check
```

The broader turn/response boundary is necessary because queued work replaces a
shared chat effect while preserving generic artifact behavior.

### Manual acceptance targets

Using local fake dispatch in Google OIDC mode:

1. Request a structured blueprint and confirm the response says queued, shows
   one job receipt, and shows no artifact receipt.
2. Exact-retry and confirm an identical chat response and one dispatch identity.
3. Reuse the key with changed input and confirm `409 Conflict`.
4. Request a single-file artifact and confirm it still completes synchronously.
5. Force responder failure after dispatch and confirm the partial response and
   retry preserve one queued job.

Stop after the 3C report and wait for acceptance/checkpoint approval.

---

## Pass 3D - Fenced Blueprint Worker and Atomic Completion

### Goal and user-visible outcome

Execute one queued job through a private-worker application service, survive
duplicate/stale workers and transient provider failures, and create exactly one
canonical blueprint with authoritative completed receipts.

### Expected file boundary

- Create `artifact_job_executor.py`.
- Create `worker_main.py`.
- Modify `artifact_job_repository.py` and `artifact_job_service.py` only for
  worker operations.
- Modify `synthesis.py` to distinguish retryable provider/timeout failure from
  deterministic local validation failure while preserving public synthesis
  behavior.
- Modify `synthesis_service.py` to generate from the immutable job snapshot.
- Create `tests/test_artifact_job_executor.py`.
- Create `tests/test_worker_main.py`.
- Extend artifact job repository/service and synthesis tests.
- Treat `main.py` and frontend as untouched.

### Required behavior

- Worker input is only strict version and opaque job ID.
- Repository claim atomically creates a unique generation, attempt count,
  90-second lease, and cancellation check.
- A 20-second heartbeat renews only the current generation. Renewal failure
  cancels local completion authority.
- The worker checks cancellation at claim, immediately before provider call,
  and in atomic completion.
- Provider 429/5xx/timeout/availability failures release to queued and return a
  retryable non-2xx while attempts remain.
- Invalid stored contract/source or deterministic schema validation persists
  failed and returns 2xx so Cloud Tasks removes the task.
- Final retryable exhaustion persists `failed` before returning 2xx.
- Completion derives adaptation receipts from the persisted personalization
  snapshot and writes one current schema-2 blueprint plus completed job in one
  transaction.
- Completed duplicate delivery returns 2xx with no provider call. A stale
  worker cannot commit after reclaim.
- Worker logs use only job ID, state, attempt, generation, duration, category,
  retryable flag, and exception class.

### TDD tasks

- [ ] RED synthesis classification tests for timeout, transient provider,
      invalid provider output, and local validation categories.
- [ ] Implement minimal typed failure categories without changing existing
      public HTTP mapping.
- [ ] RED executor tests for claim, heartbeat, completion, duplicate delivery,
      cancellation checkpoints, retryable release, final exhaustion,
      deterministic failure, and all stale-worker races.
- [ ] GREEN worker executor over snapshot generation and repository methods.
- [ ] RED worker FastAPI tests for strict payload, malformed version/ID,
      success 2xx, retryable 503, terminal 2xx, content-safe response/logs, and
      no end-user identity fields.
- [ ] GREEN minimal private worker app and lifespan wiring.
- [ ] Refactor heartbeat cleanup only after cancellation and fencing tests stay
      green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_artifact_job_repository.py \
  tests/test_artifact_job_service.py \
  tests/test_artifact_job_executor.py \
  tests/test_worker_main.py \
  tests/test_synthesis.py \
  tests/test_synthesis_service.py \
  tests/test_synthesis_quality.py \
  tests/test_artifact_read_service.py
venv/bin/python -m compileall -q \
  artifact_job_executor.py worker_main.py artifact_job_repository.py \
  synthesis.py synthesis_service.py
git diff --check
```

### Manual acceptance targets

With the deterministic fake dispatcher/worker harness:

1. Observe queued, running, completed and one canonical artifact.
2. Deliver the same task twice and confirm no second provider call after
   completion and no duplicate artifact.
3. Expire worker A, let worker B reclaim, and confirm A cannot commit.
4. Request cancellation during generation and confirm generated output is not
   persisted when cancellation intent won.
5. Force a transient first attempt and confirm the same job later completes.

Stop after the 3D report and wait for acceptance/checkpoint approval.

---

## Pass 3E - Authenticated Job Lifecycle APIs

### Goal and user-visible outcome

Authenticated owners can inspect durable progress, cancel queued/running work,
retry failed/cancelled work as a linked job, and receive bounded current-state
receipts without exposing worker or queue internals.

### Expected file boundary

- Create `artifact_job_routes.py` as a focused FastAPI `APIRouter`.
- Modify `artifact_job_service.py` and `artifact_job_dispatcher.py`.
- Modify `artifact_jobs.py` and repository only for accepted API projections.
- Modify `main.py` only to include/wire the router.
- Create `tests/test_artifact_job_routes.py`.
- Extend job service/dispatcher/repository tests.
- Modify `tests/test_main.py` only for app wiring/regressions.

### Public operations

- `GET /api/projects/{project_id}/artifact-jobs`
- `GET /api/projects/{project_id}/artifact-jobs/{job_id}`
- `POST /api/projects/{project_id}/artifact-jobs/{job_id}/cancel`
- `POST /api/projects/{project_id}/artifact-jobs/{job_id}/retry`

List uses `limit<=50`, a server cursor, and optional exact status filter.
Retry requires `Idempotency-Key`; it creates one linked job from the immutable
snapshot. Cancel records intent before task deletion and returns current
authoritative state. List/detail lazily reconcile pending dispatch and jobs
past terminal deadline.

### TDD tasks

- [ ] RED service tests for owner/workspace derivation, list/detail bounds,
      dispatch reconciliation, terminal deadline, queued cancel, running
      cancellation request, completed conflict, transient task-delete failure,
      linked retry, retry key replay/conflict, and artifact authorization.
- [ ] GREEN deterministic lifecycle commands/results.
- [ ] RED route tests for Google/local auth behavior, path/body mismatch,
      cross-user/workspace unavailable response, cursor/status validation,
      `404/409/422/503` mapping, safe errors, and no internal fields.
- [ ] GREEN router and narrow lifespan dependencies.
- [ ] Refactor HTTP error translation only after all ownership tests stay green.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_artifact_jobs.py \
  tests/test_artifact_job_repository.py \
  tests/test_artifact_job_dispatcher.py \
  tests/test_artifact_job_service.py \
  tests/test_artifact_job_routes.py \
  tests/test_auth.py \
  tests/test_main.py \
  tests/test_artifact_read_service.py
venv/bin/python -m compileall -q \
  artifact_job_routes.py artifact_job_service.py artifact_job_dispatcher.py \
  main.py
git diff --check
```

### Manual acceptance targets

1. Inspect queued, running, completed, failed, and cancelled projections.
2. Cancel queued and running jobs and verify truthful state language.
3. Retry a failed job and confirm a new linked ID with the original unchanged.
4. Attempt every operation from another workspace/user and confirm no
   existence or content disclosure.
5. Confirm completed artifact detail still requires canonical workspace access.

Stop after the 3E report and wait for acceptance/checkpoint approval.

---

## Pass 3F - Browser Job Progress, Result, Retry, and Cancellation

### Goal and user-visible outcome

The workspace shows durable blueprint jobs independently from transient chat
requests. Users can leave the originating chat, inspect progress, cancel or
retry when permitted, and open the canonical artifact after completion.

### Expected file boundary

- Create `frontend/jobs-view.mjs`.
- Create `frontend/jobs-controller.mjs` for bounded polling lifecycle.
- Modify `frontend/api.mjs`.
- Modify `frontend/state.mjs`.
- Modify `frontend/chat-view.mjs`.
- Modify `frontend/app.mjs`.
- Modify `frontend/workspace-layout.mjs`.
- Modify `frontend/index.html`.
- Modify `frontend/styles.css`.
- Create `tests/frontend/jobs-view.test.mjs`.
- Create `tests/frontend/jobs-controller.test.mjs`.
- Modify frontend API, state, chat, layout, static, workspace, and work-view
  tests as directly affected.
- Include `tests/frontend/notes-view.test.mjs`,
  `tests/frontend/chats-view.test.mjs`, and existing continuity-choice coverage
  in `tests/frontend/chat-view.test.mjs` as regression surfaces.

Treat Python source as a regression surface. Stop and revise if the UI needs a
backend contract change.

### Required behavior

- Add a Jobs section separate from Artifacts, Chats, Memory, and Notes.
- Cards show human display label, status text, created/started/completed time,
  cancellation-request state, bounded failure category, and result action.
- Queued/running jobs poll at the accepted schedule only while relevant; one
  controller owns timers and aborts requests on workspace change/sign-out.
- Terminal jobs stop polling. Manual refresh remains available.
- Cancel is enabled only when the current projection permits it. Running copy
  says `Cancellation requested`, never `Stopped` until authoritative.
- Retry appears only for failed/cancelled jobs and creates/selects a linked job.
- Completed jobs expose `Open artifact`, which loads existing canonical detail
  without trusting job content.
- Chat queued receipts link/select the job but do not imply an artifact exists.
- Existing note proposal/event receipts, continuity receipts, continuity
  choices, and chat-session drawer behavior remain unchanged.
- Loading, empty, queued, running, completed, failed, cancelled, stale,
  conflict, offline, and retry states are visible in text, keyboard operable,
  and stable on desktop/mobile.
- No queue name, task name, raw job ID as primary label, IAM identity, worker
  generation, retry headers, prompt, or stack trace is visible.

### TDD tasks

- [ ] RED API tests for list/detail/cancel/retry paths, auth, cursor/status,
      idempotency key, and same-origin validation.
- [ ] GREEN minimal API helpers.
- [ ] RED state tests for job collection/detail, workspace clearing, chat job
      receipt ingestion, status updates, terminal stop, cancellation, linked
      retry, artifact opening, and error preservation.
- [ ] GREEN immutable job state transitions.
- [ ] RED polling-controller tests with fake timers for 2/5-second cadence,
      visibility, terminal stop, abort, no overlap, backoff, and cleanup.
- [ ] GREEN focused polling controller.
- [ ] RED Jobs/chat/layout tests for controls, labels, native semantics, focus,
      wrapping, disabled states, receipt links, and no internal fields.
- [ ] GREEN view, app wiring, section registration, and bounded styles.
- [ ] Refactor only frontend job-local duplication after all selected tests pass.

### Focused automated verification

```bash
node --test \
  tests/frontend/api.test.mjs \
  tests/frontend/state.test.mjs \
  tests/frontend/jobs-controller.test.mjs \
  tests/frontend/jobs-view.test.mjs \
  tests/frontend/chat-view.test.mjs \
  tests/frontend/notes-view.test.mjs \
  tests/frontend/chats-view.test.mjs \
  tests/frontend/work-view.test.mjs \
  tests/frontend/workspace-layout.test.mjs \
  tests/frontend/workspace-static.test.mjs \
  tests/frontend/workspace-view.test.mjs
venv/bin/pytest -q \
  tests/test_artifact_job_routes.py \
  tests/test_schemas.py \
  tests/test_main.py
git diff --check
```

Run focused browser verification at desktop and mobile viewports after tests.

### Manual acceptance targets

1. Queue a blueprint, switch chats, and confirm the Jobs section continues to
   show current state.
2. Observe queued then running then completed without duplicate cards or
   overlapping polls.
3. Open the completed artifact in the existing viewer.
4. Cancel queued/running work and confirm exact authoritative language.
5. Retry failed work and confirm linked history.
6. Verify keyboard/focus, mobile wrapping, independent scrolling, offline
   recovery, and no layout overlap.
7. Confirm generic synchronous artifacts and existing artifact feedback remain
   unchanged.

Stop after the 3F report and wait for acceptance/checkpoint approval.

---

## Pass 3G - Real Cloud Tasks, Private Worker, and IAM Integration

### Goal and user-visible outcome

Replace fake dispatch in the integration environment with a real Cloud Tasks
queue that invokes a private Cloud Run worker using a dedicated OIDC service
account, while retaining deterministic local tests and failing startup on
unsafe production configuration.

### Expected file and cloud boundary

- Modify `requirements.txt` to add `google-cloud-tasks==2.24.0`.
- Modify `artifact_job_dispatcher.py` for `CloudTasksArtifactJobDispatcher`.
- Modify `main.py` and `worker_main.py` only for strict environment wiring.
- Create `artifact_job_settings.py`.
- Create `tests/test_artifact_job_settings.py`.
- Extend dispatcher/main/worker tests.
- Create `scripts/provision-phase3-artifact-jobs.sh`.
- Create `scripts/deploy-phase3-worker.sh`.
- Create `docs/development/phase-3-cloud-tasks-integration.md` with exact,
  credential-safe commands and rollback/cleanup.

Cloud mutations are part of this pass and require separate explicit approval
at implementation time. Scripts must be reviewed before execution.

### Locked cloud configuration

- Project: `project-e1e2a890-4566-48a8-a32`.
- Region: `us-east4`.
- Queue: `agent-col-blueprint-jobs`.
- Worker service: `agent-col-artifact-worker`.
- Task caller service account: `agent-col-task-caller`.
- Worker runtime service account: `agent-col-worker-runtime`.
- Worker is deployed `--no-allow-unauthenticated`, concurrency 1, min 0,
  max 1, timeout 180 seconds.
- Only task caller receives `roles/run.invoker` on the worker.
- Worker runtime receives only Firestore and Vertex AI permissions required by
  measured execution.
- Task creation identity receives queue enqueue and task-caller `actAs`, not
  worker invocation through possession of a task name.
- Queue uses the rate/concurrency/retry settings locked above.
- Task OIDC audience is the exact worker URL.

### TDD and integration tasks

- [ ] RED settings tests for required project/location/queue/worker URL/caller,
      exact production mode, URL/audience validation, fake-production denial,
      and no secret/key settings.
- [ ] GREEN strict settings loader.
- [ ] RED Cloud dispatcher tests with a fake Cloud Tasks client for canonical
      queue/task names, JSON payload, OIDC service account/audience, 120-second
      deadline, AlreadyExists recovery, retryable errors, delete behavior, and
      content-safe logging.
- [ ] GREEN official dispatcher and pinned dependency.
- [ ] RED script/static tests proving exact project/region/resource names,
      API enablement list, least-privilege bindings, private worker, queue
      limits, no embedded credentials, and idempotent command structure.
- [ ] GREEN provisioning/deployment scripts and credential-safe guide.
- [ ] Run focused deterministic tests before any cloud mutation.
- [ ] With explicit approval, enable Cloud Tasks, Cloud Run, Cloud Build,
      Artifact Registry, and required IAM APIs; create service accounts and
      queue; deploy the private worker from source; apply IAM; configure local
      public API dispatch settings.
- [ ] Verify unauthenticated worker access and an ordinary end-user token are
      denied, while Cloud Tasks delivery succeeds.
- [ ] Enable environment-only first-attempt controlled failure on the private
      worker, never through a route/body/query parameter.

### Focused automated verification

```bash
venv/bin/pytest -q \
  tests/test_artifact_job_settings.py \
  tests/test_artifact_job_dispatcher.py \
  tests/test_artifact_job_service.py \
  tests/test_artifact_job_executor.py \
  tests/test_worker_main.py \
  tests/test_main.py
venv/bin/python -m compileall -q \
  artifact_job_settings.py artifact_job_dispatcher.py main.py worker_main.py
bash -n \
  scripts/provision-phase3-artifact-jobs.sh \
  scripts/deploy-phase3-worker.sh
git diff --check
```

### Manual acceptance targets

1. Inspect queue configuration and private worker IAM in Google Cloud.
2. Prove direct unauthenticated worker invocation returns platform denial.
3. Queue one local-Google-OIDC request through real Cloud Tasks and observe one
   private worker invocation.
4. Inspect content-safe task/worker logs and Firestore state.
5. Disable cloud dispatch and confirm deterministic local fake mode still works
   only under explicit local configuration.

Stop after the 3G report and wait for acceptance/checkpoint approval.

---

## Pass 3H - Controlled Live Failure and Phase Closure

### Goal and user-visible outcome

Prove the complete asynchronous workflow with real Google OIDC, Firestore,
Cloud Tasks, private Cloud Run, Gemini, browser progress, a controlled retry,
duplicate restraint, cancellation truth, and one canonical artifact.

### Expected file boundary

- Modify `docs/aug-25-2026-final-checklist.md`.
- Modify current status/evidence documentation directly affected by Phase 3,
  likely `AGENT_COL_IDENTITY_AND_ALIGNMENT.md` and
  `BACKEND_FRONTEND_INTEGRATION_CONTRACT_INVENTORY.md`.
- Add privacy-reviewed evidence under the established repository evidence
  location.
- Disable controlled-failure environment configuration after evidence.
- No source change is expected. Any failure starts systematic debugging and a
  separately approved correction pass.

### Phase-closure verification

Because Phase 3 changes shared chat schemas, state, persistence, provider
execution, dependencies, browser behavior, and Google Cloud integration, run
the complete repository suites once:

```bash
venv/bin/pytest -q
node --test tests/frontend/*.test.mjs
venv/bin/python -m compileall -q .
git diff --check
```

Inspect pass counts, warnings, skips, and exit codes. Then run a clean
dependency installation check in a temporary virtual environment if the
current environment cannot prove the new pinned dependency resolves.

### Live evidence sequence

1. Sign in through Google OIDC and submit one blueprint job.
2. Show immediate queued response and durable Jobs entry; leave the chat.
3. Confirm existing Phase 2 Notes and Chats drawer surfaces still load and that
   no workspace note or prior-chat body appears in job/task/log evidence.
4. Show Firestore queued state and Cloud Tasks task without prompt content.
5. Trigger the deployment-gated first-attempt failure.
6. Show running/retry evidence and content-safe task/worker logs.
7. Let the second attempt complete and show exactly one canonical artifact.
8. Open the artifact in the existing viewer and inspect completion/adaptation
   receipts.
9. Exact-replay the original chat request and receive the original queued
   response without a second job or artifact.
10. Reuse the key with changed input and receive `409 Conflict`.
11. Cancel one queued job and one running job; verify truthful race behavior.
12. Explicitly retry a failed/cancelled job and prove a new linked job.
13. Attempt list/detail/cancel/retry as another workspace and principal and
    verify unavailable responses.
14. Ask a bounded Phase 2 continuity question and confirm note/prior-chat
    receipts still work after the asynchronous artifact cutover.
15. Disable failure injection and repeat one normal successful job.

### Evidence requirements

Capture judge-readable proof of:

- queue region/rate/concurrency/retry configuration;
- private worker and denied unauthenticated access;
- dedicated task-caller `roles/run.invoker` binding;
- Firestore job timeline and one canonical artifact;
- Cloud Tasks failed then successful dispatch attempts;
- Cloud Run worker logs containing only safe fields;
- browser queued/running/completed/failed/cancelled states;
- existing Phase 2 Notes, Chats, continuity choice/receipt surfaces remain
  separate from Jobs and still function;
- exact replay and changed-request conflict;
- failure injection disabled after the test.

Only user acceptance may mark Phase 3 complete and authorize its final
checkpoint. Phase 4 planning remains separately approval-gated.

## Phase-wide risks and trade-offs

- **Duplicate provider cost:** Fencing prevents duplicate authoritative
  artifacts but cannot guarantee Cloud Tasks never causes duplicate provider
  work. Queue concurrency 1 and early claims reduce the risk.
- **Nontransactional dispatch:** Firestore and Cloud Tasks cannot share one
  transaction. Deterministic task names, explicit dispatch metadata, exact
  retry, startup/inspection reconciliation, and terminal deadlines close the
  observable gap.
- **No proactive scheduler in Phase 3:** A never-delivered job becomes failed
  when inspected after its deadline. Phase 4 may add scheduled reconciliation
  only from hosted evidence; this phase does not add Cloud Scheduler by default.
- **Cancellation is cooperative:** During provider work, cancellation is an
  intent and may not save provider cost. Atomic completion precedence keeps
  public state truthful.
- **Snapshot sensitivity:** Jobs contain bounded source/history/profile context
  needed for deterministic execution and retry. Public APIs and logs exclude
  it; Phase 4 must finalize retention/deletion.
- **Temporary worker deployment:** Phase 3 deploys only the private worker for
  real queue proof. Phase 4 owns final containers and deployment of both public
  API/UI and private worker.
- **Source drift:** This plan is current as of Phase 2 checkpoint
  `a1cf67e9a3359115583c290d08ae1624f977df12`, but every pass still needs a
  short source re-check before editing. Do not apply plan text over newer
  accepted code blindly.
- **Single-user boundary:** Phase 3 intentionally does not add shared
  workspace membership. Agent Col remains a single-user collaborative agent
  with workspace-scoped data.
- **No broad retention controls:** Phase 3 keeps bounded job/source snapshots
  for retry and evidence. Whole-account deletion, broad collaboration-history
  retention controls, and automatic raw-chat sensitive-data redaction remain
  useful additions deferred to a later phase.

## Explicit exclusions

- Generic single-file asynchronous jobs.
- Direct `/api/synthesize` conversion.
- Automatic delayed assistant messages or push notifications.
- Cloud Scheduler unless Phase 4 evidence approves it.
- General-purpose planners, workflow DAGs, Pub/Sub, GKE, task marketplaces, or
  arbitrary worker payloads.
- PDF upload or document ingestion.
- Shared workspaces, teams, project sharing, or membership ACLs.
- General unrestricted chat-history search or a semantic transcript index.
- Loosening sensitive-storage policy for password/key/credential-looking
  prompts.
- Whole-account deletion, broad collaboration-history retention controls, and
  automatic sensitive-data detection/redaction for raw persisted chat messages.
- Final container/public deployment, rate limiting, retention policy, and full
  ownership audit, which remain Phase 4.
- Submission documentation, clean-clone proof, architecture diagram, and demo
  production, which remain Phases 5 and 6.

## Stop and revise conditions

Stop the current pass and return with evidence plus a revised plan if:

- the implementation baseline is not the accepted Phase 2 checkpoint or a
  later explicitly accepted checkpoint;
- the accepted source no longer has a clean post-routing blueprint dispatch
  seam;
- implementation would pass `ChatTurnClaim` into a worker or fake one;
- generic artifacts must become asynchronous for blueprint proof;
- a task payload must contain user/workspace/session/source/artifact content;
- task headers or task names would be treated as authentication;
- artifact and job completion cannot be one Firestore transaction;
- a stale worker can commit after reclaim;
- cancellation state cannot deterministically race with completion;
- exact chat replay would rerun source selection, dispatch, or generation;
- a delayed model message is required to announce completion;
- safe local tests require a real Cloud Tasks queue;
- production can silently fall back to the fake dispatcher;
- worker/public content must enter logs;
- a new external workflow engine, Pub/Sub, scheduler, database, or queue is
  required;
- backend contracts must change during frontend-only 3F;
- Phase 3 needs final public service deployment owned by Phase 4;
- three approved corrections fail for the same underlying problem.

## Approval and checkpoint sequence

1. Repository owner reviews and approves or revises this Phase 3 plan.
2. After approval, checkpoint this documentation-only plan revision to
   `origin/main` if the repository owner wants the revised Phase 3 baseline
   fixed before implementation.
3. Present Pass 3A for explicit implementation approval.
4. For each pass 3A-3H: first inspect current source for drift, then RED,
   verify RED, GREEN, verify GREEN, refactor, focused
   verification, report, manual acceptance, then explicit checkpoint approval.
5. Mark Phase 3 complete only after 3H evidence is accepted and pushed.
