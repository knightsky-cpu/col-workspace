# Repository Map

This map describes the current repository from source and tests. It is an
engineering reference for future sessions, not a development plan and not a
copy of historical documentation.

## Current System Overview

Agent Col is a FastAPI backend with a static vanilla JavaScript workspace UI.
The backend owns authentication, workspace ownership, Firestore persistence,
chat-turn idempotency, routing, expert execution, responder generation, memory,
collaborative notes, continuity, hidden working state, preference learning, and
artifacts. Startup wires the Gemini client, Firestore-backed services, routing
providers, expert executor, responder runtime, and turn service in
`main.py:1280-1400`. The frontend is served at `/workspace`, with static assets
mounted from `frontend/` at `/static/agent-col` in `main.py:1403-1417`.

The primary runtime path is `POST /api/chat`. It validates auth and ownership,
claims or replays an idempotent chat turn, loads governed context, handles
structured decisions, routes ordinary turns, executes zero or one specialist,
runs the responder, persists the canonical response, optionally updates hidden
working state, and returns a public response projection (`main.py:2759-3852`).

Runtime model access is Vertex AI Gemini/ADK. Vertex configuration requires a
Google Cloud project, `GOOGLE_CLOUD_LOCATION=global`, and
`GOOGLE_GENAI_USE_ENTERPRISE=true` (`vertex_config.py:25-53`). The container is
Python 3.14 slim, runs as a non-root `appuser`, exposes port 8080, and starts
`uvicorn main:app` on `${PORT:-8080}` (`Dockerfile:3-22`).

## Repository and Module Map

- Backend entry/config: `main.py`, `database.py`, `schemas.py`, `auth.py`,
  `vertex_config.py`, `chat_turns.py`.
- Turn orchestration/routing/responder: `agent_col_turn_service.py`,
  `agent_col_routing.py`, `agent_col_routing_v2.py`,
  `agent_col_routing_v3.py`, `agent_col_routing_v4.py`,
  `agent_col_routing_provider.py`, `agent_col_routing_provider_v2.py`,
  `agent_col_routing_provider_v3.py`, `agent_col_routing_provider_v4.py`,
  `agent_col_expert_executor.py`, `agent_col_expert_executor_v2.py`,
  `agent_col_expert_executor_v3.py`, `agent_col_responder.py`,
  `agent_col_responder_context.py`, `agent_col_responder_context_v2.py`,
  `agent_col_responder_context_v3.py`, `supervisor.py`,
  `supervisor_runtime.py`, `expert_contracts.py`, `expert_delegation.py`.
- Specialists: `source_expert.py`, `source_expert_service.py`,
  `source_expert_runtime.py`, `research_expert.py`,
  `research_expert_service.py`, `research_expert_runtime.py`,
  `computational_expert.py`, `computational_expert_service.py`,
  `requirements_verification.py`, `requirements_verification_service.py`.
- Memory: `trusted_memory_service.py`, `memory_policy.py`,
  `memory_context.py`, `memory_candidate_normalization.py`,
  `memory_candidate_decisions.py`, `memory_clarifications.py`,
  `memory_proposals.py`, `memory_proposal_tool.py`.
- Notes: `collaborative_note_service.py`, `collaborative_note_policy.py`,
  `collaborative_notes.py`, `collaborative_note_tool.py`.
- Continuity: `continuity.py`, `continuity_service.py`.
- Working state: `working_state.py`, `working_state_service.py`.
- Preference learning: `preference_learning.py`,
  `preference_learning_service.py`, `synthesis_personalization.py`.
- Artifacts: `synthesis.py`, `synthesis_schema.py`,
  `synthesis_service.py`, `blueprint_validation.py`,
  `artifact_read_service.py`, `artifact_feedback_service.py`,
  `generic_artifact_generation.py`, `generic_artifact_service.py`,
  `generic_artifact_creation_service.py`,
  `agent_col_artifact_executor.py`,
  `agent_col_artifact_feedback_executor.py`.
- Frontend: `frontend/index.html`, `frontend/app.mjs`,
  `frontend/state.mjs`, `frontend/api.mjs`, `frontend/requests.mjs`,
  `frontend/render.mjs`, `frontend/chat-view.mjs`,
  `frontend/work-view.mjs`, `frontend/memory-view.mjs`,
  `frontend/notes-view.mjs`, `frontend/chats-view.mjs`,
  `frontend/workspace-view.mjs`, `frontend/auth-view.mjs`,
  `frontend/workspace-layout.mjs`, `frontend/workspace-indicator.mjs`,
  `frontend/activity-view.mjs`, `frontend/markdown-renderer.mjs`,
  `frontend/styles.css`.

## Backend Architecture

`main.py` is the HTTP and dependency-injection composition root. Its lifespan
function creates the GenAI client, Firestore `MemoryEngine`, synthesis services,
artifact services, memory/note/continuity/working-state/preference services,
specialist services, v3/v4 routing providers, expert executor, responder
runtime, and `AgentColTurnService` (`main.py:1280-1400`).

HTTP handlers resolve authenticated effective user/project identifiers,
validate request idempotency keys for state-changing operations, invoke service
objects, project private IDs back to public IDs, and map service exceptions to
controlled HTTP errors (`main.py:464-531`, `main.py:534-723`,
`main.py:1193-1277`).

The turn service coordinates routing, expert execution, artifact creation,
artifact feedback, and responder generation. Its default routing is v3, while
artifact-capable routing uses v4 (`agent_col_turn_service.py:271-320`). Turn
timeouts are bounded at 90 seconds overall, 15 seconds for routing, 45 seconds
for expert work, and 20 seconds reserved for responder work
(`agent_col_turn_service.py:96-100`).

## Frontend Architecture

The UI is a static ES module application. `frontend/index.html:1-9` loads
`app.mjs` and CSS; the HTML shell includes workspace, work/artifacts, notes,
memory, chats, conversation, composer, retry, memory clarification, and
continuity regions (`frontend/index.html:29-260`).

