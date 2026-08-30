# Winning Core Phase 1 Remaining Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Repository `AGENTS.md` approval,
> TDD, manual-verification, and checkpoint gates remain controlling.

**Status:** Pending approval. Pass 1A is accepted for checkpoint; Passes 1B,
1C, and 1D require separate approval and acceptance.

**Goal:** Complete Phase 1 by exposing deterministic clarification choices in
the browser, proving approved memory adaptation across genuinely separate chat
sessions, and closing the governed memory lifecycle with judge-grade evidence.

**Architecture:** Treat the accepted Pass 1A FastAPI and Firestore contracts as
authoritative. The browser renders only bounded server receipts, submits the
server-issued clarification ID and choice index through the existing
idempotent chat path, and never supplies the memory category or canonical
value. Keep implementation sequential and divide the remaining work into two
small source-changing passes followed by one verification-and-evidence pass.

**Tech Stack:** Python 3.14, FastAPI, Pydantic 2, Google ADK, Gemini through
Vertex AI, Firestore, vanilla JavaScript ES modules, Node test runner, pytest,
Google OIDC.

**Specs:**

- `docs/aug-25-2026-final-checklist.md`
- `docs/superpowers/plans/2026-08-25-winning-core-phase-1-memory-continuity.md`
- `docs/superpowers/specs/2026-08-23-phase-4a-lightweight-browser-workspace-design.md`
- `docs/design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md`

**Baseline:** The accepted Pass 1A implementation checkpoint committed with
this plan. Pass 1A supplies strict public selection schemas, durable request
identity, explicit clarification-ID binding, atomic proposal creation, active
clarification recovery, safe error translation, partial-failure preservation,
and completed-turn replay.

## Remaining pass outline

| Pass | Outcome | Source changes | Acceptance boundary |
| --- | --- | --- | --- |
| 1B | A user can see, recover, and select a clarification choice in the browser, producing exactly one pending proposal. | Frontend request, state, view, wiring, style, and tests. | Browser clarification lifecycle accepted on desktop and mobile. |
| 1C | A user can approve the proposal, start a new conversation, and see an authoritative adaptation receipt explaining changed behavior. | Focused receipt rendering and continuity tests; no backend redesign. | Cross-session adaptation accepted in Google OIDC mode. |
| 1D | Correction, rejection, revocation, deletion, ownership, and failure behavior are proven and Phase 1 evidence is reconciled. | Documentation/evidence only unless a failure triggers a separately approved correction. | Phase 1 accepted and checkpointed as one truthful contest capability. |

## Global constraints

- Implement only one pass at a time; no parallel work.
- Each source-changing pass requires explicit approval before RED.
- Each pass stops at **implemented, pending manual verification**.
- Checkpoint only after the user accepts that pass.
- Firestore and application services remain the authority for memory effects.
- Browser input may contain only `clarification_id` and
  `selected_candidate_index`; it may not supply category or canonical value.
- Clarification remains session-scoped, expires after 15 minutes, and is valid
  only on the first subsequent user turn.
- Selection creates one pending V2 proposal and never activates memory.
- Clarification and proposal receipts must not coexist in one logical turn.
- Exact retry reuses the original request body and idempotency key.
- Pending memory does not affect Agent Col until explicit approval.
- Profile memory remains user-global; workspace notes remain Phase 2.
- Agent Col remains the sole user-facing responder.
- Visible truth comes from structured receipts, not model prose.
- Do not add dependencies, endpoints, Firestore collections, generalized
  workflow abstractions, or a frontend redesign.
- Do not log prompts, memory values, choice labels, OAuth tokens, or profile
  contents.

---

## Pass 1B - Browser Clarification Choice Lifecycle

### Goal and user-visible outcome

When Agent Col returns an ambiguous memory clarification, the workspace shows
two to five accessible choices. Selecting one sends the deterministic Pass 1A
request, disables duplicate actions while pending, creates one pending memory
proposal, and removes the consumed clarification. Reopening the same chat
before selection restores the still-valid choices.

### Expected file boundary

- Modify `frontend/requests.mjs`.
- Modify `frontend/state.mjs`.
- Modify `frontend/chat-view.mjs`.
- Modify `frontend/app.mjs`.
- Modify `frontend/index.html` only for one stable unframed control region.
- Modify `frontend/styles.css` only for clarification layout and states.
- Modify `tests/frontend/requests.test.mjs`.
- Modify `tests/frontend/state.test.mjs`.
- Modify `tests/frontend/chat-view.test.mjs`.
- Modify `tests/frontend/workspace-static.test.mjs`.
- Treat `schemas.py`, `main.py`, `database.py`, and
  `frontend/memory-view.mjs` as regression surfaces, not expected edits.

