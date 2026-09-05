# Agent Col Async Work Notes

Date: 2026-09-02

This document records the async orchestration work completed during the current Agent Col development session. It is intended as a detailed engineering record: what decisions were made, why those decisions were made, what implementation passes have already changed, what failures were observed, and which boundaries remain unresolved.

## Starting Point

Agent Col originally behaved too much like a request-bound chatbot for durable work. A single chat turn could try to create an artifact, propose a workspace note, propose durable memory, retrieve history, and explain the result all inside one request/response pipeline. That design created several problems:

- durable side effects competed inside one chat turn;
- note, memory, and artifact effects could block the user-facing response;
- retries and replay risked creating duplicate or contradictory durable effects;
- failures in one durable subsystem could collapse the whole chat response;
- logs and UI did not provide enough reliable evidence about what happened.

The core architectural decision was to move toward server-owned jobs and subagent-visible orchestration, while keeping application policy and user approval authoritative.

## Key Architecture Decision

The accepted direction is:

```text
User
  -> Agent Col / Supervisor
       -> conversation, reasoning, challenge, collaboration
       -> intent validation and orchestration decision
       -> queued or delegated durable work
            -> job idempotency
            -> lifecycle status
            -> retries/failure state
            -> approval-gated persistence where required
       -> public receipt/result
  -> user-facing explanation
```

The important distinction is that Agent Col owns the collaboration, not all durable execution. The application owns durable state, policy, authorization, lifecycle, and receipts.

This avoids the old failure mode:

```text
Model says "done"
  -> hopefully persistence agrees
```

The target model is:

```text
Model proposes or delegates
  -> application authorizes
  -> job executes
  -> application persists
  -> receipt proves
  -> Col reports
```

## Decisions And Rationale

### Agent Col Is The Public Orchestrator

Decision: Agent Col should be the public conversational orchestrator, not the public narrator of backend orchestration.

Reason: users should experience Agent Col as a collaborator, not as a stream of internal job IDs, raw prompts, tool payloads, owner tokens, or private execution details. Internal orchestration belongs in backend logs and public-safe projections such as the Agents panel.

### Receipts Are Required For Durable Claims

Decision: every user-visible claim that work was queued, completed, failed, saved, created, or delegated must be backed by an authoritative receipt.

Reason: this prevents hallucinated action claims. A model response cannot be treated as proof that a durable write happened. The proof must come from the application-owned effect, job, or proposal receipt.

### Working State Is Not Authorization

Decision: working state can support continuity, but it must not authorize durable writes.

Reason: working state is short-lived cognitive context. It may contain hypotheses, plans, or previous task context, but those are not the same as user authorization or application-approved durable state.

### Workspace Notes, Memory, Artifacts, And Chat History Are Separate Surfaces

Decision: keep these state types distinct.

Rationale:

- `working_state`: short-lived cognitive continuity;
- workspace notes: durable project/workspace knowledge;
- memory: durable user-level preference or profile knowledge;
- chat history: historical conversation evidence;
- artifacts: durable generated outputs.

Conflating these surfaces causes incorrect persistence behavior. A workspace decision should not automatically become durable user memory, and a remembered user preference should not be treated as a project artifact.

### Duplicate Job Protection Is Required

Decision: if an authoritative receipt shows equivalent work is already queued, running, completed, or awaiting approval, Agent Col should continue from that lifecycle state instead of recreating the work.

Reason: retries, stream recovery, replay, and response reconstruction can otherwise create duplicate jobs or duplicate proposals.

### Evidence Specialists Are Distinct From Execution Agents

Decision: evidence specialists such as research/source experts should not share the same behavioral cap or semantics as durable-action execution agents.

Reason: research/source calls gather evidence; artifact, note, memory, retrieval, and workflow agents perform governed application work. These have different lifecycle and authority rules.

### Once Work Is Delegated, Col Should Not Also Reproduce It

Decision: once work has been queued or delegated, Agent Col should not independently generate the full unfinished result in the same response.

Reason: otherwise the chat answer can compete with the eventual authoritative artifact, note, memory proposal, or retrieval result.

### Proactive Notes Need A Persistence-Value Threshold

Decision: Agent Col may proactively propose workspace notes, but only when persistence is likely to prevent meaningful rediscovery, contradiction, repeated investigation, or loss of an established workspace decision.

Reason: without a threshold, every productive engineering conversation becomes note-worthy and the Notes surface becomes noisy.

## Logging Work

A narrow diagnostic logging pass was completed before the current async work. The purpose was to make the chat pipeline observable from stdout.

The accepted logging shape records pipeline stages such as:

- `start`;
- `continuity_resolved`;
- `continuity_ambiguous`;
- `routing_finish`;
- `artifact_finish`;
- `responder_finish`;
- `turn_service_finish`;
- `turn_service_failure`.

The log rows include route, elapsed time, error class, and receipt counts for actions, artifacts, memory proposals, note proposals, continuity receipts, queued actions, and adaptations.

Why this mattered: before the logging pass, failures were ambiguous. Afterward, we could distinguish model/routing failures from database finalization failures.

The current `ChatTurnStateError` investigation depends on those logs. The logs showed that routing, artifact generation, responder generation, and turn service return all succeeded before chat finalization failed.

## Documentation And Evidence Work

Debug evidence was organized under `docs/debug-logging/`, including terminal logs and screenshots from manual testing. The purpose was to preserve evidence for behavioral regressions and prove that several earlier passes did not introduce visible failures.

The current document extends that evidence trail for async orchestration specifically.

## Agent Jobs And Public Projection

An AgentJob model/repository direction was accepted as the durable foundation for background work. The public projection is intentionally sanitized.

Public job objects should expose only safe fields such as:

- job/action type;
- public lifecycle status;
- display label;
- agent label;
- timestamps;
- public result or failure summaries.

They must not expose:

- raw prompts;
- raw model reasoning;
- private payloads;
- tool payloads;
- owner tokens;
- credentials;
- internal job IDs where not needed for public display.

Why: the Agents panel is a visibility surface for users, not a debugging dump of private orchestration internals.

## Agents Panel

A collapsible Agents panel was added under Chats in the left drawer. The target visual behavior was based on the supplied concept screenshot.

Accepted UI rules:

- the panel is collapsed by default on page load;
- it can expand and collapse like existing drawer cards;
- it shows Active Agents, Task Queue, and Completed Tasks for the current session;
- it is read-only;
- it renders backend-authoritative job state;
- it must not maintain a parallel frontend state machine;
- it must not reveal internal prompts, raw IDs, credentials, or tool payloads.

The panel currently reads from `/api/users/{user_id}/projects/{project_id}/agent/jobs` and from the dedicated agent job stream endpoint. Manual verification confirmed that short-lived jobs appear briefly as active and then move to completed/failed.

The "View all agents" label remains non-interactive by design for now. Building another detailed agent view was rejected as a distraction because the compact panel already provides the needed public projection for the current orchestration work.

## Agent Job Stream

A dedicated agent jobs stream was added so the Agents panel does not depend only on slow polling. The stream improves visibility for short-lived background jobs.

Current accepted limitation: very fast jobs may still only flash as active, because their real running duration is short. That is acceptable until longer-running subagent work exists.

Why this was added: a 3-second poll missed most short-lived jobs. A dedicated stream or fast refresh path gives better real-time visibility without polluting `/api/chat` or `/api/chat/stream`.

## Model Instruction Revisions

Agent Col's instructions were revised to support the new architecture.

Important instruction decisions:

- Col owns collaboration, discussion, challenge, and interpretation.
- Col should prefer application-authorized background/delegated paths for durable or multi-step work when available.
- Col must not leak internal orchestration details.
- Col should not claim durable completion without a receipt.
- Col should use provided relevant memory, notes, working state, and chat history without inventing unseen context.
- Col should not duplicate equivalent queued/running/completed/pending work.
- Col should not independently reproduce delegated work before a completed receipt exists.
- The older "default to no tool" rule was softened so it does not discourage legitimate delegated work.
- Evidence-specialist delegation limits were separated from durable-action job/subagent execution.

Why: the previous instructions still pushed Col to aggressively complete durable work itself. That was fighting the backend move toward queue-owned work.

## Note Proposal Queue Work

Workspace note proposal work was moved toward public AgentJob lifecycle reporting.

Observed behavior after the note pass:

- note proposals could create public AgentJob activity;
- completed note work appeared in the Agents panel;
- note proposals remained approval-gated in the Notes UI;
- chat did not crash during the accepted manual test;
- agent activity was often very brief, which is expected for current short-running work.

Why this pass mattered: it proved that the Agents panel can show governed proposal work without exposing private payloads, and that approvals remain owned by the application.

## Memory Proposal Queue Work

Memory proposal work was then moved from direct responder execution toward queued AgentJob execution.

Intended behavior:

- the responder queues memory proposal work;
- Memory Analyst appears in the Agents panel;
- the worker creates a pending memory proposal or records a sanitized failure;
- memory remains approval-gated;
- chat should not crash if memory proposal creation conflicts or fails.

Implemented pieces so far:

- `memory_proposal_tool.py` can queue memory proposal jobs through `AgentJobRepository`;
- `memory_proposal_job_worker.py` was added to execute queued memory proposal jobs;
- `agent_job_repository.py` gained filtered leasing by `action_kind`;
- `main.py` wires an in-process memory job dispatcher;
- `supervisor_runtime.py`, `agent_col_turn_service.py`, and response plumbing now carry `queued_actions`;
- focused tests were added for memory tool queueing, worker completion/failure, queue failure behavior, and logging/receipt propagation.

Focused verification before manual testing passed:

- memory proposal tool tests;
- memory proposal job worker tests;
- agent job repository tests;
- responder app catalog tests;
- supervisor runtime queued-action tests;
- targeted main tests;
- py_compile for changed Python files;
- `git diff --check`.

## Memory Conflict Failure

Manual testing found that if an unexpired pending memory proposal already occupied a category, the Memory Analyst job could fail with a conflict.

Earlier behavior: the conflict could crash the chat turn.

Implemented mitigation: conflict failures are now captured as sanitized AgentJob failures instead of propagating raw exceptions through the chat response path.

Remaining issue: the chat response can still describe memory proposal status based on queued intent instead of final job status, because chat and job completion are not yet fully decoupled.

## Current Failure: Chat Turn State Is Invalid

Manual testing then found a more serious failure:

```text
Chat turn state is invalid.
```

The terminal logs showed:

```text
Agent_Col turn pipeline stage=responder_finish route=artifact error=none artifacts=1 queued_actions=1
Agent_Col chat pipeline stage=turn_service_finish route=chat_stream error=none artifacts=1
ERROR:main:Chat turn completion failed (ChatTurnStateError).
```

This means routing, artifact generation, responder execution, and turn-service completion all returned successfully. The failure happened afterward, when `main.py` attempted to persist/complete the authoritative chat turn.

Verified source-backed cause:

- `memory_proposal_tool.py` reads the active chat turn lease from tool state.
- `memory_proposal_job_worker.py` serializes that turn lease, including the owner token, into the private job payload.
- the worker restores the same lease and calls `TrustedMemoryService.handle_natural_memory_decision`.
- `TrustedMemoryService` passes the lease into `create_guarded_memory_proposal_v2`.
- `create_guarded_memory_proposal_v2` writes memory proposal effects back onto the active chat turn when a lease is present.
- `complete_chat_turn` later validates that the final response exactly preserves already-stored effects.

Therefore, the current memory job is not truly independent background work. It still shares and mutates the live chat-turn state. That can race or conflict with final chat completion.

## Important Distinction

Queued memory proposal execution is not finished just because the work appears in the Agents panel.

There are two separate boundaries:

1. Public job lifecycle visibility: queued, running, completed, failed.
2. Chat-turn ownership and finalization: the active chat request's authoritative persistence lifecycle.

The memory job pass improved boundary 1, but it still violates boundary 2 by carrying the active turn lease into background execution.

## Current Corrective Direction

The next approved pass is to make queued memory proposal jobs queue-owned rather than chat-turn-owned.

Planned behavior:

- queued memory job payloads must not carry `turn_lease.owner_token`;
- queued memory jobs may keep trace-only source fields such as `source_turn_id` and `source_message_id`;
- the worker should execute memory proposal creation with `turn_lease=None`;
- `create_guarded_memory_proposal_v2(..., turn_lease=None)` should create the pending proposal without writing memory effects onto the active chat turn;
- the chat response should carry only a queued action receipt unless it has an actual completed proposal receipt;
- memory approval remains application-owned and user-gated;
- artifact and note orchestration remain unchanged in this corrective pass.

Why this is the right next step: it fixes the immediate correctness bug before addressing latency or full artifact/chat decoupling.

## Known Remaining Architecture Gaps

### Artifact Creation Is Still Request-Coupled

Artifact generation still happens inside the request path before the final response. That is why the chat response still waits for artifact completion.

This is accepted as unresolved for now. It should be handled after memory correctness is fixed.

### Chat Text Can Be Stale Relative To Job Completion

Because the responder may enqueue a job and then immediately generate chat text, the text can describe an intended or queued memory proposal while the job later fails due to conflict.

The authoritative source should be the job lifecycle and Memory UI. Later passes should make chat wording stricter: queued means queued, not completed.

### Latency Is Separate From Correctness

Latency rose again during recent hybrid orchestration passes. The likely reason is not the Agents panel alone. Logs show major time spent in continuity, artifact generation, and responder stages.

Latency should be optimized after the correctness boundaries are clean. Otherwise performance work risks hiding race conditions instead of removing them.

### Multiple Pending Memory Proposals Per Category

Current memory policy allows only one unexpired pending proposal per category. That can feel contradictory to broader orchestration goals, but it is a separate memory product decision.

Later direction: allow multiple pending proposals in the same category if the memory review UI and merge/conflict semantics are expanded. That should not be bundled into the current chat-turn state fix.

### Expanded Memory Categories

The current memory categories are too narrow for the long-term collaboration model. Expanding categories is desirable later, but it is explicitly out of scope for the queue-owned memory job correction.

## Manual Test Prompts Used

Artifact plus workspace note:

```text
Make an artifact and save a workspace note about the decision.
```

Artifact plus durable memory:

```text
Create a reusable shell script artifact for safely checking Git repository status on macOS, and remember that I prefer CLI workflows over GUI workflows.
```

Artifact plus durable memory with a different preference:

```text
Create a reusable shell script artifact for safely checking Python HTTP server status on macOS, and remember that I prefer C over Python.
```

Expected future behavior for the memory prompt:

- artifact creation should not be blocked by memory proposal conflict handling;
- Memory Analyst should appear in the Agents panel;
- memory proposal should appear in Memory UI if created;
- memory proposal should remain pending until user approval;
- if a category conflict exists, the job should fail safely in the Agents panel;
- chat must not show `Chat turn state is invalid`;
- chat must not claim memory was saved unless an approval-gated proposal or accepted memory receipt proves it.

## Current Status Before Next Fix

Current implementation status:

- Agents panel exists and is visually accepted for now.
- Agent job public projection exists.
- Agent job stream exists.
- Note proposal job visibility exists.
- Memory proposal worker exists.
- Memory job failures are sanitized.
- The memory job still incorrectly carries active chat-turn lease authority.
- Manual verification found `ChatTurnStateError`, so the current memory queue pass is not accepted and must not be checkpointed.

Next implementation target:

- remove active chat-turn ownership from queued memory proposal execution;
- keep source traceability;
- preserve approval-gated memory proposal behavior;
- prove with RED/GREEN tests that a completed queued memory job cannot invalidate chat turn completion.

## Queue-Owned Memory Proposal Fix

The corrective pass removed live chat-turn ownership from queued memory proposal execution.

Behavioral change:

- queued memory proposal jobs no longer serialize `turn_lease`;
- queued memory proposal jobs no longer serialize `owner_token`;
- the worker restores `NaturalMemoryCommand` with `turn_lease=None`;
- source traceability remains on the `AgentJobPayload` envelope through `source_turn_id` and `source_message_id`;
- profile-candidate memory proposals are queued;
- clarification requests remain on the direct governed path because the existing clarification flow still requires request-bound turn ownership;
- memory proposal conflicts remain sanitized AgentJob failures.

Why this fixes the observed failure:

Before this pass, the queued memory worker could write `actions` and `memory_proposals` onto the still-active chat turn. The final chat completion then compared the final response against effects already written to the turn and could reject the state with `ChatTurnStateError`.

After this pass, the queued memory worker creates the pending memory proposal without chat-turn lease ownership. The chat turn can complete with a queued-action receipt while the memory job lifecycle remains authoritative in the Agents panel and Memory UI.

TDD evidence:

- RED: `test_proposal_tool_records_memory_agent_job_queue_receipt` failed because the private job payload still contained `turn_lease`.
- RED: `test_proposal_tool_queues_memory_work_without_calling_service` failed because the private job payload still contained `turn_lease`.
- RED: `test_memory_worker_completes_queued_memory_proposal_from_private_payload` failed because the worker payload still contained `turn_lease`.
- RED: `test_proposal_tool_keeps_clarification_direct_when_job_repository_exists` failed because clarification work was being queued.
- GREEN: removed lease serialization/restoration from `memory_proposal_job_worker.py`.
- GREEN: narrowed `_should_record_memory_job` in `memory_proposal_tool.py` to profile-candidate proposals only.
- REFACTOR: updated stale failure-path assertions so conflict tests also verify `turn_lease=None`.

