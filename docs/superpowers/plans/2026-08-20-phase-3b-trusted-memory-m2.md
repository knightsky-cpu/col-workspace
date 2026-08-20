# Phase 3B Trusted Memory M2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline, task by task.
> Do not delegate to subagents. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Persist one short-lived, user-confirmable memory proposal per
allowlisted category with transactional expiry and retry behavior, while
proving that proposal creation cannot activate or modify the user's governed
memory profile.

**Architecture:** `MemoryEngine` receives an already validated
`MemoryProposal` from the future `TrustedMemoryService` and owns the exact
Firestore path, transaction, server timestamp, stored-document conversion,
and safe infrastructure error translation. The category is the deterministic
document ID, so the ten policy categories provide at most ten unresolved
slots without a collection query. A transaction returns an identical
unexpired pending proposal, rejects a different unexpired occupant, or
replaces a resolved or expired slot. No root user-profile document is read or
written in M2.

**Tech Stack:** Python 3.14.7, Pydantic 2.13.4,
google-cloud-firestore 2.28.1, pytest 9.1.1, pytest-asyncio 1.4.0

**Spec:**
`docs/superpowers/specs/2026-08-20-phase-3b-trusted-memory-design.md`

## Global constraints

- Execute inline and follow strict RED-GREEN-REFACTOR one behavior at a time.
- Keep `memory_schema_version` and `policy_version` fixed at `"1.0"`.
- Accept only an already validated `MemoryProposal`; M2 does not interpret
  natural language, infer preferences, or decide whether consent occurred.
- Use exactly `users/{user_id}/memory_proposals/{category}`. Never query for a
  model-supplied proposal ID.
- Require proposal IDs to have the form `{category}--{non_empty_suffix}`.
- Require `user_id` to match the existing `IdentifierStr` boundary: 1 through
  128 ASCII alphanumeric, underscore, or hyphen characters. Reject path
  separators before constructing a Firestore reference.
- Allow at most one unresolved proposal per category and therefore at most ten
  unresolved proposals across the two identity and eight preference
  categories.
- Require new proposals to be pending, timezone-aware, unexpired at the
  supplied observation time, and configured for exactly 24 hours from their
  application creation time.
- Use `firestore.SERVER_TIMESTAMP` for the persisted `created_at` field and
  store the application-derived, timezone-aware `expires_at` deadline.
- Treat Firestore TTL as future cleanup only. Transactional application logic
  must compare the stored `expires_at` directly.
- Define identical pending retries by the stable fields `proposal_id`,
  `category`, `proposed_value`, `expected_signal_id`, `policy_version`,
  `source_session_id`, `source_message_id`, and `expires_at`. Exclude
  `created_at` because Firestore resolves its server timestamp.
- Return an identical unexpired pending proposal without writing.
- Reject a different unexpired pending proposal without writing.
- Replace a resolved or expired category slot with the new pending proposal.
- Do not read, create, merge, or update `users/{user_id}` profile fields,
  `identity_context`, `active_preferences`, `memory_revision`, or lifecycle
  events.
- Preserve current `ChatRequest`, `ChatResponse`, `/api/chat`,
  `/api/synthesize`, supervisor, synthesis, profile compatibility, and message
  persistence behavior.
- Add no HTTP route, ADK tool, Gemini call, dependency, index, environment
  variable, authentication behavior, frontend behavior, or deployment change.
- Pytest must remain offline. Live Firestore access is limited to the explicit
  manual smoke runner.
- Logs must exclude user, proposal, session, message, category, and memory
  values. Exceptions must preserve the original cause.
- Do not commit or push until the user completes manual verification and
  explicitly authorizes the checkpoint.

## File structure

- Modify `database.py`: add the proposal-slot conflict error, validation and
  conversion helpers, one transactional `create_memory_proposal` method, and
  safe stored-document error translation.
- Create `tests/test_memory_database.py`: focused offline transaction, path,
  expiry, idempotency, replacement, validation, no-profile-mutation, and safe
  error tests.
- Create `smoke_test_memory_persistence.py`: live Firestore runner that writes
  one pseudonymous pending proposal and invokes the same proposal twice to
  prove idempotency.
- Create `tests/test_smoke_test_memory_persistence.py`: offline regression for
  the smoke runner; it must use a fake engine and perform no network access.

## Public interface

`database.py` will expose:

```python
class MemoryProposalConflictError(RuntimeError):
    """Raised when a different unexpired proposal owns a category slot."""


class MemoryEngine:
    async def create_memory_proposal(
        self,
        user_id: str,
        proposal: MemoryProposal,
        *,
        observed_at: datetime,
    ) -> MemoryProposal:
        """Create, reuse, or replace one deterministic proposal slot."""
```

`observed_at` is captured once by the caller and remains fixed if Firestore
retries the transaction. M2 deliberately does not generate proposal IDs or
clock values inside the transaction callback. M5's `TrustedMemoryService`
will own those operations before it calls this interface.

`MemoryProposalConflictError` is a persistence-state distinction, not a
Firestore outage. M5 will translate it into its typed domain conflict and
FastAPI will later map that domain failure to HTTP `409`. M2 does not add the
HTTP mapping early.

---

### Task 1: Deterministic category-slot transaction and server timestamp

**Files:**

- Modify: `database.py`
- Create: `tests/test_memory_database.py`

**Interfaces:**

- Consumes `schemas.MemoryProposal` and the existing injected
  `google.cloud.firestore.AsyncClient`.
- Produces `MemoryEngine.create_memory_proposal(user_id, proposal, *,
  observed_at) -> MemoryProposal`.
- Writes only `users/{user_id}/memory_proposals/{proposal.category}`.
- Persists exactly the proposal fields plus `resolved_at=None`, replacing the
  slot document rather than merging stale resolved fields.

- [ ] **Step 1: Write the new-slot RED test**

Create reusable deterministic fixtures in `tests/test_memory_database.py`:

```python
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.cloud import firestore

from database import MemoryEngine
from schemas import MemoryProposal


NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


def proposal(
    *,
    proposal_id: str = "response_length--proposal-1",
    value: str = "concise",
    status: str = "pending",
    created_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(hours=24),
) -> MemoryProposal:
    return MemoryProposal.model_validate(
        {
            "proposal_id": proposal_id,
            "category": "response_length",
            "proposed_value": value,
            "expected_signal_id": None,
            "policy_version": "1.0",
            "status": status,
            "source_session_id": "source-session",
            "source_message_id": "source-message",
            "created_at": created_at,
            "expires_at": expires_at,
        }
    )


def install_transaction_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    def run_without_sdk_retry(callback):
        async def run(transaction, *args, **kwargs):
            return await callback(transaction, *args, **kwargs)

        return run

    monkeypatch.setattr(
        "database.firestore.async_transactional",
        run_without_sdk_retry,
    )


@pytest.mark.asyncio
async def test_create_memory_proposal_writes_only_category_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    proposals = MagicMock()
    proposal_ref = MagicMock()
    transaction = MagicMock()
    snapshot = SimpleNamespace(exists=False, to_dict=lambda: None)
    proposal_ref.get = AsyncMock(return_value=snapshot)
    client.collection.return_value = users
    users.document.return_value = user
    user.collection.return_value = proposals
    proposals.document.return_value = proposal_ref
    client.transaction.return_value = transaction
    candidate = proposal()

    result = await MemoryEngine(client).create_memory_proposal(
        "user-1",
        candidate,
        observed_at=NOW,
    )

    assert result is candidate
    client.collection.assert_called_once_with("users")
    users.document.assert_called_once_with("user-1")
    user.collection.assert_called_once_with("memory_proposals")
    proposals.document.assert_called_once_with("response_length")
    proposal_ref.get.assert_awaited_once_with(transaction=transaction)
    transaction.set.assert_called_once_with(
        proposal_ref,
        {
            "proposal_id": "response_length--proposal-1",
            "category": "response_length",
            "proposed_value": "concise",
            "expected_signal_id": None,
            "policy_version": "1.0",
            "status": "pending",
            "source_session_id": "source-session",
            "source_message_id": "source-message",
            "created_at": firestore.SERVER_TIMESTAMP,
            "expires_at": NOW + timedelta(hours=24),
            "resolved_at": None,
        },
    )
    user.get.assert_not_called()
    user.set.assert_not_called()
```

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_memory_database.py::test_create_memory_proposal_writes_only_category_slot \
  -v
```

Expected: collection fails because `MemoryEngine` has no
`create_memory_proposal` method.

- [ ] **Step 3: Implement the minimal transaction**

In `database.py`, import `datetime`, `timedelta`, and `MemoryProposal`. Add the
public method with validation delegated to the helpers planned in Task 3.
Construct references before the callback, create a transaction with
`self._client.transaction()`, and wrap a deterministic callback at call time:

```python
transaction = self._client.transaction()

