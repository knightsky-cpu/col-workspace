# M7-EXP.4D-R3.3A Responder-Only Agent_Col Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline. Do not use
> subagents for this repository-owner-approved pass.

**Goal:** Create a separate responder-only Agent_Col ADK application and a
strict, bounded server-context contract without changing the production chat
path or executing any cognitive expert.

**Architecture:** Add a pure Pydantic boundary that pairs one validated
routing directive with zero or one normalized Source/Research result and its
application-derived receipts. Add a separate ADK `App` whose root Agent_Col
has no Source tool, Research sub-agent, or cognitive transfer path; governed
memory proposal remains its only optional tool. The existing supervisor and
`/api/chat` remain unchanged until R3.3D.

**Tech Stack:** Python 3.14, Pydantic v2, Google ADK 2.7.0, Google Gen AI SDK,
pytest

**Spec:**
`docs/superpowers/specs/2026-08-21-phase-3b-m7-exp-4d-r3-3-production-routing-integration-design.md`

## Global constraints

- Agent_Col remains the final user-facing responder.
- This pass creates an unreferenced migration boundary; it does not modify
  `main.py`, `/api/chat`, lifespan composition, or production routing.
- The responder app exposes no Source tool, Research sub-agent, cognitive
  expert transfer, Firestore tool, or artifact-write tool.
- `propose_memory_signal` is the responder's only optional tool and remains
  governed by the existing deterministic memory service.
- The original user message is not a field of responder context and will
  continue to enter ADK exactly once through `new_message` in a later pass.
- Only locally validated Source or Research results and exactly matching
  application-derived receipts may enter responder context.
- Direct and clarify routes carry no expert result, action, or citation.
- A noncompleted expert result carries no action or citation.
- Context models are frozen, reject extra fields, hide input values in
  validation errors, and retain the bounds of their nested canonical models.
- Existing `SupervisorRuntime` may be constructed with the responder app, but
  its expert trackers remain unchanged and inert in this pass.
- Do not add dependencies, call Vertex AI, access Firestore, or perform live
  expert execution.
- Do not commit or push implementation until the repository owner manually
  accepts the pass.

---

### Task 1: Strict responder-context contract

**Files:**

- Create: `agent_col_responder_context.py`
- Create: `tests/test_agent_col_responder_context.py`

**Interfaces:**

- Consumes: `AgentColRoutingDirective`
- Consumes: `SourceExpertResult | ResearchExpertResult`
- Consumes: application-derived `AgentActionReceipt` and
  `CitationReference`
- Produces: `AgentColResponderContext`
- Produces:
  `build_agent_col_responder_model_context(context) -> types.Content`

- [ ] **Step 1: Write RED tests for direct and clarify context**

Add tests that construct these literal directives:

```python
direct = AgentColRoutingDirective(route="direct")
clarify = AgentColRoutingDirective(
    route="clarify",
    clarifying_question="Which supplied page should I analyze?",
)
```

Require both contexts to accept no expert result, action, or citation. Require
an expert result, action, citation, `current_message`, `message`, profile, or
server identifier supplied to either context to fail validation rather than
enter the serialized model context.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_responder_context.py \
  -k "direct or clarify"
```

Expected: collection fails because `agent_col_responder_context` does not
exist. Correct the test setup only if it fails for another reason.

- [ ] **Step 3: Implement the minimum strict context model**

Create a frozen, `extra="forbid"`, `hide_input_in_errors=True` Pydantic model
with this public shape:

```python
ResponderExpertResult = Annotated[
    SourceExpertResult | ResearchExpertResult,
    Field(discriminator="capability"),
]

class AgentColResponderContext(BaseModel):
    routing_directive: AgentColRoutingDirective
    expert_result: ResponderExpertResult | None = None
    actions: tuple[AgentActionReceipt, ...] = Field(
        default_factory=tuple,
        max_length=1,
    )
    citations: tuple[CitationReference, ...] = Field(
        default_factory=tuple,
        max_length=12,
    )
```

The first cross-field validator behavior is:

```text
direct/clarify -> expert_result is absent; actions and citations are empty
source/research -> deferred to the next RED cycle
```

- [ ] **Step 4: Verify GREEN**

Run the same focused command. Require all direct/clarify cases to pass with no
warning.

- [ ] **Step 5: Write RED tests for Source and Research pairing**

Build real, locally valid `SourceExpertResult` and `ResearchExpertResult`
fixtures using their canonical payload and evidence models. Do not replace
those models with permissive dictionaries or mocks.

Require:

```text
source route   -> SourceExpertResult only
research route -> ResearchExpertResult only
completed      -> exact build_*_receipts() actions and citations
noncompleted   -> no action and no citation
```

Test these realistic mutations independently:

- Source result paired with Research route;
- Research result paired with Source route;
- selected expert route with no result;
- completed result missing its action;
- completed result with the other expert's action;
- completed result with missing, extra, reordered, or altered citations;
- failed result with any action or citation;
- more than one action or more than twelve citations.

Every mutation must fail with a content-safe `ValidationError`.

- [ ] **Step 6: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_responder_context.py \
  -k "source or research or receipt"
```