Application state lives in `frontend/state.mjs`. It stores auth/context,
transcript, pending turn, retry failure, active memory clarification, active
continuity choices, workspace/work/memory/notes/chats panel state, activity,
and disclosure state (`frontend/state.mjs:4-60`). Context acceptance initializes
workspace mode, user/project/auth token, and a generated session ID
(`frontend/state.mjs:79-94`). Workspace switching resets scoped conversation
and panel state (`frontend/state.mjs:190-219`).

`frontend/app.mjs` wires bootstrap, panel loading, chat submission, structured
decision submission, workspace operations, artifact operations, memory
operations, and note operations (`frontend/app.mjs:315-1318`). API calls are
centralized in `frontend/api.mjs`, which asserts same-origin relative paths,
normalizes errors, and attaches content type, auth token, and idempotency
headers (`frontend/api.mjs:13-119`).

Rendering is DOM-safe by default. Helpers use `textContent`
(`frontend/render.mjs:1-25`), the markdown renderer only permits a bounded
subset with safe `http`, `https`, and `mailto` links
(`frontend/markdown-renderer.mjs:3-28`, `frontend/markdown-renderer.mjs:163-252`),
and artifact content is rendered into text nodes inside `<pre><code>`
(`frontend/work-view.mjs:468-491`).

## Complete HTTP API Inventory

Auth model: in `local_dev`, supplied IDs are accepted; in `google_oidc`,
bearer-token auth is required and user/project ownership is enforced by
`Authenticator.resolve_user_id` and `resolve_project_id`
(`auth.py:160-175`, `auth.py:215-251`, `main.py:504-531`).

