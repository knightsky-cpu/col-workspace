# Phase 3B Trusted Memory M7.4 Production Integration Plan

**Goal:** Enable the governed pending-memory proposal tool through `/api/chat`
without weakening consent, provenance, idempotency, replay, tool restraint, or
safe failure handling.

**Architecture:** FastAPI constructs one `TrustedMemoryService` and injects it
into the ADK supervisor. Every invocation receives application-owned source
message provenance and an optional owned turn lease. Idempotent turn claims
recover precompleted receipts, the runtime deduplicates them against public ADK
function responses, and turn completion verifies rather than overwrites those
effects. Partial provider failures expose only validated completed receipts.

## Preserved invariants

- Agent_Col remains the sole user-facing conversational owner.
- The model controls only memory category and candidate value.
- Pending proposals never activate memory.
- Firestore remains durable truth; ADK sessions remain invocation-scoped.
- Completed receipts come from deterministic application actions or validated
  public ADK function responses, never model prose.
- A completed idempotent replay invokes neither Gemini nor the proposal tool.
- Headerless chat remains explicitly non-retry-safe across process failure.
- Existing approval, rejection, adaptation, history, timeout, and error
  contracts remain compatible.
- Logs and HTTP details exclude messages, values, identifiers, keys, provider
  payloads, and tool internals.

## Task 1: Public response and durable turn-effect schema

**Files:** `schemas.py`, `chat_turns.py`, schema/turn tests.

- RED: `ChatResponse` rejects or omits one memory proposal receipt.
- GREEN: add bounded `memory_proposals` and the strict partial-failure model.
- RED: a resumed in-progress claim cannot recover precompleted actions and
  proposal receipts; a completed replay drops them.
- GREEN: add typed precompleted effects to `ChatTurnClaim`, validate stored
  effects, and preserve them in replay.

## Task 2: Turn-effect persistence and completion protection

**Files:** `database.py`, `tests/test_chat_turn_database.py`.

- RED: turn completion overwrites a precompleted proposal effect.
- GREEN: require the final typed response to preserve every stored effect and
  reject omitted or conflicting proposal receipts without writes.
- RED: an idempotent structured memory decision has no pre-provider durable
  action receipt.
- GREEN: add one owned-turn action-recording primitive that merges an identical
  deterministic action, preserves proposal effects, and returns refreshed
  typed claim effects.

## Task 3: Runtime provenance, recovery, and partial evidence

**Files:** `supervisor_runtime.py`, `tests/test_supervisor_runtime.py`.

- RED: server-owned message identity, decision state, and turn lease do not
  reach ADK invocation state.
- GREEN: extend `SupervisorTurnContext` and populate only server-owned state.
- RED: resumed precompleted receipts are absent from runtime results and can
  conflict with a repeated identical tool response.
- GREEN: seed, validate, and deduplicate precompleted receipts; provide a
  bounded application-owned operational context to Agent_Col.
- RED: provider failure or timeout after a validated receipt loses the receipt.
- GREEN: attach only validated accumulated effects to typed runtime errors.

## Task 4: FastAPI production orchestration

**Files:** `main.py`, `tests/test_main.py`.

- RED: lifespan constructs a tool-free supervisor instead of injecting the
  existing memory service.
- GREEN: inject the same service instance into `create_supervisor_app()`.
- RED: headerless and idempotent paths omit source message ID, decision state,
  lease, and precompleted effects from `SupervisorTurnContext`.
- GREEN: provide those server-owned values after message persistence and lease
  renewal.
- RED: successful chat, completion, and replay omit memory proposal receipts.
- GREEN: return, persist, and replay exactly one validated receipt.
- RED: idempotent decision actions are not persisted before ADK invocation.
- GREEN: record the deterministic decision action on the owned turn first.
- RED: provider/runtime `502` or timeout `504` after a completed effect returns
  a content-free body that hides the effect.
- GREEN: return the strict partial-failure envelope; preserve existing bodies
  when no effect completed; release only the owned lease.
- RED: proposal-origin/category conflicts and persistence failures are mapped
  as generic provider failures.
- GREEN: map typed causes to safe `409` and `500` responses.

## Task 5: Verification and manual acceptance

- Run focused schema, turn-database, runtime, and main tests after each cycle.
- Run Python compilation and `git diff --check`.
- Run the full suite because chat schemas, persistence, and runtime are shared.
- Provide one live curl for an explicit reusable preference and one no-tool
  regression curl.
- Require Firestore inspection of the pending proposal, origin guard, turn
  effect, and unchanged active profile.
- Stop as **implemented, pending manual verification**. Do not commit or push.

## Exclusions

- M7.5 behavioral restraint evaluations and broad live routing matrix.
- Automatic approval, natural-language consent parsing, or generic writes.
- Search, URL, code-execution, requirements, or synthesis tool integration.
- Authentication, ownership enforcement, rate limiting, jobs, UI, or new
  infrastructure.

## Stop conditions

- Any server-owned field appears in the model-visible tool declaration.
- A proposal receipt must be inferred from model prose.
- Turn completion can omit or replace a precompleted effect.
- Partial failures expose unvalidated or private content.
- Existing idempotency, approval/rejection, or no-tool behavior regresses.
