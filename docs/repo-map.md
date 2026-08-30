# Repository Map

This map was re-derived from the repository source and tests on 2026-08-30.
Treat historical plans under `docs/legacy/` as implementation history, not as
authority for current behavior.

## Current Authority

- `README.md`: judge/developer entry point and reproducible setup guide.
- `docs/architecture.md`: current production architecture and trust
  boundaries.
- `docs/current-state.md`: current feature status and known limitations.
- `docs/repo-map.md`: this source-derived navigation map.
- `docs/submission-checklist.md`: hackathon submission coverage checklist.

## Important Root Files

- `main.py`: FastAPI application, static frontend mount, middleware, auth
  enforcement, startup service wiring, HTTP route handlers, chat turn boundary,
  and SSE chat stream endpoint.
- `schemas.py`: Pydantic request/response models shared by the FastAPI routes,
  service layer, tests, and browser API contracts.
- `database.py`: Firestore-backed `MemoryEngine`; owns chat sessions, messages,
  users, workspaces, governed memory, memory clarifications, collaborative
  notes, preference-learning records, blueprints, generic artifacts, artifact
  feedback, and working state.
- `auth.py`: local development auth and Google OIDC verification helpers. On
  Cloud Run, `K_SERVICE` requires `AGENT_COL_AUTH_MODE=google_oidc` and a Google
  OAuth client ID.
- `vertex_config.py`: validated Vertex AI / Google GenAI SDK environment
  contract. Requires `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`,
  and `GOOGLE_GENAI_USE_ENTERPRISE=true`.
- `Dockerfile`: Python 3.14 slim image that installs `requirements.txt`, copies
  the repository, runs as `appuser`, and starts `uvicorn main:app` on
  `${PORT:-8080}`.
- `requirements.txt`: runtime dependencies: FastAPI, Google ADK, Google Cloud
  Firestore, Google GenAI SDK, Pydantic, python-dotenv, and Uvicorn.
- `requirements-dev.txt`: test/runtime development dependencies layered on
  `requirements.txt`.
- `firestore.indexes.json`: Firestore index configuration; currently disables
  indexing for the blueprint payload field.
- `pytest.ini`: pytest configuration.
- `AGENTS.md`: repository collaboration workflow for source-changing passes.
- `LICENSE`, `NOTICE`: licensing and attribution.
- `agent-col-visual-target.jpeg`: visual target asset used by documentation and
  frontend review context.

Do not treat `.env` as documentation or source authority. It is local,
developer-specific configuration and must not be copied into docs.

## Production Backend

### Application Boundary

- `main.py` creates the FastAPI app with lifespan-managed dependencies.
- Startup wires:
  - `google.genai.Client` from `vertex_config.py`.
  - Firestore `MemoryEngine` from `database.py`.
  - `TrustedMemoryService`, `CollaborativeNoteService`,
    `ContinuityService`, `WorkingStateService`, and
    `PreferenceLearningService`.
  - Source, research, computation, and requirements-verification expert
    services.
  - `AgentColExpertExecutorV3`.
  - Google ADK responder runtime from `agent_col_responder.create_responder_app`
    and `SupervisorRuntime.from_app`.
  - `AgentColTurnService`.
- `/static/agent-col` serves the browser modules from `frontend/`.
- `/workspace` serves `frontend/index.html`.

### Public HTTP Surface

Current route handlers in `main.py` expose:

- `GET /`: shallow health response.
- `GET /workspace`: browser UI shell.
- `GET /api/auth/config`: auth mode and Google Sign-In configuration.
- `GET /api/auth/session`: verified local or Google-authenticated session.
- `GET /api/users/{user_id}/memory`: governed memory inspection.
- `POST /api/users/{user_id}/memory/signals/{signal_id}/revoke`: revoke active
  memory signal.
- `DELETE /api/users/{user_id}/memory/signals/{signal_id}`: delete active
  memory signal.
- `GET /api/users/{user_id}/workspaces`: list visible workspaces.
- `POST /api/users/{user_id}/workspaces`: create a workspace.
- `DELETE /api/users/{user_id}/workspaces/{workspace_id}`: delete a workspace
  while preserving the last-workspace invariant.