Stop and revise the plan if Pass 1B requires a backend contract change,
dependency, endpoint, or Firestore migration.

### Task 1: Build the immutable clarification-selection request

**Files:**

- Modify: `frontend/requests.mjs`
- Test: `tests/frontend/requests.test.mjs`

**Interfaces:**

- Produces:
  `buildMemoryClarificationSelectionChatRequest(context, choice, cryptoLike)`.
- Extends: `buildChatRequest()` three-way structured-decision exclusivity.
- Returns: the existing frozen `{key, body}` request shape.

- [ ] **Step 1: Write the RED request-builder tests**

Require a valid choice to produce:

```javascript
{
  key: "chat--selection-request-uuid",
  body: {
    project_id: "project-1",
    session_id: "session-1",
    user_id: "user-1",
    message: "Select Response length: Detailed.",
    memory_clarification_selection: {
      clarification_id: "memory-clarification--clarify-1",
      selected_candidate_index: 0,
    },
  },
}
```

Require the request and nested body to be frozen. Require malformed IDs,
boolean/fractional/out-of-range indexes, empty labels, and coexistence with
either other structured decision to throw before network access.

- [ ] **Step 2: Verify RED**

Run:

```bash
node --test tests/frontend/requests.test.mjs
```

Expected: failure because the builder and three-way exclusivity are absent.

- [ ] **Step 3: Implement the minimum builder**

Validate the receipt-owned ID and integer index, create the honest transcript
message from display labels, and delegate to `buildChatRequest()`. Count all
three structured decision fields and reject a count above one.

- [ ] **Step 4: Verify GREEN**

Run the RED command again. Require every request test to pass.

### Task 2: Track active clarification and exact retry state

**Files:**

- Modify: `frontend/state.mjs`
- Test: `tests/frontend/state.test.mjs`

**Interfaces:**

- Adds: `activeMemoryClarification` to workspace state.
- Consumes: successful `memory_clarifications` and session-detail
  `active_memory_clarification` receipts.
- Preserves: the existing `pendingTurn` and `lastFailure.request` exact-retry
  contract.

- [ ] **Step 1: Write RED state-transition tests**

Cover these independent transitions:

1. Initial state contains `activeMemoryClarification: null`.
2. A successful response with one clarification stores that receipt.
3. Beginning its selection preserves the exact frozen pending request.
4. A failed selection keeps the clarification and exact retry request.
5. A successful selection response containing one proposal clears it.
6. Session detail restores `active_memory_clarification`.
7. Session detail with no active receipt clears stale state.
8. New conversation and workspace switch clear session-scoped clarification.
9. Ordinary chat and artifact feedback do not invent or consume one.
10. Activity labels use receipt labels and never display the clarification ID.

- [ ] **Step 2: Verify RED**

Run:

```bash
node --test tests/frontend/state.test.mjs
```

Expected: failures because clarification state is absent.

- [ ] **Step 3: Implement minimal immutable transitions**

Store at most one structured receipt. Determine a selection turn by inspecting
its request body, not message text. Preserve the receipt on request failure;
clear it only after a successful selection, new conversation, workspace
switch, or authoritative session detail with no active clarification.

- [ ] **Step 4: Verify GREEN**

Run the RED command again and inspect every failure, skip, and warning.

### Task 3: Render and wire accessible clarification choices

**Files:**

- Modify: `frontend/chat-view.mjs`
- Modify: `frontend/app.mjs`
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/chat-view.test.mjs`
- Test: `tests/frontend/workspace-static.test.mjs`

**Interfaces:**

- Adds: one unframed clarification region between transcript and composer.
- Emits: `handlers.onSelectMemoryClarification(choice)` once per valid click.
- Calls: `buildMemoryClarificationSelectionChatRequest()` and the existing
  `submitRequest()` path.

- [ ] **Step 1: Write RED rendering and interaction tests**

Require two to five ordinary buttons labeled
`Category label: Value label`. Require button type, stable dimensions,
keyboard operation, visible focus, long-label wrapping, and disabled behavior
while a turn is pending or the receipt is expired. Require one click to emit
the exact receipt choice once. Require no visible internal clarification ID.

- [ ] **Step 2: Verify RED**

Run:

```bash
node --test \
  tests/frontend/chat-view.test.mjs \
  tests/frontend/workspace-static.test.mjs
