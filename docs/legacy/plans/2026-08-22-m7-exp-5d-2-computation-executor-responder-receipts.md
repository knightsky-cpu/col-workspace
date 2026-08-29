# M7-EXP.5D.2 Computation Executor, Responder Projection, and Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. This
> repository uses inline, approval-gated passes unless the owner explicitly
> authorizes subagents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert a locally validated routing-v2 computation directive into
one bounded Computational Expert execution, minimize its responder context,
and derive an authoritative completion receipt without cutting production chat
over to routing v2.

**Architecture:** Parallel v2 executor and responder modules preserve the
production v1 import graph. Deterministic application code resolves numeric
candidate IDs into `ComputationExpertInput`; the existing service returns a
full validated result; a pure projector removes raw code and output before the
responder boundary. Receipts are derived locally and only from completed
projected results.

**Tech Stack:** Python 3.14, Pydantic v2, Google ADK, Vertex AI, Gemini 3.6
Flash, pytest, pytest-asyncio

**Spec:**
`docs/superpowers/specs/2026-08-22-phase-3b-m7-exp-5c-computational-routing-provenance-design.md`

## Global Constraints

- Production `main.py`, `agent_col_turn_service.py`,
  `agent_col_expert_executor.py`, `agent_col_responder_context.py`, and routing
  v1 modules remain unchanged.
- Do not advertise computation through `/api/chat` in this pass.
- Execute zero or one expert per directive; experts never call other experts.
- Resolve operands exclusively from current-message numeric candidates already
  validated by `agent_col_routing_v2`.
- Never accept an expression, executable code, raw execution output, file,
  URL, profile value, history value, identifier, or credential from routing.
- `ComputationExpertInput.inputs.expression` is always `None`.
- Full execution evidence stays internal. Responder context excludes raw code
  and raw output.
- A completed validated result derives exactly one
  `run_computation/completed` action; every other status derives no receipt.
- Expected provider/service failures become contentless typed results.
  Unexpected programming or configuration failures remain fatal.
- Do not add active turn-budget enforcement, FastAPI wiring, persistence,
  retries, or multi-expert chaining; those belong to M7-EXP.5D.3 or later.
- No implementation-step commits. Checkpoint only after manual acceptance.

---

### Task 1: Bounded computation responder projection and receipts

**Files:**
- Modify: `computational_expert.py`
- Modify: `schemas.py`
- Test: `tests/test_computational_expert.py`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Produces: `ComputationResponderPayload`
- Produces: `ComputationResponderEvidence`
- Produces: `ComputationResponderResult`
- Produces:
  `project_computation_responder_result(result: ComputationExpertResult) -> ComputationResponderResult`
- Produces:
  `build_computation_receipts(result: ComputationResponderResult) -> ComputationExpertReceipts`

- [ ] Write RED tests proving a completed projection retains only method,
  normalized inputs, result text, limitations, and derived execution counts.
  Assert serialized projection text contains neither the executed code nor raw
  execution output.
- [ ] Write RED tests proving every noncompleted status remains contentless.
- [ ] Write RED tests proving completed results derive exactly
  `AgentActionReceipt(action_name="run_computation", status="completed")`,
  while all other statuses derive no actions and computation never derives
  citations.
- [ ] Write a RED schema test proving `run_computation` is accepted and an
  unknown action remains rejected.
- [ ] Run:
  `venv/bin/pytest -q tests/test_computational_expert.py tests/test_schemas.py -k 'computation_responder or run_computation'`
  and confirm failures are caused only by missing projection/receipt behavior.
- [ ] Add strict frozen projection models. Reuse the validated
  `ComputationInputs` and bounded result text. Represent successful execution
  with `execution_verified: Literal[True]` plus the four server-derived count
  fields; omit `execution_runs` entirely.
- [ ] Add `ComputationExpertReceipts` as a frozen dataclass containing bounded
  action and citation tuples. Add `run_computation` to
  `AgentActionReceipt.action_name`.
- [ ] Implement the two pure derivation functions and rerun both focused test
  files to GREEN.

### Task 2: Parallel routing-v2 executor and deterministic request builder

**Files:**
- Create: `agent_col_expert_executor_v2.py`
- Create: `tests/test_agent_col_expert_executor_v2.py`
- Read only: `agent_col_expert_executor.py`

**Interfaces:**
- Produces: `AgentColExpertExecutorV2ConfigurationError`
- Produces:
  `build_computation_expert_input(directive, routing_input) -> ComputationExpertInput`
- Produces: `AgentColExpertExecutorV2`
- Consumes: Source, Research, and Computational Expert services.
- Returns: `AgentColResponderContextV2` from Task 3.

- [ ] Write RED request-construction tests using literals with exact expected
  values. Cover scalars, ordered series, percent/currency units, decimal-place
  and significant-figure precision, copied objective/constraints, and
  `expression is None`.
- [ ] Verify RED because the v2 executor module does not exist.
- [ ] Implement the pure builder. It must first call
  `validate_routing_directive_for_input`, resolve from one candidate-ID map,
  and instantiate the existing strict `ComputationExpertInput`.
