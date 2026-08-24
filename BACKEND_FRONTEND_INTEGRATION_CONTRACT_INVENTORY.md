# Backend-to-Frontend Integration Contract Inventory

## Status and authority

This document inventories the backend contracts available to the Agent_Col
frontend as of commit
`5b34a407e517eb4335c76f780b789462fbbd466f`. It is a source-grounded reference,
not a proposal for new behavior.

Executable source and accepted repository contracts are authoritative when
they conflict with older status documentation. In particular, portions of
`README.md` and `docs/architecture.md` still describe chat-routed synthesis,
artifact retrieval, artifact feedback, and governed synthesis personalization
as pending even though current source implements those capabilities.

Primary sources for this inventory are:

- `main.py` for the FastAPI application and HTTP error mapping;
- `schemas.py` for public Pydantic contracts;
- `database.py` for Firestore paths and transactional lifecycle behavior;
- `agent_col_turn_service.py` for turn orchestration;
- `agent_col_routing_v3.py` and `agent_col_routing_v4.py` for routing;
- `agent_col_expert_executor_v3.py` for expert execution;
- `synthesis_service.py` and `agent_col_artifact_executor.py` for synthesis;
- `artifact_read_service.py` and `artifact_feedback_service.py` for artifacts;
- `trusted_memory_service.py` and `memory_policy.py` for governed memory;
- `docs/superpowers/specs/2026-08-23-m8-col-1-judge-facing-collaborative-artifact-loop-design.md`
  for the accepted artifact-loop boundary.

## 1. Application architecture boundary

### Frontend/backend communication model

There is currently no frontend application, static-file mount, CORS
middleware, or frontend package manifest.

The implemented backend boundary is:

```text
HTTP JSON client
  -> FastAPI main:app
  -> application services
  -> Vertex AI / Gemini where required
  -> MemoryEngine
  -> Cloud Firestore
```

Requests remain open while routing, expert execution, synthesis, response
generation, and persistence complete. There is no streaming, background job,
WebSocket, polling, or task-status contract.

The browser must never call Vertex AI or Firestore directly.

### FastAPI application entry point

- Application object: `main.app`
- Local launch target: `uvicorn main:app`
- Application lifecycle: `main.lifespan`
- Route module: `main.py`
- Public route count: nine

The lifespan constructs and stores:

- one global Google GenAI client configured for Vertex AI;
- `MemoryEngine`;
- `SynthesisApplicationService`;
- `ArtifactReadService`;
- `ArtifactFeedbackService`;
- deterministic artifact and feedback executors;
- `TrustedMemoryService`;
- Source, Research, Computation, and Requirements Verification services;
- the structured routing service;
- responder-only Agent_Col;
- `AgentColTurnService`.

### Service boundaries

| Boundary | Responsibility |
| --- | --- |
| FastAPI | HTTP validation, error translation, and request orchestration |
| `AgentColTurnService` | Routing, zero-or-one expert execution, artifact execution, and final responder invocation |
| Expert executor | Source, Research, Computation, or Requirements Verification; never more than one per turn |
| Responder-only Agent_Col | Produces the final conversational response from validated context |
| Synthesis service | Generates strict schema-2.0 blueprints and derives governed adaptations |
| Artifact executor | Persists a chat-created blueprint before response generation |
| Artifact read service | Validates and projects Firestore artifacts into public models |
| Artifact feedback service | Resolves server-issued targets and validates feedback |
| Trusted memory service | Proposal, decision, inspection, revocation, and deletion |
| `MemoryEngine` | All Firestore reads, writes, batches, and transactions |

### Persistence boundary

Firestore is authoritative for:

- session messages;
- idempotent chat turns and receipts;
- projects and blueprints;
- artifact feedback and supersession;
- governed user memory and provenance.

ADK invocation state is not the durable conversation source of truth.

## 2. Implemented API routes

All routes are declared directly in `main.py`. There are no separate FastAPI
`APIRouter` modules.

All request models derived from `StrictModel` reject undeclared fields. Invalid
path, query, or JSON values normally produce FastAPI HTTP 422 validation
responses.

