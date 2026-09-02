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
