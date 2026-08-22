# M7-EXP.5E.1-R2.1 Safe Field-Constraint Locator

**Status:** Implemented, pending manual verification

**Date:** 2026-08-22

**Scope:** Content-safe field and constraint diagnostics only

## Verified problem

After the multi-capability routing correction selected `clarify` consistently
in a targeted five-run evaluation, the complete routing harness intermittently
returned:

```text
model_output_error:schema_validation_failed:field_constraint_failed
```

The provider-safe schema strips local string length and pattern constraints.
The canonical local directive restores those constraints and can therefore
reject provider-accepted structured output. The prior diagnostic identified
the failure family but not the exact canonical field or constraint.

## Safe locator contract

For one allowlisted field-constraint failure, the decision-only CLI now emits:

```text
model_output_error:schema_validation_failed:field_constraint_failed:<field>:<constraint>
```

Allowlisted field families are:

- `schema_version`;
- `route`;
- `clarifying_question`;
- `source_intent`;
- `research_intent`;
- `computation_intent`.

Allowlisted constraint identifiers are derived from the bounded Pydantic
field-error types already recognized by the schema classifier, including
literal, enum, required-field, type, length, and pattern failures.

Multiple errors, unknown fields, unknown locations, or unknown constraint
types collapse to:

```text
unknown_field:unknown_constraint
```

Classification reads only `ValidationError.errors()` with URL, context, and
input data explicitly excluded. It does not retain or emit rejected values,
validation messages, user text, model text, URLs, objectives, questions,
identifiers, or numeric inputs. The original validation exception is still
removed from the raised exception's cause and context.

## TDD coverage

- empty clarification maps to
  `clarifying_question:string_too_short`;
- an over-300-character clarification maps to
  `clarifying_question:string_too_long`;
- a wrong schema literal maps to `schema_version:literal_error`;
- an invalid route maps to `route:enum`;
- nested Source, Research, and Computation field failures map only to their
  top-level allowlisted intent families;
- multiple and unrecognized failures collapse to the safe fallback;
- the CLI emits only the bounded field and constraint identifiers.

## Explicit exclusions

- no routing-instruction changes;
- no provider-safe or canonical schema changes;
- no truncation, coercion, retry, or structured-output repair;
- no model response or validation-message logging;
- no FastAPI, Firestore, responder, expert, or idempotency changes;
- no checkpoint before manual acceptance.

## Manual verification

Run the complete one-repetition routing harness:

```bash
python3 tool_belt_routing_check.py --repetitions 1; routing_exit=$?; printf 'exit=%s\n' "$routing_exit"
```

If the intermittent failure recurs, it must include one safe field and
constraint pair and no rejected content. If it does not recur, one bounded
five-run cross-capability evaluation may be used to seek the existing
intermittent failure without increasing the harness repetition limit.
