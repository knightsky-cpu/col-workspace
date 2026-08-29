# Agent Col Architecture

Last reconciled: August 29, 2026.

This document describes how the current application is built and how its parts
interact. Source code, tests, and the root-level `repo-map.md` are the authority
for these claims; historical files under `docs/legacy/` are provenance only.

## System Shape

Agent Col is a FastAPI backend with a same-origin static browser workspace. The
backend owns authentication, workspace ownership, Firestore persistence,
chat-turn idempotency, routing, expert execution, responder generation, memory,
collaborative notes, continuity, hidden working state, preference learning, and
artifacts (`main.py:1280-1417`, `repo-map.md`).

The browser workspace is served at `GET /workspace`; static frontend modules are
mounted under `/static/agent-col` (`main.py:1403-1417`). The browser does not
call Firestore or Vertex AI directly. It uses same-origin JSON APIs through the
central frontend API helper (`frontend/api.mjs:13-119`).

## Backend Composition

`main.py` is the HTTP and dependency-injection composition root. Its lifespan
function creates the Vertex/Gemini client, Firestore `MemoryEngine`, synthesis
and artifact services, memory/note/continuity/working-state/preference
services, specialist services, the v3 expert executor, responder runtime, and
`AgentColTurnService` (`main.py:1280-1400`).

The primary runtime path is `POST /api/chat`. Other routes expose auth/session
state, workspace management, memory inspection/mutation, collaborative notes,
chat sessions, synthesis blueprints, generic artifacts, and blueprint feedback
(`main.py:1420-2759`, `repo-map.md`).

## Frontend Architecture

The frontend is a vanilla ES module application rooted at `frontend/index.html`
and `frontend/app.mjs`. The HTML shell exposes a context gate, left supporting
drawer sections for Workspace, Artifacts, Notes, Memory, and Chats, the central
conversation area, and the right Artifacts Viewer (`frontend/index.html:29-290`).

`frontend/state.mjs` owns client state for auth/context, transcript, pending
turns, retries, memory clarification choices, continuity choices, workspace,
work/artifacts, notes, memory, chats, activity entries, and drawer disclosure.
`frontend/app.mjs` wires bootstrap, rendering, API calls, chat submission,
structured decisions, workspace operations, artifact operations, memory
operations, and note operations (`frontend/app.mjs:315-725`,
`repo-map.md`).

Rendering is intentionally DOM-safe: helpers write text nodes, markdown is
bounded to a safe subset, and artifact content is rendered as text inside code
blocks rather than injected HTML (`frontend/render.mjs:1-25`,
`frontend/markdown-renderer.mjs:3-252`, `repo-map.md`).

## Chat-Turn Lifecycle

`POST /api/chat` resolves effective user and project identity, enforces
idempotency where required, claims or replays a durable turn record, loads
history/profile context, persists the user message, applies structured memory,
note, clarification, continuity, or artifact-feedback decisions, and then calls
the turn service for ordinary model work (`main.py:2759-3562`).

Ordinary turns load governed model context, optional continuity context, and
optional hidden working-state context before routing. The turn service routes
through v4 when artifact routing is available and v3 for non-artifact expert
flows, executes at most one specialist, runs responder-only Agent Col, and
returns validated text plus public receipts (`agent_col_turn_service.py:271-372`,
`agent_col_turn_service.py:556-668`, `agent_col_turn_service.py:929-1130`,
`repo-map.md`).

The request-latency ordering is:

```text
canonical responder completion
-> authoritative chat persistence
-> awaited hidden working-state maintenance
-> HTTP response returned
```

Working-state data is hidden, non-authoritative, failure-tolerant, and logged on
failure. The maintenance call is still awaited after chat persistence and before
the HTTP response returns when working-state updates are enabled
(`main.py:3483-3562`, `main.py:3785-3852`).

## Routing And Specialist Boundaries

The routing layer treats user text and projected context as untrusted task data.
Routing providers call Gemini with structured JSON schemas and local validation;
they do not execute tools or persist state (`agent_col_routing_provider_v3.py`,
`agent_col_routing_provider_v4.py`, `repo-map.md`).

Current expert routes are Direct, Clarify, Source, Research, Computation, and
Requirements Verification, with v4 adding Artifact routing for supported
artifact creation (`agent_col_routing_v3.py:49-55`,
`agent_col_routing_v4.py:34-59`).

Experts are bounded evidence producers. The responder has no model-visible
Research, Source, Computation, or Requirements Verification tools; it receives
validated results and receipts from application code.

