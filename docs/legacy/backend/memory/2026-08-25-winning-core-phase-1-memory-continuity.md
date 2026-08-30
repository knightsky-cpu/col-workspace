# Winning Core Phase 1 Memory Continuity Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Repository `AGENTS.md` approval gates
> remain controlling: do not implement a pass until the user explicitly
> approves that pass, and do not checkpoint unaccepted source work.

**Status:** Pass 1A accepted for checkpoint. Its original Pass 1B/1C outline is
superseded by
`docs/superpowers/plans/2026-08-25-winning-core-phase-1-remaining-work.md`.

**Goal:** Give the browser a deterministic, retry-safe clarification-choice
workflow and close judge-grade cross-session memory proof without redesigning
the accepted V1/V2 memory lifecycle.

**Architecture:** Keep Firestore and the application as the authority. Add an
explicit clarification-selection field to the existing idempotent chat-turn
contract, bind it to the server-owned clarification ID and candidate index,
and consume it through `TrustedMemoryService` before Agent Col responds. Keep
the resulting proposal pending and pass its completed action/proposal receipts
into the existing responder, partial-failure, reclaim, and replay paths. Render
the active clarification and adaptation receipts from structured API data,
never from Agent Col prose.

**Tech Stack:** Python 3.14, FastAPI, Pydantic 2, Google ADK, Google GenAI SDK,
Firestore async transactions, vanilla JavaScript ES modules, Node test runner,
pytest.

**Spec:**
[`docs/aug-25-2026-final-checklist.md`](../../finalization/aug-25-2026-final-checklist.md),
[`docs/design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md`](../../../design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md),
and
[`docs/superpowers/specs/2026-08-23-phase-4a-lightweight-browser-workspace-design.md`](../../frontend/workspace-shell/2026-08-23-phase-4a-lightweight-browser-workspace-design.md).

**Verified baseline:** `36ec6ab Document Winning Core execution checklist`

## Global constraints

- Profile memory remains user-global; no workspace-note behavior enters this
  phase.
- A clarification remains session-scoped, expires after 15 minutes, and may be
  selected only on the first subsequent user turn.
- The public choice carries a server-owned `clarification_id` and bounded
  `selected_candidate_index`; category and value are resolved only from the
  persisted envelope.
- Exactly one structured decision is permitted per chat turn: memory proposal
  approval/rejection, memory clarification selection, or artifact feedback.
- Selection creates one pending V2 proposal. It never activates memory.
- A proposal receipt and clarification receipt must never coexist in one turn.
- Exact retries reuse the original idempotency key and request body.
- Reclaim, partial failure, responder timeout, and completed-turn replay retain
  authoritative effects.
- Existing semantic text selection through the ADK memory tool remains
  supported; the UI path does not remove or weaken it.
- V1/V2 inspection, approval, correction, rejection, revocation, deletion,
  context projection, synthesis adaptation, artifact adaptation, and response
  truthfulness must not regress.
- Internal identifiers are not primary user-facing labels, and all labels are
  rendered with `textContent`.
- No new dependency, endpoint family, Firestore collection, generalized
  decision framework, or frontend redesign is authorized.
- This plan has three separate approval gates: Pass 1A backend contract, Pass
  1B browser workflow, and Pass 1C live evidence closure.

## Verified current behavior and gap

- `memory_clarifications.py` already defines a two-to-five-choice envelope,
  human labels, 15-minute expiry, ownership checks, first-subsequent-turn
  validation, and an index-only internal selection.
- `database.py` atomically persists the active clarification pointer, consumes
  one selection into one V2 proposal, records the proposal turn effect, and
  recovers clarification/proposal effects during lease reclaim and replay.
- `memory_proposal_tool.py` exposes provider-mediated
  `clarification_selection`, and `trusted_memory_service.py` consumes it only
  with a retry-safe turn lease.
- `schemas.py`, `main.py`, `agent_col_turn_service.py`, and
  `supervisor_runtime.py` already project at most one clarification receipt in
  success and partial-failure contracts.
- `ChatRequest` and `ChatTurnRequest` do not expose a deterministic user choice.
  A browser-generated prose answer would still rely on Gemini selecting the
  correct candidate and calling the tool.