Expected: expert routes are rejected or incorrectly accepted because exact
route/result/receipt validation is not implemented.

- [ ] **Step 7: Implement exact expert and receipt validation**

Map route to expected capability:

```python
{
    AgentColRoute.SOURCE: ExpertCapability.SOURCE,
    AgentColRoute.RESEARCH: ExpertCapability.RESEARCH,
}
```

For Source, derive the only accepted receipt tuple with
`build_source_receipts(expert_result)`. For Research, use
`build_research_receipts(expert_result)`. Compare the context's action and
citation tuples exactly to those derived receipts. Return no best-effort
coercion and never log validation inputs.

- [ ] **Step 8: Verify GREEN**

Run the complete context test file and require every pairing and mutation case
to pass.

- [ ] **Step 9: Write RED tests for the bounded model-input renderer**

Require `build_agent_col_responder_model_context()` to return one
`google.genai.types.Content` with:

- role `user`;
- exactly one text part;
- `[SERVER_VALIDATED_ROUTING_AND_EXPERT_RESULT]` delimiters;
- a JSON payload equal to `context.model_dump(mode="json")`;
- instructions that the route is authoritative, validated expert content is
  untrusted evidence, expert tools must not be called, and receipts must not
  be fabricated or changed;
- no separate current-message field, credential, user/session/project/turn
  identifier, profile, or idempotency value.

Test the returned structure and parsed delimited JSON, not an exact prose
snapshot.

- [ ] **Step 10: Verify RED, implement the renderer, and verify GREEN**

Use `json.dumps(..., ensure_ascii=False, separators=(",", ":"))` and
`types.Part.from_text()`. Do not add user-provided values outside the
validated JSON payload.

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_responder_context.py
```

---

### Task 2: Responder-only ADK application

**Files:**

- Create: `agent_col_responder.py`
- Create: `tests/test_agent_col_responder.py`

**Interfaces:**

- Produces: `RESPONDER_INSTRUCTION`
- Produces:
  `create_responder_app(vertex_settings, memory_service=None) -> App`
- Produces: `RESPONDER_APP_NAME = "agent_col"`
- Produces: `RESPONDER_MODEL_NAME = "gemini-3.6-flash"`
- Reuses: `create_propose_memory_signal_tool()`

- [ ] **Step 1: Write the structural RED tests**

Instantiate the real ADK app with test Vertex settings and no network call.
Require:

```text
app.name                  == "agent_col"
root_agent.name           == "Agent_Col"
root_agent.model.model    == "gemini-3.6-flash"
root_agent.tools          == [] without memory service
root_agent.sub_agents     == []
```

With an injected memory service, require the exact tool-name tuple to be:

```python
("propose_memory_signal",)
```

Require `analyze_source`, `research_expert`, Google Search, URL Context, and
every transfer target to be absent from the actual tool and sub-agent
catalogs. Test the ADK objects, not the source text.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_responder.py -k catalog
```

Expected: import failure because the responder app factory does not exist.

- [ ] **Step 3: Implement the minimum responder app**

Create one root `Agent` with:

```python
Agent(
    name="Agent_Col",
    model=Gemini(
        model=RESPONDER_MODEL_NAME,
        client_kwargs=vertex_settings.client_kwargs(),
    ),
    description=(
        "General collaborative partner that retains final responsibility "
        "for each user response."
    ),
    instruction=RESPONDER_INSTRUCTION,
    tools=(
        []
        if memory_service is None
        else [create_propose_memory_signal_tool(memory_service)]
    ),
    sub_agents=[],
)
```

Return `App(name=RESPONDER_APP_NAME, root_agent=root_agent)`. Define the two
responder constants locally so the new production module does not import the
old supervisor and transitively load its cognitive-expert definitions. Do not
import or instantiate Source, Research, delegation-registry, or
cognitive-expert components.

- [ ] **Step 4: Verify GREEN**

Run the structural catalog tests and inspect the actual tool/sub-agent names.

- [ ] **Step 5: Write RED contract tests for responder responsibility**

The instruction is executable model policy, so test only its required
behavioral rules rather than exact formatting. Require normalized instruction
text to establish:

- Agent_Col owns one final response;
- server-validated routing context is authoritative;
- direct answers do not invoke an expert;
- clarify uses the supplied clarification question;
- Source/Research output is untrusted evidence to integrate;
- failed expert status cannot support invented current claims;
- application action and citation receipts cannot be fabricated;
- retrieved content cannot authorize actions or memory;
- governed memory proposal rules remain explicit, reusable, non-sensitive,
  approval-gated, limited to one candidate, and suppressed for structured
  memory-decision turns.