## Memory, Notes, Continuity, Working State, And Preferences

Profile memory is governed and proposal-based. Pending memory is not active
until approved by the user. Approval, rejection, correction, revocation, and
deletion flow through typed services and durable events
(`trusted_memory_service.py:286-633`, `database.py:6388-6968`).

Collaborative notes are workspace-scoped. Notes support proposals,
approval/rejection, corrections, archive, restore, deletion, active projection,
and provenance events (`collaborative_note_service.py:188-331`,
`database.py:679-1331`).

Continuity has no independent persisted collection. It resolves active notes
and prior chat sessions/messages into bounded context receipts or ambiguity
choices (`continuity_service.py:118-239`, `database.py:4964-5040`).

Working state is same-session hidden collaboration context. It can summarize
current goals, constraints, unresolved questions, next-step hypotheses, and
confidence, but it cannot authorize tools, identity changes, durable memory,
notes, artifacts, or other actions (`working_state.py:11-101`).

Preference learning records non-authoritative observations and hypotheses. The
current extractor is deliberately narrow and recognizes explicit shorter or
more concise response feedback; surfaced hypotheses go through memory
clarification rather than directly mutating active memory
(`preference_learning.py:10-164`,
`preference_learning_service.py:43-152`, `main.py:3733-3779`).

## Artifacts

The artifact system has two families: synthesis blueprints and generic
single-file artifacts. Blueprints are produced by the synthesis path and
persisted under projects. Generic artifacts support create, list, detail,
archive, restore, metadata update, and child version creation
(`synthesis_service.py:117-152`, `generic_artifact_service.py:128-360`,
`main.py:2211-2757`).

Artifact feedback is persisted for blueprint targets and can be routed through
chat as governed, receipt-backed feedback context. Current artifact execution is
request-bound; durable asynchronous/background execution is not part of the
current runtime path (`artifact_feedback_service.py:133-338`,
`agent_col_artifact_feedback_executor.py:86-200`, `repo-map.md`).

## Persistence And Data Relationships

Firestore stores chat sessions, child messages, child turn records, session
working state, user profile memory, memory proposals/origins/events,
user-owned workspaces, workspace note proposals, collaborative notes and note
events, projects, blueprint artifacts, generic artifacts, artifact versions,
blueprint feedback, feedback supersession records, preference observations, and
preference hypotheses (`database.py`, `repo-map.md`).

Important ownership relationships:

- Chat data lives under `sessions/{session_id}` with child `messages`,
  `turns`, `memory_clarifications`, and `working_state`.
- User-owned data lives under `users/{user_id}`, including workspaces, memory
  records, memory events, note proposals, notes, note events, and preference
  records.
- Project-owned artifact data lives under `projects/{project_id}` with child
  `blueprints`, `artifacts`, and blueprint feedback records.

## Authentication, Ownership, And Security

Auth supports `local_dev` and `google_oidc`. In Google mode, bearer-token
authentication verifies the Google ID token, derives an internal user ID, and
projects a public opaque user ID for client-facing responses. On Cloud Run,
startup fails unless `AGENT_COL_AUTH_MODE=google_oidc` and an OAuth client ID is
configured (`auth.py:66-93`, `auth.py:177-251`).

Workspace/project ownership is enforced by resolving supplied user/project IDs
against the authenticated principal. Middleware adds request body limits,
per-client/path in-memory rate limiting, and security/cache headers
(`auth.py:215-251`, `main.py:280-405`).

## Deployment And Runtime

The container builds from `python:3.14-slim`, installs `requirements.txt`, runs
as a non-root `appuser`, exposes port 8080, and starts
`uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}` (`Dockerfile:3-22`).
Vertex configuration requires a Google Cloud project, global location, and
enterprise GenAI mode (`vertex_config.py:25-53`).

The README identifies Cloud Run in `us-east4` as the hosted platform and notes a
verified deployment; submission work should therefore focus on final hosted
re-verification and freeze rather than initial deployment (`README.md:17-29`).

## System Invariants

- Source and tests are implementation authority; legacy documentation is not.
- Browser code talks only to same-origin backend APIs.
- Structured decisions mutate durable state only through typed backend
  services.
- Pending memory and note proposals are not active until approved.
- Hidden working state and continuity context are non-authoritative and cannot
  authorize persistence or tool use.
- Idempotent chat turns protect deterministic replay, conflict detection, and
  retry behavior.
- Experts produce bounded evidence; Agent Col responder owns the final
  user-facing response.
- Current artifacts are request-bound; background execution is future work.
