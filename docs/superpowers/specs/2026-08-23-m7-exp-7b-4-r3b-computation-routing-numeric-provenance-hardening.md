# M7-EXP.7B.4-R3B Computation Routing Numeric-Provenance Hardening

## Status

Implemented, pending manual verification on 2026-08-23.

## Goal

Make the Vertex routing contract explicitly match Agent_Col's authoritative
local computation validator so valid calculations do not fail merely because
the routing model repeats an operand or precision value in a free-text field.

## Verified root cause

The failed live computation had a complete deterministic projection:

- `number-1` through `number-6` represented the six operands;
- `number-7` represented the requested decimal precision;
- `numeric_projection_incomplete` was false.

A locally constructed directive selecting that series and precision passed the
authoritative validator. The live request failed earlier with the content-safe
reason `routing_directive_input:numeric_task_text`, which proves that a
provider-generated computation directive placed numeric-like syntax in its
`objective` or `constraints` field.

The provider instruction previously prohibited raw operands but did not state
the stronger local rule: computation task text may contain no digits or other
numeric-like syntax. The provider-safe JSON Schema also gave those fields no
description after unsupported pattern constraints were removed.

## Decision

Keep the local validator unchanged and strengthen only the provider-facing
routing contract:

1. Computation `objective` and `constraints` contain no digits or numeric-like
   syntax.
2. Every operand is selected through `scalar_inputs` or `series_inputs` numeric
   candidate IDs.
3. Precision is selected through `precision.digits_numeric_id`.
4. A shape-only example demonstrates the separation while explicitly requiring
   selection of the actual IDs from the current routing input.
5. Provider-safe schema descriptions repeat the numeric-free text requirement
   at the affected fields.

## Versioned live scenario

The routing fixture now contains `computation-series-precision`, using the
exact request that failed the bounded live evaluation. Its authoritative
expectation is:

```text
route: computation
series: number-1 through number-6
precision ID: number-7
precision mode: decimal_places
```

The existing routing policy assigns every standard expert scenario three
declared repetitions. R3B preserves that policy rather than creating a
special five-attempt computation rule.

## Preserved invariants

- The local `numeric_task_text` rejection remains authoritative.
- The model still chooses whether Computation is materially needed.
- No deterministic keyword router or route forcing is introduced.
- No hidden retry or automatic provider repair is introduced.
- The computation executor receives only locally validated projections.
- No Computational Expert, FastAPI, Firestore, response, or persistence
  behavior changes.

## Exclusions

- No relaxed numeric-text validation.
- No local rewriting or redaction of model-authored routing directives.
- No provider retry policy.
- No computation algorithm or execution-environment change.
- No change to expert delegation depth or count.

## Manual verification contract

Run the exact decision-only scenario in declared mode:

```bash
python3 tool_belt_routing_check.py --scenario computation-series-precision --mode declared
```

Expected:

- three attempts are reported;
- every attempt selects `computation` with no directive-input error;
- summary reports `planned_attempts=3`, `provider_calls=3`, and `exit=0`;
- shell exit status is `0`.

Only after that succeeds should the complete eight-request live E2E evaluation
be rerun with a fresh run ID. Its computation probe must return HTTP `200`, a
completed `run_computation` receipt, `19.5000`, `5.1235`, and no citations.

If `numeric_task_text` recurs after this correction, stop. The next decision is
architectural and must consider a separately approved bounded provider
correction interaction rather than weakening provenance or stacking another
undocumented prompt tweak.