### Route summary

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Health check |
| `GET` | `/api/auth/config` | Read public frontend authentication bootstrap config |
| `GET` | `/api/auth/session` | Inspect local-dev or Google OIDC session state |
| `GET` | `/api/users/{user_id}/memory` | Inspect governed memory |
| `POST` | `/api/users/{user_id}/memory/signals/{signal_id}/revoke` | Revoke an active memory signal |
| `DELETE` | `/api/users/{user_id}/memory/signals/{signal_id}` | Hard-delete bounded memory artifacts |
| `POST` | `/api/synthesize` | Direct synchronous blueprint synthesis |
| `GET` | `/api/projects/{project_id}/blueprints` | List project blueprints |
| `GET` | `/api/projects/{project_id}/blueprints/{blueprint_id}` | Read canonical blueprint detail |
| `GET` | `/api/projects/{project_id}/blueprints/{blueprint_id}/feedback` | Read feedback lifecycle |
| `POST` | `/api/chat` | Main Agent_Col interaction boundary |

### `GET /`

Purpose: confirm that the FastAPI process is responding.

Request: none.

Response:

```json
{"status":"online"}
```

Limitations:

- does not prove Firestore availability;
- does not prove Vertex AI availability;
- does not exercise any expert;
- is a liveness response, not a full readiness check.

### `GET /api/auth/config`

Purpose: expose only public authentication bootstrap settings to the browser.

Request: none.

Response fields:

- `auth_contract_version`;
- `auth_mode`;
- `google_client_id`;
- `google_signin_required`;
- `local_development`.

Frontend purpose:

- decide whether to show the local-development locator form or require Google
  sign-in before workspace entry;
- configure the Google sign-in client with the public OAuth client ID.

Limitations:

- the Google client ID is public configuration, not a secret;
- this route does not create sessions, projects, or ownership records.

### `GET /api/auth/session`

Purpose: expose the current authentication mode and, when Google OIDC mode is
enabled, return the server-verified application principal derived from a Google
ID token.

Request:

- optional `Authorization: Bearer <Google ID token>` header in local
  development mode;
- required `Authorization: Bearer <Google ID token>` header when
  `AGENT_COL_AUTH_MODE=google_oidc`.

Response fields:

- `auth_contract_version`;
- `auth_mode`;
- `authenticated`;
- `local_development`;
- `user_id`;
- `workspace_project_id`;
- `subject`;
- `email`;
- `display_name`.

Validation and failures:

- missing or malformed bearer token in Google OIDC mode returns HTTP 401;
- invalid Google token returns HTTP 403;
- missing server Google client ID in Google OIDC mode returns HTTP 500.

Limitations:

- this is an authentication-principal boundary;
- local development mode still accepts request-provided locators;
- Google OIDC mode derives both `user_id` and `workspace_project_id` from the
  verified token subject;
- durable project membership records and project display metadata are not yet
  implemented.

### `GET /api/users/{user_id}/memory`

Purpose: inspect governed collaboration memory.

Inputs:

- `user_id`: identifier, 1-128 characters, restricted to letters, digits,
  underscores, and hyphens;
- optional `after_event_id`: event cursor with the same identifier bounds.

Response: `MemoryInspectionResponse` containing:

- governed `profile`;
- up to ten unresolved proposals;
- up to fifty newest-first lifecycle events;
- optional `next_event_id` cursor.

Failures:

- HTTP 404 when the event cursor does not exist;
- HTTP 422 for malformed identifiers;
- HTTP 500 for Firestore or stored-memory validation failure.

Frontend purpose:

- memory inspection panel;
- pending proposal controls;
- active preference and identity inspection;
- paginated provenance history.

### `POST /api/users/{user_id}/memory/signals/{signal_id}/revoke`

Purpose: revoke an active governed-memory signal while retaining its lifecycle
history.

Request body: none.

Response: `MemoryMutationResponse` containing:

- a completed `revoke_memory_signal` action receipt;
- the updated `CollaborationProfile`.

Failures:

- HTTP 404 when the signal is not active or known;
- HTTP 409 when lifecycle state conflicts with the request;
- HTTP 422 for malformed identifiers or an invalid governed-category prefix;
- HTTP 500 for persistence or stored-state failure.

### `DELETE /api/users/{user_id}/memory/signals/{signal_id}`

Purpose: hard-delete the bounded memory artifacts owned by one signal.

Request body: none.

Response: HTTP 204 with no body.