- `GET /api/users/{user_id}/projects/{project_id}/notes`: list collaborative
  notes.
- `GET /api/users/{user_id}/projects/{project_id}/notes/{note_id}`: load a
  collaborative note and events.
- `POST /api/users/{user_id}/projects/{project_id}/notes/proposals`: create a
  note proposal.
- `POST /api/users/{user_id}/projects/{project_id}/notes/{note_id}/corrections`:
  create a correction proposal.
- `POST /api/users/{user_id}/projects/{project_id}/notes/{note_id}/archive`:
  archive a note.
- `POST /api/users/{user_id}/projects/{project_id}/notes/{note_id}/restore`:
  restore a note.
- `DELETE /api/users/{user_id}/projects/{project_id}/notes/{note_id}`: delete a
  note.
- `GET /api/users/{user_id}/projects/{project_id}/chat-sessions`: list chat
  sessions.
- `GET /api/users/{user_id}/projects/{project_id}/chat-sessions/{session_id}`:
  load a chat session transcript and receipts.
- `POST /api/synthesize`: create a blueprint from source text.
- `GET /api/projects/{project_id}/blueprints`: list blueprint artifacts.
- `GET /api/projects/{project_id}/blueprints/{blueprint_id}`: load a blueprint
  artifact.
- `GET /api/projects/{project_id}/blueprints/{blueprint_id}/feedback`: list
  feedback for a blueprint artifact.
- `GET /api/projects/{project_id}/artifacts`: list generic single-file
  artifacts.
- `POST /api/projects/{project_id}/artifacts`: generate and persist a generic
  single-file artifact.
- `GET /api/projects/{project_id}/artifacts/{artifact_id}`: load a generic
  artifact.
- `POST /api/projects/{project_id}/artifacts/{artifact_id}/archive`: archive an
  artifact.
- `POST /api/projects/{project_id}/artifacts/{artifact_id}/restore`: restore an
  artifact.
- `DELETE /api/projects/{project_id}/artifacts/{artifact_id}`: delete an
  artifact.
- `PATCH /api/projects/{project_id}/artifacts/{artifact_id}/metadata`: update
  artifact metadata.
- `POST /api/projects/{project_id}/artifacts/{artifact_id}/versions`: create a
  new artifact version.
- `POST /api/chat`: JSON chat endpoint for ordinary and structured chat
  requests.
- `POST /api/chat/stream`: SSE endpoint for ordinary chat requests. Structured
  decisions use `/api/chat`; the backend rejects those requests on the streaming
  endpoint.

### Agent Col Orchestration

- `agent_col_turn_service.py`: production turn orchestrator. It builds routing
  inputs, calls routing providers, executes expert/tool paths, prepares
  responder context, supports streaming text deltas, and returns authoritative
  receipts.
- `agent_col_routing.py`: shared routing primitives and URL projection helpers.
- `agent_col_routing_v2.py`, `agent_col_routing_v3.py`,
  `agent_col_routing_v4.py`: versioned routing contract models. The current
  turn service imports v3 and v4.
- `agent_col_routing_provider_v3.py`,
  `agent_col_routing_provider_v4.py`: Vertex / GenAI SDK structured-output
  routing provider boundaries using `gemini-3.6-flash`.
- `agent_col_numeric_projection.py`,
  `agent_col_text_projection.py`: deterministic projection helpers used by
  routing models and turn orchestration.
- `agent_col_expert_executor_v3.py`: production expert execution boundary for
  v3-compatible directives.
- `agent_col_responder.py`: creates the Google ADK responder app. The responder
  model is `gemini-3.6-flash`.
- `supervisor_runtime.py`: Google ADK `Runner` wrapper with run and stream turn
  support, timeout handling, and extraction of runtime tool events.
- `supervisor.py`: ADK app constants.
- `expert_contracts.py`, `expert_delegation.py`: expert capability/status
  contracts and delegation tool schema.

Earlier files such as `agent_col_expert_executor.py`,
`agent_col_expert_executor_v2.py`, `agent_col_responder_context.py`,
`agent_col_responder_context_v2.py`, `agent_col_routing_provider.py`, and
`agent_col_routing_provider_v2.py` remain in the repository for tested legacy
or migration coverage. They are not the primary production path imported by
`main.py`.

