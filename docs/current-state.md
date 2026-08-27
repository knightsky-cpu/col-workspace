# Agent Col Current State

Last reconciled: August 27, 2026.

This document is the canonical source-level status summary for the current
checkout. Older plans, audits, and snapshot reviews remain useful provenance,
but this document and executable source control when status claims differ.

## Product Identity

Agent Col is a persistent collaborative partner. It is built to maintain
trusted continuity with the user, adapt from approved memory, take governed
workspace notes, route to bounded specialist capabilities, and keep durable
side effects inspectable and user-controlled.

Agent Col is not only a coding assistant, project planner, blueprint generator,
or document tool. Structured synthesis and artifacts are collaboration
workflows beneath the broader partner identity.

## Implemented Source Capabilities

### Browser Workspace

The FastAPI app serves a same-origin browser workspace:

- `GET /workspace`
- static assets mounted under `/static/agent-col`
- frontend modules in `frontend/`
- no separate frontend build pipeline

The browser workspace includes:

- Google/local authentication entry;
- workspace selection and creation;
- conversation view with receipts, retry, continuity choices, and memory
  clarification choices;
- Work/artifact panel;
- Notes panel;
- Memory panel;
- Chats panel;
- Activity panel;
- left and right drawer layout controls.

### Authentication Foundation

The app supports two local runtime auth modes:

- `local_dev`
- `google_oidc`

Supported startup commands:

```bash
AGENT_COL_AUTH_MODE=local_dev venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

```bash
AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/workspace
```

Google mode requires a public OAuth client ID in `GOOGLE_OAUTH_CLIENT_ID` or
`GOOGLE_CLIENT_ID`, and the OAuth authorized JavaScript origin must match the
local origin. Firestore and Vertex AI still use Application Default
Credentials; browser Google OIDC and ADC are separate authentication concerns.

Production hardening is still pending. Current source has a Google OIDC
foundation, but it does not yet include the full Phase 4 production ownership,
rate-limit, retention, container, Cloud Run, and hosted-proof work.

### Chat And Turn Orchestration

`POST /api/chat` is the main Agent Col interaction boundary.

Implemented behavior includes:

- bounded chat requests and responses;
- idempotent chat turns with durable claim/replay/conflict behavior;
- persisted user and model messages;
- bounded recent history;
- server-projected URL, numeric, and text-block routing inputs;
- zero-or-one expert execution per routed turn;
- final responder-only Agent Col output;
- authoritative action, citation, artifact, memory, note, continuity, and
  adaptation receipts;
- bounded failure handling for provider errors and turn timeouts.

The responder does not have model-visible cognitive expert tools. Routing and
expert execution happen server-side first; the responder receives only
validated context and receipts.

### Memory

Governed profile memory is implemented.

Capabilities include:

- model-proposed pending memory from explicit eligible user statements;
- deterministic policy validation;
- clarification choices for ambiguous memory requests;
- approval and rejection;
- correction;
- revocation;
- hard deletion;
- bounded inspection;
- provenance and lifecycle events;
- cross-session adaptation receipts.

Memory remains profile-scoped and separate from workspace notes. Pending
proposals are not active memory until approved by the user.

### Workspace Notes And Continuity

Governed workspace notes are implemented.

Capabilities include:

- pending note proposals from chat;
- user approval and rejection;
- correction;
- archive, restore, and deletion;
- source session/message provenance;
- active-note projection into Agent Col context;
- bounded active-note retrieval;
- bounded prior-chat retrieval;
- ambiguity choices when retrieval is unclear;
- continuity receipts when notes or prior chats are used.

Notes are workspace-scoped, not global profile memory.

### Internal Working State

Internal working state is implemented for same-session collaboration support.

It stores hidden current-goal and collaboration-state context selected by the
application. It is treated as non-authoritative and possibly stale by the
responder. It cannot authorize tools, persistence, identity changes, memory,
notes, artifacts, or actions.

### Specialist Capabilities

The current expert tool belt has four bounded capabilities:

1. **Research**
   - Direct Google GenAI `generate_content` with Google Search grounding is the
     primary production path.
   - Validates provider grounding metadata, public sources, grounding supports,
     source IDs, and bounded claims.
   - Compacts valid grounded output to at most eight findings while preserving
     original support count.
   - Preserves content-safe invalid-output reasons.
   - Emits `google_search` action receipts and citations only for completed
     validated results.

2. **Source**
   - Direct GenAI chat with URL Context for supplied public URLs.
   - A second tool-free classification pass structures already grounded
     statements.
   - Validates retrieval status, URL metadata, grounding chunks/supports, exact
     statement copying, and source IDs.
   - Emits `url_context` action receipts and citations only for completed
     validated results.

3. **Computation**
   - Isolated ADK workflow with built-in Python code execution.
   - Validates paired executable code and successful output.
   - Projects raw code and raw output out before responder context.
   - Emits `run_computation` action receipts only for completed validated
     results.

4. **Requirements Verification**
   - Direct, tool-free structured Gemini generation.
   - Validates every assessment against supplied requirement and subject block
     IDs, exact subject excerpts, status coherence, counts, and local evidence.
   - Preserves content-safe invalid-output reasons.
   - Emits `verify_requirements` action receipts only for completed validated
     results.

Research and Requirements Verification currently preserve detailed
invalid-output reasons. Source and Computation fail safely but currently expose
only the normalized status.

### Synthesis And Artifacts

Synchronous structured synthesis remains implemented at `POST /api/synthesize`.

Current artifact capabilities include:

- persisted blueprint artifacts;
- generic single-file artifacts;
- artifact listing and detail;
- artifact archive and restore;
- metadata update;
- version creation;
- artifact feedback targets;
- accepted/rejected/edited feedback records and supersession metadata;
- chat-routed artifact effects for currently supported request-bound flows.

The current artifact system is still request-bound. It is not yet the planned
durable asynchronous Cloud Tasks/private-worker workflow.

## Current API Surface

Primary implemented routes in `main.py` include:

- `GET /`
- `GET /workspace`
- `GET /api/auth/config`
- `GET /api/auth/session`
- `GET /api/users/{user_id}/memory`
- `GET /api/users/{user_id}/workspaces`
- `POST /api/users/{user_id}/workspaces`
- `GET /api/users/{user_id}/projects/{project_id}/notes`
- `GET /api/users/{user_id}/projects/{project_id}/notes/{note_id}`
- `POST /api/users/{user_id}/projects/{project_id}/notes/{note_id}/corrections`
- `POST /api/users/{user_id}/projects/{project_id}/notes/{note_id}/archive`
- `POST /api/users/{user_id}/projects/{project_id}/notes/{note_id}/restore`
- `DELETE /api/users/{user_id}/projects/{project_id}/notes/{note_id}`
- `GET /api/users/{user_id}/projects/{project_id}/chat-sessions`
- `GET /api/users/{user_id}/projects/{project_id}/chat-sessions/{session_id}`
- `POST /api/users/{user_id}/memory/signals/{signal_id}/revoke`
- `DELETE /api/users/{user_id}/memory/signals/{signal_id}`
- `POST /api/synthesize`
- `GET /api/projects/{project_id}/blueprints`
- `GET /api/projects/{project_id}/blueprints/{blueprint_id}`
- `GET /api/projects/{project_id}/artifacts`
- `POST /api/projects/{project_id}/artifacts`
- `GET /api/projects/{project_id}/artifacts/{artifact_id}`
- `POST /api/projects/{project_id}/artifacts/{artifact_id}/archive`
- `POST /api/projects/{project_id}/artifacts/{artifact_id}/restore`
- `PATCH /api/projects/{project_id}/artifacts/{artifact_id}/metadata`
- `POST /api/projects/{project_id}/artifacts/{artifact_id}/versions`
- `GET /api/projects/{project_id}/blueprints/{blueprint_id}/feedback`
- `POST /api/chat`

`main.py` remains the authoritative route list.

## Current Technology Stack

Pinned runtime dependencies:

- FastAPI `0.141.1`
- Google API Core `2.34.0`
- Google ADK `2.7.0`
- Google Cloud Firestore `2.28.1`
- Google GenAI SDK `2.18.1`
- Pydantic `2.13.4`
- python-dotenv `1.2.3`
- Uvicorn `0.52.4`

Development dependencies:

- httpx `0.28.1`
- pytest `9.1.1`
- pytest-asyncio `1.4.0`

Model constants currently use Gemini `gemini-3.6-flash`.

## Current Documentation Status

Use this document and `README.md` for current status. Historical design and
planning files under `docs/superpowers/` remain provenance. Files under
`docs/legacy/` are historical snapshots and should not be used as current
implementation descriptions.

## Remaining Winning Core Phases

### Phase 3 - Durable Asynchronous Artifact Work

Pending.

The four specialist expert surfaces are wired and accepted, but the Winning
Core durable artifact-job phase is separate and remains unimplemented.

Expected work includes:

- one selected asynchronous artifact workflow;
- durable Firestore job records;
- `queued`, `running`, `completed`, `failed`, and `cancelled` states;
- idempotent submission, worker execution, completion, retry, and
  cancellation;
- Google Cloud Tasks dispatch;
- private Cloud Run worker authentication;
- browser job progress, result, retry, and cancellation controls;
- controlled failure and retry evidence.

### Phase 4 - Production Hardening And Deployment

Pending after Phase 3 acceptance.

Expected work includes:

- fail-closed production startup;
- canonical workspace ownership and authorization;
- cross-owner denial checks;
- request/body size limits;
- rate limiting;
- security headers;
- log privacy canaries;
- retention and deletion behavior;
- Dockerfile and production startup scripts;
- Cloud Run service configuration;
- IAM/service accounts;
- Cloud Tasks OIDC if the private worker remains in scope;
- hosted auth, ownership, failure, and smoke checks.

### Phase 5 - Reproducibility And Submission Evidence

Pending after Phase 4 acceptance.

Expected work includes:

- final hosted-build README and architecture reconciliation after deployment
  work changes the source baseline;
- clean-clone setup proof;
- exact local and hosted commands;
- full relevant test evidence;
- dependency, licensing, and ignored-file audit;
- judge-readable Cloud Run, Firestore, and Cloud Tasks evidence.

### Phase 6 - Demo And Build Freeze

Pending after Phase 5 acceptance.

Expected work includes:

- four-minute demo script;
- visible memory adaptation;
- governed workspace note demonstration;
- consequential clarification;
- artifact workflow and feedback demonstration;
- controlled failure or retry proof;
- hosted URL and Google Cloud evidence;
- final submission copy and build freeze.

## Known Gaps

- No Dockerfile, `.dockerignore`, production start scripts, or Cloud Run
  service configuration are present.
- No Google Cloud Tasks runtime dependency or private worker implementation is
  present.
- Durable asynchronous artifact jobs with queued/running/completed/failed/
  cancelled states are still planned.
- Production startup currently needs Phase 4 hardening; local development still
  defaults to `local_dev` unless explicitly configured.
- Source and Computation do not yet preserve detailed invalid-output reasons.
- Some older docs remain historical and should not be used as current status.

## Safe Visual Work Boundary

For visual polish, use `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md`.

The safe default is CSS-only work in `frontend/styles.css`. Visual-only passes
must not change API routes, request payloads, JavaScript state transitions,
forms, data hooks, auth, memory, notes, artifacts, working state, prompts, or
backend behavior.