Behavior:

- deletes the signal's bounded proposal, origin, and lifecycle events;
- removes the active projection if present;
- returns HTTP 204 when the targeted artifacts are already absent.

Failures:

- HTTP 422 for malformed identifiers or an invalid category prefix;
- HTTP 500 for persistence or stored-state failure.

Frontend limitation: the response does not return the updated profile or state
whether anything existed. The frontend must refresh memory after deletion.

### `POST /api/synthesize`

Purpose: directly generate and persist one synchronous structured blueprint.

Request: `SynthesisRequest`.

```json
{
  "project_id": "identifier",
  "session_id": "identifier",
  "user_id": "identifier",
  "source_text": "1-10000 characters"
}
```

Response: `SynthesisResponse`.

```json
{
  "blueprint_id": "identifier",
  "blueprint": {
    "synthesized_conceptual_model": {},
    "personalization_trace": {},
    "architectural_decisions": [],
    "socratic_clarifying_questions": [],
    "step_by_step_execution_roadmap": [],
    "diagnostic_warnings": []
  }
}
```

Behavior:

- loads governed collaboration memory and up to twenty history messages;
- generates a strict schema-2.0 blueprint synchronously;
- validates personalization;
- persists the blueprint;
- returns the full blueprint.

Failures:

- HTTP 422 for invalid identifiers, source length, JSON, or extra fields;
- HTTP 500 for Firestore failure;
- HTTP 502 for provider, schema, semantic, or personalization failure;
- HTTP 504 for synthesis timeout.

Limitations:

- no idempotency key;
- a retry can create another artifact;
- no durable job;
- verified adaptations are persisted but not returned separately in
  `SynthesisResponse`;
- bypasses Agent_Col's conversational routing and should remain a developer or
  backward-compatibility surface rather than the primary frontend workflow.

### `GET /api/projects/{project_id}/blueprints`

Purpose: list one bounded, newest-first page of project blueprint metadata.

Inputs:

- `project_id`;
- `limit`: integer from 1 through 50, default 20;
- optional `before`: artifact-document cursor.

Response: `BlueprintArtifactListResponse` containing:

- artifact contract version `1.0`;
- blueprint metadata;
- optional `next_before` cursor.

Metadata includes:

- artifact reference;
- creation timestamp;
- originating session and optional turn;
- optional parent artifact ID;
- active feedback counts;
- adaptation categories.

Failures:

- HTTP 404 when the cursor does not exist;
- HTTP 422 for invalid identifiers or limits;
- HTTP 500 for an invalid stored artifact or database failure.

Special behavior:

- known legacy schema-1.0 artifacts are omitted from list results;
- another invalid current artifact can fail the complete page;
- in Google OIDC mode, the path `project_id` must match the server-derived
  `workspace_project_id`.

### `GET /api/projects/{project_id}/blueprints/{blueprint_id}`

Purpose: return one canonical blueprint and its frontend-facing metadata.

Response: `BlueprintArtifactDetailResponse` containing:

- artifact contract version;
- metadata;
- full canonical `SynthesisBlueprint`;
- server-derived feedback targets;
- verified adaptations;
- applied feedback IDs.

Failures:

- HTTP 404 when the artifact is absent under that project;
- HTTP 409 for a known legacy or unsupported schema;
- HTTP 422 for malformed identifiers;
- HTTP 500 for a malformed stored artifact or database failure.

Frontend purpose:

- canonical artifact detail;
- blueprint rendering;
- feedback target selection;
- adaptation receipt display.

### `GET /api/projects/{project_id}/blueprints/{blueprint_id}/feedback`

Purpose: list the immutable feedback lifecycle for a blueprint.

Inputs:

- `limit`: integer from 1 through 50, default 20;
- optional `before`: feedback-document cursor.

Response: `BlueprintArtifactFeedbackListResponse` containing:

- feedback contract version `1.0`;
- artifact ID;
- newest-first feedback events;
- optional `next_before` cursor.

Each event includes:

- a bounded feedback reference;
- feedback and optional correction text;
- session/message/turn provenance;
- public `active` or `superseded` lifecycle status;
- predecessor and successor identifiers.

Failures:

- HTTP 404 when the artifact or cursor is absent;
- HTTP 422 for malformed inputs;
- HTTP 500 for invalid feedback, invalid parent state, or database failure.

