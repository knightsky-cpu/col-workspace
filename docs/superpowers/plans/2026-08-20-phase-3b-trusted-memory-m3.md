# Phase 3B Trusted Memory M3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline, task by task.
> Do not delegate to subagents. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Turn an explicitly approved pending memory proposal into one typed,
active collaboration signal through an atomic Firestore transaction, while
supporting idempotent retries, correction and supersession, monotonic profile
revisions, and read-only typed profile loading.

**Architecture:** `MemoryEngine` remains the Firestore boundary. It receives a
validated category, proposal ID, confirmation provenance, and caller-captured
observation time from the future `TrustedMemoryService`. It reads the proposal
slot and governed root projection before any write, creates deterministic
immutable event documents, replaces exactly one category in the active
projection, increments `memory_revision` once, and marks the proposal approved
in the same transaction. A correction additionally validates the proposal's
`expected_signal_id`, preserves the prior signal's original source provenance,
and creates its deterministic superseded event. The existing arbitrary profile
compatibility API remains available but is not used or migrated by M3.

**Tech Stack:** Python 3.14.7, Pydantic 2.13.4,
google-cloud-firestore 2.28.1, pytest 9.1.1, pytest-asyncio 1.4.0

**Spec:**
`docs/superpowers/specs/2026-08-20-phase-3b-trusted-memory-design.md`

## Global constraints

- Execute inline and follow strict RED-GREEN-REFACTOR one observable behavior
  at a time.
- Keep `memory_schema_version` and `policy_version` fixed at `"1.0"`.
- Add no natural-language interpretation, consent inference, clock reads, UUID
  generation, logging, network calls, or mutable application-state effects
  inside Firestore transaction callbacks.
- Capture `observed_at`, category, proposal ID, and confirmation provenance
  before entering the transaction. Firestore may rerun the callback.
- Use only these existing bounded paths:
  `users/{user_id}`, `users/{user_id}/memory_proposals/{category}`, and
  `users/{user_id}/memory_events/{event_id}`.
- Use deterministic event IDs:
  `{signal_id}--approved`, `{signal_id}--corrected`, and
  `{signal_id}--superseded`. M3 does not create revoked events.
- The approved signal ID equals the proposal ID.
- Validate every derived event ID against the existing 128-character
  `IdentifierStr` bound before constructing a Firestore reference. A proposal
  ID that cannot safely accept the longest `--superseded` lifecycle suffix is
  invalid for this operation and must fail before Firestore access. M5 will
  later generate proposal IDs within this derived bound.
- Read every document needed to decide the mutation before enqueuing any
  transaction write.
- Never overwrite an existing event. An identical existing event establishes
  idempotent completion; a differing event is a conflict or invalid stored
  state.
- Increment the root `memory_revision` exactly once per newly committed
  approval or correction. An idempotent retry must not increment it.
- Use `firestore.SERVER_TIMESTAMP` for persisted lifecycle `created_at`, active
  signal `approved_at`, proposal `resolved_at`, and root `memory_updated_at`.
  Caller-captured `observed_at` is used only to construct the immediate typed
  return value and make expiry decisions deterministic.
- Preserve all unrelated root user fields with `merge=True`. Write the complete
  validated governed fields (`memory_schema_version`, `memory_revision`,
  `identity_context`, and `active_preferences`) so each bounded map remains
  internally consistent.
- A missing root document or a legacy root with no governed fields loads as an
  empty version `1.0`, revision `0` profile without causing a write.
- Ignore arbitrary legacy root fields during typed profile loading. Never
  promote, delete, return, or inject them through the governed profile.
- Reject malformed governed stored data as `MemoryEngineError`; do not silently
  repair it.
- Initial approval requires no active signal and
  `proposal.expected_signal_id is None`.
- Correction requires one active signal for the category and an exact
  `proposal.expected_signal_id` match. A missing or stale expectation conflicts
  without writes.
- A superseded event must retain the old signal's original source session,
  source message, source type, value, and policy version by reading the old
  signal's `source_event_id`. Its confirmation fields record the current
  approval action and `related_signal_id` points to the new signal.
