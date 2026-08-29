# M7-EXP.4D-R3.3B Deterministic Expert Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline. Do not use
> subagents for this repository-owner-approved pass.

**Goal:** Add a persistence-free deterministic executor that runs exactly the
Source or Research capability selected by a locally validated Agent_Col
routing directive, contains expected expert failures, and produces an exact
`AgentColResponderContext` without changing the production chat path.

**Architecture:** Reuse `SourceExpertService` directly. Introduce an isolated
Research application service whose ADK root is a deterministic one-node
`Workflow` containing the existing bounded `single_turn` Research agent. Add
one executor that revalidates the directive against its exact routing input,
maps only the selected intent into the canonical expert input, invokes zero or
one configured expert, derives receipts through the existing trusted receipt
builders, and returns the already-strict responder context. No model chooses
or changes the route inside this executor.

**Tech Stack:** Python 3.14, Pydantic v2, Google ADK 2.7.0 Workflow/Runner,
Google Gen AI SDK, pytest, pytest-asyncio

**Spec:**
`docs/superpowers/specs/2026-08-21-phase-3b-m7-exp-4d-r3-3-production-routing-integration-design.md`

## Verified repository and provider boundary

- `SourceExpertService.analyze()` is already a directly callable application
  service. It performs bounded URL Context retrieval, a tool-free structured
  classification call, local grounding validation, and safe error
  translation.
- `create_research_expert()` currently returns a bounded
  `mode="single_turn"` ADK agent with Google Search, no child agents, disabled
  parent/peer transfers, `include_contents="none"`, and a 45-second timeout.
- The installed ADK `Runner` rejects an `LlmAgent` in `single_turn` mode when
  that agent is the application root; a root LLM agent must use `chat` or
  `task` mode.
- ADK 2.7.0 supports a `Workflow` as an application root and supports a
  `single_turn` LLM agent as a Workflow node. A structural local probe
  verified this graph:

```text
Workflow: research_workflow
  START -> research_expert (single_turn)
```

- The older `SequentialAgent` could also wrap the specialist, but it is
  deprecated in the installed ADK version. This pass must use `Workflow`.
- A local schema probe verified that the Workflow node converts a user
  `Content` containing only `ResearchExpertInput.model_dump_json()` into the
  canonical input model. Wrapping that JSON in textual delimiters fails the
  node's central input-schema validation, so the isolated invocation must send
  pure validated JSON. The Research system instruction already identifies the
  input object as untrusted task data.
- Because the Research agent has no `output_schema`, ADK's Workflow wrapper
  promotes its natural-language response text into `event.output`. The
  existing Research normalizer interprets a non-null `event.output` as a
  structured `ResearchExpertDraft`. The adapter must therefore copy the final
  event with only `output=None` before calling `normalize_research_event()`;
  this selects the existing provider-grounded natural-language normalization
  path without altering content or grounding metadata.
- `ResearchExpertTurnTracker` is intentionally not reused. It requires a
  parent Agent_Col function-call claim before accepting a Research event,
  while this service is an isolated deterministic invocation with no model
  transfer.
- Existing `normalize_research_event()`, `build_research_receipts()`,
  `build_source_receipts()`, and `AgentColResponderContext` remain the
  authoritative output and receipt boundaries.

## Global constraints

- Agent_Col remains the semantic routing decision-maker and final responder.
  Application code only executes its locally validated directive.
- Version 1.0 executes zero experts for `direct` and `clarify`, and exactly one
  selected expert attempt for `source` or `research`.
- Expert execution is deterministic dispatch, not keyword routing and not a
  second model-controlled routing decision.
- Experts cannot call other experts. Delegation depth is one.
- A Source failure cannot fall back to Research. A Research failure cannot
  fall back to Source. No failure returns to the routing provider.
- Expected expert failures become content-free canonical expert results. They
  produce no completed action receipt and no citations.
- Unexpected executor configuration defects fail closed; they are not
  mislabeled as provider unavailability.
- Selected Source URL identifiers are mapped only through the exact validated
  `AgentColRoutingInput`, preserving directive order.
