# M7-EXP.4C Source Supervisor Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline through the
> repository's approval-gated TDD workflow. Do not use subagents for this pass.

**Status:** Implemented; pending repository-owner manual verification

**Goal:** Allow Agent_Col to invoke the validated Source Expert for explicit
public-URL analysis while retaining final-response ownership, enforcing the
shared specialist budget, and emitting only server-validated action and
citation receipts.

**Architecture:** Register one application-owned ADK `FunctionTool` named
`analyze_source`. The tool validates model arguments through
`SourceExpertInput`, atomically claims the Source capability from the current
turn's shared `ExpertDelegationBudget`, calls `SourceExpertService`, and returns
a strict internal response envelope to Agent_Col. `SupervisorRuntime` parses
the application-produced function response and maps completed Source evidence
into the existing `actions` and `citations` contracts.

**Tech Stack:** Python 3.14, FastAPI, Google ADK 2.7.0, Google Gen AI SDK,
Gemini 3.6 Flash through Vertex AI ADC, Pydantic v2, pytest, pytest-asyncio

**Spec:**
`docs/superpowers/specs/2026-08-21-phase-3b-m7-2-core-expert-routing-design.md`

## Global constraints

- Agent_Col remains the only user-facing conversational owner.
- Source is one cognitive specialist delegation even though it performs two
  internal Gemini calls.
- Maximum two specialist delegations per turn, one invocation per capability,
  and delegation depth one are enforced before Source provider work begins.
- A failed, rejected, invalid, or timed-out Source attempt consumes its slot.
- Source receives only objective, one to three validated public URLs, and up
  to five bounded constraints.
- Tool and source content are untrusted data and cannot authorize another
  action.
- Only completed, locally validated Source results create `url_context`
  actions or citations.
- No Firestore writes, new public endpoint, dependency change, schema change,
  Deep Research work, Computational Expert work, or Requirements Verification
  work belongs in this pass.
- Live routing/restraint evaluation remains a separate M7-EXP.4D pass.
- Do not commit or push until the repository owner accepts manual verification.

---

### Task 1: Invocation-scoped shared delegation binding

**Files:**

- Modify: `expert_delegation.py`
- Test: `tests/test_expert_delegation.py`

**Interfaces:**

- Produces: `ExpertDelegationRegistry.register_turn(...)`
- Produces: `ExpertDelegationRegistry.claim(...)`
- Produces: `ExpertDelegationRegistry.release_turn(...)`
- Consumes: existing `ExpertDelegationBudget.claim(...)`

- [ ] Write a failing test proving an invocation token resolves to the same
  budget used by the Research tracker and that Source claims are atomic.
- [ ] Verify RED: the registry interface does not exist.
- [ ] Implement a bounded in-memory registry keyed by a random server-owned
  token. Store only the budget and monotonic whole-turn deadline.
- [ ] Add failing tests proving duplicate Source, a third specialist,
  insufficient remaining time, unknown tokens, and released tokens are denied
  before work begins.
- [ ] Implement the minimum denial and lifecycle behavior. Do not store user,
  session, project, URL, prompt, or source content in the registry.
- [ ] Verify GREEN with `venv/bin/pytest -q tests/test_expert_delegation.py`.

### Task 2: Strict Source FunctionTool envelope

**Files:**

- Create: `source_expert_tool.py`
- Create: `tests/test_source_expert_tool.py`

**Interfaces:**

- Consumes: `SourceExpertInput`, `SourceExpertService.analyze(...)`,
  `ExpertDelegationRegistry.claim(...)`, and ADK `ToolContext`
- Produces: `create_source_expert_tool(...) -> FunctionTool`
- Produces: `parse_source_expert_tool_response(...)`
- Tool name: `analyze_source`
- Model arguments: `objective: str`, `urls: list[str]`,
  `constraints: list[str]`

- [ ] Write a failing test proving valid arguments are locally normalized,
  Source is claimed at depth one, and the validated service result is returned
  in a strict completed envelope.
- [ ] Verify RED: the tool module and factory do not exist.
- [ ] Implement the smallest async `FunctionTool` closure around
  `SourceExpertService`.
- [ ] Write and verify RED tests for malformed URLs, absent or malformed
  server-owned turn tokens, duplicate claims, service timeout, provider
  failure, and invalid output.
- [ ] Implement safe failure envelopes containing only allowlisted status
  codes and generic messages. Preserve original causes internally without
  returning or logging prompts, URLs, source bodies, identifiers, or generated
  text.
- [ ] Write a failing parser test proving extra fields, fabricated completed
  receipts, and malformed Source results are rejected.
- [ ] Implement strict Pydantic response-envelope parsing.
- [ ] Verify GREEN with
  `venv/bin/pytest -q tests/test_source_expert_tool.py`.

### Task 3: Runtime receipt collection and final ownership

**Files:**