- Preserve current `ChatRequest`, `ChatResponse`, `/api/chat`,
  `/api/synthesize`, supervisor, synthesis, message persistence, pending
  proposal, and legacy profile behavior.
- Add no HTTP route, response field, ADK tool, Gemini call, dependency, index,
  environment variable, authentication behavior, frontend behavior, or
  deployment change.
- M3 does not implement proposal rejection, revocation, hard deletion, event
  inspection, chat decisions, context rendering integration, or action
  receipts.
- Pytest remains offline. Live Firestore access is limited to the explicit
  manual smoke runner.
- Logs and public infrastructure errors must exclude user IDs, proposal IDs,
  signal IDs, session IDs, message IDs, categories, and memory values. Wrapped
  failures must preserve the original exception as `__cause__`.
- Do not commit or push until the user completes manual verification and
  explicitly authorizes the checkpoint.

## File structure

- Modify `database.py`: add typed profile loading, approval-state exceptions,
  the immutable approval result, event/profile conversion helpers, and one
  transactional `approve_memory_proposal` method that also handles correction.
- Create `tests/test_memory_approval_database.py`: focused offline profile,
  approval, idempotency, expiry, conflict, correction, provenance,
  read-before-write, and safe-error tests.
- Create `smoke_test_memory_approval.py`: live Firestore runner that performs
  an initial approval, identical retry, and correction for a unique
  pseudonymous development user.
- Create `tests/test_smoke_test_memory_approval.py`: offline regression for the
  smoke runner using a fake engine and no network access.

## Public interface

`database.py` will expose:

```python
from dataclasses import dataclass
from datetime import datetime

from memory_policy import (
    ConfirmationChannel,
    MemoryCategory,
)
from schemas import CollaborationProfile, MemoryEvent


class MemoryProposalNotFoundError(RuntimeError):
    """Raised when a requested proposal slot does not exist."""


class MemoryProposalExpiredError(RuntimeError):
    """Raised when a requested pending proposal has expired."""


@dataclass(frozen=True, slots=True)
class MemoryApprovalResult:
    profile: CollaborationProfile
    event: MemoryEvent
    superseded_event: MemoryEvent | None = None


class MemoryEngine:
    async def get_collaboration_profile(
        self,
        user_id: str,
    ) -> CollaborationProfile:
        """Load only the governed active-memory projection."""

    async def approve_memory_proposal(
        self,
        user_id: str,
        category: MemoryCategory,
        proposal_id: str,
        *,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
        observed_at: datetime,
    ) -> MemoryApprovalResult:
        """Atomically approve or correct one governed memory signal."""
```

`category` is a typed, application-validated path selector. The future M5
`TrustedMemoryService` will derive it from the bounded proposal identifier and
will translate persistence-state exceptions into its domain errors. M3 does not
add HTTP mappings early.

`MemoryProposalNotFoundError` represents an absent category slot.
`MemoryProposalExpiredError` represents a pending proposal whose deadline is
not later than `observed_at`. The existing `MemoryProposalConflictError`
represents a replaced slot, rejected or inconsistently resolved proposal, stale
correction, mismatched deterministic event, or conflicting retry. These
expected state distinctions propagate without infrastructure logging.

`MemoryApprovalResult` is an internal persistence result, not a public HTTP
schema or user-visible action receipt. M5 will convert it into validated service
results.

## Stored-document contract

The root projection is merged at `users/{user_id}`:

```python
{
    "memory_schema_version": "1.0",
    "memory_revision": new_revision,
    "identity_context": identity_context_document,
    "active_preferences": active_preferences_document,
    "memory_updated_at": firestore.SERVER_TIMESTAMP,
}
```

The active signal stored in the applicable category map is:

```python
{
    "signal_id": proposal.proposal_id,
    "category": proposal.category,
    "value": proposal.proposed_value,
    "policy_version": proposal.policy_version,
    "source_event_id": new_event.event_id,
    "approved_at": firestore.SERVER_TIMESTAMP,
}
```