- `frontend/state.mjs` preserves the successful response in the current
  transcript, but `frontend/chat-view.mjs` ignores `memory_clarifications` and
  `adaptations`.
- Reopening a stored chat restores message text only; it cannot currently
  recover an unconsumed active clarification from the owned session.
- `frontend/memory-view.mjs` already supports V1/V2 proposal approval and
  rejection plus active-signal revoke/delete controls.
- `startNewConversation()` already creates a new session ID, and
  `MemoryContextRenderer` already supplies approved V1/V2 signals plus
  authoritative adaptation receipts to a later session.

## Expected file map

**Pass 1A production files**

- Modify `schemas.py`: public selection request and recoverable active
  clarification on session detail.
- Modify `chat_turns.py`: include selection in the durable request identity.
- Modify `database.py`: persist and compare selection request metadata, bind
  direct selection to an explicit clarification ID, and retrieve the owned
  active clarification.
- Modify `trusted_memory_service.py`: add deterministic direct-selection
  command/service while preserving semantic tool selection.
- Modify `main.py`: orchestrate direct selection, error translation, receipt
  merging, responder context, reclaim, partial failure, and replay.

**Pass 1B production files**

- Modify `frontend/requests.mjs`: validated immutable selection request builder.
- Modify `frontend/state.mjs`: retain/recover/clear active clarification state
  and record structured clarification activity.
- Modify `frontend/chat-view.mjs`: render choice controls and adaptation
  receipts.
- Modify `frontend/app.mjs`: submit choice controls through the structured chat
  request.
- Modify `frontend/index.html`: add one stable clarification-control region.
- Modify `frontend/styles.css`: accessible responsive choice layout and stable
  disabled/pending states.

**Expected test files**

- Modify `tests/test_schemas.py`.
- Modify `tests/test_chat_turns.py` only if constructor/identity coverage is not
  already fully exercised through database tests.
- Modify `tests/test_chat_turn_database.py`.
- Modify `tests/test_memory_clarification_database.py`.
- Modify `tests/test_memory_proposal_service.py`.
- Modify `tests/test_main.py`.
- Modify `tests/frontend/requests.test.mjs`.
- Modify `tests/frontend/state.test.mjs`.
- Modify `tests/frontend/chat-view.test.mjs`.
- Modify `tests/frontend/workspace-static.test.mjs`.

`memory_clarifications.py`, `memory_proposal_tool.py`,
`agent_col_turn_service.py`, `supervisor_runtime.py`, `supervisor.py`, and
`frontend/memory-view.mjs` are expected regression surfaces, not expected
production edits. Stop and revise this plan if implementation requires changing
their accepted contracts.

---

## Pass 1A - Deterministic Public Clarification Selection

### Task 1: Define the public selection and exclusivity contracts

**Files:**

- Modify: `schemas.py`
- Test: `tests/test_schemas.py`

**Interfaces:**

- Produces: `MemoryClarificationSelectionRequest` with
  `clarification_id: IdentifierStr` and
  `selected_candidate_index: int` bounded from 0 through 4.
- Extends: `ChatRequest.memory_clarification_selection`.
- Extends: `ChatSessionDetailResponse.active_memory_clarification` so an owned
  open clarification can be recovered after reopening the session.

- [ ] **Step 1: Write RED schema tests**

```python
selection = MemoryClarificationSelectionRequest(
    clarification_id="memory-clarification--abc",
    selected_candidate_index=1,
)
request = ChatRequest(
    project_id="project-1",
    session_id="session-1",
    user_id="user-1",
    message="Select Response length: Detailed.",
    memory_clarification_selection=selection,
)
assert request.memory_clarification_selection == selection
```

Add parameterized failures for index `-1`, index `5`, malformed identifiers,
and every pair among `memory_decision`, `memory_clarification_selection`, and
`artifact_feedback_decision`. Add session-detail validation with zero or one
`active_memory_clarification`.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_schemas.py -k "clarification_selection or structured_decision or active_memory_clarification"
```

Expected: failures because the request type and fields do not exist and the
current two-field validator does not enforce three-way exclusivity.

- [ ] **Step 3: Implement the minimum schema**

```python
class MemoryClarificationSelectionRequest(StrictModel):
    clarification_id: IdentifierStr
    selected_candidate_index: int = Field(ge=0, le=4)