### Experts and Tools

- `source_expert.py`, `source_expert_service.py`, `source_expert_runtime.py`,
  `source_expert_tool.py`: source-grounded expert models, direct service logic,
  runtime tracking, and ADK tool boundary tests.
- `research_expert.py`, `research_expert_service.py`,
  `research_expert_runtime.py`: research expert models, Google Search grounded
  GenAI service, and runtime tracking.
- `computational_expert.py`, `computational_expert_service.py`: computation
  expert models and GenAI-backed service boundary.
- `requirements_verification.py`,
  `requirements_verification_service.py`: requirements verification models and
  service boundary.
- `computational_executor_spike.py`, `agent_col_routing_spike.py`, and
  `*_routing_check.py` / `*_routing_evaluation.py` files are evaluation,
  compatibility, or live-check utilities, not FastAPI route handlers.

### Memory, Notes, Continuity, Preferences, and Working State

- `trusted_memory_service.py`: governed memory lifecycle service.
- `memory_policy.py`, `memory_proposals.py`, `memory_proposal_tool.py`,
  `memory_candidate_decisions.py`, `memory_candidate_normalization.py`,
  `memory_clarifications.py`, `memory_context.py`: memory policy, proposal,
  clarification, projection, and model-context helpers.
- `collaborative_notes.py`, `collaborative_note_policy.py`,
  `collaborative_note_candidates.py`, `collaborative_note_service.py`,
  `collaborative_note_tool.py`: collaborative note models, validation, proposal
  derivation, persistence service, and ADK tool boundary.
- `continuity.py`, `continuity_service.py`: continuity choices and term
  expansion.
- `preference_learning.py`, `preference_learning_service.py`: preference
  observation/hypothesis capture and surfaced-confirmation logic.
- `working_state.py`, `working_state_service.py`: hidden working-state snapshot
  models and GenAI-backed update service.

### Artifacts and Synthesis

- `synthesis.py`, `synthesis_schema.py`, `synthesis_quality.py`,
  `synthesis_personalization.py`, `synthesis_service.py`: blueprint synthesis
  models, schema adaptation, quality checks, personalization, and service
  boundary.
- `blueprint_validation.py`: blueprint validation helpers.
- `artifact_read_service.py`: read model for blueprint artifacts.
- `artifact_feedback_service.py`: artifact feedback listing and resolution.
- `agent_col_artifact_executor.py`: chat-owned artifact creation execution.
- `agent_col_artifact_feedback_executor.py`: chat-owned feedback execution.
- `generic_artifact_generation.py`: GenAI-backed single-file artifact
  generation.
- `generic_artifact_creation_service.py`,
  `generic_artifact_service.py`: persistence and lifecycle service boundaries
  for generic artifacts.

### Persistence Model

`database.py` uses Firestore collections for:

- `sessions` and nested `messages` for chat history and turn records.
- `users/{user_id}/workspaces` for workspace containers.
- `users/{user_id}/workspaces/{workspace_id}/collaborative_notes` and related
  note proposal/event collections.
- `users/{user_id}/workspaces/{workspace_id}/preference_*` records.
- `projects/{project_id}/blueprints`, `artifacts`, and artifact feedback
  collections.
- governed memory signals, proposals, clarifications, and events.
- working-state snapshots.

The API resolves effective user and project IDs from auth context before
touching owner-scoped data.

## Browser Frontend

The browser UI is plain static ES modules under `frontend/`; there is no
frontend package manager, bundler, or build step in this repository.

- `frontend/index.html`: UI shell loaded by `/workspace`.
- `frontend/app.mjs`: browser application coordinator. It bootstraps auth,
  loads workspace/memory/notes/artifact/chat-session data, submits chat turns,
  handles ordinary-turn SSE deltas, refreshes authoritative effects, and wires
  DOM events to view modules.
- `frontend/api.mjs`: same-origin API client, normalized API errors,
  idempotency/auth headers, JSON fetch helpers, and SSE frame parsing.
- `frontend/requests.mjs`: request builders, generated IDs/idempotency keys,
  context parsing, and chat endpoint selection. Ordinary chat uses
  `/api/chat/stream`; structured decisions use `/api/chat`.
