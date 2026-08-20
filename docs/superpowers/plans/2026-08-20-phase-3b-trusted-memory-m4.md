# Phase 3B Trusted Memory M4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan inline, task by task. Do not delegate this pass to subagents.

**Goal:** Add bounded, transactional revocation and hard deletion for governed memory signals while preserving retry safety, typed profile state, and content-free error logging.

**Architecture:** `MemoryEngine` remains the Firestore persistence boundary. Revocation removes one active projection and creates one immutable deterministic event; hard deletion reads and removes only the target proposal slot and four deterministic event paths. Both operations use public async Firestore transactions, validate all caller input before Firestore access, perform every transaction read before any write, and return typed state for the later M5 service/API layer.

**Tech Stack:** Python 3.14, Pydantic v2 domain models, `google-cloud-firestore==2.28.1` async transactions, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-08-20-phase-3b-trusted-memory-design.md`

## Global Constraints

- M4 modifies persistence and offline/live smoke verification only; it does not add FastAPI routes, service commands, chat decisions, model context, ADK tools, frontend behavior, authentication, or deployment changes.
- Firestore remains the source of truth for active governed memory and lifecycle events.
- Revocation means “stop using this memory signal but retain its approved history.”
- Hard deletion removes all value-bearing memory artifacts and source provenance owned by the target signal from the active projection, matching category proposal, and deterministic target-event paths.
- Hard deletion does not delete source or confirmation chat messages; collaboration-history retention is a separate domain.
- A successor event may retain the deleted target's opaque signal ID in `related_signal_id`. M4 does not scan or mutate unrelated successor events because that would violate the bounded fixed-path contract and immutable-event boundary.
- Revocation is idempotent only when the stored deterministic revoked event proves the same action completed; unknown or inactive signals otherwise raise a typed not-found error.
- Hard deletion is idempotent: a retry after all target-owned artifacts are absent performs no write and returns the current profile.
- Any removal, including deletion of inactive history, increments `memory_revision` exactly once per successful transaction.
- Transaction callbacks perform no logging, networking, model calls, random-ID generation, wall-clock reads, or mutable application-state access.
- Every transaction read occurs before the first `set` or `delete` operation.
- Logs exclude user, session, message, proposal, signal, and event identifiers and exclude all memory values and document contents.
- No dependency changes are permitted.
- Do not commit or push M4 until focused verification is green and the user manually accepts the live pass.

---

## Public Persistence Contract

Add these persistence-only types to `database.py`:

```python
class MemorySignalNotFoundError(RuntimeError):
    """Raised when a governed memory signal cannot be revoked."""


class MemorySignalConflictError(RuntimeError):
    """Raised when stored signal state conflicts with a memory mutation."""


@dataclass(frozen=True, slots=True)
class MemoryRevocationResult:
    """Return governed state created by a memory revocation."""

    profile: CollaborationProfile
    event: MemoryEvent


@dataclass(frozen=True, slots=True)
class MemoryDeletionResult:
    """Return governed state after bounded hard deletion."""

    profile: CollaborationProfile
    artifacts_deleted: bool
```

Add these public `MemoryEngine` methods:

```python
async def revoke_memory_signal(
    self,
    user_id: str,
    category: MemoryCategory,
    signal_id: str,
    *,
    confirmation_channel: ConfirmationChannel,
    confirmation_session_id: str | None,
    confirmation_message_id: str | None,
    observed_at: datetime,
) -> MemoryRevocationResult:
    ...


async def delete_memory_signal(
    self,
    user_id: str,
    category: MemoryCategory,
    signal_id: str,
) -> MemoryDeletionResult:
    ...