```

Expected: failures because the clarification region and handler do not exist.

- [ ] **Step 3: Implement the minimum UI and wiring**

Render from `state.activeMemoryClarification` using DOM `textContent`. Wire the
choice handler through the Task 1 builder. Keep existing composer, transcript,
memory panel, retry button, and responsive layout unchanged. Do not introduce
a modal, nested card, instructional feature text, or a second approval path.

- [ ] **Step 4: Verify GREEN and focused frontend regression**

Run:

```bash
node --test \
  tests/frontend/requests.test.mjs \
  tests/frontend/state.test.mjs \
  tests/frontend/chat-view.test.mjs \
  tests/frontend/memory-view.test.mjs \
  tests/frontend/workspace-static.test.mjs \
  tests/frontend/workspace-view.test.mjs
```

Expected: all selected frontend tests pass.

### Pass 1B automated verification

Run the focused frontend command above, followed by:

```bash
venv/bin/pytest -q \
  tests/test_schemas.py \
  tests/test_memory_clarifications.py \
  tests/test_memory_clarification_database.py \
  tests/test_memory_proposal_service.py \
  tests/test_chat_turns.py \
  tests/test_chat_turn_database.py \
  tests/test_agent_col_turn_service.py \
  tests/test_supervisor_runtime.py \
  tests/test_main.py
```

Also run `git diff --check`. The broader backend boundary is required because
the UI directly consumes shared selection, session-detail, retry, and receipt
contracts.

### Pass 1B manual acceptance targets

Use Google OIDC at `/workspace` on desktop and a narrow mobile viewport.

1. Submit: `Please remember two things: I prefer detailed answers, and I prefer step-by-step explanations.`
2. Confirm exactly two visible choices and no pending proposal.
3. Reopen the same chat before selection and confirm the choices return.
4. Choose `Response length: detailed` and confirm controls disable while
   pending.
5. Confirm exactly one pending Response length proposal and no remaining
   clarification region.
6. Trigger an ordinary validation or transport failure and confirm the same
   choice remains available with exact retry.
7. Confirm keyboard focus, label wrapping, and no overlap on desktop/mobile.
8. Confirm list-valued memory still creates one proposal directly.

Stop at **implemented, pending manual verification**. Pass 1C requires separate
approval after Pass 1B acceptance and checkpointing.

---

## Pass 1C - Cross-Session Adaptation Receipt and Proof

### Goal and user-visible outcome

After approving the clarified proposal and starting a genuinely new
conversation, Agent Col adapts without the user restating the preference. The
originating response displays an authoritative adaptation receipt showing what
approved category influenced the model.

### Expected file boundary

- Modify `frontend/chat-view.mjs`.
- Modify `tests/frontend/chat-view.test.mjs`.
- Modify `tests/frontend/state.test.mjs` only for continuity regressions.
- Modify `frontend/styles.css` only if receipt wrapping requires it.
- Treat all Python source, Firestore contracts, memory panel controls, and
  navigation as regression surfaces, not expected edits.

Stop and revise if adaptation proof requires changing backend receipt or
profile-memory semantics.

### Task 4: Render authoritative adaptation receipts

**Files:**

- Modify: `frontend/chat-view.mjs`
- Test: `tests/frontend/chat-view.test.mjs`

**Interfaces:**

- Extends: `renderReceipts(container, response)`.
- Consumes: structured V1/V2 `response.adaptations`.
- Displays: category and value labels without exposing signal/event IDs.

- [ ] **Step 1: Write RED receipt tests**

Require scalar, list-valued, and domain-experience adaptations to produce
bounded human-readable labels. Require malformed receipts to be ignored
safely. Require model prose claiming adaptation without a receipt to produce
no adaptation label.

- [ ] **Step 2: Verify RED**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs
```

Expected: failure because chat receipts currently omit adaptations.

- [ ] **Step 3: Implement minimal structured rendering**

Use existing label/value helpers where available. Render one compact receipt
per structured adaptation, bound the displayed count to the API contract, and
use `textContent`. Do not expose `signal_id` or `source_event_id` in primary UI.

- [ ] **Step 4: Verify GREEN**

Run the RED command again and require all chat-view tests to pass.

### Task 5: Protect new-conversation continuity behavior

**Files:**

- Modify: `tests/frontend/state.test.mjs`
- Modify: `frontend/state.mjs` only if the RED test exposes a real defect.

**Interfaces:**

- Preserves: user/workspace identity and approved memory inspection state.
- Replaces: session ID and clears transcript, pending turn, failure, and
  session-scoped clarification.

- [ ] **Step 1: Add continuity regression coverage**

Require `startNewConversation()` to create a new session ID while retaining the
same user/workspace and loaded global memory profile. Require session-scoped
clarification to clear. Require the next successful response's adaptation
receipt to remain attached to that new turn.

- [ ] **Step 2: Run the test**

Run:

```bash
node --test tests/frontend/state.test.mjs
```