async def create_in_transaction(transaction):
    snapshot = await proposal_ref.get(transaction=transaction)
    if not snapshot.exists:
        transaction.set(
            proposal_ref,
            self._proposal_document(proposal),
        )
        return proposal
    return self._resolve_occupied_proposal_slot(
        transaction,
        proposal_ref,
        snapshot.to_dict(),
        proposal,
        observed_at,
    )

run_transaction = firestore.async_transactional(create_in_transaction)
return await run_transaction(transaction)
```

The callback may read and enqueue a write only. It must not log, generate an
ID, read a clock, call a service, or mutate application state.

Implement `_proposal_document(proposal)` using
`proposal.model_dump(mode="python")`, then replace `created_at` with
`firestore.SERVER_TIMESTAMP` and add `resolved_at=None`.

- [ ] **Step 4: Verify GREEN**

Run the named test from Step 2. Expected: one test passes.

- [ ] **Step 5: Add and verify read-before-write ordering**

Add a test whose fake `proposal_ref.get` appends `"read"` and whose
`transaction.set` appends `"write"` to one list. Assert the final list is
exactly `['read', 'write']`. Run the two Task 1 tests and expect both to pass.

- [ ] **Step 6: Refactor while green**

Keep document serialization in one static helper and the transaction callback
free of duplicated field construction. Rerun the two Task 1 tests.

---

### Task 2: Idempotent retry, conflict, expiry, and resolved-slot replacement

**Files:**

- Modify: `database.py`
- Modify: `tests/test_memory_database.py`

**Interfaces:**

- Produces `MemoryProposalConflictError`.
- Adds private stored-document validation and stable-equality helpers.
- Preserves Task 1's public method and exact Firestore path.
- Performs zero writes for an identical unexpired retry or a conflicting
  unexpired occupant.

- [ ] **Step 1: Write the identical-retry RED test**

Use an existing snapshot whose dictionary contains the candidate fields,
`created_at=NOW + timedelta(milliseconds=20)` to simulate Firestore's resolved
server timestamp, and `resolved_at=None`. Call with `observed_at=NOW +
timedelta(seconds=1)` and assert:

```python
assert result.proposal_id == candidate.proposal_id
assert result.created_at == NOW + timedelta(milliseconds=20)
transaction.set.assert_not_called()
```

This test proves that `created_at` is intentionally excluded from stable retry
identity while the stored authoritative timestamp is returned.

- [ ] **Step 2: Verify RED**

Run only the identical-retry test. Expected: the current occupied-slot branch
does not return the stored proposal without writing.

- [ ] **Step 3: Implement stored-document conversion and stable equality**

Select only `MemoryProposal.model_fields` from the stored dictionary so the
Firestore-only `resolved_at` field cannot violate `extra="forbid"`:

```python
proposal_fields = {
    field_name: document.get(field_name)
    for field_name in MemoryProposal.model_fields
}
stored = MemoryProposal.model_validate(proposal_fields)
```

Compare the exact stable fields listed in Global constraints. If the stored
proposal is pending, unexpired, and identical, return the stored validated
model without calling `transaction.set`.

- [ ] **Step 4: Verify GREEN**

Run the identical-retry test and the Task 1 tests. Expected: all pass.

- [ ] **Step 5: Write the occupied-slot conflict RED test**

Add `test_create_memory_proposal_rejects_different_unexpired_slot`. Store a
pending `response_length--proposal-1` with value `concise`, submit
`response_length--proposal-2` with value `detailed`, and assert:

```python
candidate = proposal(
    proposal_id="response_length--proposal-2",
    value="detailed",
)

with pytest.raises(MemoryProposalConflictError) as caught:
    await engine.create_memory_proposal(
        "user-1",
        candidate,
        observed_at=NOW,
    )