| Method | Exact path | Auth requirement | Request/body model | Response model | Ownership/authorization checks | Major side effects | Primary handler/service | Frontend caller |
|---|---|---|---|---|---|---|---|---|
| GET | `/workspace` | None | None | HTML file | None | None | `workspace` serves `frontend/index.html` (`main.py:1412-1417`) | Browser entry |
| GET | `/` | None | None | `dict[str,str]` | None | None | `health_check` (`main.py:1420-1422`) | none |
| GET | `/api/auth/config` | None | None | `dict[str,object]` | None | None | `auth_config` (`main.py:1425-1434`) | `getAuthConfig` (`frontend/api.mjs:135-142`), bootstrap (`frontend/app.mjs:315-357`) |
| GET | `/api/auth/session` | Local: none; Google: bearer token | None | `principal.public_dict()` | Google token verification/session (`auth.py:160-213`) | None | `auth_session` (`main.py:1437-1449`) | `getAuthSession` (`frontend/api.mjs:121-132`) |
| GET | `/api/users/{user_id}/memory` | User auth | Query `after_event_id` | `MemoryInspectionResponse` | Resolves effective user (`main.py:1456-1469`) | None | `memory_service.inspect_memory` (`main.py:1470-1489`) | `inspectMemory` (`frontend/api.mjs:361-372`), `loadMemory` (`frontend/app.mjs:529-547`) |
| GET | `/api/users/{user_id}/workspaces` | User auth | Query `limit` | `WorkspaceListResponse` | Resolves effective user and request workspace defaults (`main.py:1496-1513`) | None | `db.list_workspaces` (`main.py:1514-1528`) | `listWorkspaces` (`frontend/api.mjs:375-386`), `loadWorkspaces` (`frontend/app.mjs:431-450`) |
| POST | `/api/users/{user_id}/workspaces` | User auth | `WorkspaceCreateRequest` | `WorkspaceCreateResponse` | Resolves effective user; derives workspace ID from default/display name (`main.py:1534-1555`) | Creates user workspace doc | `db.create_workspace` (`main.py:1556-1569`) | `createWorkspace` (`frontend/api.mjs:389-405`), handler (`frontend/app.mjs:747-768`) |
| DELETE | `/api/users/{user_id}/workspaces/{workspace_id}` | User auth | None | 204 response | Resolves effective user and default workspace (`main.py:1576-1593`) | Deletes non-default workspace or tombstones default; refuses last workspace | `db.delete_workspace` (`main.py:1594-1618`) | `deleteWorkspace` (`frontend/api.mjs:408-421`), handler (`frontend/app.mjs:769-795`) |
| GET | `/api/users/{user_id}/projects/{project_id}/notes` | User + project auth | Query `status_filter`, `limit`, `cursor` | `CollaborativeNoteListResponse` | Resolves effective user/project (`main.py:1646-1670`) | None | `collaborative_note_service.list_notes` (`main.py:1671-1695`) | `listNotes` (`frontend/api.mjs:462-480`), `loadNotes` (`frontend/app.mjs:549-568`) |
| GET | `/api/users/{user_id}/projects/{project_id}/notes/{note_id}` | User + project auth | Query `limit` | `CollaborativeNoteDetailResponse` | Resolves effective user/project (`main.py:1702-1722`) | None | `collaborative_note_service.get_note` (`main.py:1723-1746`) | `getNote` (`frontend/api.mjs:482-497`), `loadNoteDetail` (`frontend/app.mjs:570-591`) |
| POST | `/api/users/{user_id}/projects/{project_id}/notes/proposals` | User + project auth; requires `Idempotency-Key` | `CollaborativeNoteProposalRequest` | `CollaborativeNoteProposalResponse` | Validates idempotency and resolves user/project (`main.py:1753-1788`) | Creates pending note proposal | `collaborative_note_service.create_proposal` (`main.py:1789-1809`) | `createNoteProposal` (`frontend/api.mjs:524-543`), handler (`frontend/app.mjs:1127-1154`) |
| POST | `/api/users/{user_id}/projects/{project_id}/notes/{note_id}/corrections` | User + project auth; requires `Idempotency-Key` | `CollaborativeNoteCorrectionRequest` | `CollaborativeNoteProposalResponse` | Validates idempotency and resolves user/project (`main.py:1816-1852`) | Creates pending correction proposal | `collaborative_note_service.create_correction` (`main.py:1853-1878`) | `createNoteCorrection` (`frontend/api.mjs:500-521`), handler (`frontend/app.mjs:1100-1125`) |
| POST | `/api/users/{user_id}/projects/{project_id}/notes/{note_id}/archive` | User + project auth | `CollaborativeNoteMutationRequest` | `CollaborativeNoteLifecycleResponse` | Shared lifecycle resolver validates user/project and expected revision (`main.py:1881-1928`) | Archives note and writes event | `collaborative_note_service.archive_note` (`main.py:1931-1954`) | `archiveNote` (`frontend/api.mjs:546-562`), handler (`frontend/app.mjs:1156-1197`) |
| POST | `/api/users/{user_id}/projects/{project_id}/notes/{note_id}/restore` | User + project auth | `CollaborativeNoteMutationRequest` | `CollaborativeNoteLifecycleResponse` | Shared lifecycle resolver validates user/project and expected revision (`main.py:1881-1928`) | Restores note and writes event | `collaborative_note_service.restore_note` (`main.py:1957-1980`) | `restoreNote` (`frontend/api.mjs:565-581`), handler (`frontend/app.mjs:1156-1197`) |
| DELETE | `/api/users/{user_id}/projects/{project_id}/notes/{note_id}` | User + project auth | `CollaborativeNoteMutationRequest` | 204 response | Resolves effective user/project and expected revision (`main.py:1987-2007`) | Deletes note doc and writes delete event | `collaborative_note_service.delete_note` (`main.py:2008-2025`) | `deleteNote` (`frontend/api.mjs:584-600`), handler (`frontend/app.mjs:1156-1197`) |
| GET | `/api/users/{user_id}/projects/{project_id}/chat-sessions` | User + project auth | Query `limit` | `ChatSessionListResponse` | Resolves effective user/project (`main.py:2032-2051`) | None | `db.list_chat_sessions` (`main.py:2052-2070`) | `listChatSessions` (`frontend/api.mjs:603-617`), `loadChatSessions` (`frontend/app.mjs:593-610`) |
| GET | `/api/users/{user_id}/projects/{project_id}/chat-sessions/{session_id}` | User + project auth | Query `limit` | `ChatSessionDetailResponse` | Resolves effective user/project; DB validates session ownership (`main.py:2076-2104`, `database.py:1475-1585`) | None | `db.get_chat_session_detail` (`main.py:2097-2126`) | `getChatSession` (`frontend/api.mjs:619-635`), `loadChatSession` (`frontend/app.mjs:612-631`) |
| POST | `/api/users/{user_id}/memory/signals/{signal_id}/revoke` | User auth | None | `MemoryMutationResponse` | Resolves effective user; service validates signal ownership/category (`main.py:2132-2145`, `database.py:6669-6817`) | Revokes active memory signal and writes memory event/profile revision | `memory_service.revoke_memory_signal` (`main.py:2146-2173`) | `revokeMemorySignal` (`frontend/api.mjs:424-437`), handler (`frontend/app.mjs:1199-1215`) |
| DELETE | `/api/users/{user_id}/memory/signals/{signal_id}` | User auth | None | 204 response | Resolves effective user; service validates signal locator (`main.py:2180-2193`, `database.py:6819-6968`) | Removes owned memory proposal/origin/events and updates profile projection | `memory_service.delete_memory_signal` (`main.py:2194-2208`) | `deleteMemorySignal` (`frontend/api.mjs:440-453`), handler (`frontend/app.mjs:1217-1233`) |
| POST | `/api/synthesize` | User + project auth via body IDs | `SynthesisRequest` | `SynthesisResponse` | Resolves `payload.user_id` and `payload.project_id` (`main.py:2211-2230`) | Creates blueprint artifact | `synthesis_service.synthesize` (`main.py:2232-2256`) | none |
| GET | `/api/projects/{project_id}/blueprints` | Project auth | Query `limit`, `before` | `BlueprintArtifactListResponse` | Resolves effective project (`main.py:2263-2277`) | None | `artifact_service.list_blueprints` (`main.py:2278-2302`) | `listBlueprints` (`frontend/api.mjs:192-204`), `loadWorkList` (`frontend/app.mjs:452-492`) |
| GET | `/api/projects/{project_id}/blueprints/{blueprint_id}` | Project auth | None | `BlueprintArtifactDetailResponse` | Resolves effective project (`main.py:2308-2321`) | None | `artifact_service.get_blueprint` (`main.py:2322-2352`) | `getBlueprint` (`frontend/api.mjs:206-219`), `loadWorkDetail` (`frontend/app.mjs:494-527`) |
| GET | `/api/projects/{project_id}/artifacts` | Project auth | Query `limit`, `before`, `lifecycle_status` | `SingleFileArtifactListResponse` | Resolves effective project (`main.py:2358-2376`) | None | `generic_artifact_service.list_artifacts` (`main.py:2377-2402`) | `listArtifacts` (`frontend/api.mjs:238-250`), `loadWorkList` (`frontend/app.mjs:452-492`) |
| POST | `/api/projects/{project_id}/artifacts` | User + project auth | `SingleFileArtifactCreateRequest` | `SingleFileArtifactCreateResponse` | Resolves payload user and path project (`main.py:2408-2426`) | Generates and persists single-file artifact | `generic_artifact_generator` + `generic_artifact_creation_service.create_artifact` (`main.py:2427-2468`) | `createArtifact` (`frontend/api.mjs:268-285`), handler (`frontend/app.mjs:844-864`) |
| GET | `/api/projects/{project_id}/artifacts/{artifact_id}` | Project auth | None | `SingleFileArtifactDetailResponse` | Resolves effective project (`main.py:2474-2487`) | None | `generic_artifact_service.get_artifact` (`main.py:2488-2511`) | `getArtifact` (`frontend/api.mjs:252-265`), `loadWorkDetail` (`frontend/app.mjs:494-527`) |
| POST | `/api/projects/{project_id}/artifacts/{artifact_id}/archive` | Project auth | None | `SingleFileArtifactLifecycleResponse` | Resolves effective project (`main.py:2517-2530`) | Marks generic artifact archived | `generic_artifact_service.archive_artifact` (`main.py:2531-2554`) | `archiveArtifact` (`frontend/api.mjs:287-300`), handler (`frontend/app.mjs:866-883`) |
| POST | `/api/projects/{project_id}/artifacts/{artifact_id}/restore` | Project auth | None | `SingleFileArtifactLifecycleResponse` | Resolves effective project (`main.py:2560-2573`) | Marks generic artifact active | `generic_artifact_service.restore_artifact` (`main.py:2574-2597`) | `restoreArtifact` (`frontend/api.mjs:303-316`), handler (`frontend/app.mjs:885-902`) |
| PATCH | `/api/projects/{project_id}/artifacts/{artifact_id}/metadata` | Project auth | `SingleFileArtifactMetadataUpdateRequest` | `SingleFileArtifactLifecycleResponse` | Resolves effective project (`main.py:2603-2617`) | Updates mutable artifact display label/filename | `generic_artifact_service.update_artifact_metadata` (`main.py:2618-2646`) | `updateArtifactMetadata` (`frontend/api.mjs:319-337`), handler (`frontend/app.mjs:904-925`) |
| POST | `/api/projects/{project_id}/artifacts/{artifact_id}/versions` | User + project auth | `SingleFileArtifactEditRequest` | `SingleFileArtifactCreateResponse` | Resolves payload user and path project (`main.py:2652-2671`) | Creates child/revised generic artifact version | `generic_artifact_service.create_artifact_version` (`main.py:2672-2705`) | `createArtifactVersion` (`frontend/api.mjs:340-358`), handler (`frontend/app.mjs:927-952`) |
| GET | `/api/projects/{project_id}/blueprints/{blueprint_id}/feedback` | Project auth | Query `limit`, `before` | `BlueprintArtifactFeedbackListResponse` | Resolves effective project (`main.py:2711-2726`) | None | `artifact_feedback_service.list_feedback` (`main.py:2727-2757`) | `listBlueprintFeedback` (`frontend/api.mjs:222-236`), `loadWorkDetail` (`frontend/app.mjs:494-527`) |
| POST | `/api/chat` | Local: optional idempotency; Google: bearer + idempotency; structured decisions require idempotency | `ChatRequest` | `ChatResponse` or partial failure JSON | Resolves user/project, validates idempotency, claims/replays turn, validates session ownership (`main.py:2759-2916`) | Persists user/model messages, turn records, memory/note/artifact/feedback effects, preference observations, working state | `chat` + `AgentColTurnService` (`main.py:2918-3852`) | `apiFetchJson("/api/chat")` (`frontend/app.mjs:634-671`) |

