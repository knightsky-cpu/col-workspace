# M7-EXP.7B.3 Deterministic Orchestration Evaluation Implementation Plan

**Goal:** Add one reproducible offline evaluator that exercises Agent_Col's
production turn service, routing-v3 expert executor, responder projection,
authoritative receipts, timeout reserve, governed-memory separation, and HTTP
idempotency boundary with controlled collaborators only.

**Architecture:** Keep the evaluator outside production request handling. The
runner supplies deterministic routing directives and controlled expert
services to the real `AgentColTurnService` and `AgentColExpertExecutorV3`, then
checks the resulting typed contexts and receipts locally. In-process FastAPI
requests exercise completed replay and conflict translation with a controlled
database boundary. No Vertex call, expert-provider call, external network
request, code execution, or Firestore access is permitted.

**Scope:** Add only the offline orchestration evaluator, its focused tests, and
this plan. Do not change production routing, expert services, responder logic,
FastAPI behavior, memory policy, schemas, dependencies, or persistence.

## Contract

- Exercise `direct`, `clarify`, `source`, `research`, `computation`, and
  `requirements_verification` through the production turn service.
- The routing collaborator returns exactly one fixture-derived directive and
  records the exact projected routing input received from the turn service.
- Direct and clarify call zero cognitive expert services.
- Each expert route calls only its matching controlled service exactly once.
- Completed results produce only the locally derived action and citation
  receipts allowed by the accepted receipt matrix.
- Typed expert failures and the responder-reserve timeout path produce no
  completed cognitive action and no citations; no fallback expert executes.
- Wrong-capability results and forged, missing, or incompatible receipts are
  rejected by `AgentColResponderContextV3` before responder use.
- Instruction-like expert evidence remains untrusted context and cannot create
  a memory proposal or persistent effect in this evaluator.
- Responder failure preserves only precompleted application-authorized effects
  plus already validated expert receipts.
- A completed idempotent replay returns the stored response and performs no
  turn, memory, history, lease, or persistence work.
- A changed request under the same key returns the existing HTTP 409 conflict
  without downstream work.
- Default output contains only scenario IDs, route/capability metadata,
  receipt counts, failure codes, totals, elapsed milliseconds, and exit code.

## Exit semantics

- Exit `0`: every deterministic invariant passes.
- Exit `1`: at least one orchestration, receipt, memory, timeout, or replay
  invariant fails.
- Exit `2`: evaluator configuration or execution prevents a complete result.

## Files

- Create `tool_belt_orchestration_check.py`.
- Create `tests/test_tool_belt_orchestration_check.py`.
- Create this implementation plan.

## TDD cycles

### Cycle 1: six-route production orchestration matrix

1. Write RED tests for one offline command covering all six routes.
2. Require exact projected routing input identity, zero-or-one matching expert
   calls, responder invocation, receipt matrix parity, and metadata-only output.
3. Implement the minimal controlled runner around the real production turn
   service and v3 executor.

### Cycle 2: failure, timeout, and trust probes

1. Write RED tests for typed expert failure, exhausted expert budget, wrong
   capability, forged receipt, responder failure, and instruction-like expert
   evidence.
2. Require no fallback, no completed receipt for failed/timed-out experts, and
   no memory proposal derived from expert content.
3. Implement the minimal probes and classifications.

### Cycle 3: HTTP replay and conflict probes

1. Write RED tests proving in-process replay returns the stored response with
   no downstream access.
2. Write RED tests proving changed-request conflict returns HTTP 409 with no
   downstream access.
3. Implement only the controlled application-state collaborators required to
   exercise the existing FastAPI boundary.

## Focused verification

```bash
venv/bin/pytest -q \
  tests/test_tool_belt_orchestration_check.py \
  tests/test_agent_col_turn_service.py \
  tests/test_agent_col_expert_executor_v3.py \
  tests/test_agent_col_responder_context_v3.py \
  tests/test_main.py \
  -k 'orchestration_check or turn_service or executor_v3 or v3_context or v3_responder or idempotent or replay or expert_receipts'
venv/bin/python -m py_compile tool_belt_orchestration_check.py
git diff --check
```

The full suite is not required because no production behavior changes. The
focused set covers every production boundary directly exercised by the new
offline evaluator.

## Manual verification

```bash
source venv/bin/activate && python3 tool_belt_orchestration_check.py; orchestration_exit=$?; printf 'exit=%s\n' "$orchestration_exit"
```

Expected: every named deterministic probe reports `pass`, the summary reports
zero provider/network/Firestore calls, and the process exits `0`.

## Stop conditions

Stop and revise before expanding scope if the evaluator would require a live
provider, external network request, Firestore, real code execution, production
policy change, route forcing in the live application, new dependency, raw
private/model output, or weakening an accepted receipt or memory invariant.