- The Research service uses a constant internal service identity and a random
  invocation-session identifier. It receives no real user, project, session,
  turn, idempotency, profile, memory, or Firestore identifier.
- Research request JSON is the only task content sent to its isolated ADK
  invocation. It is sent as pure JSON so ADK can enforce the existing
  `ResearchExpertInput` schema before the node runs.
- Every created Research invocation session is deleted on success, provider
  error, invalid output, timeout, or caller cancellation.
- Application receipts are derived only from completed locally validated
  results through existing receipt builders. Model text never creates a
  receipt.
- Logs may contain safe exception class names and capability/status codes.
  They must exclude messages, questions, objectives, constraints, URLs,
  identifiers, provider payloads, model output, findings, and citations.
- This pass does not modify `main.py`, `/api/chat`, lifespan composition,
  `SupervisorRuntime`, Firestore, idempotency, memory behavior, schemas,
  dependencies, or production routing.
- This pass makes no live Vertex AI or Firestore request.
- Do not commit or push implementation until the repository owner manually
  accepts the pass.

---

### Task 1: Isolated Research application service

**Files:**

- Create: `research_expert_service.py`
- Create: `tests/test_research_expert_service.py`

**Interfaces:**

- Produce: `RESEARCH_EXPERT_APP_NAME = "agent_col_research"`
- Produce: `RESEARCH_EXPERT_WORKFLOW_NAME = "research_workflow"`
- Produce: `RESEARCH_EXPERT_SERVICE_USER_ID = "research_service"`
- Produce: `RESEARCH_EXPERT_MAX_LLM_CALLS = 2`
- Produce: `ResearchExpertServiceError`
- Produce: `ResearchExpertService.from_vertex_settings(...)`
- Produce:
  `async ResearchExpertService.research(request) -> ResearchExpertResult`

#### RED cycle 1: supported isolated ADK topology

- [ ] Write a structural test that calls
  `ResearchExpertService.from_vertex_settings()` with test Vertex settings
  and inspects the real ADK objects without making a provider request.
- [ ] Require one `App` named `agent_col_research`, one root `Workflow` named
  `research_workflow`, and exactly one graph edge from `START` to the existing
  `research_expert` agent.
- [ ] Require the specialist to retain all accepted constraints:

```text
mode                         single_turn
input_schema                 ResearchExpertInput
tool catalog                 google_search only
sub-agents                   none
transfer to parent/peers     disabled
include_contents             none
timeout                      45 seconds
```

- [ ] Assert that neither `SequentialAgent`, a chat-mode wrapper, Agent_Col,
  Source, memory, nor a persistence tool is present in the graph.
- [ ] Verify RED:

```bash
venv/bin/pytest -q tests/test_research_expert_service.py -k topology
```

Expected: collection fails because `research_expert_service` does not exist.

- [ ] Implement the minimum factory with:

```python
research_expert = create_research_expert(
    vertex_settings=vertex_settings,
)
workflow = Workflow(
    name=RESEARCH_EXPERT_WORKFLOW_NAME,
    edges=[("START", research_expert)],
)
app = App(name=RESEARCH_EXPERT_APP_NAME, root_agent=workflow)
sessions = InMemorySessionService()
runner = Runner(app=app, session_service=sessions)
```

- [ ] Do not mutate the Research agent's mode, tools, schemas, instruction,
  transfer flags, or timeout to make it root-compatible.
- [ ] Verify GREEN with the same focused command.

#### RED cycle 2: exact request projection and completed result

- [ ] Add fake runner and fake session-service collaborators that record all
  arguments and yield one real grounded `google.adk.events.Event` authored by
  `research_expert`.
- [ ] Construct a canonical `ResearchExpertInput` with a question, objective,
  and ordered constraints.
- [ ] Require `research()` to:

  - create exactly one random invocation session;
  - use only the constant internal service user ID;
  - send exactly one user-role text part equal to
    `request.model_dump_json()` with no prefix, suffix, or duplicate fields;
  - pass `RunConfig(max_llm_calls=2)`;
  - fully consume the runner event stream;
  - accept exactly one final Research event;
  - copy that event with only `output=None`, preserving its text and grounding
    metadata, then normalize it through `normalize_research_event()`;
  - require `ExpertStatus.COMPLETED`;
  - return the canonical completed `ResearchExpertResult`;
  - delete the same invocation session exactly once after the stream ends.