- `frontend/state.mjs`: immutable-ish client state transitions for auth,
  workspace selection, pending turns, transcripts, effects, artifacts, notes,
  memory, chat sessions, and disclosure state.
- `frontend/chat-view.mjs`: transcript, receipts, memory clarification choices,
  and continuity choices.
- `frontend/work-view.mjs`: artifact list/detail, lifecycle actions, metadata
  editing, version creation, feedback, and exports.
- `frontend/memory-view.mjs`: governed memory proposals, active signals,
  destructive action confirmation, and event disclosure.
- `frontend/notes-view.mjs`: collaborative note lists, details, proposals,
  corrections, archive/restore/delete actions.
- `frontend/chats-view.mjs`: chat-session list and selection.
- `frontend/workspace-view.mjs`,
  `frontend/workspace-indicator.mjs`: workspace list, creation/deletion, and
  current workspace display.
- `frontend/workspace-layout.mjs`: drawer and section expansion state helpers.
- `frontend/auth-view.mjs`: Google Sign-In script/rendering helpers and session
  context mapping.
- `frontend/activity-view.mjs`: activity panel rendering.
- `frontend/markdown-renderer.mjs`: safe Markdown subset renderer.
- `frontend/render.mjs`: low-level DOM/text helpers.
- `frontend/styles.css`: browser UI styling.

## Tests and Checks

- `tests/`: pytest suite for backend models, services, FastAPI behavior,
  Firestore persistence boundaries, routing/evaluation utilities, deployment
  packaging, and smoke-test wrappers. Current source inspection found 139 Python
  test files under `tests/`.
- `tests/frontend/`: Node test files for browser ES modules. Current source
  inspection found 16 `.mjs` test files.
- `tests/fixtures/`: JSON routing, memory, research, source, tool-belt, and
  synthesis-quality fixtures.
- `live-tests/`: manually run smoke checks and provider-backed checks. Current
  source inspection found 25 Python files. These may require live Google
  credentials or deployed/local services depending on the script.
- Root `*_check.py` and `*_evaluation.py` files: evaluation and live-check
  utilities used by tests or manual verification; they are not imported by
  `main.py` as production routes.

Useful focused commands:

```bash
python -m pytest tests/test_main.py
python -m pytest tests/test_agent_col_turn_service.py tests/test_supervisor_runtime.py
node --test tests/frontend/*.test.mjs
python -m pytest tests/test_deployment_packaging.py tests/test_firestore_indexes.py
```

Run live tests only when the required Google credentials, Vertex AI settings,
and service state are intentionally available.

## Deployment and Configuration

- Runtime server: `uvicorn main:app`.
- Container entry point: `Dockerfile`.
- Cloud target documented by the repository: Cloud Run.
- Required Vertex / GenAI environment:
  - `GOOGLE_CLOUD_PROJECT`
  - `GOOGLE_CLOUD_LOCATION=global`
  - `GOOGLE_GENAI_USE_ENTERPRISE=true`
- Auth modes:
  - `AGENT_COL_AUTH_MODE=local_dev` for local development.
  - `AGENT_COL_AUTH_MODE=google_oidc` for Cloud Run or Google-authenticated
    operation.
  - `GOOGLE_OAUTH_CLIENT_ID` or `GOOGLE_CLIENT_ID` when Google OIDC is enabled.
- Firestore configuration:
  - service identity or application default credentials must have Firestore
    access.
  - indexes/config live in `firestore.indexes.json`.

Deployment docs live in `docs/deployment/`.

## Documentation Directories

- `docs/README.md`: documentation index.
- `docs/development/`: local setup, testing, and troubleshooting docs.
- `docs/deployment/`: Cloud Run deployment, hardening, and handoff docs.
- `docs/design/`: current design and contract documents that are not direct
  implementation history.
- `docs/forward/`: forward-looking implementation plans.
- `docs/legacy/`: preserved implementation history, prior plans, evaluation
  records, architecture notes, research, and finalization documents.
- `docs/notes/`: informal notes, scratch findings, investigation notes, and
  working observations from the documentation cleanup.

When current docs disagree with source, source and tests win. When historical
docs disagree with current docs, keep the history intact and update the
authoritative current-state docs instead.