```

`category` is explicit because it deterministically selects the active-profile map and category proposal slot. Both methods require `signal_id` to use the exact `{category}--{suffix}` prefix and require every derived event ID to remain within the existing 128-character identifier bound.

---

### Task 1: Transactional memory revocation

**Files:**
- Modify: `database.py`
- Create: `tests/test_memory_lifecycle_database.py`

**Interfaces:**
- Consumes: `MemoryCategory`, `ConfirmationChannel`, `ActiveMemorySignal`, `CollaborationProfile`, `MemoryEvent`, `_memory_event_from_document()`, `_memory_event_document()`, `_collaboration_profile_document()`, and `_raise_firestore_error()`.
- Produces: `MemorySignalNotFoundError`, `MemorySignalConflictError`, `MemoryRevocationResult`, and `MemoryEngine.revoke_memory_signal()`.

- [ ] **Step 1: Write the first failing revocation test**

  Add `test_revoke_memory_signal_atomically_revokes_active_signal`. Its offline Firestore fake must expose one active `response_length` signal, its approved source event, and an absent `{signal_id}--revoked` event. Assert:

  - the returned profile revision changes from 1 to 2;
  - `response_length` is absent from `active_preferences`;
  - the returned event is `revoked` and retains the original signal value, policy version, and source session/message references;
  - the event records the current confirmation channel/session/message and revision 2;
  - the transaction writes the deterministic revoked event and merged root profile atomically;
  - persisted event and profile timestamps use `firestore.SERVER_TIMESTAMP`;
  - no proposal or source event is mutated.

- [ ] **Step 2: Verify RED**

  Run:

  ```bash
  pytest -q tests/test_memory_lifecycle_database.py::test_revoke_memory_signal_atomically_revokes_active_signal
  ```

  Expected: collection fails because `MemoryRevocationResult` and/or `MemoryEngine.revoke_memory_signal` do not exist. The failure must not be a fake setup or import typo.

- [ ] **Step 3: Implement the minimum successful revocation path**

  Add the two typed persistence errors, the `MemoryRevocationResult` dataclass, input validation shared with deletion, and `revoke_memory_signal()`.

  The transaction must:

  1. read the root user document and deterministic revoked-event document;
  2. validate the root as `CollaborationProfile` or use the empty default;
  3. find the signal only in the map selected by `category`;
  4. when active, read and validate the signal's immutable approved/corrected source event before any write;
  5. construct a revoked event with ID `{signal_id}--revoked`, the source event's provenance, the caller's confirmation fields, `related_signal_id=None`, and `memory_revision=profile.memory_revision + 1`;
  6. remove only the matching category projection;
  7. set the revoked event and merge the updated governed profile.

  Catch only `GoogleAPIError` and stored-data `ValueError` at the public boundary and translate them through `_raise_firestore_error("revoke_memory_signal", exc)`. Allow `MemorySignalNotFoundError` and `MemorySignalConflictError` to propagate unchanged for M5 mapping.

- [ ] **Step 4: Verify GREEN for the successful path**

  Run the exact test from Step 2. Expected: `1 passed`.

- [ ] **Step 5: Add a failing read-before-write test**

  Add `test_revoke_memory_signal_reads_every_document_before_writing`. Record operations from root, revoked-event, and source-event reads and transaction writes. Assert all three reads precede both writes.

  Run:

  ```bash
  pytest -q tests/test_memory_lifecycle_database.py::test_revoke_memory_signal_reads_every_document_before_writing
  ```

  Expected RED if any helper performs an early write; otherwise it may already pass because Step 3 intentionally implements this invariant. If it passes immediately, temporarily perturb the assertion or implementation locally only to prove the test observes ordering, then restore the correct test and code before continuing. Do not preserve the perturbation.

- [ ] **Step 6: Add and implement idempotent retry behavior**

  Add `test_revoke_memory_signal_returns_existing_event_without_writes`. The active projection is absent and the deterministic revoked event exists. Assert the method:

  - validates that the event targets the same signal/category and carries the same confirmation fields;
  - accepts `profile.memory_revision >= event.memory_revision`, allowing unrelated later memory changes;
  - returns the current profile and stored event;
  - performs no writes.

  Add `test_revoke_memory_signal_rejects_different_retry_confirmation` and assert `MemorySignalConflictError` with no writes when the stored event does not prove the same action.

  Run:

  ```bash
  pytest -q \
    tests/test_memory_lifecycle_database.py::test_revoke_memory_signal_returns_existing_event_without_writes \
    tests/test_memory_lifecycle_database.py::test_revoke_memory_signal_rejects_different_retry_confirmation
  ```

  Expected after minimal implementation: `2 passed`.

- [ ] **Step 7: Add and implement not-found and integrity behavior**

  Add focused tests for:

  - unknown signal with no revoked event → `MemorySignalNotFoundError`;
  - inactive/superseded signal with no revoked event → `MemorySignalNotFoundError`;
  - deterministic revoked event exists while the same signal remains active → `MemoryEngineError` caused by `ValueError`, because stored state is internally inconsistent;
  - missing/mismatched source event for an active signal → `MemoryEngineError` caused by `ValueError`;
  - a different signal active in the same category is not removed.

  Run:

  ```bash
  pytest -q tests/test_memory_lifecycle_database.py -k 'revoke and (not_found or inconsistent or source or different_active)'
  ```

  Expected after minimal implementation: all selected tests pass.

- [ ] **Step 8: Add and implement validation and safe-error tests**

  Add parameterized tests proving invalid `user_id`, category, signal prefix, overlong derived ID, confirmation-channel combination, and naive `observed_at` raise `ValueError` before `client.collection()`.

  Add a Firestore-failure test using `ServiceUnavailable` and assert:

  - `MemoryEngineError.__cause__` is the original exception;
  - the public message is `Firestore revoke_memory_signal operation failed.`;
  - logs contain none of the private identifiers, source references, confirmation references, values, or backend details.

  Run:

  ```bash
  pytest -q tests/test_memory_lifecycle_database.py -k 'revoke'
  ```

  Expected: all revocation tests pass.

- [ ] **Step 9: Refactor while green**

  Extract only helpers directly shared by M4, such as:

  - `_validate_memory_signal_inputs()`;
  - `_profile_without_signal()`;
  - `_validate_existing_revocation()`;
  - `_revocation_event()`.

  Do not split `database.py` or restructure M1-M3 in this pass. Rerun the Step 8 command after refactoring.

---

### Task 2: Bounded transactional hard deletion

**Files:**
- Modify: `database.py`
- Modify: `tests/test_memory_lifecycle_database.py`

**Interfaces:**
- Consumes: the M4 signal validation helper, typed profile parsing, category proposal parsing, deterministic event IDs, and public `AsyncTransaction.delete()`.
- Produces: `MemoryDeletionResult` and `MemoryEngine.delete_memory_signal()`.

- [ ] **Step 1: Write the first failing active-signal deletion test**

  Add `test_delete_memory_signal_removes_owned_artifacts`. Arrange:

  - a root profile whose active category points to the target signal;
  - a category proposal whose embedded `proposal_id` matches the target;
  - an existing `{signal_id}--approved` event document;
  - absent corrected, superseded, and revoked paths.

  Assert:

  - all six reads—root, category proposal, and four deterministic event paths—occur before any write/delete;
  - the active projection is removed;
  - the proposal and only the existing target event document are deleted;
  - the root governed profile is merged once with revision incremented exactly once;
  - `artifacts_deleted` is `True`;
  - no source or confirmation message path is accessed.

- [ ] **Step 2: Verify RED**

  Run:

  ```bash
  pytest -q tests/test_memory_lifecycle_database.py::test_delete_memory_signal_removes_owned_artifacts
  ```

  Expected: failure because `MemoryDeletionResult` and/or `delete_memory_signal()` do not exist.

- [ ] **Step 3: Implement the minimum bounded deletion transaction**

  Before creating Firestore references, validate `user_id`, `category`, `signal_id`, category prefix, and all four derived event IDs.

  In one transaction:

  1. read root, category proposal, approved event, corrected event, superseded event, and revoked event;
  2. parse the root as governed profile or empty default;
  3. remove the category projection only when its nested `signal_id` equals the target;
  4. delete the category proposal only when its embedded `proposal_id` equals the target;
  5. validate every existing event document against its path, target signal, and category before deleting it;
  6. if any target-owned artifact was found, increment revision exactly once and merge the governed root profile;
  7. delete each discovered target-owned proposal/event document;
  8. return `MemoryDeletionResult(updated_profile, True)`.

  If no target-owned artifact exists, return the current profile with `artifacts_deleted=False` and perform no write/delete. If the root is absent but inactive target history exists, create an empty governed root at revision 1 so the required deletion revision is retained.

  Catch `GoogleAPIError` and stored-data `ValueError` at the public boundary and translate them through `_raise_firestore_error("delete_memory_signal", exc)`.

- [ ] **Step 4: Verify GREEN for active deletion**

  Run the exact test from Step 2. Expected: `1 passed`.

- [ ] **Step 5: Add and implement inactive-history deletion**

  Add `test_delete_memory_signal_removes_inactive_history`. The target is not projected, but fixed superseded/revoked event paths exist. Assert those events are deleted and root revision increases once.

  Add `test_delete_memory_signal_creates_revision_root_for_orphan_history`. The root is absent but one valid fixed target event exists. Assert deletion plus a new empty governed root at revision 1.

  Run:

  ```bash
  pytest -q \
    tests/test_memory_lifecycle_database.py::test_delete_memory_signal_removes_inactive_history \
    tests/test_memory_lifecycle_database.py::test_delete_memory_signal_creates_revision_root_for_orphan_history
  ```

  Expected after minimal implementation: `2 passed`.

- [ ] **Step 6: Add and implement exact ownership boundaries**

  Add tests proving:

  - a newer proposal occupying the same category slot is retained when its embedded proposal ID differs;
  - a different active signal in the category is retained;
  - event paths outside the four deterministic target IDs are never read or deleted;
  - source and confirmation chat messages are never read or deleted;
  - malformed/mismatched documents fail closed with `MemoryEngineError` rather than deleting uncertain data.

  Add an explicit test documenting the bounded lineage limitation: deleting a superseded target deletes its own fixed events, while a successor corrected event outside the target's fixed paths is neither read nor mutated even if its `related_signal_id` names the target.

  Run:

  ```bash
  pytest -q tests/test_memory_lifecycle_database.py -k 'delete and (ownership or different or bounded or malformed or lineage)'
  ```

  Expected: all selected tests pass.

- [ ] **Step 7: Add and implement idempotency**

  Add `test_delete_memory_signal_is_idempotent_when_artifacts_are_absent`. Assert an absent target returns `artifacts_deleted=False`, preserves the current revision/profile, and performs no write or delete.

  Add `test_delete_memory_signal_retry_after_deletion_preserves_revision` using a stateful offline fake or two arranged calls. Assert the first call increments once and the retry does not increment again.

  Run:

  ```bash
  pytest -q tests/test_memory_lifecycle_database.py -k 'delete and idempotent or retry_after_deletion'
  ```

  Expected: both tests pass.

- [ ] **Step 8: Add validation and safe-error tests**

  Parameterize invalid `user_id`, category, signal prefix, and derived event length. Assert `ValueError` occurs before `client.collection()`.

  Simulate `ServiceUnavailable` from a transaction read and assert:

  - `MemoryEngineError.__cause__` is preserved;
  - the public message is `Firestore delete_memory_signal operation failed.`;
  - logs exclude all identifiers, values, document content, and backend details.

  Run:

  ```bash
  pytest -q tests/test_memory_lifecycle_database.py -k 'delete'
  ```

  Expected: all deletion tests pass.

- [ ] **Step 9: Refactor while green**

  Extract only deletion helpers needed to keep the transaction auditable, such as `_memory_event_ids_for_signal()`, `_validate_deletable_event()`, and `_proposal_belongs_to_signal()`. Keep all state-dependent work inside the retryable callback and all input-derived reference construction outside it.

  Rerun:

  ```bash
  pytest -q tests/test_memory_lifecycle_database.py
  ```

  Expected: all M4 persistence tests pass.

---

### Task 3: Reproducible live M4 smoke runner

**Files:**
- Create: `smoke_test_memory_lifecycle.py`
- Create: `tests/test_smoke_test_memory_lifecycle.py`

**Interfaces:**
- Consumes: `MemoryEngine.create_memory_proposal()`, `approve_memory_proposal()`, `revoke_memory_signal()`, `delete_memory_signal()`, and `get_collaboration_profile()`.
- Produces: one offline-tested command-line runner with `revoke` and `delete` stages so Firestore can be inspected between retained-history and hard-deletion states.

- [ ] **Step 1: Write failing smoke-runner tests**

  Add offline fake-engine tests for:

  - `run_revocation_smoke()` creates and approves one unique signal, revokes it, retries the identical revocation, loads the final profile, and verifies revisions `1 → 2 → 2` with no active category signal;
  - `run_deletion_smoke()` deletes the supplied revoked signal, retries deletion, loads the final profile, and verifies revisions `2 → 3 → 3` with first `artifacts_deleted=True` and retry `False`;
  - both safe summaries omit memory values, chat content, source identifiers, and confirmation identifiers;
  - both paths close the engine in `finally`.

  Run:

  ```bash
  pytest -q tests/test_smoke_test_memory_lifecycle.py
  ```

  Expected: collection failure because the smoke module/functions do not exist.

- [ ] **Step 2: Implement the staged smoke runner**

  Implement:

  ```text
  python3 smoke_test_memory_lifecycle.py revoke
  python3 smoke_test_memory_lifecycle.py delete --user-id <ID> --signal-id <ID> --category response_length
  ```

  The `revoke` stage generates server-side-safe random identifiers before persistence, creates a 24-hour proposal, approves through `memory_api`, revokes through `memory_api`, verifies an identical retry, and prints only structural evidence needed for the delete command.

  The `delete` stage accepts the three non-secret locators printed by the first stage, performs deletion and an idempotent retry, reloads the profile, and prints only structural pass evidence. It must not print the memory value or any message/session content.

- [ ] **Step 3: Verify GREEN and CLI help**

  Run:

  ```bash
  pytest -q tests/test_smoke_test_memory_lifecycle.py
  python3 smoke_test_memory_lifecycle.py --help
  ```

  Expected: all tests pass; help documents the two stages without contacting Firestore.

---

### Task 4: Focused regression verification and manual acceptance handoff

**Files:**
- Verify only; no new production behavior.

**Interfaces:**
- Consumes: M1-M4 persistence and schema contracts.
- Produces: evidence for the manual acceptance gate; no Git commit or push.

- [ ] **Step 1: Run the complete M4 focused suite**

  ```bash
  pytest -q \
    tests/test_memory_lifecycle_database.py \
    tests/test_smoke_test_memory_lifecycle.py
  ```

  Expected: all M4 tests pass with no unexplained warnings.

- [ ] **Step 2: Run directly related M2/M3 regressions**

  ```bash
  pytest -q \
    tests/test_memory_database.py \
    tests/test_memory_approval_database.py \
    tests/test_smoke_test_memory_persistence.py \
    tests/test_smoke_test_memory_approval.py
  ```

  Expected: all related proposal, approval, correction, profile, and smoke tests pass. The full repository suite is not required because M4 does not change FastAPI, supervisor, Gemini, synthesis, frontend, or deployment surfaces.

- [ ] **Step 3: Run static hygiene checks**

  ```bash
  python3 -m py_compile database.py smoke_test_memory_lifecycle.py tests/test_memory_lifecycle_database.py tests/test_smoke_test_memory_lifecycle.py
  git diff --check
  ```

  Expected: both commands exit 0.

- [ ] **Step 4: Present manual runtime verification**

  Ask the user to run the revocation stage:

  ```bash
  python3 smoke_test_memory_lifecycle.py revoke
  ```

  Expected summary: `trusted-memory-m4 revoke-pass`, approval revision 1, revocation revision 2, retry revision 2, and printed `user_id`, `category`, `signal_id`, and revoked event ID.

  Before deletion, inspect Firestore and verify:

  - the governed `response_length` projection is absent;
  - the proposal remains;
  - the approved and revoked lifecycle events remain;
  - the revoked event uses the original source references and current revocation confirmation fields;
  - `memory_revision` is 2.

  Then run the exact delete command using the printed locators:

  ```bash
  python3 smoke_test_memory_lifecycle.py delete \
    --user-id <PRINTED_USER_ID> \
    --signal-id <PRINTED_SIGNAL_ID> \
    --category response_length
  ```

  Expected summary: `trusted-memory-m4 delete-pass`, deletion revision 3, retry revision 3, first deletion `artifacts_deleted=true`, retry `artifacts_deleted=false`.

  Inspect Firestore again and verify:

  - the category proposal document is gone;
  - all four deterministic target event paths are absent;
  - no active target projection exists;
  - the governed root remains at `memory_revision` 3;
  - unrelated user/session/project data remains unchanged.

  Firestore console:

  <https://console.cloud.google.com/firestore/databases/-default-/data/panel/users?project=project-e1e2a890-4566-48a8-a32>

- [ ] **Step 5: Stop at the manual gate**

  Report **implemented, pending manual verification**. Do not commit or push. After the user confirms both Firestore stages, checkpoint exactly the M4 files and then propose M5 as a separate pass.

---

## Stop Conditions

Stop implementation and propose a revised plan if any of these occurs:

- the pinned async Firestore transaction API cannot expose public bounded document deletion through the existing fake pattern;
- a transaction requires a query or subcollection scan to locate target artifacts;
- deletion would have to mutate a successor's immutable event to erase an incoming `related_signal_id`;
- any mutation can occur before every required transaction read completes;
- a malformed document cannot be distinguished safely from a target-owned artifact;
- M4 requires changes to `main.py`, supervisor code, schemas, dependencies, authentication, frontend, or deployment;
- the live smoke result cannot be inspected between revocation and deletion;
- a Firestore failure leaks a memory value, identifier, or backend detail into logs.

## Post-M4 Boundary

After manual acceptance and checkpointing, propose **M5 — Trusted memory application service and inspection API**. M5 will map these persistence results/errors to authenticated-later local-development HTTP contracts, add bounded event/proposal inspection, and return mutation receipts. M5 must not be started as part of M4.
