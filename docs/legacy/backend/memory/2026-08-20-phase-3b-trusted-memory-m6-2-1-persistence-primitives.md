# Trusted Memory M6.2.1 Persistence Primitives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline. The repository
> owner has selected inline execution. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Build the durable Firestore claim, lease, completion, replay, and
bounded-history primitives required for one retry-safe logical chat turn,
without integrating them into `/api/chat` yet.

**Architecture:** A focused `chat_turns.py` domain module owns identifiers,
typed results, constants, and domain errors. `MemoryEngine` owns all Firestore
transactions. One turn document arbitrates ownership, deterministic message
documents prevent duplicate logical messages, and completed replay is rebuilt
from the model message plus validated receipt fields.

**Tech Stack:** Python 3.14, dataclasses, Pydantic v2, asynchronous Google Cloud
Firestore client, pytest, pytest-asyncio, unittest.mock.

**Spec:**
[`docs/superpowers/specs/2026-08-20-phase-3b-trusted-memory-m6-idempotency-design.md`](2026-08-20-phase-3b-trusted-memory-m6-idempotency-design.md)

## Global constraints

- This pass changes persistence primitives only. It does not change FastAPI,
  `/api/chat`, the supervisor, smoke runners, or public HTTP behavior.
- `Idempotency-Key` remains optional when M6.2.2 integrates the route.
- Keys are 1 through 128 unnormalized ASCII characters matching
  `^[A-Za-z0-9_-]+$`.
- `turn_id` is the lowercase hexadecimal SHA-256 digest of the validated key.
- Turn schema version is exactly `"1.0"`.
- Lease duration is exactly 120 seconds.
- Owner tokens are generated once outside Firestore transaction callbacks.
- Completion requires matching ownership and an unexpired lease.
- Turn documents contain no raw user or model text and no raw idempotency key.
- Raw text remains only in deterministic chat-message documents.
- Input validation raises `ValueError` before Firestore access.
- Firestore `GoogleAPIError` becomes `MemoryEngineError` with the original
  exception preserved as its cause.
- Logs exclude content, response receipts, memory values, identifiers, owner
  tokens, and idempotency keys.
- No dependency changes are permitted.
- No intermediate Git commits are permitted. This repository checkpoints a
  pass only after focused verification and explicit user manual acceptance.
- Full-suite execution is required at the end because `database.py` and
  `get_chat_history()` are shared persistence contracts used by chat,
  synthesis context, memory flows, and existing smoke runners.

## File structure

- Create `chat_turns.py`: pure turn-domain constants, validation, identifier
  derivation, dataclasses, and domain errors. No Firestore imports.
- Create `tests/test_chat_turns.py`: pure unit tests for key validation,
  deterministic IDs, constants, and immutable result types.
- Create `tests/test_chat_turn_database.py`: offline Firestore transaction tests
  for claim, replay, lease renewal/release, completion, corruption handling,
  and safe provider-error translation.
- Modify `database.py`: add the four turn operations, document parsing helpers,
  and optional current-message exclusion in bounded history reads.
- Modify `tests/test_database.py`: preserve existing history behavior and prove
  the new exclusion/limit contract.

---

### Task 1: Pure turn-domain contract

**Files:**

- Create: `chat_turns.py`
- Create: `tests/test_chat_turns.py`

**Interfaces:**

- Consumes: `MemoryDecisionRequest` and `ChatResponse` from `schemas.py`.
- Produces:

```python
CHAT_TURN_SCHEMA_VERSION: Literal["1.0"]
CHAT_TURN_LEASE_DURATION: timedelta

@dataclass(frozen=True, slots=True)
class ChatTurnIds:
    turn_id: str
    user_message_id: str
    model_message_id: str

@dataclass(frozen=True, slots=True)
class ChatTurnRequest:
    project_id: str
    session_id: str
    user_id: str
    message: str
    memory_decision: MemoryDecisionRequest | None = None

@dataclass(frozen=True, slots=True)
class ChatTurnClaim:
    request: ChatTurnRequest
    ids: ChatTurnIds
    owner_token: str
    lease_expires_at: datetime
    resumed: bool

@dataclass(frozen=True, slots=True)
class ChatTurnReplay:
    response: ChatResponse
```