## Persistence and Data Relationships

- `sessions/{session_id}`: chat session metadata with `project_id`,
  `user_id`, timestamps, last preview/role, and `last_completed_turn_id`.
  Messages are child docs at `sessions/{session_id}/messages/{message_id}`
  with `role`, `text`, and `timestamp` (`database.py:331-399`,
  `database.py:1475-1585`, `database.py:3073-3171`).
- `sessions/{session_id}/turns/{turn_id}`: durable idempotent turn records.
  They store schema/status, project/user, structured decision payloads,
  deterministic user/model message IDs, lease owner/expiry, and later
  receipts/effects plus completion metadata (`database.py:1587-1905`,
  `database.py:3073-3171`).
- `sessions/{session_id}/memory_clarifications/{clarification_id}`: durable
  clarification envelopes tied to a session/workspace/user. Parent session
  pointer fields include `active_memory_clarification_id`,
  `last_consumed_memory_clarification_id`, and
  `last_consuming_memory_turn_id` (`database.py:5436-5580`,
  `database.py:6012-6366`).
- `sessions/{session_id}/working_state/current`: hidden current-session
  working-state snapshot, saved only after validating chat session ownership
  (`database.py:5042-5118`).
- `users/{user_id}`: collaboration profile and memory projection fields,
  including memory revision, identity context, active preferences, and user
  metadata. Memory approval/revocation updates this document
  (`database.py:6388-6567`, `database.py:6669-6817`,
  `database.py:7420-7429`).
- `users/{user_id}/workspaces/{workspace_id}`: user-owned workspace documents.
  Default workspaces can be synthesized unless tombstoned; non-default
  workspaces are created or deleted as child docs (`database.py:471-677`).
- `users/{user_id}/memory_proposals/{category}`: category-slot memory
  proposals. V2 guarded proposals include source session/message, evidence
  message, clarification ID, expected active signal, status, and expiration
  (`database.py:5385-5435`, `database.py:5849-6010`).
- `users/{user_id}/memory_proposal_origins/{origin_id}`: deterministic
  provenance guard docs mapping source/evidence/clarification to a proposal and
  category, preventing conflicting proposals from the same source
  (`database.py:5605-5620`, `database.py:5867-6004`,
  `memory_proposals.py:17-68`).
- `users/{user_id}/memory_events/{event_id}`: immutable memory lifecycle
  events for approved, corrected, superseded, and revoked signals. Deletion
  removes owned proposal/origin/event artifacts and updates the projected
  profile (`database.py:6388-6567`, `database.py:6669-6968`).
- `users/{user_id}/workspaces/{workspace_id}/note_proposals/{proposal_id}`:
  pending/resolved collaborative note proposals with 24-hour expiry, grounded
  to session/message IDs and optional expected note/revision
  (`database.py:679-857`).
- `users/{user_id}/workspaces/{workspace_id}/collaborative_notes/{note_id}`:
  active/archived notes owned by user/workspace with revision and source event
  metadata; child events live at `events/{event_id}` (`database.py:859-1120`,
  `database.py:1122-1331`).
- `users/{user_id}/workspaces/{workspace_id}/preference_observations/{observation_id}`
  and `preference_hypotheses/{hypothesis_id}`: non-authoritative
  workspace-scoped preference learning records (`database.py:5119-5238`).
- `projects/{project_id}`: project aggregate metadata updated when artifacts or
  feedback are written (`database.py:2279-2460`, `database.py:4051-4179`,
  `database.py:4321-4617`).
- `projects/{project_id}/blueprints/{blueprint_id}`: synthesis blueprint
  artifacts with contract/schema, originating session/turn/user, feedback
  counts, adaptation receipts, applied feedback IDs, and blueprint payload
  (`database.py:2279-2460`, `database.py:4051-4109`,
  `database.py:4627-4962`).