Event documents omit `event_id` because the deterministic document path is its
canonical storage. `_memory_event_from_document(event_id, document)` injects
the path ID before Pydantic validation. Event documents otherwise contain
exactly the `MemoryEvent` fields and substitute
`created_at=firestore.SERVER_TIMESTAMP`.

The proposal slot is merged only with:

```python
{
    "status": "approved",
    "resolved_at": firestore.SERVER_TIMESTAMP,
}
```

All original proposal and provenance fields remain unchanged.

---

### Task 1: Read-only typed collaboration profile

**Files:**

- Modify: `database.py`
- Create: `tests/test_memory_approval_database.py`

- [ ] **Step 1: Write the absent-profile RED test**

Add
`test_get_collaboration_profile_returns_empty_versioned_profile_when_absent`.
Use an injected fake `AsyncClient`, return a non-existent user snapshot, and
assert the result equals:

```python
CollaborationProfile(
    memory_schema_version="1.0",
    memory_revision=0,
    identity_context={},
    active_preferences={},
)
```

Assert no `set`, `update`, batch, or transaction operation occurs.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_memory_approval_database.py::test_get_collaboration_profile_returns_empty_versioned_profile_when_absent \
  -v
```

Expected: collection fails because `MemoryEngine` has no
`get_collaboration_profile` method.

- [ ] **Step 3: Implement the minimal typed read**

Add `get_collaboration_profile`. Validate `user_id` before Firestore access,
read `users/{user_id}`, and pass the snapshot through one helper that selects
only the four governed profile fields. When the document is absent, or when all
four governed fields are absent, return `CollaborationProfile()`.

Do not call `get_user_profile()` because that compatibility method returns
arbitrary root fields and would weaken the governed boundary.

- [ ] **Step 4: Verify GREEN**

Run the named test from Step 2. Expected: one test passes.

- [ ] **Step 5: Add legacy exclusion and typed-profile tests**

Add one test for a root containing only legacy arbitrary fields and one test for
a valid root containing both governed and unrelated fields. Assert that:

- the legacy-only root produces an empty versioned profile;
- valid governed signals are returned as `ActiveMemorySignal` instances;
- unrelated fields are absent from the returned model;
- the read performs no write.

Run all Task 1 tests and expect them to pass.

- [ ] **Step 6: Add malformed-data and safe-error tests**

Add tests proving that an unsupported schema version, mismatched projection
key, malformed signal, and Firestore `GoogleAPIError` become
`MemoryEngineError`, preserve their cause, and log no private identifiers or
values. Add invalid `user_id` cases and assert rejection occurs before
`client.collection()`.

Run all Task 1 tests and expect them to pass.

- [ ] **Step 7: Refactor while green**

Keep governed field selection and Pydantic validation in one private helper.
Rerun all Task 1 tests.

---

### Task 2: Atomic first approval and revision-one projection

**Files:**

- Modify: `database.py`
- Modify: `tests/test_memory_approval_database.py`

- [ ] **Step 1: Write the first-approval RED test**

Add `test_approve_memory_proposal_atomically_creates_event_and_projection`.
Arrange:

- one valid, unexpired pending `response_length=concise` proposal;
- an absent root profile;
- absent deterministic approved and corrected event snapshots;
- `confirmation_channel="chat_decision"` with valid confirmation session and
  message IDs;
- a fixed timezone-aware `observed_at`.

Assert the result contains revision `1`, an `approved` event named
`response_length--proposal-1--approved`, no superseded event, and an active
`response_length` signal whose `source_event_id` is that approved event.

Assert the transaction enqueues exactly:

1. the immutable approved event create;
2. the complete governed root projection merge;
3. the proposal status/resolution merge.

Assert the stored timestamps are server sentinels and the immediate typed result
uses the fixed `observed_at`.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_memory_approval_database.py::test_approve_memory_proposal_atomically_creates_event_and_projection \
  -v
```

Expected: collection fails because the approval interface and result type do
not exist.

- [ ] **Step 3: Add the minimal immutable result and transaction**

Add `MemoryApprovalResult`, the two new state exceptions, input validation, and
`approve_memory_proposal`.

Construct proposal, root, approved-event, and corrected-event references before
the callback. Inside the callback:

