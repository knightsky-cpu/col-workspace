# Memory Lifecycle Audit

Date: 2026-09-03

This document records the current memory lifecycle as observed in source after
the queue-first memory decoupling work. It is intentionally source-evidence
oriented so future async-work passes can distinguish the intended architecture
from the current implementation.

## Target Direction

Memory work should be asynchronous and governed:

- Agent Col may accept an explicit memory request and enqueue governed memory
  work.
- Agent Col should not present final memory creation, failure, approval, or
  persistence status as if chat owns that lifecycle.
- The Memory Analyst job, job events, job reports, and Memory UI should be the
  authoritative surfaces for pending proposals, failures, active memories, and
  approval state.
- Memory creation should remain governed: no direct storage from chat, no direct
  approval from model output, and no bypass of policy, evidence validation,
  proposal governance, user approval, or persistence rules.
- Memory jobs should be able to run alongside note and artifact jobs without
  blocking chat or each other.

## Current End-To-End Flow

### 1. Ordinary Chat Request

The frontend sends ordinary user prompts to `/api/chat/stream`, while structured
memory decisions and clarification selections still use `/api/chat`.

Source evidence:

- `frontend/requests.mjs` `selectChatEndpoint` sends requests containing
  `memory_decision` or `memory_clarification_selection` to `/api/chat`.
- `frontend/requests.mjs` still exports `buildMemoryDecisionChatRequest` and
  `buildMemoryClarificationSelectionChatRequest`.

Relevant files:

- `frontend/requests.mjs`
- `frontend/app.mjs`
- `main.py`

Implication:

Ordinary memory intent can now be queue-first, but some memory decision and
clarification paths are still chat-coupled.

### 2. Chat Turn Claim And Continuity Gate

The backend claims the chat turn through `database.claim_chat_turn(...)` before
the Agent Col turn service runs. Explicit memory clauses are now checked before
continuity resolution consumes the turn.

Source evidence:

- `main.py` claims the chat turn with structured fields such as
  `memory_decision`, `memory_clarification_selection`, and
  `collaborative_note_decision`.
- `main.py` skips continuity resolution when `has_explicit_memory_clause(...)`
  returns true.
- `continuity_service.py` still has broad prior-context classification, but the
  explicit-memory precheck prevents clear new-memory commands from entering
  continuity.

Relevant files:

- `main.py`
- `continuity_service.py`
- `agent_col_turn_service.py`

Current behavior:

`remember that I like pancakes...` is treated as new memory work instead of a
historical continuity lookup.

### 3. Explicit Memory Clause Detection

`AgentColTurnService` owns the deterministic explicit-memory clause parser. It
recognizes narrowly scoped forms such as:

- `remember that I ...`
- `please remember I ...`
- embedded clauses such as `also remember ...`
- `and remember my preference is ...`

Source evidence:

- `agent_col_turn_service.py` defines `_EXPLICIT_MEMORY_CLAUSE`.
- `_explicit_memory_clause_text(...)` extracts the request text and memory body.
- `_explicit_memory_command(...)` builds a `NaturalMemoryCommand` with a
  `ProfileCandidateDecision`.

Current mapping:

```text
category = "user_requested_memory"
canonical_value = extracted body
evidence_text = extracted request text
```

Important finding:

There is no source-level distinction between the words `love` and `like` in the
explicit memory parser. Both are accepted as part of the extracted memory body
when they follow a supported explicit-memory clause shape.

### 4. Queue-First Durable Acceptance

`AgentColTurnService._queue_explicit_durable_actions(...)` queues explicit
durable work before model routing. The current ordering is:

1. artifact
2. workspace note
3. memory

Source evidence:

- Artifact directives are queued through the artifact executor.
- Workspace-note commands are queued through the note queue.
- Memory commands are queued through the memory queue.

Relevant file:

- `agent_col_turn_service.py`

Current behavior:

A single user turn can now queue note, memory, and artifact work before the
model responder finishes. This is aligned with the async direction.

Current limitation:

Memory command queueing currently appends the memory queued action but does not
increment the local `next_index` afterward. That has not surfaced as a current
failure because memory is last in the queue-first ordering, but it is an action
index detail to preserve if later work is added after memory.

### 5. Memory Job Creation And Dispatch

The application creates a `MemoryProposalJobWorker`, wraps it in a local
`MemoryQueue`, persists the job, reloads it, and dispatches it immediately as an
in-process asyncio task.

Source evidence:

- `main.py` constructs `MemoryProposalJobWorker`.
- `main.py` defines `dispatch_memory_job(...)`.
- `main.py` defines `MemoryQueue.queue(...)`, which calls
  `queue_memory_agent_job(...)`, reloads the job, then dispatches it.
- `memory_proposal_job_worker.py` `dispatch(...)` creates an asyncio task for
  `run_job(...)`.

Relevant files:

- `main.py`
- `memory_proposal_job_worker.py`
- `agent_job_repository.py`

Concurrency implication:

Memory jobs are not synchronously executed by chat. They are dispatched as
background tasks. Artifact and note jobs follow the same broad pattern, so the
backend has the beginning of independent concurrent execution.