- `ChatTurnConflictError`, `ChatTurnInProgressError`,
  `ChatTurnOwnershipError`, and `ChatTurnStateError` subclass `RuntimeError`.
- `validate_idempotency_key(value: object) -> str` returns the unchanged valid
  key or raises `ValueError`.
- `derive_chat_turn_ids(idempotency_key: str) -> ChatTurnIds` returns the three
  exact identifiers defined below.
- `ChatTurnInProgressError` validates that `retry_after_seconds` is a positive
  integer and exposes it as a read-only instance attribute.
- `derive_chat_turn_ids()` validates its input and returns:
  `turn_id = sha256(key.encode("ascii")).hexdigest()`,
  `user_message_id = f"turn--{turn_id}--user"`, and
  `model_message_id = f"turn--{turn_id}--model"`.

- [ ] **Step 1: Write one clean RED test for exact path derivation**

Avoid a collection-time import error. The first test dynamically imports the
not-yet-existing module and converts absence of the approved interface into an
ordinary assertion failure:

```python
import hashlib
import importlib

import pytest


def test_derive_chat_turn_ids_hashes_key_and_bounds_message_ids() -> None:
    try:
        module = importlib.import_module("chat_turns")
    except ModuleNotFoundError:
        pytest.fail("chat_turns domain module is missing", pytrace=False)
    derive = getattr(module, "derive_chat_turn_ids", None)
    assert callable(derive), "derive_chat_turn_ids is missing"
    key = "550e8400-e29b-41d4-a716-446655440000"
    digest = hashlib.sha256(key.encode("ascii")).hexdigest()

    result = derive(key)

    assert result.turn_id == digest
    assert result.user_message_id == f"turn--{digest}--user"
    assert result.model_message_id == f"turn--{digest}--model"
    assert len(result.user_message_id) <= 128
    assert len(result.model_message_id) <= 128
```

- [ ] **Step 2: Verify the first RED failure**

Run:

```bash
pytest -q tests/test_chat_turns.py::test_derive_chat_turn_ids_hashes_key_and_bounds_message_ids
```

Expected: one assertion failure with `chat_turns domain module is missing`, not
a collection error.

- [ ] **Step 3: Implement only valid-key identifier derivation**

Create `chat_turns.py` with `ChatTurnIds` and
`derive_chat_turn_ids(idempotency_key: str)`. For this first GREEN, require a
string, encode it as ASCII, derive the lowercase SHA-256 digest, and return the
three exact IDs. Do not add lease, request, response, or error types yet.

- [ ] **Step 4: Verify GREEN and normalize the test import**

Run the exact node from Step 2. Expected: PASS. Then replace the dynamic import
with `from chat_turns import derive_chat_turn_ids` and rerun the node to prove
the refactor stays green.

- [ ] **Step 5: Write validation RED cases**

Add `test_validate_idempotency_key_rejects_invalid_values` with the values
`None`, `7`, `""`, `" key"`, `"key "`, `"key/value"`, `"key.value"`, `"clé"`,
and `"a" * 129`. Assert `ValueError` containing `idempotency_key`. Also assert
that `derive_chat_turn_ids()` rejects each value instead of normalizing it.

Run:

```bash
pytest -q tests/test_chat_turns.py -k idempotency_key
```

Expected: FAIL because the public validation function and full boundary do not
exist.

- [ ] **Step 6: Implement validation minimally and verify GREEN**

Add the compiled `^[A-Za-z0-9_-]+$` pattern and
`validate_idempotency_key(value: object) -> str`. Make identifier derivation
call it before hashing. Rerun the command from Step 5; all selected tests must
pass.

