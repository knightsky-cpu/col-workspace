# Real Asynchronous Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the real chat/background-work decoupling so chat, Memory
Analyst, Note Curator, Artifact Builder, job reports, and direct UI actions can
operate side by side without owning or blocking each other's lifecycle.

**Architecture:** Preserve the existing AgentJob, worker lease, resource service,
approval, idempotency, and report foundations. Remove or replace the remaining
chat-owned durable effect paths, stale single-effect restrictions, and
whole-workspace frontend refresh coupling with explicit job/resource/report
boundaries.

**Tech Stack:** FastAPI, Firestore, asyncio worker tasks, Google ADK/GenAI,
vanilla frontend modules, Node test runner, pytest.

**Spec:** `docs/async-work/real-asynchronous-vision.md`

**Current-State Evidence:** `docs/async-work/memory-lifecycle-audit.md`,
`docs/async-work/notes-lifecycle-audit.md`,
`docs/async-work/artifact-lifecycle-audit.md`, and current source verified on
2026-09-03.

## Global Constraints

- Durable state changes require application-owned authorization.
- Memory remains governed and approval-gated.
- Workspace notes remain workspace-scoped and approval-gated unless created by
  an explicit direct UI flow with the existing contract.
- Artifacts remain durable resources with their own lifecycle.
- AgentJobs own background execution status.
- Job reports own public-safe terminal explanations.
- Chat must not invent, finalize, approve, or fail background outcomes.
- Independent supported work in the same turn must be accepted independently.
- Unsupported work must not erase supported queued work.
- UI surfaces should stay interactive while unrelated work is running.
- Idempotency, ownership, leases, governance, approval, and worker boundaries
  must not be weakened to get apparent parallelism.
- Do not introduce broad deterministic routing for arbitrary user intent.
- Each implementation pass requires TDD, focused verification, and manual
  verification before the next source-changing pass.
- Do not bundle memory category/product-policy changes with architectural
  decoupling.

---

## Normative Target

The target lifecycle from `real-asynchronous-vision.md` is:

```text
User action or Agent Col delegation
  -> deterministic or model-assisted intent acceptance
  -> application-owned job enqueue
  -> public queued receipt
  -> background worker leases and executes the job
  -> durable subsystem validates and persists the result or governed proposal
  -> job reaches completed, failed, or cancelled
  -> public-safe job report explains the terminal outcome
  -> affected UI surface refreshes from its own authoritative API
```

The important ownership rule is that chat may recognize, acknowledge, delegate,
and ask questions, but durable execution belongs to AgentJobs and workers,
durable resource state belongs to Memory/Notes/Artifacts services, and terminal
explanations belong to job reports.

The final end-to-end success case is:

```text
The user asks Agent Col a question.
Agent Col starts responding.
While it responds, the user creates a workspace note in the UI.
At the same time, an artifact job is running.
At the same time, a Memory Analyst job creates a pending memory proposal.
The Agents panel updates job lifecycle state.
The Notes panel updates note state.
The Memory panel updates memory proposal state.
The Artifact viewer updates artifact state.
Chat continues without blocking those surfaces.
No surface claims ownership of another surface's lifecycle.
No model-authored text contradicts authoritative application state.
```

## Verified Current State

### Working Architecture To Preserve

- `AgentJobRepository` already provides idempotent enqueue with private payload
  persistence in `enqueue_job_with_payload` and conflict checks by job id and
  idempotency key (`agent_job_repository.py:101-169`).
- `AgentJobRepository.lease_next_queued_job` supports action-kind-specific
  leasing for workers (`agent_job_repository.py:273-338`).
- App startup wires separate memory, note, and artifact workers with separate
  in-process background task sets (`main.py:2003-2027`,
  `main.py:2037-2062`, `main.py:2067-2092`).
- Memory jobs restore private payloads without live chat-turn lease ownership:
  `memory_command_from_payload` returns `turn_lease=None`
  (`memory_proposal_job_worker.py:100-128`).
- Memory worker execution is outside chat response generation and creates
  terminal reports (`memory_proposal_job_worker.py:164-181`,
  `memory_proposal_job_worker.py:230-320`).
