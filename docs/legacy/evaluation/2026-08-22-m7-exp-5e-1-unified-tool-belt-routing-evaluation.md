# M7-EXP.5E.1 Unified Tool-Belt Routing Evaluation Plan

**Status:** Implemented, pending manual verification

**Date:** 2026-08-22

**Scope:** Decision-only evaluation; no production routing changes and no
expert execution

## Goal

Evaluate Agent_Col's production routing-v2 judgment across the complete
currently implemented core tool belt in one strict, reproducible harness:

- direct response and tool restraint;
- focused clarification;
- Source Expert selection and exact URL provenance;
- Research Expert selection;
- Computational Expert selection and exact numeric provenance;
- one deliberately multi-capability request that must be clarified rather
  than over-delegated.

The harness measures the routing decision only. It does not call Source,
Research, or Computation experts, execute the production turn service, write
Firestore data, or change Agent_Col's routing prompt.

## Architecture

```text
Versioned scenario fixture
    |
    v
Deterministic production URL and numeric projection
    |
    v
Production routing-v2 provider on Vertex AI
    |
    v
Locally validated AgentColRoutingDirective
    |
    v
Pure expected-route and candidate-fidelity evaluator
    |
    v
Metadata-only result and bounded exit code
```

The provider receives the same `AgentColRoutingInput` shape used by the
production turn service. No expert is constructed or invoked. This isolates
Agent_Col's routing judgment from provider execution, response synthesis,
persistence, and network behavior of individual experts.

## Contract boundaries

- Agent_Col remains the decision maker. The fixture evaluates decisions; it
  does not force routes through keywords or deterministic dispatch rules.
- Candidate projection uses production URL and numeric projectors.
- The fixture contains only user messages, expected route metadata, expected
  server candidate IDs, and manual-review classifications.
- Exact Source URL candidate membership is evaluated without assigning
  semantic meaning to selection order.
- Exact computation scalar membership, series grouping and source order within
  each group, precision candidate, and precision mode are evaluated. Scalar
  and group tuple order are not treated as semantic because their names,
  rather than outer tuple position, carry meaning.
- Model-generated objectives, names, constraints, and clarification prose are
  not emitted by the CLI.
- The pure evaluator does not judge the semantic quality of model-generated
  computation input names or objectives. Production local validation still
  enforces their safety and shape; this pass measures route and deterministic
  candidate provenance, not free-text interpretation quality.
- Clarification quality and the cross-capability case remain explicit manual
  semantic-review targets.
- One run per scenario is the default. Repetition is bounded to five and is
  intended for a specifically selected scenario after a baseline finding.
- Exit `0` means every selected decision matched the fixture contract.
- Exit `1` means at least one valid directive failed routing or candidate
  fidelity.
- Exit `2` means configuration, provider, timeout, structured-output, or
  directive/input validation prevented a quality conclusion.

## Failure classification

Quality failures are separated into:

- `unnecessary_expert`;
- `missing_expert`;
- `wrong_expert`;
- `route_mismatch`;
- `url_selection_mismatch`;
- `scalar_selection_mismatch`;
- `series_selection_mismatch`;
- `precision_selection_mismatch`.

Execution failures are separated into:

- `timeout_error`;
- `model_output_error`;
- `provider_error`;
- `directive_input_error`;
- `configuration_error`.

This distinction prevents provider instability from being mislabeled as poor
Agent_Col judgment and prevents a schema-valid but wrong candidate choice from
being counted as a routing success.

## Approved exclusions

- no `/api/chat` calls;
- no FastAPI or Firestore interaction;
- no specialist execution or receipts;
- no production prompt or routing changes;
- no deterministic route enforcement;
- no Requirements Verification Expert;
- no Deep Research;
- no multi-agent or multi-expert execution;
- no persistence of evaluation inputs or outputs.

## TDD sequence

1. Add strict fixture loading and production candidate projection tests.
2. Add semantic-invariant tests for contradictory or stale fixture metadata.
3. Add pure evaluation tests for restraint, route, URL, numeric grouping, and
   precision fidelity.
4. Add a versioned fixture spanning all five route outcomes and boundary
   cases.
5. Add decision-only runner tests for result classification, safe output,
   bounded repetition, provider failures, Vertex ADC configuration, and
   client cleanup.
6. Run focused routing-v2 regression tests and a metadata-only live baseline.

## Manual verification command

Run from the repository root with the project virtual environment activated:

```bash
python3 tool_belt_routing_check.py --repetitions 1; printf 'exit=%s\n' "$?"
```

The FastAPI server does not need to be running. The command uses Vertex AI via
the repository's existing ADC configuration. It performs one routing-only
model call per fixture scenario and does not write Firestore.

If one valid decision differs from the fixture, rerun only that scenario:

```bash
python3 tool_belt_routing_check.py --scenario SCENARIO_ID --repetitions 3; printf 'exit=%s\n' "$?"
```

Do not treat a repeated mismatch as authorization to tune the production
router. Record the evidence and propose a separate correction pass.