- [ ] **Step 7: Write RED tests for constants, immutable result types, and errors**

Add tests proving:

- schema version is exactly `"1.0"`;
- lease duration is exactly 120 seconds;
- `ChatTurnRequest`, `ChatTurnClaim`, and `ChatTurnReplay` are frozen and carry
  the exact annotated values;
- the four domain errors subclass `RuntimeError`;
- `ChatTurnInProgressError(9).retry_after_seconds == 9`;
- boolean, non-integer, zero, and negative retry delays raise `ValueError`.

Run:

```bash
pytest -q tests/test_chat_turns.py -k "contract or error or immutable"
```

Expected: FAIL because those constants and types do not exist.

- [ ] **Step 8: Implement the remaining pure domain contract and verify GREEN**

Add the exact constants, dataclasses, and exceptions listed in this task's
Interfaces section. Import `ChatResponse` and `MemoryDecisionRequest` only for
the typed dataclasses. Rerun all of `tests/test_chat_turns.py`; all tests must
pass with no warning.

- [ ] **Step 9: Refactor while preserving the boundary**

Keep `chat_turns.py` Firestore-free. Do not add serialization helpers, HTTP
headers, or route behavior. Rerun `pytest -q tests/test_chat_turns.py` after any
cleanup.

---

### Task 2: Atomic turn claim, conflict, contention, and replay

**Files:**

- Modify: `database.py`
- Create: `tests/test_chat_turn_database.py`

**Interfaces:**

- Consumes: all types and constants from Task 1.
- Produces:

- `MemoryEngine.claim_chat_turn(self, request: ChatTurnRequest, *,
  idempotency_key: str, observed_at: datetime) -> ChatTurnClaim |
  ChatTurnReplay`.

- The method generates `owner_token = secrets.token_hex(16)` before wrapping
  or executing the transaction callback.
- The transaction reads the turn and deterministic user-message documents
  before writing anything.
- A completed turn additionally reads the deterministic model-message document
  and reconstructs `ChatResponse` from model text and stored receipt arrays.
- Missing paired documents, invalid schema/status/timestamps, mismatched IDs,
  invalid receipt payloads, or raw content in the turn document raise
  `ChatTurnStateError`.
- Stored request mismatch raises `ChatTurnConflictError` without writes.
- An unexpired lease raises `ChatTurnInProgressError` with
  `ceil((lease_expires_at - observed_at).total_seconds())`.
- An expired lease updates only `lease_owner`, `lease_expires_at`, and
  `updated_at`, returning `ChatTurnClaim(resumed=True)`.
- A new turn document contains exactly `schema_version`, `status`,
  `project_id`, `user_id`, `memory_decision`, `user_message_id`,
  `model_message_id`, `lease_owner`, `lease_expires_at`, `created_at`, and
  `updated_at`. `status` is `"in_progress"`; `created_at` and `updated_at` use
  `firestore.SERVER_TIMESTAMP`; `memory_decision` is `None` or
  `request.memory_decision.model_dump(mode="json")`.
- Request comparison requires exact project/user/decision metadata and a user
  message document containing only role `"user"`, the exact request text, and
  a Firestore-resolved timestamp. Session identity is supplied by the document
  path.

- [ ] **Step 1: Write the first claim RED test**

Build an offline transaction fixture following
`tests/test_memory_approval_database.py::install_transaction_runner`. Its
document references must be distinct for the session, turn, user message, and
model message. Then add:

```python
@pytest.mark.asyncio
async def test_claim_chat_turn_atomically_creates_turn_and_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = empty_chat_turn_store()
    monkeypatch.setattr("database.secrets.token_hex", lambda _: "owner-token")
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    claim = await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert claim.owner_token == "owner-token"
    assert claim.resumed is False
    assert claim.lease_expires_at == NOW + timedelta(seconds=120)
    assert store.transaction.set.call_args_list == [
        call(
            store.session_ref,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(store.turn_ref, expected_new_turn_document(claim)),
        call(
            store.user_message_ref,
            {
                "role": "user",
                "text": request.message,
                "timestamp": firestore.SERVER_TIMESTAMP,
            },
        ),
    ]
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q tests/test_chat_turn_database.py::test_claim_chat_turn_atomically_creates_turn_and_user_message
```