Focused automated verification:

```text
venv/bin/python -m pytest tests/test_memory_proposal_tool.py tests/test_memory_proposal_job_worker.py -q
30 passed in 0.37s
```

```text
venv/bin/python -m pytest tests/test_memory_proposal_tool.py tests/test_memory_proposal_job_worker.py tests/test_agent_job_repository.py tests/test_agent_col_responder.py::test_responder_app_catalog_exposes_only_governed_memory_tool tests/test_supervisor_runtime.py -k "memory or queued" tests/test_agent_col_turn_service.py -k "responder or memory or queued" tests/test_main.py -k "memory_proposal or agent_job or chat_turn" tests/test_logging_configuration.py -q
59 passed, 359 deselected, 1 warning in 1.23s
```

```text
venv/bin/python -m py_compile memory_proposal_tool.py memory_proposal_job_worker.py agent_job_repository.py agent_col_turn_service.py supervisor_runtime.py agent_col_responder.py main.py
passed
```

```text
git diff --check
passed
```

Remaining limitation:

This pass fixes the active chat-turn ownership bug for queued memory proposal jobs. It does not fully decouple artifact generation, note proposal generation, or responder wording from the chat request path.

## Manual Verification After Queue-Owned Memory Fix

Manual testing after the queue-owned memory fix showed real progress and one remaining correctness problem.

Prompt used:

```text
Create a reusable shell script artifact for safely checking Python HTTP server status on macOS, and remember that I prefer C over Python.
```

Observed behavior:

- the chat turn did not fail with `ChatTurnStateError`;
- the artifact was created and appeared in the artifact viewer;
- the Memory UI showed a pending proposal for the preference;
- the Agents panel showed an Artifact Builder completed job;
- the Agents panel also showed a Memory Analyst failed job, even though the pending memory proposal existed.

The second result is not acceptable as final behavior. It proves that removing the chat-turn lease fixed the direct chat-finalization crash, but the job lifecycle still does not have a trustworthy public report boundary. A user can currently see the durable resource in one surface and a contradictory terminal job status in another surface.

Likely failure classes to investigate before the next source-changing pass:

- a real category conflict happened, the Memory UI was showing an older pending proposal, and the job failure summary was too generic to make that clear;
- the memory service created a proposal successfully, but job completion or post-completion bookkeeping failed afterward, leaving a split-brain state where the resource exists and the job reports failure;
- the job projection exposes too little user-safe report detail to reconcile resource state and terminal job state.

The current logs prove the chat did not crash, but they do not prove which of the above classes caused the mismatch. The next implementation pass must add source-backed diagnostics and tests around the terminal job/report boundary instead of guessing.

## Public Job Identity Boundary

A security boundary decision was made before adding public job reports:

- public surfaces must not expose internal `job_id` values;
- public surfaces must not expose `session_id`;
- public surfaces must not expose `source_turn_id`;
- public surfaces must not expose `source_message_id`;
- public surfaces must not expose raw prompts, private payloads, tool payloads, owner tokens, credentials, or model reasoning;
- artifact labels, note titles, memory preference summaries, action kinds, lifecycle states, and public-safe timestamps are acceptable;
- the visible job number should be an ordinal display number only.

The accepted public display shape is a chronological three-digit number assigned from the current list order, such as:

```text
001
002
003
```

This number is not an identifier and must not be usable as a direct lookup key. It exists only to help users visually distinguish jobs in the panel and job reports. Backend internals may still use durable IDs, but the public API and UI should not expose them.

Why: users may have someone looking over their shoulder, may share a screenshot, or may run the app in a visible workspace. Public orchestration surfaces must not leak internal identifiers that are not already intentionally user-visible.

## Report Repository Direction

The accepted report direction is to separate public task reporting from chat text.

Target ownership split:

- Job owns lifecycle: queued, running, completed, failed, cancelled.
- Durable resource owns actual state: artifact, note proposal, memory proposal, accepted memory, and related approval state.
- Report owns public explanation: what happened, what the user can inspect, and whether the result is complete, pending approval, failed, or skipped.
- Chat owns conversation: reasoning with the user, asking and answering questions, challenging assumptions, and issuing work when appropriate.

This split means Agent Col does not need to narrate every task completion or approval result inside the same chat turn. The Agents panel can show task progress, and a job report surface can show user-safe result briefs when the user wants details.

The proposed report UI direction:

- completed and failed rows in the Agents panel can expand to show a short public report brief;
- the footer text should become `View all job reports` with the existing arrow acting as the control;
- activating the arrow opens a themed modal or pop-up listing current-session job reports;
- reports should be shown as compact list content, not nested cards;
- no internal IDs should appear in the modal or row expansion.

This report repository is also the right place to decouple proposal approval results from chat. Accepting or rejecting a memory or note proposal should remain an application-owned write. A later report can record a public-safe result without forcing Agent Col to narrate the approval in the active chat stream.

## Public Report Boundary Implementation Pass

The first public report boundary pass has now been implemented.

What changed:

- public agent job projections now expose `job_number` as a three-digit display ordinal instead of raw backend job IDs;
- public agent job event projections now expose `event_number` instead of raw event IDs or job IDs;
- public agent job reports now have their own stored model and repository path;
- public report API responses expose only report numbers, job display numbers, action kind, agent label, lifecycle status, title, summary, optional public resource label, and creation time;
- memory proposal background jobs now write terminal reports for completed and failed outcomes;
- memory proposal conflict failures now report the specific public-safe failure summary instead of a generic failed status;
- frontend API helpers now include a `listAgentJobReports` call for the public report surface.

The job display number is derived from chronological job creation order. This required one correction during the pass: the first implementation incorrectly derived `job_number` inside reports from report order. That would have made a report for a later-started job look like `001` if it completed first. A regression test now verifies that reports can be listed in completion order while their `job_number` still reflects job start order.

The stored report model still contains private backend IDs for ownership and joining. Those IDs are not exposed through the public projection. This keeps backend state durable and queryable while keeping the UI and public API safe for screenshots and shoulder-surfing.

TDD evidence recorded during the pass:

- RED: `tests/test_agent_job_reports.py` failed because `AgentJobReport` did not exist.
- RED: `tests/test_agent_job_repository.py -k report` failed because report repository methods did not exist.
- RED: `tests/test_memory_proposal_job_worker.py` failed because the worker did not create truthful terminal reports.
- RED: frontend API tests failed because `listAgentJobReports` did not exist.
- RED: `test_agent_job_reports_return_public_safe_projection` failed after adding the chronological job-number requirement because reports were numbered by report order.
- GREEN: report model, repository methods, public projection, report endpoint, memory worker reporting, and frontend API helper were implemented.

Focused verification after implementation:

```text
venv/bin/python -m pytest tests/test_agent_job_reports.py tests/test_agent_job_repository.py tests/test_memory_proposal_job_worker.py tests/test_main.py -k "report or agent_job or memory_proposal" -q
45 passed, 269 deselected, 1 warning
```

```text
node --test tests/frontend/api.test.mjs tests/frontend/agents-view.test.mjs tests/frontend/app-runtime.test.mjs
67 passed
```

```text
venv/bin/python -m py_compile agent_col_agent_jobs.py agent_job_repository.py memory_proposal_job_worker.py main.py
passed
```

```text
git diff --check
passed
```

Remaining limitations:

- this pass does not add the report modal or expandable completed-task report UI;
- this pass does not fully decouple artifact creation from the chat request path;
- this pass does not fully decouple note proposal creation from the chat request path;
- this pass does not remove backend route path parameters that still use private job IDs internally for detail, cancel, retry, or events;
- this pass does not change memory category rules or allow multiple pending memory proposals in the same category;
- this pass does not solve latency caused by request-bound artifact generation or responder waiting.

The next architectural target remains the same: move artifact creation behind the queued job/report boundary so the chat stream can acknowledge queued work quickly, the artifact can arrive through authoritative artifact state and job reports, and the artifact viewer can refresh from job/artifact completion state instead of waiting for Agent Col to narrate the result.

## Memory Chat-Bound Validation Failure

Manual verification after the report-boundary pass showed a more specific memory failure that came from partial decoupling.

Prompt class:

```text
Create a reusable shell script artifact for safely checking Python HTTP server status on macOS, and remember that I prefer assembly over C.
```

Observed behavior:

- the artifact path continued to run through the chat turn;
- the model attempted to create a memory proposal;
- the Memory Analyst job appeared in the Agents panel;
- in one run, a valid pending memory proposal appeared after changing the wording enough to avoid the conflict;
- in the failing run, the terminal log showed that ADK rejected the tool argument before the tool body could own the request:

```text
Failed to convert argument 'decision' ...
input_value='collaboration_preferences'
```

Root cause:

The live chat tool still annotated `decision` as the strict `ProviderNaturalMemoryDecision` union. That meant ADK performed provider-category validation in the chat request path before `propose_memory_signal` could enqueue a background job. The model produced a loose but understandable category, `collaboration_preferences`, for a user-requested memory. Because that category was not in the strict provider union, the failure happened at argument conversion time, outside the queue/report boundary.

Why this matters:

This is exactly the kind of failure the async architecture is supposed to prevent. If the background task layer is authoritative, the chat tool should record a public memory intent and return a queue receipt. The worker should then validate, normalize, create the proposal, or write a sanitized failure report. Letting ADK strict-validation reject the tool call in the live chat path keeps memory partially coupled to chat and creates the same fragility the background job system is meant to remove.

## Queue-Owned Memory Intent Pass

The follow-up memory pass changed the live memory tool boundary so profile-candidate memory requests are queued as raw public intent when an `AgentJobRepository` is available.

What changed:

- `propose_memory_signal` now accepts a raw decision object instead of the strict provider-union type;
- profile-candidate memory requests queue an AgentJob and private job payload before strict memory validation runs;
- the direct governed path remains available when no job repository exists;
- raw job payloads still omit chat-turn lease and owner-token values;
- the worker remains the place where memory decisions are converted into governed `NaturalMemoryCommand` values;
- `collaboration_preferences` is normalized to `user_requested_memory` before governed memory validation;
- clarification decisions remain direct for now because clarification response handling is still chat-bound and needs a separate design pass.

Why this is the right direction:

It moves the memory proposal creation boundary closer to the intended ownership split:

```text
Col chat tool
  -> queue memory intent
  -> return queued receipt

Memory Analyst worker
  -> validate / normalize
  -> call TrustedMemoryService
  -> create proposal or sanitized failure report
```

This does not make memory fully independent in every possible flow yet. It specifically removes the strict provider-category conversion from the live chat path for profile-candidate memory proposals, which was the failure seen in manual testing.

TDD evidence recorded during the pass:

- RED: `test_proposal_tool_queues_loose_profile_candidate_without_validation` failed because ADK rejected `collaboration_preferences` before the tool could queue it.
- RED: `test_memory_worker_normalizes_collaboration_preferences_candidate` failed because the worker rejected a queued payload containing `collaboration_preferences`.
- GREEN: the tool queues raw profile-candidate memory intent when a job repository is present.
- GREEN: the worker normalizes `collaboration_preferences` to `user_requested_memory` before invoking the governed memory service.
- REFACTOR: old strict schema tests were replaced with tests asserting the new chat-tool contract: expose only public `decision` and `clarification_selection`, and do not expose strict provider category enums in the live chat tool schema.

Focused verification after implementation:

```text
venv/bin/python -m pytest tests/test_memory_proposal_tool.py tests/test_memory_proposal_job_worker.py -q
32 passed
```

```text
venv/bin/python -m pytest tests/test_memory_proposal_tool.py tests/test_memory_proposal_job_worker.py tests/test_memory_candidate_decisions.py -q
38 passed
```

```text
venv/bin/python -m pytest tests/test_agent_job_reports.py tests/test_agent_job_repository.py tests/test_memory_proposal_job_worker.py tests/test_memory_proposal_tool.py tests/test_memory_candidate_decisions.py tests/test_main.py -k "report or agent_job or memory_proposal or collaboration_preferences" -q
75 passed, 275 deselected, 1 warning
```

```text
node --test tests/frontend/api.test.mjs tests/frontend/agents-view.test.mjs tests/frontend/app-runtime.test.mjs
67 passed
```

```text
venv/bin/python -m py_compile memory_candidate_decisions.py memory_proposal_tool.py memory_proposal_job_worker.py agent_col_agent_jobs.py agent_job_repository.py main.py
passed
```

Remaining limitations:

- artifact creation is still request-bound and can still drive latency;
- note proposal execution is not fully moved to the same raw-intent queue boundary;
- memory clarifications remain direct in the chat path;
- a conflict caused by one-pending-memory-proposal-per-category still produces a failed Memory Analyst report until later category/multiple-pending policy work is approved;
- responder wording can still mention artifacts or memory outcomes based on the chat path rather than relying solely on job reports;
- the report modal and expandable completed-task report UI are still not implemented.

## Chat Surface Memory Report Separation Pass

After the queue-owned memory intent pass, the remaining problem was not the worker's ability to create memory proposals. The remaining problem was ownership: Agent Col could still promote memory proposal completion into the chat response after a queue receipt existed, and partial-failure handling could still drop queued-action receipts.

Decision:

Once memory work is queued, chat should not also become the reporter for that background task's completed/pending result. Memory proposal completion, failure, conflict, and approval status belong to the Memory UI, Agents panel, and job reports. Agent Col may acknowledge that work was queued when the queue receipt exists, but background task outcomes should not depend on the active chat response.

Why:

If Col reports background task outcomes inside the same chat turn, the system keeps fighting the same coupling boundary. A fast task may appear as both queued and completed; a failed responder may hide queued work; a later worker report may contradict chat text; and the user cannot reliably keep chatting while background work is active. Job reports are the correct public-safe authority for task outcomes.

Implemented behavior:

- `supervisor_runtime.py` now ignores a later direct pending memory-proposal function response if a memory proposal job has already been queued in the same turn;
- queued memory work remains in `queued_actions`;
- queued memory work is not promoted into chat-owned `actions` or `memory_proposals`;
- `main.py` now treats queued actions as valid partial effects, so a responder failure after queueing can still return a partial-failure response with the queued-action receipt;
- the job report/resource surfaces remain responsible for completed or failed background outcomes.

TDD evidence recorded during the pass:

- RED: `test_run_turn_does_not_promote_pending_memory_after_queued_work` failed because the supervisor still appended a completed `propose_memory_signal` action and pending memory proposal after a queue receipt.
- RED: `test_chat_stream_preserves_queued_action_partial_failure_effects` failed because queued actions were ignored when deciding whether a safe partial-failure response existed.
- GREEN: queued memory work suppresses later chat-owned pending memory proposal effects in the same turn.
- GREEN: queued-action partial failures now survive through the stream error payload.

Focused verification after implementation:

```text
venv/bin/python -m pytest tests/test_supervisor_runtime.py::test_run_turn_does_not_promote_pending_memory_after_queued_work tests/test_main.py::test_chat_stream_preserves_queued_action_partial_failure_effects -q
2 passed, 1 warning
```

```text
venv/bin/python -m pytest tests/test_supervisor_runtime.py tests/test_main.py -k "queued or memory_proposal or partial_failure or agent_job" -q
18 passed, 308 deselected, 1 warning
```

```text
venv/bin/python -m pytest tests/test_memory_proposal_tool.py tests/test_memory_proposal_job_worker.py tests/test_memory_candidate_decisions.py -q
38 passed
```

```text
node --test tests/frontend/api.test.mjs tests/frontend/agents-view.test.mjs tests/frontend/app-runtime.test.mjs
67 passed
```

```text
venv/bin/python -m py_compile supervisor_runtime.py main.py memory_proposal_tool.py memory_proposal_job_worker.py memory_candidate_decisions.py
passed
```

Remaining limitations:

- artifact creation is still request-bound and should be the next major decoupling target;
- note proposal completion is still not fully separated through reports;
- memory clarification remains direct in chat;
- the report modal and expandable completed-task report UI still need to be built;
- artifact IDs can still leak in model-authored chat text because artifact context/responder wording has not yet been hardened in this pass.

## Queued Memory Report Boundary Hardening Pass

Manual verification of the previous pass showed the right architectural problem: the structured chat result no longer carried a memory proposal, but Agent Col's natural-language response still claimed that a pending memory proposal had been submitted. The Agents panel showed Memory Analyst as failed, while chat described a pending proposal. That contradiction proved the remaining bug was ownership and wording at the queue/report boundary, not the core memory write path.

Decision:

Queued memory work must be named and reported as a memory request until a background worker creates a real proposal or terminal failure report. Agent Col is allowed to acknowledge that memory work was queued, but it must not claim proposal creation, pending proposal status, saved memory, approval, rejection, conflict, or failure from the live chat path. Those outcomes belong to Memory UI and job reports.

Why:

This is the same boundary we are trying to make reliable across memory, notes, and artifacts. If chat can translate a queued job into a completed or pending outcome, the user gets contradictory state and manual testing remains muddy. The public report/resource surfaces need to be authoritative for terminal background outcomes. Chat should keep flowing and should not be responsible for proving or narrating background completion.