There is no dedicated feedback write endpoint. Structured `POST /api/chat` is
the implemented write authority.

### `POST /api/chat`

Purpose: provide the primary Agent_Col conversational boundary.

Request: `ChatRequest`.

```json
{
  "project_id": "identifier",
  "session_id": "identifier",
  "user_id": "identifier",
  "message": "1-10000 characters",
  "memory_decision": {
    "proposal_id": "identifier",
    "decision": "approve"
  },
  "artifact_feedback_decision": {
    "artifact_id": "identifier",
    "target_id": "identifier",
    "decision": "edited",
    "feedback_text": "bounded feedback",
    "correction_text": "required for edited feedback",
    "expected_schema_version": "2.0",
    "supersedes_feedback_id": null
  }
}
```

`memory_decision` and `artifact_feedback_decision` are both optional but are
mutually exclusive.

Optional header:

```text
Idempotency-Key: 1-128 ASCII letters, digits, underscores, or hyphens
```

Response: `ChatResponse` containing:

- conversational `response`;
- completed action receipts;
- artifact references;
- artifact-feedback references;
- citations;
- pending memory-proposal receipts;
- verified adaptation receipts.

Idempotent behavior:

- a completed identical keyed request replays the stored response;
- a changed request with the same key returns HTTP 409;
- an active in-progress key returns HTTP 409 with `Retry-After`;
- artifact feedback requires an idempotency key;
- chat-routed artifact creation is available only through the claimed,
  idempotent path;
- headerless chat has no durable replay and cannot use the v4 artifact route.

Failures include:

- HTTP 404 for a missing proposal, artifact, or feedback target;
- HTTP 409 for idempotency conflict, active turn, memory conflict, stale
  artifact schema, feedback conflict, or lease/turn ownership conflict;
- HTTP 410 for an expired memory proposal;
- HTTP 422 for request validation, invalid decision, invalid idempotency key,
  or feedback without an idempotency key;
- HTTP 500 for database, invalid stored history/context, or inconsistent
  durable state;
- HTTP 502 for routing or responder failure;
- HTTP 504 for routing or complete-turn timeout.

If an artifact or feedback action completed before responder failure, HTTP 502
or HTTP 504 can return `ChatPartialFailureResponse` containing authoritative
completed receipts.

HTTP 200 alone does not prove that an expert completed. Provider-level expert
failures can produce a normal Agent_Col response without a matching completed
action. Frontend code must inspect `actions`, `artifacts`, and `citations`.

OpenAPI currently documents normal responses and automatic HTTP 422 responses,
but does not declare most runtime HTTP 404, 409, 410, 500, 502, or 504 variants.

## 3. Data contracts

Public contracts are defined in `schemas.py`.

### Shared validation and serialization

- Extra JSON fields are forbidden.
- Identifiers are 1-128 characters and match `[A-Za-z0-9_-]+`.
- Chat and synthesis source text are limited to 10,000 characters.
- Feedback and correction text are limited to 1,500 characters.
- Blueprint schema version is `2.0`.
- Artifact contract version is `1.0`.
- Datetimes serialize as JSON date-time strings.
- URLs use Pydantic `HttpUrl` and serialize as strings.
- Empty receipt arrays are normally present in successful responses.
- FastAPI validation failures use the standard structured HTTP 422 body.
- Most application errors use `{"detail":"message"}`.
- Partial chat failures use `ChatPartialFailureResponse` instead.

### Public request models

- `ChatRequest`
- `MemoryDecisionRequest`
- `ArtifactFeedbackDecisionRequest`
- `SynthesisRequest`

GET and DELETE routes use validated path/query inputs rather than body models.

### Public response models

- `ChatResponse`
- `ChatPartialFailureResponse`
- `MemoryInspectionResponse`
- `MemoryMutationResponse`
- `SynthesisResponse`
- `BlueprintArtifactListResponse`
- `BlueprintArtifactDetailResponse`
- `BlueprintArtifactFeedbackListResponse`

### Receipt and reference models

- `AgentActionReceipt`
- `ArtifactReference`
- `ArtifactFeedbackReference`
- `CitationReference`
- `MemoryProposalReceipt`
- `AdaptationReceipt`

