# Real Asynchronous Work Vision

Date: 2026-09-03

This document records the intended end state for Agent Col asynchronous work.
It exists because the decoupling effort has crossed multiple machines,
contexts, and implementation passes, and the goal needs to stay explicit:
Agent Col, background agents, durable resource surfaces, and the chat UI should
work together without blocking or owning each other's lifecycle.

## Core Goal

Agent Col should be an asynchronous collaborative workspace, not a single
chat-bound request pipeline that happens to show extra panels.

The target experience is:

- the user can send a chat message and Agent Col can respond;
- the user can create or approve a note while chat is still responding;
- a Memory Analyst can create a governed pending memory proposal while an
  Artifact Builder is generating an artifact;
- a Note Curator can start work without waiting for an artifact job to finish;
- the Agents panel shows authoritative job lifecycle state;
- the Notes, Memory, and Artifacts surfaces show authoritative durable resource
  state;
- chat remains useful for conversation and delegation, but does not become the
  source of truth for background job completion, failure, approval, or durable
  persistence.

The important design principle is separation of ownership. Agent Col may
recognize intent, ask clarifying questions, and delegate work. Background jobs
own execution. Durable resource systems own persisted notes, memories, and
artifacts. Public job reports own terminal job explanations.

## Intended Lifecycle

The intended lifecycle for durable work is:

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

Chat can acknowledge the queued receipt, but it should not report the final
result unless it has an authoritative completed receipt or report. A model
sentence is not proof that memory was saved, a note was proposed, or an artifact
was created.

## Work Types

The async architecture must treat these as separate work types:

- chat response work: conversational reasoning, questions, synthesis, and user
  collaboration;
- artifact work: generated project outputs, blueprints, revisions, and artifact
  lifecycle changes;
- workspace note work: proposed or approved workspace-scoped knowledge,
  decisions, requirements, constraints, and task state;
- governed memory work: user-level preferences, collaboration style, goals,
  interests, standing instructions, and allowed light identity details;
- continuity work: prior-context retrieval used to answer the current turn;
- approval work: user decisions on pending notes, memory proposals, artifact
  feedback, or other governed resources.

These work types may communicate through explicit, authoritative state, but
they should not block one another by sharing a single chat request lifecycle.

## Parallelism Requirement

One unambiguous user turn may legitimately contain independent supported work:

- one workspace-note proposal;
- one governed-memory proposal;
- one artifact request.

Those jobs should be accepted independently and allowed to run side by side.
Unsupported or model-routed parts of the message must not cause a supported
durable action to be lost.

The queue must also accept new work while existing work is running. If an
Artifact Builder job is active, a Note Curator job should still be able to
start. If a Memory Analyst job is active, chat should still respond and the user
should still be able to interact with the Notes, Memory, and Artifacts surfaces.

This is not a request for uncontrolled agent spawning. It is a request for
bounded asynchronous execution:

- deterministic acceptance only for supported durable action kinds;
- application-owned idempotency and ownership;
- worker-owned leases and retries;
- governed validation before persistence;
- public-safe job reports;
- independent UI surfaces that refresh from authoritative APIs.

## Current State

The system is moving in the right direction but is not fully asynchronous yet.

What exists now:

- AgentJob records provide a durable queue foundation for background work.
- The Agents panel gives a public view of queued, running, completed, and failed
  work.
- Job reports provide a public-safe place to explain terminal background
  outcomes.
- Workspace note proposals can be queued through Note Curator jobs.
- Memory proposal work can be queued through Memory Analyst jobs for explicit
  memory requests.
- Artifact creation has moved toward Artifact Builder jobs and public reports.
- Some direct resource actions, such as note approval and memory approval, use
  dedicated APIs instead of routing through chat.
- The system has begun suppressing duplicate queued memory work and preventing
  chat from claiming background completion without receipts.

What is still not fully right:

- Chat still has too much responsibility for narrating or reconciling background
  work outcomes.
- Some response text can still conflict with job reports or resource panels.
- Some durable work acceptance still depends on turn timing, continuity state,
  or responder behavior.
