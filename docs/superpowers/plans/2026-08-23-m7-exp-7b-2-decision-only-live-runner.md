# M7-EXP.7B.2 Decision-Only Live Evaluation Runner Implementation Plan

**Goal:** Cut the existing tool-belt routing CLI over to the accepted routing-v3 fixture, provider, and pure evaluator while preserving fixed attempts, metadata-only reporting, and a strict no-expert/no-persistence boundary.

**Architecture:** Keep `tool_belt_routing_check.py` as the single operator-facing decision-only CLI. Replace its v2 dependencies with the production v3 provider and the accepted 7B.1 contracts. The runner accepts either a one-attempt baseline mode or fixture-declared repetitions, calls the routing provider exactly once per planned attempt, evaluates the returned directive locally, and emits only allowlisted metadata. It never invokes `AgentColTurnService`, an expert executor, FastAPI, Firestore, or a responder.

**Scope:** Modify only the runner and its focused tests, plus this plan. Do not change routing prompts, schemas, fixtures, evaluators, production orchestration, dependencies, or persistence.

## Contract

- Modes are `baseline` and `declared`.
- `baseline` runs every selected scenario once.
- `declared` runs each selected scenario exactly `scenario.live_repetitions` times.
- `--scenario` selects one exact fixture ID; missing IDs are configuration errors.
- No automatic retry is permitted.
- Every planned attempt is reported, even after a prior semantic or execution failure.
- Exit `0`: every automatable selected attempt passes.
- Exit `1`: at least one semantic route or candidate-selection finding occurs and no inconclusive execution failure occurs.
- Exit `2`: configuration, timeout, provider, model-output, or directive-input failure prevents a complete conclusion. Semantic findings remain visible when exit `2` takes precedence.
- Manual-review classifications are emitted but do not independently change exit `0`.
- Output may contain fixture/schema versions, commit, provider/model identifiers, scenario IDs, run numbers, expected/actual routes, finding codes, failure classifications, counts, and elapsed milliseconds.
- Output may not contain scenario messages, projected values or text, model-authored objectives/constraints/questions, provider response text, credentials, expert output, or Firestore content.

## Files

- Modify `tests/test_tool_belt_routing_check.py`.
- Modify `tool_belt_routing_check.py`.
- Create this implementation plan.

## Task 1: v3 modes and attempt policy

1. Write RED tests proving baseline executes one attempt and declared mode uses each scenario's fixture-owned repetition count.
2. Prove selection of a missing scenario is a configuration error and performs no provider call.
3. Implement the minimal mode and selection boundary using `ToolBeltRoutingV3Scenario`.
4. Verify GREEN with only the named tests.

## Task 2: v3 findings, failures, and content-safe output

1. Write RED tests proving route/candidate findings map to exit `1`.
2. Write RED tests for v3 timeout, provider, structured-output field locator, and directive-input classifications.
3. Prove execution failures take exit precedence without suppressing semantic results.
4. Prove manual-review markers do not expose clarification prose.
5. Prove output excludes fixture messages and model-authored intent text.
6. Implement the minimal v3 exception and evaluator integration.

## Task 3: live Vertex boundary and CLI cutover

1. Write RED tests proving the live runner uses Vertex ADC settings, passes the exact production v3 routing input, calls only the injected routing provider, and closes both clients.
2. Write RED CLI tests for `--mode baseline|declared`, the v3 fixture path, and rejection of the removed arbitrary `--repetitions` surface.
3. Add a metadata header and final summary with fixture/schema version, repository commit, model/provider identifiers, planned/provider-call counts, manual-review count, and elapsed time.
4. Implement the minimal v3 live runner and CLI cutover.

## Focused verification

```bash
venv/bin/pytest -q \
  tests/test_tool_belt_routing_check.py \
  tests/test_tool_belt_routing_evaluation_v3.py \
  tests/test_agent_col_routing_provider_v3.py \
  tests/test_agent_col_routing_v3.py
venv/bin/python -m py_compile tool_belt_routing_check.py
git diff --check
```

The full suite is not required because the pass changes only the isolated evaluation CLI; production routing, orchestration, persistence, and API behavior remain unchanged.

## Manual verification

After implementation, run one call in each mode:

```bash
source venv/bin/activate && python3 tool_belt_routing_check.py --scenario stable-explanation --mode baseline; printf 'exit=%s\n' "$?"
source venv/bin/activate && python3 tool_belt_routing_check.py --scenario explicit-no-tools-with-url --mode declared; printf 'exit=%s\n' "$?"
```

Expected behavior:

- the baseline emits one attempt;
- the declared restraint case emits exactly five attempts;
- every valid restraint decision is `direct`;
- no expert action, citation, response, or Firestore write occurs;
- output remains metadata-only;
- exit is `0` only when all automatable selected checks pass.

## Stop conditions

Stop and revise before expanding scope if implementation would require expert execution, production prompt/schema changes, route forcing, retries, persistence, raw diagnostic content, fixture weakening, new dependencies, or any provider call during automated tests.