- `projects/{project_id}/artifacts/{artifact_id}`: generic single-file
  artifacts with contract/schema, originating session/turn/user, lifecycle
  status, optional parent artifact ID, filename/family/format/content/summary
  (`database.py:2461-2638`, `database.py:4111-4319`,
  `database.py:4697-4798`).
- `projects/{project_id}/blueprints/{blueprint_id}/feedback/{feedback_id}`:
  immutable blueprint feedback events. Supersession links live in sibling
  `feedback_supersessions/{supersedes_feedback_id}` and update blueprint
  feedback counts (`database.py:2639-2995`, `database.py:4321-4617`,
  `database.py:4800-4927`).
- Continuity has no separate persisted collection. It reads persisted active
  notes and prior chat sessions/messages as continuity sources
  (`continuity_service.py:189-239`, `database.py:1173-1203`,
  `database.py:4964-5040`).

## Chat-Turn Lifecycle

`POST /api/chat` first resolves auth and effective user/project. Google-auth
chat requires an idempotency key, and structured decision turns require an
idempotency key (`main.py:2759-2852`). When an idempotency key is present, the
API validates it and calls `database.claim_chat_turn(...)`; a completed matching
turn returns a replay immediately, a live in-progress turn returns conflict,
and an expired in-progress turn can resume with precompleted effects
(`main.py:2853-2916`, `database.py:1587-1905`).

The handler loads history and collaboration profile, validates stored messages,
builds server-validated memory context, and saves the user message when the
turn is not using an existing claim (`main.py:2918-3012`,
`main.py:408-461`). Structured memory, collaborative note, clarification,
continuity, and artifact-feedback decisions are handled before ordinary model
routing (`main.py:3013-3431`).

Ordinary turns optionally load hidden working-state context before generation,
renew the turn lease, merge precompleted receipts, and call
`turn_service.run_turn(...)` (`main.py:3433-3562`). Timeout and service errors
can release the claim or return partial responses with already-persisted
effects (`main.py:3563-3675`, `main.py:984-1142`).

Latency-critical ordering: `/api/chat` does not return immediately after
responder text is produced. The request awaits canonical responder completion,
then authoritative chat persistence, then hidden working-state maintenance if
enabled, and only then returns the HTTP response. Working-state data is
non-authoritative and update failures are swallowed/logged, but the update path
itself is awaited and can contribute to request latency (`main.py:3483-3562`,
`main.py:3785-3852`, `database.py:3073-3171`).

The ordering is:

`canonical responder completion -> authoritative chat persistence -> awaited hidden working-state maintenance -> HTTP response returned`.

## Routing and Specialist Flows

Routing v3 supports `DIRECT`, `CLARIFY`, `SOURCE`, `RESEARCH`, `COMPUTATION`,
and `REQUIREMENTS_VERIFICATION` (`agent_col_routing_v3.py:49-55`). V3 routing
input is bounded and validates unique capabilities, URL IDs, numeric candidate
IDs, text candidate IDs, and route-specific payload shape
(`agent_col_routing_v3.py:90-182`, `agent_col_routing_v3.py:213-249`).

Routing v4 adds `ARTIFACT` and artifact intent. Artifact routing is only valid
when artifact creation is available and no structured decision is already
present; non-artifact v4 directives downcast through v3 validation
(`agent_col_routing_v4.py:34-59`, `agent_col_routing_v4.py:77-215`).

Routing providers call Gemini with structured JSON schemas and then revalidate
locally. Provider prompts delimit routing input as untrusted and forbid the
router from executing tools or persisting state (`agent_col_routing_provider_v3.py:20-53`,
`agent_col_routing_provider_v3.py:182-197`,
`agent_col_routing_provider_v4.py:35-82`,
`agent_col_routing_provider_v4.py:334-349`).

`AgentColExpertExecutorV3` executes at most one specialist and maps outputs into
responder context (`agent_col_expert_executor_v3.py:162-353`). Source expert
analyzes supplied public URLs only (`source_expert_service.py:24-51`).
Research expert uses direct Google Search grounding or ADK execution and
validates grounding (`research_expert_service.py:175-257`). Computational
expert uses a temporary bounded ADK invocation (`computational_expert_service.py:76-138`).
Requirements verification disables tools/search and returns structured results
(`requirements_verification_service.py:27-42`,
`requirements_verification_service.py:89-139`).

## Memory Subsystem

Memory is governed and proposal-based. Policy versions and categories are
explicit; v2 adds explanation pace, learning approach, accessibility support,
development environments, user-requested memory, and domain experience
(`memory_policy.py:9-28`, `memory_policy.py:109-177`).

Natural memory decisions are handled server-side by `TrustedMemoryService`.
Structured memory turns cannot create another proposal, profile candidate
decisions create guarded proposals, ambiguous choices create short-lived
clarification envelopes, and clarification selections require a turn lease
(`trusted_memory_service.py:286-500`). Preference hypotheses can open memory
confirmation as clarification rather than writing durable memory directly
(`trusted_memory_service.py:502-554`).

Proposal IDs and origin IDs are deterministic and validate source/evidence
constraints (`memory_proposals.py:17-68`, `memory_proposals.py:96-160`).
Explicit approve, reject, revoke, and delete paths are separate from natural
chat proposal creation (`trusted_memory_service.py:556-633`).

## Collaborative Notes Subsystem

Collaborative notes are proposal-driven and workspace-scoped. Policy defines
contract version, note kinds/statuses/events, prohibited "note everything"
patterns, and title/body normalization (`collaborative_note_policy.py:8-33`,
`collaborative_note_policy.py:57-143`).

The service supports explicit API proposals, natural chat proposals grounded in
the current message, approve/reject decisions, corrections, and
archive/restore/delete lifecycle (`collaborative_note_service.py:188-331`).
Proposal IDs are stable from user/workspace/session/source messages/note
content/idempotency fields (`collaborative_notes.py:18-68`).

## Continuity Subsystem

Continuity resolves user references to prior notes or chats. Injected
continuity context is server-validated but non-authorizing and untrusted for
truth (`continuity.py:18-94`). The service detects prior-reference language,
resolves explicit user selections, matches active notes by title/token, searches
prior sessions excluding the current one, expands terms with Gemini when useful,
and returns either resolved context or bounded ambiguous choices
(`continuity_service.py:118-239`, `continuity_service.py:282-566`).

