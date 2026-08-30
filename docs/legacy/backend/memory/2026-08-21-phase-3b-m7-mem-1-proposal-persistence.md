# Phase 3B M7-MEM.1 Proposal Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, source-message-guarded trusted-memory proposal
service and atomic Firestore persistence boundary without registering an ADK
tool or changing the public chat route.

**Architecture:** A small pure `memory_proposals.py` module derives versioned
origin and proposal IDs and defines the optional idempotent-turn lease. The
`TrustedMemoryService` validates untrusted category/value input and
current-message grounding before calling one new `MemoryEngine` transaction.
That transaction reads the origin, category slot, root profile, and optional
turn document before writing the proposal, origin guard, and identical turn
effect atomically.

**Tech Stack:** Python 3.14, Pydantic v2, `google-cloud-firestore==2.28.1`,
pytest, pytest-asyncio.

**Spec:**
[`docs/superpowers/specs/2026-08-21-phase-3b-trusted-memory-m7-governed-proposal-tool-design.md`](2026-08-21-phase-3b-trusted-memory-m7-governed-proposal-tool-design.md)

## Global constraints

- No `supervisor.py`, `supervisor_runtime.py`, `main.py`, ADK registration,
  public `ChatResponse`, or expert-capability change belongs in this pass.
- Firestore remains the sole durable collaboration-memory source.
- The model never selects user, session, source-message, proposal, origin,
  timestamp, lease, provenance, or persistence identifiers.
- One transaction reads every required document before its first write.
- The origin guard stores no proposed value or raw message text.
- Preferred names must be grounded in the current source message.
- An existing active value is a typed no-op and performs no write.
- Identical retry returns the original stored proposal and expiry.
- Changed origin/category/value or turn effect conflicts without mutation.
- Logs exclude messages, values, identifiers, turn keys, provider payloads,
  and Firestore details.
- Existing proposal approval, rejection, correction, revocation, deletion,
  inspection, chat-turn persistence, and replay behavior must remain green.
- Production behavior must follow verified RED → GREEN cycles.

---

### Task 1: Deterministic proposal identity and receipt schema

**Files:**

- Create: `memory_proposals.py`
- Modify: `schemas.py`
- Test: `tests/test_memory_proposal_ids.py`
- Test: `tests/test_memory_schemas.py`

**Interfaces:**

- Produces `ProposalOriginIds(origin_id: str, proposal_id: str)`.
- Produces `ProposalTurnLease(turn_id: str, owner_token: str)`.
- Produces `derive_proposal_origin_ids(user_id, session_id,
  source_message_id, category) -> ProposalOriginIds`.
- Adds `propose_memory_signal` to `AgentActionReceipt.action_name`.
- Reuses the existing `MemoryProposalReceipt` schema.

- [ ] **Step 1: Write failing deterministic-ID and action-schema tests**

Use hand-derived SHA-256 literals for a fixed user/session/message/category.
Assert domain separation, 32 lowercase hexadecimal origin IDs, category-bound
proposal IDs, strict identifier validation, and acceptance of the new action
name.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q tests/test_memory_proposal_ids.py tests/test_memory_schemas.py::test_agent_action_receipt_accepts_governed_proposal_action
```

Expected: import or literal-validation failure because the helper and action
name do not exist.

- [ ] **Step 3: Implement the pure helper and schema literal**

The digest input is exactly:

```text
memory-proposal-origin-v1\0{user_id}\0{session_id}\0{source_message_id}
```

The origin ID is the first 32 lowercase hexadecimal digest characters and the
proposal ID is `{category}--{origin_id}`. Validate every input before hashing.

- [ ] **Step 4: Verify GREEN**

Run the exact focused command from Step 2 and require all tests to pass.

### Task 2: Trusted-memory proposal service validation

**Files:**

- Modify: `trusted_memory_service.py`
- Create: `tests/test_memory_proposal_service.py`

**Interfaces:**

- Produces immutable `ProposeMemorySignalCommand` with server-owned source
  context, untrusted category/value, and optional `ProposalTurnLease`.
- Produces immutable `TrustedMemoryProposalResult` containing one completed
  action and one `MemoryProposalReceipt`.
- Produces `TrustedMemoryService.propose_memory_signal(command)`.
- Consumes `MemoryEngine.create_guarded_memory_proposal(...)` from Task 3.

- [ ] **Step 1: Write failing service tests**

Test valid normalized preference, grounded preferred name, normalized broad
roles, invalid category/value before database access, ungrounded preferred
name before access, invalid server identifiers before access, and rejection
when `memory_decision_present` is true.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q tests/test_memory_proposal_service.py
```