1. read the proposal slot;
2. read the root profile;
3. read both deterministic new-event paths;
4. reject missing, expired, resolved, or mismatched state as planned in Task 3;
5. build revision `1`, the approved event, and active projection;
6. enqueue all writes only after the last read;
7. return the immutable typed result.

Use `firestore.async_transactional` exactly as the M2 transaction does.

- [ ] **Step 4: Verify GREEN**

Run the named test from Step 2. Expected: one test passes.

- [ ] **Step 5: Prove read-before-write order and preference/identity routing**

Add an operation-order test asserting all proposal, root, approved-event, and
corrected-event reads occur before the first write. Add one parameterized test
covering:

- preference category `response_length` writes only `active_preferences`;
- identity category `preferred_name` writes only `identity_context`.

Both root maps must preserve already validated signals in other categories.

- [ ] **Step 6: Refactor serialization while green**

Extract private helpers for active-signal construction, root serialization,
event serialization, and category-map replacement. Helpers must remain pure and
must not read clocks or Firestore. Rerun all Task 2 tests.

---

### Task 3: Approval state validation and idempotent retry

**Files:**

- Modify: `database.py`
- Modify: `tests/test_memory_approval_database.py`

- [ ] **Step 1: Write the identical-retry RED test**

Add `test_approve_memory_proposal_returns_existing_approval_without_writes`.
Arrange an approved proposal, revision-one root projection, matching approved
event, and absent corrected event. Assert the returned profile and event are
loaded from stored state, `superseded_event is None`, and no transaction write
is enqueued.

- [ ] **Step 2: Verify RED**

Run the named test. Expected: it fails because the minimal Task 2 implementation
rejects resolved proposals instead of recognizing completed identical state.

- [ ] **Step 3: Implement stable event and projection equality**

For an existing approved or corrected event:

- inject and validate its deterministic path ID;
- compare every semantic field except the server-resolved `created_at`;
- require the proposal to be approved;
- require the active projection to point to the proposal signal and source
  event;
- require profile revision to equal the event revision;
- return stored typed state without writes.

Do not overwrite, merge, or recreate an existing event.

- [ ] **Step 4: Verify GREEN**

Run the named retry test and the first-approval test. Expected: both pass.

- [ ] **Step 5: Add state-failure RED-GREEN cycles**

Add and individually verify tests for:

- absent proposal slot -> `MemoryProposalNotFoundError`;
- slot occupied by another proposal ID -> `MemoryProposalConflictError`;
- `observed_at >= expires_at` -> `MemoryProposalExpiredError`;
- rejected proposal -> `MemoryProposalConflictError`;
- approved proposal without its event -> `MemoryEngineError`;
- both approved and corrected events present -> `MemoryEngineError`;
- existing deterministic event with differing fields ->
  `MemoryProposalConflictError`;
- initial approval proposal with non-`None` `expected_signal_id` ->
  `MemoryProposalConflictError`;
- category, proposal ID, confirmation-channel, confirmation-ID, or timestamp
  validation failure -> `ValueError` before Firestore access.
- a proposal whose deterministic lifecycle suffix would exceed the
  128-character identifier bound -> `ValueError` before Firestore access;
- a malformed stored active signal whose deterministic lifecycle suffix would
  exceed the bound -> `MemoryEngineError` before event reads or writes.

Each expected state failure must enqueue no writes. Infrastructure and stored
integrity failures must preserve causes and use content-free logs; expected
not-found, expired, and conflict states must remain unlogged.

- [ ] **Step 6: Refactor while green**

Keep idempotent-result detection separate from new-mutation construction so a
retry cannot accidentally enter correction logic after the new signal is
already active. Rerun all Task 3 tests.

---

### Task 4: Atomic correction and supersession provenance

**Files:**

- Modify: `database.py`
- Modify: `tests/test_memory_approval_database.py`

- [ ] **Step 1: Write the correction RED test**

Add `test_approve_memory_proposal_atomically_corrects_and_supersedes`.
Arrange:

- a revision-one profile with active `response_length=concise` signal;
- that active signal's valid source approved event;
- a pending `response_length=detailed` proposal whose
  `expected_signal_id` equals the active signal ID;