Expected: FAIL with `AttributeError: 'MemoryEngine' object has no attribute
'claim_chat_turn'`.

- [ ] **Step 3: Implement the minimum new-claim transaction**

Add imports for `math`, `secrets`, `Mapping`, Pydantic `ValidationError`, and
the Task 1 types. Validate `ChatTurnRequest` strings and timezone-aware
`observed_at` before obtaining a collection or transaction. Generate the owner
token before defining the callback. In the callback, read both snapshots,
reject orphan state, and create exactly the three writes asserted above.

- [ ] **Step 4: Verify the new-claim test is GREEN**

Run the exact node from Step 2. Expected: one passing test.

- [ ] **Step 5: Add RED cases for every no-write claim branch**

Add independently named tests proving:

```text
test_claim_chat_turn_rejects_request_mismatch_without_writes
test_claim_chat_turn_rejects_unexpired_lease_with_ceiling_retry_delay
test_claim_chat_turn_concurrent_second_claim_observes_unexpired_lease
test_claim_chat_turn_reclaims_expired_lease_with_new_owner
test_claim_chat_turn_reuses_owner_token_when_sdk_retries_callback
test_claim_chat_turn_rejects_turn_without_user_message
test_claim_chat_turn_rejects_user_message_without_turn
test_claim_chat_turn_document_excludes_raw_key_and_chat_text
test_claim_chat_turn_rejects_raw_text_in_turn_document
test_claim_chat_turn_replays_completed_response_without_writes
test_claim_chat_turn_rejects_completed_turn_without_model_message
test_claim_chat_turn_validates_all_inputs_before_firestore_access
test_claim_chat_turn_preserves_firestore_failure_as_cause
test_claim_chat_turn_failure_log_excludes_private_values_and_ids
```

The contention test uses a stateful fake: after the first transaction's writes
are applied, the second claim reads the resulting unexpired turn and must raise
`ChatTurnInProgressError` without any write. The owner-token retry test captures
the callback installed by a custom `firestore.async_transactional` fake,
invokes that same callback twice, and asserts `database.secrets.token_hex` was
called exactly once. The privacy test recursively inspects the turn document
and proves neither the raw key nor the user message occurs in any key or value.
The completed replay fixture stores only bounded metadata and receipts in the
turn document, with response text solely in the model-message document.

- [ ] **Step 6: Run the expanded claim tests and inspect RED reasons**

Run:

```bash
pytest -q tests/test_chat_turn_database.py -k claim
```

Expected: each new case fails because its corresponding branch or validation
does not exist, not because the fixture is malformed.

- [ ] **Step 7: Implement claim parsing and branches minimally**

Add four private helpers in `MemoryEngine`:

- `_validate_chat_turn_request(self, request: ChatTurnRequest, observed_at:
  datetime) -> None` validates every input before Firestore access.
- `_chat_turn_request_document(self, request: ChatTurnRequest, claim:
  ChatTurnClaim) -> dict[str, object]` returns the exact new-turn document.
- `_assert_chat_turn_request_matches(self, request: ChatTurnRequest, ids:
  ChatTurnIds, turn_data: object, user_message_data: object) -> None` validates
  stored structure and raises conflict only for a well-formed different
  request.
- `_chat_turn_replay(self, ids: ChatTurnIds, turn_data: object,
  model_message_data: object) -> ChatTurnReplay` reconstructs the typed replay.

`_chat_turn_replay()` constructs `ChatResponse` and translates Pydantic
`ValidationError` into `ChatTurnStateError`. It rejects any user/model text
fields in the turn document and requires model-message role `"model"` plus a
non-empty string `text`.

