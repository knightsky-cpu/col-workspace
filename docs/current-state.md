# Agent Col Current State

Last reconciled: September 5, 2026.

This document describes what Agent Col implements in the current checkout.
Source code and [Repository map](repo-map.md) are the authority for these
claims. Private local historical files, future plans, and migration research
are provenance or planning records unless current source still matches them.

## Current Product State

Agent Col is implemented as a persistent collaborative partner: a FastAPI
backend, same-origin browser workspace, Google OIDC or local-development auth,
Gemini/ADK responder execution, bounded specialists, Firestore persistence,
governed memory, collaborative notes, continuity, hidden working state,
artifacts, queued AgentJobs, and browser speech.

The current production deployment model is one Cloud Run FastAPI container.
That container serves the static UI, same-origin APIs, model/provider calls,
Firestore access, STT/TTS routes, and process-local AgentJob workers.

## Implemented

- Same-origin browser workspace served at `/workspace`.
- Local-development auth and Google OIDC auth modes.
- User-owned workspaces with workspace-scoped chat, notes, artifacts, and
  AgentJob state.
- Persisted chat sessions with retry-safe idempotent turn records.
- Ordinary-turn SSE chat streaming through `/api/chat/stream`.
- Ordinary non-streaming JSON chat through `/api/chat`.
- Direct governed resource APIs for memory proposal decisions, memory
  clarification selection, collaborative-note decisions, continuity choices,
  artifact feedback, note lifecycle, memory signal revocation/deletion, and
  artifact lifecycle actions.
- Firestore-backed `AgentJob` records, private payloads, public events,
  completion reports, retry/cancel routes, startup/runtime drain loops, and
  process-local workers.
- Queue-backed chat-routed work for supported explicit memory, collaborative
  note, and blueprint artifact requests.
- Governed profile memory with proposal, clarification, approval, rejection,
  correction, revocation, deletion, inspection, provenance, lifecycle events,
  and adaptation receipts.
- Shared memory-proposal eligibility exclusions for deterministic routing and
  model/tool-proposed evidence.
- Governed collaborative notes with proposal, correction, decision, archive,
  restore, delete, active projection, event history, and workspace scoping.
- Bounded continuity from active notes and prior chat sessions/messages, with
  direct continuity-choice selection.
- Hidden same-session working state used as non-authoritative collaboration
  context after canonical response persistence.
- Narrow preference-learning observations and hypotheses from explicit
  concise/shorter-response feedback.
- Bounded Research, Source, Computation, and Requirements Verification
  specialists.
- Synthesis blueprints and generic single-file artifacts with lifecycle,
  metadata, versioning, feedback, detail, and export surfaces.
- Browser voice input through Google Cloud Speech-to-Text.
- Spoken assistant responses through Google Cloud Text-to-Speech for completed
  assistant messages.
- Offline Python and frontend test coverage plus live smoke runners for
  configured local or hosted services.

## Implemented With Limits

- AgentJob execution is persisted and drainable, but worker execution is
  process-local inside the FastAPI/Cloud Run instance. There is no Cloud Tasks,
  Pub/Sub, or separate private worker service in the current runtime.
- AgentJob cancel mutates persisted job status but does not cancel an already
  running in-process asyncio task.
- AgentJob retry clones private payload data and dispatches through the
  registered process-local dispatcher when possible, but failed workers are
  currently marked non-retryable by default.
- Rate limiting is in-process per running instance, not distributed.
- Working state is hidden, same-session, best-effort, possibly stale, and
  non-authoritative.
- Continuity resolves bounded context or returns user choices; it is not
  open-ended retrieval authority.
- Preference learning is intentionally narrow and does not silently mutate
  active memory.
- Direct `/api/synthesize` and generic artifact creation are request-bound
  generation paths. Chat-routed blueprint artifact requests are queue-backed.
- Firestore indexes and pagination strategy are intentionally narrow.
- Blueprint artifacts expose list/detail/feedback routes; matching blueprint
  archive/restore/delete routes are not registered in `main.py`.

## Not Implemented

- A separate durable worker service outside the FastAPI/Cloud Run process.
- Cloud Tasks or Pub/Sub-backed AgentJob delivery.
- A globally distributed rate limiter.
- Broad preference inference.
- PostgreSQL as the active persistence backend.
- Model Armor, Agent Registry, Agent Gateway, Agent Observability, or Memory
  Bank as separate Gemini Enterprise Agent Platform services.

## User-Visible Surfaces

- Browser authentication entry and session projection.
- Workspace selection, creation, deletion, and scoped application state.
- Chat UI with idempotent retry, receipts, citations, queued action receipts,
  memory clarification choices, continuity choices, and status/error display.
- Workspace drawer sections for Workspace, Artifacts, Notes, Memory, Chats,
  and Agents.
