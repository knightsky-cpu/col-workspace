# Trusted Memory M6.2.2 FastAPI Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline. The repository
> owner has selected inline execution. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Integrate the accepted durable chat-turn primitives into the optional
`Idempotency-Key` branch of `POST /api/chat`, providing safe replay,
contention/conflict responses, deterministic memory-decision provenance, lease
renewal, atomic completion, and retryable provider-failure recovery while
preserving the existing headerless route.

**Architecture:** FastAPI remains the transport and orchestration boundary.
The route validates the optional header, asks `MemoryEngine` to arbitrate the
durable turn, returns completed replays before loading context, and otherwise
uses the claim's deterministic user-message ID throughout the existing memory
and supervisor flow. Immediately before the provider call it renews the lease;
after a successful typed response it atomically completes the turn, while a
handled provider failure attempts a safe best-effort lease release without
replacing the original `502` or `504`.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, asynchronous Firestore
adapter, pytest, pytest-asyncio, HTTPX ASGI transport.

**Spec:**
[`docs/superpowers/specs/2026-08-20-phase-3b-trusted-memory-m6-idempotency-design.md`](../specs/2026-08-20-phase-3b-trusted-memory-m6-idempotency-design.md)

## Global constraints

- This pass changes only FastAPI chat orchestration and its offline route
  tests. It does not change Firestore primitives, Pydantic request/response
  schemas, the supervisor runtime, smoke runners, deployment, or documentation
  outside this implementation plan.
- `Idempotency-Key` remains optional and transport-level. `ChatRequest` JSON is
  unchanged.
- A present key is validated by `validate_idempotency_key()` before Firestore,
  trusted-memory, supervisor, or provider access.
- A missing header follows the existing automatic-ID `save_message()` path.
- A completed replay returns its stored typed `ChatResponse` immediately and
  performs no profile, history, trusted-memory, supervisor, renewal,
  completion, or message-write call.
- A claimed turn does not call `save_message()` for either role. Claim already
  persisted the deterministic user message; completion atomically persists the
  deterministic model message.
- Idempotent history reads use `limit=20` and
  `exclude_message_id=claim.ids.user_message_id` so the current user message
  appears to Gemini only as `SupervisorTurnContext.message`.
- An optional memory decision uses the deterministic user-message ID as
  `confirmation_message_id` on first execution and every resume.
- The current owner renews its lease immediately before `supervisor.run_turn()`.
- `ChatTurnConflictError` maps to `409` with exactly
  `"Idempotency key conflicts with a different chat request."`.
- `ChatTurnInProgressError` maps to `409` with exactly
  `"Chat turn is already in progress."` and an integer `Retry-After` header.
- `ChatTurnOwnershipError` maps to `409` with exactly
  `"Chat turn ownership changed; retry with the same idempotency key."`.
- `ChatTurnStateError` maps to `500` with exactly
  `"Chat turn state is invalid."`.
- Invalid header values map to `422` with exactly
  `"Idempotency key is invalid."`.
- Firestore failures continue to map through `_raise_database_http_error()` to
  the existing safe `500` response.
- On `SupervisorRuntimeError` or `SupervisorTimeoutError`, an owned idempotent
  turn attempts `release_chat_turn()` before returning the existing `502` or
  `504`. Release failure is logged by exception class only and never replaces
  the provider-facing error.
- A failure during atomic completion is not followed by release. Firestore has
  an ambiguous commit boundary; retrying the same key must re-read durable
  state rather than guessing whether completion committed.
- No log or response may expose message text, response text, profile values,
  memory values, user/session/project/proposal/signal IDs, owner token, turn
  IDs, or the idempotency key.
- No dependencies are added.
- No intermediate Git commits are permitted. This repository checkpoints only
  after focused verification and explicit user manual acceptance.
- The full suite is required at the end because `/api/chat` is a shared public
  route and the change crosses validation, persistence, memory, supervisor,
  and response contracts.

## File structure

- Modify `main.py`: optional header binding, claim/replay/error translation,
  owned-turn history exclusion, deterministic confirmation provenance, lease
  renewal/release, and atomic completion orchestration.
- Modify `tests/test_main.py`: extend the existing deterministic service fake
  and add focused HTTP tests for every new branch and preserved headerless
  behavior.
- Do not modify `chat_turns.py`, `database.py`, `schemas.py`, or supervisor
  modules. If their accepted M6.2.1 interfaces prove insufficient, stop and
  present evidence instead of expanding this pass.

---