- [ ] **Step 8: Verify all claim tests are GREEN**

Run:

```bash
pytest -q tests/test_chat_turn_database.py -k claim
```

Expected: all claim tests pass with no unexplained warning.

---

### Task 3: Lease renewal and safe release

**Files:**

- Modify: `database.py`
- Modify: `tests/test_chat_turn_database.py`

**Interfaces:**

- Consumes: `ChatTurnClaim` from Task 1.
- Produces:

- `MemoryEngine.renew_chat_turn_lease(self, claim: ChatTurnClaim, *,
  observed_at: datetime) -> ChatTurnClaim`.
- `MemoryEngine.release_chat_turn(self, claim: ChatTurnClaim, *, observed_at:
  datetime) -> None`.

- Renewal returns a new immutable claim with the same request, IDs, owner token,
  and `resumed` flag, but with `lease_expires_at = observed_at + 120 seconds`.
- Renewal rejects completed, missing, mismatched-owner, or expired state with
  `ChatTurnOwnershipError` and no write.
- Release rejects a missing/completed/mismatched-owner turn with
  `ChatTurnOwnershipError`. For the matching owner it sets
  `lease_expires_at = observed_at` and `updated_at = SERVER_TIMESTAMP`.
- Releasing the same already-expired lease is idempotent and performs no write.

- [ ] **Step 1: Add and verify renewal RED tests**

Add:

```text
test_renew_chat_turn_lease_extends_matching_unexpired_owner
test_renew_chat_turn_lease_rejects_expired_owner_without_write
test_renew_chat_turn_lease_rejects_reclaimed_owner_without_write
test_renew_chat_turn_lease_validates_before_firestore_access
```

Run:

```bash
pytest -q tests/test_chat_turn_database.py -k renew_chat_turn
```

Expected: FAIL because `renew_chat_turn_lease` does not exist.

- [ ] **Step 2: Implement renewal transaction and verify GREEN**

Read the turn document before writing, parse its status/owner/expiry, enforce
the exact ownership rules, update only the lease fields, and return
`dataclasses.replace(claim, lease_expires_at=new_expiry)`.

Run the exact command from Step 1. Expected: all renewal tests pass.

- [ ] **Step 3: Add and verify release RED tests**

Add:

```text
test_release_chat_turn_expires_matching_lease
test_release_chat_turn_is_idempotent_when_same_lease_already_expired
test_release_chat_turn_rejects_reclaimed_owner_without_write
test_release_chat_turn_rejects_completed_turn_without_write
test_release_chat_turn_preserves_firestore_failure_as_cause
```

Run:

```bash
pytest -q tests/test_chat_turn_database.py -k release_chat_turn
```

Expected: FAIL because `release_chat_turn` does not exist.

- [ ] **Step 4: Implement release transaction and verify GREEN**

Use the same stored-state parser as renewal. Do not delete the turn or message
documents. Do not clear the owner token: retaining it makes a repeated release
recognizable until a new claim replaces ownership.

Run the exact command from Step 3. Expected: all release tests pass.

---

### Task 4: Atomic completion and durable replay state

**Files:**

- Modify: `database.py`
- Modify: `tests/test_chat_turn_database.py`

**Interfaces:**

- Consumes: `ChatTurnClaim` and validated `ChatResponse`.
- Produces:

- `MemoryEngine.complete_chat_turn(self, claim: ChatTurnClaim, response:
  ChatResponse, *, observed_at: datetime) -> None`.

- The transaction reads turn and model-message documents before any write.
- It requires in-progress state, exact owner token, and
  `lease_expires_at > observed_at`.
- An existing model-message document before completion is corruption and raises
  `ChatTurnStateError`.
- It writes the deterministic model message, validated receipt arrays, status,
  completion timestamps, and parent session timestamp atomically.