class ChatRequest(StrictModel):
    # existing fields remain unchanged
    memory_clarification_selection: (
        MemoryClarificationSelectionRequest | None
    ) = None

    @model_validator(mode="after")
    def allow_only_one_structured_decision(self) -> Self:
        decisions = (
            self.memory_decision,
            self.memory_clarification_selection,
            self.artifact_feedback_decision,
        )
        if sum(item is not None for item in decisions) > 1:
            raise ValueError("Structured decisions are mutually exclusive.")
        return self
```

Add `active_memory_clarification: MemoryClarificationReceipt | None = None` to
`ChatSessionDetailResponse` without changing existing response defaults.

- [ ] **Step 4: Verify GREEN**

Run the RED command again, then:

```bash
venv/bin/pytest -q tests/test_schemas.py
```

Expected: all schema tests pass.

### Task 2: Make selection part of the retry-safe turn identity

**Files:**

- Modify: `chat_turns.py`
- Modify: `database.py`
- Test: `tests/test_chat_turn_database.py`

**Interfaces:**

- Consumes: `MemoryClarificationSelectionRequest`.
- Extends: `ChatTurnRequest.memory_clarification_selection`.
- Persists: `memory_clarification_selection` as metadata only; no prompt or
  candidate value is copied into the turn document.

- [ ] **Step 1: Write RED claim, conflict, reclaim, and replay tests**

Create a request containing:

```python
memory_clarification_selection=MemoryClarificationSelectionRequest(
    clarification_id="memory-clarification--clarify-1",
    selected_candidate_index=0,
)
```

Require the initial turn document to contain the JSON selection, exact retry to
match, a changed clarification ID or index to raise `ChatTurnConflictError`,
and reclaim/replay to preserve the existing action/proposal effects. Require
all three structured decision kinds to remain mutually exclusive.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_chat_turn_database.py -k "clarification_selection"
```

Expected: failures because `ChatTurnRequest` and stored request comparisons do
not contain the selection.

- [ ] **Step 3: Implement durable request matching**

Add the field to `ChatTurnRequest`, validate its type in
`claim_chat_turn()` and `_validate_chat_turn_claim()`, enforce three-way
exclusivity, write its JSON form to the turn document, and compare it in both
`_assert_chat_turn_request_matches()` and
`_assert_chat_turn_claim_matches_document()`. Use `.get()` so pre-Phase-1
turns without the field continue to compare as `None`.

- [ ] **Step 4: Verify GREEN**

Run the RED command again, then:

```bash
venv/bin/pytest -q tests/test_chat_turn_database.py tests/test_chat_turns.py
```

Expected: all selected suites pass with old-turn compatibility retained.

### Task 3: Bind deterministic selection to the persisted clarification

**Files:**

- Modify: `database.py`
- Modify: `trusted_memory_service.py`
- Test: `tests/test_memory_clarification_database.py`
- Test: `tests/test_memory_proposal_service.py`

**Interfaces:**

- Produces: `SelectMemoryClarificationCommand`.
- Produces: `TrustedMemoryService.select_memory_clarification()` returning the
  existing `NaturalMemoryProposalResult`.
- Extends: `consume_memory_clarification_to_proposal_v2()` with
  `expected_clarification_id: str | None`; the ADK semantic path supplies
  `None`, while the deterministic UI path supplies the receipt ID.

- [ ] **Step 1: Write RED explicit-ID and service tests**

Require a matching ID/index to create one pending V2 proposal whose
`clarification_id` and `evidence_message_id` come from the stored envelope.
Require a stale ID, different exact-retry index, expired envelope, non-first
subsequent turn, and missing active pointer to fail without writes. Require an
exact same-turn retry to return the same proposal.

Service test command shape:

```python
result = await service.select_memory_clarification(
    SelectMemoryClarificationCommand(
        user_id="user-1",
        workspace_id="project-1",
        session_id="session-1",
        source_message_id="turn--select--user",
        clarification_id="memory-clarification--clarify-1",
        selected_candidate_index=0,
        turn_lease=ProposalTurnLease(
            turn_id="select-turn",
            owner_token="owner-1",
        ),
    )
)
assert result.status == "pending"
```

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_memory_clarification_database.py tests/test_memory_proposal_service.py -k "explicit_id or direct_selection"
```

Expected: failures because no direct command/service or explicit-ID binding
exists.

- [ ] **Step 3: Implement one shared consumption path**

Validate the direct command, construct the existing internal
`MemoryClarificationSelection`, and call the database transaction with the
expected clarification ID. Reject a mismatch before any proposal write. Keep
the existing `handle_natural_memory_decision()` semantic branch, but route both
branches through the same private service helper so proposal receipts and
validation do not diverge.

Introduce a user-state selection exception only for selectable conditions
(stale ID, expired, consumed, wrong turn, invalid index). Preserve
`MemoryClarificationStateError` for malformed Firestore state and
`ChatSessionOwnershipError` for ownership failures; do not classify corruption
as a user conflict.

- [ ] **Step 4: Verify GREEN and semantic-path compatibility**

Run:

```bash
venv/bin/pytest -q tests/test_memory_clarifications.py tests/test_memory_clarification_database.py tests/test_memory_proposal_service.py tests/test_memory_proposal_tool.py
```

Expected: all tests pass, including provider-mediated semantic selection.

### Task 4: Recover one active owned clarification with session detail

**Files:**

- Modify: `database.py`
- Modify: `main.py`
- Test: `tests/test_chat_turn_database.py`
- Test: `tests/test_main.py`

**Interfaces:**

- Produces: `ChatSessionDetailResponse.active_memory_clarification` from the
  session's `active_memory_clarification_id` and owned envelope.
- Does not list old, consumed, or unrelated clarification documents.

- [ ] **Step 1: Write RED retrieval tests**

Require owned open state to return `clarification_receipt(envelope)`, no pointer
to return `None`, a consumed/expired envelope to return no selectable choice,
and a missing or mismatched pointed document to fail as invalid stored state.
Require an ownership mismatch to preserve the route's existing unavailable
behavior and never return choice labels.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_chat_turn_database.py tests/test_main.py -k "session_detail and active_memory_clarification"
```

Expected: failures because session detail currently returns messages only.

- [ ] **Step 3: Implement bounded recovery**

Read only the active pointer after validating the session owner/workspace. Read
at most one envelope document, validate it through
`MemoryClarificationEnvelope`, and project only an open, unexpired receipt.
Pass an application clock/`observed_at` into the database boundary rather than
using browser time as authority. Translate malformed pointed state to a safe
500 response without logging labels or candidate values.

- [ ] **Step 4: Verify GREEN**

Run the RED command again, then the complete chat-session database/API tests.

### Task 5: Orchestrate direct selection before the responder

**Files:**

- Modify: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**

- Consumes: `ChatRequest.memory_clarification_selection`.
- Calls: `TrustedMemoryService.select_memory_clarification()` only after a
  retry-safe turn claim exists.
- Seeds: completed `propose_memory_signal` action and one pending proposal into
  the existing `AgentColTurnCommand` precompleted effects.
- Returns: merged authoritative action/proposal/adaptation receipts.

- [ ] **Step 1: Write RED API orchestration tests**

Require:

1. selection without `Idempotency-Key` returns 422 before persistence;
2. a valid selection calls the deterministic service with authenticated user,
   effective workspace, claimed source message ID, explicit clarification ID,
   bounded index, and current turn lease;
3. the responder receives `memory_decision_present=True`, one precompleted
   proposal action, and one precompleted proposal;
4. success returns exactly one action and proposal and no clarification;
5. completed replay returns the identical response without calling the service;
6. selection conflict returns a content-safe 409;
7. malformed durable state returns a content-safe 500;
8. ownership mismatch uses the existing uniform unavailable response;
9. responder timeout/failure after consumption preserves the proposal in the
   partial response and exact retry reuses it;
10. ordinary chat, proposal approval/rejection, and artifact feedback remain
    unchanged.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_main.py -k "memory_clarification_selection"