- [ ] Assert that no real user/project/session/turn identifier, profile,
  history, idempotency value, URL, or credential appears in create/run calls
  or the serialized request.
- [ ] Verify RED:

```bash
venv/bin/pytest -q tests/test_research_expert_service.py \
  -k "completed or request or session"
```

Expected: the factory exists, but no execution lifecycle exists.

- [ ] Implement the minimum async lifecycle. Generate the invocation ID with
  `uuid4().hex`; do not accept an invocation ID from a caller.
- [ ] Serialize only the already validated `ResearchExpertInput`. Do not add
  delimiters or duplicate request fields because ADK validates the pure JSON
  against the node's existing `input_schema` before execution.
- [ ] Collect only final events authored by `research_expert`. Internal
  Workflow bookkeeping events cannot become results.
- [ ] Verify GREEN with the same focused command.

#### RED cycle 3: bounded failures and unconditional cleanup

- [ ] Add independent cases for:

  - no final Research event;
  - more than one final Research event;
  - final event from another author;
  - final event with invalid or missing grounding;
  - ADK validation failure;
  - ADK node timeout;
  - generic provider/runtime error;
  - adapter timeout;
  - caller cancellation.

- [ ] Require safe status mapping:

```text
validation/input rejection  -> rejected_input
ADK/adapter timeout         -> timed_out
invalid normalized output   -> invalid_output
other provider/runtime      -> unavailable
```

- [ ] Require every ordinary failure to raise
  `ResearchExpertServiceError(status)` with the exact public message
  `"Research Expert execution failed."`, preserving the original exception
  as `__cause__` when one exists.
- [ ] Require session deletion exactly once whenever creation succeeded,
  including timeout and cancellation paths. Cancellation must be re-raised
  after cleanup instead of being converted into a normal expert result.
- [ ] Require zero deletion calls when session creation itself fails.
- [ ] Require logging to omit seeded private request text, IDs, provider
  payloads, findings, and citations.
- [ ] Verify RED:

```bash
venv/bin/pytest -q tests/test_research_expert_service.py \
  -k "failure or invalid or timeout or cancel or logging"
```

- [ ] Implement one exception-mapping helper using public exception types
  exposed by the installed ADK where stable. Unknown exceptions map to
  `unavailable`; do not depend on private ADK exception classes.
- [ ] Put session deletion in `finally`. Do not reach into private Runner,
  Workflow, agent, Gemini, or provider-client attributes for cleanup.
- [ ] Verify GREEN by running the full service test file.

---

### Task 2: Deterministic selected-expert executor

**Files:**

- Create: `agent_col_expert_executor.py`
- Create: `tests/test_agent_col_expert_executor.py`

**Interfaces:**

- Produce: `AgentColExpertExecutorConfigurationError`
- Produce: `AgentColExpertExecutor.available_capabilities`
- Produce:
  `async AgentColExpertExecutor.execute(directive, routing_input)`
- Return: `AgentColResponderContext`

The constructor accepts optional application-owned `SourceExpertService` and
`ResearchExpertService` instances. `available_capabilities` is derived from
those configured services in stable Source-then-Research order. It is not a
caller-supplied or model-supplied value.

#### RED cycle 1: zero-expert routes and configuration authority

- [ ] Create recording fake Source and Research services.
- [ ] Require `direct` and `clarify` to:

  - call `validate_routing_directive_for_input()` first;
  - call neither service;
  - return `AgentColResponderContext` with the exact directive;
  - carry no expert result, action, or citation.

- [ ] Require `available_capabilities` to report exactly the configured
  services and reject duplicate or caller-defined capability state.
- [ ] Require a routing input that advertises a capability absent from the
  executor to fail before either service is accessed. This is an application
  wiring defect, not provider unavailability, and raises the content-safe
  `AgentColExpertExecutorConfigurationError`.
- [ ] Verify RED:

```bash
venv/bin/pytest -q tests/test_agent_col_expert_executor.py \
  -k "direct or clarify or capabilities or configuration"
```

Expected: collection fails because `agent_col_expert_executor` does not exist.

- [ ] Implement the constructor, property, exact-input revalidation, and
  zero-expert branches only.
- [ ] Do not add keyword matching, fallback selection, provider access, or
  model calls.
- [ ] Verify GREEN with the same focused command.

#### RED cycle 2: exact Source mapping and execution

- [ ] Build a routing input whose current and history URL candidates are
  deliberately out of identifier order. Build a Source directive selecting a
  noncontiguous subset in a different order.
- [ ] Require the executor to construct exactly one `SourceExpertInput` with:

```text
objective    directive.source_intent.objective
urls         URLs mapped in selected_url_ids order
constraints  directive.source_intent.constraints
```

- [ ] Require one and only one `SourceExpertService.analyze()` call.
- [ ] Require a completed result to return a Source
  `AgentColResponderContext` with the exact `url_context` action and ordered
  provider-derived citations from `build_source_receipts()`.
- [ ] Require unknown, duplicate, or unavailable Source IDs to fail during
  canonical routing validation before Source access.
- [ ] Require Source never to run for `research`, `direct`, or `clarify`.
- [ ] Verify RED:

```bash
venv/bin/pytest -q tests/test_agent_col_expert_executor.py -k source
```

- [ ] Implement a private mapping helper based solely on candidate IDs from
  the exact routing input. Do not parse URLs from the original message or
  allow the expert service to choose URLs.
- [ ] Derive receipts through `build_source_receipts()` and construct the
  strict responder context. Do not copy receipt values manually.
- [ ] Verify GREEN with the same focused command.

#### RED cycle 3: exact Research mapping and execution

- [ ] Build a Research directive and require exactly one
  `ResearchExpertInput` with:

```text
question     directive.research_intent.question
objective    directive.research_intent.objective
constraints  directive.research_intent.constraints
```

- [ ] Require one and only one `ResearchExpertService.research()` call.
- [ ] Require a completed result to return a Research
  `AgentColResponderContext` with the exact `google_search` action and ordered
  provider-derived citations from `build_research_receipts()`.
- [ ] Require Research never to run for `source`, `direct`, or `clarify`.
- [ ] Verify RED:

```bash
venv/bin/pytest -q tests/test_agent_col_expert_executor.py -k research
```

- [ ] Implement only the exact intent projection and one service call.
- [ ] Derive receipts through `build_research_receipts()` and construct the
  strict responder context.
- [ ] Verify GREEN with the same focused command.

#### RED cycle 4: contained failure without fallback

- [ ] Parameterize both experts across `rejected_input`, `unavailable`,
  `timed_out`, and `invalid_output` service errors.
- [ ] Require the executor to convert each typed service error into the
  corresponding canonical Source or Research result with:

```text
status       exact safe status
summary      absent
limitations  empty
payload      absent
evidence     absent
actions      empty
citations    empty
```

- [ ] Require the strict responder context to accept the selected capability's
  content-free result and derive no receipts.
- [ ] Assert that a Source failure never calls Research and a Research failure
  never calls Source.
- [ ] Assert that no selected expert is called twice.
- [ ] Let unexpected, untyped programming errors propagate to the future turn
  service rather than disguising them as ordinary provider failure.
- [ ] Require logs, exception messages, and result serialization to omit
  private seeded messages, URLs, IDs, provider payloads, and expert content.
- [ ] Verify RED:

```bash
venv/bin/pytest -q tests/test_agent_col_expert_executor.py \
  -k "failure or fallback or content"
```

- [ ] Implement typed failure containment only. Use canonical Source/Research
  result constructors and existing receipt builders; do not invent a generic
  expert payload.
- [ ] Verify GREEN by running the complete executor test file.

---

### Task 3: Offline executor smoke runner

**Files:**

- Create: `smoke_test_agent_col_expert_executor.py`
- Create: `tests/test_smoke_test_agent_col_expert_executor.py`

**Purpose:** Give the repository owner one deterministic, non-billable command
that exercises all four routes and Research cleanup without starting FastAPI,
calling Vertex AI, or accessing Firestore.