- absent deterministic new corrected event and prior superseded event.

Assert one transaction returns revision `2` and enqueues:

1. `{new_signal_id}--corrected` with the new proposal's source provenance and
   `related_signal_id` set to the old signal ID;
2. `{old_signal_id}--superseded` with the old signal's original source
   provenance, the current confirmation provenance, and `related_signal_id`
   set to the new signal ID;
3. the root projection replacement with only the new active category value;
4. the new proposal's approved status and server resolution timestamp.

Both new events must carry revision `2`. All source-event and superseded-event
reads must precede all four writes.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_memory_approval_database.py::test_approve_memory_proposal_atomically_corrects_and_supersedes \
  -v
```

Expected: the test fails because Task 3 rejects or lacks correction behavior.

- [ ] **Step 3: Implement the minimal correction path**

After ruling out an idempotent completed retry, inspect the current active
signal for the category. When present:

1. require exact `expected_signal_id` equality;
2. read `memory_events/{active_signal.source_event_id}`;
3. read `memory_events/{active_signal.signal_id}--superseded`;
4. validate the source event matches the active signal's category, value,
   signal ID, policy version, and event ID;
5. require the superseded path to be absent for a new correction;
6. build the corrected and superseded events and revision-two projection;
7. enqueue writes only after both reads complete.

- [ ] **Step 4: Verify GREEN**

Run the named correction test, first-approval test, and identical-retry test.
Expected: all pass.

- [ ] **Step 5: Add stale and malformed correction cycles**

Add and individually verify tests for:

- missing `expected_signal_id` while a category is active -> conflict;
- mismatched expected active signal -> conflict;
- missing prior source event -> `MemoryEngineError`;
- prior source event whose identity or value differs from the active projection
  -> `MemoryEngineError`;
- pre-existing differing superseded event -> conflict;
- correction preserves every unrelated active preference and identity signal;
- correction does not expose the prior value in the new active projection.

Every failure must enqueue no writes.

- [ ] **Step 6: Add corrected-retry idempotency**

Arrange the post-correction profile, approved proposal, matching corrected event,
and matching prior superseded event. Assert an identical retry returns all three
stored typed objects with no writes and no revision increment. A missing or
differing superseded event must fail without repair.

- [ ] **Step 7: Refactor while green**

Extract pure constructors for approved, corrected, and superseded events. Keep
the transaction callback as orchestration over validated reads and prepared
writes. Rerun all Task 4 tests.

---

### Task 5: Offline smoke contract, focused regression, and live acceptance

**Files:**

- Create: `smoke_test_memory_approval.py`
- Create: `tests/test_smoke_test_memory_approval.py`
- Modify only if a discovered defect requires it: `database.py`

- [ ] **Step 1: Write the smoke-runner RED test**

Add an offline test that injects a fake `MemoryEngine` into the runner and
asserts this exact sequence:

1. create initial pending proposal;
2. approve it;
3. repeat the identical approval and observe no revision change;
4. create a correction proposal with `expected_signal_id` equal to the first
   active signal;
5. approve the correction;
6. load the typed final profile;
7. close the engine once.

Assert the runner reports revision `1` for the initial approval and retry,
revision `2` for correction, the corrected and superseded event IDs, the final
active value, and the generated pseudonymous development user ID. The test must
perform no network access.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_smoke_test_memory_approval.py \
  -v
```

Expected: collection fails because `smoke_test_memory_approval.py` does not
exist.

- [ ] **Step 3: Implement the minimal live runner**

Create a directly runnable async script. Generate all user, proposal, source,
confirmation, and event-related identifiers before database operations. Use
only pseudonymous development values. The script must validate and print
content-free structural evidence; it must not print the preferred name, memory
value, source message contents, credentials, or raw Firestore documents.

- [ ] **Step 4: Verify GREEN**

Run the smoke-runner test from Step 2. Expected: all tests pass offline.

- [ ] **Step 5: Run focused offline verification**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_memory_approval_database.py \
  tests/test_memory_database.py \
  tests/test_memory_schemas.py \
  tests/test_database.py \
  tests/test_smoke_test_memory_approval.py \
  tests/test_smoke_test_memory_persistence.py \
  -v
