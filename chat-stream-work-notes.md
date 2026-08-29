# Chat Streaming Work Notes

## 2026-08-29 - Accepted U9B Progressive Chat Streaming Pass

Status: accepted after user manual verification.

Checkpoint target: the accepted uncommitted U9B implementation and these notes
are intended to be committed directly to `origin/main` as one repository
checkpoint.

## Purpose

This pass added progressive rendering for ordinary Agent Col chat responses
without replacing the canonical persisted `ChatResponse` or bypassing the
existing Agent Col lifecycle.

The user-visible stream is provisional. The authoritative turn still consists
of a validated final responder result, successful canonical persistence, and an
attempted hidden working-state update. Only the SSE `final` event tells the
frontend that the turn is complete.

The existing `POST /api/chat` JSON endpoint remains the compatibility and
structured-decision path. The new `POST /api/chat/stream` endpoint is limited to
ordinary conversational requests.

## Final Lifecycle

The implemented streaming lifecycle is:

```text
rate limiting
-> authentication
-> workspace/project ownership
-> stream eligibility
-> idempotency claim/replay/conflict
-> governed history/profile/continuity/working-state context
-> AgentColTurnService
-> existing routing
-> specialist and artifact execution when selected
-> final Agent Col responder through SupervisorRuntime
-> application-owned ADK event normalization
-> provisional SSE delta events
-> canonical responder completion and validation
-> authoritative ChatResponse persistence
-> awaited failure-tolerant hidden working-state maintenance attempt
-> authoritative SSE final event
```

The important distinction is:

```text
user-visible streamed text != authoritative turn completion
```

No streamed fragment is stored as the canonical chat response. The persisted
and final `ChatResponse` remains authoritative.

## Streaming Protocol

The application-level SSE event contract is intentionally small:

### `delta`

```text
event: delta
data: {"text":"append-safe user-visible text"}
```

- Contains only provisional Agent Col response text.
- Is append-only from the frontend's perspective.
- Contains no receipts, citations, internal IDs, routing information, tool
  events, provider metadata, thought parts, hidden reasoning, or working state.

### `final`

```text
event: final
data: <canonical validated ChatResponse JSON>
```

- Is emitted only after authoritative persistence.
- Is emitted after the working-state maintenance attempt.
- Replaces/converges the provisional frontend response immediately.
- Is the only event that marks the UI turn complete.
- Provides authoritative receipts, citations, adaptations, artifacts, memory,
  notes, and continuity metadata.

### `error`

```text
event: error
data: {"detail":"sanitized message","status":502,"provisional":true}
```

- Never exposes provider internals or hidden application state.
- Records whether provisional text may already have been shown.
- May include a canonical structured `partial_failure` when prior actions or
  effects were authoritatively completed.
- Never emits a subsequent `final` when canonical persistence failed.

## Backend Changes

### `supervisor_runtime.py`

- Added `SupervisorRuntime.stream_turn(...)` as the narrow streaming sibling of
  `run_turn(...)`.
- Kept both methods on one shared `_run_turn_events(...)` execution path.
- Uses the installed ADK `StreamingMode.SSE` only inside the existing runtime.
- Added `SupervisorTextDelta` and `SupervisorTurnCompleted` application events.
- Preserved responder ownership, session creation/deletion, validation, tool
  observation, receipts, source handling, and delegation-token cleanup.
- Filters partial events to user-visible text from `Agent_Col` only.
- Ignores thought parts, tool calls/responses, non-Agent-Col authors, and raw ADK
  metadata.
- Preserves the exactly-one validated final Agent Col response contract.

### ADK partial normalization

The normalizer is deterministic and application-owned. It tracks two viable
interpretations of provider partial text:

1. true text deltas that concatenate;
2. cumulative partial snapshots that monotonically extend.