```

Expected: failures because FastAPI does not orchestrate direct selection.

- [ ] **Step 3: Implement minimal orchestration**

Use a single `structured_memory_decision_present` boolean for proposal
approval/rejection or clarification selection when configuring Agent Col.
Keep separate tuples for precompleted structured actions and proposals, merge
them with reclaimed effects, and use `_merge_receipts()` for success and
partial failure. A selection must not call the ADK proposal tool again.

Release a claimed lease safely before translating a pre-responder selection
failure. Do not include clarification IDs, candidate labels, or values in logs.

- [ ] **Step 4: Verify GREEN and backend integration**

Run:

```bash
venv/bin/pytest -q tests/test_schemas.py tests/test_memory_clarifications.py tests/test_memory_clarification_database.py tests/test_memory_proposal_service.py tests/test_memory_proposal_tool.py tests/test_chat_turns.py tests/test_chat_turn_database.py tests/test_agent_col_turn_service.py tests/test_supervisor_runtime.py tests/test_main.py
```

Expected: all tests pass with only the existing ADK deprecation warning.

**Pass 1A manual acceptance targets**

1. API selection with a known open clarification produces one pending proposal.
2. Exact retry returns the same proposal/action response.
3. A changed index with the same key returns idempotency conflict.
4. Reopening the owned session before selection returns the same bounded choice
   receipt.
5. No browser behavior is claimed yet; Pass 1A is accepted on API/runtime
   behavior.

Stop after reporting **implemented, pending manual verification**. Do not begin
Pass 1B without explicit approval.

---

## Pass 1B - Browser Clarification and Adaptation Proof Surface

### Task 6: Build the immutable browser selection request

**Files:**

- Modify: `frontend/requests.mjs`
- Test: `tests/frontend/requests.test.mjs`

**Interfaces:**

- Produces: `buildMemoryClarificationSelectionChatRequest(context, choice,
  cryptoLike)`.
- Request body contains `memory_clarification_selection` plus an honest
  application-generated transcript message; labels are never treated as
  authority.

- [ ] **Step 1: Write RED builder tests**

```javascript
const request = buildMemoryClarificationSelectionChatRequest(context, {
  clarification_id: "memory-clarification--clarify-1",
  candidate_index: 1,
  category_label: "Response length",
  value_label: "Detailed",
}, cryptoLike);

assert.deepEqual(request.body.memory_clarification_selection, {
  clarification_id: "memory-clarification--clarify-1",
  selected_candidate_index: 1,
});
assert.equal(request.body.message, "Select Response length: Detailed.");
assert.equal(Object.isFrozen(request.body), true);
```

Require malformed ID, non-integer/out-of-range index, empty label, and any
coexisting structured decision to throw before fetch.

- [ ] **Step 2: Verify RED**

Run:

```bash
node --test tests/frontend/requests.test.mjs
```

Expected: failure because the builder does not exist.

- [ ] **Step 3: Implement the minimum builder and GREEN**

Validate, normalize, and delegate to `buildChatRequest()`. Extend its
exclusivity check to all three structured decisions. Run the RED command and
require all tests to pass.

### Task 7: Track active, pending, consumed, and recovered clarification state

**Files:**

- Modify: `frontend/state.mjs`
- Test: `tests/frontend/state.test.mjs`

**Interfaces:**

- Adds: `activeMemoryClarification` to workspace state.
- Successful clarification response sets it.
- Starting a selection marks the matching choice pending without discarding the
  exact retry request.
- Successful selection clears it.
- Failed selection keeps it available and preserves exact retry.
- Reopened session detail restores it from
  `active_memory_clarification`.
- New conversation or workspace switch clears it.

- [ ] **Step 1: Write RED state-transition tests**

Cover ordinary response with no clarification, clarification success,
selection pending, selection failure, exact retry, selection success, session
reopen, new conversation, and workspace switch. Also require
`activityEntriesFromResponse()` to add a human-readable clarification entry
without exposing its ID.

- [ ] **Step 2: Verify RED**

Run:

```bash
node --test tests/frontend/state.test.mjs
```

Expected: failures because active clarification state is absent.

- [ ] **Step 3: Implement minimal immutable transitions and GREEN**

Store only the structured receipt returned by the API. Derive pending/consumed
state from `pendingTurn`, `lastFailure`, and completed request bodies; do not
trust response prose. Run the RED command and require all tests to pass.

### Task 8: Render accessible choices and authoritative adaptations

**Files:**

- Modify: `frontend/chat-view.mjs`
- Modify: `frontend/app.mjs`
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/chat-view.test.mjs`
- Test: `tests/frontend/workspace-static.test.mjs`

