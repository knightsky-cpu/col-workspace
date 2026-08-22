# M7-EXP.4D-R3.3C Turn Orchestration Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline. Do not use
> subagents for this repository-owner-approved pass.

**Goal:** Compose the accepted structured router, deterministic expert
executor, bounded responder context, and responder-only Agent_Col runtime
behind one persistence-free `AgentColTurnService`, with one 90-second outer
deadline and a protected 20-second responder reserve, without changing the
live `/api/chat` path.

**Architecture:** Add one application service that receives an already
validated, persistence-independent turn command. It projects the minimal
routing input, requests exactly one locally validated routing directive,
executes zero or one selected expert, appends one server-validated responder
context block, invokes the responder-only runtime, and returns a merged result.
The service owns cognitive orchestration only. FastAPI retains HTTP,
Firestore, memory-decision, idempotency, and durable completion authority.

**Tech Stack:** Python 3.14, Pydantic v2, Google Gen AI SDK, Google ADK 2.7.0,
`asyncio`, pytest, pytest-asyncio

**Spec:**
`docs/superpowers/specs/2026-08-21-phase-3b-m7-exp-4d-r3-3-production-routing-integration-design.md`

## Verified current boundaries

- `request_agent_col_routing_directive()` already performs one tool-free
  structured Vertex request, locally validates `AgentColRoutingDirective`,
  and accepts an explicit provider timeout.
- `project_routing_url_candidates()` already projects at most eight unique,
  public HTTP(S) URLs from the current message followed by newest user-authored
  history.
- `AgentColExpertExecutor.execute()` already revalidates a directive against
  its exact routing input, invokes zero experts for `direct`/`clarify`, invokes
  exactly one selected Source or Research service otherwise, contains expected
  expert failures as content-free results, and never falls back to another
  expert.
- `build_agent_col_responder_model_context()` already renders one strict,
  bounded, server-validated routing/expert context block that excludes the
  current user message and server identifiers.
- `SupervisorRuntime.run_turn()` already provides the responder invocation
  session lifecycle, sends the original message once as ADK `new_message`,
  preserves precompleted memory effects, validates new memory-proposal
  receipts, and deletes its temporary session in `finally`.
- The accepted responder-only app exposes governed memory proposal as its only
  optional model-visible tool. Its cognitive expert trackers are inert because
  neither Source nor Research is reachable from that app.
- `SupervisorRuntime` has its own 90-second safety timeout. R3.3C will wrap it
  in the *remaining* outer-turn budget; the smaller outer remainder is
  authoritative, so changing the established runtime is unnecessary.
- `main._merge_receipts()` implements stable equality-based deduplication. The
  turn service needs the same behavior internally, but R3.3C will not move or
  delete the live helper because `/api/chat` cutover belongs to R3.3D.

## Command-contract clarification

The accepted design sketch lists task and memory-effect fields but omits the
three server identifiers required by the existing responder runtime. That
runtime needs `project_id`, `session_id`, and `user_id` to create its temporary
ADK invocation state and to bind the governed memory-proposal tool safely.

R3.3C will therefore make those three validated identifiers explicit fields of
`AgentColTurnCommand`. This is not permission to expose them to the routing
provider or cognitive experts:

```text
AgentColTurnCommand
  project_id                 responder runtime only
  session_id                 responder runtime only
  user_id                    responder runtime only
  message                    routing current_message + ADK new_message
  recent_user_messages       URL projection only
  model_input_context        responder runtime only
  source_message_id          governed memory context only
  memory_decision_present    governed memory context only
  turn_lease                 governed memory context only
  precompleted_actions       responder/runtime receipt recovery only
  precompleted_memory_proposals
```

The constructed `AgentColRoutingInput` remains exactly:

```text
current_message
candidate_urls
available_capabilities
```

It receives no identifier, profile, approved memory value, full history,
model-authored URL, source-message ID, lease, idempotency key, Firestore
object, or precompleted effect.

## Public interfaces

Create in `agent_col_turn_service.py`:

```python
@dataclass(frozen=True, slots=True)
class AgentColTurnCommand:
    project_id: str
    session_id: str
    user_id: str
    message: str
    recent_user_messages: tuple[str, ...] = ()
    model_input_context: tuple[types.Content, ...] = ()
    source_message_id: str | None = None
    memory_decision_present: bool = False
    turn_lease: ProposalTurnLease | None = None
    precompleted_actions: tuple[AgentActionReceipt, ...] = ()
    precompleted_memory_proposals: tuple[MemoryProposalReceipt, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentColTurnResult:
    response: str
    actions: tuple[AgentActionReceipt, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    citations: tuple[CitationReference, ...] = ()
    memory_proposals: tuple[MemoryProposalReceipt, ...] = ()
```

The service constructor consumes:

- the application-owned Vertex `genai.Client` for routing only;
- the accepted `AgentColExpertExecutor`;
- a responder-only `SupervisorRuntime`-compatible runtime;
- the canonical `request_agent_col_routing_directive()` callable by default,
  with a narrow injectable callable seam for offline tests; and
- production-default deadline settings and an injectable monotonic clock for
  deterministic tests.

The routing callable seam receives the client, exact `AgentColRoutingInput`,
and computed timeout. It may not accept any other command or application
state. Production composition uses the canonical provider function unchanged.

The service exposes only:

```python
async def run_turn(
    self,
    command: AgentColTurnCommand,
) -> AgentColTurnResult:
```

Define safe service errors:

```text
AgentColTurnServiceError
  +-- AgentColTurnRoutingError
  +-- AgentColTurnRoutingTimeoutError
  +-- AgentColTurnResponderError
  `-- AgentColTurnTimeoutError
```

Each error may carry only already validated action and memory-proposal
receipts required by the existing partial-failure contract. Error messages and
logs contain no message, URL, identifier, memory value, model output, expert
content, citation, or provider payload.

## Deadline contract

Production constants:

```text
outer turn deadline       90 seconds
routing provider maximum  15 seconds
expert required budget    45 seconds
responder reserve         20 seconds
```

Rules:

1. Capture one monotonic deadline immediately before routing.
2. Enclose routing, optional expert execution, responder-context construction,
   and responder invocation in one `asyncio.timeout(90)` scope.
3. Pass `min(15, remaining_outer_time)` to the routing provider.
4. For `source` or `research`, start the executor only when remaining time is
   at least `45 + 20` seconds.
5. When the reserve gate blocks expert startup, do not call the executor.
   Build a route-matching, content-free expert result with status `timed_out`.
   This truthfully communicates that the selected evidence operation could
   not run within the turn deadline and produces no action or citation.
6. After routing/expert work, run the responder under the exact remaining
   outer time. The existing responder runtime's internal 90-second timeout is
   only a secondary ceiling.
7. Do not retry routing, an expert, or the responder.
8. Caller cancellation propagates unchanged after dependency cleanup; it is
   not mislabeled as a provider or validation failure.

## Receipt ordering and merging

Stable, equality-based deduplication must produce this action order:

1. precompleted application actions;
2. completed cognitive-expert action, if any;
3. responder-produced governed memory-proposal action, if any.

The service must not trust responder text or ADK function-call narration to
create expert receipts. Expert actions and citations come only from
`AgentColResponderContext`, which already recomputes and validates them from
the normalized expert result.

Result merging:

```text
actions          stable_merge(command precompleted,
                              expert context,
                              responder result)
artifacts        responder result only
citations        stable_merge(expert context, responder result)
memory proposals stable_merge(command precompleted,
                              responder result)
