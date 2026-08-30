# Agent Col Current State

Last reconciled: August 30, 2026.

This document describes what Agent Col can do in the current checkout. Source
code, tests, and [Repository map](repo-map.md) are the authority for these
claims; historical files under `docs/legacy/` and forward plans under
`docs/forward/` are not implementation truth.

## Current Product State

Agent Col is implemented as a persistent collaborative partner: a FastAPI
backend, same-origin browser workspace, Gemini/ADK specialist execution,
Firestore persistence, governed memory, collaborative notes, continuity,
working state, preference learning, and artifacts.

Repository deployment notes identify an accepted Cloud Run deployment in
`us-east4`. Remaining submission work is final hosted re-verification, demo
evidence, and freeze rather than initial deployment.

## Status Classification

Implemented:

- Same-origin browser workspace served by FastAPI.
- Local-development auth and Google OIDC auth modes.
- User/workspace/project ownership checks.
- Workspace-scoped chat sessions and idempotent chat turns.
- Ordinary-turn SSE chat streaming plus JSON structured-decision chat.
- Governed profile memory.
- Governed collaborative notes.
- Bounded continuity from active notes and prior chat sessions.
- Hidden same-session working state.
- Narrow preference learning for explicit concise/shorter-response feedback.
- Routed Research, Source, Computation, and Requirements Verification
  specialists.
- Synchronous blueprint synthesis and generic single-file artifact workflows.
- Artifact detail, lifecycle, metadata update, versioning, feedback, and export
  surfaces.

Implemented with limitation:

- Working state is hidden, same-session, best-effort maintenance and
  non-authoritative.
- Continuity resolves bounded context or returns user choices; it is not
  open-ended retrieval authority.
- Preference learning is intentionally narrow and does not silently mutate
  active memory.
- Artifact execution is request-bound, not a durable background job system.
- Rate limiting is in-memory per process/Cloud Run instance.
- Firestore indexes and pagination strategy are intentionally narrow.

Intentionally deferred:

- Durable asynchronous/background execution.
- Cloud Tasks or private worker execution.
- Distributed rate limiting.
- Broader preference inference.
- Larger indexed-query and retention-policy hardening.
- Cleanup of retained legacy/versioned/evaluation source files after submission
  freeze.

Not implemented:

- Background artifact jobs that continue after the HTTP request ends.
- A globally distributed rate limiter.
- Model Armor, Agent Registry, Agent Gateway, Agent Observability, or Memory
  Bank as separate Gemini Enterprise Agent Platform services.

## Implemented User-Visible Capabilities

- Google or local-development authentication entry.
- Workspace selection, creation, deletion, and workspace-scoped chat state.
- Conversation UI with idempotent retry, receipts, citations, memory
  clarification choices, continuity choices, and status/error display.
- Progressive streaming for ordinary chat turns through `/api/chat/stream`;
  `/api/chat` remains the canonical JSON and structured-decision path
  described in [Repository map](repo-map.md).
- Supporting drawer sections for Workspace, Artifacts, Notes, Memory, and
  Chats; there is activity/receipt state and rendering support in code, but the
  inspected HTML does not expose a separately labeled Activity drawer section
  (`frontend/index.html`, `frontend/activity-view.mjs`).
- Right-side Artifacts Viewer with artifact detail, content display, metadata,
  lifecycle, versioning, feedback, and export behavior.
- Memory inspection plus approval/rejection, correction, revocation, and
  deletion flows where surfaced by the backend.
- Collaborative note proposals, decisions, corrections, archive/restore/delete,
  detail, and event display.
- Chat session list/detail reconstruction.

## Implemented Backend Capabilities

- FastAPI routes for auth/session, workspaces, memory, notes, chat sessions,
  synthesis, artifacts, feedback, chat, and ordinary chat streaming
  as listed in [Repository map](repo-map.md).
- Firestore-backed chat sessions, messages, turn records, user workspaces,
  memory, note, artifact, feedback, continuity-source, working-state, and
  preference records (`database.py`, `repo-map.md`).
- Google OIDC and local-dev auth modes with Cloud Run fail-closed checks for
  Google auth configuration (`auth.py`).
- Request perimeter middleware for request size, in-memory per-client/path rate
  limiting, cache control, and security headers.
- Durable chat idempotency with turn claim, replay, live conflict, expired-turn
  resume, deterministic user/model message IDs, and completion validation.
- Partial failure responses that preserve already-completed effects where
  possible.

## Implemented Frontend Capabilities

- Same-origin API helper with relative-path enforcement, auth headers,
  idempotency headers, JSON handling, timeout/error normalization, and
  structured error details.
- Immutable chat request construction with generated idempotency keys and exact
  retry body/key preservation.
- Structured chat decision requests for memory clarification and continuity
  selections.
- Panel-specific rendering for chat, artifacts/work, notes, memory, chats, and
  workspace state.