### Task 1: Optional header, durable claim, safe replay, and claim errors

**Files:**

- Modify: `tests/test_main.py:1-1600`
- Modify: `main.py:1-467`

**Interfaces:**

- Consumes from `chat_turns.py`:

```python
class ChatTurnConflictError(RuntimeError): ...
class ChatTurnInProgressError(RuntimeError):
    retry_after_seconds: int
class ChatTurnOwnershipError(RuntimeError): ...
class ChatTurnStateError(RuntimeError): ...

@dataclass(frozen=True, slots=True)
class ChatTurnRequest:
    project_id: str
    session_id: str
    user_id: str
    message: str
    memory_decision: MemoryDecisionRequest | None = None

@dataclass(frozen=True, slots=True)
class ChatTurnClaim: ...

@dataclass(frozen=True, slots=True)
class ChatTurnReplay:
    response: ChatResponse

def validate_idempotency_key(value: object) -> str: ...
```

- Consumes from `MemoryEngine`:

```python
async def claim_chat_turn(
    self,
    request: ChatTurnRequest,
    *,
    idempotency_key: str,
    observed_at: datetime,
) -> ChatTurnClaim | ChatTurnReplay: ...
```

- Produces the transport signature:

```python
@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
) -> ChatResponse: ...
```

- [ ] **Step 1: Extend the existing route fake without changing production**

Add typed fake state for `chat_turn_result`, `chat_turn_error`,
`renewed_claim`, `renew_error`, `release_error`, and `complete_error`. Extend
`FakeMemoryEngine.get_chat_history()` with the accepted keyword-only
`exclude_message_id: str | None = None`; preserve the existing three-item
history event when exclusion is absent and record
`("history", session_id, limit, exclude_message_id)` only when it is present.
Add fake `claim_chat_turn()`, `renew_chat_turn_lease()`,
`release_chat_turn()`, and `complete_chat_turn()` methods that append bounded
event names and typed arguments without logging raw keys or owner tokens.

- [ ] **Step 2: Write the invalid-header RED test**

Add `test_chat_rejects_invalid_idempotency_key_before_service_access`,
parameterized with `"bad/key"`, `"bad.key"`, `"contains space"`, `"bad$key"`,
and `"a" * 129`. Send otherwise valid JSON plus `Idempotency-Key`. Assert `422`,
`{"detail": "Idempotency key is invalid."}`, no service events, no memory
decision calls, and no supervisor calls.

- [ ] **Step 3: Verify invalid-header RED**

Run:

```bash
venv/bin/pytest -q tests/test_main.py::test_chat_rejects_invalid_idempotency_key_before_service_access
```

Expected: five failures because the route does not bind or validate the
header and proceeds into the existing chat flow.

- [ ] **Step 4: Bind and validate the optional header minimally**

Import `Annotated`, `UTC`, `datetime`, `Header`, and
`validate_idempotency_key`. Add the exact endpoint parameter above. When the
header is present, validate it in a `try` block; translate `ValueError` to the
exact safe `422` detail. Do not claim or otherwise change the route yet.

- [ ] **Step 5: Verify invalid-header GREEN and headerless regression**

Run:

```bash
venv/bin/pytest -q \
  tests/test_main.py::test_chat_rejects_invalid_idempotency_key_before_service_access \
  tests/test_main.py::test_chat_uses_context_and_persists_both_messages
```

Expected: six passes. The existing headerless test must still record one user
save and one model save.

- [ ] **Step 6: Write completed-replay RED**

Add `test_chat_replays_completed_idempotent_turn_without_downstream_access`.
Configure the fake claim result as `ChatTurnReplay` containing a non-empty
`ChatResponse` with action, artifact, citation, and adaptation receipts. Send a
valid header. Assert exact `200` JSON equality and that the only service event
is `("claim_chat_turn",)`; profile, history, trusted memory, renewal,
supervisor, completion, and `save_message()` must not run.

- [ ] **Step 7: Verify completed-replay RED**

Run:

```bash
venv/bin/pytest -q tests/test_main.py::test_chat_replays_completed_idempotent_turn_without_downstream_access
```

Expected: FAIL because the route does not call `claim_chat_turn()` and invokes
the current context/supervisor/write path.

- [ ] **Step 8: Implement claim construction and immediate replay**

Construct `ChatTurnRequest` from all five request-identity fields without
normalizing any field. Call `claim_chat_turn()` with the validated key and
`datetime.now(UTC)`. Return `ChatTurnReplay.response` immediately. Retain a
typed `ChatTurnClaim | None` for an owned turn; leave the remainder of owned
execution for Task 2.