- Note worker execution is outside chat response generation and creates
  terminal reports (`collaborative_note_job_worker.py:102-134`,
  `collaborative_note_job_worker.py:183-292`).
- Artifact worker execution is outside chat response generation and creates
  terminal reports (`agent_col_artifact_executor.py:489-527`,
  `agent_col_artifact_executor.py:576-758`).
- Agent Col queues explicit durable actions before routing in the queue-first
  path (`agent_col_turn_service.py:925-966`).
- Routed artifact turns now queue artifact work and return queued actions rather
  than completed artifact receipts in chat (`agent_col_turn_service.py:1154-1391`).
- Direct Notes UI operations use Notes-specific pending state rather than
  `state.pendingTurn` (`docs/async-work/notes-lifecycle-audit.md`, source
  evidence `frontend/notes-view.mjs:352-383` and
  `frontend/state.mjs:1624-1640`).
- Direct Memory approval uses a memory API path according to the memory audit;
  this direct approval boundary should be preserved.
- Work list/detail refresh already uses canonical artifact APIs and completed
  artifact jobs trigger Work refresh (`frontend/app.mjs:1199-1233`,
  `frontend/app.mjs:996-1088`).

### Remaining Coupling To Remove Or Replace

- `frontend/app.mjs` renders the whole workspace on every chat streaming delta
  (`frontend/app.mjs:1484-1495`).
- `frontend/app.mjs` refreshes Work and Notes on completed jobs, but not Memory
  for `propose_memory_signal` (`frontend/app.mjs:1199-1233`).
- `frontend/app.mjs` blocks workspace selection, creation, deletion, and new
  conversation while chat is pending (`frontend/app.mjs:1593-1648`,
  `frontend/app.mjs:2234-2247`).
- `frontend/requests.mjs` still routes structured memory decisions, memory
  clarification selections, artifact feedback decisions, collaborative note
  decisions, and continuity selections through `/api/chat`
  (`frontend/requests.mjs:111-122`).
- `main.py` still claims chat turns for structured decisions and records memory
  decisions, note decisions, memory clarification selections, and artifact
  feedback in the chat path (`main.py:4442-4520`,
  `main.py:4648-4805`).
- Preference-learning confirmation can still open memory clarification from the
  ordinary chat path (`main.py:4857-4894`).
- `supervisor_runtime.py` gives memory duplicate suppression via
  `memory_prequeued_for_turn`, but there is no equivalent `note_prequeued_for_turn`
  (`supervisor_runtime.py:454-482`).
- `collaborative_note_tool.py` can still enqueue note work from the responder
  after deterministic note prequeue because it only checks precompleted durable
  effects (`collaborative_note_tool.py:516-568`).
- `supervisor_runtime.py` still treats memory and note proposal receipts as
  conflicting in the same model tool pass (`supervisor_runtime.py:536-601`).
- `supervisor_runtime.py` validates at most one precompleted memory proposal and
  at most one precompleted note proposal (`supervisor_runtime.py:824-885`).
  That may be correct for model-tool fallback, but it must not block independent
  queued memory and note work.
- `supervisor.py` still contains the stale instruction: "Never create both a
  note proposal and a memory proposal or clarification in one ordinary turn"
  (`supervisor.py:141-159`), even though production responder instructions in
  `agent_col_responder.py` no longer contain that prohibition
  (`agent_col_responder.py:246-304`).
- `agent_col_turn_service._stable_merge_queued_actions` has memory-specific
  duplicate suppression only (`agent_col_turn_service.py:368-381`).
- Agent Col artifact feedback remains explicitly chat-owned
  (`agent_col_artifact_feedback_executor.py:1-199`) and persists through
  `record_chat_turn_artifact_feedback_effect` (`database.py:2907`).
- Legacy chat-turn artifact creation effects remain in `database.py`
  (`database.py:2547`, `database.py:2729`), even though the modern turn service
  queues artifacts.
- Direct generic artifact creation is outside chat but still synchronous with
  provider generation (`main.py:3875-3938`).
