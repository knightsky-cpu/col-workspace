# Updated Finalization Handoff

Last updated: August 28, 2026.

## Purpose

This handoff supersedes `docs/superpowers/plans/2026-08-28-next-session-finalization-handoff.md` for next-session alignment. It reflects the current repository state after Target A, Target B, production hardening checklist creation, Cloud Run deployment planning, chat response streaming planning, and the revised frontend visual improvement plan.

The next agent must read this handoff before proposing or performing work. This document does not authorize source changes by itself.

## Required Reading Order

1. `AGENTS.md`
   - Binding repository workflow.
   - Source changes require investigation, bounded plan, explicit approval, TDD, focused verification, manual verification, and then checkpoint approval.
   - GitHub checkpoints go directly to `origin/main` with explicit path staging when requested.

2. `docs/superpowers/plans/2026-08-28-updated-finalization-handoff.md`
   - This document.
   - Use it as the current handoff entrypoint.

3. `PRODUCTION_HARDENING_CHECKLIST.md`
   - Root-level deployment hardening checklist.
   - It records that Target A and Target B are demo-ready and that current priority is single-service production hardening, Cloud Run deployment proof, and targeted latency measurement.
   - It points to the Cloud Run implementation plan so future agents do not reinvent deployment planning.

4. `docs/superpowers/plans/2026-08-28-cloud-run-production-hardening-deployment.md`
   - Current source-backed and official-doc-backed Cloud Run production hardening implementation plan.
   - Use before any Cloud Run, Docker, production configuration, security header, ownership, logging, request-limit, rate-limit, hosted smoke, or latency measurement work.

5. `docs/superpowers/plans/2026-08-28-target-a-b-findings-and-reliability-testing.md`
   - Current Target A/B implementation findings.
   - Treat this as newer than `README.md`, `docs/current-state.md`, and the older next-session handoff for Target A/B status.

6. `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md`
   - Governs frontend appearance-only work.
   - CSS-only changes in `frontend/styles.css` are the default safe visual path.
   - HTML, JavaScript, backend, prompts, auth, persistence, memory, notes, artifacts, and working state are locked for visual-only work.

7. `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md`
   - Current visual improvement plan.
   - It explicitly uses root-level `agent-col-visual-target.jpeg` as the visual benchmark.
   - It contains official CSS, WCAG, Google Identity, FastAPI, and Starlette documentation evidence.
   - It identifies safe and unsafe files, conceptual CSS snippets, source snippets, expected touched files, verification commands, and manual visual checks.

8. `agent-col-visual-target.jpeg`
   - Root-level visual reference image.
   - Use it as the explicit visual quality bar for the frontend polish phase.

9. `docs/superpowers/plans/2026-08-28-chat-response-streaming-plan.md`
   - Current behavior-change plan for true progressive assistant response streaming.
   - This is not a safe CSS-only visual pass.
   - It requires backend streaming, frontend request/rendering changes, TDD, Cloud Run streaming verification, and preservation of final response semantics.

10. `docs/final-checklist-planning.md`
    - Strategic finalization reference for the hackathon submission.
    - Older durable async work remains deferred unless the user reopens it.

11. `docs/current-state.md` and `README.md`
    - Useful architecture and setup references, but now partially stale on Target A/B status.
    - Update only after the user explicitly authorizes a documentation convergence pass.

12. `docs/architecture.md`, `docs/submission-checklist.md`, `docs/development/local-setup.md`, and `docs/development/testing.md`
    - Use for architecture, submission, setup, and verification context.

## Current Repository State

Current recent checkpoint sequence:

```text
8dce526 docs: revise frontend visual improvement plan
d2d4e95 docs: add chat response streaming plan
932ad1e Add frontend visual improvement plan
336cb4e Add Cloud Run hardening deployment plan
e2b456f Add production hardening checklist
0db3d0e Implement Target B visible working-state leadership
753eaa5 Implement Target A preference learning
fff4232 Add Target A and B implementation plans
```