Action receipts only support `status="completed"`. Absence means the action was
not authoritatively completed.

### Synthesis blueprint model

`SynthesisBlueprint` contains:

- `synthesized_conceptual_model`;
- `personalization_trace`;
- `architectural_decisions` and alternatives;
- `socratic_clarifying_questions` and suggested options;
- `step_by_step_execution_roadmap` and micro-tasks;
- `diagnostic_warnings`.

The artifact-detail API is the canonical source for this content. Agent_Col's
prose response is not a replacement for the stored artifact.

### Governed-memory models

Important public and persistence models are:

- `CollaborationProfile`;
- `ActiveMemorySignal`;
- `MemoryProposal`;
- `MemoryEvent`.

Supported categories are:

- `response_length`;
- `explanation_structure`;
- `example_usage`;
- `question_style`;
- `planning_granularity`;
- `progress_check_ins`;
- `tool_use_style`;
- `formatting_style`;
- `preferred_name`;
- `broad_roles`.

### Important internal contracts

The following are server-internal contracts and must not become frontend write
authority:

- `AgentColRoutingInput` and `AgentColRoutingDirective` v4;
- routes `direct`, `clarify`, `source`, `research`, `computation`,
  `requirements_verification`, and `artifact`;
- `AgentColTurnCommand` and `AgentColTurnResult`;
- `AgentColResponderContextV3`;
- `ExpertResult`, `ExpertCapability`, and `ExpertStatus`;
- `SynthesisCommand` and governed generation results;
- deterministic artifact and feedback execution commands;
- trusted-memory lifecycle commands;
- `ChatTurnClaim` and `ChatTurnReplay`.

The frontend must not fabricate or submit routing directives, expert results,
action receipts, artifact IDs, feedback IDs, or memory provenance.

## 4. Firestore and backend persistence entities

| Path | Purpose and lifecycle | Current ownership assumption | Frontend relevance |
| --- | --- | --- | --- |
| `users/{user_id}` | Governed profile projection and revision | Path uses caller-supplied `user_id` | Memory panel |
| `users/{user_id}/memory_proposals/{category}` | One category slot; pending, approved, or rejected; pending expires after 24 hours | Caller-supplied user | Pending approvals |
| `users/{user_id}/memory_proposal_origins/{origin_id}` | Deduplicates proposal creation against source message and category | Caller-supplied user/session provenance | Internal only |
| `users/{user_id}/memory_events/{event_id}` | Approved, corrected, superseded, and revoked provenance | Caller-supplied user | Memory history |
| `sessions/{session_id}` | Stores only `updated_at` | No stored owner or project on parent | Not publicly listable |
| `sessions/{session_id}/messages/{message_id}` | User/model text and timestamp | No user or project field on message | Transcript data exists but has no API |
| `sessions/{session_id}/turns/{turn_id}` | In-progress/completed idempotent turn, lease, request identity, and receipts | Stores supplied user/project IDs | Replay and effect recovery |
| `projects/{project_id}` | Stores only `updated_at` | No verified owner or display metadata | Cannot support project picker |
| `projects/{project_id}/blueprints/{blueprint_id}` | Immutable blueprint content plus mutable feedback counts | Stores supplied `user_id`; reads do not filter by it | Artifact list/detail |
| `projects/{project_id}/blueprints/{blueprint_id}/feedback/{feedback_id}` | Immutable feedback event | Write validates against the blueprint's stored supplied user ID | Feedback history |
| `projects/{project_id}/blueprints/{blueprint_id}/feedback_supersessions/{prior_feedback_id}` | Links prior feedback to its successor | Project/artifact path only | Produces public superseded status |

Additional persistence behavior:

- chat-created artifact IDs are deterministic from the idempotent turn;
- direct `/api/synthesize` uses a Firestore-generated artifact ID;
- feedback updates bounded counts but does not mutate blueprint content;
- `parent_artifact_id` and `applied_feedback_ids` exist in models but no
  production workflow populates them;
- there are no project, session, job, upload, or authentication entities.

## 5. Agent_Col interaction flow