## Working-State Subsystem

Working state is hidden, same-session, non-authoritative context. The snapshot
schema carries request summary, current goal, intent hypothesis, constraints,
unresolved questions, next step, confidence, clarification status, and blocking
reason (`working_state.py:11-78`). Rendering wraps it in
`[SERVER_VALIDATED_WORKING_STATE]` and explicitly says it is stale,
non-authoritative, and not user memory (`working_state.py:81-101`).

Working-state updates are gated by route and collaboration markers
(`working_state.py:104-152`). The provider is instructed not to include hidden
chain of thought and receives delimited untrusted inputs; server-owned
user/project/session/source fields are reattached after provider output
(`working_state_service.py:31-65`, `working_state_service.py:179-253`).

Request-latency ordering: `/api/chat` awaits working-state maintenance after
canonical chat completion/persistence and before the HTTP response returns.
Failures are non-fatal and logged, but the maintenance call itself is awaited
(`main.py:3785-3852`). The exact ordering is:

`canonical responder completion -> authoritative chat persistence -> awaited hidden working-state maintenance -> HTTP response returned`.

## Preference-Learning Subsystem

Preference learning is source-backed and conservative. Observations are
non-authoritative, cannot adapt the current response directly, and must match
memory policy dimensions (`preference_learning.py:10-52`). Hypotheses require
enough evidence, sufficient confidence, no contradictions, and recency before
surfacing (`preference_learning.py:54-164`).

The implemented extractor is deterministic and narrow: it recognizes explicit
shorter/concise correction language and maps it to `response_length=concise`
(`preference_learning_service.py:43-73`). Capture failures are logged and
ignored; surfaced hypotheses go through memory clarification confirmation
(`preference_learning_service.py:92-152`, `main.py:3733-3779`).

## Artifact Subsystem

There are two artifact families: synthesis blueprints and generic single-file
artifacts. Schema constants define blueprint schema `2.0` and artifact contract
`1.0`; single-file artifacts validate family, format, filename, content
size/control characters, and JSON parseability where relevant
(`schemas.py:56-57`, `schemas.py:198-325`).

Blueprint synthesis builds a delimited prompt from source text, bounded history,
and profile context, then locally validates provider output against semantic
constraints (`synthesis.py:33-155`, `synthesis.py:158-258`,
`blueprint_validation.py:6-105`). Governed synthesis also derives adaptation
receipts from collaboration profile (`synthesis_service.py:117-152`).

Generic artifact generation is a bounded single-file provider call with
untrusted source/context, no tools/search/persistence/final-answer authority,
and local match validation against requested family/format/filename
(`generic_artifact_generation.py:22-164`). Creation, lifecycle, metadata, and
versioning are service-backed (`generic_artifact_creation_service.py:47-83`,
`generic_artifact_service.py:128-360`).

Artifact feedback resolves canonical blueprint targets, validates expected
schema/version/receipts, writes feedback, and feeds server-validated feedback
context to the responder without letting it mutate memory or global preferences
(`artifact_feedback_service.py:133-338`,
`agent_col_artifact_feedback_executor.py:86-200`).

## Authentication, Security, and Ownership

Auth supports `local_dev` and `google_oidc`. Cloud Run requires
`AGENT_COL_AUTH_MODE=google_oidc` and an OAuth client ID, preventing accidental
local-dev auth in Cloud Run (`auth.py:11-93`). Google subjects are converted to
internal user IDs and public user IDs; workspace ownership accepts the default
workspace or subject-prefixed child workspaces (`auth.py:107-143`).

HTTP middleware adds no-sniff/frame/referrer/permissions headers, sets
no-store for static/workspace responses, enforces per-client/path in-memory rate
limiting, and limits request body size (`main.py:280-405`). Public API
responses project internal effective user IDs back to supplied public user IDs
for chat, sessions, notes, and responses (`main.py:534-723`).

Frontend API requests assert same-origin relative paths and add authorization
and idempotency headers through one helper (`frontend/api.mjs:13-119`). Safe DOM
rendering uses text helpers and bounded markdown rendering
(`frontend/render.mjs:1-25`, `frontend/markdown-renderer.mjs:21-28`,
`frontend/markdown-renderer.mjs:163-252`).

## Frontend State and Rendering Behavior

Request construction is immutable and idempotency-aware. Chat requests validate
identifiers, message text, and mutually exclusive structured decisions; retries
preserve the exact same key/body (`frontend/requests.mjs:35-108`). Continuity
and memory clarification selections become structured chat requests with
generated user-facing messages (`frontend/requests.mjs:248-319`).

Pending turn state preserves retryable request/error metadata and updates
activity (`frontend/state.mjs:302-369`). Chat session detail loading rebuilds
the transcript and can restore active memory clarification state
(`frontend/state.mjs:514-580`). Transcript reconstruction pairs user/model
messages and inserts an empty model response for a dangling user message
(`frontend/state.mjs:671-728`).

Panel views are separated by concern: chat renders transcript, receipts,
clarification choices, continuity choices, pending state, and retry
(`frontend/chat-view.mjs:49-227`); work renders artifacts, export, lifecycle,
metadata, versioning, and feedback (`frontend/work-view.mjs:345-779`); memory
renders active signals/proposals/events (`frontend/memory-view.mjs:67-244`);
notes render proposals, note detail, correction, lifecycle, and events
(`frontend/notes-view.mjs:35-384`).

## Error, Retry, and Idempotency Behavior

Backend chat idempotency uses deterministic turn/user/model IDs from an
idempotency key, a live lease owner token, replay of completed turns, rejection
of live in-progress turns, and resumption of expired turns with precompleted
effects (`database.py:1587-1905`). Completion checks claim ownership, lease
validity, absence of an existing model message, and preserved effects before
writing the model response (`database.py:3073-3171`).