assert str(caught.value) == (
    "An unexpired memory proposal already occupies this category."
)
transaction.set.assert_not_called()
```

Do not include category, user, proposal, session, message, or value data in the
exception text.

- [ ] **Step 6: Verify RED, then implement the conflict**

Run the named conflict test. Expected: import or behavior failure because the
typed conflict does not exist. Add `MemoryProposalConflictError` and raise it
only for a different unexpired pending occupant. Rerun the named test and
expect it to pass.

- [ ] **Step 7: Write replacement RED tests**

Parameterize these stored-slot states:

```python
(
    ("pending", NOW - timedelta(seconds=1)),
    ("approved", NOW + timedelta(hours=1)),
    ("rejected", NOW + timedelta(hours=1)),
)
```

Submit a different pending candidate and assert one full replacement
`transaction.set(proposal_ref, expected_document)` occurs for every case.
Assert the replacement resets `resolved_at` to `None` and writes no root
profile or event document.

- [ ] **Step 8: Verify RED, implement replacement, and verify GREEN**

Run only the replacement test. Implement the smallest state/expiry branch that
reuses `_proposal_document`. Rerun all Task 2 and Task 1 tests. Expected: all
pass.

- [ ] **Step 9: Add the expiry boundary test**

Store a pending proposal with `expires_at == observed_at` and prove it is
expired and replaceable. This locks the rule to `expires_at > observed_at` for
an active slot, rather than `>=`. Run the named test and all Task 2 tests.

---

### Task 3: Input validation and content-free failure translation

**Files:**

- Modify: `database.py`
- Modify: `tests/test_memory_database.py`

**Interfaces:**

- Preserves the existing `MemoryEngineError` contract and original exception
  chaining.
- Rejects caller errors before any Firestore reference or transaction access.
- Allows `MemoryProposalConflictError` to propagate unchanged and unlogged.
- Converts Google API failures, exhausted SDK-transaction `ValueError`, and
  invalid stored proposal documents to `MemoryEngineError` with content-free
  logs.

- [ ] **Step 1: Write pre-Firestore validation RED tests**

Parameterize these cases and assert `client.collection` and
`client.transaction` are never called:

```python
(
    ("", proposal(), NOW),
    ("user/other", proposal(), NOW),
    ("x" * 129, proposal(), NOW),
    ("user-1", object(), NOW),
    ("user-1", proposal(status="approved"), NOW),
    (
        "user-1",
        proposal(proposal_id="formatting_style--proposal-1"),
        NOW,
    ),
    (
        "user-1",
        proposal(expires_at=NOW + timedelta(hours=23)),
        NOW,
    ),
    (
        "user-1",
        proposal(expires_at=NOW),
        NOW,
    ),
)
```

Add separate cases for a naive `observed_at`, naive `created_at`, naive
`expires_at`, a future `created_at`, and a proposal ID with an empty category
suffix.

- [ ] **Step 2: Verify RED**

Run the parameterized validation test. Expected: at least one invalid case
reaches Firestore or succeeds.

- [ ] **Step 3: Implement the minimal validators**

Add private helpers that:

- validate `user_id` against `^[A-Za-z0-9_-]{1,128}$` before any path
  construction;
- require `isinstance(proposal, MemoryProposal)`;
- require aware `datetime` objects for all three times;
- require `proposal.status == "pending"`;
- require `proposal.proposal_id.startswith(f"{proposal.category}--")` and a
  non-empty suffix;
- require `proposal.created_at <= observed_at < proposal.expires_at`;
- require `proposal.expires_at - proposal.created_at == timedelta(hours=24)`.

All validation happens before `self._client.collection(...)`.

- [ ] **Step 4: Verify GREEN**

Run the validation test plus Tasks 1 and 2. Expected: all pass.

- [ ] **Step 5: Write safe Firestore-failure RED test**

Make the patched transaction runner raise
`ServiceUnavailable("private-backend-detail")`. Use private sentinel strings
for every identifier and the proposed value. Assert:

```python
candidate = proposal()
private_values = (
    "private-user-id",
    "source-session",
    "source-message",
    "concise",
    "private-backend-detail",
)

with pytest.raises(MemoryEngineError) as caught:
    await engine.create_memory_proposal(
        "private-user-id",
        candidate,
        observed_at=NOW,
    )

assert caught.value.__cause__ is firestore_error
assert str(caught.value) == (
    "Firestore create_memory_proposal operation failed."
)
for private_text in private_values:
    assert private_text not in caplog.text