- Worker failure summaries for notes and artifacts collapse distinct failure
  causes into generic reports (`collaborative_note_job_worker.py:205-213`,
  `collaborative_note_job_worker.py:258-292`,
  `agent_col_artifact_executor.py:589-597`,
  `agent_col_artifact_executor.py:725-758`).
- The current worker dispatch model is best-effort in-process dispatch from the
  request that enqueued the job. Each worker has `run_one`, but there is no
  verified always-on drainer in source for jobs missed after process restart or
  dispatch loss (`memory_proposal_job_worker.py:183-207`,
  `collaborative_note_job_worker.py:136-160`,
  `agent_col_artifact_executor.py:529-552`).

## Implementation Phases

The phases below are dependency-aware. Each phase should be implemented as a
separate approval-gated pass under the repository's TDD workflow.

### Phase 1: Characterize The Current Async Boundary

**Purpose:** Lock down the already-working queue-first and worker boundaries
before removing stale coupling. This prevents future passes from accidentally
regressing artifact, note, or memory queue acceptance.

**Why First:** The system already has correct pieces. Characterization tests
make those pieces non-negotiable and give later cleanup a safety net.

**Expected Files:**

- Modify tests only:
  - `tests/test_agent_col_turn_service.py`
  - `tests/test_agent_col_turn_service_artifacts.py`
  - `tests/test_memory_proposal_job_worker.py`
  - `tests/test_collaborative_note_job_worker.py`
  - `tests/test_agent_col_artifact_executor.py`
  - `tests/frontend/app-runtime.test.mjs`
  - `tests/frontend/state.test.mjs`

**Source Evidence To Preserve:**

- Queue-first action order exists at `agent_col_turn_service.py:925-966`.
- Memory worker restores `turn_lease=None` at
  `memory_proposal_job_worker.py:118-128`.
- Note and artifact workers execute outside chat at
  `collaborative_note_job_worker.py:183-204` and
  `agent_col_artifact_executor.py:576-606`.

**Acceptance Criteria:**

- A single turn with explicit note + explicit memory + explicit artifact queues
  three `QueuedActionReceipt` objects without precompleted proposal receipts.
- The same turn can route to `clarify` or `direct` afterward without losing the
  queued actions.
- Worker payload restoration for memory, note, and artifact does not require or
  carry a live chat-turn owner token.
- Current artifact routed queue behavior still has `result.artifacts == ()`.
- Frontend tests prove existing completed artifact and note jobs refresh their
  resource surfaces.

**Product-Policy Exclusions:**

- Do not change memory category-slot conflict behavior.
- Do not change the deterministic parser's supported syntax.

### Phase 2: Make Frontend Surfaces Refresh From Their Own Owners

**Purpose:** Remove the most visible UI coupling: chat streaming should not
rerender the whole workspace, and completed Memory Analyst jobs should refresh
Memory like completed Note Curator and Artifact Builder jobs refresh their
surfaces.

**Why Before Backend Migration:** The UI must be able to observe independent job
completion before more backend work moves out of chat. This also makes manual
verification reliable.

**Expected Files:**

- Modify:
  - `frontend/app.mjs`
  - `frontend/state.mjs`
  - `frontend/chat-view.mjs`
  - `frontend/agents-view.mjs` only if render hooks need narrower entry points
- Tests:
  - `tests/frontend/app-runtime.test.mjs`
  - `tests/frontend/state.test.mjs`
  - `tests/frontend/chat-view.test.mjs`
  - `tests/frontend/agents-view.test.mjs`

**Source Evidence:**

- Whole-workspace render on each SSE delta is at `frontend/app.mjs:1484-1495`.
- Completed job refresh omits memory at `frontend/app.mjs:1199-1233`.
- Startup currently loads all surfaces independently at
  `frontend/app.mjs:2224-2228`.

**Planned Changes:**

- Add narrow render/update functions so chat deltas update only the chat surface
  and chat status.
- Keep explicit full `renderWorkspace()` for workspace selection, startup, and
  layout-level state changes.
- Extend `refreshAuthoritativeResourcesForCompletedJobs` so completed
  `propose_memory_signal` jobs call `loadMemory()`.
- Make resource refresh calls idempotent by job public ref, as Work/Notes already
  do with `refreshKey`.