At the time this handoff was created, the worktree was clean before the new handoff file was added.

Important status correction:

- `README.md` and `docs/current-state.md` still list Target A and Target B as planned.
- Newer evidence shows Target A and Target B have been implemented and manually exercised:
  - `753eaa5 Implement Target A preference learning`
  - `0db3d0e Implement Target B visible working-state leadership`
  - `docs/superpowers/plans/2026-08-28-target-a-b-findings-and-reliability-testing.md`
- Target A/B are considered tested enough end to end for the project demo, but the findings document still recommends broader consistency and reliability testing across more topics and conversation shapes.

## Current Product Understanding

Agent Col is a persistent Collaborative Partner for the All Things Agentic Hackathon. It is not only a coding assistant, planner, blueprint generator, or document tool.

Current accepted product story:

```text
messy user work
-> clarification and guided collaboration
-> bounded specialist help or artifact synthesis
-> governed notes and continuity
-> correction and feedback
-> evidence-governed preference hypothesis
-> user-confirmed memory
-> later-session adaptation
-> Agent Col recommends the next useful step
-> Cloud Run proof and demo evidence
```

Implemented source capabilities include:

- browser workspace at `/workspace`;
- local development auth and Google OIDC foundation;
- persisted chat sessions and retry-safe chat turns;
- governed profile memory;
- governed workspace notes and continuity receipts;
- hidden same-session working state;
- four bounded specialist capabilities: Research, Source, Computation, and Requirements Verification;
- synchronous request-bound synthesis and artifacts;
- artifact lifecycle, versioning, feedback, archive, and restore surfaces;
- Target A preference learning confirmation loop;
- Target B visible agent leadership from working state.

Still pending:

- production configuration gate;
- opaque production identity and ownership hardening;
- request limits, rate limits, and browser security headers;
- privacy-safe production logging;
- retention/deletion documentation;
- Dockerfile and `.dockerignore`;
- Cloud Run deployment;
- hosted smoke/security proof;
- content-safe latency measurement;
- frontend visual polish against `agent-col-visual-target.jpeg`;
- optional later chat response streaming behavior pass;
- final documentation/evidence package, architecture diagram, demo video, and submission freeze.

Deferred from pre-submission scope:

- Cloud Tasks;
- private worker;
- durable asynchronous artifact jobs;
- generalized planner;
- worker IAM, queue auth, durable job retry/cancel proof.

## Current Plan Map

### Production Hardening

Use `PRODUCTION_HARDENING_CHECKLIST.md` as the root-level checklist and `docs/superpowers/plans/2026-08-28-cloud-run-production-hardening-deployment.md` as the implementation plan.

The recommended first production pass is the production configuration gate:

```text
fail closed in production
-> require AGENT_COL_AUTH_MODE=google_oidc
-> reject local_dev in production
-> preserve local_dev locally
```

Do not begin Cloud Run implementation from older Phase 4 docs alone. The current plan deliberately preserves single-service hardening ideas while dropping the old dependency on Cloud Tasks/private worker work.

### Target A And Target B

Use `docs/superpowers/plans/2026-08-28-target-a-b-findings-and-reliability-testing.md`.

Target A implemented:

```text
repeated correction evidence
-> non-authoritative preference hypothesis
-> user confirmation
-> existing governed memory proposal path
-> explicit approval before active memory
```

Target B implemented:

```text
hidden same-session working state
-> action-oriented next_step_hypothesis
-> visible recommendation or continuation when already authorized
```

Preserve this authority distinction:

```text
observation evidence != preference hypothesis != candidate memory != active memory
```

Working state remains hidden, same-session scoped, non-authoritative, and unable to authorize tools, persistence, memory, notes, artifacts, identity changes, or actions.

### Frontend Visual Work

Use the safe visual guide and the revised visual improvement plan together:

- `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md`
- `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md`
- `agent-col-visual-target.jpeg`

Current visual pass boundary:

```text
frontend/styles.css only by default
same HTML hooks
same JavaScript behavior
same backend routes
same requests and responses
same model output
same receipts and artifacts
same notes, memory, working-state behavior
```

The visual target is explicit:

- dark app shell;
- near-black blue/green surfaces;
- restrained teal primary accent;
- amber secondary accents;
- subtle borders;
- 8px-or-less radius;
- dense professional workspace;
- polished top bar, drawers, chat surface, composer, and artifact panel.

Do not treat the visual plan as approval to change streaming, chat request flow, prompt behavior, response text, artifact content, or renderer logic.

### Chat Response Streaming

Use `docs/superpowers/plans/2026-08-28-chat-response-streaming-plan.md`.

The user's target is true progressive assistant output while the model generates, not a fake delayed line-by-line reveal after the complete response is already available.

This is a separate behavior-changing pass. It is not authorized by the safe visual guide or frontend visual plan. It touches backend streaming, frontend API/state/rendering, tests, and Cloud Run streaming verification.

Preserve:

- existing `/api/chat` JSON behavior as fallback;
- same final model response;
- same prompts and model behavior;
- same receipts, artifacts, memory, notes, continuity, retry semantics, and persistence;
- no raw ADK/tool/internal events in the browser stream.

## Source Surfaces To Inspect Before Source-Backed Claims

For production hardening and Cloud Run:

- `auth.py`
- `main.py`
- `database.py`
- `vertex_config.py`
- `generic_artifact_service.py`
- `requirements.txt`
- `tests/test_auth.py`
- `tests/test_main.py`
- relevant database and API tests

For frontend visual polish:

- `frontend/styles.css`
- `frontend/index.html`
- `frontend/app.mjs`
- `frontend/chat-view.mjs`
- `frontend/work-view.mjs`
- `tests/frontend/workspace-static.test.mjs`
- `tests/frontend/chat-view.test.mjs`
- `tests/test_workspace_static.py`

For streaming:

- `main.py`
- `schemas.py`
- `agent_col_turn_service.py`
- `supervisor_runtime.py`
- `frontend/api.mjs`
- `frontend/app.mjs`
- `frontend/state.mjs`
- `frontend/chat-view.mjs`
- relevant frontend/backend chat tests

For Target A/B reliability:

- `agent_col_responder.py`
- `agent_col_responder_context_v3.py`
- `working_state.py`
- `working_state_service.py`
- memory policy, candidate, clarification, proposal, and context modules
- Target A/B tests added in the implementation commits

## Recommended Next Work Sequence

1. Production configuration gate.
2. Opaque identity and ownership hardening.
3. Request limits, rate limits, and security headers.
4. Privacy-safe logging.
5. Container and Cloud Run configuration.
6. Hosted smoke and security proof.
7. Latency measurement before optimization.
8. Frontend visual polish against `agent-col-visual-target.jpeg`.
9. Optional chat response streaming behavior pass.
10. Documentation/evidence convergence, architecture diagram, demo video, submission freeze.

The user may change this order. Current user priority has been production hardening and Cloud Run deployment, with latency measurement and frontend polish also important.

## Required Next-Agent Report

After reading the required documents and inspecting relevant source for the requested next task, report:

- Agent Col's current product identity;
- current implemented capabilities;
- the stale-vs-current Target A/B documentation correction;
- why production hardening and Cloud Run are now the main deployment focus;
- why frontend visual work must align with `agent-col-visual-target.jpeg`;
- why safe visual work is CSS-only by default;
- why streaming is a separate behavior-changing pass;
- which exact plan controls the next requested work;
- which files are expected to be touched and which are locked;
- focused verification and manual checks appropriate to the next pass.

## Stop Condition

After using this handoff for alignment, do not implement source changes unless the user has explicitly authorized a bounded implementation pass under `AGENTS.md`.

Documentation-only updates may be made and checkpointed when the user explicitly requests them, as with this handoff.
