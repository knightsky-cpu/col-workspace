# Phase 3B M7-MEM.2 ADK Proposal Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a governed ADK proposal-tool adapter and deterministic runtime
receipt collection without enabling the tool through the public chat route.

**Architecture:** A focused adapter wraps `TrustedMemoryService` with ADK
`FunctionTool`, exposes only category and proposed value to Gemini, and reads
server-owned provenance from invocation state. `SupervisorRuntime` validates
public ADK function-response events into typed action and proposal receipts.
The current production supervisor factory remains tool-free until M7.4 adds
complete FastAPI context, replay, and partial-failure handling.

**Tech Stack:** Python 3.14, `google-adk==2.7.0`, Pydantic v2, pytest,
pytest-asyncio.

**Spec:**
[`docs/superpowers/specs/2026-08-21-phase-3b-trusted-memory-m7-governed-proposal-tool-design.md`](2026-08-21-phase-3b-trusted-memory-m7-governed-proposal-tool-design.md)

## Global constraints

- Agent_Col remains the sole user-facing conversational owner.
- Model-visible tool arguments are exactly `category` and `proposed_value`.
- User, session, source-message, source text, decision state, timestamps,
  leases, provenance, and persistence identifiers remain server-owned.
- The adapter may create only an inactive pending proposal.
- Runtime receipts come only from validated public ADK function responses,
  never model prose.
- At most one distinct successful proposal receipt may exist per invocation.
- Existing session cleanup, timeout, provider-error, and tool-restraint
  behavior must remain green.
- `main.py`, public `ChatResponse`, turn completion/replay, FastAPI error
  mapping, Firestore schema, dependencies, and UI are out of scope.
- The default production `create_supervisor_app()` call remains tool-free so
  an incomplete public side-effect path cannot be exposed.
- Every production behavior begins with an observed failing test.

---

### Task 1: Strict ADK proposal-tool adapter

**Files:**

- Create: `memory_proposal_tool.py`
- Create: `tests/test_memory_proposal_tool.py`

**Interfaces:**

- Produces `create_propose_memory_signal_tool(memory_service) -> FunctionTool`.
- Produces strict pending and rejected tool-response models.
- Produces `parse_memory_proposal_tool_response(value)` for runtime use.
- Consumes the existing `ProposeMemorySignalCommand`,
  `TrustedMemoryService`, and `ProposalTurnLease` contracts.

- [ ] Write a RED declaration test proving the tool module is absent and the
  desired declaration contains only category and proposed value.
- [ ] Implement the minimal async `FunctionTool` factory with injected
  `ToolContext` and verify the declaration omits all server-owned fields.
- [ ] Write RED success and invalid-candidate tests using a specific fake
  service and invocation-state fixture.
- [ ] Implement server-state extraction, service delegation, strict pending
  output, and bounded `invalid_memory_candidate` rejection for local
  validation failures.
- [ ] Write RED parser tests for valid pending/rejected envelopes, extra
  fields, malformed receipts, and content-free failures.
- [ ] Implement the minimum strict response parser and rerun the adapter file.

### Task 2: Explicit supervisor registration and restraint

**Files:**

- Modify: `supervisor.py`
- Modify: `tests/test_supervisor.py`

**Interfaces:**

- Extends `create_supervisor_app(*, memory_service=None)`.
- An injected service registers exactly one governed `FunctionTool`.
- The no-argument production factory remains tool-free through M7.4.

- [ ] Write RED tests for explicit one-tool registration while retaining the
  default tool-free production factory.
- [ ] Implement dependency-injected registration without global mutable
  service state.
- [ ] Write a RED instruction-contract test covering explicit reusable
  current-message feedback, no inference, no sensitive or temporary memory,
  no proposal on decision turns, one-call maximum, pending-not-active wording,
  ambiguity clarification, and default no-tool behavior.
- [ ] Amend the instruction and generalize Agent_Col from an engineering-only
  partner to a cross-domain collaborative partner.
- [ ] Run `tests/test_supervisor.py` and the real offline ADK app-construction
  regression.

### Task 3: Public ADK function-response receipt collection

**Files:**

- Modify: `supervisor_runtime.py`
- Modify: `tests/test_supervisor_runtime.py`

**Interfaces:**

- Adds `memory_proposals: tuple[MemoryProposalReceipt, ...]` to
  `SupervisorTurnResult`.
- Consumes `Event.get_function_responses()` and the strict adapter parser.
- Preserves existing response, action, artifact, citation, and cleanup
  contracts.

- [ ] Write a RED test proving model prose cannot create a receipt while a
  valid `propose_memory_signal` function response can.
- [ ] Implement extraction through the public ADK event API and return the
  validated action and proposal receipt.
- [ ] Write RED tests proving a rejected response emits no receipt, identical
  successes deduplicate, distinct successes conflict, malformed exact-tool
  responses fail closed, and unrelated function responses are ignored.
- [ ] Implement the minimum bounded accumulator and conflict checks.
- [ ] Rerun runtime tests, including provider failure, timeout, exactly-one
  final response, and session deletion regressions.

### Task 4: Offline contract smoke runner

**Files:**

- Create: `smoke_test_memory_proposal_tool_contract.py`
- Create: `tests/test_smoke_test_memory_proposal_tool_contract.py`

**Interfaces:**

- Produces `run_memory_proposal_tool_contract_smoke(...)` with an injected
  service and fixed server context.
- Prints only tool name, the two model argument names, and receipt count.

- [ ] Write a RED import/behavior test for the missing runner.
- [ ] Implement a real `FunctionTool` declaration and invocation against a
  fake service; do not call Gemini or Firestore.
- [ ] Verify the summary excludes source text, memory value, identifiers,
  provider data, and internal state.

### Task 5: Focused and shared verification

**Files:** all files changed above.

- [ ] Run:

```bash
venv/bin/pytest -q \
  tests/test_memory_proposal_tool.py \
  tests/test_supervisor.py \
  tests/test_supervisor_runtime.py \
  tests/test_smoke_test_memory_proposal_tool_contract.py
```

- [ ] Run related trusted-memory and main startup regressions without making
  production chat tool-enabled.
- [ ] Run Python compilation and `git diff --check`.
- [ ] Run the full suite because the ADK supervisor/runtime is shared by chat.
- [ ] Stop as **implemented, pending manual verification**. Do not commit or
  push until the repository owner runs the offline smoke command and accepts
  the pass.

## Stop conditions

- ADK exposes any server-owned parameter to the model declaration.
- Receipt extraction requires private ADK internals rather than
  `Event.get_function_responses()`.
- Invalid or multiple proposal results cannot fail closed deterministically.
- The current FastAPI chat path would become tool-enabled in this pass.
- Logs, errors, or smoke output would reveal source content, memory values,
  identifiers, tool state, or provider payloads.