**Acceptance Criteria:**

- Streaming SSE delta test observes chat render/update without Work, Notes,
  Memory, Workspace drawer, or Artifact viewer full rerender.
- Completed Memory Analyst job triggers exactly one Memory refresh for a job ref.
- Completed Artifact Builder and Note Curator refresh behavior is unchanged.
- Chat submit/complete/fail still renders the transcript correctly.

**Manual Verification Target:**

- Start a long chat response, then verify the Memory/Notes/Work panels are not
  visually reset on each text delta.

### Phase 3: Remove Stale Proposal-Conflict Rules And Add Note Prequeue Suppression

**Purpose:** Let independently supported memory and note work coexist while
preventing the responder from duplicating a deterministic note prequeue.

**Why After Phase 1:** The characterization tests will prove which queue
receipts are expected before changing runtime conflict behavior.

**Expected Files:**

- Modify:
  - `supervisor_runtime.py`
  - `collaborative_note_tool.py`
  - `agent_col_responder.py`
  - `supervisor.py`
  - `agent_col_turn_service.py`
- Tests:
  - `tests/test_supervisor_runtime.py`
  - `tests/test_agent_col_responder.py`
  - `tests/test_agent_col_turn_service.py`
  - `tests/test_collaborative_note_tool.py`

**Source Evidence:**

- Memory prequeue state exists at `supervisor_runtime.py:466-468`.
- Note state lacks `note_prequeued_for_turn` at `supervisor_runtime.py:472-482`.
- Note tool only checks precompleted effects at `collaborative_note_tool.py:537`.
- Runtime raises memory/note conflict at `supervisor_runtime.py:586-601`.
- Stale standalone supervisor instruction remains at `supervisor.py:153-154`.
- Memory-only queued action dedupe is at `agent_col_turn_service.py:368-381`.

**Planned Changes:**

- Add `note_prequeued_for_turn` to supervisor session state when prequeued
  actions contain `propose_collaborative_note`.
- Make `propose_collaborative_note` return `{"status": "no_note"}` when that
  flag is set, matching the memory prequeue guard in
  `memory_proposal_tool.py:562-563`.
- Remove or narrow the runtime conflict that rejects note and memory receipts
  solely because both are present. It may still reject duplicate or contradictory
  receipts for the same surface.
- Remove the stale note+memory prohibition from `supervisor.py`.
- Generalize queued action merge dedupe by durable action identity enough to
  avoid duplicate note receipts without hiding distinct note + memory + artifact
  queued actions.

**Acceptance Criteria:**

- Deterministically prequeued note work prevents a responder note tool call from
  enqueuing a second Note Curator job.
- Deterministically prequeued memory work still prevents duplicate Memory
  Analyst jobs.
- A model tool response containing one queued memory and one queued note no
  longer fails only because both exist.
- Conflicting two-note or two-memory receipts are still rejected.
- No stale instruction in `supervisor.py` forbids note + memory in one turn.

**Product-Policy Exclusions:**

- "At most one memory tool call per turn" may remain for model fallback. The
  decoupling requirement is that queue-first independent actions can coexist.

### Phase 4: Decouple Memory Decisions And Clarification Selection From `/api/chat`

**Purpose:** Move memory approval/rejection and clarification selection out of
the chat request lifecycle, while keeping governance and approval semantics.

**Why After Refresh And Runtime Cleanup:** The Memory UI must already refresh
from Memory Analyst completion, and runtime must not depend on chat to carry
memory decision receipts.

**Expected Files:**

- Modify:
  - `frontend/requests.mjs`
  - `frontend/app.mjs`
  - `frontend/api.mjs`
  - `main.py`
  - `trusted_memory_service.py` only if a direct clarification-selection command
    needs a new confirmation channel
  - `database.py` only if direct clarification selection needs a non-chat-turn
    persistence branch
- Tests:
  - `tests/frontend/api.test.mjs`
  - `tests/frontend/app-runtime.test.mjs`
  - `tests/test_main.py`
  - `tests/test_trusted_memory_service.py`
  - `tests/test_chat_turn_database.py` for legacy compatibility boundaries

