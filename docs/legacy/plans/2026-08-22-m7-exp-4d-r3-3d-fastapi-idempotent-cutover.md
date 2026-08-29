# M7-EXP.4D-R3.3D FastAPI and Idempotent Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline. Do not use
> subagents for this repository-owner-approved pass.

**Goal:** Cut the production `/api/chat` path over from the unrestricted
supervisor to the accepted model-controlled router, deterministic zero-or-one
expert executor, and responder-only Agent_Col runtime while preserving
FastAPI-owned persistence, governed memory, idempotency, and error semantics.

**Architecture:** FastAPI continues to claim or replay an idempotent turn,
load trusted context, persist the user message, apply any explicit memory
decision, and renew the lease. It then creates one `AgentColTurnCommand` and
calls the persistence-free `AgentColTurnService`. The service routes, executes
at most one read-only cognitive expert, and invokes responder-only Agent_Col.
FastAPI converts the returned result into `ChatResponse` and either saves the
headerless model message or atomically completes the claimed turn.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, Google Gen AI SDK, Google
ADK 2.7.0, Firestore AsyncClient, pytest, pytest-asyncio, httpx

**Spec:**
`docs/superpowers/specs/2026-08-21-phase-3b-m7-exp-4d-r3-3-production-routing-integration-design.md`

## Global constraints

- Work directly on `main` only because the repository owner explicitly
  approved this workflow; do not create a PR or feature branch.
- Follow RED, verify RED, GREEN, verify GREEN, and refactor for each behavior.
- Do not change Firestore schemas, dependencies, authentication, deployment,
  synthesis behavior, memory policy, expert contracts, or routing semantics.
- FastAPI remains authoritative for persistence, memory decisions,
  idempotency claims, lease renewal/release, atomic completion, and HTTP codes.
- `AgentColTurnService` remains persistence-free and receives no database or
  idempotency key.
- Agent_Col remains the routing decision-maker and final responder; the
  application executes only the validated route.
- At most one cognitive expert executes per turn and experts never call other
  experts.
- Completed idempotent replay must bypass routing, experts, and responder.
- The current unrestricted supervisor may remain in source as an unreferenced
  migration artifact, but it must not remain on the live request path.
- Do not log messages, URLs, identifiers, memory values, expert content,
  provider payloads, or model output.

## File map

- Modify `schemas.py`: add the dedicated bounded `ChatMessageText` alias and
  apply it only to `ChatRequest.message`.
- Modify `main.py`: compose the new turn boundary during lifespan, build
  `AgentColTurnCommand`, invoke it from `/api/chat`, map service failures, and
  preserve durable completion behavior.
- Modify `tests/test_main.py`: replace the live unrestricted-supervisor test
  seam with a turn-service seam and cover validation, composition, routing
  input projection, receipt persistence/replay, failure mapping, partial
  effects, and lease recovery.
- Create this plan only; do not add another production smoke runner unless the
  existing HTTP and pytest verification prove insufficient.

---

### Task 1: Bound chat messages at the HTTP schema

**Files:**
- Modify: `tests/test_main.py`
- Modify: `schemas.py`

**Interfaces:**
- Produces: `ChatMessageText`, a stripped string of length 1 through 10,000.
- Changes: `ChatRequest.message` from `NonEmptyStr` to `ChatMessageText`.
- Preserves: every other use of `NonEmptyStr`.

- [ ] **Step 1: Write the failing HTTP-boundary test**