Timeout and service errors preserve completed receipts where possible and can
return partial failure responses with already-persisted actions, artifacts,
feedback, memory, notes, or continuity (`main.py:984-1142`,
`main.py:3563-3675`). Turn service error classes carry completed effects
(`agent_col_turn_service.py:209-258`).

Frontend retry uses the saved request and same idempotency key
(`frontend/requests.mjs:104-108`, `frontend/state.mjs:302-328`,
`frontend/app.mjs:673-725`). API errors normalize timeout messaging and
preserve response details (`frontend/api.mjs:22-75`).

## Deployment and Runtime Integration

Runtime dependencies are FastAPI, Google API Core, Google ADK, Firestore,
Google GenAI, Pydantic, python-dotenv, and Uvicorn (`requirements.txt:1-8`).
The README documents required environment variables, ADC/Vertex/Firestore
expectations, and that no Gemini API key is used (`README.md:112-149`).

Firestore indexes currently define no custom indexes and disable indexing of
the blueprint field for collection-group `blueprints`
(`firestore.indexes.json:1-9`).

## Major End-to-End Flows

Ordinary chat: frontend builds a frozen request with idempotency key, backend
claims the turn, loads context/history, resolves continuity and working state,
routes through v4/v3, executes zero or one expert, runs the responder, persists
the response, awaits hidden working-state maintenance if enabled, and frontend
refreshes work/memory/notes/chats based on receipts (`frontend/requests.mjs:35-108`,
`main.py:2759-3852`, `agent_col_turn_service.py:317-372`,
`frontend/app.mjs:634-671`).

Chat artifact creation: v4 routes artifact intent only when artifact creation
is available and no structured decision is present. Artifact executor creates a
blueprint or single-file artifact, records the turn effect, validates canonical
stored artifact, sends bounded artifact context to the responder, and frontend
refreshes the work panel (`agent_col_routing_v4.py:77-215`,
`agent_col_artifact_executor.py:156-518`, `frontend/app.mjs:634-671`).

Manual artifact creation: frontend work form posts source text/context to the
generic artifact API. Backend generates and persists a single-file artifact,
then frontend reloads active work list/detail (`frontend/work-view.mjs:59-70`,
`frontend/app.mjs:844-961`, `main.py:2404-2468`).

Memory proposal flow: natural/structured decisions create a proposal or
clarification; response carries at most one memory proposal/clarification;
frontend displays it; approve/reject returns through a structured chat decision
(`trusted_memory_service.py:286-591`, `schemas.py:859-895`,
`frontend/memory-view.mjs:123-177`, `frontend/app.mjs:1064-1098`).

Note flow: explicit or natural proposals create pending note proposals;
frontend displays them; approve/reject/correction/lifecycle operations update
notes and activity (`collaborative_note_service.py:188-331`,
`frontend/notes-view.mjs:35-384`, `frontend/app.mjs:1100-1197`).

## Tests and Protected Invariants

Routing tests protect bounded candidate projection, exact ID/span matching, no
fenced requirement leakage, source/computation/requirements schemas, artifact
routing constraints, and v3 compatibility (`tests/test_agent_col_routing_v3.py:60-601`,
`tests/test_agent_col_routing_v4.py:45-261`,
`tests/test_agent_col_text_projection.py:14-117`).

Expert tests protect source grounding, research grounding/retry/failure
cleanup/content-safe diagnostics, computational execution bounds, requirements
validation, and evaluator fixtures (`tests/test_research_expert_service.py:194-862`,
`tests/test_research_expert.py:173-1060`,
`tests/test_tool_belt_routing_evaluation.py:24-592`).

Subsystem tests protect memory normalization/no inference, collaborative note
proposal/lifecycle behavior, artifact read/legacy filtering, artifact feedback
receipt preservation, frontend state/retry/refresh behavior, and safe markdown
rendering (`tests/test_memory_candidate_normalization.py:40-80`,
`tests/test_collaborative_note_service.py:176-509`,
`tests/test_artifact_read_service.py:146-371`,
`tests/test_agent_col_turn_service_feedback.py:87-172`,
`tests/frontend/state.test.mjs:79-1470`,
`tests/frontend/markdown-renderer.test.mjs:81-156`).

## Production, Compatibility, Tests-Only, and Dead-Code Classification

Current production path:

- `main.py` imports `AgentColExpertExecutorV3`, `create_responder_app`,
  `AgentColTurnService`, and `SupervisorRuntime` directly (`main.py:31-43`,
  `main.py:196-197`), then wires them at startup (`main.py:1280-1400`).
- `agent_col_turn_service.py` imports and uses v3 responder
  context/routing/provider and v4 artifact routing/provider
  (`agent_col_turn_service.py:12-60`, `agent_col_turn_service.py:271-320`).
- `agent_col_routing_v4.py` and `agent_col_routing_provider_v4.py` are current
  for artifact-capable routing; `agent_col_turn_service.py:556-668` uses v4
  and downcasts non-artifact routes.
- `agent_col_routing_v3.py`, `agent_col_routing_provider_v3.py`,
  `agent_col_responder_context_v3.py`, and `agent_col_expert_executor_v3.py`
  are current for non-artifact expert routing/execution
  (`agent_col_turn_service.py:39-49`, `agent_col_turn_service.py:929-1130`).
- `supervisor_runtime.py` is current production responder runtime: it is
  imported by `main.py:197`, constructed in `main.py:1344-1345`, and called by
  `agent_col_turn_service.py:88-93`, `agent_col_turn_service.py:428-478`,
  `agent_col_turn_service.py:719-760`, and `agent_col_turn_service.py:1012-1069`.

Compatibility/versioned code still referenced:

- `agent_col_routing.py` is not the primary route schema anymore, but its
  shared primitives/helpers remain production dependencies: v3/v4 routing
  import from it, and the turn service uses `project_routing_url_candidates`
  (`agent_col_routing_v3.py:20-26`, `agent_col_routing_v4.py:8-18`,
  `agent_col_turn_service.py:38`).
- `agent_col_routing_v2.py` is still referenced by current v3/v4 code for
  shared model pieces; v3 imports v2 definitions, and v4/provider-v4 import v2
  constraints/types (`agent_col_routing_v3.py:26`, `agent_col_routing_v4.py:13`,
  `agent_col_routing_provider_v4.py:12`).