**Source Evidence:**

- Structured memory requests are routed to `/api/chat` at
  `frontend/requests.mjs:111-122`.
- Chat path handles memory decisions at `main.py:4648-4704`.
- Chat path handles clarification selection with a live `ProposalTurnLease` at
  `main.py:4775-4805`.
- Memory job restoration already proves proposals can be created without a turn
  lease (`memory_proposal_job_worker.py:118-128`).

**Planned Changes:**

- Keep existing direct memory approval/rejection API as the canonical approval
  path.
- Add a memory-owned API for clarification selection if one does not already
  exist.
- Route UI memory clarification selections to the memory API instead of
  `/api/chat`.
- Keep old `/api/chat` structured memory paths temporarily as compatibility
  shims only if tests prove current clients still need them.
- Ensure direct clarification selection creates a pending governed proposal or
  no-effect result without chat-turn ownership.

**Acceptance Criteria:**

- Selecting a memory clarification while chat is pending does not call
  `/api/chat` and does not require a chat turn claim.
- Memory proposal approval/rejection remains direct and governance-preserving.
- Legacy `/api/chat` memory decision tests either remain as compatibility tests
  or are replaced by direct API tests in the same pass.
- Memory decision and clarification failure responses remain public-safe and do
  not expose private job or turn identifiers.

**Product-Policy Decision Required:**

- Whether memory clarification selection should produce a public AgentJob report
  or remain a direct Memory API result. This is ownership/reporting policy, not
  required to decouple chat.

### Phase 5: Quarantine Or Remove Chat-Based Collaborative Note Decisions

**Purpose:** Make direct Notes APIs the only active UI lifecycle for note
approval/rejection and prevent note decisions from needing chat turn ownership.

**Why After Memory Decisions:** Memory has stricter governance and clarification
complexity. Notes are simpler and already mostly direct, so this pass can follow
the memory decision migration pattern.

**Expected Files:**

- Modify:
  - `frontend/requests.mjs`
  - `frontend/app.mjs`
  - `main.py`
  - `collaborative_note_service.py` only if provenance needs a non-chat source
    event model
  - `database.py` only to quarantine legacy turn-effect helpers behind tests
- Tests:
  - `tests/frontend/api.test.mjs`
  - `tests/frontend/app-runtime.test.mjs`
  - `tests/test_main.py`
  - `tests/test_collaborative_note_service.py`
  - `tests/test_chat_turn_database.py`

**Source Evidence:**

- Direct note decision route exists at `main.py:2775-2821`.
- Chat-based note decision path remains at `main.py:4705-4773`.
- Legacy request builder remains at `frontend/requests.mjs:234-257`.
- Optional note turn-effect restrictions remain in `database.py:4162-4232`.

**Planned Changes:**

- Remove the frontend builder and selection path for chat-based note decisions
  when no current caller remains.
- Keep direct note approval/rejection through `decideNoteProposal`.
- If the backend compatibility route remains, mark it compatibility-only and
  ensure the active UI no longer uses it.
- Do not change Note Curator job proposal creation in this pass.

**Acceptance Criteria:**

- Approving and rejecting notes from the Notes UI never calls `/api/chat`.
- Note approval/rejection can happen while chat is pending.
- Direct note decision response still refreshes Notes and AgentJob reports.
- Chat-based note decision tests are either removed with callers or explicitly
  renamed as compatibility coverage.

**Product-Policy Exclusion:**

- Do not remove the synthetic source message used for direct UI note proposal
  provenance until a replacement provenance model is designed.

### Phase 6: Move Agent Col Artifact Feedback Out Of Chat-Turn Effects

**Purpose:** Artifact feedback from Agent Col should be artifact-owned durable
work, not a chat-owned effect.

**Why After Memory/Note Decisions:** Artifact feedback needs a canonical target
and may update artifact feedback counts. It should follow after simpler direct
approval paths are decoupled.

**Expected Files:**

- Modify or create:
  - `agent_col_artifact_feedback_executor.py`
  - `artifact_feedback_service.py`
  - `agent_job_repository.py` only if a new action kind is needed
  - `main.py`
  - `frontend/app.mjs`
  - `frontend/api.mjs`
  - `database.py`