- Agents panel showing queued/running/completed/failed AgentJobs and reports.
- Memory drawer showing active memory, pending proposals, clarifications,
  events, direct decisions, revoke, and delete actions.
- Notes drawer showing active/archived notes, proposals, corrections,
  decisions, lifecycle actions, and event detail.
- Work/artifacts surface showing blueprint and generic artifacts, artifact
  detail, metadata, versions, lifecycle actions, feedback, and export behavior.
- Microphone dictation to the backend STT route and optional spoken responses
  from completed assistant messages.

## Backend Capabilities

- FastAPI routes for auth, workspaces, memory, memory clarifications,
  continuity choices, notes, chat sessions, AgentJobs, synthesis, artifacts,
  artifact feedback, speech, ordinary JSON chat, and ordinary SSE chat.
- Firestore-backed storage for chat sessions, messages, turns, workspaces,
  governed memory, memory clarifications, collaborative notes, preference
  records, working state, artifacts, feedback, AgentJobs, AgentJob events, and
  AgentJob reports.
- Google OIDC and local-dev auth modes with Cloud Run fail-closed checks for
  hosted Google auth configuration.
- Request perimeter middleware for request size, in-memory per-client/path
  rate limiting, cache control, and security headers.
- Durable chat idempotency with turn claim, replay, live conflict,
  expired-turn resume, deterministic message IDs, and completion validation.
- Partial failure responses that preserve already-completed effects where
  possible.

## Frontend Capabilities

- Static ES module UI served by FastAPI without a frontend build step.
- Same-origin API helper with relative-path enforcement, auth headers,
  idempotency headers, JSON handling, SSE parsing, timeout/error
  normalization, and structured error details.
- Immutable-ish chat request construction with generated idempotency keys and
  exact retry body/key preservation.
- Ordinary chat streaming through `/api/chat/stream`.
- Direct API calls for governed memory, note, continuity, artifact-feedback,
  workspace, work, and AgentJob surfaces.
- Panel-specific refresh behavior after authoritative receipts and completed
  AgentJobs.
- Safe text/Markdown rendering and text-based artifact content display.

## Specialist And Tool Capabilities

Specialists are bounded evidence producers. The responder does not receive
open-ended model-visible expert tools for Research, Source, Computation, or
Requirements Verification.

- Research uses Gemini with Google Search grounding, validates grounding
  metadata, and returns public citations/receipts for completed validated
  results.
- Source uses Gemini URL Context for supplied public URLs and performs
  structured classification over grounded statements.
- Computation uses bounded ADK computation execution with built-in Python code
  execution, input limits, max LLM-call limits, timeout handling, and session
  cleanup.
- Requirements Verification uses direct structured Gemini generation plus local
  validation against supplied requirement and subject blocks.
- Artifact creation is constrained by route and artifact validation before
  persistence.

## Current Runtime Configuration

Required runtime configuration is source-backed in `auth.py`,
`vertex_config.py`, `speech_service.py`, and `main.py`.

- `AGENT_COL_AUTH_MODE=local_dev` for local development or
  `AGENT_COL_AUTH_MODE=google_oidc` for hosted Google auth.
- `GOOGLE_OAUTH_CLIENT_ID` or fallback `GOOGLE_CLIENT_ID` for Google OIDC.
- `GOOGLE_CLOUD_PROJECT`.
- `GOOGLE_CLOUD_LOCATION=global`.
- `GOOGLE_GENAI_USE_ENTERPRISE=True`.
- `AGENT_COL_STT_LANGUAGE_CODES`, defaulting to `en-US`.
- `AGENT_COL_STT_MODEL`, defaulting to `latest_short`.
- Optional `AGENT_COL_SPEECH_MAX_AUDIO_BYTES`.

Server-side Google Cloud calls use Application Default Credentials locally and
the Cloud Run runtime service account when deployed. The browser never calls
Firestore, Vertex AI, Speech-to-Text, or Text-to-Speech directly.

## Current Documentation Authority

- [README](../README.md): developer entry point, setup, and deployment path.
- [Architecture](architecture.md): concise current architecture and trust
  boundaries.
- [Local setup](local-setup.md): top-level clone/configure/run/deploy setup.
- [Repository map](repo-map.md): detailed source-derived file, route, and
  lifecycle map.
- [Deployment runbook](deployment/google-cloud-run-deployment-instructions.md):
  canonical MacBook/Cloud Run deployment procedure for the maintained service.

## Known Technical Debt

- External durable worker architecture for AgentJobs.
- Distributed rate limiting.
- Broader indexed-query and pagination hardening.
- Broader preference extraction beyond explicit concise/shorter feedback.
- Blueprint/generic artifact lifecycle parity.
- Workspace deletion cleanup for AgentJob/report collections.
- Legacy/versioned/dead-code cleanup after release stabilization.
- Retention, deletion, and operational hardening beyond the current service
  behavior.