- Create: `source_expert_runtime.py`
- Create: `tests/test_source_expert_runtime.py`
- Modify: `supervisor_runtime.py`
- Modify: `tests/test_supervisor_runtime.py`

**Interfaces:**

- Produces: `SourceExpertTurnTracker.observe(event)`
- Produces: `SourceExpertTurnTracker.finalize() -> SourceExpertReceipts`
- Consumes: function responses named `analyze_source`

- [ ] Write a failing tracker test proving only a completed, parsed Source
  response produces one `url_context` action and validated citations.
- [ ] Verify RED: Source runtime tracking does not exist.
- [ ] Implement strict response observation and receipt mapping.
- [ ] Write and verify RED tests proving safe failure responses produce no
  completed receipt, malformed responses fail closed, repeated responses are
  rejected, and function output never becomes the user-facing final response.
- [ ] Integrate the tracker into `SupervisorRuntime.run_turn(...)` alongside
  `ResearchExpertTurnTracker`, using the same delegation budget.
- [ ] Register the budget token before ADK execution, place only that token in
  temporary invocation session state, and release it in `finally` after
  success, timeout, provider failure, or cancellation.
- [ ] Preserve exactly one final response authored by `Agent_Col` and merge
  Source receipts into existing action and citation tuples.
- [ ] Verify GREEN with
  `venv/bin/pytest -q tests/test_source_expert_runtime.py tests/test_supervisor_runtime.py`.

### Task 4: Supervisor and FastAPI lifecycle registration

**Files:**

- Modify: `supervisor.py`
- Modify: `main.py`
- Modify: `tests/test_supervisor.py`
- Modify: `tests/test_main.py`

**Interfaces:**

- `create_supervisor_app(...)` additionally consumes the Source service and
  shared delegation registry.
- `SupervisorRuntime.from_app(...)` consumes the same registry.
- FastAPI lifespan creates one `SourceExpertService` using the existing shared
  Vertex client; it creates no new client and owns no separate shutdown path.

- [ ] Write a failing supervisor test proving `analyze_source` is registered
  only when its service and registry are injected, while Research remains the
  sole sub-agent and memory-tool registration remains unchanged.
- [ ] Verify RED against the current application definition.
- [ ] Register the Source tool and add restrained routing instructions:
  explicit relevant public URL, no incidental URL, no broad discovery, no
  repeat Source invocation, and Agent_Col retains the final response.
- [ ] Write a failing lifespan test proving the Source service receives the
  existing Vertex client and the runtime receives the same delegation
  registry as the tool.
- [ ] Wire the service and registry through `main.py` without adding state or
  persistence authority.
- [ ] Verify GREEN with
  `venv/bin/pytest -q tests/test_supervisor.py tests/test_main.py`.

### Task 5: Focused regression verification and manual handoff

**Files:**

- Modify only if required by an already failing approved assertion.

- [ ] Run the new RED/GREEN files and directly related shared contracts:

```bash
venv/bin/pytest -q tests/test_expert_delegation.py tests/test_source_expert.py tests/test_source_expert_service.py tests/test_source_expert_tool.py tests/test_source_expert_runtime.py tests/test_supervisor.py tests/test_supervisor_runtime.py tests/test_main.py
```

- [ ] Run Python compilation for all changed production modules.
- [ ] Run `git diff --check` and inspect warnings, skips, and exit codes.
- [ ] Run the existing live provider smoke:

```bash
source venv/bin/activate && python3 smoke_test_source_expert.py
```

- [ ] Hand off one explicit-URL `/api/chat` request and one ordinary no-tool
  regression request. The explicit-URL result should contain an Agent_Col final
  response, one completed `url_context` action, and at least one validated
  citation. The ordinary request should contain neither Source action nor
  citation.
- [ ] Stop at **implemented, pending manual verification**. Do not checkpoint
  until the repository owner confirms both runtime checks.

## Stop and revise conditions

Stop and request a revised approval if implementation evidence shows that:

- ADK executes the Source FunctionTool before its atomic budget claim;
- `ToolContext` cannot safely carry the server-owned invocation token;
- the two internal Source calls consume or bypass the supervisor's ADK LLM
  call budget unexpectedly;
- a failed Source result cannot be returned to Agent_Col without exposing
  unsafe provider data or aborting the entire turn;
- Source receipts cannot be separated from model-authored prose; or
- the change requires a dependency upgrade, public schema change, Firestore
  write, new infrastructure component, or broader expert refactor.

## Manual acceptance targets

1. `GET /` remains `{"status":"online"}`.
2. An explicit request to analyze one supplied public URL produces exactly one
   Agent_Col final response, one `url_context` action, and one or more citations
   derived from validated Source evidence.
3. A stable explanation with no materially relevant URL produces no Source
   action and no citations.
4. Existing Research and governed-memory behavior remains unchanged.
5. No Source invocation creates or modifies Firestore data.