```

Expected: all selected tests pass with no network access. The full suite is not
required because M3 adds unused persistence interfaces and does not alter any
existing HTTP, supervisor, synthesis, or model-consumer contract.

Run static checks:

```bash
venv/bin/python -m compileall \
  database.py \
  smoke_test_memory_approval.py \
  tests/test_memory_approval_database.py \
  tests/test_smoke_test_memory_approval.py
git diff --check
```

Expected: both commands exit `0`.

- [ ] **Step 6: Stop at the manual gate**

Report the pass as **implemented, pending manual verification**. Do not commit,
push, or begin M4.

## Manual runtime verification targets

### 1. Live approval, retry, and correction

From the project root with the virtual environment active and ADC configured:

```bash
python3 smoke_test_memory_approval.py
```

Expected:

- the runner exits `0`;
- initial approval reports revision `1` and an `--approved` event;
- identical retry reports revision `1` again;
- correction reports revision `2`, one `--corrected` event, and one
  `--superseded` event;
- final typed profile reports exactly one active tested category and the new
  signal ID;
- no private value, chat text, credential, or raw Firestore document is
  printed.

### 2. Firestore structure

Open:

<https://console.cloud.google.com/firestore/databases/-default-/data/panel/users?project=project-e1e2a890-4566-48a8-a32>

Navigate to the pseudonymous user ID printed by the runner. Verify:

- root `memory_schema_version` is `1.0`;
- root `memory_revision` is `2`;
- exactly the corrected signal is active in the tested category;
- the category proposal slot is `approved` and has `resolved_at`;
- the first signal has `--approved` and `--superseded` event documents;
- the second signal has one `--corrected` event document;
- both correction-related events carry revision `2`;
- server timestamps are populated;
- no duplicate event document exists after the retry;
- unrelated legacy root fields, if any, remain unchanged.

### 3. Application startup regression

In terminal 1:

```bash
uvicorn main:app --reload
```

In terminal 2:

```bash
curl --fail-with-body --silent --show-error \
  http://127.0.0.1:8000/
```

Expected: HTTP `200` with `{"status":"online"}`. M3 intentionally has no new
HTTP memory route. A live `/api/chat` provider call is not an M3 acceptance gate
because the current free-tier Gemini quota can independently return `429`; the
offline regression suite continues to verify the unchanged chat boundary.

## Scope notes and exclusions

- M3 proves the governed memory producer at the persistence layer, but it does
  not yet let a client approve memory through chat or inspect it through HTTP.
- M3 uses explicit confirmation provenance supplied by its caller; M5 owns the
  service-level authorization command and M6 connects structured chat decisions.
- Rejection is intentionally deferred with the other lifecycle service commands
  rather than partially exposed from `MemoryEngine` in this pass.
- Revocation and hard deletion remain M4.
- The current Gemini free-tier `429 RESOURCE_EXHAUSTED` condition is external to
  this offline/Firestore pass and is not hidden or treated as an M3 code defect.
- No existing arbitrary profile field is migrated into trusted memory.

## Stop and revise conditions

Stop implementation and return for a revised approval if evidence shows that:

- the Firestore async transaction API cannot support the planned read-before-
  write sequence without a different persistence shape;
- correction provenance cannot be reconstructed from the active signal's
  stored `source_event_id`;
- the approved design requires a new dependency, Firestore index, schema
  migration, HTTP contract, ADK change, or model call;
- a transaction would need an unbounded query or subcollection scan;
- live Firestore behavior differs from the offline SDK contract in a way that
  changes atomicity, idempotency, or event immutability;
- implementation requires modifying existing chat, synthesis, supervisor, or
  legacy profile behavior;
- unrelated user-owned changes overlap the approved files.

## Proposed follow-up after manual acceptance

After the user confirms the M3 live smoke and Firestore structure, checkpoint
only the accepted M3 files. Then propose **M4 — Revocation and hard deletion**
as a separate bounded pass with new RED tests, transactional removal, retained
revocation provenance, and exact idempotent deletion semantics.