Implemented behavior:

- queued memory job labels now say `Memory request: <category>` instead of `Memory proposal: <category>`;
- queued memory job events now say `Memory request queued.`;
- Agent Col's responder instruction now explicitly states that queued memory work is not a completed memory proposal receipt;
- Agent Col is instructed not to describe queued memory work as a pending proposal, created proposal, submitted proposal, saved preference, stored preference, remembered preference, approved memory, or failed memory outcome;
- `supervisor_runtime.py` now sanitizes canonical final response text when queued memory work exists and no completed memory proposal exists, replacing unauthorized memory completion claims with report-bound queued wording while preserving unrelated response text.

TDD evidence recorded during the pass:

- RED: `test_proposal_tool_records_memory_agent_job_queue_receipt` and `test_proposal_tool_queues_memory_work_without_calling_service` failed because queued memory jobs still used `Memory proposal: response_length`.
- RED: `test_run_turn_rewrites_queued_memory_completion_claims` failed because the supervisor returned model-authored text claiming a pending proposal after only a queued memory receipt existed.
- RED: `test_responder_instruction_does_not_report_queued_memory_as_pending` failed because the responder instruction did not contain the explicit queued-memory/report ownership rule.
- GREEN: queued memory work is labeled as a request, final response text is guarded against false pending-proposal claims, and the responder instruction records the intended ownership boundary.

Focused verification after implementation:

```text
venv/bin/python -m pytest tests/test_memory_proposal_tool.py::test_proposal_tool_records_memory_agent_job_queue_receipt tests/test_memory_proposal_tool.py::test_proposal_tool_queues_memory_work_without_calling_service -q
2 passed
```

```text
venv/bin/python -m pytest tests/test_supervisor_runtime.py::test_run_turn_rewrites_queued_memory_completion_claims tests/test_supervisor_runtime.py::test_run_turn_does_not_promote_pending_memory_after_queued_work tests/test_supervisor_runtime.py::test_run_turn_collects_queued_memory_receipt_from_function_response -q
3 passed, 1 warning
```

```text
venv/bin/python -m pytest tests/test_agent_col_responder.py::test_responder_instruction_does_not_report_queued_memory_as_pending tests/test_agent_col_responder.py::test_responder_instruction_prevents_duplicate_or_competing_job_outputs -q
2 passed, 1 warning
```

```text
venv/bin/python -m pytest tests/test_memory_proposal_tool.py tests/test_memory_proposal_job_worker.py tests/test_memory_candidate_decisions.py tests/test_supervisor_runtime.py tests/test_agent_col_responder.py -k "memory or queued or report or instruction" -q
65 passed, 41 deselected, 1 warning
```

```text
venv/bin/python -m pytest tests/test_agent_job_repository.py tests/test_main.py -k "queued or memory_proposal or partial_failure or agent_job" -q
35 passed, 270 deselected, 1 warning
```

Remaining limitations:

- this pass hardens memory/report ownership but does not fully decouple artifacts or notes yet;
- streaming partial deltas can still briefly show model-authored text before canonical final response sanitization if the model streams unsafe wording before the final event;
- the report modal and completed-task report inspection UI remain unimplemented;
- artifact creation is still request-bound and remains the main latency/coupling target;
- memory policy still allows only one pending proposal per category until a later product-policy pass expands that behavior.

## Agent Report Inspection Surface Pass

After the report repository/API work, the next missing piece was user inspection. The Agents panel had completed/failed job rows but no report viewer, so job reports were authoritative in backend shape only. The user clarified the intended UI boundary: the existing small arrow in the Agents panel footer should become the clickable affordance, without a visual restyle, and should open a popup overlay rather than another card. The popup itself needs an `x` close button in its top-right corner.

Decision:

The Agents panel owns job report inspection. Agent Col chat should not be the report-delivery mechanism for background task completion, failure, approval, or conflict outcomes. The chat surface may keep conversational context and issue work, but reports must be inspectable from the background-work surface with public-safe display fields only.

Why:

This keeps the ownership split concrete for future artifact and note decoupling. If the only way to learn whether a background task completed is through a model-authored chat response, then chat remains coupled to task completion timing and error handling. A report popup gives users a separate, explicit place to inspect completed/failed work while chat stays available.

Implemented behavior:

- the Agents footer text now says `View all job reports`;
- the existing arrow remains the arrow affordance, but is now a button with no visual button chrome;
- clicking the arrow opens a popup overlay with `role="dialog"` and `aria-modal="true"`;
- the popup has an `x` close button in the top-right of the overlay itself;
- frontend state now tracks report loading status, report data, report errors, and popup visibility independently from job list state;
- opening the popup loads reports through `/agent/reports`;
- report rendering uses public display fields such as report number, job number, agent label, status, title, summary, public resource label, and timestamp;
- internal IDs and backend routing fields are not rendered even if present in the report object.

TDD evidence recorded during the pass:

- RED: `agent report state loads public reports without replacing jobs` failed because report state functions did not exist.
- RED: `renderAgentsPanel opens job reports from the existing footer arrow` failed because the footer still rendered static `View all agents` text and a non-clickable arrow.
- RED: `renderAgentsPanel shows report popup as a compact public-safe list` failed because no popup existed.
- RED: `agent report popup loads reports from the background report surface` failed because `app.mjs` did not wire the arrow callback or report endpoint fetch.
- GREEN: state, renderer, CSS, and app wiring now load and display public-safe reports from the report surface.

Focused verification after implementation:

```text
node --test tests/frontend/state.test.mjs tests/frontend/agents-view.test.mjs
65 passed
```

```text
node --test tests/frontend/app-runtime.test.mjs --test-name-pattern "agent report popup loads reports from the background report surface"
31 passed
```

Remaining limitations:

- this is report inspection only; artifact generation is still request-bound and remains the next major decoupling target;
- note proposal execution/reporting still needs the same separation;
- the popup is backed by `/agent/reports`, but completed-job row inline expansion is not implemented in this pass;
- manual visual verification is still pending by design.

## Direct Memory Approval Surface Pass

After the report popup pass, manual screenshots still showed memory approval
results appearing as ordinary Agent Col chat responses. That behavior violated
the ownership split we had established: Agent Col may queue work and converse,
but background/task resource outcomes should be owned by their own surfaces.
For memory, approve/reject is not model work. It is a direct user decision that
should write through the memory API and refresh the Memory UI without asking
Agent Col to narrate the result.

Decision:

Memory proposal approve/reject now belongs to the Memory UI and direct memory
API. It must not depend on chat submit readiness, must not call `/api/chat` or
`/api/chat/stream`, and must be usable while an ordinary chat turn is pending.
Agent reports remain the authoritative inspection surface for background job
completion/failure, while the Memory UI remains authoritative for user-managed
memory state.

Why:

The earlier partial decoupling still let user approval actions collide with the
chat turn lifecycle. That is the same failure family as the `ChatTurnStateError`
and timeout/partial-effect confusion observed during manual runs: a task outcome
or approval action had to flow back through the active conversation path. Moving
memory approve/reject to direct resource endpoints creates a separate error
boundary. If the memory decision fails, the Memory UI owns the error. If chat is
pending, the decision can still be accepted. If background jobs are reporting,
the report surface can update independently from the chat transcript.

Implemented behavior:

- added `POST /api/users/{user_id}/memory/proposals/{proposal_id}/{decision}`;
- the endpoint accepts only `approve` or `reject`;
- the endpoint calls `TrustedMemoryService.decide_memory_proposal` with
  `confirmation_channel="memory_api"` and no chat session/message confirmation
  identifiers;
- the endpoint returns the same public `MemoryMutationResponse` shape used by
  other direct memory mutation routes;
- the frontend API now exposes `decideMemoryProposal`;
- `submitMemoryDecision` in `frontend/app.mjs` no longer checks
  `selectCanSubmit(state)`;
- Memory UI proposal approve/reject calls the direct memory endpoint, refreshes
  Memory UI state, and refreshes agent job/report surfaces;
- approve/reject no longer creates an Agent Col chat turn or waits for the
  active chat request to finish.

TDD evidence recorded during the pass:

- RED: `test_approve_memory_proposal_uses_memory_api_without_chat_turn` and
  `test_reject_memory_proposal_uses_memory_api_without_chat_turn` failed with
  404 because no direct proposal decision route existed.
- GREEN: the direct route was added and both backend tests passed, asserting the
  memory service command uses `memory_api`, records no chat confirmation IDs,
  emits the memory decision event, and never calls the turn service.
- RED: `decideMemoryProposal calls the direct proposal decision path` failed
  because `frontend/api.mjs` exported no direct proposal decision wrapper.
- GREEN: `decideMemoryProposal` was added and validates user/proposal locators
  plus the bounded decision value.
- RED: `memory proposal approval during a pending chat uses direct memory API`
  failed because the existing Memory UI handler returned early while chat was
  pending and therefore never called the memory endpoint.
- GREEN: the handler now calls the direct memory endpoint while chat is pending,
  refreshes resource state, and does not issue any additional chat request.

Focused verification after implementation:

```text
venv/bin/python -m pytest tests/test_main.py::test_approve_memory_proposal_uses_memory_api_without_chat_turn tests/test_main.py::test_reject_memory_proposal_uses_memory_api_without_chat_turn -q
2 passed, 1 warning
```

```text
node --test tests/frontend/api.test.mjs --test-name-pattern "decideMemoryProposal"
35 passed
```

```text
node --test tests/frontend/app-runtime.test.mjs --test-name-pattern "memory proposal approval during a pending chat uses direct memory API"
31 passed
```

```text
venv/bin/python -m pytest tests/test_main.py -k "memory_signal or memory_proposal" -q
6 passed, 282 deselected, 1 warning
```

```text
node --test tests/frontend/api.test.mjs tests/frontend/app-runtime.test.mjs tests/frontend/memory-view.test.mjs tests/frontend/requests.test.mjs
98 passed
```

One attempted backend verification command failed because the `pytest -k`
expression contained an unquoted bare word sequence. The command was corrected
and rerun successfully as shown above.

Remaining limitations:

- memory proposal creation is already queued to background work, but artifact
  creation remains request-bound and is still the major latency/coupling target;
- workspace note proposal approve/reject and note proposal creation still need
  the same direct resource/job ownership treatment;
- legacy chat request builders for memory decisions still exist for older
  request/recovery tests, but normal Memory UI approve/reject no longer uses
  them;
- manual visual verification is intentionally deferred until more background
  work surfaces are decoupled, per the current testing strategy.

## Artifact Creation Queue Ownership

The artifact creation pass moved request-bound artifact generation behind the
existing AgentJob/report boundary.

Behavioral change:

- artifact routing still happens in the chat request path;
- artifact work is now enqueued with an `AgentJobPayload` instead of generated
  before the responder runs;
- the chat turn receives a queued `create_artifact` action and no completed
  artifact/action receipt;
- the responder receives a bounded queued-artifact context and must not claim
  the artifact is already created;
- the artifact worker leases only `create_artifact` jobs;
- the worker restores the private payload, generates the artifact, persists it
  through the existing artifact services, completes/fails the job, and writes a
  public-safe report;
- queued artifact payloads do not serialize `owner_token` or `turn_lease`;
- the production lifespan now owns an in-process artifact job worker and task
  set, mirroring the memory worker shape.

Why this matters:

Before this pass, an artifact route wrote job lifecycle rows but still generated
and persisted the artifact synchronously inside the chat request before the
responder could complete. The job was therefore instrumentation, not ownership.
After this pass, chat delegates artifact execution and returns with queued work;
the artifact surface, Agents panel, and reports become the authoritative places
to observe completion.

TDD evidence recorded during the pass:

- RED: `test_artifact_executor_queues_single_file_work_without_generation`
  failed because `AgentColArtifactExecutor` had no `queue` API.
- RED: `test_artifact_worker_creates_single_file_artifact_from_private_payload`
  failed because `AgentColArtifactCreationJobWorker` did not exist.
- RED: `test_turn_service_queues_artifact_before_responder_without_generation`
  failed because the turn service still called synchronous `execute`.
- RED: dispatcher coverage failed because the executor constructor did not
  accept an artifact job dispatcher.
- RED: after backing out premature blueprint worker code,
  `test_artifact_worker_creates_blueprint_artifact_from_private_payload` failed
  because blueprint jobs finished as failed instead of completed.
- GREEN: queue payload creation, worker leasing/execution/reporting,
  prequeued responder context, main lifespan worker wiring, and blueprint
  persistence were implemented.

Focused verification after implementation:

```text
venv/bin/python -m pytest tests/test_agent_col_artifact_executor.py tests/test_agent_col_turn_service_artifacts.py tests/test_agent_col_turn_service.py -k "artifact or queued" -q
34 passed, 45 deselected, 1 warning
```

```text
venv/bin/python -m pytest tests/test_agent_job_reports.py tests/test_agent_job_repository.py -k "report or agent_job" -q
27 passed
```

```text
venv/bin/python -m pytest tests/test_main.py -k "agent_report or agent_job or artifact" -q
51 passed, 237 deselected, 1 warning
```

Remaining limitations:

- artifact routing still runs in the chat request path so Agent Col can decide
  whether artifact creation is appropriate;
- chat still contains a queued action receipt with the internal job id because
  the existing `QueuedActionReceipt` contract still carries it; public job and
  report list surfaces remain sanitized;
- artifact viewer refresh after job completion depends on existing frontend
  refresh paths and requires manual verification;
- workspace note proposal creation and approval are still later decoupling
  passes.

## Chat And Background Surface Decoupling

The next pass extended the artifact queue ownership work into the surrounding
chat/background independence boundary.

Behavioral change:

- workspace note approval/rejection now has a direct notes API endpoint at
  `/api/users/{user_id}/projects/{project_id}/notes/proposals/{proposal_id}/{decision}`;
- that endpoint calls `CollaborativeNoteService.decide_proposal` directly and
  does not claim, renew, complete, or release a chat turn;
- the frontend Notes drawer uses the direct notes API for proposal
  approval/rejection instead of building a chat request;
- direct note proposal creation, note corrections, note lifecycle mutations,
  artifact archive/restore/delete, artifact metadata edits, artifact version
  creation, and artifact lifecycle filtering no longer check chat submit
  readiness or `pendingTurn`;
- note-list responses can hydrate `pending_proposals` into the Notes drawer so
  the drawer is not dependent on chat receipts for proposal visibility;
- artifact creation still queues through `AgentJob`, but the responder no
  longer receives model-visible queued-artifact prompt context. The queued
  receipt remains structured runtime state and background jobs/reports remain
  authoritative for progress, completion, and failure.

Why this matters:

The previous artifact pass moved generation and persistence behind the job
worker, but unrelated UI actions could still be blocked by the active chat
turn, and note approvals still routed through `/api/chat`. This pass removes
those coupling points. A running chat stream no longer prevents note proposal
approval, memory proposal approval, artifact lifecycle actions, or Agents panel
refreshes in the covered automated runtime scenarios.

TDD evidence recorded during the pass:

- RED: `test_direct_collaborative_note_decision_does_not_use_chat_turn` failed
  with `404` because no direct note decision route existed.
- RED: `note API wrappers use canonical user workspace note paths` failed at
  import because `decideNoteProposal` did not exist.
- RED: `note proposal approval during a pending chat uses direct note API`
  failed because note decisions still used chat submit readiness/chat request
  routing.
- RED: `artifact lifecycle actions during a pending chat use direct work API`
  failed until direct work actions were no longer gated by active chat state and
  the test fixture reflected the full work-list load path.
- RED: artifact turn-service tests failed because queued-artifact text context
  was still passed into the responder.
- GREEN: direct backend/frontend note decisions, pending proposal hydration,
  frontend busy-state separation for note/work surfaces, and artifact responder
  context removal were implemented.

Focused verification after implementation:

```text
node --test tests/frontend/api.test.mjs tests/frontend/state.test.mjs tests/frontend/app-runtime.test.mjs
3 files passed
```

```text
venv/bin/python -m pytest tests/test_main.py -k "collaborative_note" -q
17 passed, 272 deselected, 1 warning
```

```text
venv/bin/python -m pytest tests/test_agent_col_turn_service_artifacts.py -k "artifact" -q
10 passed, 1 warning
```

```text
venv/bin/python -m pytest tests/test_agent_col_artifact_executor.py tests/test_agent_job_repository.py tests/test_agent_job_reports.py -k "artifact or agent_job or report" -q
49 passed, 1 warning
```

Remaining limitations:

- chat routing still decides whether to enqueue artifact creation; execution,
  persistence, job lifecycle, and reports are worker-owned;
- public chat responses still carry queued action receipts using the existing
  internal `QueuedActionReceipt.job_id` contract; public job/report list
  surfaces remain sanitized;
- direct artifact feedback still routes through the chat request builder and
  should be moved to a direct artifact-feedback API in a follow-up pass;
- manual end-to-end verification remains deferred until the remaining
  direct-feedback and any uncovered drawer actions are decoupled.

## Direct Memory Clarification Selection Pass