Durability limitation:

The dispatch model is best-effort in-process async work. Worker methods such as
`run_one(...)` can lease queued work by action kind, but source search did not
show a durable external scheduler or always-on drainer that continuously
recovers and executes missed queued jobs after process restart or dispatch loss.

### 6. Job Payload And Candidate Restoration

Memory jobs store a private `AgentJobPayload`. The worker restores it into a
`NaturalMemoryCommand` before calling the governed service.

Source evidence:

- `memory_proposal_job_worker.py` `memory_job_payload(...)` stores governed
  command data.
- `memory_proposal_job_worker.py` `raw_memory_job_payload(...)` stores raw
  provider candidate data before strict validation.
- `memory_proposal_job_worker.py` `memory_command_from_payload(...)` validates
  provider decisions through `validate_provider_natural_memory_decision(...)`.

Relevant files:

- `memory_proposal_job_worker.py`
- `memory_candidate_decisions.py`

Current behavior:

Provider alias normalization supports `profile_candidate` payloads that contain
`value` instead of `canonical_value`, but only for the supported narrow case.
Strict governed schema validation remains in place.

### 7. Governed Memory Proposal Creation

The worker calls `TrustedMemoryService.handle_natural_memory_decision(...)`.
For profile candidates, the service:

1. validates evidence against the source message;
2. derives proposal origin IDs;
3. calls `database.create_guarded_memory_proposal_v2(...)`;
4. returns a pending proposal receipt.

Source evidence:

- `trusted_memory_service.py` validates decision evidence before proposal
  creation.
- `trusted_memory_service.py` handles `ProfileCandidateDecision` by calling
  `create_guarded_memory_proposal_v2(...)`.
- `database.py` enforces active-signal and pending-proposal conflict rules.

Relevant files:

- `trusted_memory_service.py`
- `database.py`
- `memory_policy.py`

Governance preserved:

The worker creates pending proposals only. It does not activate memory. User
approval remains required.

### 8. Pending Proposal Conflicts

The database currently enforces a category-wide pending proposal slot. For the
general category `user_requested_memory`, any unexpired pending proposal in that
category blocks another pending proposal, even if the value is semantically
different.

Source evidence:

- `database.py` raises `MemoryProposalConflictError` when an unexpired pending
  proposal already occupies the category.
- `memory_proposal_job_worker.py` maps that exception to:
  `A pending memory proposal already exists for this category.`

Observed effect:

If the user asks to remember one preference and leaves that proposal pending,
a second unrelated `user_requested_memory` request can fail at the worker even
though the explicit-memory queue acceptance succeeded.

This is not caused by the words `love` or `like`; it is caused by category-slot
governance.

### 9. Job Completion, Failure, Events, And Reports

The worker writes job events and creates job reports.

Completion path:

- job status becomes `completed`;
- event message is `Memory proposal created.`;
- report title is `Memory proposal pending review`;
- report summary is `A memory proposal was created and is pending your review.`;
- public resource label is the proposed memory value.

Failure path:

- job status becomes `failed`;
- failure summary is selected by error code;
- report title is `Memory proposal not created`;
- known summaries include:
  - `A pending memory proposal already exists for this category.`
  - `That memory is already active.`
  - `The memory request could not be attached to the current turn.`
  - `Memory proposal could not be created.`

Source evidence:

- `memory_proposal_job_worker.py` `_complete_job(...)`
- `memory_proposal_job_worker.py` `_fail_job(...)`
- `memory_proposal_job_worker.py` `_memory_failure_report(...)`

Current diagnostic limitation:

Expected failure branches are converted to sanitized job summaries. Unexpected
background exceptions are logged, but expected conflict/state branches do not
log the underlying exception detail. This can make live failures hard to
diagnose from stdout alone unless persisted job reports/events are inspected.

### 10. Memory UI And Approval

The Memory panel reads memory state through direct API calls. Approval and
rejection also use a direct memory API path.

Source evidence:

- `frontend/api.mjs` `decideMemoryProposal(...)` posts to
  `/api/users/{user_id}/memory/proposals/{proposal_id}/{decision}`.
- `frontend/app.mjs` `submitMemoryDecision(...)` calls that direct API.
- `main.py` exposes `decide_memory_proposal(...)` as a direct memory endpoint.
- `trusted_memory_service.py` accepts `confirmation_channel="memory_api"` for
  direct Memory UI approval.

Relevant files:

- `frontend/api.mjs`
- `frontend/app.mjs`
- `main.py`
- `trusted_memory_service.py`

Current behavior:

The Memory panel approval/rejection path is properly decoupled from chat.

Remaining old path:

The chat endpoint still has a structured `memory_decision` branch using
`confirmation_channel="chat_decision"`. That path remains for compatibility
with old chat-driven memory decision flows.

## Current Chat Coupling Problems

### Agent Col Still Narrates Memory Outcomes

The responder instructions state that queued memory work is not final memory
status and that final status belongs to Memory UI and job reports.

Source evidence:

- `agent_col_responder.py` says queued memory work must not be described as a
  pending, created, submitted, saved, stored, remembered, approved, or failed
  memory outcome.