Expected: import or attribute failure because the command, result, and service
method do not exist.

- [ ] **Step 3: Implement minimum service behavior**

Validate identifiers and source text, require a real Boolean decision flag,
normalize values with `validate_memory_value`, use
`IdentityContextPolicy.validate(..., require_grounding=True)` for preferred
names, derive IDs, obtain one clock value, call the database once, and build
receipts only from the stored proposal result.

- [ ] **Step 4: Verify GREEN**

Run the exact focused command from Step 2 and require all tests to pass.

### Task 3: Atomic origin-guarded proposal transaction

**Files:**

- Modify: `database.py`
- Create: `tests/test_memory_proposal_guard_database.py`

**Interfaces:**

- Produces `MemoryEngine.create_guarded_memory_proposal(...) ->
  MemoryProposal`.
- Produces typed `MemoryProposalOriginConflictError`,
  `MemoryProposalStateError`, and `MemorySignalAlreadyActiveError`.
- Consumes validated IDs, normalized value, source locators, timestamp, and an
  optional `ProposalTurnLease`.

- [ ] **Step 1: Write failing transaction happy-path test**

Use complete Firestore reference and snapshot fakes. Assert read order:
origin, category slot, root profile, then optional turn; assert no write occurs
before all reads. Assert proposal `expected_signal_id` comes from the active
profile and the origin document contains identifiers but no value or message.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q tests/test_memory_proposal_guard_database.py::test_guarded_proposal_reads_all_state_before_atomic_writes
```

Expected: attribute failure because the guarded method does not exist.

- [ ] **Step 3: Implement minimum happy-path transaction**

Validate arguments before client access, build all references, perform every
read, parse the root profile, derive the active signal, construct the pending
proposal, and set the proposal and origin documents in one transaction.

- [ ] **Step 4: Verify GREEN**

Run the exact focused command from Step 2.

- [ ] **Step 5: RED/GREEN active no-op and category conflict**

Add tests proving identical active value raises the typed no-op with no write,
while a different unexpired category proposal preserves the existing category
conflict with no mutation. Implement only those branches and rerun the file.

- [ ] **Step 6: RED/GREEN identical and changed origin retries**

Add tests proving an exact origin/proposal retry returns the stored timestamps
without writes and changed category, value, proposal identity, or malformed
stored state raises a typed conflict/state error without mutation. Implement
the minimal comparison and rerun the file.

- [ ] **Step 7: RED/GREEN safe Firestore translation**

Add a provider failure containing private values. Require
`MemoryEngineError.__cause__` preservation and content-free logs. Implement
translation through the established `_raise_firestore_error` boundary.

### Task 4: Idempotent turn-effect persistence

**Files:**

- Modify: `database.py`
- Modify: `tests/test_memory_proposal_guard_database.py`
- Run regressions: `tests/test_chat_turn_database.py`

**Interfaces:**

- Consumes optional `ProposalTurnLease`.
- Stores one `propose_memory_signal` action and one `MemoryProposalReceipt` on
  an owned, unexpired, in-progress turn in the proposal transaction.

- [ ] **Step 1: Write failing owned-turn effect test**

Assert the transaction validates turn status, user, source message, owner, and
expiry and writes the exact action/receipt arrays in the same transaction as
the proposal and origin.

- [ ] **Step 2: Verify RED**

Run the named new test and confirm the turn document is not updated.

- [ ] **Step 3: Implement minimum turn validation and write**

Preserve existing unrelated action entries, reject malformed effect arrays,
and write the new receipt with `merge=True` only after every read succeeds.

- [ ] **Step 4: Verify GREEN**

Run the named test and `pytest -q tests/test_chat_turn_database.py`.

- [ ] **Step 5: RED/GREEN ownership and effect conflicts**

Add table-driven cases for expired lease, changed owner, wrong user/source,
identical precompleted effect, and differing precompleted effect. Require zero
writes on every conflict and no write for an already-identical effect.

### Task 5: Origin lifecycle cleanup

**Files:**

- Modify: `database.py`
- Modify: `tests/test_memory_lifecycle_database.py`

**Interfaces:**

- Extends `delete_memory_signal()` to derive a version-1 origin ID from a
  `{category}--{32 lowercase hex}` signal and delete an owned matching origin
  guard atomically.
- Preserves historical signals without version-1 origin suffixes.

- [ ] **Step 1: Write failing origin-cleanup test**

Arrange a signal with a version-1 origin suffix and matching origin document.
Assert the origin is read before writes and deleted with the proposal/events.

- [ ] **Step 2: Verify RED**

Run the named lifecycle test and confirm the origin reference is untouched.

- [ ] **Step 3: Implement minimum bounded cleanup**

Read the deterministic origin document only for a valid version-1 suffix,
validate its proposal/category ownership, include it in `artifacts_deleted`,
and delete it atomically. Do not query the origin collection.

- [ ] **Step 4: Verify GREEN and historical compatibility**

Run:

```bash
pytest -q tests/test_memory_lifecycle_database.py
```

### Task 6: Live Firestore smoke runner

**Files:**

- Create: `smoke_test_memory_proposal_persistence.py`
- Create: `tests/test_smoke_test_memory_proposal_persistence.py`

**Interfaces:**

- Produces `run_proposal_persistence_smoke(...)` with injectable engine,
  clock, and ID source.
- CLI creates a new pending proposal, retries it identically, verifies the
  first expiry is preserved, and prints identifiers required for manual
  Firestore inspection.

- [ ] **Step 1: Write failing smoke-runner behavior test**

Use a fake engine to assert one service command, one identical retry, equal
proposal IDs/expiries, and a bounded summary that excludes the proposed value
and source text.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q tests/test_smoke_test_memory_proposal_persistence.py
```