This pass finished the half-completed memory clarification selection
decoupling checkpoint from `e6c57f7`.

Completed work:

- added a direct Memory-owned clarification selection endpoint at
  `/api/users/{user_id}/projects/{project_id}/memory/clarifications/{clarification_id}/select`;
- the direct endpoint validates the idempotency key, derives a deterministic
  direct selection source message id from that key, verifies authenticated user
  scope, and calls `TrustedMemoryService.select_memory_clarification`;
- `SelectMemoryClarificationCommand` and
  `MemoryEngine.consume_memory_clarification_to_proposal_v2` now allow
  `turn_lease=None` for direct Memory API selection;
- direct Memory API selection skips chat-turn effect writes and does not claim,
  renew, complete, or release a live chat turn;
- existing chat-owned clarification selection can still pass a
  `ProposalTurnLease` and keep the previous retry-safe chat-turn effect path;
- direct selection preserves session ownership, workspace ownership, active
  clarification id binding, expiry validation, candidate validation, origin
  idempotency, pending-proposal conflict checks, and no-save consumption;
- the frontend has a `selectMemoryClarification` API wrapper for the direct
  endpoint with idempotency and bounded input validation;
- the chat surface no longer routes memory clarification selection through
  `/api/chat`;
- active memory clarification choices remain selectable while an ordinary chat
  stream is pending, call the direct Memory endpoint, clear the consumed
  clarification from the UI, and refresh the Memory panel.

Why this matters:

Before this pass, choosing a memory clarification candidate was modeled as
another chat turn. That meant the selection depended on chat submit readiness,
chat-turn ownership, and a live chat-turn lease even though the selected
clarification is already a server-owned Memory lifecycle object. After this
pass, the user action goes to Memory directly. Chat can still ask the question,
but Memory owns the selection lifecycle and proposal creation.

TDD evidence recorded during the pass:

- RED: `test_memory_api_clarification_selection_does_not_require_turn_lease`
  failed because the service rejected selection without `ProposalTurnLease`.
- RED: direct route tests in `tests/test_main.py` failed because the direct
  Memory clarification selection endpoint did not exist and no direct response
  model was available.
- RED: `selectMemoryClarification calls the direct clarification selection
  path` failed at import because the frontend API wrapper did not exist.
- RED: `chat endpoint selection streams only ordinary requests` failed because
  `memory_clarification_selection` still forced `/api/chat`.
- RED: `memory clarification selection during a pending chat uses direct
  memory API` failed because the runtime path still depended on chat submit
  readiness and chat request routing.
- GREEN: direct backend route/schema/service/database mode, frontend API
  wrapper, frontend request routing, and pending-chat runtime selection behavior
  were implemented.

Focused verification after implementation:

```text
venv/bin/pytest -q tests/test_memory_proposal_service.py tests/test_main.py
317 passed, 1 warning
```

```text
node --test tests/frontend/api.test.mjs tests/frontend/requests.test.mjs tests/frontend/app-runtime.test.mjs tests/frontend/chat-view.test.mjs tests/frontend/state.test.mjs
180 passed
```

```text
git diff --check
no output
```

Remaining direct decoupling:

- direct artifact feedback still needs to move off `/api/chat` onto an
  Artifact-owned feedback lifecycle endpoint;
- continuity selection still routes through `/api/chat` and remains dependent
  on chat submit readiness;
- any remaining chat-response structured decision paths should be audited after
  artifact feedback and continuity selection are decoupled.

Next proposed pass:

- move artifact feedback acceptance/rejection/edit selection out of `/api/chat`
  and onto a direct artifact feedback API that records the decision without
  claiming or leasing a chat turn.

Work deferred until core decoupling is complete:

- broad manual end-to-end browser acceptance for every drawer action;
- UI polish that does not change ownership boundaries;
- public receipt contract cleanup such as removing internal job ids from chat
  queued action receipts;
- larger worker/runtime architecture changes unrelated to direct lifecycle
  ownership.

## Direct Artifact Feedback Enforcement Pass

This pass finished the direct artifact feedback boundary. The direct feedback
recording endpoint already existed, and the frontend work surface already used
it. The remaining defect was that `/api/chat` still accepted
`artifact_feedback_decision`, claimed a chat turn, and could execute feedback
through the chat turn service.

Completed work:

- `/api/chat` now rejects `artifact_feedback_decision` immediately with a safe
  conflict response telling callers to use the direct artifact feedback API;
- the rejection happens before idempotency-specific artifact feedback handling,
  chat-turn claim, turn service dispatch, chat-turn completion, or release;
- the direct endpoint at
  `/api/projects/{project_id}/blueprints/{blueprint_id}/feedback` remains the
  Artifact-owned lifecycle API for acceptance, rejection, and edited feedback;
- direct endpoint safe-error mapping now also covers feedback ledger
  conflict/state exceptions, not only feedback service exceptions;
- stale backend tests for chat-owned feedback execution/error handling were
  converted to the direct route or removed when they only proved the retired
  responder path;
- a stale static frontend assertion from the prior memory clarification pass
  was corrected so the static suite reflects the current direct Memory API
  wiring.

Why this matters:

Before this pass, normal UI feedback already used the direct artifact API, but
`/api/chat` still carried a second, chat-turn-owned execution path. That meant
artifact feedback had two authorities: the direct Artifact lifecycle route and
the chat turn claim path. After this pass, chat is no longer an artifact
feedback execution surface.

TDD evidence recorded during the pass:

- RED: `test_chat_rejects_artifact_feedback_without_claiming_turn` failed
  because `/api/chat` still reached `claim_chat_turn` and returned the old
  execution behavior.
- RED: `test_chat_rejects_artifact_feedback_even_without_idempotency_key`
  failed because the old artifact-feedback idempotency check still fired before
  direct-route enforcement.
- GREEN: `_execute_chat` now rejects artifact feedback decisions before any
  chat-owned lifecycle work.
- Follow-up focused feedback tests exposed stale old-chat safe-error coverage;
  those tests were moved to the direct endpoint, and missing direct ledger
  error mappings were added.

Focused verification after implementation:

```text
venv/bin/pytest -q tests/test_main.py -k "feedback"
11 passed, 284 deselected, 1 warning
```

```text
node --test tests/frontend/workspace-static.test.mjs
22 passed
```

Remaining direct decoupling:

- continuity selection still routes through `/api/chat` and depends on chat
  submit readiness;
- legacy schema/request-builder compatibility still allows parsing
  `artifact_feedback_decision`, but `/api/chat` no longer executes it;
- the internal artifact feedback executor remains covered by its unit tests but
  is no longer the public chat route for feedback.

Next proposed pass:

- move continuity selection out of `/api/chat` and onto a direct
  continuity-owned selection endpoint that records the selected server-owned
  source without claiming or leasing a chat turn.

Work deferred until core decoupling is complete:

- remove legacy frontend request helpers and schema fields for retired chat
  structured decisions after all direct lifecycle routes are in place;
- broad manual end-to-end browser acceptance for every drawer action;
- public receipt contract cleanup such as removing internal job ids from chat
  queued action receipts;
- larger worker/runtime architecture changes unrelated to direct lifecycle
  ownership.

## Direct Continuity Selection Pass

This pass moved explicit continuity choice selection off `/api/chat`. Chat still
discovers ambiguous continuity and returns bounded server-owned choices, but the
user's selected choice is now resolved and recorded through a direct continuity
lifecycle endpoint.

Completed work:

- added
  `/api/users/{user_id}/projects/{project_id}/continuity/choices/{choice_id}/select`
  as the direct continuity selection API;
- `/api/chat` now rejects `continuity_selection` immediately with a safe
  conflict response telling callers to use the direct continuity API;
- the rejection happens before chat-turn claim, turn service dispatch,
  chat-turn completion, or release;
- direct continuity selections resolve the server-owned choice through
  `ContinuityService.resolve(selection=...)`;
- selected continuity receipts are persisted under the owned session in the
  `continuity_selections` subcollection rather than relying on a completed chat
  turn;
- recent continuity-anchor reads now include direct selections before completed
  chat-turn receipts;
- the frontend selects continuity choices with the direct API and keeps choice
  buttons usable while an ordinary chat stream is pending;
- static frontend coverage now rejects reintroducing the old app import of
  `buildContinuitySelectionChatRequest`.

Why this matters:

Before this pass, continuity selection was still a chat turn. A user could only
select an ambiguous source by submitting another `/api/chat` request, which
claimed a live chat turn and recorded the selected continuity receipt only as
part of that completed turn. After this pass, the Continuity lifecycle owns
explicit selection and persistence.

TDD evidence recorded during the pass:

- RED: `test_chat_rejects_continuity_selection_without_claiming_turn` failed
  because `/api/chat` still reached `claim_chat_turn` and returned the old
  chat-owned behavior.
- RED: `test_select_continuity_choice_uses_direct_api_without_chat_turn` and
  `test_select_continuity_choice_maps_unresolved_selection_to_conflict` failed
  because the direct continuity endpoint did not exist.
- RED: `test_record_continuity_selection_writes_direct_session_receipt` failed
  because `MemoryEngine.record_continuity_selection` did not exist.
- RED: `test_list_recent_session_continuity_receipts_includes_direct_selections`
  failed because recent anchors only came from completed chat turns.
- RED: frontend API/request/view/runtime tests failed because there was no
  `selectContinuityChoice` export, endpoint routing still selected `/api/chat`,
  continuity choice buttons were disabled during pending chat, and the app still
  used the chat request builder.
- GREEN: direct route, schema, database persistence/readback, API wrapper,
  request routing, chat-view enablement, and app direct selection wiring were
  implemented.

Focused verification after implementation:

```text
venv/bin/pytest -q tests/test_main.py tests/test_chat_turn_database.py tests/test_continuity_service.py
455 passed, 1 warning
```

```text
node --test tests/frontend/api.test.mjs tests/frontend/requests.test.mjs tests/frontend/chat-view.test.mjs tests/frontend/app-runtime.test.mjs tests/frontend/workspace-static.test.mjs
144 passed
```

```text
git diff --check
no output
```

Remaining direct decoupling:

- `/api/chat` still accepts and executes `memory_decision`;
- `/api/chat` still accepts and executes `collaborative_note_decision`;
- legacy schema/request-builder compatibility still allows parsing retired
  structured chat decisions, even when the app now uses direct APIs for those
  user actions.

Next proposed pass:

- reject `memory_decision` in `/api/chat` and make the direct Memory proposal
  approve/reject API the only execution path for memory proposal decisions.

Work deferred until core decoupling is complete:

- remove legacy frontend request helpers and schema fields for retired chat
  structured decisions after all direct lifecycle routes are in place;
- broad manual end-to-end browser acceptance for every drawer action;
- public receipt contract cleanup such as removing internal job ids from chat
  queued action receipts;
- larger worker/runtime architecture changes unrelated to direct lifecycle
  ownership.

## Direct Memory Decision Enforcement Pass

This pass made the direct Memory proposal approve/reject API the only public
execution path for explicit memory proposal decisions. The existing direct route
at `/api/users/{user_id}/memory/proposals/{proposal_id}/{decision}` already
owned the Memory lifecycle; the remaining defect was that `/api/chat` still
accepted `memory_decision`, saved a chat message, called the Memory service with
chat confirmation metadata, and could continue through the chat turn service.

Completed work:

- `/api/chat` now rejects `memory_decision` immediately with a safe conflict
  response telling callers to use the direct Memory API;
- `/api/chat/stream` returns the same direct-Memory enforcement response for
  `memory_decision` instead of redirecting callers to `/api/chat`;
- the rejection happens before chat-turn claim, history reads, message saves,
  Memory service mutation, turn service dispatch, chat-turn completion, or
  release;
- frontend chat endpoint selection no longer treats `memory_decision` as a
  reason to use `/api/chat`;
- stale backend tests that proved chat-owned memory decision execution were
  replaced with direct-route coverage or removed when they only described the
  retired chat confirmation lifecycle.

Why this matters:

Before this pass, memory proposal approval had two authorities: the direct
Memory API and a chat-turn-owned structured decision path. That second path
created unnecessary dependency on chat-turn claiming and chat message identity.
After this pass, explicit memory proposal approval/rejection is Memory-owned.

TDD evidence recorded during the pass:

- RED: `test_chat_rejects_memory_decision_without_claiming_turn` failed because
  `/api/chat` still reached `claim_chat_turn` instead of rejecting before chat
  lifecycle work.
- RED: `test_chat_stream_rejects_memory_decision_without_claiming_turn` failed
  because `/api/chat/stream` still returned the old structured-decision
  `/api/chat` redirect response.
- RED: `chat endpoint selection streams only ordinary requests` failed because
  the frontend request selector still routed `memory_decision` to `/api/chat`.
- GREEN: `_execute_chat` now rejects `memory_decision` before the generic
  structured-decision stream check, and `selectChatEndpoint` no longer includes
  `memory_decision` in its JSON-chat selector list.
- Follow-up focused backend verification exposed stale chat-owned tests; those
  were narrowed to direct-route error mapping or ordinary replay behavior, and
  the retired deterministic chat confirmation-message-id test was removed.

Focused verification after implementation:

```text
venv/bin/pytest -q tests/test_main.py
295 passed, 1 warning
```

```text
node --test tests/frontend/api.test.mjs tests/frontend/requests.test.mjs tests/frontend/app-runtime.test.mjs tests/frontend/workspace-static.test.mjs
123 passed
```

```text
git diff --check
no output
```

Remaining direct decoupling:

- `/api/chat` still accepts and executes `collaborative_note_decision`;
- legacy schema/request-builder compatibility still allows parsing retired
  structured chat decisions, even when the app now uses direct APIs for those
  user actions;
- unreachable legacy memory-decision code remains inside `_execute_chat` until
  the final structured-decision cleanup pass.

Next proposed pass:

- reject `collaborative_note_decision` in `/api/chat` and make the direct
  collaborative note proposal approve/reject API the only execution path for
  note proposal decisions.

Work deferred until core decoupling is complete:

- remove legacy frontend request helpers and schema fields for retired chat
  structured decisions after all direct lifecycle routes are in place;
- delete unreachable backend structured-decision branches after the final direct
  lifecycle owner is enforced;
- broad manual end-to-end browser acceptance for every drawer action;
- public receipt contract cleanup such as removing internal job ids from chat
  queued action receipts;
- larger worker/runtime architecture changes unrelated to direct lifecycle
  ownership.

## Direct Collaborative Note Decision Enforcement Pass

This pass made the direct collaborative note proposal approve/reject API the
only public execution path for explicit note proposal decisions. The existing
direct route at
`/api/users/{user_id}/projects/{project_id}/notes/proposals/{proposal_id}/{decision}`
already owned the Notes lifecycle; the remaining defect was that `/api/chat`
still accepted `collaborative_note_decision`, claimed a chat turn, recorded a
chat-turn decision effect, and could continue through the turn service.

Completed work:

- `/api/chat` now rejects `collaborative_note_decision` immediately with a safe
  conflict response telling callers to use the direct notes API;
- `/api/chat/stream` returns the same direct-notes enforcement response for
  `collaborative_note_decision` instead of redirecting callers to `/api/chat`;
- the rejection happens before chat-turn claim, Note service mutation,
  chat-turn decision-effect writes, turn service dispatch, chat-turn
  completion, or release;
- frontend chat endpoint selection no longer treats
  `collaborative_note_decision` as a reason to use `/api/chat`;
- stale backend tests that proved chat-owned note decision execution were
  replaced with direct-route coverage or removed when they only described the
  retired chat effect/responder lifecycle;
- direct-route Google privacy coverage now verifies public-safe note decision
  event receipts without depending on chat completion.

Why this matters:

Before this pass, collaborative note proposal approval had two authorities: the
direct Notes API and a chat-turn-owned structured decision path. After this
pass, explicit note proposal approval/rejection is Notes-owned and no longer
depends on a live chat-turn lease.

TDD evidence recorded during the pass:

- RED:
  `test_chat_rejects_collaborative_note_decision_without_claiming_turn` failed
  because `/api/chat` still returned the old idempotency-key requirement before
  direct-route enforcement.
- RED:
  `test_chat_stream_rejects_collaborative_note_decision_without_claiming_turn`
  failed because `/api/chat/stream` still returned the old structured-decision
  `/api/chat` redirect response.
- RED: `chat endpoint selection streams only ordinary requests` failed because
  the frontend request selector still routed `collaborative_note_decision` to
  `/api/chat`.
- GREEN: `_execute_chat` now rejects `collaborative_note_decision` before the
  generic structured-decision stream check, and `selectChatEndpoint` no longer
  includes `collaborative_note_decision` in its JSON-chat selector list.
- Follow-up focused backend verification exposed stale chat-owned tests; the
  direct privacy behavior was retargeted to the direct route, and the retired
  chat effect/responder tests were removed.

Focused verification after implementation:

```text
venv/bin/pytest -q tests/test_main.py
294 passed, 1 warning
```

```text
node --test tests/frontend/api.test.mjs tests/frontend/requests.test.mjs tests/frontend/app-runtime.test.mjs tests/frontend/workspace-static.test.mjs
123 passed
```

```text
git diff --check
no output
```

Remaining direct decoupling:

- legacy schema/request-builder compatibility still allows parsing retired
  structured chat decisions, even though `/api/chat` now rejects their
  execution;
- unreachable legacy structured-decision branches remain inside `_execute_chat`
  for memory decisions and collaborative note decisions;
- old frontend request builders for retired chat structured decisions remain
  only for compatibility/test coverage.

Next proposed pass:

- remove retired structured-decision execution branches and stale request
  helpers now that Memory, Artifact, Notes, and Continuity direct lifecycle
  APIs own their user actions.

Work deferred until core decoupling is complete:

- broad manual end-to-end browser acceptance for every drawer action;
- public receipt contract cleanup such as removing internal job ids from chat
  queued action receipts;
- larger worker/runtime architecture changes unrelated to direct lifecycle
  ownership.

## Explicit Artifact Router Decoupling Pass

This pass removed the live artifact-router dependency after deterministic
artifact work has already been queued.

Completed work:

- explicit artifact creation requests that are recognized by the deterministic
  prequeue path now enqueue `create_artifact` and complete the chat turn through
  the prequeued-action responder path without calling the artifact router;
- combined explicit artifact plus workspace-note requests preserve action
  ordering and pass both queued receipts to the responder;
- ambiguous artifact discussion still uses the artifact router and still fails
  through the existing routing-timeout path when the router times out;
- artifact generation and persistence remain owned by the queued artifact job
  worker, not by the chat turn.

Why this matters:

The prior artifact execution decoupling moved generation/persistence behind
AgentJob, but explicit artifact turns could still fail after successful prequeue
because the chat turn called the artifact router before responding. That left a
live blocking dependency in front of an already-authoritative durable lifecycle.
After this pass, once explicit artifact work is queued, chat does not need the
router to decide the same artifact lifecycle again.

TDD evidence recorded during the pass:

- RED:
  `test_explicit_artifact_and_note_request_completes_without_router` failed
  because the turn service still called `TimingOutV4RoutingRequest` and raised
  `AgentColTurnRoutingTimeoutError` after queuing artifact and note work.
- GREEN: `_run_artifact_capable_with_deadline` now short-circuits to
  `_complete_prequeued_turn` when prequeued actions include `create_artifact`,
  before building router input or calling the artifact router.
- REFACTOR: the old post-router duplicate `create_artifact` prequeue branch was
  removed because the prequeued artifact path now exits earlier.

Focused verification after implementation:

```text
venv/bin/pytest -q tests/test_agent_col_turn_service_artifacts.py::test_explicit_artifact_and_note_request_completes_without_router
1 passed, 1 warning
```

```text
venv/bin/pytest -q tests/test_agent_col_turn_service_artifacts.py -k "explicit_artifact_and_note_request or ambiguous_artifact_discussion or artifact"
12 passed, 1 warning
```

```text
venv/bin/pytest -q tests/test_agent_col_turn_service.py -k "prequeue or note or memory"
13 passed, 45 deselected, 1 warning
```

Remaining direct decoupling:

- explicit workspace-note and memory prequeue paths still run through the
  artifact-capable turn path and can still depend on router completion even
  after deterministic durable work has been queued;
- ambiguous artifact requests still require chat-time routing, which is
  intentional until a separate artifact-intent lifecycle exists outside chat;
- legacy structured-decision schemas, frontend request helpers, and unreachable
  backend branches remain as deferred cleanup.

Next proposed pass:

- remove the artifact-router dependency for explicit note-only and memory-only
  durable requests once their deterministic prequeue has already produced
  queued actions, while preserving router behavior for ordinary chat and
  ambiguous artifact discussion.

Work deferred until core decoupling is complete:

- structured-decision cleanup: remove retired frontend request builders,
  retired structured chat fields, and unreachable backend execution branches
  only after the active lifecycle dependencies are gone;
- broad manual end-to-end browser acceptance for every drawer action;
- public receipt contract cleanup such as removing internal job ids from chat
  queued action receipts;
- larger worker/runtime architecture changes unrelated to direct lifecycle
  ownership.

## Memory-Owned Preference-Hypothesis Confirmation Pass

This uncommitted review pass moved surfaced preference-hypothesis confirmation
out of synchronous chat-turn effect ownership.

Completed work:

- preference observation and hypothesis capture still run after a normal
  conversational response;
- a surfaced, validated hypothesis now queues private Memory Analyst work;
- chat returns and persists only the queued receipt, not a completed Memory
  clarification effect;
- the Memory worker restores the validated private hypothesis and calls
  `open_preference_hypothesis_confirmation` with `turn_lease=None`;
- the worker records the clarification id and terminal Memory job report;
- the clarification still presents the governed candidate and explicit
  `no_save` choice, so confirmation creates no active memory;
- suppression remains limited to the existing deterministic ambiguous-memory
  preflight receipt, preventing a competing clarification while allowing
  unrelated queued note work and preference capture in the same turn.

Retry and provenance guarantees:

- queue and clarification identity use a SHA-256 digest over the user,
  workspace, session, source message, and the complete validated hypothesis;
- distinct hypotheses accepted from the same source message derive distinct
  clarification ids;
- the source user message remains the clarification evidence message;
- the hypothesis's durable last-observed timestamp makes repeated queue
  acceptance byte-for-byte identical, including private payload timestamps;
- the worker uses the persisted job creation time for the clarification
  creation window, so repeated execution builds the same envelope;
- the existing no-lease clarification transaction returns an exact stored
  retry without another write.

TDD evidence:

- RED: five focused tests failed because the service rejected no-lease
  confirmation, the worker did not recognize the private work type, no queue
  helper existed, and chat still attempted synchronous clarification creation.
- GREEN: those tests passed after queue, worker, service, and chat ownership
  moved to the Memory lifecycle.
- REFACTOR: clarification identity construction was simplified after GREEN;
  no unrelated production behavior changed.

Focused verification:

```text
venv/bin/pytest -q tests/test_trusted_memory_service.py tests/test_memory_proposal_job_worker.py tests/test_memory_proposal_tool.py tests/test_memory_clarification_database.py::test_clarification_exact_retry_without_turn_lease_returns_existing
56 passed
```

```text
venv/bin/pytest -q tests/test_main.py::test_chat_records_preference_observation_without_active_memory tests/test_main.py::test_chat_surfaces_preference_confirmation_without_saving_memory tests/test_main.py::test_chat_does_not_capture_preference_on_replay_or_structured_decision tests/test_main.py::test_chat_preflights_ambiguous_memory_request_into_clarification tests/test_main.py::test_chat_passes_preflight_receipt_tuple_through_real_turn_service tests/test_main.py::test_chat_preflight_still_captures_unrelated_preference_feedback
6 passed, 1 warning
```

```text
venv/bin/python -m py_compile main.py preference_learning.py trusted_memory_service.py memory_proposal_job_worker.py memory_proposal_tool.py
passed
```

Next remaining live chat-ownership dependency:

- responder tool state still exposes Memory and Notes turn-owner tokens even
  though queued workers restore those commands with `turn_lease=None`; that
  exposure should be removed in a separately approved pass without changing
  mixed-intent routing or prequeued-action duplicate suppression.

Work still deferred:

- preference policy and memory category policy changes;
- legacy structured `/api/chat` and old chat-turn effect-helper cleanup;
- ambiguous artifact routing changes;
- UI hardening and broad manual testing.

## Deterministic Ambiguous-Memory Preflight Decoupling Pass

This test-branch pass moved deterministic ambiguous-memory clarification
creation out of active chat-turn effect ownership.

Completed work:

- deterministic preflight still recognizes and validates the same bounded
  server-derived Memory candidates;
- preflight now queues a Memory Analyst job through the application-owned
  Memory queue with `turn_lease=None`;
- source-message provenance remains the claimed user message id;
- the queued receipt is passed into the turn service as prequeued work, which
  suppresses a duplicate explicit-memory queue attempt while preserving other
  independently supported actions in the same prompt;
- chat returns only the queued action receipt and no completed Memory
  clarification receipt;
- responder failure preserves the accepted queued receipt as a partial failure
  instead of completing a chat-owned clarification effect;
- post-response preference learning can still capture an unrelated
  non-authoritative observation from a mixed-intent turn, while a surfaced
  hypothesis cannot open a second chat-owned clarification after deterministic
  preflight work has already been queued;
- the Memory worker restores the private clarification command with
  `turn_lease=None`, creates the clarification through the governed Memory
  service, and records the clarification id and terminal job report;
- direct clarification selection and preference-hypothesis confirmation were
  not changed.

Why this matters:

Before this pass, `_execute_chat` synchronously called
`TrustedMemoryService.handle_natural_memory_decision` with the active
`ProposalTurnLease`, inserted the completed clarification receipt into the chat
turn, and depended on chat completion to persist matching effect state. The new
path ends chat ownership at queue acceptance. Clarification creation and its
terminal explanation now belong to the Memory worker, Memory state, and job
report surfaces.

TDD evidence:

- RED:
  `venv/bin/pytest -q tests/test_main.py -k "chat_preflight"` failed both
  preflight cases because chat still synchronously created and returned the
  clarification instead of queueing Memory-owned work.
- GREEN: the same command passed after preflight used the Memory queue, chat
  carried only the queued receipt, and failure reconciliation preserved that
  receipt without completing a chat effect.
- RED/GREEN review follow-up: a mixed-intent regression proved that suppressing
  all preference capture whenever preflight work was queued was too broad.
  Capture now remains available for unrelated explicit style feedback, while
  only the second chat-owned preference-confirmation clarification is
  suppressed.
- Collection-shape review confirmed that the awaited Memory queue receipt
  already has a trailing comma and therefore forms a one-element tuple. A
  regression now executes `_execute_chat` through the real
  `AgentColTurnService` and verifies tuple-shaped prequeued actions reach the
  responder boundary.
- REFACTOR: the lifespan now keeps one shared Memory queue instance for both
  turn-service and deterministic-preflight acceptance; no unrelated cleanup
  was performed.

Focused verification:

```text
venv/bin/pytest -q tests/test_main.py -k "chat_preflight"
2 passed, 293 deselected, 1 warning
```

```text
venv/bin/pytest -q tests/test_main.py -k "chat_preflight or select_memory_clarification or preference_confirmation"
6 passed, 289 deselected, 1 warning
```

```text
venv/bin/pytest -q tests/test_memory_proposal_job_worker.py
8 passed
```

```text
venv/bin/pytest -q tests/test_memory_proposal_tool.py -k "queued or clarification"
8 passed, 24 deselected
```

```text
venv/bin/pytest -q tests/test_agent_col_turn_service.py -k "preflight_memory or prequeue or note or memory"
15 passed, 45 deselected, 1 warning
```

Broader verification note:

- running `tests/test_main.py` together with the Memory worker file produced
  301 passing tests and two unrelated event-order assertion failures:
  `test_chat_builds_turn_command_and_persists_both_messages` and
  `test_chat_completes_claimed_turn_without_duplicate_message_writes`; both
  expect no `chat_session_detail` event even though ordinary chat already loads
  the active Memory clarification before this pass. They were not changed
  because that test expectation is outside this boundary.

Next remaining live chat-ownership dependency:

- preference-hypothesis confirmation still creates a completed Memory
  clarification synchronously after the responder and supplies the active
  `ProposalTurnLease`; the next bounded pass should queue that validated
  hypothesis as Memory-owned work without changing preference policy.

Work still deferred:

- legacy structured `/api/chat` cleanup;
- old chat-turn durable-effect helper cleanup;
- memory category policy;
- UI hardening and broad manual testing.

## Memory Clarification Creation Dependency Audit

Checkpoint commit before this audit: `93229f0e255c74b942cd7e48df603f20ce80d538`.

Read-only inspection covered the two remaining source-backed Memory
clarification creation dependencies:

1. deterministic ambiguous-memory preflight in `main.py`;
2. preference-hypothesis confirmation in `trusted_memory_service.py`.

No source behavior was changed during this audit.

### Deterministic ambiguous-memory preflight

Active production call path:

- ordinary `/api/chat` and `/api/chat/stream` enter `_execute_chat`;
- after structured Memory decision and clarification-selection handling, the
  preflight gate runs when there is a claimed chat turn, no structured Memory
  or other durable decision, and no precompleted Memory proposal or
  clarification;
- `_deterministic_memory_clarification_decision(payload.message)` recognizes a
  narrow ambiguous explicit Memory request, such as a request to remember one
  of multiple preferences;
- `_execute_chat` calls
  `TrustedMemoryService.handle_natural_memory_decision(...)` with a
  `ClarifyDecision` and `ProposalTurnLease(turn_id=chat_turn_claim.ids.turn_id,
  owner_token=chat_turn_claim.owner_token)`;
- `TrustedMemoryService.handle_natural_memory_decision` creates a
  `MemoryClarificationEnvelope`, using the lease turn id as
  `clarification_turn_id`, and calls
  `database.create_memory_clarification(..., turn_lease=command.turn_lease)`;
- `_execute_chat` inserts the resulting clarification receipt into
  `precompleted_memory_clarifications`, passes it through
  `AgentColTurnCommand`, and returns it in `ChatResponse.memory_clarifications`.

Where `ProposalTurnLease` is introduced and why it is required today:

- the lease is constructed in `main.py` from `chat_turn_claim`;
- it is required by the current chat response contract, not by the Memory
  storage primitive itself;
- `database.create_memory_clarification` accepts `turn_lease=None`, but with a
  lease it also writes the clarification as a chat-turn effect;
- `database.complete_chat_turn` then requires
  `response.memory_clarifications` to exactly match stored chat-turn
  clarification effects. Returning a completed clarification receipt without a
  matching stored chat-turn effect would fail
  `Completed response conflicts with stored turn effects.`

Memory-owned feasibility:

- Memory-owned creation with `turn_lease=None` is source-supported:
  `TrustedMemoryService.handle_natural_memory_decision` already falls back to
  `source_message_id` for `clarification_turn_id` when no lease is supplied,
  and `database.create_memory_clarification` skips chat-turn reads and writes in
  the no-lease path;
- it is not safe to keep the current synchronous chat-returned completed
  clarification shape while using `turn_lease=None`, because chat completion
  would either fail the stored-effect invariant or require restoring chat-turn
  Memory ownership;
- the safe boundary is queued Memory work: the chat turn receives only a queued
  action receipt, while the Memory worker creates the active clarification with
  `turn_lease=None`.

Recommended execution style:

- queued Memory work, not a direct Memory operation;
- reuse the existing worker contract that already handles queued
  `NaturalMemoryClarificationResult` by storing `clarification_id` in job
  result refs and emitting the "Memory clarification pending response" report;
- keep server-derived candidates from the deterministic recognizer and
  `source_message_id` provenance; do not infer clarification identity or
  candidates from model text.

Tests currently locking in old behavior:

- `tests/test_main.py::test_chat_preflights_ambiguous_memory_request_into_clarification`
  asserts the completed clarification is returned in chat and the natural
  Memory command carries a `ProposalTurnLease`;
- `tests/test_main.py::test_chat_preflight_clarification_returns_fallback_when_responder_fails`
  asserts the fallback chat response also returns a completed clarification.

### Preference-hypothesis confirmation

Active production call path:

- ordinary `_execute_chat` completes responder execution and builds
  `chat_response`;
- if there is a claimed chat turn, no structured durable decision, no
  continuity selection, and the response has no Memory proposals, Memory
  clarifications, collaborative note effects, artifact feedback, or continuity
  choices, `_execute_chat` calls `preference_learning_service.capture(...)`;
- when capture returns a `surfaced_hypothesis`, `_execute_chat` calls
  `TrustedMemoryService.open_preference_hypothesis_confirmation(...)` with
  `ProposalTurnLease(turn_id=chat_turn_claim.ids.turn_id,
  owner_token=chat_turn_claim.owner_token)`;
- `TrustedMemoryService.open_preference_hypothesis_confirmation` creates a
  two-choice clarification from the hypothesis and "Do not save", derives the
  clarification id using the lease turn id, and calls
  `database.create_memory_clarification(..., turn_lease=turn_lease)`;
- `_execute_chat` overwrites `chat_response.memory_clarifications` with the
  returned receipt before calling `database.complete_chat_turn`.

Where `ProposalTurnLease` is introduced and why it is required today:

- the lease is constructed in `main.py` from `chat_turn_claim`;
- `TrustedMemoryService.open_preference_hypothesis_confirmation` explicitly
  rejects non-lease calls with "A preference confirmation requires retry-safe
  turn ownership";
- as with deterministic preflight, the deeper reason is the current chat
  response effect invariant: a completed clarification returned from chat must
  have been written as a chat-turn clarification effect.

Memory-owned feasibility:

- the storage layer can support no-lease clarification creation, but
  `open_preference_hypothesis_confirmation` would need a narrow API change to
  allow `turn_lease=None` and derive `clarification_turn_id` from
  `source_message_id`;
- keeping the completed clarification in `ChatResponse.memory_clarifications`
  would remain unsafe without chat-turn effect ownership;
- Memory-owned preference confirmation is safest as queued Memory work that
  carries the server-validated `PreferenceHypothesis` payload privately to the
  worker, then calls the Memory service with `turn_lease=None`.