**Interfaces:**

- Renders: one unframed clarification region between transcript and composer.
- Emits: the exact selected receipt choice through
  `handlers.onSelectMemoryClarification(choice)`.
- Renders: adaptation receipt category and value in the originating turn's
  receipt list.

- [ ] **Step 1: Write RED rendering and interaction tests**

Require two-to-five buttons with visible `category_label: value_label`, button
type, bounded data attributes, and no visible clarification ID. Require one
click to emit the exact structured choice once, all controls disabled while a
turn is pending, expired choices disabled, and successful selection to remove
the region. Require `renderReceipts()` to show `Adaptation: Response length -
Detailed` from structured receipt data and ignore prose claims.

- [ ] **Step 2: Verify RED**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs tests/frontend/workspace-static.test.mjs
```

Expected: failures because no region, handler, or adaptation rendering exists.

- [ ] **Step 3: Implement the minimum UI**

Use a semantic heading plus ordinary buttons in one stable region. Render all
server labels through `textContent`; use the structured ID only as a data value
and request field. Wire the handler in `app.mjs` to the Task 6 builder and
existing `submitRequest()` path. Use existing button, focus-visible, muted,
error, and responsive conventions. Do not create a modal, nested card, new
navigation section, or separate approval mechanism.

- [ ] **Step 4: Verify GREEN and frontend regression**

Run:

```bash
node --test tests/frontend/requests.test.mjs tests/frontend/state.test.mjs tests/frontend/chat-view.test.mjs tests/frontend/memory-view.test.mjs tests/frontend/workspace-static.test.mjs tests/frontend/workspace-view.test.mjs
```

Expected: all selected frontend files pass.

### Task 9: Run the Phase 1 integrated verification boundary

No production changes are permitted in this task.

- [ ] Run the complete directly affected backend boundary:

```bash
venv/bin/pytest -q \
  tests/test_schemas.py \
  tests/test_memory_policy.py \
  tests/test_memory_policy_v2.py \
  tests/test_memory_context.py \
  tests/test_memory_clarifications.py \
  tests/test_memory_clarification_database.py \
  tests/test_memory_proposal_guard_database.py \
  tests/test_memory_proposal_service.py \
  tests/test_memory_proposal_tool.py \
  tests/test_memory_inspection_database.py \
  tests/test_memory_approval_database.py \
  tests/test_memory_rejection_database.py \
  tests/test_memory_lifecycle_database.py \
  tests/test_chat_turns.py \
  tests/test_chat_turn_database.py \
  tests/test_agent_col_turn_service.py \
  tests/test_supervisor.py \
  tests/test_supervisor_runtime.py \
  tests/test_main.py