- It removes `lease_owner` and `lease_expires_at` using
  `firestore.DELETE_FIELD`.

- [ ] **Step 1: Write and verify the completion RED test**

Add:

```python
@pytest.mark.asyncio
async def test_complete_chat_turn_atomically_stores_response_and_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_chat_turn_store()
    response = ChatResponse(
        response="A durable answer.",
        actions=[],
        artifacts=[],
        citations=[],
        adaptations=[],
    )

    await MemoryEngine(store.client).complete_chat_turn(
        claim,
        response,
        observed_at=NOW + timedelta(seconds=1),
    )

    assert store.transaction.set.call_args_list == [
        call(
            store.session_ref,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(
            store.model_message_ref,
            {
                "role": "model",
                "text": response.response,
                "timestamp": firestore.SERVER_TIMESTAMP,
            },
        ),
        call(
            store.turn_ref,
            expected_completed_turn_update(response),
            merge=True,
        ),
    ]
```

Run:

```bash
pytest -q tests/test_chat_turn_database.py::test_complete_chat_turn_atomically_stores_response_and_receipts
```

Expected: FAIL because `complete_chat_turn` does not exist.

- [ ] **Step 2: Implement minimal completion and verify GREEN**

Serialize only `actions`, `artifacts`, `citations`, and `adaptations` into the
turn update using `response.model_dump(mode="json", exclude={"response"})`.
Write response text only to the model-message document.

Run the exact node from Step 1. Expected: PASS.

- [ ] **Step 3: Add RED ownership, corruption, and provider-error cases**

Add:

```text
test_complete_chat_turn_rejects_expired_lease_without_writes
test_complete_chat_turn_rejects_reclaimed_owner_without_writes
test_complete_chat_turn_rejects_completed_state_without_writes
test_complete_chat_turn_rejects_preexisting_model_message
test_complete_chat_turn_validates_response_before_firestore_access
test_complete_chat_turn_preserves_firestore_failure_as_cause
test_complete_chat_turn_failure_log_excludes_response_receipts_and_ids
test_completed_claim_reconstructs_exact_chat_response
test_completed_claim_rejects_invalid_stored_receipts
test_completed_claim_rejects_invalid_model_message
```

Run:

```bash
pytest -q tests/test_chat_turn_database.py -k "complete_chat_turn or completed_claim"
```

Expected: the new branches fail for their missing behavior.

- [ ] **Step 4: Implement minimal guards and replay parsing**

Use the shared stored-turn parser. Domain errors pass through unchanged;
Firestore `GoogleAPIError` alone is translated through
`_raise_firestore_error()`.

- [ ] **Step 5: Verify completion and replay tests are GREEN**

Run the exact command from Step 3. Expected: all selected tests pass.

---

### Task 5: Bounded history exclusion without ID exposure

**Files:**

- Modify: `database.py`
- Modify: `tests/test_database.py`

**Interfaces:**

- Extends the existing signature to:

- `MemoryEngine.get_chat_history(self, session_id: str, limit: int | None =
  None, *, exclude_message_id: str | None = None) -> list[dict[str, object]]`.

- Existing calls and return payloads remain unchanged.
- When `exclude_message_id` and `limit` are both supplied, Firestore receives
  `limit + 1`, snapshots with the matching document ID are skipped, and at most
  `limit` prior messages are returned chronologically.
- Document IDs never appear in returned dictionaries.
- `exclude_message_id` is validated before Firestore access.

- [ ] **Step 1: Write the bounded-exclusion RED test**

Add a test with 21 descending snapshots where the current user message is the
newest document and `limit=20`:

```python
history = await MemoryEngine(client).get_chat_history(
    "session-1",
    limit=20,
    exclude_message_id="turn--digest--user",
)

query.limit.assert_called_once_with(21)
assert len(history) == 20
assert [item["text"] for item in history] == expected_prior_texts
assert all("id" not in item and "message_id" not in item for item in history)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q tests/test_database.py -k chat_history
```