- [ ] **Step 9: Verify replay GREEN**

Run the exact node from Step 7. Expected: PASS with only the claim event.

- [ ] **Step 10: Write claim-error RED tests**

Add `test_chat_translates_idempotent_claim_errors_without_downstream_access`,
parameterized over:

- `ChatTurnConflictError` -> `409`, exact conflict detail, no special header;
- `ChatTurnInProgressError(17)` -> `409`, exact in-progress detail,
  `Retry-After: 17`;
- `ChatTurnStateError` -> `500`, exact invalid-state detail;
- `MemoryEngineError` -> existing `500`, `"Database operation failed."`.

Assert each request stops after the claim attempt and all logs exclude unique
private message, key, user, session, project, and exception-text markers.

- [ ] **Step 11: Verify claim-error RED**

Run:

```bash
venv/bin/pytest -q tests/test_main.py::test_chat_translates_idempotent_claim_errors_without_downstream_access
```

Expected: failures because claim domain errors are not translated to the
approved HTTP contract.

- [ ] **Step 12: Implement focused claim-error translation and verify GREEN**

Catch the four approved errors around the claim call. Return the exact safe
details from Global Constraints, set `headers={"Retry-After":
str(exc.retry_after_seconds)}` only for active ownership, and log state failure
by exception class only. Rerun Task 1's three focused test nodes together; all
must pass.

---

### Task 2: Owned-turn context, deterministic memory provenance, renewal, and completion

**Files:**

- Modify: `tests/test_main.py:1-1700`
- Modify: `main.py:311-500`

**Interfaces:**

- Consumes from `MemoryEngine`:

```python
async def get_chat_history(
    self,
    session_id: str,
    limit: int | None = None,
    *,
    exclude_message_id: str | None = None,
) -> list[dict[str, object]]: ...

async def renew_chat_turn_lease(
    self,
    claim: ChatTurnClaim,
    *,
    observed_at: datetime,
) -> ChatTurnClaim: ...

async def complete_chat_turn(
    self,
    claim: ChatTurnClaim,
    response: ChatResponse,
    *,
    observed_at: datetime,
) -> None: ...
```

- Produces no new public type. It assembles one `ChatResponse` before either
  atomic completion or the existing headerless model save.

- [ ] **Step 1: Write ordinary owned-turn RED**

Add `test_chat_completes_claimed_turn_without_duplicate_message_writes`.
Configure a valid `ChatTurnClaim`. Assert:

- claim occurs before context reads;
- profile and history begin concurrently;
- history receives `limit=20` and the deterministic user-message exclusion;
- the supervisor context contains prior history but not the current message;
- renewal occurs immediately before the supervisor event;
- `complete_chat_turn()` receives the renewed claim and the exact typed
  `ChatResponse` returned over HTTP;
- neither user nor model `save_message()` is called.

- [ ] **Step 2: Verify ordinary owned-turn RED**

Run:

```bash
venv/bin/pytest -q tests/test_main.py::test_chat_completes_claimed_turn_without_duplicate_message_writes
```

Expected: FAIL because the current route uses automatic message writes, does
not exclude the deterministic user message, and does not renew or complete.

- [ ] **Step 3: Implement the minimum owned-turn branch**

For a claim:

1. set `user_message_id = claim.ids.user_message_id` instead of calling
   `save_message()`;
2. pass `exclude_message_id=user_message_id` to each applicable history read;
3. keep the existing concurrent profile/history load for ordinary turns;
4. keep the current sequential history then memory-decision order for
   decision turns;
5. renew the claim with `datetime.now(UTC)` immediately before the supervisor;
6. build `ChatResponse` once from the supervisor result and server-derived
   receipts;
7. call `complete_chat_turn(renewed_claim, chat_response,
   observed_at=datetime.now(UTC))`;
8. return that same typed response.

For a missing header, retain existing user/model `save_message()` calls and
the exact current ordering.

- [ ] **Step 4: Verify ordinary owned-turn GREEN and headerless compatibility**

Run:

```bash
venv/bin/pytest -q \
  tests/test_main.py::test_chat_completes_claimed_turn_without_duplicate_message_writes \
  tests/test_main.py::test_chat_uses_context_and_persists_both_messages \
  tests/test_main.py::test_chat_starts_context_reads_concurrently
```

Expected: three passes. Headerless event ordering and concurrent reads remain
unchanged.