- Some UI refresh behavior still treats chat as if it owns the whole workspace
  surface.
- The left drawer, chat surface, memory surface, notes surface, and artifact
  viewer still need clearer independence from active chat streaming state.
- The queue and workers need stronger evidence that multiple independent
  background jobs can be accepted and run concurrently without one job blocking
  another.
- Memory proposal category-slot behavior can still make separate natural memory
  requests appear coupled when they collide in the governed proposal store.

## Desired UI Decoupling

The UI should not behave as though the chat panel owns the workspace.

The target UI behavior is:

- chat streaming updates only the chat surface and any explicitly relevant chat
  state;
- the left drawer can refresh notes, memory, artifacts, chats, workspaces, and
  agent jobs without waiting for chat completion;
- the artifact viewer can refresh or inspect artifacts independently of the chat
  request lifecycle;
- direct UI actions, such as creating a note, approving a note, approving
  memory, or inspecting job reports, should remain available while chat is
  responding;
- resource panels should consume their own authoritative APIs and event streams
  rather than depending on a whole-workspace refresh after chat;
- cross-surface communication should happen through explicit resource IDs,
  public receipts, reports, and event streams, not through implicit chat state.

The surfaces should remain coordinated. They should not be isolated silos. The
important change is that coordination must be explicit and state-driven, not a
side effect of the chat request finishing.

## Desired Backend Decoupling

The backend should separate chat orchestration from durable execution.

The target backend behavior is:

- Agent Col accepts or delegates supported durable work quickly;
- each accepted durable action gets its own idempotent job;
- each job has one owner, one worker lifecycle, and one terminal report;
- workers can lease different jobs concurrently when their action kinds and
  resources do not conflict;
- resource-specific persistence remains governed by its own service;
- job failure does not fail the chat response;
- chat failure does not cancel already accepted background jobs;
- retries use job and source-turn idempotency rather than model memory or
  repeated tool calls;
- background workers expose public progress through jobs and reports, not chat
  narration.

This means Agent Col should not be the component that reports final memory,
note, or artifact creation. It may point the user to the relevant panel or
report, but the authoritative result belongs to the job/report/resource system.

## Invariants

The following invariants should guide future implementation passes:

- Durable state changes require application-owned authorization.
- Memory remains governed and approval-gated.
- Workspace notes remain workspace-scoped and approval-gated unless created by
  an explicit direct UI flow with the existing contract.
- Artifacts remain durable resources with their own lifecycle.
- Agent jobs own background execution status.
- Job reports own public-safe terminal explanations.
- Chat must not invent or finalize background outcomes.
- A queued receipt is not a completed result.
- A completed resource receipt is stronger than model-authored text.
- Independent supported work in the same turn should be accepted independently.
- Unsupported work must not erase supported queued work.
- UI surfaces should stay interactive while unrelated work is running.
- Idempotency, ownership, leases, and worker boundaries must not be weakened to
  get apparent parallelism.

## Near-Term Direction

The next work should be organized around lifecycle audits and narrow decoupling
passes:

1. Audit every path where chat still creates, reports, retries, or finalizes
   durable work.
2. Audit every UI path that blocks resource actions or resource refreshes on
   active chat state.
3. Identify every background task or agent-like operation that is not yet behind
   AgentJob lifecycle reporting.
4. Move remaining durable side effects behind queue-first or direct resource
   APIs, depending on whether they are agent work or user-owned direct actions.
5. Ensure note, memory, and artifact workers can process independent jobs
   concurrently.
6. Ensure chat can continue while jobs are queued, running, completing, failing,
   or awaiting user approval.
7. Tighten response sanitization so chat cannot contradict authoritative job or
   resource state.
8. Revisit governed memory proposal slot behavior after the async ownership
   boundary is stable.

## Definition Of Success

The async work is successful when this scenario works naturally:

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

That is the intended direction: dynamic, governed, observable asynchronous work
with Agent Col as a collaborator and orchestrator, not a bottleneck.