Expected: import failure because the runner does not exist.

- [ ] **Step 3: Implement the runner and verify GREEN**

Use `MemoryEngine` and `TrustedMemoryService` in the CLI path. Do not call
Gemini or ADK. Print a one-line command result and close the engine in
`finally`.

### Task 7: Focused regression verification

**Files:** all files changed above.

- [ ] **Step 1: Run focused M7-MEM.1 tests**

```bash
pytest -q \
  tests/test_memory_proposal_ids.py \
  tests/test_memory_proposal_service.py \
  tests/test_memory_proposal_guard_database.py \
  tests/test_smoke_test_memory_proposal_persistence.py
```

- [ ] **Step 2: Run related shared-contract regressions**

```bash
pytest -q \
  tests/test_memory_schemas.py \
  tests/test_memory_database.py \
  tests/test_memory_lifecycle_database.py \
  tests/test_chat_turn_database.py \
  tests/test_memory_approval_database.py
```

- [ ] **Step 3: Run static validation**

```bash
venv/bin/python -m py_compile \
  memory_proposals.py \
  trusted_memory_service.py \
  database.py \
  smoke_test_memory_proposal_persistence.py
git diff --check
```

- [ ] **Step 4: Stop for manual acceptance**

Do not commit. Report as **implemented, pending manual verification** and give
the exact smoke command, expected summary, Firestore paths, and regression
boundary. Checkpoint only after the repository owner confirms the live smoke
and manual Firestore inspection.