- [ ] Write RED tests for a smoke runner that uses only recording fakes and
  canonical completed expert fixtures.
- [ ] Require it to prove:

```text
direct    -> zero expert calls, zero receipts
clarify   -> zero expert calls, zero receipts
source    -> one Source call, exact URL order, url_context receipt
research  -> one Research call, google_search receipt
failure   -> no fallback, no receipts
cleanup   -> isolated Research session deleted
```

- [ ] Require a stable final line:

```text
r3.3b deterministic-expert-executor pass routes=4 max_experts=1 research_cleanup=true
```

- [ ] Verify RED:

```bash
venv/bin/pytest -q tests/test_smoke_test_agent_col_expert_executor.py
```

- [ ] Implement the minimum runner and verify GREEN.

---

### Task 4: Focused regression verification

- [ ] Run the new focused tests:

```bash
venv/bin/pytest -q \
  tests/test_research_expert_service.py \
  tests/test_agent_col_expert_executor.py \
  tests/test_smoke_test_agent_col_expert_executor.py
```

- [ ] Because the executor consumes shared routing, Source, Research, receipt,
  and responder-context contracts, run the directly related regression set:

```bash
venv/bin/pytest -q \
  tests/test_agent_col_routing.py \
  tests/test_agent_col_routing_provider.py \
  tests/test_source_expert.py \
  tests/test_source_expert_service.py \
  tests/test_research_expert.py \
  tests/test_research_expert_runtime.py \
  tests/test_agent_col_responder_context.py \
  tests/test_research_expert_service.py \
  tests/test_agent_col_expert_executor.py \
  tests/test_smoke_test_agent_col_expert_executor.py
```

- [ ] Compile only the affected Python surfaces:

```bash
venv/bin/python -m py_compile \
  research_expert_service.py \
  agent_col_expert_executor.py \
  smoke_test_agent_col_expert_executor.py
```

- [ ] Run whitespace and repository-safety checks:

```bash
git diff --check
git status --short
```

- [ ] Do not run the entire repository suite by default. The pass adds an
  unreferenced orchestration boundary and does not alter FastAPI, Firestore,
  memory, synthesis, or the existing production supervisor. Expand only if a
  focused regression exposes a shared-contract failure.

## Stop conditions

Stop implementation and return for a revised plan if any of these occurs:

- ADK 2.7.0 cannot execute the existing `single_turn` Research agent as the
  sole node of a root `Workflow`;
- the Workflow changes or strips provider grounding metadata before local
  normalization;
- safe Research cleanup requires private ADK attribute access;
- deterministic execution requires changing the accepted routing directive,
  Source/Research result, receipt, or responder-context contracts;
- a selected expert cannot be limited to one logical attempt at the executor
  boundary;
- implementation would require `main.py`, Firestore, dependency, or existing
  production-supervisor changes;
- cancellation cannot be propagated after attempting session cleanup;
- a failure path would need to expose raw provider or user content.

## Manual runtime verification targets

After automated verification, the repository owner runs:

```bash
source venv/bin/activate && python3 smoke_test_agent_col_expert_executor.py
```

Expected:

```text
r3.3b deterministic-expert-executor pass routes=4 max_experts=1 research_cleanup=true
```

Acceptance additionally requires:

1. no Vertex AI quota warning, provider request, or AFC warning;
2. no Firestore access;
3. no traceback or ADK deprecation warning;
4. exit code zero;
5. `git diff -- main.py supervisor.py supervisor_runtime.py database.py`
   produces no output.

No browser, curl, Uvicorn, or Firestore inspection is required because R3.3B
is deliberately not connected to the production HTTP lifecycle. That live
integration belongs to R3.3D after R3.3C is accepted.

## Proposed next pass after acceptance

**M7-EXP.4D-R3.3C — Turn Orchestration Service**

Compose the accepted routing provider, deterministic expert executor,
responder-only runtime, one 90-second outer deadline, responder reserve, and
safe result merging behind a persistence-free `AgentColTurnService`. Do not
modify `/api/chat`; production cutover remains R3.3D.