- Tests:
  - `tests/test_agent_col_artifact_feedback_executor.py`
  - `tests/test_chat_turn_database.py`
  - `tests/test_agent_job_repository.py`
  - `tests/frontend/api.test.mjs`
  - `tests/frontend/app-runtime.test.mjs`

**Source Evidence:**

- The current executor is explicitly chat-owned at
  `agent_col_artifact_feedback_executor.py:1`.
- It calls `record_chat_turn_artifact_feedback_effect` at
  `agent_col_artifact_feedback_executor.py:119-123`.
- The direct feedback API already persists feedback through
  `artifact_feedback_service.record_feedback` at `main.py:4320-4336`.
- The artifact feedback service resolves canonical targets before persistence
  (`artifact_feedback_service.py:192-230`).

**Planned Changes:**

- Prefer reusing direct `ArtifactFeedbackService.record_feedback` as the
  resource-owned persistence boundary.
- Introduce an AgentJob-backed artifact feedback action only if feedback can be
  initiated by Agent Col while chat continues. Use a specific action kind such
  as `record_artifact_feedback` if added.
- Ensure artifact feedback jobs/reports refresh Work detail or feedback list
  from canonical APIs.
- Retire or quarantine `record_chat_turn_artifact_feedback_effect` for active
  paths after replacement tests are green.

**Acceptance Criteria:**

- Agent Col can accept artifact feedback without writing artifact feedback onto
  the active chat turn.
- Direct Work UI feedback remains direct and idempotent.
- Artifact feedback completion refreshes canonical artifact feedback state.
- Feedback failure produces a public-safe job report if AgentJob-backed.
- Existing feedback target validation and schema-conflict handling remain.

### Phase 7: Improve Worker Failure Reports Without Weakening Boundaries

**Purpose:** Make failed AgentJob reports diagnostic enough to reconcile resource
state without exposing private payloads or internal identifiers.

**Why Here:** After durable lifecycle ownership is cleaner, failures should be
explained at the job/report layer rather than by chat.

**Expected Files:**

- Modify:
  - `memory_proposal_job_worker.py`
  - `collaborative_note_job_worker.py`
  - `agent_col_artifact_executor.py`
  - `agent_col_agent_jobs.py` only if report summary enum/shape needs expansion
  - `tests/test_memory_proposal_job_worker.py`
  - `tests/test_collaborative_note_job_worker.py`
  - `tests/test_agent_col_artifact_executor.py`

**Source Evidence:**

- Memory has distinct known error codes in worker branches
  (`memory_proposal_job_worker.py:252-319`).
- Note failures collapse several causes into one failure summary
  (`collaborative_note_job_worker.py:205-213`,
  `collaborative_note_job_worker.py:258-292`).
- Artifact failures catch all exceptions and emit one generic summary
  (`agent_col_artifact_executor.py:589-597`,
  `agent_col_artifact_executor.py:725-758`).

**Planned Changes:**

- Preserve private exception details in server logs where appropriate.
- Map expected failure classes to public-safe report summaries.
- Keep raw prompts, private payloads, owner tokens, source ids, and model
  reasoning out of public reports.
- Add tests for each expected public summary.

**Acceptance Criteria:**

- Artifact generation timeout, provider validation failure, invalid payload, and
  persistence failure produce distinct public-safe failure codes/summaries.
- Note proposal conflict, invalid note candidate, and turn-state errors produce
  distinct public-safe failure codes/summaries.
- Memory conflict and already-active summaries remain unchanged.
- Unexpected exceptions are logged with class information but public reports
  remain sanitized.

### Phase 8: Add A Recoverable AgentJob Drainer Boundary

**Purpose:** Move from best-effort request-dispatched background tasks toward a
recoverable queue execution model that can pick up queued work after missed
dispatch or process restart.

**Why After Worker Semantics:** The workers must have stable ownership,
idempotency, failure, and report behavior before a drainer runs them
continuously.

**Expected Files:**