```text
User submits ChatRequest
  |
  +-- optional idempotency claim or replay
  |
  +-- load up to 20 history messages
  +-- load governed CollaborationProfile
  |
  +-- persist or identify the user message
  |
  +-- optional structured memory decision
  |
  +-- artifact feedback decision?
  |      yes -> bypass routing
  |             validate server-issued target
  |             persist feedback effect
  |             responder acknowledges result
  |
  +-- otherwise build bounded routing input
         URLs + numeric candidates + text blocks + capabilities
         |
         Vertex structured router
         |
         local directive validation
         |
         +-- direct
         +-- clarify
         +-- Source Expert
         +-- Research Expert
         +-- Computational Expert
         +-- Requirements Verification Expert
         +-- artifact/create_blueprint
                 |
                 exact current message is source
                 governed synthesis
                 persist artifact effect
                 canonical artifact read
         |
         responder-only Agent_Col
         |
         optional pending memory proposal
         |
         ChatResponse + authoritative receipts
         |
         persist model message and complete turn
```

There is no expert chaining. Retrieved or generated content cannot authorize
another tool or persistence operation.

## 6. Current frontend-relevant capabilities

### Safe to implement now

- basic chat composer and current-runtime transcript;
- one client-generated development project/session/user context;
- per-turn idempotency keys;
- loading, error, conflict, and timeout states;
- action receipts;
- citation links;
- artifact creation through chat;
- artifact list and canonical detail;
- server-issued artifact feedback targets;
- accepted, rejected, and edited feedback through structured chat requests;
- feedback history and supersession display;
- memory inspection and pagination;
- memory proposal approval/rejection through structured chat requests;
- memory revocation and hard deletion;
- adaptation receipt display;
- fixed-project context for a local or judged demo build.

### Implemented but constrained

- Sessions persist internally but cannot be retrieved publicly.
- Projects persist internally but have no listing or metadata API.
- Artifact feedback is complete through chat but has no separate write endpoint.
- Direct synthesis exists but is not retry-safe.
- Chat is synchronous and non-streaming.
- Routing decisions are not included in `ChatResponse`; only observable
  receipts expose completed effects.
- Chat responses contain no canonical message ID, turn ID, or timestamp.

## 7. Missing frontend APIs and contracts

| Missing boundary | Why the frontend needs it | Priority | MVP or future |
| --- | --- | --- | --- |
| Session transcript/history retrieval | Restore a transcript after reload or on another device | P0 | Required for a credible persistent-chat MVP |
| Session listing and metadata | Resume or switch conversations without knowing raw IDs | P1 | May be deferred for a single-session demo |
| Explicit session creation and ownership | Establish canonical session identity and owner | P0 for public | Local frontend may temporarily generate IDs |
| Project listing and metadata | Populate a project switcher and display names | P1 | A fixed `agent-col` project can serve local MVP |
| Project creation and ownership | Prevent arbitrary project-ID access and establish ownership | P0 for public | Not required for a fixed local demo |
| Verified authentication principal | Replace request-provided `user_id` | P0 for public | Required before public deployment |
| Ownership enforcement on every read/write | Prevent cross-user resource access | P0 for public | Required before public deployment |
| Canonical chat-message/turn envelope | Provide IDs, timestamps, and reliable transcript reconciliation | P1 | Best delivered with history retrieval |
| Artifact version creation from parent/feedback | Create a new immutable artifact using selected feedback | P2 | Future; not needed by first UI |
| Artifact deletion and retention control | Support production privacy and lifecycle requirements | P1/P0 for public policy | Future implementation |
| Project/session deletion | Support account and data-retention lifecycle | P1/P0 for public policy | Future implementation |
| Durable synthesis job/status/cancel API | Survive disconnects and display queued/running/failed states | P2 unless runtime requires it | Not required for synchronous local MVP |
| Capability/status discovery | Dynamically advertise available experts or tools | P2 | UI should not add a capability picker yet |
| File/upload ingestion | Support PDF and document workflows | P2 | Not implemented; text-only MVP |
| Rate-limit and stable retry contract | Support safe public operation | P0 for public | Not required for local frontend |
| Comprehensive OpenAPI error declarations | Generate a reliable typed frontend error client | P1 | Initial UI can handle known envelopes manually |

### Implemented contracts that are not missing

The following were previously documented as pending but are implemented:

- artifact list API;
- artifact detail API;
- feedback history API;
- accepted, rejected, and edited feedback writes;
- feedback supersession;
- chat-routed artifact synthesis;
- governed synthesis personalization;
- verified adaptation receipts;
- public auth bootstrap config;
- authentication session inspection;
- Google sign-in initiated by the browser with bearer-token transport.

A dedicated feedback `POST` endpoint is not required by the accepted design.
Structured `/api/chat` is the current write authority.

## 8. Authentication and authorization assumptions

### Current development identity

The repository now has an authentication-principal foundation with two modes:

- `local_dev` is the default local mode and preserves the existing development
  locator workflow;
- `google_oidc` verifies a Google ID token from the `Authorization` header and
  derives the application `user_id` from the token `sub` claim.

In `local_dev`, the backend still trusts:

- `user_id` from JSON or the URL path;
- `project_id` from JSON or the URL path;
- `session_id` from JSON.

In `google_oidc`, user-scoped routes reject a request when the supplied
`user_id` does not match the server-derived `google--{sub}` principal.

There are no:

- authenticated cookies;
- ownership lookups;
- Firestore-backed access checks tied to an authenticated subject.

Google Application Default Credentials authenticate the backend to Vertex AI
and Firestore. ADC does not authenticate application users.

### Current ownership model

The current model provides authenticated user and derived workspace-project
consistency, but not a complete multi-project membership system:

- in local mode, identifiers select Firestore paths;
- in Google OIDC mode, the user identity is checked before user-scoped route
  service access;
- in Google OIDC mode, the effective project ID must match the
  server-derived `workspace_project_id`;
- turn records retain effective user/project identity;
- feedback writes verify that supplied `user_id` matches the blueprint's stored
  supplied `user_id`;
- durable project membership records, project display names, sharing, and
  project switching do not exist yet.

The backend still needs durable project ownership records before public
multi-project use.

### Required before public deployment

- project, session, artifact, feedback, and memory ownership records;
- project, session, artifact, feedback, and memory ownership checks;
- safe unavailable-resource behavior for unauthorized resources;
- durable logout and authenticated-session lifecycle beyond clearing browser
  runtime state;
- account deletion and data-retention policy;
- request-rate controls;
- secure deployment headers and hosted security review.

## 9. Frontend implementation recommendations

### Components supported by current contracts

- `ChatComposer`
- in-memory `ChatTranscript`
- `TurnStatus`
- `ActionReceiptList`
- `CitationList`
- `ArtifactList`
- `ArtifactDetail`
- `ArtifactFeedbackForm`
- `ArtifactFeedbackHistory`
- `MemoryProfilePanel`
- `MemoryProposalCard`
- `MemoryEventHistory`
- `AdaptationReceiptList`
- local-development project/session context

### Components requiring backend additions

- persistent transcript loader;
- conversation/session sidebar;
- project switcher;
- authenticated account shell;
- artifact version history or editor;
- background-job status view;
- upload/document picker;
- capability-management controls.

### Unsupported assumptions the frontend must avoid

- Do not treat HTTP 200 as proof that a tool completed.
- Do not infer a routing decision from Agent_Col prose.
- Do not fabricate action or citation receipts.
- Do not call `/api/synthesize` as the primary conversational workflow.
- Always send a unique idempotency key for UI chat submissions.
- Do not retry direct synthesis as if it were idempotent.
- Do not assume streaming or cancellation exists.
- Do not assume messages can be restored after reload.
- Do not treat artifact feedback as global governed memory.
- Do not mutate canonical artifact JSON locally.
- Do not present project, session, or user IDs as authentication.
- Do not advertise file ingestion, artifact versioning, background jobs, or
  capability toggles.
- Do not assume CORS is configured; use a same-origin mount or development
  proxy.
- Handle normal `detail` errors, FastAPI validation arrays, and partial-failure
  receipt envelopes separately.

## 10. Frontend readiness conclusion

The backend supports the core local browser loop:

```text
chat
  -> authoritative receipts
  -> artifact list and detail
  -> artifact feedback
  -> governed-memory inspection and control
```

The most important missing contract for the local frontend is session history
retrieval. The most important missing boundary for public deployment is verified
identity with ownership enforcement.

The first frontend should therefore use a fixed local project and user context,
generate one session identifier locally, always use idempotent chat, and avoid
presenting the current locator identifiers as secure accounts.