- [ ] **Step 5: Write deterministic memory-decision RED**

Add `test_chat_idempotent_decision_uses_deterministic_confirmation_message_id`.
Configure an approval claim and approved memory result. Assert the memory
service receives one `MemoryDecisionCommand` whose confirmation message is
`claim.ids.user_message_id`, the owned-turn history excludes that same ID, the
response includes the decision action and resulting adaptation receipt, and
completion receives that exact response. Assert no automatic message saves.

- [ ] **Step 6: Verify memory-decision RED then GREEN**

Run:

```bash
venv/bin/pytest -q tests/test_main.py::test_chat_idempotent_decision_uses_deterministic_confirmation_message_id
```

Expected before implementation: FAIL because the current route receives the
automatic `user-message-1`. After Step 3, expected: PASS with the deterministic
ID and one completion.

- [ ] **Step 7: Write renewal/completion error RED tests**

Add `test_chat_translates_owned_turn_persistence_errors_safely`, parameterized
over:

- renewal `ChatTurnOwnershipError` -> approved `409` ownership detail;
- completion `ChatTurnOwnershipError` -> approved `409` ownership detail;
- renewal or completion `ChatTurnStateError` -> approved safe `500` state
  detail;
- renewal or completion `MemoryEngineError` -> existing safe database `500`.

Assert renewal errors prevent supervisor and completion; completion errors
occur after one supervisor call; no automatic message saves occur; and logs
exclude all unique request, key, owner, response, and exception-text markers.

- [ ] **Step 8: Verify renewal/completion error RED**

Run:

```bash
venv/bin/pytest -q tests/test_main.py::test_chat_translates_owned_turn_persistence_errors_safely
```

Expected: failures because ownership and state errors are not yet translated
around renewal and completion.

- [ ] **Step 9: Implement one safe turn-operation translator**

Add a private helper that translates `ChatTurnOwnershipError`,
`ChatTurnStateError`, and `MemoryEngineError` to the exact safe details in
Global Constraints. Log only the operation category and exception class. Use
it around renewal and completion. Do not release after a completion error.

- [ ] **Step 10: Verify Task 2 GREEN**

Run all four focused Task 2 nodes. Expected: all parameter cases and direct
tests pass without unexplained warnings.

---

### Task 3: Provider-failure lease release without error masking

**Files:**

- Modify: `tests/test_main.py:1-1800`
- Modify: `main.py:100-500`

**Interfaces:**

- Consumes from `MemoryEngine`:

```python
async def release_chat_turn(
    self,
    claim: ChatTurnClaim,
    *,
    observed_at: datetime,
) -> None: ...
```

- Produces:

```python
async def _release_chat_turn_safely(
    database: MemoryEngine,
    claim: ChatTurnClaim,
) -> None: ...
```

The helper catches `MemoryEngineError`, `ChatTurnOwnershipError`,
`ChatTurnStateError`, and `ValueError`, logs only the exception class, and
returns without raising so it cannot mask the provider error.

- [ ] **Step 1: Write provider-failure release RED tests**

Add `test_chat_releases_claim_after_supervisor_failure`, parameterized over
`SupervisorRuntimeError` and `SupervisorTimeoutError`. Configure a valid claim.
Assert exact existing `502`/`504` response bodies, one renewal, one supervisor
attempt, one release using the renewed claim, no completion, and no automatic
message saves.

- [ ] **Step 2: Verify provider-failure release RED**

Run:

```bash
venv/bin/pytest -q tests/test_main.py::test_chat_releases_claim_after_supervisor_failure
```

Expected: FAIL because the owned lease is not released.

- [ ] **Step 3: Implement best-effort release and verify GREEN**

Add `_release_chat_turn_safely()` with `datetime.now(UTC)`. Await it in both
existing supervisor exception branches only when a claim exists, before
raising the original HTTP exception. Rerun Step 2; both parameter cases must
pass.

- [ ] **Step 4: Write release-failure non-masking RED**

Add `test_chat_release_failure_does_not_replace_supervisor_error`. Configure a
private runtime-error marker and a separate private release-error marker.
Assert the HTTP result remains the original `502`, release was attempted once,
completion did not run, and neither marker nor any request/key/owner ID appears
in logs.

- [ ] **Step 5: Verify release-failure RED then GREEN**

Run:

```bash
venv/bin/pytest -q tests/test_main.py::test_chat_release_failure_does_not_replace_supervisor_error
```

Expected before helper exception handling: FAIL because release replaces the
provider error or escapes. After catching the four bounded release failures,
expected: PASS with the original `502` intact.