- Create or modify:
  - `agent_job_dispatcher.py` or a similarly scoped module
  - `main.py`
  - `agent_job_repository.py` only if lease query performance/filters need
    adjustment
  - worker tests for memory, notes, artifacts
  - `tests/test_agent_job_repository.py`
  - `tests/test_main.py`

**Source Evidence:**

- Workers expose `run_one` by action kind:
  - memory: `memory_proposal_job_worker.py:183-207`
  - notes: `collaborative_note_job_worker.py:136-160`
  - artifacts: `agent_col_artifact_executor.py:529-552`
- Current app dispatches immediate in-process tasks only after enqueue:
  - memory: `main.py:2043-2062`
  - notes: `main.py:2073-2092`
  - artifacts: `main.py:2012-2016`
- Repository leasing is scoped and transactional
  (`agent_job_repository.py:273-338`).

**Planned Changes:**

- Add a bounded in-process drainer that periodically leases queued jobs by
  supported action kind while the app is running.
- Keep immediate dispatch on enqueue for responsiveness.
- Ensure the drainer does not create unbounded concurrency. Use per-action-kind
  or global limits that still allow Memory Analyst, Note Curator, and Artifact
  Builder to run concurrently.
- Keep lease ownership per worker invocation and preserve idempotency.
- Do not introduce external infrastructure in this pass.

**Acceptance Criteria:**

- A queued memory job with no immediate dispatcher is picked up by `run_one`.
- A queued note job with no immediate dispatcher is picked up by `run_one`.
- A queued artifact job with no immediate dispatcher is picked up by `run_one`.
- Concurrent queued memory, note, and artifact jobs can each enter running state
  without one action kind starving the others.
- Drainer shutdown does not mark queued jobs failed.

**Product-Policy Decision Required:**

- Whether a future production deployment should use an external durable worker
  process, Cloud Run job, Pub/Sub, Cloud Tasks, or another queue service. The
  in-process drainer is a local architecture bridge, not a final operations
  decision.

### Phase 9: Decouple Left Drawer And Workspace-Level UI Actions From Chat Pending State

**Purpose:** Let the left drawer and resource surfaces remain usable while chat
is streaming, while preserving safeguards for actions that truly cannot happen
mid-turn.

**Why After Backend Lifecycles:** It is safer to loosen UI gating after durable
work no longer depends on chat-turn effects.

**Expected Files:**

- Modify:
  - `frontend/app.mjs`
  - `frontend/state.mjs`
  - `frontend/workspace-view.mjs`
  - `frontend/chats-view.mjs`
  - `frontend/chat-view.mjs`
- Tests:
  - `tests/frontend/app-runtime.test.mjs`
  - `tests/frontend/state.test.mjs`
  - `tests/frontend/workspace-view.test.mjs` if present or add focused coverage
  - `tests/frontend/chat-view.test.mjs`

**Source Evidence:**

- Workspace select/create/delete guard on chat pending:
  `frontend/app.mjs:1593-1648`.
- New conversation guard on chat pending:
  `frontend/app.mjs:2234-2247`.
- Chat session load uses `selectCanSubmit`, which includes pending-turn gating
  (`frontend/app.mjs:1422-1445`).

**Planned Changes:**

- Separate "chat submit eligibility" from "resource surface action eligibility".
- Allow read-only drawer refresh, note creation, memory approval, artifact
  inspection, and job report inspection during chat streaming.
- Keep destructive workspace deletion guarded if it would invalidate the active
  chat workspace.
- Treat starting a new conversation during an active turn as a product decision:
  either allow independent pending chat per session or keep that specific guard.

**Acceptance Criteria:**

- User can open/refresh Agents, Notes, Memory, Work, and job reports while chat
  is pending.
- User can create a direct note while chat is pending.
- User can approve/reject a memory proposal while chat is pending.
- User can inspect an artifact while chat is pending.
- Workspace deletion remains blocked for the active workspace while chat is
  pending unless a product decision explicitly allows it.

**Product-Policy Decisions Required:**

- Whether a user may switch workspaces while an active chat turn is streaming.
- Whether a user may start a new conversation while an active chat turn is
  streaming.
- Whether active chat should continue in the old workspace/session if the user
  changes the visible workspace.

