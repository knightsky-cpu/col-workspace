# Agent Col Agent Jobs And Subagent Orchestration Design

Last updated: September 1, 2026.

## Purpose

Agent Col needs to handle multi-step work without forcing every durable effect
through one chat-turn completion path. The system should keep the main chat
interactive while background work progresses, expose that work in a clear
Agents panel, and preserve application-owned authority over identity, scope,
approval, persistence, retries, and final writes.

The design direction is agent-first orchestration with minimal deterministic
application logic. Application code should not try to predict complex model
behavior. It should own stable contracts, policy gates, lifecycle transitions,
idempotency, persistence, and public projections. Subagents should perform
model-backed work where generation, retrieval, synthesis, or multi-step
reasoning is needed.

## Current Boundary

Current chat execution is request-bound. `/api/chat` and `/api/chat/stream`
resolve identity and workspace scope, claim or replay the chat turn, route the
request, run specialist or responder work, persist the canonical response and
effects, and return the authoritative chat response.

That shape is fragile for requests that naturally include multiple durable
effects, such as artifact creation plus note proposal plus memory proposal.
One chat turn should not directly own multiple competing durable effects. It
should own the user's message, the assistant response, and durable receipts for
work that was accepted into an agent-job pipeline.

## Target Shape

```text
User prompt
-> chat identity and workspace resolution
-> continuity/context resolution
-> Agent Col planning and policy validation
-> one or more durable AgentJob records
-> ChatResponse.queued_actions receipts
-> independent subagent/job execution streams
-> application-owned final writes and approval gates
-> frontend Agents panel status projection
```

The chat stream remains the conversation stream. Agent-job status and event
streams are separate orchestration surfaces.

## Authority Split

Application-owned deterministic responsibilities:

- authenticate and authorize user, workspace, project, and session scope;
- validate public request and response schemas;
- assign durable job IDs and idempotency keys;
- enforce lifecycle transitions and terminal immutability;
- lease jobs and fence stale or duplicate execution attempts;
- persist job records and public job events;
- call existing authoritative services for final writes;
- preserve governed memory and collaborative-note approval gates;
- project only user-safe public status, labels, and result references.

Subagent-backed responsibilities:

- perform artifact creation or revision work;
- perform research/source/computation style multi-step analysis when routed;
- prepare collaborative-note proposal content;
- prepare governed-memory proposal candidates;
- retrieve or summarize prior chat/workspace context within bounded inputs;
- report public-safe progress events through the job event contract.

The application should keep deterministic interpretation narrow. If the output
model is not stable, the app should not infer complex intent by ad hoc rules;
it should ask the model/router for a structured plan and then validate that
plan against policy.

## Public Lifecycle

All public job projections use the same lifecycle vocabulary:

```text
queued
running
completed
failed
cancelled
```

Internal worker states may be richer later, but they must project into this
public lifecycle.

## Data Model

`AgentJob` is the durable work record.

Required fields:

- `job_id`
- `user_id`
- `project_id`
- `workspace_id`
- `session_id`
- `source_turn_id`
- `source_message_id`
- `action_kind`
- `status`
- `display_label`
- `agent_label`
- `created_at`
- `updated_at`
- `idempotency_key`
- `attempt_count`
- `lease_owner`
- `lease_expires_at`
- `result_refs`
- `failure_summary`

`AgentJobEvent` is the public-safe event stream record.

Required fields:

- `event_id`
- `job_id`
- `event_type`
- `message`
- `created_at`
- `status`
- `public_visibility`
- `metadata`

Events must not contain internal prompts, model reasoning, raw agent IDs,
credentials, service-account data, private tool payloads, or raw provider
errors.

## API Surface

The planned API surface is agent-oriented rather than generic task-oriented:

```text
GET  /api/agent/jobs
GET  /api/agent/jobs/{job_id}
GET  /api/agent/jobs/{job_id}/events
POST /api/agent/jobs/{job_id}/cancel
POST /api/agent/jobs/{job_id}/retry
```

The list endpoint should accept effective project/session filters through the
same ownership resolution rules used by existing project and chat-session
routes. The first implementation should support polling. A streaming job event
endpoint can be added after the repository and panel contracts are stable.

## Chat Integration

`ChatResponse.queued_actions` is the chat receipt contract. It tells the user
that Agent Col accepted work into the orchestration system. It is not the job
record itself.

For a multi-action request, the eventual desired behavior is:

```text
Create a bash script artifact and save a workspace note that it must stay
Bash-only.
```

The chat response may include:

```text
queued_action: Artifact Agent / Create repo_helper.sh / queued
queued_action: Notes Agent / Propose Bash-only workspace constraint / queued
```

The artifact and note proposal are later delivered through their existing
authoritative surfaces after the corresponding jobs complete.

## Approval Behavior

Approval is application-owned and user-owned. A subagent may prepare a memory
proposal or note proposal, but the application decides whether the output is a
valid pending proposal, and the user decides whether to approve it.

Approving a pending note or memory proposal should not require blocking the
main chat pipeline. Structured approval turns should eventually be processed
as independent authoritative application actions, with their own idempotency
and job/event updates where needed.

## Agents Panel UI Concept

The left drawer should include a collapsible `Agents` card below `Chats`.
The panel is a read-only projection of backend orchestration state, not a
parallel frontend state machine.

Active Agents:

- show currently running subagents;
- order by spawn or start time;
- display a status indicator, agent/task type, public-safe task description,
  and optional elapsed/start time;
- use green for running and red for failed/stopped;
- never expose internal prompts, reasoning, raw IDs, credentials, or tool
  payloads.

Task Queue:

- show durable queued tasks waiting to execute;
- display task/action type, short display label, and queue status;
- preserve backend-authoritative ordering.

Completed Tasks:

- show completed, failed, and cancelled background tasks for the current chat
  session only;
- keep this compact and text/list based;
- display terminal status, task type, result description, and optional
  completion time.

Collapsed Summary:

- the collapsed card should show counts such as
  `Agents - 2 active · 3 queued`;
- counts come from the public backend projection.

Future controls:

- cancel and retry can be added later if supported by the job lifecycle;
- controls must call backend action routes and must not mutate frontend state
  optimistically beyond pending UI affordances.

## Failure Handling

Failures should be explicit and inspectable:

- chat failures should not erase queued job receipts already persisted;
- job failures should preserve public-safe failure summaries and internal logs;
- retry should create or link a new attempt without duplicating completed
  outputs;
- cancellation should be fenced so a running worker cannot complete a job after
  cancellation without passing lifecycle checks.

## Sequencing

1. Implement the receipt contract. This is already complete as of commit
   `10bbb2f`.
2. Define `AgentJob` and `AgentJobEvent` domain models.
3. Add the Firestore-backed job repository and lifecycle fencing.
4. Add `/api/agent/jobs` status and event APIs.
5. Add the read-only Agents panel.
6. Add one local subagent-backed executor.
7. Route multi-action chat requests into durable jobs.
8. Add cancel/retry controls after lifecycle behavior is proven.

## Non-Goals For The First Execution Slices

- No Cloud Tasks dependency in the first local implementation slice.
- No open-ended deterministic intent parser.
- No direct frontend mutation of job lifecycle state.
- No raw model reasoning or private prompt display.
- No bypass of governed memory or collaborative-note proposal approval.
- No pollution of `/api/chat/stream` with background job events.