However, the sanitizer currently removes only success/completion claims for
queued memory work. It does not remove false-negative claims such as:

- `I wasn't able to create a memory proposal...`
- `The memory proposal was not created...`

Source evidence:

- `supervisor_runtime.py` `_QUEUED_MEMORY_COMPLETION_CLAIM_PATTERN` only covers
  completion/saved/submitted language.
- `_sanitize_queued_work_response_text(...)` removes matching queued completion
  claims but does not address queued failure claims.

Observed effect:

The UI can show a pending memory proposal while the chat response says the
proposal was not created. This is a chat-reporting problem, not necessarily a
memory lifecycle failure.

### Memory Job Completion Does Not Refresh Memory Panel

Completed artifact and note jobs trigger resource refreshes from the agent-job
stream/list path. Completed memory jobs do not.

Source evidence:

- `frontend/app.mjs` `refreshAuthoritativeResourcesForCompletedJobs(...)`
  refreshes Work for `create_artifact`.
- It refreshes Notes for `propose_collaborative_note`.
- It does not refresh Memory for `propose_memory_signal`.

Observed effect:

Memory panel visibility can depend on chat completion refreshes, manual
refreshes, or unrelated Memory UI loads instead of memory job completion.

### Chat Streaming Rerenders The Whole Workspace

Each streaming chat delta updates pending response text and calls
`renderWorkspace()`.

Source evidence:

- `frontend/app.mjs` `submitRequest(...)` calls `renderWorkspace()` on each SSE
  delta.

Impact:

Chat streaming is still coupled to the entire workspace surface. This conflicts
with the desired model where chat, drawer panels, job updates, notes, memory,
and artifact viewer can update independently.

### Memory Clarification Selection Still Uses Chat

The chat view sends memory clarification selections through a chat request.

Source evidence:

- `frontend/app.mjs` `onSelectMemoryClarification(...)` builds a
  `buildMemoryClarificationSelectionChatRequest(...)`.
- `frontend/requests.mjs` routes that structured request to `/api/chat`.
- `main.py` handles `payload.memory_clarification_selection` inside the chat
  pipeline.

Impact:

Memory clarification selection is still coupled to chat turn availability,
chat idempotency, and chat response completion.

### Preference Learning Still Mutates Memory From Chat

After the turn service returns a chat response, `main.py` may run preference
learning and open a memory clarification directly from the chat path.

Source evidence:

- `main.py` calls `preference_learning_service.capture(...)`.
- If a hypothesis is surfaced, `main.py` calls
  `memory_service.open_preference_hypothesis_confirmation(...)`.
- The resulting memory clarification is inserted into `chat_response`.

Impact:

This is a memory side effect owned by chat rather than by the Memory Analyst
job lifecycle.

## Current Answer To The Love Versus Like Question

The current source does not treat `love` and `like` differently in deterministic
explicit-memory acceptance.

Evidence:

- The parser accepts `remember that i ...` and captures the rest as body.
- The governed `user_requested_memory` value validation checks string shape,
  length, alphabetic content, and prohibited patterns. It does not require the
  word `like`.
- The worker failure summary observed for similar cases is consistent with
  pending proposal category conflict, not lexical rejection.

Most likely explanation for the observed mismatch:

1. Queue-first memory acceptance succeeded.
2. The worker created or attempted to create a pending proposal.
3. Chat produced an incorrect failure-style narrative because final memory
   status is still leaking into the responder surface.
4. A separate Memory Analyst failure can occur when the database rejects another
   pending `user_requested_memory` proposal because the category slot is already
   occupied.

## Async Architecture Gaps To Resolve Later

These are findings, not implemented changes:

1. Make queued-memory chat text purely acknowledge queue acceptance, never final
   success or failure.
2. Refresh Memory when completed `propose_memory_signal` jobs appear in the
   agent-job stream/list path.
3. Move memory clarification selection out of `/api/chat` into a memory-owned
   direct or job-backed lifecycle.
4. Move preference-learning memory confirmations out of ordinary chat response
   completion or explicitly document them as a separate background memory
   lifecycle.
5. Decide whether `user_requested_memory` should allow multiple pending
   proposals by value/origin instead of one category-wide pending slot.
6. Add or verify a durable job-drainer process for queued jobs that were not
   dispatched in-process.
7. Partition frontend rendering so chat deltas update only chat, agent job
   events update Agents, memory events update Memory, note events update Notes,
   and artifact events update Work/Artifact Viewer.

## Summary

The current memory lifecycle has a working queue-first governed path for
explicit new-memory commands, and Memory UI approval is already direct. The
remaining problems are lifecycle ownership and surface coupling:

- chat still contains legacy memory decision and clarification branches;
- chat can still narrate final memory outcomes incorrectly;
- Memory does not refresh from Memory Analyst job completion;
- preference-learning memory clarification remains chat-owned;
- category-wide pending proposal governance can make unrelated explicit memory
  requests conflict;
- background worker dispatch is in-process and does not yet prove durable
  asynchronous draining.

This confirms the repository is moving toward true asynchronous work, but the
memory lifecycle is not fully decoupled yet.
