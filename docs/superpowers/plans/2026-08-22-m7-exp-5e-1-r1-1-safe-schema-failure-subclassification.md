# M7-EXP.5E.1-R1.1 Safe Schema-Failure Subclassification

**Status:** Implemented, pending manual verification

**Date:** 2026-08-22

**Scope:** Content-safe local schema-failure subclassification only

## Goal

Identify which invariant family rejects a non-empty, valid JSON routing
directive after it passes Gemini's provider-safe schema boundary but fails the
canonical local `AgentColRoutingDirective` contract.

This pass adds diagnostic precision. It does not change routing decisions,
prompts, schemas, provider retries, expert execution, or public application
responses.

## Safe diagnostic contract

A `schema_validation_failed` output carries exactly one bounded subreason:

- `route_payload_mismatch`: the selected route and populated payload fields do
  not match;
- `field_constraint_failed`: a known field type, literal, pattern, length, or
  required-field constraint failed;
- `intent_invariant_failed`: a Source or Computation intent violated a local
  cross-field invariant;
- `unexpected_field`: the directive contained a forbidden field;
- `unknown_schema_failure`: the failure did not match a known safe family or
  combined more than one family.

Classification uses only Pydantic error types and structural locations with
input and context explicitly excluded. It does not store or emit rejected
values, model text, user text, validation messages, URLs, numeric inputs, or
objectives.

The decision-only evaluation CLI emits:

```text
model_output_error:schema_validation_failed:<safe_subreason>
```

The exception message remains constant, and the original validation exception
is not retained as its cause or context.

## TDD coverage

- an unclassified Pydantic error maps to `unknown_schema_failure`;
- an absent route-required payload maps to `route_payload_mismatch`;
- a locally rejected empty field maps to `field_constraint_failed`;
- duplicate intent selections map to `intent_invariant_failed`;
- a forbidden field maps to `unexpected_field` without leaking its value;
- the CLI appends only the safe subreason and retains exit code `2`.

## Explicit exclusions

- no routing instruction changes;
- no provider-schema or canonical-schema changes;
- no retry or repair loop;
- no model response or validation-message logging;
- no FastAPI, Firestore, responder, or expert changes;
- no correction of the multi-capability routing contract in this pass.

## Manual verification

Run the bounded cross-capability scenario again:

```bash
python3 tool_belt_routing_check.py --scenario cross-capability-boundary --repetitions 5; routing_exit=$?; printf 'exit=%s\n' "$routing_exit"
```

If a schema validation failure recurs, it must include exactly one safe
subreason and no user or model content. That result determines the next
root-cause correction.