Add a test that posts a 10,001-character message and asserts HTTP 422 plus
zero database, memory-service, or turn-service access. The production mutation
this catches is removing or bypassing the dedicated chat-message maximum.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_main.py::test_chat_rejects_oversized_message_before_service_access
```

Expected: FAIL because the current unbounded `NonEmptyStr` permits the
request to reach downstream work.

- [ ] **Step 3: Implement the minimal schema bound**

Add:

```python
ChatMessageText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=10_000,
    ),
]
```

Use it only for `ChatRequest.message`.

- [ ] **Step 4: Verify GREEN and the exact upper boundary**

Run the RED test plus a 10,000-character acceptance test. Assert normalized
text remains the value passed into the turn request fingerprint.

---

### Task 2: Compose the production turn service during lifespan

**Files:**
- Modify: `tests/test_main.py`
- Modify: `main.py`

**Interfaces:**
- Constructs: `ResearchExpertService.from_vertex_settings(vertex_settings)`.
- Constructs: `AgentColExpertExecutor(source_service=..., research_service=...)`.
- Constructs: responder-only `SupervisorRuntime.from_app(create_responder_app(...))`.
- Constructs: `AgentColTurnService(routing_client=client,
  expert_executor=..., responder_runtime=...)`.
- Exposes: `app.state.turn_service`.

- [ ] **Step 1: Write failing lifespan tests**

Tests must prove the shared Vertex client is used by synthesis, routing, and
Source; the validated settings create isolated Research and responder
runtimes; governed memory is injected only into the responder; the turn
service receives the exact dependencies; and `app.state.supervisor` is no
longer the production chat dependency.

- [ ] **Step 2: Verify RED**

Run the new lifespan tests and confirm they fail because `main.lifespan`
still constructs `create_supervisor_app()` and exposes `app.state.supervisor`.

- [ ] **Step 3: Implement minimal lifespan composition**

Replace the unrestricted-supervisor construction with the accepted Source,
Research, executor, responder-only runtime, and turn-service composition.
Preserve one shared application-owned `genai.Client`, one `MemoryEngine`, and
the existing shutdown behavior. Do not make startup provider calls.

- [ ] **Step 4: Verify GREEN**

Run the lifespan tests and the existing health, synthesis-lifespan, and
resource-construction-failure tests.

---

### Task 3: Cut `/api/chat` over to `AgentColTurnService`

**Files:**
- Modify: `tests/test_main.py`
- Modify: `main.py`

**Interfaces:**
- Consumes: `AgentColTurnCommand`.
- Produces: `AgentColTurnResult` converted to the existing `ChatResponse`.
- Preserves: existing user-message persistence, explicit memory-decision
  ordering, approved-context rendering, lease renewal, and completion.

- [ ] **Step 1: Write the failing command-construction test**

The test must post a chat turn with mixed user/model history and assert that
the turn service receives:

```text
project_id, session_id, user_id
current normalized message
recent_user_messages = only validated user-authored history in chronological order
approved model_input_context
source_message_id
memory_decision_present
turn_lease when claimed
precompleted actions and proposals when resumed
```

The production mutation this catches is passing full or model-authored history
into routing or dropping governed-memory/idempotency context.

- [ ] **Step 2: Verify RED**

Run the new test and confirm the old `supervisor.run_turn()` path fails the
expected turn-service call assertion.

- [ ] **Step 3: Implement the minimal cutover**

Retrieve `request.app.state.turn_service`, derive `recent_user_messages` from
the already validated bounded history, construct one `AgentColTurnCommand`,
and call `run_turn()` exactly once. Do not route in FastAPI and do not expose
model-authored messages as URL candidates.

- [ ] **Step 4: Verify GREEN**

Run the command-construction, headerless persistence, memory-decision, and
claimed-turn ordering tests.

---

### Task 4: Map service failures and preserve completed effects

**Files:**
- Modify: `tests/test_main.py`
- Modify: `main.py`

**Interfaces:**
- `AgentColTurnRoutingError` -> HTTP 502.
- `AgentColTurnRoutingTimeoutError` -> HTTP 504.
- `AgentColTurnResponderError` -> HTTP 502.
- `AgentColTurnTimeoutError` -> HTTP 504.
- Other safe `AgentColTurnServiceError` -> HTTP 502.
- All terminal owned-turn failures release the lease.
- Completed governed-memory actions continue to produce the existing partial
  failure response and remain recoverable from the turn ledger.

- [ ] **Step 1: Write parameterized failing error tests**

Cover every error class, headerless and claimed turns, lease release, absence
of model-message writes, safe log content, nested governed-memory domain
causes, and partial-effect recovery.

- [ ] **Step 2: Verify RED**

Confirm the tests fail because `main.py` currently catches only
`SupervisorRuntimeError` and `SupervisorTimeoutError`.

- [ ] **Step 3: Implement minimal error translation**

Generalize the existing receipt-aware partial-failure and nested-cause helpers
to the safe turn-service error surface. Preserve the current public error
details and do not log the underlying private provider or task data.

- [ ] **Step 4: Verify GREEN**

Run all new failure tests plus the existing memory-proposal conflict,
ownership, release-failure, and partial-failure tests.

---

### Task 5: Prove idempotent expert receipts and production restraint

**Files:**
- Modify: `tests/test_main.py`
- Modify: `main.py` only if a failing test reveals a missing approved behavior.

**Interfaces:**
- Completed replay returns the stored `ChatResponse` before turn-service
  access.
- Successful Source/Research actions and citations are written once through
  `complete_chat_turn()` and replay unchanged.
- Headerless success writes one user and one model message.
- A changed request under the same idempotency key remains HTTP 409.

- [ ] **Step 1: Write failing receipt/replay tests**

Use literal expected action and citation payloads. Assert the first claimed
request calls the turn service once and completes once; the replay calls
neither the turn service nor any context/database operation beyond claim; and
the stored response is byte-for-byte equivalent after JSON serialization.

- [ ] **Step 2: Verify RED**

Confirm the new turn-service receipt scenario fails against the old live
supervisor seam or incomplete cutover behavior.

- [ ] **Step 3: Implement only missing approved behavior**

Build `ChatResponse` from `AgentColTurnResult`, stably merge explicit decision
actions with service actions, and persist through the existing headerless or
idempotent completion branch. Do not add routing metadata to Firestore.

- [ ] **Step 4: Verify GREEN**

Run the receipt, replay, conflict, completion-order, and duplicate-write
regression tests.

---

### Task 6: Refactor tests and verify the complete cutover

**Files:**
- Modify: `tests/test_main.py`
- Modify: `main.py` only for behavior-neutral cleanup.

- [ ] **Step 1: Remove obsolete unrestricted-supervisor test assumptions**

Rename test fakes and assertions to the production `turn_service` boundary.
Retain tests for the lower-level `SupervisorRuntime` in its dedicated test
module because that runtime is still used by responder-only Agent_Col.

- [ ] **Step 2: Run focused verification**

```bash
venv/bin/pytest -q \
  tests/test_main.py \
  tests/test_agent_col_turn_service.py \
  tests/test_agent_col_expert_executor.py \
  tests/test_agent_col_responder.py \
  tests/test_agent_col_responder_context.py \
  tests/test_agent_col_routing.py \
  tests/test_agent_col_routing_provider.py \
  tests/test_supervisor_runtime.py
```

- [ ] **Step 3: Run full verification**

Run `venv/bin/pytest -q`. The full suite is required because `/api/chat`, the
shared lifespan, Pydantic request validation, Firestore idempotency, governed
memory, Source, Research, and responder runtime all meet at this cutover.

- [ ] **Step 4: Run static checks**

```bash
venv/bin/python -m py_compile main.py schemas.py
git diff --check
```

- [ ] **Step 5: Prepare manual runtime verification**

Provide single-line commands for health, direct restraint, Source execution,
exact idempotent replay, same-key conflict, and oversized input. Require a
manual Firestore inspection of the completed claimed turn and chat messages.
Do not checkpoint until the user confirms the live pass.

## Stop conditions

Stop and request a revised plan if implementation requires any of:

- a new dependency or external infrastructure;
- a Firestore document/schema migration;
- routing in FastAPI rather than through Agent_Col's structured directive;
- exposing cognitive experts to the responder-only ADK app;
- more than one expert execution per turn;
- persisting raw routing directives or expert content;
- altering the accepted memory policy or idempotency fingerprint;
- swallowing cancellation or retrying a logical expert/provider operation;
- a second live chat pipeline or fallback to the unrestricted supervisor.
