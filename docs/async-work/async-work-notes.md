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