- Safe text/markdown rendering and text-based artifact content display
  (`frontend/render.mjs`, `frontend/markdown-renderer.mjs`,
  `frontend/work-view.mjs`).

## Specialist And Tool Capabilities

Current routed specialist capabilities are bounded evidence producers. The
responder does not directly receive model-visible expert tools.

- Research uses Gemini with Google Search grounding, validates provider
  grounding metadata, and returns public citations/receipts only for completed
  validated results.
- Source analyzes supplied public URLs using Gemini URL Context for retrieval,
  then performs a tool-free structured classification pass over grounded
  statements.
- Computation uses bounded ADK computation execution in a temporary in-memory
  invocation session. The computational agent is configured with built-in Python
  code execution, bounded inputs, max LLM calls, timeout handling, and session
  cleanup.
- Requirements Verification uses direct tool-free structured Gemini generation
  and local validation against supplied requirement and subject blocks
  (`requirements_verification_service.py`).
- Artifact routing supports request-bound artifact creation where route and
  artifact constraints validate.

## Memory, Notes, Continuity, Working State, And Preferences

Governed profile memory is implemented. It supports model-proposed pending
memory, deterministic policy validation, ambiguous-memory clarification,
approval/rejection, correction, revocation, hard deletion, bounded inspection,
provenance, lifecycle events, and adaptation receipts. Pending proposals are
not active memory until approved.

Collaborative notes are implemented and workspace-scoped. They support pending
proposals, user approval/rejection, correction, archive, restore, deletion,
source provenance, active-note projection, and note events
(`collaborative_note_service.py`, `database.py`).

Continuity is implemented and intentionally bounded. It reads active notes and
prior chat sessions/messages as sources, returning either resolved context with
receipts or ambiguity choices when the reference cannot be resolved safely
(`continuity_service.py`).

Working state is implemented and intentionally bounded/non-authoritative. It is
hidden same-session context, can be unavailable or stale, and cannot authorize
tools, memory, notes, artifacts, identity changes, or durable actions
(`working_state.py`). In `/api/chat`, the request awaits:

```text
canonical responder completion
-> authoritative chat persistence
-> awaited hidden working-state maintenance
-> HTTP response returned
```

Working-state update failures are logged and swallowed, but when enabled the
maintenance call is awaited before the response returns.

Preference learning is implemented but intentionally narrow. It stores
non-authoritative observations/hypotheses and currently recognizes explicit
shorter/concise response feedback; surfaced hypotheses are confirmed through
the governed memory clarification path (`preference_learning.py`,
`preference_learning_service.py`, `main.py`).

## Artifact Behavior

Implemented artifact capabilities include synchronous blueprint synthesis,
blueprint list/detail, generic single-file artifact create/list/detail,
archive/restore, metadata update, child version creation, blueprint feedback
records, feedback supersession metadata, and chat-routed supported artifact
effects.

Artifact execution is currently request-bound. Durable asynchronous/background
execution is not part of the current runtime path.

## Test And Evidence Status

[Repository map](repo-map.md) records the current source-backed test inventory.
Existing tests cover routing constraints, expert validation, memory
normalization and proposal behavior, collaborative-note lifecycle behavior,
artifact read/feedback behavior, frontend state/retry behavior, and safe
markdown rendering.

This document does not claim a fresh full-suite run. For this documentation
pass, the required verification is `git diff --check` after edits.

## Implemented But Intentionally Bounded

- Continuity ambiguity handling is implemented as bounded resolved context or
  explicit user choices, not open-ended retrieval authority.
- Working state is implemented as hidden, same-session, non-authoritative
  context, not durable memory or an action authority.
- Preference learning is implemented narrowly for explicit concise/shorter
  response feedback.
- Artifact generation and feedback are implemented for current request-bound
  paths, not background jobs.
- Rate limiting is implemented in memory per running instance, not as a
  distributed limiter.

## Known Current Limitations

- Durable asynchronous/background execution is not implemented.
- Firestore pagination/index strategy is intentionally narrow; custom indexes
  are limited in the checked-in index file (`firestore.indexes.json`).
- Source and Computation fail safely but expose less detailed invalid-output
  diagnostics than Research and Requirements Verification (`repo-map.md`).
- Some older routing/provider/executor/context modules remain as compatibility,
  tests-only, live-check-only, or apparently unused code (`repo-map.md`).
- Retention/deletion policy and broader operational hardening remain limited to
  the currently implemented service behavior and docs.

## Post-Submission Technical Debt

- Distributed rate limiting.
- Indexed pagination/query expansion.
- Broader preference extraction beyond explicit concise/shorter feedback.
- Durable asynchronous/background execution.
- Blueprint/generic artifact lifecycle parity.
- Legacy/versioned/dead-code cleanup after the submission freeze.
- Deeper retention, deletion, and operational hardening.