```

The responder runtime receives the original precompleted actions/proposals so
its existing governed-memory validation remains authoritative. It does not
receive expert actions as precompleted application actions; those are already
present in the separate validated routing/expert context and are merged by the
turn service afterward.

## Global constraints

- Agent_Col remains the sole semantic router and final user-facing responder.
- Application code executes only the locally validated directive; there is no
  keyword router and no second model-controlled routing decision.
- Version 1.0 executes at most one cognitive expert and delegation depth is
  one. Experts cannot call one another.
- Direct and clarify execute no cognitive expert.
- Source and Research failure never trigger fallback, rerouting, or retry.
- Expert content is untrusted evidence and cannot authorize memory,
  persistence, or application actions.
- The current user message reaches the routing provider once and the responder
  once; it is never duplicated in responder server context.
- Recent user messages are used only for public-URL projection. Their text is
  not sent wholesale to the routing provider.
- No database client, Firestore operation, idempotency key, HTTP object, or
  persistence callback enters this service.
- This pass does not modify `main.py`, `/api/chat`, FastAPI lifespan,
  `database.py`, Firestore, idempotency, request schemas, dependencies, or the
  current production supervisor path.
- This pass makes no live Vertex AI, URL retrieval, Search, or Firestore call.
- Do not commit or push implementation until the repository owner manually
  accepts the pass.

---

### Task 1: Turn command, result, and routing-input projection

**Files:**

- Create: `agent_col_turn_service.py`
- Create: `tests/test_agent_col_turn_service.py`

#### RED cycle 1: strict orchestration inputs

- [ ] Write the smallest test constructing `AgentColTurnCommand` with valid
  server identifiers, a current message containing a URL, recent *user-only*
  messages containing older URLs, responder model context, source-message ID,
  lease, and precompleted receipts.
- [ ] Invoke a service with recording fake routing, executor, and responder
  collaborators.
- [ ] Require the recorded `AgentColRoutingInput` to contain:

  - the normalized current message exactly once;
  - current-message URL candidates first;
  - unique recent-user URL candidates in newest-message-first order;
  - exactly the executor's stable `available_capabilities` tuple.

- [ ] Assert the serialized routing input contains none of the server IDs,
  model context, lease values, source-message ID, precompleted effects,
  profile/memory text, full recent message text, or a model-authored URL.
- [ ] Verify RED:

```bash
venv/bin/pytest -q tests/test_agent_col_turn_service.py \
  -k "routing_input or excluded_context"
```

Expected: collection fails because `agent_col_turn_service` does not exist.

- [ ] Implement the frozen command/result dataclasses, collaborator protocols,
  constructor validation, and minimal routing-input projection using
  `project_routing_url_candidates()`.
- [ ] Call `request_agent_col_routing_directive()` exactly once through the
  injected application-owned Vertex client with the bounded timeout.
- [ ] Verify GREEN with the same focused command.

#### RED cycle 2: routing failures stop the turn

- [ ] Parameterize the fake routing boundary to raise provider failure,
  provider timeout, invalid-output failure, and directive/input mismatch.
- [ ] Require safe translation into the corresponding turn-service routing
  error or routing-timeout error, preserving the original exception as
  `__cause__`.
- [ ] Require zero executor calls and zero responder calls.
- [ ] Require error messages/logs to exclude all task and identity content.
- [ ] Require already precompleted action/proposal receipts to remain attached
  for R3.3D's partial-failure mapping.
- [ ] Verify RED, implement the minimum translation, then verify GREEN:

```bash
venv/bin/pytest -q tests/test_agent_col_turn_service.py \
  -k "routing_failure or routing_timeout or content_safe"
```

---

### Task 2: Deterministic route execution and responder invocation

**Files:**

- Modify: `agent_col_turn_service.py`
- Modify: `tests/test_agent_col_turn_service.py`

#### RED cycle 3: all route modes reach responder correctly

- [ ] Parameterize valid `direct`, `clarify`, `source`, and `research`
  directives.
- [ ] Require the service to pass the directive and its *exact same routing
  input object* to `AgentColExpertExecutor.execute()` when the reserve allows
  execution.
- [ ] Require direct and clarify executor dispatch to result in zero specialist
  service access through the accepted executor contract.
- [ ] Require Source or Research to result in only the selected expert context;
  never both and never a fallback.
- [ ] Require exactly one server-generated routing/expert `types.Content` to be
  appended after the command's existing `model_input_context`.
- [ ] Require the `SupervisorTurnContext` sent to the responder runtime to
  preserve the command's three IDs, source-message ID, memory-decision flag,
  lease, and precompleted effects.
- [ ] Require the current message to appear only as
  `SupervisorTurnContext.message`; it must not occur in the appended responder
  context unless it is independently present inside a legitimate expert
  evidence field.
- [ ] Require one responder call and exactly one final response.
- [ ] Verify RED, implement the minimum composition, then verify GREEN:

```bash
venv/bin/pytest -q tests/test_agent_col_turn_service.py \
  -k "direct or clarify or source or research or responder_context"