```

- [ ] **Step 6: Verify RED, implement error translation, and verify GREEN**

Run the safe failure test. Expected: raw `ServiceUnavailable` escapes. Wrap
only the transactional execution in `try/except`. Translate `GoogleAPIError`
and transaction-exhaustion or stored-document `ValueError` through the
existing content-free logger and `MemoryEngineError`, preserving `__cause__`.
Do not catch `MemoryProposalConflictError`.

Rerun the named test and expect it to pass.

- [ ] **Step 7: Add malformed stored-document and conflict-log tests**

Add one snapshot missing `source_message_id` and prove it becomes a safely
chained `MemoryEngineError`. Add one conflict test with `caplog` and prove no
error log is emitted. Run all of `tests/test_memory_database.py`.

- [ ] **Step 8: Run persistence regressions**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_memory_database.py \
  tests/test_database.py \
  tests/test_memory_schemas.py \
  -v
```

Expected: all tests pass with no network access.

---

### Task 4: Reproducible live Firestore smoke runner

**Files:**

- Create: `smoke_test_memory_persistence.py`
- Create: `tests/test_smoke_test_memory_persistence.py`

**Interfaces:**

- Produces `exercise_memory_proposal(engine, *, user_id, proposal_id,
  observed_at) -> MemoryProposal` for offline testing.
- The command-line entrypoint creates one `MemoryEngine`, a pseudonymous unique
  user ID and proposal ID, calls the same proposal twice, verifies the stable
  proposal ID, closes the client, and prints one copy-safe success line.
- Performs no profile activation, event creation, API request, Gemini call, or
  ADK invocation.

- [ ] **Step 1: Write the smoke-runner RED test**

Create a fake engine with `create_memory_proposal = AsyncMock` returning the
same validated proposal twice. Import `exercise_memory_proposal`, call it, and
assert:

```python
assert result.proposal_id == "response_length--smoke-proposal"
assert fake_engine.create_memory_proposal.await_count == 2
assert all(
    call.kwargs["observed_at"] == NOW
    for call in fake_engine.create_memory_proposal.await_args_list
)
```

Also run the module entrypoint with `MemoryEngine`, `uuid4`, and the clock
patched so the test remains offline. Assert the output starts with
`trusted-memory-m2 pass user_id=memory-m2-smoke-` and contains only the
pseudonymous generated ID and the allowlisted category.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_smoke_test_memory_persistence.py \
  -v
```

Expected: collection fails because `smoke_test_memory_persistence.py` does not
exist.

- [ ] **Step 3: Implement the minimal runner**

Use `datetime.now(UTC)` once, `uuid4().hex` for pseudonymous identifiers, and
`timedelta(hours=24)` for expiry. Construct a `MemoryProposal` with
`response_length=concise`, call `create_memory_proposal` twice with the exact
same object and `observed_at`, and raise a content-free `RuntimeError` if the
stable proposal IDs differ. Close the client in `finally`.

The final output format is:

```text
trusted-memory-m2 pass user_id=memory-m2-smoke-<random> category=response_length
```

- [ ] **Step 4: Verify GREEN**

Run the smoke-runner test from Step 2. Expected: all tests pass without network
access.

- [ ] **Step 5: Run focused automated verification**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_memory_database.py \
  tests/test_database.py \
  tests/test_memory_schemas.py \
  tests/test_smoke_test_memory_persistence.py \
  -v
```

Expected: all focused persistence, schema, compatibility, and smoke-runner
tests pass.

- [ ] **Step 6: Run required cross-cutting regression verification**

`database.py` is shared by chat, synthesis, and the new memory boundary, so
focused checks alone are insufficient. Run:

```bash
venv/bin/python -m pytest
venv/bin/python -m pip check
venv/bin/python -m compileall -q \
  database.py \
  smoke_test_memory_persistence.py \
  tests/test_memory_database.py \
  tests/test_smoke_test_memory_persistence.py
git diff --check
```

Expected: the full suite passes, dependencies are consistent, compilation
succeeds, and no whitespace errors are reported. Report existing unrelated
warnings exactly rather than hiding them.

## Manual runtime verification targets

M2 has no HTTP proposal endpoint, so a proposal-creation `curl` command would
be dishonest. Use the Python smoke runner for the new behavior and the existing
chat route only as a regression check.

1. Start in the repository with the virtual environment active and run:

   ```bash
   python3 smoke_test_memory_persistence.py
   ```

   Expected: one line matching
   `trusted-memory-m2 pass user_id=memory-m2-smoke-<random>
   category=response_length`. The command internally submits the identical
   proposal twice and exits nonzero if idempotency fails.

2. Open the Firestore console link supplied in the implementation pass report.
   Navigate to the printed
   `users/{user_id}/memory_proposals/response_length` document. Verify it has
   `status=pending`, `policy_version=1.0`, `created_at` as a Firestore timestamp,
   `expires_at` approximately 24 hours later, and `resolved_at=null`.