It emits only the common append-safe prefix supported by all still-viable
interpretations. When an interpretation becomes impossible, it can safely emit
from the remaining candidate. If the sequence remains ambiguous, it buffers
instead of guessing. Final text is emitted as a suffix only when it can be
proven to extend the already emitted text; otherwise the frontend waits for the
canonical `final` replacement.

This prevents duplicate output from cumulative ADK snapshots while also
avoiding corruption of valid repeated-prefix true deltas.

### `agent_col_turn_service.py`

- Extended the responder runtime protocol with `stream_turn(...)`.
- Added `AgentColTurnService.stream_turn(...)` beside the existing `run_turn(...)`.
- Added `AgentColTextDelta` and `AgentColTurnCompleted` events.
- Reused the existing routing, specialist, artifact, deadline, receipt, and
  failure-mapping orchestration.
- Streams only the final Agent Col responder after required specialist/artifact
  prework has completed.
- Uses a child task and queue to relay responder deltas while retaining one
  canonical completed result.
- Propagates cancellation into responder work when the installed ASGI stack
  cancels the stream generator.

### `main.py`

- Added `POST /api/chat/stream` using FastAPI `StreamingResponse` and SSE.
- Kept `POST /api/chat` intact as the JSON fallback and structured-decision path.
- Extracted only the narrow shared `_execute_chat(...)` lifecycle needed by both
  transports; the complete chat route was not duplicated.
- Added `/api/chat/stream` to the existing chat rate-limit boundary.
- Enforced ordering of rate limit, authentication, ownership, stream
  eligibility, then idempotency.
- Preserved claim, replay, conflict, history/context loading, routing,
  specialists, artifacts, governed memory, notes, continuity, preference
  learning, canonical response assembly, and persistence behavior.
- Completed idempotency replay emits only canonical `final`; it does not pretend
  to rerun or re-stream provider output.
- Live duplicate claims retain the existing conflict and `Retry-After` behavior.
- Persistence failure after visible deltas emits sanitized `error` and no
  `final`.
- Working-state maintenance remains awaited and failure-tolerant; its failure
  does not suppress a successfully persisted `final`.

## Frontend Changes

### `frontend/api.mjs`

- Added authenticated same-origin POST SSE support through `fetch` and
  `ReadableStream`.
- Parses frames split across arbitrary network chunks and supports CRLF/LF
  framing.
- Batches deltas received in one read to reduce unnecessary DOM updates.
- Converts SSE error events and interrupted streams into bounded `ApiError`
  instances.
- Carries authoritative `partial_failure` metadata separately from provisional
  response prose.

### `frontend/requests.mjs`

- Added explicit endpoint selection.
- Ordinary chat requests use `/api/chat/stream`.
- Memory decisions, memory clarification selections, note decisions,
  continuity selections, artifact-feedback decisions, and other structured
  turns continue to use `/api/chat`.

### `frontend/state.mjs`

- Added `pendingResponseText` without changing the exact pending request used
  for retry/idempotency.
- Added append-only delta accumulation.
- Clears provisional text on completion, failure, workspace changes, chat
  session loads, and new conversations.
- Stores interrupted visible text separately as
  `lastFailure.provisionalResponseText`; it is never inserted into the canonical
  transcript.
- On `final`, commits the canonical response through the existing
  `completePendingTurn(...)` transition.
- On structured partial failure, applies only authoritative memory
  clarifications, continuity choices, collaborative-note proposals/events, and
  panel refresh metadata. Provisional prose does not drive application state.

### `frontend/app.mjs`

- Routes ordinary requests through the SSE helper and structured requests
  through the existing JSON helper.
- Preserves the existing request body and idempotency key.
- Renders after each buffered delta and removes the waiting status on the first
  visible text.
- Renders the canonical final response immediately when `final` arrives.
- Runs artifact, memory, note, and chat-history refreshes only after visible
  canonical completion, so secondary work cannot delay the final message.
- Uses authoritative structured partial-failure metadata for panel refreshes.

### `frontend/chat-view.mjs`

- Added a pending Agent Col response card rendered through the existing safe
  Markdown renderer.