Recommended execution style:

- queued Memory work, not direct synchronous Memory creation;
- preference confirmation is opportunistic post-response learning, so it should
  not block chat completion or restore chat effect ownership;
- the queued receipt should be the only chat-visible artifact for this
  lifecycle. The active clarification should surface through Memory-owned
  session state, job result refs, and the worker report.

Tests currently locking in old behavior:

- `tests/test_main.py::test_chat_surfaces_preference_confirmation_without_saving_memory`
  asserts the completed preference clarification is returned in chat;
- `tests/test_trusted_memory_service.py::test_preference_hypothesis_confirmation_opens_unsaved_memory_choice`
  constructs a required `ProposalTurnLease`;
- `tests/test_trusted_memory_service.py::test_confirmed_hypothesis_creates_pending_proposal_not_active_memory`
  opens the preference confirmation with a lease before selecting it.

### Shared contract and pass split

Both dependencies should converge on the same Memory-owned clarification
creation contract:

- server-validated source context and candidates;
- `source_message_id` as the no-lease clarification turn/source discriminator;
- `TrustedMemoryService`/database creation with `turn_lease=None`;
- no completed Memory clarification receipt in `ChatResponse`;
- chat-visible queued action receipt only;
- Memory worker completion/report owns the created clarification result.

They should be split into two implementation passes:

1. deterministic ambiguous-memory preflight first;
2. preference-hypothesis confirmation second.

The split is recommended because the trigger timing and product behavior differ.
The deterministic path is an explicit user Memory request that currently
short-circuits into immediate clarification UI and fallback response handling.
Preference confirmation is post-response, opportunistic, and already suppressed
whenever other durable effects exist. Keeping them separate reduces regression
risk and keeps TDD evidence easy to inspect.

### Recommended next pass

Goal:

- move deterministic ambiguous-memory preflight creation to queued Memory-owned
  clarification work with `turn_lease=None`.

Expected files:

- `main.py`: replace synchronous preflight clarification creation and
  `precompleted_memory_clarifications` insertion with queued Memory job
  creation/dispatch and queued action receipt handling;
- `memory_proposal_job_worker.py`: likely add or generalize a private
  clarification-creation payload helper if the existing natural-memory payload
  is not sufficient for preflight provenance/reporting;
- `memory_proposal_tool.py`: possible helper reuse only if the queue-building
  code should not live in `main.py`;
- `tests/test_main.py`: update the two deterministic preflight tests to assert
  queued receipt only, no completed chat clarification, and no
  `ProposalTurnLease`;
- `tests/test_memory_proposal_job_worker.py`: add focused worker coverage for
  the queued deterministic clarification payload creating via
  `TrustedMemoryService.handle_natural_memory_decision(..., turn_lease=None)`;
- `docs/async-work/async-work-notes.md`: record pass outcome after
  implementation.

Expected verification:

- focused RED/GREEN pytest for the two `tests/test_main.py` deterministic
  preflight cases;
- focused worker pytest for the new queued clarification-creation payload;
- focused related Memory proposal tool/job tests if queue helper code is shared;
- `py_compile` for touched Python modules;
- `git diff --check`.

Time/usage estimate:

- deterministic preflight pass alone is a medium pass, roughly 60-90 minutes
  for TDD, implementation, focused verification, docs, commit, and push;
- this is unlikely to fit comfortably inside half of the current remaining
  window if half means about 45-50 minutes, though it might fit only with a very
  tight implementation and no unexpected test fallout;
- preference-hypothesis confirmation is another medium-to-large pass, roughly
  75-120 minutes because it needs a Memory service API contract change plus
  private queued hypothesis payload handling;
- both paths together should not be attempted in the current remaining window.

Handoff context:

- exact remaining live chat ownership is limited to Memory clarification
  creation paths that return completed clarification receipts from chat:
  deterministic ambiguous-memory preflight in `main.py` and
  preference-hypothesis confirmation in `main.py`/
  `trusted_memory_service.py`;
- Memory clarification selection has already moved to queued Memory-owned work
  and calls `TrustedMemoryService.select_memory_clarification(...,
  turn_lease=None)`;
- direct Memory storage supports no-lease clarification creation, but chat
  completion still requires any completed Memory clarification included in
  `ChatResponse` to match stored chat-turn effects;
- legacy structured `/api/chat` compatibility cleanup remains deferred unless a
  source-level conflict appears while removing these active creation
  dependencies.

## Memory-Owned Natural Clarification Selection Pass

This pass preserved natural chat answers to active Memory clarifications while
moving execution fully behind Memory-owned queued work.

Behavioral change:

- Agent Col can still recognize natural answers such as "the first one" when a
  server-validated active Memory clarification exists;
- the responder now uses a narrow `select_memory_clarification_candidate` tool
  for that lifecycle instead of `propose_memory_signal` with
  `clarification_selection`;
- the narrow tool exposes only `selected_candidate_index` to the model;
- the clarification id comes only from server-injected active clarification
  context and tool state;
- the narrow tool queues a Memory Analyst job with a private
  `memory_clarification_selection` payload;
- the Memory Analyst worker consumes that payload by calling
  `TrustedMemoryService.select_memory_clarification(..., turn_lease=None)`;
- chat receives only the queued action receipt for this lifecycle;
- chat does not receive or persist a completed memory proposal/effect from the
  natural clarification-selection path.

Why this boundary matters:

The direct Memory clarification API already supported `turn_lease=None`, but
the responder/tool natural path still pointed at the old
`propose_memory_signal(... clarification_selection ...)` route. That old route
was actively reachable from responder instructions and was broken after
chat-turn leases were removed from memory tool context. A direct synchronous
repair would have conflicted with chat-turn completion because Memory-owned
selection intentionally does not write chat-turn memory proposal effects. The
queued selection boundary preserves natural conversation while keeping the
Memory UI, Memory service, worker, and job reports authoritative for the final
result.

TDD evidence recorded during the pass:

- RED: `test_memory_worker_completes_queued_clarification_selection_without_turn_lease`
  failed because the worker treated every memory job payload as a natural
  memory decision and failed the clarification-selection payload.
- GREEN: `memory_proposal_job_worker.py` now restores
  `SelectMemoryClarificationCommand` from a private selection payload and calls
  `select_memory_clarification` with `turn_lease=None`.
- RED: selection-tool tests failed because
  `create_select_memory_clarification_tool` did not exist.
- GREEN: `memory_proposal_tool.py` now exposes
  `select_memory_clarification_candidate`, queues a Memory Analyst job, and
  requires `active_memory_clarification_id` from server-owned tool state.
- RED: responder tests failed because the app did not wire the new tool and the
  instruction still routed natural clarification answers through
  `propose_memory_signal`.
- GREEN: `agent_col_responder.py` wires the new tool and instructs Agent Col to
  use it only with server-validated active clarification context.
- RED: runtime tests failed because `SupervisorTurnContext` had no active
  clarification field and did not collect the new tool response.
- GREEN: `supervisor_runtime.py` now injects active clarification context into
  tool state and model context, and collects the new tool's queued action
  without adding memory proposals.
- RED: the main chat boundary test failed because `AgentColTurnCommand` had no
  active clarification context.
- GREEN: `main.py` reads the active Memory clarification from authoritative
  chat-session detail for ordinary chat turns and passes it through
  `agent_col_turn_service.py`.
- RED: the `propose_memory_signal` declaration test failed because
  `clarification_selection` was still model-visible.
- GREEN: `propose_memory_signal` no longer exposes `clarification_selection`;
  natural selection is available only through the narrow queued tool.
- REFACTOR: replaced stale malformed-selection coverage with invalid-index
  coverage on the new selection tool.

Focused verification after implementation:

```text
venv/bin/python -m pytest tests/test_memory_proposal_tool.py tests/test_memory_proposal_job_worker.py tests/test_agent_col_responder.py tests/test_supervisor_runtime.py -k "memory or clarification" -q
52 passed, 63 deselected, 1 warning
```

```text
venv/bin/python -m pytest tests/test_agent_col_turn_service.py tests/test_main.py -k "clarification_selection or active_memory_clarification or queued" -q
9 passed, 345 deselected, 1 warning
```

```text
venv/bin/python -m py_compile agent_col_responder.py memory_proposal_tool.py memory_proposal_job_worker.py supervisor_runtime.py agent_col_turn_service.py main.py
passed
```

```text
git diff --check
passed
```

Remaining direct decoupling:

- preference-hypothesis confirmation can still open a Memory clarification from
  the ordinary chat path with a live `ProposalTurnLease`;
- deterministic ambiguous Memory clarification preflight still creates
  clarification receipts in the chat path with a live `ProposalTurnLease`;
- legacy structured `/api/chat` Memory clarification-selection compatibility
  still exists, but current active frontend selection and natural responder
  selection no longer need it;
- ambiguous artifact requests still require chat-time routing.

Next proposed pass:

- inspect and decouple the next smallest live chat-ownership dependency:
  Memory clarification creation that still requires a live `ProposalTurnLease`
  for preference-hypothesis confirmation or deterministic ambiguous-memory
  preflight. Preserve governed clarification receipts, but move creation behind
  a Memory-owned queued or direct lifecycle only if the source evidence can be
  kept authoritative without chat-turn effects.

## Read-Only Clarification-Selection Reachability Investigation

This was a read-only investigation only. No source behavior was changed.

Investigation result:

- the legacy natural Memory clarification-selection branch in
  `TrustedMemoryService.handle_natural_memory_decision` is still reachable from
  an active responder/tool path;
- it is no longer reachable with a valid `ProposalTurnLease`, because the
  responder memory tool context no longer carries chat-turn ids or owner tokens;
- this is active remaining chat/responder coupling, not deferred dead-code
  cleanup.

Exact live responder/tool path:

1. An ordinary chat request reaches `/api/chat/stream` or `/api/chat`.
2. `main.py` builds an `AgentColTurnCommand` and calls the turn service.
3. `SupervisorRuntime.run_turn` creates ADK session state with Memory context,
   but no longer exposes `memory_turn_id` or `memory_turn_owner_token`.
4. `agent_col_responder.py` and `supervisor.py` still instruct the model that
   when the user answers a prior Memory clarification, it should call
   `propose_memory_signal` with `clarification_selection`.
5. `memory_proposal_tool.py::propose_memory_signal(...)` still accepts
   `clarification_selection`.
6. `_server_context()` returns `turn_lease=None`.
7. `_server_command()` builds
   `NaturalMemoryCommand(..., clarification_selection=..., turn_lease=None)`.
8. `TrustedMemoryService.handle_natural_memory_decision()` enters its
   `command.clarification_selection is not None` branch and raises
   `ValueError("A clarification selection requires retry-safe turn ownership.")`.
9. The tool catches that `ValueError` and returns
   `{"status": "rejected", "error_code": "invalid_memory_candidate"}`.

Separate deferred compatibility cleanup:

- the legacy structured `/api/chat` `memory_clarification_selection` path still
  exists in backend code and tests;
- current frontend click behavior does not use that path: `frontend/app.mjs`
  calls the direct `selectMemoryClarification(...)` wrapper, and
  `frontend/requests.mjs::selectChatEndpoint()` no longer routes
  `memory_clarification_selection` to `/api/chat`;
- keep the structured `/api/chat` compatibility path separate and deferred
  unless later source inspection proves it is still part of an active live
  dependency.

Current active decoupling focus:

- retire the responder/tool natural clarification-selection path so the direct
  Memory clarification API is the only active selection lifecycle;
- preserve already-direct selection through
  `/api/users/{user_id}/projects/{project_id}/memory/clarifications/{clarification_id}/select`;
- preserve Memory governance, duplicate suppression, mixed-intent routing, and
  source-message provenance from the prior completed pass;
- do not start structured-decision cleanup yet.

Next proposed pass:

- remove responder/supervisor instructions that advertise
  `clarification_selection` through `propose_memory_signal`;
- make `memory_proposal_tool.py` reject or ignore `clarification_selection`
  before it can call `TrustedMemoryService.handle_natural_memory_decision`;
- add focused RED tests proving the responder/tool path no longer calls the
  natural service branch for clarification selection and that direct selection
  remains the active lifecycle;
- update this notes file after implementation, then checkpoint.

Resume notes for the next machine:

- start from clean `main` after the documentation checkpoint;
- do not implement this pass until explicitly approved again;
- inspect current source before editing in case another machine has changed the
  branch;
- keep the legacy structured `/api/chat` clarification-selection cleanup
  separate unless live source inspection proves it belongs in the same pass.

## Responder Memory/Note Owner-Token And Clarification Creation Decoupling Pass

This pass removed the remaining live responder owner-token dependency for
model-invoked memory/note proposal tools and moved Memory clarification
creation off chat-turn lease ownership.

Completed work:

- supervisor ADK session state no longer exposes `memory_turn_id`,
  `memory_turn_owner_token`, `note_turn_id`, or `note_turn_owner_token`;
- memory and collaborative-note tools ignore stale owner-token state and submit
  `turn_lease=None` to their owning services;
- queued memory/note proposal jobs now use `source_message_id` as
  `source_turn_id` when no lease exists, matching the already-decoupled worker
  restore path;
- natural Memory clarification creation now uses `source_message_id` as
  clarification provenance when no chat-turn lease is present;
- Memory clarification creation can persist a Memory-owned clarification
  document and active session pointer without reading or writing a chat turn;
- duplicate/retry suppression is preserved for both turn-owned and
  source-message-owned clarification creation;
- the already-direct clarification selection lifecycle remains covered and
  unchanged;
- mixed-intent routing remains intact: deterministic durable work can be queued
  without a live owner token, but chat routing still handles conversational work
  in the same user prompt.

Why this matters:

The prior pass removed turn leases from explicit note/memory prequeue, but a
live chat-owned lease still leaked through responder tool session state. That
left model-invoked note/memory proposal work dependent on a chat turn owner
token even though queued jobs and worker restores already use source-message
provenance. Memory clarification creation had the same ownership issue: the
service rejected no-lease clarification creation and the database transaction
required a turn document/effect write. This pass makes those lifecycles
Memory/Note-owned while preserving governance checks, session/project scoping,
idempotent duplicate handling, and mixed-intent chat routing.

TDD evidence recorded during the pass:

- RED: `venv/bin/pytest -q tests/test_supervisor_runtime.py -k "server_owned_memory_context or server_owned_note_context"`
  failed because responder session state still contained memory/note turn ids
  and owner tokens.
- RED: `venv/bin/pytest -q tests/test_memory_proposal_tool.py tests/test_collaborative_note_tool.py -k "queued or turn_lease or owner_token or pending_result"`
  failed because stale tool state still reconstructed `ProposalTurnLease`.
- RED: `venv/bin/pytest -q tests/test_memory_proposal_service.py -k "natural_clarification"`
  failed because natural clarification creation still required retry-safe turn
  ownership.
- RED: `venv/bin/pytest -q tests/test_memory_clarification_database.py -k "clarification_creation_without_turn_lease or exact_retry_without_turn_lease or validates_before_firestore_access"`
  failed because database validation still rejected `turn_lease=None`.
- GREEN: supervisor stopped placing owner tokens into ADK session state;
  memory/note tools stopped reading owner tokens; natural clarification
  creation uses source-message provenance when no lease exists; database
  clarification creation skips turn reads/writes in the no-lease path.
- REFACTOR: none beyond narrow naming/docstring updates.

Focused verification after implementation:

```text
venv/bin/pytest -q tests/test_supervisor_runtime.py
47 passed, 1 warning
```

```text
venv/bin/pytest -q tests/test_memory_proposal_tool.py tests/test_collaborative_note_tool.py
42 passed
```

```text
venv/bin/pytest -q tests/test_memory_proposal_service.py
22 passed
```

```text
venv/bin/pytest -q tests/test_memory_clarification_database.py
12 passed
```

```text
venv/bin/pytest -q tests/test_main.py -k "select_memory_clarification or memory_clarification"
4 passed, 290 deselected, 1 warning
```

```text
node --test tests/frontend/requests.test.mjs --test-name-pattern "chat endpoint selection"
21 passed
```

```text
node --test tests/frontend/api.test.mjs --test-name-pattern "selectMemoryClarification"
39 passed
```

```text
node --test tests/frontend/app-runtime.test.mjs --test-name-pattern "memory clarification selection during a pending chat uses direct memory API"
41 passed
```

```text
venv/bin/pytest -q tests/test_memory_proposal_job_worker.py
5 passed
```

Remaining direct decoupling:

- the legacy natural Memory clarification-selection branch in
  `TrustedMemoryService.handle_natural_memory_decision` still requires a
  `ProposalTurnLease`; direct clarification selection already has its own
  Memory-owned API, so this remaining branch should be retired or redirected
  without reintroducing chat ownership;
- ambiguous artifact requests still require chat-time routing;
- legacy structured-decision schemas, frontend request helpers, and unreachable
  backend branches remain as deferred cleanup.

Next proposed pass:

- remove or quarantine the legacy natural Memory clarification-selection branch
  that still requires a live chat-turn lease, while preserving the direct
  `/memory/clarifications/{clarification_id}/select` lifecycle as the only
  active selection path.

Work deferred until core decoupling is complete:

- structured-decision cleanup: remove retired frontend request builders,
  retired structured chat fields, and unreachable backend execution branches
  only after the active lifecycle dependencies are gone;
- broad manual end-to-end browser acceptance for every drawer action;
- public receipt contract cleanup such as removing internal job ids from chat
  queued action receipts;
- larger worker/runtime architecture changes unrelated to direct lifecycle
  ownership.

## Explicit Note/Memory Prequeue Lease Decoupling Pass

This pass removed chat-turn lease ownership from deterministic explicit
workspace-note and memory prequeue commands.

Completed work:

- explicit workspace-note prequeue commands now use `turn_lease=None`;
- explicit memory prequeue commands now use `turn_lease=None`;
- mixed-intent prompts still route/respond normally after durable note/memory
  work is queued, so conversational work in the same user message is preserved;
- existing queue code continues to use `source_message_id` as `source_turn_id`
  whenever a queued note or memory command has no turn lease.

Why this matters:

The prior proposed symmetry pass would have skipped routing for explicit
note-only and memory-only turns. Re-inspection showed that would be too broad:
prequeued note/memory work can be only one clause in a mixed-intent prompt, and
the remaining request still needs routed conversational handling. The smaller
correct boundary was the live lease dependency. Explicit note and memory
prequeue no longer carry a chat-turn owner token into durable work that can
already be identified by source message provenance and queued-action receipts.

TDD evidence recorded during the pass:

- RED: `venv/bin/pytest -q tests/test_agent_col_turn_service.py -k "prequeue or note or memory"`
  failed in six explicit prequeue cases because note and memory commands still
  contained `ProposalTurnLease`.
- GREEN: `_explicit_workspace_note_command` and `_explicit_memory_command` now
  set `turn_lease=None` for deterministic prequeue commands.
- REFACTOR: none.

Focused verification after implementation:

```text
venv/bin/pytest -q tests/test_agent_col_turn_service.py -k "prequeue or note or memory"
13 passed, 45 deselected, 1 warning
```

```text
venv/bin/pytest -q tests/test_memory_proposal_tool.py tests/test_collaborative_note_tool.py -k "queued or turn_lease or owner_token"
2 passed, 41 deselected
```

```text
venv/bin/pytest -q tests/test_memory_proposal_job_worker.py -k "payload or turn_lease or queued"
3 passed, 2 deselected
```

Remaining direct decoupling:

- responder tool state still exposes `memory_turn_owner_token` and
  `note_turn_owner_token`, allowing model-invoked memory/note tools to
  reconstruct `ProposalTurnLease` even though queued jobs do not serialize owner
  tokens and workers restore commands with `turn_lease=None`;
- ambiguous artifact requests still require chat-time routing;
- legacy structured-decision schemas, frontend request helpers, and unreachable
  backend branches remain as deferred cleanup.

Next proposed pass:

- remove chat-turn owner-token exposure from responder memory/note tool state
  and make model-invoked queued memory/note proposal jobs use source-message
  provenance instead of a live chat-turn lease, while preserving prequeued-action
  duplicate suppression.

Work deferred until core decoupling is complete:

- structured-decision cleanup: remove retired frontend request builders,
  retired structured chat fields, and unreachable backend execution branches
  only after the active lifecycle dependencies are gone;
- broad manual end-to-end browser acceptance for every drawer action;
- public receipt contract cleanup such as removing internal job ids from chat
  queued action receipts;
- larger worker/runtime architecture changes unrelated to direct lifecycle
  ownership.

## Responder ClarifyDecision Queue Decoupling Pass

This uncommitted review pass moved responder-generated ambiguous Memory
decisions onto the existing Memory AgentJob lifecycle.

Completed work:

- the raw and validated queue predicates now admit only
  `profile_candidate` and `clarify` decisions;
- responder `ClarifyDecision` calls queue exactly one Memory Analyst job and
  return only its queued receipt;
- the responder tool no longer calls synchronous Memory clarification
  creation when the production job repository is available;
- supervisor and chat responses carry no completed clarification effect for
  this path;
- the existing worker restores the queued `ClarifyDecision` and creates the
  governed clarification with `turn_lease=None`;
- deterministic preflight duplicate suppression, preference confirmation,
  profile-candidate queueing, and direct clarification selection remain
  unchanged.

TDD evidence:

- RED: the focused responder-tool regression failed because `clarify` still
  fell through to synchronous `handle_natural_memory_decision`;
- GREEN: admitting only `clarify` alongside `profile_candidate` in the raw and
  validated queue predicates made the tool return one queued receipt without a
  synchronous service call;
- REFACTOR: none.

Focused verification:

```text
venv/bin/pytest -q tests/test_memory_proposal_tool.py tests/test_memory_proposal_job_worker.py
42 passed
```

```text
venv/bin/pytest -q tests/test_supervisor_runtime.py -k "queued_memory or clarification or prequeued"
9 passed, 40 deselected, 1 warning
```

```text
venv/bin/pytest -q tests/test_main.py::test_chat_returns_responder_queued_clarification_without_effect tests/test_main.py::test_chat_preflights_ambiguous_memory_request_into_clarification tests/test_main.py::test_chat_passes_preflight_receipt_tuple_through_real_turn_service tests/test_main.py::test_chat_preflight_still_captures_unrelated_preference_feedback tests/test_main.py::test_chat_surfaces_preference_confirmation_without_saving_memory tests/test_agent_col_turn_service.py::test_turn_service_preserves_preflight_memory_queue_without_requeue
6 passed, 1 warning
```

```text
venv/bin/python -m py_compile memory_proposal_tool.py
passed
```

Next remaining live chat-owned Memory dependency:

- legacy `memory_clarification_selection` requests sent through `/api/chat`
  still synchronously consume the clarification with an active
  `ProposalTurnLease`; the active frontend uses the direct Memory selection
  API, so retiring or redirecting this compatibility path is a separate
  bounded pass.

## Legacy Chat Clarification-Selection Retirement Pass

This uncommitted review pass retired the last reachable
`memory_clarification_selection` lifecycle owned by `/api/chat`.

Completed work:

- `/api/chat` now rejects `memory_clarification_selection` with HTTP 409 and
  directs callers to the direct Memory API;
- rejection occurs before clarification-specific idempotency handling, chat
  turn claim, `ProposalTurnLease` construction, Memory service execution, turn
  service execution, or chat completion;
- the direct Memory clarification-selection endpoint remains unchanged and
  continues to execute with `turn_lease=None`;
- queued natural-language clarification selection remains unchanged;
- `ChatRequest`, historical `ChatTurnRequest` metadata, and the frontend
  compatibility request builder remain for later contract cleanup;
- tests requiring successful chat-owned selection and its downstream error
  handling were removed because that lifecycle is no longer reachable.

TDD evidence:

- RED: the focused chat regression returned the former idempotency-key 422
  response instead of the required pre-claim 409;
- GREEN: the early structured-decision guard returned 409 with no claim,
  Memory service call, turn-service call, completion, or durable effect;
- REFACTOR: obsolete execution-path tests were removed; production execution
  code remains deferred cleanup behind the new guard.

Focused verification:

```text
venv/bin/pytest -q tests/test_main.py::test_chat_rejects_clarification_selection_before_claim_or_execution tests/test_main.py::test_select_memory_clarification_uses_memory_api_without_chat_turn tests/test_main.py::test_select_memory_clarification_memory_api_requires_idempotency_key tests/test_main.py::test_select_memory_clarification_memory_api_maps_stale_state_to_conflict tests/test_memory_proposal_tool.py::test_clarification_selection_tool_queues_memory_work_without_service_call tests/test_memory_proposal_job_worker.py::test_memory_worker_completes_queued_clarification_selection_without_turn_lease tests/test_supervisor_runtime.py::test_run_turn_collects_queued_memory_clarification_selection_only
8 passed, 1 warning
```

```text
node --test --test-name-pattern "memory clarification selection during a pending chat uses direct memory API" tests/frontend/app-runtime.test.mjs
1 passed
```

```text
node --test --test-name-pattern "selectMemoryClarification" tests/frontend/api.test.mjs
2 passed
```

```text
venv/bin/pytest -q tests/test_schemas.py tests/test_chat_turn_database.py -k "memory_clarification_selection"
5 passed, 153 deselected
```

```text
node --test --test-name-pattern "memory clarification selection" tests/frontend/requests.test.mjs
2 passed
```

```text
venv/bin/python -m py_compile main.py
passed
```

Deferred cleanup:

- remove the now-unreachable `/api/chat` clarification-selection execution and
  fallback branches;
- remove compatibility request builders and chat-state helpers after the
  public contract retirement boundary is approved;
- retain historical persisted turn metadata until a separate schema migration.

## Atomic/Idempotent Preference-Capture Prerequisite (Pass A)

This uncommitted review pass adds the persistence prerequisite for moving
preference capture out of the synchronous chat lifecycle later. Chat
orchestration and queue behavior are intentionally unchanged in Pass A.

Completed work:

- one Firestore transaction now covers deterministic observation insertion,
  hypothesis read/merge/write, and capture-outcome persistence;
- the deterministic observation id keys an immutable capture-outcome document,
  so exact retries return the original observation, hypothesis, and surfaced
  hypothesis snapshot without incrementing evidence or rewriting state;
- retry-time clock drift does not change the stored logical outcome, while
  conflicting content under the same observation id is rejected;
- distinct concurrent observations targeting one hypothesis use Firestore
  transaction conflict retries, preventing lost hypothesis updates;
- the transaction still delegates confidence, contradiction, evidence-count,
  age, and surfacing decisions to the existing preference-learning policy
  functions;
- `PreferenceLearningService.capture_strict(...)` exposes the same capture
  behavior with persistence failures propagated for a future worker, while the
  current synchronous `capture(...)` caller retains its sanitized no-effect
  failure behavior.

TDD evidence:

- RED: atomic database tests failed because no atomic capture operation
  existed, and the strict service test failed because no propagating service
  path existed;
- GREEN: the transaction and strict service path made exact retry, concurrent
  merge, stable threshold outcome, and persistence propagation tests pass;
- RED/GREEN follow-up: a retry with a later clock value initially conflicted;
  logical observation comparison was narrowed to exclude only `created_at`, so
  the original persisted outcome is now returned unchanged.

Pass B — next approved dependency:

- add durable queued/background preference-capture work using the Pass A
  primitive, then remove synchronous capture from the live chat lifecycle;
- preference capture is non-authoritative internal learning work. Preserve the
  current user-facing response behavior and do not append its queued receipt to
  `ChatResponse` unless a source-backed policy requirement is identified;
- keep surfaced hypotheses flowing into the existing Memory-owned
  preference-confirmation job, preserving provenance, thresholds, governance,
  and duplicate suppression.

## Queued Preference-Capture Decoupling (Pass B)

This uncommitted review pass moves non-authoritative preference capture off the
synchronous chat lifecycle and onto the existing durable Memory AgentJob
domain.

Completed work:

- chat performs deterministic extraction and validates the resulting
  `PreferenceObservation` without persisting it;
- the exact accepted observation queues in a private
  `preference_learning_capture` payload with deterministic identity and source
  turn/message provenance;
- chat does not call synchronous `PreferenceLearningService.capture()`, wait
  for observation/hypothesis persistence, or append the internal capture
  receipt to `ChatResponse`;
- the Memory worker restores and provenance-validates the accepted observation,
  then calls `capture_observation_strict()` without rerunning extraction, using
  Pass A's atomic/idempotent persistence primitive;
- persistence or downstream queue failures produce a sanitized, retryable
  AgentJob failure and report without changing the already-completed chat;
- a surfaced hypothesis queues the existing deterministic
  preference-confirmation AgentJob;
- deterministic ambiguous-memory preflight records suppression only in the
  capture job's downstream-confirmation flag: preference capture still runs,
  but competing confirmation work is not queued;
- turns without recognized preference evidence do not create capture jobs.

TDD evidence:

- RED: focused service, queue, worker, and chat tests failed because
  recognition, the private capture work type, worker dependencies, and chat
  enqueue behavior did not yet exist;
- GREEN: recognition queues one private job, exact enqueue retries reuse its
  deterministic identity, worker capture and sanitized failure paths pass, and
  chat responses remain independent of the internal job receipt;
- REFACTOR: preference-confirmation queue/dispatch is shared by the existing
  Memory queue facade and the new worker path.

Corrective durability follow-up:

- the initial implementation stored the raw learning command and reran
  extraction in the worker, which could reinterpret accepted work after a
  restart or code change;
- recognition now returns the fully validated observation, the private payload
  stores that exact evidence, and recovery execution persists it directly;
- focused coverage proves extraction runs once during acceptance and is not
  invoked when the worker restores the durable payload.

Preserved behavior:

- Pass A confidence, contradiction, age, evidence-count, and surfacing policy;
- Memory confirmation governance and deterministic duplicate suppression;
- direct Memory APIs, deterministic memory preflight, clarification selection,
  mixed-intent routing, and ordinary chat response contracts.

## Preference Capture/Confirmation Failure Attribution

The closure audit found one phase-attribution defect in the queued preference
capture worker: the exception boundary covered both atomic evidence capture and
the later confirmation-job enqueue. A confirmation scheduling failure could
therefore report that evidence was not captured after capture had succeeded.

This uncommitted review pass narrows those failure phases:

- an exception from `capture_observation_strict()` remains the sanitized,
  retryable `preference_capture_failed` result;
- an exception while scheduling a surfaced hypothesis now produces the
  separate retryable `preference_confirmation_enqueue_failed` result;
- the confirmation failure report states that preference evidence was
  captured but confirmation could not be scheduled;
- confirmation failure is not silently swallowed and confirmation remains a
  required governed follow-up for a surfaced hypothesis;
- retry execution can safely revisit the same atomic capture and deterministic
  confirmation identities without duplicating evidence or clarification work.

TDD evidence:

- RED: the downstream enqueue-failure regression received
  `preference_capture_failed`;
- GREEN: the same scenario receives
  `preference_confirmation_enqueue_failed`, while the existing true capture
  failure test still receives `preference_capture_failed`;
- the focused retry regression executes the same stored observation twice,
  records one logical evidence write, and reuses one confirmation-job identity.

Audited closure sequence:

1. finish required deferred correctness and dead-path cleanup;
2. implement AgentJob retry, lease recovery, and drainer work;
3. run automated cross-boundary lifecycle verification;
4. perform manual break-testing across chat, resource surfaces, process
   restart, retry, failure, and mixed-intent behavior.

## Dead Chat Clarification-Selection Execution Cleanup

This uncommitted cleanup pass removes only the unreachable synchronous
`memory_clarification_selection` execution lifecycle behind `/api/chat`'s
authoritative early HTTP 409 guard.

Removed:

- the dead `_execute_chat` branch that called
  `select_memory_clarification(...)` with an active `ProposalTurnLease`;
- its dead synchronous result/error mapping into chat-owned actions and Memory
  proposal receipts;
- the selection-specific responder failure/timeout fallback helper and its
  unreachable call sites.

Preserved:

- the early `/api/chat` 409 compatibility response;
- the direct Memory clarification-selection API with `turn_lease=None`;
- queued natural-language clarification selection;
- `ChatRequest.memory_clarification_selection`;
- historical `ChatTurnRequest` and persisted structured-decision metadata;
- all other deferred structured-decision branches and inert lease plumbing.

Remaining closure work:

- separately approved cleanup of the other unreachable structured-decision
  branches, inert turn-lease/effect plumbing, and inactive frontend builders;
- AgentJob retry/recovery/drainer work remains the next later phase, followed by
  automated boundary verification and manual break-testing.

## Dead Structured Chat Execution Cleanup

This uncommitted backend-only cleanup pass removes the remaining unreachable
structured `/api/chat` execution/fallback behavior that sits behind the
authoritative early HTTP 409 guards.

Removed:

- the dead Memory-decision branch that called `decide_memory_proposal(...)` from
  `_execute_chat` and recorded a chat-turn decision action;
- the dead collaborative-note-decision branch that called `decide_proposal(...)`
  from `_execute_chat` and recorded a chat-turn note decision effect;
- the dead post-guard Continuity-selection execution path by keeping ordinary
  conversational Continuity resolution and always passing `selection=None` from
  `_execute_chat`;
- obsolete Memory-clarification-selection `/api/chat` idempotency/fallback
  handling that could no longer run after the early direct-API guard;
- structured-decision booleans in the ordinary turn command that could only have
  been true through rejected request fields.

Preserved:

- all early `/api/chat` 409 guards for retired structured inputs;
- ordinary conversational Continuity resolution, including ambiguous-choice
  chat responses and resolved context injection;
- deterministic ambiguous-Memory preflight and queued Memory AgentJob receipt
  behavior;
- responder/explicit Memory AgentJob queueing, queued natural-language
  clarification selection, preference recognition and private capture-job
  enqueue;
- Note AgentJob queueing;
- Artifact AgentJob queueing;
- direct resource APIs for Memory, Notes, Continuity, Artifact feedback, and
  resource mutation surfaces;
- `ChatRequest`, historical `ChatTurnRequest` structured metadata,
  `ProposalTurnLease` propagation, frontend structured builders, legacy
  `TrustedMemoryService` branches, synchronous artifact executor cleanup,
  AgentJob retry/recovery/drainer work, and Note shutdown hygiene.