Expected: the new test fails because `get_chat_history()` does not accept
`exclude_message_id`; existing history tests remain green.

- [ ] **Step 3: Implement minimal exclusion behavior**

Validate the optional ID, request one extra document only when both exclusion
and a limit exist, skip by `snapshot.id`, slice to the requested bound, then
apply the existing chronological reversal.

- [ ] **Step 4: Verify all history tests are GREEN**

Run the exact command from Step 2. Expected: all selected tests pass.

---

### Task 6: Focused integration verification and manual handoff

**Files:**

- Verify only; no additional file is authorized unless a preceding RED/GREEN
  cycle proves it necessary within the approved persistence boundary.

**Interfaces:**

- Confirms all M6.2.1 primitives compose without changing `/api/chat`.

- [ ] **Step 1: Run pure and persistence-focused tests**

```bash
pytest -q tests/test_chat_turns.py tests/test_chat_turn_database.py tests/test_database.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Run directly affected trusted-memory database tests**

```bash
pytest -q tests/test_memory_approval_database.py tests/test_memory_rejection_database.py tests/test_memory_lifecycle_database.py
```

Expected: all tests pass. These protect the shared transaction and confirmation
provenance boundaries.

- [ ] **Step 3: Run static source validation**

```bash
python3 -m py_compile chat_turns.py database.py
```

Expected: exit code `0` with no output.

- [ ] **Step 4: Run whitespace validation**

```bash
git diff --check
```

Expected: exit code `0` with no output.

- [ ] **Step 5: Run the full suite because shared persistence changed**

```bash
pytest -q
```

Expected baseline: at least the existing 484 tests plus the new M6.2.1 tests
pass. The existing Google GenAI Pydantic warning may remain; no new warning,
failure, error, or skip is accepted.

- [ ] **Step 6: Report as implemented, pending manual verification**

The report must include exact RED failures, GREEN commands, changed files,
full-suite counts, and the following manual inspection targets:

1. run the unchanged health and headerless chat regression to prove no public
   route behavior changed;
2. inspect that no `sessions/{session_id}/turns` document was created by the
   headerless request, because M6.2.2 route integration is intentionally absent;
3. confirm existing Firestore chat and trusted-memory data remain readable.

No idempotent curl can succeed in M6.2.1 because FastAPI integration is outside
this pass. Claiming otherwise is a scope error.

- [ ] **Step 7: Wait for user acceptance before checkpointing**

Do not stage, commit, push, or begin M6.2.2 until the repository owner confirms
the manual regression targets passed and explicitly authorizes the next action.

## Initial RED execution order

The implementation must begin with these nodes, one cycle at a time:

```bash
pytest -q tests/test_chat_turns.py::test_derive_chat_turn_ids_hashes_key_and_bounds_message_ids
pytest -q tests/test_chat_turn_database.py::test_claim_chat_turn_atomically_creates_turn_and_user_message
pytest -q tests/test_chat_turn_database.py::test_renew_chat_turn_lease_extends_matching_unexpired_owner
pytest -q tests/test_chat_turn_database.py::test_release_chat_turn_expires_matching_lease
pytest -q tests/test_chat_turn_database.py::test_complete_chat_turn_atomically_stores_response_and_receipts
pytest -q tests/test_database.py -k bounded_history_excludes_current_message
```

Each test must fail for the stated missing behavior before its production code
is written. The implementer must not write the entire test file first and then
the entire production implementation; each listed boundary gets its own
RED-GREEN-REFACTOR cycle.

## Explicit exclusions for M6.2.1

- No `main.py` changes.
- No `schemas.py` changes.
- No `supervisor.py` or `supervisor_runtime.py` changes.
- No header parsing or HTTP error mapping.
- No live provider invocation.
- No smoke-runner creation.
- No Firestore TTL or cleanup policy.
- No authentication or ownership authorization.
- No checkpoint before manual acceptance.