Tests-only or live-check-only:

- `agent_col_routing_provider.py` is referenced by tests and
  `live-tests/smoke_test_agent_col_routing.py`, but not by `main.py` or
  `agent_col_turn_service.py` (`tests/test_agent_col_routing_provider.py:59-233`,
  `live-tests/smoke_test_agent_col_routing.py:26-210`).
- `agent_col_routing_provider_v2.py` is referenced by v2 tests/live smoke tests
  only (`tests/test_agent_col_routing_provider_v2.py:45-547`,
  `live-tests/smoke_test_agent_col_routing_v2.py:22-210`).
- `agent_col_expert_executor.py` and `agent_col_responder_context.py` are
  referenced by tests/live tests, not production imports
  (`tests/test_agent_col_expert_executor.py:157-466`,
  `tests/test_agent_col_responder_context.py:97-431`,
  `live-tests/smoke_test_agent_col_expert_executor.py:8-214`).
- `agent_col_expert_executor_v2.py` and `agent_col_responder_context_v2.py` are
  referenced by v2 tests and one live computation smoke test, not production
  imports (`tests/test_agent_col_expert_executor_v2.py:12-522`,
  `tests/test_agent_col_responder_context_v2.py:23-273`,
  `live-tests/smoke_test_agent_col_computation_pipeline.py:13-105`).
- `source_routing_check.py`, `research_routing_check.py`,
  `memory_routing_check.py`, `tool_belt_routing_check.py`,
  `tool_belt_routing_evaluation.py`, `tool_belt_routing_evaluation_v3.py`, and
  `tool_belt_orchestration_check.py` are check/evaluation scripts with
  corresponding tests, not imported by production runtime
  (`tests/test_source_routing_check.py:67-271`,
  `tests/test_research_routing_check.py:64-230`,
  `tests/test_memory_routing_check.py:96-764`).

Apparently unused/dead from production perspective:

- `agent_col_routing_spike.py` is a standalone spike/evaluation module
  referenced by its own tests and fixture loader, with no production imports
  found (`agent_col_routing_spike.py:70-83`,
  `tests/test_agent_col_routing_spike.py:13-481`).
- No production import path was found for v1 provider/executor/responder-context
  modules beyond tests/live checks; treat them as legacy test-covered code
  unless intentionally retained for historical compatibility.

## Current Implemented Capability Inventory

Implemented capabilities include authenticated/local workspace sessions,
durable chat with idempotent retry/replay, v4/v3 model routing, source URL
analysis, grounded research, numeric computation, requirements verification,
responder-only final answers, governed memory proposals/clarifications,
collaborative note proposals/corrections/lifecycle, continuity resolution from
prior chats/notes, hidden working state, conservative preference learning,
blueprint synthesis, generic single-file artifact creation/versioning/lifecycle,
artifact feedback, frontend work/memory/notes/chats panels, and safe markdown
rendering. The backing source paths are the API, service, persistence, and
frontend paths cited above.

## Current Technical Limitations

- Chat session listing scans a bounded 200 sessions and filters/sorts in
  application code, rather than using an indexed owner/project query path
  (`database.py:405-465`).
- Workspace listing similarly scans up to 200 workspace docs and synthesizes the
  default workspace in application logic (`database.py:471-544`).
- Rate limiting is in-process memory keyed by client host/path, not a
  distributed Cloud Run-wide limiter (`main.py:286-303`).
- Local-dev auth trusts supplied user/project identifiers after validation;
  Cloud Run forces Google OIDC, but local/dev mode is intentionally permissive
  (`auth.py:66-93`, `auth.py:215-251`).
- Preference learning currently recognizes only explicit concise/shorter
  correction language (`preference_learning_service.py:43-73`).
- Working-state updates are hidden and failure-tolerant, but when enabled they
  are awaited before the chat HTTP response returns (`main.py:3813-3852`).
- Archived work UI lists archived generic artifacts; blueprint artifacts do not
  expose matching archive/restore APIs in the current frontend path
  (`frontend/app.mjs:452-492`, `main.py:2259-2352`, `main.py:2513-2597`).

## Submission-Freeze Findings

Contest/submission blockers or required remaining work:

- Final hosted/deployment re-verification for the submission freeze: confirm the
  deployed Cloud Run runtime still has Google OIDC auth mode and Vertex global
  enterprise config, because the source enforces those production assumptions
  (`auth.py:66-93`, `vertex_config.py:25-53`, `Dockerfile:20-22`).
- Final smoke verification of the primary demo path: `/workspace` loads the
  static frontend, signs in when Google mode is active, sends `/api/chat`,
  persists the turn, and refreshes work/memory/notes/chats panels
  (`main.py:1412-1417`, `frontend/app.mjs:315-357`,
  `frontend/app.mjs:634-671`, `main.py:2759-3852`).
- Final verification that no stale documentation is used as source of truth for
  submission docs; this map is source-backed and should be the current reference
  for `current-state`, `architecture`, and `submission-checklist`.

Optional/demo-visible polish:

- Improve visible latency communication around the awaited post-completion
  working-state update, since HTTP response return waits for that maintenance
  step when enabled (`main.py:3813-3852`).
- Make generic artifact family/format choices harder to mismatch in the
  frontend; backend validation already rejects mismatches (`schemas.py:328-347`,
  `frontend/work-view.mjs:59-70`).

Post-submission technical debt:

- Distributed rate limiting beyond the current in-memory per-process limiter
  (`main.py:286-303`).
- Indexed/paginated chat-session and workspace listing beyond current bounded
  scans (`database.py:405-544`).
- Broader preference extraction beyond explicit concise/shorter feedback
  (`preference_learning_service.py:43-73`).
- Artifact lifecycle parity if blueprint archive/restore is desired; generic
  artifacts have lifecycle APIs, while blueprints are listed/read/feedback-only
  in the current frontend path (`main.py:2259-2352`, `main.py:2513-2597`,
  `frontend/app.mjs:452-527`).
- Cleanup or archival decision for v1/v2/spike routing/provider/executor
  modules after confirming no historical compatibility requirement remains.