```

#### RED cycle 4: authoritative receipt merging

- [ ] Use canonical `AgentActionReceipt`, `CitationReference`,
  `ArtifactReference`, and `MemoryProposalReceipt` instances rather than
  permissive dictionaries.
- [ ] Require stable deduplication and the documented action order across:

  - precompleted decision/proposal effects;
  - the expert context action/citations;
  - responder runtime actions/artifacts/citations/proposals.

- [ ] Require responder-only artifacts to pass through unchanged.
- [ ] Require direct/clarify and failed expert contexts to add no cognitive
  action or citation.
- [ ] Require a responder attempt to be unable to remove an expert receipt by
  omitting it, or duplicate one by returning an equal receipt.
- [ ] Verify RED, implement one private generic stable-merge helper, then
  verify GREEN:

```bash
venv/bin/pytest -q tests/test_agent_col_turn_service.py \
  -k "receipt or artifact or merge"
```

#### RED cycle 5: responder failures preserve trusted effects

- [ ] Make the fake responder raise `SupervisorRuntimeError` carrying a new
  governed memory-proposal action/proposal after a completed expert context.
- [ ] Require translation to `AgentColTurnResponderError` with stable merged
  precompleted, expert, and responder partial effects and the original error
  as cause.
- [ ] Require no retry and no second expert or responder call.
- [ ] Require safe logs and exception text to exclude all command, expert, and
  responder content.
- [ ] Verify RED, implement the minimum error translation, then verify GREEN:

```bash
venv/bin/pytest -q tests/test_agent_col_turn_service.py \
  -k "responder_failure or partial_effect"
```

---

### Task 3: One outer deadline and responder reserve

**Files:**

- Modify: `agent_col_turn_service.py`
- Modify: `tests/test_agent_col_turn_service.py`

#### RED cycle 6: routing budget and late-expert prevention

- [ ] Inject a monotonic test clock and bounded test deadline values without
  changing production defaults.
- [ ] Require routing to receive no more than 15 seconds and never more than
  the current outer remainder.
- [ ] Simulate routing consumption leaving less than the expert's 45-second
  budget plus the 20-second responder reserve.
- [ ] Require zero executor calls for a selected Source or Research route.
- [ ] Require the responder to receive a route-matching, content-free
  `timed_out` result with no action or citation.
- [ ] Simulate exactly 65 seconds remaining and require one executor call,
  proving the inclusive boundary.
- [ ] Verify RED, implement the reserve gate and safe skipped-expert context,
  then verify GREEN:

```bash
venv/bin/pytest -q tests/test_agent_col_turn_service.py \
  -k "routing_budget or responder_reserve or late_expert"
```

#### RED cycle 7: outer deadline contains every phase

- [ ] Use short injected deadlines and cancellable fake collaborators to prove
  that the same outer timeout contains:

  - a hanging routing request;
  - a hanging expert executor;
  - a hanging responder runtime.

- [ ] Require one `AgentColTurnRoutingTimeoutError` for the routing provider's
  own bounded timeout, and `AgentColTurnTimeoutError` when the shared outer
  deadline expires in any phase.
- [ ] Require the responder to be bounded by the computed remaining outer
  time, not a fresh 90 seconds.
- [ ] Require caller cancellation to propagate as `CancelledError` and require
  each fake dependency's `finally` cleanup marker to run.
- [ ] Require zero orchestration retries in all timeout/cancellation cases.
- [ ] Verify RED, implement one outer `asyncio.timeout()` and remaining-time
  calculation, then verify GREEN:

```bash
venv/bin/pytest -q tests/test_agent_col_turn_service.py \
  -k "outer_deadline or cancellation or no_retry"