3. Inspect `users/{user_id}`. Verify no `identity_context`,
   `active_preferences`, or `memory_revision` field was created. No
   `memory_events` document should exist for the smoke user.

4. With Uvicorn running, execute this single-line regression request:

   ```bash
   curl --fail-with-body --silent --show-error --max-time 100 --request POST --header 'Content-Type: application/json' --data '{"project_id":"agent-col","session_id":"phase-3b-memory-m2-regression","user_id":"wifiknight","message":"Explain in one paragraph why pending memory must remain inactive until explicit approval."}' http://127.0.0.1:8000/api/chat
   ```

   Expected: HTTP `200` with the unchanged `response`, `actions`, `artifacts`,
   and `citations` fields. The chat request must not create a memory proposal,
   because supervisor proposal tooling is explicitly deferred to M7.

5. Inspect the application log. Verify it contains no raw user, proposal,
   session, message, category, or memory-value identifiers from the smoke
   operation.

## Acceptance criteria

- A new proposal writes exactly one deterministic category-slot document in a
  Firestore transaction with a server `created_at` timestamp.
- The transaction reads the slot before any write.
- An identical unexpired retry returns the stored proposal and performs no
  write.
- A different unexpired pending proposal raises a content-free typed conflict
  and performs no write.
- Pending proposals at or beyond their deadline and resolved proposals are
  replaceable.
- Caller validation fails before Firestore access.
- Firestore and corrupted-document failures preserve causes and log no private
  content or identifiers.
- Proposal creation cannot read or mutate the root active-memory projection or
  lifecycle events.
- The live smoke runner proves one Firestore write and an idempotent retry.
- Existing chat and synthesis behavior remains green.
- No commit or push occurs before user manual acceptance and explicit
  checkpoint authorization.

## Explicit M2 exclusions

- No proposal ID or clock generation in `TrustedMemoryService`.
- No approval, rejection command, correction, active projection, profile
  loading, lifecycle event, memory revision, revocation, or hard deletion.
- No unresolved-proposal inspection query or response schema.
- No HTTP memory endpoint or chat decision field.
- No supervisor proposal tool, ADK instruction change, or model-facing memory
  arguments.
- No active memory context injection or adaptation receipts in chat or
  synthesis.
- No authentication, frontend, Cloud Run, Search, URL Context, supervisor
  synthesis delegation, or R2 requirement coverage.

## Spec coverage and intentional deferrals

- The deterministic category slot and maximum-ten unresolved bound are covered
  by Tasks 1 and 2 because M1 exposes exactly ten categories.
- Server timestamp storage, direct `expires_at` comparison, and Firestore
  transaction retry safety are covered by Tasks 1 through 3.
- Identical retry, occupied-slot conflict, resolved replacement, and expiry
  replacement are covered by Task 2.
- Safe errors and the no-active-profile boundary are covered by Tasks 1 and 3.
- Reproducible live Firestore evidence is covered by Task 4.
- Proposal ID generation, typed service errors, and HTTP `409` mapping remain
  assigned to M5. M2 exposes the persistence conflict needed by that later
  service without integrating it early.
- Approval and active memory remain assigned to M3; M2 cannot create a durable
  user trait.

## Stop conditions

Stop implementation and present a revised plan before continuing if:

- the installed async Firestore client cannot execute or reliably fake the
  planned transaction callback;
- live evidence shows `SERVER_TIMESTAMP` is unresolved or not stored after
  commit;
- Firestore transaction retry behavior requires ID or time generation inside
  the callback;
- the implementation must read or mutate the root profile to satisfy proposal
  creation;
- an API, supervisor, service, dependency, index, or deployment change becomes
  necessary;
- existing chat or synthesis regressions fail for reasons caused by M2.

## Next approval boundary

After this plan is reviewed, implementation requires a separate explicit
authorization such as:

> Approved; execute Trusted Memory M2 inline.

After M2 is implemented, automatically verified, manually accepted, and
checkpointed, the next separately planned pass is **M3 — Approval, correction,
and active projection**. M3 will add transactional lifecycle events, memory
revision control, active-profile projection updates, correction and
supersession behavior, and typed profile reads. It will not yet add the HTTP
inspection API, structured chat decisions, or supervisor proposal tool.
