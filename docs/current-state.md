# Agent Col Current State

Last reconciled: August 29, 2026.

This document describes what Agent Col can do in the current checkout. Source
code, tests, and the root-level `repo-map.md` are the authority for these
claims; historical files under `docs/legacy/` are not implementation truth.

## Current Product State

Agent Col is implemented as a persistent collaborative partner: a FastAPI
backend, same-origin browser workspace, Gemini/ADK specialist execution,
Firestore persistence, governed memory, collaborative notes, continuity,
working state, preference learning, and artifacts (`main.py:1280-1417`,
`repo-map.md`).

The README identifies a verified Cloud Run deployment in `us-east4`, so
remaining submission work is final hosted re-verification and freeze rather than
initial deployment (`README.md:17-29`).

## Implemented User-Visible Capabilities

- Google or local-development authentication entry.
- Workspace selection, creation, deletion, and workspace-scoped chat state.
- Conversation UI with idempotent retry, receipts, citations, memory
  clarification choices, continuity choices, and status/error display.
- Supporting drawer sections for Workspace, Artifacts, Notes, Memory, and
  Chats; there is activity/receipt state and rendering support in code, but the
  inspected HTML does not expose a separately labeled Activity drawer section
  (`frontend/index.html:75-222`, `frontend/activity-view.mjs:9-30`).
- Right-side Artifacts Viewer with artifact detail, content display, metadata,
  lifecycle, versioning, feedback, and export behavior.
- Memory inspection plus approval/rejection, correction, revocation, and
  deletion flows where surfaced by the backend.
- Collaborative note proposals, decisions, corrections, archive/restore/delete,
  detail, and event display.
- Chat session list/detail reconstruction.

## Implemented Backend Capabilities

- FastAPI routes for auth/session, workspaces, memory, notes, chat sessions,
  synthesis, artifacts, feedback, and chat (`main.py:1420-2759`,
  `repo-map.md`).
- Firestore-backed chat sessions, messages, turn records, user workspaces,
  memory, note, artifact, feedback, continuity-source, working-state, and
  preference records (`database.py`, `repo-map.md`).
- Google OIDC and local-dev auth modes with Cloud Run fail-closed checks for
  Google auth configuration (`auth.py:66-93`, `auth.py:177-251`).
- Request perimeter middleware for request size, in-memory per-client/path rate
  limiting, cache control, and security headers (`main.py:280-405`).
- Durable chat idempotency with turn claim, replay, live conflict, expired-turn
  resume, deterministic user/model message IDs, and completion validation
  (`database.py:1587-1905`, `database.py:3073-3171`).
- Partial failure responses that preserve already-completed effects where
  possible (`main.py:984-1142`, `main.py:3563-3675`).

## Implemented Frontend Capabilities

- Same-origin API helper with relative-path enforcement, auth headers,
  idempotency headers, JSON handling, timeout/error normalization, and
  structured error details (`frontend/api.mjs:13-119`).
- Immutable chat request construction with generated idempotency keys and exact
  retry body/key preservation (`frontend/requests.mjs:35-108`).
- Structured chat decision requests for memory clarification and continuity
  selections (`frontend/requests.mjs:248-319`).
- Panel-specific rendering for chat, artifacts/work, notes, memory, chats, and
  workspace state (`frontend/app.mjs:359-725`, `repo-map.md`).
- Safe text/markdown rendering and text-based artifact content display
  (`frontend/render.mjs:1-25`, `frontend/markdown-renderer.mjs:3-252`,
  `frontend/work-view.mjs:468-491`).

## Specialist And Tool Capabilities

Current routed specialist capabilities are bounded evidence producers. The
responder does not directly receive model-visible expert tools.

- Research uses Gemini with Google Search grounding, validates provider
  grounding metadata, and returns public citations/receipts only for completed
  validated results (`research_expert_service.py:175-257`, `repo-map.md`).
- Source analyzes supplied public URLs using Gemini URL Context for retrieval,
  then performs a tool-free structured classification pass over grounded
  statements (`source_expert_service.py:24-158`).
- Computation uses bounded ADK computation execution in a temporary in-memory
  invocation session. The computational agent is configured with built-in Python
  code execution, bounded inputs, max LLM calls, timeout handling, and session
  cleanup (`computational_expert.py:34-46`,
  `computational_expert_service.py:63-138`).
- Requirements Verification uses direct tool-free structured Gemini generation
  and local validation against supplied requirement and subject blocks
  (`requirements_verification_service.py:27-139`).
- Artifact routing supports request-bound artifact creation where route and
  artifact constraints validate (`agent_col_routing_v4.py:34-215`,
  `agent_col_artifact_executor.py:156-518`).

## Memory, Notes, Continuity, Working State, And Preferences

Governed profile memory is implemented. It supports model-proposed pending
memory, deterministic policy validation, ambiguous-memory clarification,
approval/rejection, correction, revocation, hard deletion, bounded inspection,
provenance, lifecycle events, and adaptation receipts. Pending proposals are
not active memory until approved (`trusted_memory_service.py:286-633`,
`database.py:6388-6968`).

Collaborative notes are implemented and workspace-scoped. They support pending
proposals, user approval/rejection, correction, archive, restore, deletion,
source provenance, active-note projection, and note events
(`collaborative_note_service.py:188-331`, `database.py:679-1331`).

Continuity is implemented and intentionally bounded. It reads active notes and
prior chat sessions/messages as sources, returning either resolved context with
receipts or ambiguity choices when the reference cannot be resolved safely
(`continuity_service.py:118-239`, `continuity_service.py:282-566`).

Working state is implemented and intentionally bounded/non-authoritative. It is
hidden same-session context, can be unavailable or stale, and cannot authorize
tools, memory, notes, artifacts, identity changes, or durable actions
(`working_state.py:11-101`). In `/api/chat`, the request awaits:

```text
canonical responder completion
-> authoritative chat persistence
-> awaited hidden working-state maintenance
-> HTTP response returned
```

Working-state update failures are logged and swallowed, but when enabled the
maintenance call is awaited before the response returns (`main.py:3483-3562`,
`main.py:3785-3852`).

Preference learning is implemented but intentionally narrow. It stores
non-authoritative observations/hypotheses and currently recognizes explicit
shorter/concise response feedback; surfaced hypotheses are confirmed through
the governed memory clarification path (`preference_learning.py:10-164`,
`preference_learning_service.py:43-152`, `main.py:3733-3779`).

## Artifact Behavior

Implemented artifact capabilities include synchronous blueprint synthesis,
blueprint list/detail, generic single-file artifact create/list/detail,
archive/restore, metadata update, child version creation, blueprint feedback
records, feedback supersession metadata, and chat-routed supported artifact
effects (`main.py:2211-2757`, `generic_artifact_service.py:128-360`,
`artifact_feedback_service.py:133-338`).

Artifact execution is currently request-bound. Durable asynchronous/background
execution is not part of the current runtime path.

## Test And Evidence Status

The root `repo-map.md` records the current source-backed test inventory.
Existing tests cover routing constraints, expert validation, memory
normalization and proposal behavior, collaborative-note lifecycle behavior,
artifact read/feedback behavior, frontend state/retry behavior, and safe
markdown rendering (`repo-map.md`).

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
  are limited in the checked-in index file (`firestore.indexes.json:1-9`).
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