If the new test passes immediately, retain it as regression evidence and do
not modify production state. If it fails for the intended behavior, implement
only the minimal state correction through RED-GREEN-REFACTOR.

### Pass 1C automated verification

Run:

```bash
node --test tests/frontend/*.test.mjs
```

Then run the complete Phase 1 backend boundary:

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

Compile changed modules and run `git diff --check`.

### Pass 1C manual acceptance targets

1. Approve the Pass 1B pending Response length proposal in the Memory panel.
2. Confirm it becomes active only after approval.
3. Click `New conversation` and confirm the previous transcript and
   clarification controls are absent.
4. Submit: `Compare two practical ways to organize a week of study.`
5. Confirm the response is observably detailed without restating the
   preference.
6. Confirm the turn displays an authoritative Response length adaptation
   receipt.
7. Confirm no adaptation receipt appears after a controlled response without
   an active matching signal.
8. Repeat at desktop and mobile widths and verify receipt wrapping and focus.

Stop at **implemented, pending manual verification**. Pass 1D requires separate
approval after Pass 1C acceptance and checkpointing.

---

## Pass 1D - Governed Lifecycle and Evidence Closure

### Goal and user-visible outcome

Prove the complete memory lifecycle and produce truthful repository/demo
evidence: propose, clarify, select, approve, adapt in another session, correct,
reject, revoke, and delete without hidden or duplicate persistence.

### Expected file boundary

This pass changes no production source by default.

- Modify `docs/aug-25-2026-final-checklist.md` after evidence succeeds.
- Modify the narrow canonical status/evidence documentation identified by the
  repository review.
- Add bounded screenshots or evidence records only in the repository's
  established evidence location.
- Do not change source to make a failed demonstration appear successful.

Any failure triggers systematic debugging, a focused correction plan, explicit
approval, TDD, and a new manual gate before this pass resumes.

### Task 6: Prove the complete lifecycle in Google OIDC mode

- [ ] Start from a fresh conversation and a category with controlled state.
- [ ] Prove clarification, deterministic selection, pending proposal, and
  explicit approval.
- [ ] Prove adaptation in a genuinely different chat session.
- [ ] Propose and approve a correction to the same category.
- [ ] Prove the corrected value adapts a later fresh session.
- [ ] Reject a separate proposal and prove it never becomes active.
- [ ] Revoke the corrected signal and prove it is no longer provided to the
  model.
- [ ] Delete the signal and prove its owned lifecycle data disappears from
  bounded inspection.
- [ ] Verify mixed V1/V2 inspection and controls still work.
- [ ] Verify workspace and user ownership remain uniform and non-disclosing.
- [ ] Inspect logs and require no prompts, values, labels, tokens, or private
  profile contents.

### Task 7: Capture controlled failure and retry evidence

- [ ] Induce one bounded transport or responder failure after a completed
  clarification selection.
- [ ] Confirm the partial response remains truthful about the pending proposal.
- [ ] Retry with the exact key/body and confirm no duplicate proposal or event.
- [ ] Capture the user-visible result and bounded, content-safe operational log.
- [ ] Remove any temporary failure mechanism before final verification.

### Task 8: Reconcile Phase 1 documentation and evidence

- [ ] Update the final checklist with accepted Pass 1A-1D checkpoints.
- [ ] Reconcile canonical memory status against executable behavior.
- [ ] Record evidence paths for clarification, proposal approval, adaptation,
  correction, rejection, revocation, deletion, and controlled retry.
- [ ] Preserve the distinction between profile memory and Phase 2 workspace
  notes.
- [ ] Record provider-probabilistic behavior separately from deterministic
  application receipts.
- [ ] Run `git diff --check` and scan documentation for secrets and stale
  claims.
- [ ] Checkpoint only accepted documentation/evidence paths to `origin/main`.

### Pass 1D acceptance targets

Phase 1 is accepted only when all of these are true:

1. Clarification selection is deterministic and inspectable in the browser.
2. Approved profile memory demonstrably changes a later session.
3. The UI shows an authoritative adaptation receipt.
4. Correction, rejection, revocation, and deletion behave truthfully.
5. Retry and controlled failure produce no duplicate effect.
6. Google OIDC ownership remains non-disclosing.
7. Runtime logs contain no private memory or authentication content.
8. Repository status and evidence match the demonstrated build.

## Phase 1 completion boundary

After Pass 1D acceptance:

- Mark Phase 1 complete in `docs/aug-25-2026-final-checklist.md`.
- Confirm every accepted checkpoint exists on `origin/main`.
- Freeze the Phase 1 public contracts before planning Phase 2.
- Do not create or implement the Phase 2 workspace-note plan until the user
  separately authorizes planning.