### Phase 10: Quarantine Legacy Chat-Turn Durable Effect Helpers

**Purpose:** Remove old single-effect assumptions from active paths after their
replacement boundaries are proven.

**Why Last:** These helpers are still covered by tests and may serve
compatibility paths. Removing them before migration would increase risk without
improving user-visible async behavior.

**Expected Files:**

- Modify:
  - `database.py`
  - `main.py`
  - `agent_col_artifact_executor.py`
  - `agent_col_artifact_feedback_executor.py`
  - tests that currently assert chat-turn artifact/note/feedback effects

**Source Evidence:**

- Legacy artifact effect helpers:
  `database.py:2547`, `database.py:2729`.
- Legacy artifact feedback effect helper:
  `database.py:2907`.
- Legacy note turn-effect restriction:
  `database.py:4162-4232`.
- Current modern Artifact Builder path queues work instead of returning
  completed artifact receipts in chat (`agent_col_turn_service.py:1154-1391`).

**Planned Changes:**

- Remove active callers first; then either delete helpers or mark them
  compatibility-only with tests that prove ordinary async paths do not call them.
- Remove stale single-durable-effect assertions from ordinary async code paths.
- Preserve chat turn replay/idempotency for chat messages themselves.

**Acceptance Criteria:**

- Ordinary note + memory + artifact turn does not call any legacy
  `record_chat_turn_*_effect` helper for durable resource creation.
- Chat turn completion remains idempotent and replay-safe.
- Legacy tests are updated to match current architecture or explicitly scoped to
  compatibility.

## Final End-To-End Acceptance Boundary

After all phases, add a focused integration/browser scenario that proves the
real async target:

```text
1. Start a chat request that streams for long enough to observe pending state.
2. While chat is streaming, create a note through the Notes UI.
3. While chat is streaming, approve or reject a pending memory proposal.
4. Queue or observe an Artifact Builder job.
5. Verify Agents shows independent lifecycle updates.
6. Verify Notes refreshes from Notes API.
7. Verify Memory refreshes from Memory API.
8. Verify Work/Artifact Viewer refreshes from artifact APIs.
9. Verify chat continues and completes without owning those results.
10. Verify chat text contains only queued acknowledgements unless authoritative
    completed receipts/reports are present.
```

Automated acceptance should include:

- Backend test proving one turn can queue `propose_collaborative_note`,
  `propose_memory_signal`, and `create_artifact` as independent jobs.
- Backend test proving memory, note, and artifact workers can lease/run distinct
  jobs concurrently without job-id/idempotency collisions.
- Frontend test proving streaming chat deltas do not rerender or disable
  unrelated resource surfaces.
- Frontend test proving completed memory, note, and artifact jobs refresh their
  own resource surfaces.
- API tests proving note and memory approval paths do not use `/api/chat`.
- API or integration tests proving Agent Col artifact feedback no longer writes
  through chat-turn durable effect ownership.

## Product-Policy Decisions To Keep Separate

These questions should not block architectural decoupling, but they require
explicit product decisions before implementation:

- Should memory allow multiple pending proposals in the same category when the
  values are distinct?
- Should memory clarification selection produce AgentJob reports or remain a
  direct Memory API outcome?
- Should direct generic artifact creation become job-backed by default, or only
  for provider-generated/slow artifacts?
- Should artifact metadata/archive/restore/delete remain direct operations or
  appear in AgentJobs for auditability?
- May users switch workspaces during an active chat turn?
- May users start a new conversation during an active chat turn?
- What safe diagnostic detail belongs in public failed job reports versus
  server logs only?

## Self-Review Notes

- The plan preserves existing AgentJob, worker, report, and direct resource API
  foundations instead of redesigning them.
- The plan does not weaken memory governance or approval.
- The plan does not introduce generic regex routing or broad deterministic
  interpretation.
- The plan treats `async-work-notes.md` as historical context; where it conflicts
  with current source, current source and lifecycle audits control.
- The plan includes artifact lifecycle evidence because artifact decoupling is
  part of the requested final boundary, even though the four planning-basis
  documents named by the user did not list the artifact audit explicitly.