Remaining deferred work:

- frontend structured-chat builder retirement;
- inert turn-lease/effect plumbing cleanup outside this backend chat pass;
- legacy TrustedMemoryService lease branch review;
- synchronous artifact executor cleanup outside `_execute_chat`;
- AgentJob payload-preserving retry, retry dispatch, startup/runtime draining,
  expired running-lease recovery, terminal report/event consistency, hidden
  working-state durability, and Note shutdown hygiene.

## Inactive Frontend Structured-Chat Builder Cleanup

This uncommitted frontend-only cleanup pass removes stale request-builder
exports for structured `/api/chat` resource decisions after the active UI moved
those actions to direct resource APIs.

Removed:

- `buildMemoryDecisionChatRequest`;
- `buildMemoryClarificationSelectionChatRequest`;
- `buildCollaborativeNoteDecisionChatRequest`;
- `buildContinuitySelectionChatRequest`;
- `buildArtifactFeedbackChatRequest`;
- obsolete frontend request tests that only validated those retired chat
  builders.
- generic `buildChatRequest(...)` construction of retired structured resource
  fields and stale `/api/chat` endpoint selection for frontend resource actions.

Preserved:

- ordinary chat request construction, exact retry construction, and chat
  streaming helpers used by `frontend/app.mjs`;
- active direct resource APIs for Memory decisions, Memory clarification
  selections, Note decisions, Continuity selections, and Artifact feedback;
- frontend state/recovery compatibility fixtures that still handle historical
  structured request bodies without constructing new structured chat requests;
- backend `ChatRequest`, persisted `ChatTurnRequest` metadata,
  `ProposalTurnLease`, `_execute_chat`, supervisor/turn effect plumbing,
  `TrustedMemoryService`, artifact executor legacy execution, AgentJob
  recovery, and Note worker shutdown behavior.

Remaining deferred work:

- inert turn-lease/effect plumbing cleanup;
- legacy TrustedMemoryService lease branch review;
- synchronous artifact executor cleanup outside `_execute_chat`;
- AgentJob payload-preserving retry, retry dispatch, startup/runtime draining,
  expired running-lease recovery, terminal report/event consistency, hidden
  working-state durability, and Note shutdown hygiene.

## Live Orchestration Lease Cleanup

This uncommitted backend cleanup pass removes the remaining live chat
orchestration propagation of `ProposalTurnLease` after Memory, Note, Artifact,
preflight, and preference work moved to queue-owned or direct resource
lifecycles.

Removed:

- `AgentColTurnCommand.turn_lease`;
- `SupervisorTurnContext.turn_lease`;
- `_execute_chat` construction of `ProposalTurnLease` for ordinary
  conversational turns;
- turn-service forwarding of `command.turn_lease` into responder/supervisor
  contexts;
- tests whose only purpose was asserting that live turn orchestration propagated
  the chat lease into responder context.

Preserved:

- `ChatTurnClaim.owner_token` and chat-turn claim, renew, release, complete,
  replay, transcript, and message persistence;
- historical `ChatTurnRequest` structured metadata;
- `ChatTurnClaim.precompleted_*` historical/recovery fields and stored effect
  readers/assertions;
- deterministic Memory preflight queueing with `turn_lease=None`;
- preference capture queueing;
- Memory, Note, and Artifact AgentJob queueing and queue receipts returned from
  chat;
- direct resource APIs.

Intentionally deferred:

- `TrustedMemoryService` command `turn_lease` fields and lease-aware branches;
- `NaturalCollaborativeNoteCommand.turn_lease`;
- database optional `turn_lease` parameters and chat-turn effect
  writers/readers;
- synchronous artifact executor and artifact-feedback executor legacy effect
  behavior;
- AgentJob retry/recovery/drainer work and Note shutdown hygiene.

## Memory/Note Command Lease Cleanup

This uncommitted backend cleanup pass removes resource-command ownership of
`ProposalTurnLease` now that live chat orchestration, direct resource APIs, and
AgentJob workers no longer execute Memory/Note resource mutations under chat-turn
ownership.

Removed:

- `ProposeMemorySignalCommand.turn_lease`;
- `NaturalMemoryCommand.turn_lease`;
- `SelectMemoryClarificationCommand.turn_lease`;
- `NaturalCollaborativeNoteCommand.turn_lease`;
- production caller arguments that only supplied `turn_lease=None`;
- Memory and Note tool/job digest branches that could vary by command lease,
  while preserving the active no-lease digest/source-message behavior;
- tests and assertions whose only purpose was proving those commands received or
  forwarded a lease.

Preserved:

- direct Memory clarification selection through the Memory service;
- deterministic ambiguous-Memory preflight queueing;
- Memory and Note AgentJob payload restoration and execution;
- natural Memory and Note tool queue paths;
- current no-lease Memory proposal, Memory clarification, and Note proposal
  semantics;
- `ChatTurnClaim.owner_token`, historical `ChatTurnRequest` metadata,
  `ChatTurnClaim.precompleted_*`, and historical replay/effect readers.

Still deferred:

- database optional `turn_lease` parameters and chat-turn effect-writer branches;
- `record_chat_turn_decision_action`;
- `record_chat_turn_collaborative_note_decision_effect`;
- historical replay readers/assertions;
- synchronous artifact executor and artifact-feedback executor legacy effect
  behavior;
- AgentJob retry/recovery/drainer work and Note shutdown hygiene.

## Preference Confirmation Service Lease Cleanup

This backend cleanup pass removes the last `turn_lease` parameter from
`TrustedMemoryService.open_preference_hypothesis_confirmation(...)`. Preference
confirmation is now always Memory-owned job work: the worker restores the
persisted hypothesis payload, supplies the job `created_at` as
`confirmation_created_at`, and the service derives the clarification source
identity from `preference_hypothesis_confirmation_digest`.

Removed:

- `turn_lease` from `open_preference_hypothesis_confirmation(...)`;
- the `ProposalTurnLease` validation branch in that method;
- the lease-turn-id clarification identity branch;
- the Memory worker argument that only supplied `turn_lease=None`;
- tests and assertions that preserved the obsolete non-None service argument.

Preserved:

- deterministic preference-confirmation job id and idempotency key generation;
- private persisted hypothesis payload restoration;
- `confirmation_created_at`-based clarification creation and expiry;
- preference confirmation choices, governance, and pending-proposal behavior;
- at this checkpoint the database call still supplied `turn_lease=None`;
  the subsequent database writer cleanup below removes that argument.

Still deferred:

- database optional `turn_lease` parameters and chat-turn effect-writer branches;
- `record_chat_turn_decision_action`;
- `record_chat_turn_collaborative_note_decision_effect`;
- historical replay readers/assertions;
- synchronous artifact executor and artifact-feedback executor legacy effect
  behavior;
- AgentJob retry/recovery/drainer work and Note shutdown hygiene.

## Memory/Note Database Writer Cleanup

This pass removes database-side Memory/Note chat-turn effect writer capability
from checkpoint `7b139db27e6a17bcb7e8795b1af07a3338f525ed`. It supersedes the
earlier sections that defer these writers. Source search before editing found
no production caller supplying a non-None lease; after cleanup all nine
production calls omit the argument entirely.

Removed:

- `turn_lease` from `create_collaborative_note_proposal`,
  `create_memory_clarification`, `create_guarded_memory_proposal`,
  `create_guarded_memory_proposal_v2`, and
  `consume_memory_clarification_to_proposal_v2`;
- their optional chat-turn reads, ownership checks, effect validation, and
  effect writes, including clarification-consumption writer branches;
- `_collaborative_note_proposal_turn_effect_update`,
  `_memory_clarification_turn_effect_update`, and `_proposal_turn_effect_update`;
- `record_chat_turn_decision_action`,
  `record_chat_turn_collaborative_note_decision_effect`, and the now-unused
  `ChatTurnNoteDecisionEffectResult` return type;
- seven explicit `turn_lease=None` service call arguments, obsolete writer-only
  tests and fixtures, and assertions that service/worker calls forward None.

Preserved:

- existing no-lease resource transactions, provenance, ownership/governance,
  pending-proposal behavior, expiry, and resource idempotency;
- clarification consumption uses `source_message_id` as its consumption identity,
  exactly as the former no-lease branch did;
- direct Memory/Note APIs, preference confirmation, deterministic Memory
  preflight, natural tool queueing, and Memory/Note worker execution;
- real chat claim/renew/release/complete/replay and transcript persistence,
  historical structured request metadata, and `ChatTurnClaim.precompleted_*`;
- historical effect readers and completion validation; retained chat-turn tests
  are unchanged, including reclaim/recovery and persisted-effect replay tests;
- negative-call spies in `test_main.py` used to assert direct APIs and retired
  structured-input rejection never invoke the obsolete writers.

Verification:

- RED: `test_clarification_creation_rejects_turn_lease_argument` expected
  `TypeError`; the old API instead raised its lease-validation `ValueError`.
- `./venv/bin/python -m pytest tests/test_memory_clarification_database.py tests/test_memory_proposal_guard_database.py tests/test_collaborative_note_database.py -q`: 43 passed.
- `./venv/bin/python -m pytest tests/test_chat_turn_database.py -k 'claim or replay or precompleted or complete_chat_turn or release_chat_turn' -q`: 59 passed, 28 deselected.
- `./venv/bin/python -m pytest tests/test_trusted_memory_service.py tests/test_collaborative_note_service.py tests/test_memory_proposal_job_worker.py tests/test_collaborative_note_job_worker.py -q`: 44 passed.
- `./venv/bin/python -m pytest tests/test_main.py -k 'preflight or select_memory_clarification or approve_memory_proposal_uses_memory_api or reject_memory_proposal_uses_memory_api or direct_collaborative_note_decision' -q`: 10 passed, 285 deselected; one dependency `BaseAgentConfig` deprecation warning.
- `./venv/bin/python -m pytest tests/test_memory_proposal_tool.py tests/test_collaborative_note_tool.py -q`: 47 passed.
- `./venv/bin/python -m py_compile database.py trusted_memory_service.py collaborative_note_service.py` and `git diff --check`: passed.

Historical readers/assertions are compatibility requirements, not pending writer
deletions. Artifact execution/effect writers, artifact-feedback execution/effects,
AgentJob retry/recovery/drainer work, and Note shutdown hygiene remain deferred.
No backend schema migration or frontend change is included. Live Firestore and
browser acceptance were not performed for that pass. The reviewed Memory/Note
database writer cleanup was checkpointed as
`105dcc2bf74866f78fe247689b2635f971731657`.

## Artifact Chat-Turn Writer Cleanup

This pass removes the remaining artifact-side chat-turn writer capability from
checkpoint `105dcc2bf74866f78fe247689b2635f971731657`. It supersedes the earlier
sections that defer synchronous artifact executor cleanup and artifact-feedback
chat-owned effects.

Removed:

- `AgentColArtifactExecutor.execute()` and the synchronous blueprint/single-file
  generation helpers that wrote chat-turn artifact effects;
- the synchronous artifact responder projection/model-context helper used only by
  chat-owned execution;
- the chat-owned `AgentColArtifactFeedbackExecutor` module, its turn-service
  protocol/wiring/deadline path, and lifespan injection;
- database writers `record_chat_turn_blueprint_effect`,
  `record_chat_turn_single_file_artifact_effect`, and
  `record_chat_turn_artifact_feedback_effect`, plus their private writer result
  dataclasses;
- writer-only tests and the live smoke script that created new chat-turn artifact
  effects.

Preserved:

- `AgentColArtifactExecutor.queue()`, `AgentColArtifactCreationJobWorker`,
  `artifact_job_payload()`, `build_artifact_source_text()`, and queued artifact
  responder context;
- direct artifact creation/version APIs and direct artifact feedback
  API/service/database behavior;
- `ChatTurnRequest.artifact_feedback_decision` historical metadata,
  `ChatTurnClaim.precompleted_artifacts`, and
  `ChatTurnClaim.precompleted_artifact_feedback`;
- historical artifact/feedback replay, reclaim, release, validation, and
  completion-preservation readers/tests.

Verification:

- RED: `test_artifact_executor_exposes_queue_without_chat_owned_execute`
  expected `AgentColArtifactExecutor.execute` to be absent; it failed because the
  method still existed.
- RED: `test_turn_service_constructor_no_longer_accepts_chat_owned_feedback_executor`
  expected the turn service to reject the stale executor injection; it failed
  because the constructor still accepted it.
- RED: `test_memory_engine_no_longer_exposes_chat_owned_artifact_writers`
  expected the three DB writer methods to be absent; it failed because they still
  existed.
- Focused artifact executor/turn-service/database/direct-feedback checks passed
  after cleanup; final `py_compile` and `git diff --check` were run for the
  review report.

Historical artifact readers/assertions are compatibility requirements, not
pending writer deletions. AgentJob retry/recovery/drainer work, Note shutdown
hygiene, frontend behavior, and Memory/Note behavior remain intentionally out of
scope.

## ProposalTurnLease Symbol Hygiene And Decoupling Closure

This tiny cleanup removes the final unused `ProposalTurnLease` production symbol
after live orchestration, Memory/Note command plumbing, Memory/Note database
effect writers, preference-confirmation lease handling, artifact synchronous
execution, and artifact-feedback chat-owned execution were retired.

Removed:

- the unused `ProposalTurnLease` dataclass from `memory_proposals.py`;
- the private turn-id regex used only by that dead dataclass;
- the dedicated test that only validated `ProposalTurnLease` metadata.

Preserved:

- `ChatTurnClaim.owner_token`;
- chat claim/renew/release/complete/replay behavior;
- historical `ChatTurnRequest` structured metadata and `precompleted_*` fields;
- historical effect readers, validators, replay, reclaim, and completion
  preservation;
- active direct resource APIs and active AgentJob queue/worker paths;
- frontend compatibility checks for retired structured chat resource inputs.

Source audit now finds no production `ProposalTurnLease` usage, no
resource-side `turn_lease` capability, no resource-owned `record_chat_turn_*`
writers, no live structured `/api/chat` resource execution path, and no
synchronous chat-owned artifact or feedback executor path. The resource/chat
ownership decoupling cleanup boundary is closed. Remaining async work is
recovery/reliability work: AgentJob payload-preserving retry, retry dispatch,
startup/runtime draining, expired running-lease recovery, shutdown hygiene,
terminal event/report consistency, hidden working-state durability, stale
frontend compatibility cleanup, and stale documentation cleanup.

## AgentJob Retry Payload Preservation

This pass starts the recovery/reliability phase after resource/chat ownership
decoupling closure. The retry endpoint already derived deterministic retry job
IDs and preserved public retry lineage, but `AgentJobRepository.retry_job(...)`
created only the retry job document. It did not create the retry job's private
payload document, while Memory, Note, and Artifact workers all load private
payload by the queued job's own `job_id`.

Fixed:

- retry creation now reads and validates the failed source job's private
  `AgentJobPayload` before creating the retry job;
- retry creation writes a private payload document under the retry job id in the
  same transaction;
- the copied payload preserves the original accepted private evidence/content,
  source turn/message identity, original payload creation timestamp, user,
  project, workspace, session, and action kind; only `job_id` is changed so the
  existing worker payload loader can resolve the retry job;
- missing or corrupt source payloads fail closed instead of fabricating or
  re-extracting replacement data;
- idempotent retry replays still return the existing retry job only after the
  retry payload is present, scope-valid, and exactly equals the validated source
  payload copy with only `job_id` changed for the retry job.

Preserved:

- retry lineage and idempotency semantics: retry job id remains derived from
  user/workspace/source job/idempotency key, `retry_of_job_id` still points at
  the failed source job, and `attempt_count` still increments from the source;
- payload privacy: retry payloads remain in the same private payload
  subcollection and are not projected in public job responses;
- worker execution boundaries for Memory, Notes, and Artifacts.

Not included:

- retry dispatch after creating the retry job;
- startup/runtime queued-job draining;
- expired running-lease recovery;
- shutdown hygiene or terminal report consistency cleanup.

## AgentJob Retry Dispatch

This pass dispatches queued retry jobs after the retry endpoint successfully
creates or idempotently returns a retry job. It reuses the same startup-wired
worker dispatch functions as newly queued Memory, Note, and Artifact work.

Fixed:

- the retry endpoint now calls a retry dispatch helper only after
  `AgentJobRepository.retry_job(...)` succeeds;
- the helper routes queued retry jobs by `action_kind` to the existing Memory,
  Note, or Artifact worker dispatcher;
- successful retry dispatches are tracked in-process by retry `job_id` so a
  repeated idempotent retry request does not schedule duplicate concurrent work;
- if the dispatcher raises after the retry is durably queued, the endpoint still
  returns the queued retry job and leaves it recoverable.

Preserved:

- retry private-payload preservation and exact replay integrity;
- retry lineage and idempotency;
- original failed job immutability;
- worker-specific private payload loading;
- queue/worker boundaries.

Not included:

- general queued-job draining;
- expired running-lease recovery;
- retry dispatch recovery across process restart;
- shutdown hygiene or terminal report consistency cleanup.