- Added an explicit incomplete state for provisional text when a stream fails.
- Does not render receipts or infer metadata from provisional prose.
- Replaces the pending card with the canonical transcript entry without
  duplicating response text or receipt surfaces.

### `frontend/styles.css`

- Added small pending/incomplete response styles only.
- Pending responses use a restrained dashed treatment.
- Interrupted provisional responses use the existing danger visual language.
- Existing Markdown, transcript, receipt, drawer, artifact, memory, note, and
  layout styling remains in place.

## Files Touched

Production source:

- `supervisor_runtime.py`
- `agent_col_turn_service.py`
- `main.py`
- `frontend/api.mjs`
- `frontend/app.mjs`
- `frontend/chat-view.mjs`
- `frontend/requests.mjs`
- `frontend/state.mjs`
- `frontend/styles.css`

Tests:

- `tests/test_supervisor_runtime.py`
- `tests/test_agent_col_turn_service.py`
- `tests/test_main.py`
- `tests/frontend/api.test.mjs`
- `tests/frontend/chat-view.test.mjs`
- `tests/frontend/requests.test.mjs`
- `tests/frontend/state.test.mjs`
- `tests/frontend/workspace-static.test.mjs`

Documentation:

- `chat-stream-work-notes.md`

## Issues Found And Resolutions

### 1. ADK partials cannot be assumed to be append deltas

Issue: installed ADK streaming can expose partial text in forms that may behave
as deltas or cumulative snapshots. Blind append logic duplicates cumulative
content.

Resolution: application-owned candidate normalization emits only text proven
append-safe. Ambiguous sequences buffer until disambiguated or canonical final.

### 2. Repeated-prefix true deltas are ambiguous

Issue: a chunk can begin with already emitted text while still being a valid
new true delta. Treating every repeated prefix as a snapshot can drop text.

Resolution: retain both candidate interpretations and emit only their common
prefix. Tests cover true deltas, cumulative snapshots, and repeated-prefix
ambiguity.

### 3. Streaming initially missed the existing rate-limit boundary

Issue: the new route was not initially included in the existing chat rate-limit
predicate.

Resolution: `/api/chat/stream` now shares the same rate-limit boundary as
`/api/chat`, with regression coverage.

### 4. Stream eligibility initially ran before auth/ownership

Issue: rejecting structured input before authentication or ownership checks
could change the established security/lifecycle ordering.

Resolution: eligibility is checked only after effective authentication and
workspace/project ownership resolution, and before idempotency claim.

### 5. Secondary refreshes delayed visible canonical completion

Issue: artifact, memory, note, and history reloads initially occurred before the
final render, making the authoritative message appear later than necessary.

Resolution: canonical state is committed and rendered immediately on `final`;
secondary authoritative refreshes follow.

### 6. Partial failures initially retained effects only as retry metadata

Issue: artifact refresh information was retained, but authoritative memory
clarifications, continuity choices, and note proposals/events were not restored
into their decision UI state after a partial failure.

Resolution: `failPendingTurn(...)` now projects those structured authoritative
effects through the same existing helpers used on successful completion. It
does not inspect provisional prose.

### 7. Client disconnect behavior required implementation evidence

Issue: client disconnect cannot be assumed to release idempotency claims or
automatically cancel every provider operation.

Resolution: the installed Starlette/Uvicorn ASGI behavior cancels the streaming
generator on `http.disconnect`, and cancellation is propagated through the turn
service/runtime where supported. No new claim-release behavior was invented.

- Disconnect before persistence leaves the existing truthful in-progress claim
  for normal expiry/reclaim recovery.
- Disconnect after persistence but before receipt of `final` leaves a completed
  canonical turn; retry returns final-only replay.
- A turn is never marked completed without canonical persistence.

## TDD And Verification Evidence

Behavioral tests were written and observed RED before production changes for:

- true-delta and cumulative/snapshot ADK events;
- duplicate prevention and repeated-prefix ambiguity;
- thought/tool/non-Agent-Col filtering;
- routing, specialist, artifact, and responder streaming boundaries;
- SSE delta/final/error ordering;
- persistence-before-final ordering;
- persistence and working-state failures;
- replay, live conflict, timeout, recovery, and disconnect behavior;
- structured-decision JSON compatibility;
- frontend frame parsing, accumulation, interruption, safe Markdown, canonical
  convergence, immediate final rendering, and structured partial effects.

Final automated results:

- Focused backend: 318 passed, with one existing ADK deprecation warning.
- Focused frontend: 133 passed.
- Full frontend: 193 passed.
- Full backend: 2475 passed and 7 failed, with one warning.
- Python compilation passed for changed backend modules.
- JavaScript syntax checks passed for changed frontend modules.
- `git diff --check` passed.
- Local `/workspace` and `/api/auth/config` checks returned HTTP 200.
- User manual verification completed successfully on 2026-08-29.

The seven backend failures were separately reproduced against clean `HEAD` and
were not U9B regressions:

- three computation-pipeline smoke failures from a missing relocated fixture;
- one routing-v3 smoke failure from a relocated-module import;
- three tool-belt orchestration fake-request failures lacking
  `working_state_service`.

## Warning For Future Streaming Changes

Streaming crosses runtime, orchestration, transport, persistence, retry, and UI
state boundaries. A visually small streaming change can alter authoritative
behavior. Treat future mechanical changes as high risk and repeat the lifecycle
investigation and TDD process before editing.

### Visual changes that are generally safe when kept presentation-only

The following can usually be changed in a bounded visual pass:

- colors, borders, spacing, typography, and layout of `.turn-model--pending` and
  `.turn-model--incomplete`;
- waiting animation appearance and reduced-motion styling;
- visual distinction between provisional and completed assistant cards;
- Markdown block spacing inside the existing safe renderer output;
- responsive sizing that does not change DOM ownership or state transitions;
- non-semantic decorative icons that remain hidden from assistive technology.

Even these changes must preserve readable incomplete/error states, safe Markdown
rendering, no text overlap, and a clear visual distinction between provisional
and authoritative content.

### Changes requiring special attention and renewed behavioral approval

Do not make the following as visual cleanup or incidental refactoring:

- changing when `final` is emitted or when the UI marks a turn complete;
- rendering receipts, citations, adaptations, artifacts, memory, notes, or
  continuity data before canonical `final`;
- deriving panel refreshes or decisions from streamed prose;
- changing ADK event interpretation, author filtering, thought/tool filtering,
  or append normalization;
- appending raw provider events directly in the frontend;
- calling Google GenAI/ADK directly from `main.py` or bypassing
  `SupervisorRuntime`/`AgentColTurnService`;
- moving persistence after `final`, persisting fragments, or replacing the
  canonical `ChatResponse` with streamed text;
- changing cancellation, timeout, claim release, idempotency conflict, replay,
  or expired-turn recovery semantics;
- moving stream eligibility ahead of authentication or ownership checks;
- streaming structured memory, clarification, note, continuity, or artifact
  feedback decisions without a separately approved contract pass;
- awaiting secondary panel/history refreshes before rendering canonical final;
- changing retry to create a new request body or idempotency key;
- exposing raw provider errors, internal IDs, routing data, hidden working state,
  or reasoning content.

### Required invariants for any future implementation pass

Future work must preserve:

```text
rate limit -> auth -> ownership -> eligibility -> idempotency
```

and:

```text
validated responder final
-> authoritative persistence
-> working-state maintenance attempt
-> final event
```

The normalizer must remain small, deterministic, application-owned, and
append-safe. If output cannot be proven safe to append, buffer it. The frontend
must understand only the application SSE contract, never raw ADK semantics.

Keep `/api/chat` as the final-only fallback until a separately approved pass
proves that changing this compatibility boundary is necessary and safe.