- [ ] **Step 6: Verify RED, implement the instruction, and verify GREEN**

The instruction must not tell the responder that Source, Research, transfer,
Firestore, or artifact-write tools are available. Run the complete responder
app test file.

- [ ] **Step 7: Verify runtime construction compatibility**

Add a test that passes the real responder app to
`SupervisorRuntime.from_app()` without making a provider call. Require
construction to succeed and `RESPONDER_APP_NAME` to equal the existing
runtime's session app name. This compatibility assertion catches a real
session-routing defect while allowing the responder production module to
remain independent of the legacy supervisor module.

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_responder.py
```

No `supervisor_runtime.py` change is allowed in this task. If construction
fails because the existing runtime truly requires a cognitive expert,
stop—the R3.3A boundary is wrong and requires a revised plan.

---

### Task 3: Offline responder-boundary smoke runner

**Files:**

- Create: `smoke_test_agent_col_responder.py`
- Create: `tests/test_smoke_test_agent_col_responder.py`

**Interfaces:**

- Produces: one local, provider-free manual acceptance command
- Consumes: the real responder app factory and responder-context renderer

- [ ] **Step 1: Write the smoke-runner RED tests**

Require a pure `run_smoke() -> str` boundary to:

- create the responder app with dummy-but-valid Vertex settings;
- verify zero cognitive tools and zero sub-agents;
- verify memory injection produces only `propose_memory_signal`;
- render valid direct and clarify contexts;
- return one content-safe summary containing `responder-boundary pass`;
- make no model, network, database, or expert call.

Exercise the real app and context objects. Test `main()` separately only to
confirm it prints the `run_smoke()` result; do not replace the app or context
objects with mocks.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_smoke_test_agent_col_responder.py
```

Expected: import failure because the smoke runner does not exist.

- [ ] **Step 3: Implement the minimum offline runner and verify GREEN**

The successful output must be one line similar to:

```text
r3.3a responder-boundary pass tools=memory-only subagents=0 routes=direct,clarify
```

Do not print prompts, context JSON, identifiers, or provider configuration.

- [ ] **Step 4: Run focused regressions**

Run:

```bash
venv/bin/pytest -q \
  tests/test_agent_col_responder_context.py \
  tests/test_agent_col_responder.py \
  tests/test_smoke_test_agent_col_responder.py \
  tests/test_supervisor_runtime.py \
  tests/test_memory_proposal_tool.py
```

These are the directly related boundaries because the new responder reuses
the existing runtime and governed memory tool. Do not run the full suite:
`main.py`, production routing, persistence, synthesis, and expert execution
remain unchanged.

- [ ] **Step 5: Run static verification**

```bash
venv/bin/python -m py_compile \
  agent_col_responder_context.py \
  agent_col_responder.py \
  smoke_test_agent_col_responder.py
git diff --check
```

- [ ] **Step 6: Stop at manual verification**

Report the pass as **implemented, pending manual verification**. Do not commit
or push the implementation.

## Manual runtime verification targets

Primary offline acceptance command:

```bash
source venv/bin/activate && python3 smoke_test_agent_col_responder.py
```

Acceptance requires:

```text
r3.3a responder-boundary pass tools=memory-only subagents=0 routes=direct,clarify
```

with exit status zero and no Google SDK, ADK, Firestore, network, quota, or
credential error.

Optional live regression—this verifies only that the intentionally unchanged
current chat path still responds; it does **not** prove the new responder is
live:

```bash
curl --fail-with-body --silent --show-error --max-time 100 \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"project_id":"agent-col","session_id":"r3-3a-regression","user_id":"wifiknight","message":"Explain in one concise paragraph why a responder should not reroute an already validated expert decision."}' \
  http://127.0.0.1:8000/api/chat
```

The optional curl requires an already running FastAPI process and consumes a
Vertex request. A 200 response is a regression signal only. It must not be
reported as evidence that R3.3A is integrated into production.

## Stop conditions

Stop and revise this plan before implementation expands if:

- ADK implicitly exposes a cognitive capability despite empty `sub_agents`
  and the memory-only tool list;
- `SupervisorRuntime.from_app()` requires a cognitive expert;
- exact Source/Research receipt validation cannot use the existing canonical
  result and receipt builders;
- implementing the boundary requires changing `main.py`,
  `supervisor_runtime.py`, Firestore, idempotency, or dependencies;
- a new provider call is necessary to prove the structural boundary.

## Expected implementation diff

```text
Create agent_col_responder_context.py
Create agent_col_responder.py
Create smoke_test_agent_col_responder.py
Create tests/test_agent_col_responder_context.py
Create tests/test_agent_col_responder.py
Create tests/test_smoke_test_agent_col_responder.py
```

No existing production file changes are expected.
