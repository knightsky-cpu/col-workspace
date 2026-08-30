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

Runtime composition details:

- `vertex_config.load_vertex_ai_settings` validates the Vertex/GenAI runtime
  contract before model-backed services are created.
- `genai.Client` is shared by synthesis, generic artifact generation,
  continuity term expansion, working-state maintenance, and model-backed
  expert/provider code.
- `MemoryEngine` is the Firestore repository boundary for chat, workspaces,
  governed memory, collaborative notes, continuity lookup data, working state,
  artifacts, and feedback.
- `AgentColTurnService` receives the database, trusted memory service,
  collaborative note service, continuity service, expert executor, responder
  runtime, artifact executor, artifact feedback executor, and v3/v4 routing
  providers. This makes it the production orchestration boundary for
  `/api/chat` and `/api/chat/stream`.
- Static frontend serving is intentionally simple: there is no frontend build
  pipeline between source files in `frontend/` and the browser modules served
  by FastAPI.

### Public HTTP Surface

Current route handlers in `main.py` expose 33 public routes. This table is
derived from the active FastAPI decorators and handler annotations, not from
historical route inventories.

| Method | Route | Purpose | Request model / input | Response model / output | Auth boundary | Ownership / scope | Primary handler / service | Important behavior |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/workspace` | Serve the browser workspace shell. | N/A. Plain HTML request. | `FileResponse` with `response_class=HTMLResponse`. | Public route; no principal resolution at this handler. | N/A. API calls made by the shell enforce user/workspace/project ownership. | `workspace`; static file from `frontend/index.html`. | Sends `Cache-Control: no-store`; static ES modules are served from `/static/agent-col`. |
| `GET` | `/` | Shallow service health check. | N/A. Plain GET. | `dict[str, str]` containing `{"status": "online"}`. | Public route; no principal resolution. | N/A. | `health_check`. | Only proves the FastAPI process can answer. It does not prove Firestore, Vertex AI, Gemini, or ADK access. |
| `GET` | `/api/auth/config` | Report browser auth configuration. | N/A. Plain GET. | `dict[str, object]` with auth contract version, mode, public Google client ID, sign-in requirement, and local-dev flag. | Public route; reads configured auth mode. | N/A. | `auth_config`; `Authenticator` settings. | Exposes only browser-safe auth settings, not secrets. |
| `GET` | `/api/auth/session` | Project the current local-dev or Google OIDC session. | Optional `Authorization: Bearer ...` header. | `principal.public_dict()`. | `local_dev` returns a local-development principal without a bearer token. `google_oidc` requires and verifies a Google ID token. | Google mode resolves the opaque public user locator from the verified Google subject; path/body IDs are not involved. | `auth_session`; `Authenticator.session`. | Missing Google bearer token returns `401`; invalid token returns `403`; auth configuration failure returns `500`. |
| `GET` | `/api/users/{user_id}/memory` | Inspect governed memory profile, unresolved proposals, clarifications, and events. | Path `user_id`; optional `after_event_id` query cursor. | `MemoryInspectionResponse`. | Resolves `{user_id}` with `_resolve_effective_user_id`. `local_dev` accepts the supplied locator; `google_oidc` requires the public locator to match the verified subject. | Effective internal user ID is authoritative; supplied user ID is only a locator in Google mode. | `inspect_memory`; `TrustedMemoryService.inspect_memory`. | Invalid event cursor returns `404`; storage failures map to bounded `500` errors. |
| `GET` | `/api/users/{user_id}/workspaces` | List visible workspaces for a user. | Path `user_id`; `limit` query. | `WorkspaceListResponse`. | Resolves `{user_id}` and request workspace defaults. | User-scoped. Google mode derives subject-owned default workspace/project identifiers. | `list_user_workspaces`; `MemoryEngine.list_workspaces`. | Synthesizes/defaults the current workspace projection when needed unless the default workspace has been deleted. |
| `POST` | `/api/users/{user_id}/workspaces` | Create a user-owned workspace. | Path `user_id`; body `WorkspaceCreateRequest`. | `WorkspaceCreateResponse`. | Resolves `{user_id}` and workspace defaults. | User/workspace-scoped. In Google mode, the workspace ID is derived under the verified subject-owned default workspace prefix. | `create_user_workspace`; `MemoryEngine.create_workspace`. | Invalid display names or workspace requests return `422`. |
| `DELETE` | `/api/users/{user_id}/workspaces/{workspace_id}` | Delete a visible workspace. | Path `user_id`, `workspace_id`; no request body. | `204 No Content`. | Resolves `{user_id}` and workspace defaults. | User/workspace-scoped. The service enforces workspace visibility and prevents deleting the last visible workspace. | `delete_user_workspace`; `MemoryEngine.delete_workspace`. | Missing workspace returns `404`; last-workspace deletion returns `409`; validation errors return `422`. |
| `GET` | `/api/users/{user_id}/projects/{project_id}/notes` | List workspace-scoped collaborative notes. | Path `user_id`, `project_id`; query `status_filter`, `limit`, `cursor`. | `CollaborativeNoteListResponse`. | Resolves user and project with `_resolve_note_scope`. | Effective user and workspace project are authoritative; Google mode requires the user locator and project locator to belong to the verified subject. | `list_collaborative_notes`; `CollaborativeNoteService.list_notes`. | Response is projected back to the supplied public user locator; service errors map through collaborative-note HTTP handling. |
| `GET` | `/api/users/{user_id}/projects/{project_id}/notes/{note_id}` | Load one collaborative note and event history. | Path `user_id`, `project_id`, `note_id`; `limit` query. | `CollaborativeNoteDetailResponse`. | Resolves user and project with `_resolve_note_scope`. | Workspace note scope; stored owner is checked by the service/read path. | `get_collaborative_note`; `CollaborativeNoteService.get_note`. | Public projection rewrites internal owner IDs to the supplied public user locator. |
| `POST` | `/api/users/{user_id}/projects/{project_id}/notes/proposals` | Create an explicit collaborative-note proposal. | Path `user_id`, `project_id`; body `CollaborativeNoteProposalRequest`; required `Idempotency-Key` header. | `CollaborativeNoteProposalResponse`. | Validates idempotency key, then resolves user/project with `_resolve_note_scope`. | Workspace-scoped proposal under the effective user/project; body content is not authority for ownership. | `create_collaborative_note_proposal`; `CollaborativeNoteService.create_proposal`. | Produces a pending proposal rather than directly creating an active note. Missing idempotency key returns `400`; malformed key returns `422`. |
| `POST` | `/api/users/{user_id}/projects/{project_id}/notes/{note_id}/corrections` | Create a correction proposal for an existing note. | Path `user_id`, `project_id`, `note_id`; body `CollaborativeNoteCorrectionRequest`; required `Idempotency-Key` header. | `CollaborativeNoteProposalResponse`. | Validates idempotency key, then resolves user/project with `_resolve_note_scope`. | Workspace note scope; correction targets the existing note located by path. | `create_collaborative_note_correction`; `CollaborativeNoteService.create_correction`. | Produces a pending correction proposal; conflicts map to `409`. |
| `POST` | `/api/users/{user_id}/projects/{project_id}/notes/{note_id}/archive` | Archive a collaborative note. | Path `user_id`, `project_id`, `note_id`; body `CollaborativeNoteMutationRequest`. | `CollaborativeNoteLifecycleResponse`. | Resolves lifecycle scope through `_resolve_note_lifecycle_request`. | Workspace note scope with expected-revision protection. | `archive_collaborative_note`; `CollaborativeNoteService.archive_note`. | Writes lifecycle event and returns public-owner-projected note state; revision conflicts map to `409`. |
| `POST` | `/api/users/{user_id}/projects/{project_id}/notes/{note_id}/restore` | Restore an archived collaborative note. | Path `user_id`, `project_id`, `note_id`; body `CollaborativeNoteMutationRequest`. | `CollaborativeNoteLifecycleResponse`. | Resolves lifecycle scope through `_resolve_note_lifecycle_request`. | Workspace note scope with expected-revision protection. | `restore_collaborative_note`; `CollaborativeNoteService.restore_note`. | Writes lifecycle event and returns public-owner-projected note state; revision conflicts map to `409`. |
| `DELETE` | `/api/users/{user_id}/projects/{project_id}/notes/{note_id}` | Delete a collaborative note. | Path `user_id`, `project_id`, `note_id`; body `CollaborativeNoteMutationRequest`. | `204 No Content`. | Resolves user/project and expected revision before deletion. | Workspace note scope with expected-revision protection. | `delete_collaborative_note`; `CollaborativeNoteService.delete_note`. | Destructive operation; conflicts map to `409`; validation errors map to `422`. |
| `GET` | `/api/users/{user_id}/projects/{project_id}/chat-sessions` | List chat sessions for a user/project. | Path `user_id`, `project_id`; `limit` query. | `ChatSessionListResponse`. | Resolves `{user_id}` and `{project_id}`. | Effective user/project scope. Stored session owners are checked before public projection. | `list_chat_sessions`; `MemoryEngine.list_chat_sessions`. | Response projects internal effective user IDs back to the supplied public user locator. |
| `GET` | `/api/users/{user_id}/projects/{project_id}/chat-sessions/{session_id}` | Load a chat session transcript and receipts. | Path `user_id`, `project_id`, `session_id`; `limit` query. | `ChatSessionDetailResponse`. | Resolves `{user_id}` and `{project_id}`. | Effective user/project scope plus stored session ownership. | `get_chat_session`; `MemoryEngine.get_chat_session_detail`. | Returns chronological public transcript/detail projection; invalid stored clarification state maps to bounded `500`. |
| `POST` | `/api/users/{user_id}/memory/signals/{signal_id}/revoke` | Revoke an active governed-memory signal. | Path `user_id`, `signal_id`; no request body. | `MemoryMutationResponse`. | Resolves `{user_id}` with `_resolve_effective_user_id`. | Effective user scope; memory service validates the signal locator under the resolved user. | `revoke_memory_signal`; `TrustedMemoryService.revoke_memory_signal`. | Writes revocation event/profile update; missing signal returns `404`; lifecycle conflict returns `409`. |
| `DELETE` | `/api/users/{user_id}/memory/signals/{signal_id}` | Hard-delete a governed-memory signal/provenance chain. | Path `user_id`, `signal_id`; no request body. | `204 No Content`. | Resolves `{user_id}` with `_resolve_effective_user_id`. | Effective user scope; memory service validates the signal locator under the resolved user. | `delete_memory_signal`; `TrustedMemoryService.delete_memory_signal`. | Destructive operation; validation errors return `422`; storage failures are bounded. |
| `POST` | `/api/synthesize` | Generate and persist a blueprint artifact from source text. | Body `SynthesisRequest`. | `SynthesisResponse`. | Resolves `payload.user_id` and `payload.project_id`. | User/project scope from authenticated context; body IDs are locators, not authority, in Google mode. | `synthesize`; `SynthesisApplicationService.synthesize`. | Request-bound generation; synthesis timeout returns `504`; provider/service failure returns `502`. |
| `GET` | `/api/projects/{project_id}/blueprints` | List blueprint artifacts for a project. | Path `project_id`; query `limit`, `before`. | `BlueprintArtifactListResponse`. | Resolves `{project_id}` with `_resolve_effective_project_id`. | Project scope. Google mode requires the project to be subject-owned or a subject-prefixed workspace project. | `list_blueprint_artifacts`; `ArtifactReadService.list_blueprints`. | Missing pagination cursor returns `404`; invalid stored artifact state maps to bounded `500`. |
| `GET` | `/api/projects/{project_id}/blueprints/{blueprint_id}` | Load one blueprint artifact. | Path `project_id`, `blueprint_id`; no request body. | `BlueprintArtifactDetailResponse`. | Resolves `{project_id}` with `_resolve_effective_project_id`. | Project scope; blueprint is loaded under the effective project. | `get_blueprint_artifact`; `ArtifactReadService.get_blueprint`. | Missing blueprint returns `404`; unsupported schema returns `409`; invalid stored state maps to bounded `500`. |
| `GET` | `/api/projects/{project_id}/artifacts` | List generic single-file artifacts. | Path `project_id`; query `limit`, `before`, `lifecycle_status`. | `SingleFileArtifactListResponse`. | Resolves `{project_id}` with `_resolve_effective_project_id`. | Project scope; artifact visibility is scoped to the effective project. | `list_generic_artifacts`; `GenericArtifactReadService.list_artifacts`. | Supports active/archived filtering through `lifecycle_status`; bad cursor returns `404`. |
| `POST` | `/api/projects/{project_id}/artifacts` | Generate and persist a generic single-file artifact. | Path `project_id`; body `SingleFileArtifactCreateRequest`. | `SingleFileArtifactCreateResponse`. | Resolves `payload.user_id` and path `project_id`. | Effective user/project scope; path project is authoritative after auth resolution. | `create_generic_artifact`; `generate_generic_artifact`; `GenericArtifactCreationService.create_artifact`. | Request-bound GenAI artifact generation; timeout returns `504`; generation failure returns `502`. |
| `GET` | `/api/projects/{project_id}/artifacts/{artifact_id}` | Load one generic artifact. | Path `project_id`, `artifact_id`; no request body. | `SingleFileArtifactDetailResponse`. | Resolves `{project_id}` with `_resolve_effective_project_id`. | Project scope; artifact is loaded under the effective project. | `get_generic_artifact`; `GenericArtifactReadService.get_artifact`. | Missing artifact returns `404`; invalid stored state maps to bounded `500`. |
| `POST` | `/api/projects/{project_id}/artifacts/{artifact_id}/archive` | Archive a generic artifact. | Path `project_id`, `artifact_id`; no request body. | `SingleFileArtifactLifecycleResponse`. | Resolves `{project_id}` with `_resolve_effective_project_id`. | Project scope; artifact is mutated under the effective project. | `archive_generic_artifact`; `GenericArtifactReadService.archive_artifact`. | Lifecycle mutation; missing artifact returns `404`; invalid stored state maps to bounded `500`. |
| `POST` | `/api/projects/{project_id}/artifacts/{artifact_id}/restore` | Restore an archived generic artifact. | Path `project_id`, `artifact_id`; no request body. | `SingleFileArtifactLifecycleResponse`. | Resolves `{project_id}` with `_resolve_effective_project_id`. | Project scope; artifact is mutated under the effective project. | `restore_generic_artifact`; `GenericArtifactReadService.restore_artifact`. | Lifecycle mutation; missing artifact returns `404`; invalid stored state maps to bounded `500`. |
| `DELETE` | `/api/projects/{project_id}/artifacts/{artifact_id}` | Delete a generic artifact. | Path `project_id`, `artifact_id`; no request body. | `204 No Content`. | Resolves `{project_id}` with `_resolve_effective_project_id`. | Project scope; artifact is deleted under the effective project. | `delete_generic_artifact`; `GenericArtifactReadService.delete_artifact`. | Destructive operation; missing artifact returns `404`; invalid stored state maps to bounded `500`. |
| `PATCH` | `/api/projects/{project_id}/artifacts/{artifact_id}/metadata` | Update generic artifact display metadata. | Path `project_id`, `artifact_id`; body `SingleFileArtifactMetadataUpdateRequest`. | `SingleFileArtifactLifecycleResponse`. | Resolves `{project_id}` with `_resolve_effective_project_id`. | Project scope; metadata mutation is scoped to the effective project. | `update_generic_artifact_metadata`; `GenericArtifactReadService.update_artifact_metadata`. | Updates mutable display fields such as label/filename metadata; missing artifact returns `404`. |
| `POST` | `/api/projects/{project_id}/artifacts/{artifact_id}/versions` | Create a child version of a generic artifact. | Path `project_id`, `artifact_id`; body `SingleFileArtifactEditRequest`. | `SingleFileArtifactCreateResponse`. | Resolves `payload.user_id` and path `project_id`. | Effective user/project scope; parent artifact is located under the effective project. | `create_generic_artifact_version`; `GenericArtifactReadService.create_artifact_version`. | Creates a new version linked to the parent artifact; generation/storage failures are bounded. |
| `GET` | `/api/projects/{project_id}/blueprints/{blueprint_id}/feedback` | List feedback for one blueprint artifact. | Path `project_id`, `blueprint_id`; query `limit`, `before`. | `BlueprintArtifactFeedbackListResponse`. | Resolves `{project_id}` with `_resolve_effective_project_id`. | Project scope; feedback is listed under the effective project and blueprint. | `list_blueprint_feedback`; `ArtifactFeedbackService.list_feedback`. | Missing blueprint/cursor returns `404`; invalid stored feedback maps to bounded `500`. |
| `POST` | `/api/chat` | Canonical JSON chat path for ordinary chat and structured decision turns. | Body `ChatRequest`; `Idempotency-Key` header is optional for ordinary local-dev turns, required in Google OIDC, and required for structured/effect decisions. | `ChatResponse`; typed partial-failure/error JSON when implemented failure branches preserve completed effects. | Resolves `payload.user_id` and `payload.project_id`; Google mode verifies the bearer token and requires subject-owned locators. | Effective user/project/session scope. `_ensure_visible_workspace_for_chat` checks workspace visibility before execution; supplied IDs are locators, not authority, in Google mode. | `chat`; `_execute_chat`; `AgentColTurnService.run_turn`. | Handles ordinary chat plus memory decisions, memory clarification selections, collaborative-note decisions, continuity selections, and artifact-feedback decisions. Claims/replays/resumes durable idempotent turns, routes through v3/v4, executes specialists/tools, persists canonical messages/effects, and returns the authoritative validated response. |
| `POST` | `/api/chat/stream` | SSE transport for ordinary conversational chat turns only. | Body `ChatRequest`; same idempotency header rules as `/api/chat`; response transport is `text/event-stream`. | SSE `delta`, `final`, and `error` events; `final` carries a validated `ChatResponse`. | Same user/project/session/workspace boundary as `/api/chat`, then `_execute_chat(..., ordinary_only=True)`. | Same effective user/project/session scope as `/api/chat`. Structured decision payload fields are rejected on this endpoint. | `chat_stream`; `_execute_chat`; `AgentColTurnService.stream_turn`; `StreamingResponse`. | Streamed `delta` events are provisional and not independently durable truth. Structured decisions return `409` with `Structured chat decisions must use /api/chat.` The `final` event is the authoritative response projection. |

Route families and transport boundaries:

- `/api/auth/*` endpoints are browser bootstrap/session endpoints. They do not
  mutate project data.
- `/api/users/{user_id}/workspaces/*` endpoints are user-scoped workspace
  inventory/lifecycle endpoints.
- `/api/users/{user_id}/projects/{project_id}/notes/*` endpoints are
  workspace-scoped collaborative-note read/proposal/lifecycle endpoints.
- `/api/users/{user_id}/memory/*` endpoints expose governed-memory inspection
  and destructive signal actions for the resolved effective user.
- `/api/projects/{project_id}/blueprints/*` endpoints expose read-only
  blueprint artifact and feedback surfaces. Blueprint archive/restore/delete
  routes are not registered in `main.py`.
- `/api/projects/{project_id}/artifacts/*` endpoints expose generic
  single-file artifact read/create/lifecycle/metadata/versioning surfaces.
- `/api/synthesize` is a request-bound blueprint generation endpoint separate
  from chat-routed artifact creation.
- `/api/chat` is the canonical JSON path for ordinary turns and all structured
  decisions. `/api/chat/stream` is SSE for ordinary conversational turns only.

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

### Chat-Turn Lifecycle

The production chat lifecycle is owned by `_execute_chat` in `main.py` and
`AgentColTurnService`.

1. The handler resolves the effective user ID and project ID from the supplied
   `ChatRequest` locators plus the configured auth mode.
2. Structured decision requests are detected before streaming starts. If the
   caller used `/api/chat/stream`, the request is rejected with `409`.
3. Google OIDC chat requires an `Idempotency-Key`. Structured/effect decisions
   also require an idempotency key because they can mutate governed state.
4. When an idempotency key is present, the backend validates the key, verifies
   workspace visibility for the effective user/project, and claims or replays a
   durable chat turn through `MemoryEngine.claim_chat_turn`.
5. Pre-flight structured decisions can approve/reject governed memory,
   resolve memory clarifications, resolve continuity choices, approve/reject
   collaborative-note proposals, or submit artifact feedback decisions before
   the ordinary response is generated.
6. The backend loads validated chat history, governed memory context,
   continuity context, and hidden working-state context. These inputs are
   server-owned context, not authority for identity or ownership.
7. `AgentColTurnService` constructs a turn command, chooses v4 routing when
   artifact routing is available, falls back/downcasts to v3-compatible expert
   execution for non-artifact specialist work, and runs the ADK responder.
8. `/api/chat` waits for `run_turn`; `/api/chat/stream` iterates
   `stream_turn`, emits provisional `delta` events, and waits for
   `AgentColTurnCompleted`.
9. The canonical `ChatResponse` is assembled from responder text plus action,
   artifact, citation, memory, note, adaptation, continuity, and feedback
   receipts.
10. If a durable chat turn was claimed, `MemoryEngine.complete_chat_turn`
    persists the authoritative model response and effects. Without a claim, the
    model message is saved directly.
11. Preference learning may capture a conservative observation only after a
    clean ordinary turn without pending governed effects.
12. Hidden working-state maintenance runs after canonical chat completion; it
    is failure-tolerant but awaited before the HTTP response returns when
    enabled.
13. The response projection converts internal effective user IDs back to the
    supplied public user locator before returning to the browser.

Reliability behavior in this lifecycle:

- Completed idempotent turns can be replayed instead of run again.
- Live in-progress turns return conflict behavior with retry guidance.
- Expired/resumable turns can carry precompleted effects forward.
- Timeout and service-error branches attempt to release or complete turn claims
  safely and can return typed partial-failure payloads when effects were already
  persisted.
- The final JSON `ChatResponse` or SSE `final` event is the durable client
  truth. SSE deltas are UI latency hints only.

### Routing Details

- v4 routing is the current artifact-aware routing path used by the turn
  service when artifact creation is available.
- v3 routing remains current for non-artifact expert directive execution and
  compatibility with `AgentColExpertExecutorV3`.
- `agent_col_routing.py` is still production-relevant for shared primitives and
  URL candidate projection used by v3/v4 code.
- v1/v2 provider/executor/responder-context files are retained for tests,
  migration coverage, or live checks, but they are not the primary path wired by
  `main.py`.
- Routing providers use the Vertex/GenAI SDK structured-output boundary and the
  configured Gemini model name in the provider modules.
- Routing results are not trusted as final answers. They select allowed
  execution paths; the responder and server-side validation determine the
  public response and persisted receipts.

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

Specialist execution boundary:

- Source expert execution validates source-oriented requests and returns
  bounded, source-attributed findings for responder use.
- Research expert execution uses Google Search-grounded GenAI service logic and
  fails closed when grounded evidence is missing or invalid.
- Computational expert execution is isolated behind computation request/result
  models and service-level validation.
- Requirements verification checks candidate work against requirements-oriented
  contracts and returns evidence/coverage signals.
- Expert outputs are receipts/context for Agent Col. They do not directly
  mutate user ownership, memory authority, or final response truth unless the
  server turns them into validated persisted effects.

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

Governed-memory lifecycle:

- Memory proposal generation is governed by `memory_policy.py` and normalized
  by candidate/proposal helpers before it can become user-visible.
- Natural chat can surface proposals or clarification choices, but active
  memory changes require explicit user approval or clarified selection.
- Approval/rejection decisions are structured chat turns through `/api/chat`,
  not free-form text handled by the streaming endpoint.
- Revocation and deletion are explicit HTTP mutations under
  `/api/users/{user_id}/memory/signals/{signal_id}`.
- Memory inspection projects active profile state, unresolved proposals,
  clarifications, and event provenance for the resolved user.
- Adaptation receipts are derived from governed profile context; a model cannot
  unilaterally create permanent memory or preferences.

Collaborative-note lifecycle:

- Notes are workspace-scoped and proposal-driven.
- Explicit proposal and correction endpoints create pending proposals.
- Chat can also create note proposals through the turn service when policy and
  routing choose that path.
- Note approve/reject decisions are structured chat turns through `/api/chat`.
- Archive, restore, and delete are HTTP lifecycle operations protected by the
  expected revision in `CollaborativeNoteMutationRequest`.
- Note list/detail responses include public owner projection and event
  provenance suitable for the browser notes drawer.

Continuity behavior:

- Continuity uses prior chat/session data and active notes to resolve user
  references to earlier work.
- When resolution is ambiguous, the backend returns bounded choices and waits
  for a structured continuity selection.
- Continuity selections are accepted only on `/api/chat`; the streaming
  endpoint rejects them as structured decisions.
- Continuity context is server-validated context for the responder. It is not
  an ownership boundary and does not override current source truth.

Working-state behavior:

- Working state is hidden, same-session context stored under the chat/session
  scope.
- It is explicitly non-authoritative and excluded from user-visible memory.
- The update service receives delimited inputs and server-owned identifiers,
  then stores only validated snapshot fields.
- Working-state update failure is logged and non-fatal, but the update call is
  awaited after canonical response persistence when the feature is enabled.

Preference-learning behavior:

- Preference observations and hypotheses are stored separately from governed
  memory.
- Current extraction is intentionally narrow. Source inspection shows an
  explicit concise/shorter-language trigger path rather than broad preference
  inference.
- A surfaced hypothesis must pass confirmation through governed memory before
  it becomes an active adaptation source.

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

Artifact lifecycle details:

- Blueprint synthesis and generic single-file artifact creation are separate
  artifact families.
- `/api/synthesize` creates blueprint artifacts directly from a
  `SynthesisRequest`.
- Chat-routed artifact creation goes through v4 routing and
  `AgentColArtifactExecutor`.
- Generic artifact creation through `/api/projects/{project_id}/artifacts`
  uses request-bound GenAI generation and `GenericArtifactCreationService`.
- Generic artifact read/lifecycle/versioning routes are implemented by
  `GenericArtifactReadService`.
- Generic artifact versions are new artifact records linked to a parent
  artifact, not in-place overwrites.
- Artifact feedback is project/blueprint-scoped. Feedback can be submitted
  through chat decisions and listed through the blueprint feedback endpoint.
- Artifact generation is currently synchronous/request-bound. There is no
  production background job route in `main.py`.

### Persistence Model

`database.py` uses Firestore collections for:

- `sessions/{session_id}` for chat session metadata, owner/project scope, last
  preview state, active memory clarification pointers, and last completed turn.
- `sessions/{session_id}/messages/{message_id}` for chronological user/model
  transcript messages.
- `sessions/{session_id}/turns/{turn_id}` for durable idempotent turn claims,
  leases, request fingerprints, deterministic message IDs, structured decision
  payloads, precompleted effects, completion metadata, and replay state.
- `sessions/{session_id}/memory_clarifications/{clarification_id}` for durable
  memory clarification envelopes tied to a session/workspace/user.
- `sessions/{session_id}/working_state/current` for hidden same-session working
  state.
- `users/{user_id}/workspaces` for workspace containers.
- `users/{user_id}/workspaces/{workspace_id}/collaborative_notes` and related
  note proposal/event collections.
- `users/{user_id}/workspaces/{workspace_id}/preference_*` records.
- `projects/{project_id}/blueprints` for synthesis blueprint artifacts.
- `projects/{project_id}/blueprints/{blueprint_id}/feedback` and feedback
  supersession data for artifact feedback.
- `projects/{project_id}/artifacts` for generic single-file artifacts,
  lifecycle state, metadata, and version links.
- governed memory signals, proposals, clarifications, and events.

The API resolves effective user and project IDs from auth context before
touching owner-scoped data.

Owner and authority relationships:

- Authenticated principal resolution happens in `auth.py`; Firestore paths use
  effective internal user/project IDs after that resolution.
- Public API projections convert internal Google-derived user IDs back to the
  opaque public locator supplied by the browser.
- Workspace IDs are visible project scopes for chat/notes/work panels.
- Project artifact paths are project-scoped; user identity is additionally
  resolved for artifact creation and version creation because those operations
  create user-attributed records.
- Model-generated text, routing output, continuity context, working state, and
  frontend state are not ownership authority.

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

### Frontend Endpoint Map

| Frontend module/function area | Backend endpoint family | Behavior |
| --- | --- | --- |
| `frontend/auth-view.mjs`, `frontend/api.mjs` auth helpers | `/api/auth/config`, `/api/auth/session` | Loads auth mode, renders Google Sign-In when required, and maps session context to public user/project/workspace locators. |
| Workspace panel in `frontend/app.mjs` and workspace view modules | `/api/users/{user_id}/workspaces` | Lists, creates, deletes, and switches visible workspaces; switching resets scoped conversation/panel state. |
| Chat submit/retry in `frontend/app.mjs` | `/api/chat` or `/api/chat/stream` selected by `frontend/requests.mjs` | Ordinary chat uses SSE streaming; structured decisions and retries with structured payloads use canonical JSON. Retry preserves the saved request and idempotency key. |
| Chat transcript in `frontend/chat-view.mjs` and `frontend/state.mjs` | `/api/users/{user_id}/projects/{project_id}/chat-sessions` | Lists and loads durable chat sessions and rebuilds transcript state from stored messages/receipts. |
| Memory drawer in `frontend/memory-view.mjs` | `/api/users/{user_id}/memory`, memory signal revoke/delete routes, structured `/api/chat` decisions | Displays active memory/proposals/events; revoke/delete call direct HTTP mutations; approve/reject/clarification selections use structured chat. |
| Notes drawer in `frontend/notes-view.mjs` | `/api/users/{user_id}/projects/{project_id}/notes/*`, structured `/api/chat` decisions | Lists notes, loads detail/events, creates proposals/corrections, applies archive/restore/delete, and routes proposal decisions through JSON chat. |
| Work/artifacts surface in `frontend/work-view.mjs` | `/api/projects/{project_id}/blueprints/*`, `/api/projects/{project_id}/artifacts/*` | Lists blueprint and generic artifacts, loads details, creates generic artifacts, archives/restores/deletes generic artifacts, edits metadata, creates versions, exports content, and lists blueprint feedback. |
| Activity and receipts rendering | Primarily `/api/chat` and `/api/chat/stream` response receipts | Refreshes affected panels after authoritative receipts arrive from the backend. |

Frontend trust and rendering:

- `frontend/api.mjs` only accepts same-origin relative API paths and centralizes
  auth/idempotency headers.
- `frontend/requests.mjs` validates identifiers and keeps structured decision
  payloads mutually exclusive before transport selection.
- `frontend/state.mjs` treats streamed deltas as pending UI state; final server
  responses and refreshed resource fetches are authoritative.
- `frontend/render.mjs` uses text-node helpers, and
  `frontend/markdown-renderer.mjs` implements a bounded Markdown subset with
  safe link protocols.
- Artifact content is rendered as text in code/pre surfaces rather than being
  executed as HTML.

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

### Tests and Protected Invariants

The test suite is broad enough that this map should point future work to
focused checks rather than encouraging a full-suite habit.

- `tests/test_main.py` and related FastAPI tests protect route behavior,
  auth/idempotency failure modes, partial-failure branches, and response
  projections.
- Turn-service tests protect routing orchestration, responder handoff,
  specialist execution receipts, artifact routing, feedback handling, and
  idempotent effect preservation.
- Routing tests protect v3/v4 request/result schemas, bounded projection, URL
  candidate handling, artifact eligibility, and compatibility behavior.
- Memory tests protect candidate normalization, proposal policy, clarification
  lifecycle, approval/rejection, revocation/deletion, and event projection.
- Collaborative-note tests protect proposal derivation, explicit proposal
  creation, corrections, decisions, lifecycle mutations, and revision
  conflicts.
- Continuity tests protect ambiguity detection, note/session matching, explicit
  selections, and bounded receipt/choice behavior.
- Artifact tests protect blueprint read models, generic artifact validation,
  creation/lifecycle/versioning, feedback receipt behavior, and schema
  conflicts.
- Frontend Node tests protect request construction, endpoint selection,
  streaming/error parsing, state transitions, transcript reconstruction, safe
  Markdown rendering, and panel refresh behavior.
- Deployment/configuration tests protect Docker packaging expectations,
  Firestore index shape, environment validation, and documented runtime smoke
  wrappers.

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

Runtime/deployment integration details:

- Cloud Run is the documented production target; the container runs Uvicorn on
  `${PORT:-8080}`.
- `auth.py` rejects Cloud Run startup in `local_dev` mode by checking the Cloud
  Run runtime signal and requiring Google OIDC configuration.
- No Gemini API key path is documented as production configuration. The
  repository uses Google Cloud project/location/enterprise GenAI settings and
  Application Default Credentials or service identity.
- Firestore access is through the configured Google credentials/service
  identity, with index configuration kept in `firestore.indexes.json`.
- Rate limiting and body-size/security middleware are implemented in `main.py`
  before route handlers run.

### Production, Compatibility, and Legacy Code Boundaries

Current production path:

- `main.py` imports and wires `AgentColExpertExecutorV3`,
  `create_responder_app`, `SupervisorRuntime`, and `AgentColTurnService`.
- `AgentColTurnService` imports current v3 responder/routing context and v4
  artifact routing/provider modules.
- `agent_col_routing_v4.py` and `agent_col_routing_provider_v4.py` are current
  for artifact-capable routing.
- `agent_col_routing_v3.py`, `agent_col_routing_provider_v3.py`,
  `agent_col_responder_context_v3.py`, and
  `agent_col_expert_executor_v3.py` are current for non-artifact expert
  execution.
- `supervisor_runtime.py` is the production ADK runner wrapper used by the turn
  service.

Compatibility/test-retained code:

- `agent_col_routing.py` remains production-relevant for shared primitives even
  though it is not the newest route schema.
- `agent_col_routing_v2.py` remains referenced by current v3/v4 model code for
  shared model pieces.
- v1/v2 provider, executor, and responder-context modules are retained for
  tests/live checks or migration history unless a future cleanup proves they
  are removable.
- `*_routing_check.py`, `*_routing_evaluation.py`, and spike modules are
  evaluation or live-check utilities, not FastAPI route handlers.

### Current Technical Limitations

- Health check is shallow; it does not exercise Vertex AI, Firestore, Gemini,
  ADK, or auth configuration.
- Local-dev auth intentionally trusts validated supplied identifiers. Hosted
  Cloud Run operation is expected to use Google OIDC.
- Rate limiting is in-process and per running instance, not a distributed Cloud
  Run-wide limiter.
- Workspace and chat-session listings use bounded application-side listing and
  filtering paths rather than a fully indexed owner/project query model.
- Preference extraction is currently narrow and recognizes explicit
  concise/shorter correction language; broad preference inference is not
  implemented.
- Hidden working-state update failure is non-fatal, but when enabled the update
  is awaited after canonical chat persistence before the HTTP response returns.
- Generic artifacts have archive/restore/delete/metadata/version APIs.
  Blueprint artifacts expose list/detail/feedback routes in `main.py`; matching
  blueprint lifecycle mutation routes are not registered.
- Artifact generation is synchronous/request-bound; no background job API is
  registered.

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