- [ ] Rerun request-construction tests to GREEN.
- [ ] Write the next RED tests proving stable capability order
  `(source, research, computation)`, zero experts for direct/clarify, exactly
  one selected service call, no fallback, and configuration mismatch rejection
  before expert access.
- [ ] Add computation service success tests proving the executor projects the
  full result, derives its exact receipt, and returns no citations.
- [ ] Add failure tests for `rejected_input`, `unavailable`, `timed_out`, and
  `invalid_output`. Each result must be contentless with no receipt. Use a
  deliberately bypassed invalid internal model only to exercise construction
  drift; do not weaken canonical schemas.
- [ ] Implement the executor with explicit route branches. Catch only the
  documented service errors and Pydantic request-construction failures.
  Unexpected exceptions propagate.
- [ ] Run:
  `venv/bin/pytest -q tests/test_agent_col_expert_executor_v2.py`
  and confirm GREEN.

### Task 3: Parallel routing-v2 responder context

**Files:**
- Create: `agent_col_responder_context_v2.py`
- Create: `tests/test_agent_col_responder_context_v2.py`
- Read only: `agent_col_responder_context.py`

**Interfaces:**
- Produces: `AgentColResponderContextV2`
- Produces:
  `build_agent_col_responder_v2_model_context(context) -> types.Content`
- The discriminated result union contains Source, Research, and bounded
  Computation responder results.

- [ ] Write RED tests for direct/clarify isolation and exact Source/Research
  receipt parity with v1.
- [ ] Write RED computation tests proving route-capability matching, exact
  receipt derivation, no citations, contentless failures, and rejection of
  changed or fabricated receipts.
- [ ] Write a RED serialization test proving the responder prompt contains the
  bounded computation projection but excludes executed code, raw output,
  current message, profile, project/session/user IDs, idempotency key, and
  credentials.
- [ ] Implement a strict frozen context mirroring the v1 authority language and
  using routing-v2 types. Derive expected receipts by concrete result type.
- [ ] Run:
  `venv/bin/pytest -q tests/test_agent_col_responder_context_v2.py`
  and confirm GREEN.

### Task 4: Reproducible live computation-pipeline smoke runner

**Files:**
- Create: `smoke_test_agent_col_computation_pipeline.py`
- Create: `tests/test_smoke_test_agent_col_computation_pipeline.py`

**Interfaces:**
- Command: `python3 smoke_test_agent_col_computation_pipeline.py`
- Exit `0`: one completed computation, one exact receipt, bounded responder
  projection, no citations, no raw code/output in serialized context.
- Exit `1`: locally valid execution completes but an acceptance invariant does
  not match.
- Exit `2`: configuration, provider, timeout, validation, or service failure.

- [ ] Write RED tests for exact Vertex ADC client settings, construction of the
  existing `ComputationalExpertService`, temporary resource cleanup through
  that service, safe metadata-only output, exit classification, and no
  production FastAPI invocation.
- [ ] Verify RED because the runner does not exist.
- [ ] Implement a single fixed series scenario using the accepted six-value
  routing fixture and a computation-only executor configuration. Do not call
  Source, Research, FastAPI, or Firestore.
- [ ] Run:
  `venv/bin/pytest -q tests/test_smoke_test_agent_col_computation_pipeline.py`
  and confirm GREEN.

### Task 5: Focused verification and manual acceptance gate

**Files:**
- Verify all files above.
- Verify production files named in Global Constraints remain unchanged from
  checkpoint `b80256c`.

- [ ] Run the focused new and regression suites:

```bash
venv/bin/pytest -q \
  tests/test_computational_expert.py \
  tests/test_computational_expert_service.py \
  tests/test_schemas.py \
  tests/test_agent_col_routing_v2.py \
  tests/test_agent_col_expert_executor_v2.py \
  tests/test_agent_col_responder_context_v2.py \
  tests/test_smoke_test_agent_col_computation_pipeline.py \
  tests/test_agent_col_expert_executor.py \
  tests/test_agent_col_responder_context.py
```

- [ ] Compile every new/modified Python module and run `git diff --check`.
- [ ] Run `git diff --exit-code b80256c` over `main.py`,
  `agent_col_turn_service.py`, both production v1 executor/responder/routing
  modules, Firestore modules, and idempotency modules.
- [ ] Report **implemented, pending manual verification**. State explicitly
  that `/api/chat` still cannot select or execute computation.
- [ ] User runs:
  `source venv/bin/activate && python3 smoke_test_agent_col_computation_pipeline.py; printf 'exit=%s\n' "$?"`
- [ ] Accept only when the runner reports one completed computation, exact
  `run_computation` receipt, bounded responder context, and `exit=0`.
  Firestore inspection is not required because this pass performs no
  persistence.

## Stop conditions

Stop and propose a revised pass before expanding scope if:

- deterministic request construction cannot preserve exact candidate values,
  order, units, or precision;
- responder serialization contains raw code or raw execution output;
- a failed computation can derive a receipt;
- Source or Research behavior regresses;
- executor integration requires turn-service, FastAPI, lifespan, Firestore,
  idempotency, dependency, or active-budget changes;
- the live Computational Expert cannot satisfy the fixed bounded scenario.
