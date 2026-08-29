# Next Session Finalization Handoff

Last updated: August 28, 2026.

## Purpose

This document is an explicit handoff for the next Agent Col work session. It
maps the current documentation set and gives the next agent precise
instructions for aligning itself with the repository, the current finalization
strategy, the remaining tasks, and their significance to the All Things
Agentic Hackathon Collaborative Partner submission.

The next session must review this handoff and all referenced current
documentation before proposing or performing work.

## Required Next-Session Instructions

The next agent must:

1. Read `AGENTS.md` first and follow its approval-gated workflow.
2. Read this handoff document completely.
3. Read every document listed under "Current Authority Documents".
4. Read every document listed under "Implementation Planning Documents".
5. Skim every document listed under "Superseded Or Historical Context" only to
   understand what is no longer current authority.
6. Inspect the source files named by the Target A/B implementation plan before
   making source-backed claims about implementation seams.
7. Report to the user its comprehensive understanding of:
   - Agent Col's current product identity;
   - implemented source capabilities;
   - remaining work;
   - why Target A and Target B matter;
   - why production hardening matters;
   - why visual polish is separate and controlled;
   - why deferred async/Cloud Tasks work is not a pre-submission blocker;
   - how the current roadmap supports the Collaborative Partner hackathon
     track and judging rubric.
8. Do not implement source changes from this handoff alone.
9. Do not treat old Winning Core phase ordering as current finalization
   authority.
10. After reporting understanding, await explicit user instructions.

## Current Authority Documents

These documents define the current project state and strategic direction.

- `README.md`
  - Public-facing project overview, current status, implemented features,
    local setup, local auth startup commands, tests, and deferred work.
  - Important startup commands:

```bash
AGENT_COL_AUTH_MODE=local_dev venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- `docs/current-state.md`
  - Canonical source-level status summary.
  - Treat this as the main authority for implemented features and current
    gaps unless source code proves otherwise.
  - Key current-state claims:
    - browser workspace at `/workspace`;
    - local and Google OIDC auth foundation;
    - persisted chat sessions and retry-safe chat turns;
    - governed profile memory;
    - governed workspace notes and continuity;
    - hidden same-session working state;
    - four bounded specialist capabilities: Research, Source, Computation,
      Requirements Verification;
    - synchronous request-bound synthesis and artifacts;
    - production hardening still pending;
    - Target A and Target B still pending;
    - durable async artifacts, Cloud Tasks, and private worker are deferred.

- `docs/final-checklist-planning.md`
  - Current strategic finalization reference.
  - Supersedes the old Winning Core execution order for pre-submission work.
  - Establishes the current closing strategy:

```text
reconcile roadmap
-> Target A
-> Target B
-> production hardening
-> Cloud Run proof
-> controlled frontend visual polish
-> documentation and evidence package
-> architecture diagram
-> four-minute demo
-> submission verification
-> freeze
```

- `docs/architecture.md`
  - Current architecture overview.
  - Review especially the responder-only Agent Col boundary, server-side
    routing/expert execution, Firestore authority, governed memory, notes,
    working state, and artifact flow.

- `docs/submission-checklist.md`
  - Current submission checklist after roadmap reconciliation.
  - Should now be interpreted around the Collaborative Partner story and
    single-service deployment proof, not old async job-state proof.

- `docs/development/local-setup.md`
  - Developer setup reference.
  - Confirms the correct auth mode spelling is `google_oidc`, not
    `google_iodc`.

## Implementation Planning Documents

These documents are current planning references. They do not authorize source
changes by themselves.

- `docs/superpowers/plans/2026-08-28-target-a-b-collaborative-partner-implementation.md`
  - Pending implementation plan for the two remaining Collaborative Partner
    product targets.
  - Must be treated as pending source-backed validation and user approval.
  - Target A:

```text
observation/correction evidence
-> non-authoritative preference hypothesis
-> user confirmation
-> existing governed memory proposal/approval lifecycle
-> later adaptation
```

  - Target A deliberately revises the old M9 no-behavioral-inference
    boundary while preserving the higher-level memory governance rule:

```text
observation evidence != preference hypothesis != candidate memory != active memory
```

  - Target B:

```text
use existing working-state understanding to make Agent Col more visibly lead
the collaboration
```

  - Target B must not introduce a generalized planner.

- `docs/superpowers/plans/2026-08-27-contest-finalization-production-hardening.md`
  - Pending single-service production hardening plan.
  - Salvages the useful Phase 4 web-service hardening work while removing the
    old dependency on Phase 3 Cloud Tasks/private-worker execution.
  - Key targets: fail-closed production config, required Google OIDC in
    production, opaque identity, ownership hardening, body limits, rate
    limits, security headers, privacy-safe logs, deletion/retention,
    Dockerfile, `.dockerignore`, Cloud Run config, and hosted smoke/security
    verification.

- `docs/superpowers/plans/2026-08-27-contest-finalization-documentation-sanitization.md`
  - Documentation cleanup plan that reconciled old roadmap docs with the new
    finalization strategy.
  - Useful for understanding which documents were intentionally revised.

- `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md`
  - Safe visual-only frontend guide.
  - Governs the later visual polish phase.
  - Default scope is CSS-only changes in `frontend/styles.css` for appearance,
    readability, spacing, hierarchy, visual coherence, and judge
    comprehension.
  - It explicitly excludes behavior changes, JavaScript state changes,
    backend routes, prompts, auth, persistence, memory, notes, artifacts, and
    working-state behavior unless separately approved.

## Superseded Or Historical Context

These documents are still useful provenance, but they must not override the
current finalization strategy.

- `docs/aug-25-2026-final-checklist.md`
  - Historical Winning Core checklist.
  - Now marked as superseded for pre-submission sequencing.
  - Durable async/Cloud Tasks/private-worker work is no longer a
    pre-submission prerequisite.

- `docs/superpowers/plans/2026-08-25-winning-core-phase-3-async-artifact-work.md`
  - Historical/deferred Phase 3 durable async artifact plan.
  - Useful future engineering reference only.

- `docs/superpowers/plans/2026-08-25-winning-core-phase-4-production-deployment.md`
  - Historical Phase 4 plan.
  - Preserve single-service hardening ideas, but do not preserve its old
    dependency on Phase 3 Cloud Tasks/private worker.

- `docs/research/2026-08-25-phase-3-durable-artifact-cloud-tasks-audit.md`
  - Historical audit for deferred async artifact work.

- `docs/research/2026-08-25-phase-4-production-hardening-deployment-audit.md`
  - Historical production-hardening audit.
  - Use as supporting context for hardening, not as current execution order.

- `docs/frontend-notes.md`
  - UX history and backlog context.
  - Do not treat old gap statements inside it as current implementation
    authority without source verification.

- `docs/legacy/`
  - Legacy planning and provenance.
  - Only use for context when current documents or source code point there.

## Source Surfaces To Inspect For Current Understanding

The next session should inspect these source files before making source-backed
claims or implementation recommendations:

- `main.py`
- `agent_col_responder.py`
- `agent_col_expert_executor_v3.py`
- `agent_col_responder_context_v3.py`
- `memory_policy.py`
- `memory_candidate_decisions.py`
- `memory_clarifications.py`
- `memory_proposals.py`
- `memory_context.py`
- `trusted_memory_service.py`
- `collaborative_note_service.py`
- `working_state.py`
- `working_state_service.py`
- `database.py`
- `schemas.py`
- `frontend/index.html`
- `frontend/styles.css`
- `frontend/*.mjs`
- relevant tests under `tests/` and `tests/frontend/`

Recommended source searches:

```bash
rg -n "Source|Research|Computation|Requirements Verification|capabilities|tool belt" \
  agent_col_expert_executor_v3.py main.py agent_col_responder.py tests docs

rg -n "infer preferences|autonomous background|Do not infer memory|MemoryContextRenderer|propose_memory_signal|memory_decision|MemoryClarification" \
  AGENT_COL_IDENTITY_AND_ALIGNMENT.md docs memory_*.py trusted_memory_service.py memory_context.py main.py tests frontend

rg -n "working_state|SERVER_VALIDATED_WORKING_STATE|next_step_hypothesis|current_goal|unresolved_questions" \
  working_state.py working_state_service.py agent_col_responder.py main.py tests docs
```

## Current Project Understanding To Report

The next session's first substantive response should report the following:

- Agent Col is a persistent Collaborative Partner for the All Things Agentic
  Hackathon, not merely a coding assistant or artifact generator.
- The core app is request-bound and accepted for its current implemented
  collaboration surfaces.
- Memory, notes, continuity, working state, specialist tools, and artifacts
  are separate governed surfaces with different authority levels.
- The responder itself does not have Research, Source, Computation, or
  Requirements Verification as model-visible tools. Routing selects at most
  one server-side expert, the executor runs it, then validated context and
  receipts are passed to the responder.
- The current expert tool belt exposes four bounded capabilities in stable
  order when configured: Source, Research, Computation, and Requirements
  Verification.
- Requirements Verification and Research preserve content-safe invalid-output
  reasons; Source and Computation fail safely but are less uniform here.
- Target A matters because the Collaborative Partner track rewards continuing
  adaptation to the user's way of thinking. The implementation must revise the
  old M9 no-behavioral-inference contract without allowing silent profiling or
  unapproved memory.
- Target B matters because the track explicitly asks for an agent that "leads
  the way." Existing working state already contains the right same-session
  information; the remaining work is to consume it more visibly and usefully,
  not to build a planner.
- Production hardening matters because Demo and Production Readiness are part
  of judging and because the current local-dev defaults are not safe public
  deployment posture.
- Visual polish matters only as a judge-facing comprehension pass after
  functional freeze, and must follow the safe visual-only guide.
- Cloud Tasks/private-worker async artifact work is deferred until after
  submission and is not evidence that the current accepted collaboration
  features are unreliable.

## Hackathon Significance

The current roadmap is aligned to the Collaborative Partner contest story:

```text
messy user work
-> clarification and guidance
-> bounded specialist help or artifact synthesis
-> governed notes and continuity
-> correction/feedback
-> evidence-governed preference hypothesis
-> user-confirmed memory
-> later-session adaptation
-> Agent Col recommends the next useful step
-> Cloud Run proof and concise demo evidence
```

This supports the judging categories:

- Innovation and Operational Utility:
  - persistent collaboration;
  - governed adaptation;
  - notes and continuity;
  - bounded specialist work;
  - synthesis and artifacts.
- Architectural Discipline and Tech Stack:
  - Gemini through Vertex AI;
  - Google ADK;
  - Firestore;
  - planned Cloud Run;
  - deterministic application authority over model outputs.
- Demo and Production Readiness:
  - hosted Cloud Run proof;
  - reproducible README;
  - architecture diagram;
  - public four-minute video;
  - visible Firestore/Cloud evidence.

## Stop Condition

After reviewing the mapped documents and source surfaces, the next session
should report its comprehensive understanding to the user and await further
instructions. This handoff does not grant approval to implement Target A,
Target B, production hardening, visual polish, or deployment.