- [ ] **Step 6: Refactor only after all focused tests are green**

Keep claim/replay, owned completion, and headerless behavior visually distinct
inside `chat()`. Extract only the two error/release helpers required above; do
not introduce a service layer, route class, middleware, or general workflow
framework in this pass.

---

### Task 4: Focused regression and full contract verification

**Files:**

- Verify: `main.py`
- Verify: `tests/test_main.py`
- Verify unchanged shared contracts: `chat_turns.py`, `database.py`,
  `schemas.py`, `supervisor_runtime.py`, `trusted_memory_service.py`

- [ ] **Step 1: Run all idempotent route tests**

Run:

```bash
venv/bin/pytest -q tests/test_main.py -k "idempotent or idempotency or owned_turn or releases_claim or release_failure"
```

Expected: all selected tests pass with no unexplained warning.

- [ ] **Step 2: Run the complete FastAPI route module**

Run:

```bash
venv/bin/pytest -q tests/test_main.py
```

Expected: all route, lifecycle, synthesis, memory-inspection, and existing chat
tests pass. The existing ADK `BaseAgentConfig` deprecation warning may remain;
no new warning is accepted.

- [ ] **Step 3: Run accepted turn and persistence contracts**

Run:

```bash
venv/bin/pytest -q \
  tests/test_chat_turns.py \
  tests/test_chat_turn_database.py \
  tests/test_database.py
```

Expected: all M6.2.1 domain/persistence and bounded-history tests remain green.

- [ ] **Step 4: Run the full suite because the route crosses shared contracts**

Run:

```bash
venv/bin/pytest -q
```

Expected: all tests pass. Record the exact count, warning count, skipped tests,
and exit code rather than inferring success.

- [ ] **Step 5: Run static diff checks**

Run:

```bash
venv/bin/python -m py_compile main.py tests/test_main.py
git diff --check
git status --short
```

Expected: compile and whitespace checks exit `0`; status shows only the
approved `main.py`, `tests/test_main.py`, and this plan document.

- [ ] **Step 6: Stop at implemented, pending manual verification**

Do not commit or push. Report exact TDD RED/GREEN evidence, test results,
limitations, the manual commands below, and the proposed M6.2.3 boundary.

## Manual runtime acceptance targets

Use a fresh key and a fresh session so earlier Firestore data cannot produce a
false pass.

1. Start `uvicorn main:app --reload` in the activated virtual environment.
2. Send a valid chat request with a fresh `Idempotency-Key`; expect `200` with
   a complete `ChatResponse`.
3. Repeat the identical header and JSON body; expect the exact same JSON and no
   second provider invocation in the application log.
4. Reuse the key with changed message text; expect `409` with
   `"Idempotency key conflicts with a different chat request."`.
5. Send the existing headerless chat curl; expect the unchanged `200` path.
6. Inspect Firestore and confirm the idempotent session contains one turn
   document, one deterministic user-message document, and one deterministic
   model-message document. Confirm the turn is `completed` and does not contain
   raw chat text or the raw key.
7. Confirm the replay and conflict attempts add no messages and do not mutate
   the completed turn.

Firestore console:
[project-e1e2a890-4566-48a8-a32](https://console.cloud.google.com/firestore/databases/-default-/data/panel/sessions?project=project-e1e2a890-4566-48a8-a32)

## Known exclusions and stop conditions

- A deterministic live failure/retry smoke runner and reproducibility docs are
  M6.2.3, not this pass.
- Authentication, authorization, rate limiting, retention, and TTL remain
  deferred by the accepted design.
- The system does not claim exactly-once Gemini execution across the crash
  window after provider completion and before durable completion.
- The implementation releases leases only for handled supervisor `502`/`504`
  failures as specified. It does not broaden release behavior to validation,
  memory-domain, context, or ambiguous persistence failures.
- If M6.2.1 interfaces cannot express the route contract without modification,
  stop before editing those modules and present the exact mismatch for a
  revised approval.
- If an existing headerless test changes event order, response JSON, or error
  translation, treat that as a regression rather than updating the test.

## Proposed next pass

- **M6.2.3 live reliability evidence and documentation:** add a deterministic
  smoke runner for new/replay/conflict paths, document exact terminal and
  Firestore verification, record the honest delivery guarantee, and update
  local setup/testing/troubleshooting/API documentation. No production
  behavior change is included unless live M6.2.2 evidence first proves a
  separate defect and the user approves its focused correction.