```

---

### Task 4: Offline orchestration smoke runner

**Files:**

- Create: `smoke_test_agent_col_turn_service.py`
- Create: `tests/test_smoke_test_agent_col_turn_service.py`

#### RED cycle 8: executable end-to-end service proof

- [ ] Add a subprocess test that invokes:

```bash
venv/bin/python smoke_test_agent_col_turn_service.py
```

- [ ] Require one concise success line and exit code zero.
- [ ] The smoke runner must use only fake routing, expert, and responder
  collaborators while exercising the real `AgentColTurnService`.
- [ ] Cover at minimum:

  - direct route with zero cognitive receipt;
  - completed Source route with one `url_context` action and citation;
  - late selected expert skipped to preserve responder time;
  - routing failure prevents downstream access;
  - one final responder-owned response;
  - no network, Vertex, URL retrieval, Search, Firestore, or credential access.

- [ ] Verify RED:

```bash
venv/bin/pytest -q tests/test_smoke_test_agent_col_turn_service.py
```

Expected: subprocess fails because the smoke runner does not exist.

- [ ] Implement the smallest offline smoke runner and verify GREEN with the
  same command.

---

## Focused verification

Run only the new service surface plus its directly consumed accepted
boundaries:

```bash
venv/bin/pytest -q \
  tests/test_agent_col_turn_service.py \
  tests/test_agent_col_routing.py \
  tests/test_agent_col_routing_provider.py \
  tests/test_agent_col_expert_executor.py \
  tests/test_agent_col_responder_context.py \
  tests/test_agent_col_responder.py \
  tests/test_supervisor_runtime.py \
  tests/test_smoke_test_agent_col_turn_service.py
venv/bin/python smoke_test_agent_col_turn_service.py
git diff --check
```

This broader focused set is warranted because R3.3C composes shared routing,
expert, responder-context, and runtime contracts. The full repository suite is
not required because this pass leaves FastAPI, Firestore, schemas,
idempotency, synthesis, deployment, and the live chat path unchanged.

## Manual runtime verification targets

R3.3C is deliberately unreferenced by production. Manual acceptance is an
offline orchestration proof, not a live `/api/chat` or Firestore test.

1. Activate the repository environment and run:

```bash
source venv/bin/activate
python3 smoke_test_agent_col_turn_service.py
```

2. Require exit code zero and exactly one summary line in this form:

```text
r3.3c turn-orchestration-service pass routes=2 max_experts=1 reserve=true routing_failure_contained=true
```

3. No Uvicorn process, Google credential, Vertex quota, URL retrieval, Search,
   or Firestore access is required.
4. No new Firestore document should appear because the service has no
   persistence dependency.
5. The existing live `/api/chat` behavior is intentionally unchanged until
   R3.3D. A live curl cannot verify R3.3C and is not required for this pass.

## Expected files and protected surfaces

Expected changes after approved implementation:

- Create: `agent_col_turn_service.py`
- Create: `tests/test_agent_col_turn_service.py`
- Create: `smoke_test_agent_col_turn_service.py`
- Create: `tests/test_smoke_test_agent_col_turn_service.py`

Protected from modification in R3.3C:

- `main.py`
- `schemas.py`
- `supervisor.py`
- `supervisor_runtime.py`
- `agent_col_routing.py`
- `agent_col_routing_provider.py`
- `agent_col_expert_executor.py`
- `agent_col_responder.py`
- `agent_col_responder_context.py`
- `database.py`
- all Firestore, memory, idempotency, synthesis, deployment, and dependency
  files

## Stop conditions

Stop and revise this plan before production changes if:

- the responder-only runtime cannot be bounded by an outer timeout without
  modifying its cleanup behavior;
- an accepted router, executor, or responder contract must change;
- correct result merging requires trusting model-authored receipts;
- a route can invoke more than one cognitive expert;
- expert failure requires fallback or rerouting;
- a database, idempotency, HTTP, or persistence dependency enters the service;
- the command's server identifiers appear in routing or expert input;
- live `/api/chat`, lifespan composition, or request validation must change;
- automated proof requires Vertex, URL retrieval, Search, Firestore, or real
  credentials.

## Proposed next pass after manual acceptance

**M7-EXP.4D-R3.3D — FastAPI and Idempotent Cutover**

After R3.3C is manually accepted, integrate the accepted turn service into
lifespan and `/api/chat`, add the dedicated 10,000-character chat-message
bound, preserve claim/replay/lease recovery and completed-memory partial
failures, map safe service errors to the accepted HTTP statuses, and prove
identical action/citation replay. R3.3D requires a separate investigation,
plan, approval, TDD cycle, live curl verification, and Firestore acceptance.