```

- [ ] Run all frontend tests because the shared chat state, request builder, and
  workspace shell are changed:

```bash
node --test tests/frontend/*.test.mjs
```

- [ ] Compile changed Python modules:

```bash
venv/bin/python -m compileall -q \
  schemas.py chat_turns.py database.py trusted_memory_service.py main.py
```

- [ ] Run `git diff --check` and inspect every warning, skip, and failure count.
- [ ] Review the diff for raw memory logging, model-selected authority,
  duplicate effects, unbounded labels, stale controls, unrelated refactors, and
  changes outside the expected file map.

The full unrelated repository suite is not required unless focused tests reveal
a cross-cutting regression. This phase already runs the complete shared memory,
chat-turn, orchestration, API, and frontend boundaries.

**Pass 1B manual visual/runtime acceptance targets**

Use Google OIDC at `http://127.0.0.1:8000/workspace` on desktop and a narrow
mobile viewport.

1. Submit: `Please remember two things: I prefer detailed answers, and I prefer step-by-step explanations.`
   Expected: exactly two bounded choice buttons; no proposal exists yet.
2. Reopen the same chat before choosing.
   Expected: the same open choices return; no duplicate clarification appears.
3. Choose `Response length: detailed`.
   Expected: one structured turn, disabled controls while pending, exactly one
   pending Response length proposal, and no clarification receipt in that turn.
4. Retry the exact request only if a controlled transport failure is induced.
   Expected: the same proposal is reused; no duplicate proposal or event.
5. Approve through the Memory panel.
   Expected: the proposal disappears and Response length becomes active.
6. Verify list-valued regression with `Please remember that I prefer macOS and Linux development environments.`
   Expected: one list-valued proposal, not a clarification.
7. Verify keyboard focus, long-label wrapping, disabled state, no overlapping
   controls, and readable layout at desktop and mobile widths.

Stop after reporting **implemented, pending manual verification**. Do not begin
Pass 1C until the user accepts Pass 1B.

---

## Pass 1C - Judge-Grade Cross-Session Proof and Evidence Closure

This is a verification/evidence pass. It changes no production source unless a
failure is found. Any failure requires systematic debugging, a separately
approved correction plan, and a new TDD pass.

### Task 10: Prove adaptation, correction, revocation, and deletion live

- [ ] Launch Google OIDC mode with the ignored OAuth client ID and valid ADC.
- [ ] Use a fresh preference category or clean up existing test state first.
- [ ] Complete the approved clarification workflow from Pass 1B.
- [ ] Click `New conversation` and record the new session ID boundary through
  observable chat/session behavior without displaying private IDs in primary UI.
- [ ] Submit a neutral task that does not restate the preference:
  `Compare two practical ways to organize a week of study.`
- [ ] Require a visibly detailed response and an authoritative Response length
  adaptation receipt.
- [ ] Inspect Memory and require the active signal plus approved event with the
  clarified provenance relationship.
- [ ] Submit `Please remember that I now prefer concise responses.`, approve the
  correction, start another new conversation, and require concise adaptation
  plus a correction event.
- [ ] Revoke the signal, start another new conversation, and require no Response
  length adaptation receipt.
- [ ] Delete the signal and require it and its owned lifecycle history to be
  absent from inspection.
- [ ] Record screenshots or video segments for clarification, pending proposal,
  active preference/event, new-session adaptation receipt, correction, and
  removal.
- [ ] Inspect runtime logs and require no prompt text, choice labels, canonical
  values, OAuth tokens, or private profile values.

### Task 11: Reconcile Phase 1 status and checkpoint evidence

- [ ] Update `docs/aug-25-2026-final-checklist.md` Phase 1 status only after
  Passes 1A-1C are manually accepted.
- [ ] Record the accepted commit and evidence paths in the phase completion
  table.
- [ ] Report any provider-probabilistic limitation separately from deterministic
  application receipt success.
- [ ] Checkpoint only the explicitly accepted Phase 1 paths directly to
  `origin/main` using explicit path staging.
- [ ] Do not create or begin the Phase 2 implementation plan until the Phase 1
  checkpoint is confirmed on `origin/main` and the user authorizes Phase 2
  planning.

## Stop and revise conditions

Stop implementation and return to planning if any of the following occurs:

- deterministic selection cannot use the existing chat-turn lease and atomic
  proposal-effect boundary;
- an explicit UI selection would require trusting category/value from the
  browser instead of the persisted envelope;
- restoring active choices requires unbounded clarification history;
- accepted semantic selection, V1 memory, artifact feedback, or replay
  contracts must be removed or weakened;
- a Firestore index, collection migration, new dependency, or chat-turn schema
  migration becomes necessary;
- clarification and proposal receipts coexist in one logical turn;
- exact retry can create a second proposal;
- a user or workspace ownership mismatch can reveal clarification labels;
- production logs include memory values or OAuth credentials;
- manual Google-OIDC behavior differs from the authoritative receipts.

## Approval sequence

1. Approve Pass 1A only: deterministic backend selection and recoverable active
   clarification.
2. After Pass 1A manual acceptance, approve Pass 1B only: browser choice and
   adaptation surfaces.
3. After Pass 1B manual acceptance, approve Pass 1C only: live proof and
   evidence closure.
4. Accept Phase 1 and authorize its GitHub checkpoint.
5. Separately authorize creation of the Phase 2 plan.
