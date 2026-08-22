# M7-EXP.5E.1-R1 Safe Routing Output Diagnostics

**Status:** Implemented, pending manual verification

**Date:** 2026-08-22

**Scope:** Content-safe routing structured-output diagnostics only

## Goal

Distinguish why the routing-v2 provider rejected a model response after the
M7-EXP.5E.1 cross-capability evaluation reported an undifferentiated
`model_output_error`.

This pass adds diagnostic evidence. It does not change the routing policy,
provider schema, model configuration, retry behavior, or expert execution.

## Diagnostic contract

`AgentColRoutingV2ProviderOutputError` carries exactly one internal reason:

- `missing_response_text`: the provider returned no usable text;
- `invalid_json`: the provider text was not valid JSON;
- `schema_validation_failed`: valid JSON did not satisfy the canonical local
  `AgentColRoutingDirective` contract.

The exception message remains the existing constant:

```text
Routing v2 provider returned invalid structured output.
```

The original parsing or validation exception is not retained as an exception
cause or context. This prevents rejected provider text and Pydantic input
details from entering tracebacks through exception chaining.

The decision-only evaluation CLI emits only:

```text
model_output_error:<reason_code>
```

It does not emit the provider response, validation locations, user message,
URL candidates, numeric candidates, objectives, or identifiers beyond the
already public fixture scenario ID and repetition number.

## TDD coverage

- Blank and non-string response text map to `missing_response_text`.
- Malformed JSON maps to `invalid_json`.
- Wrong schema versions, forbidden fields, and invalid route payloads map to
  `schema_validation_failed`.
- Exception messages and representations contain no rejected content.
- Invalid JSON and schema failures retain neither exception cause nor context.
- The CLI projects only the stable reason code and retains exit code `2`.
- Existing provider, timeout, directive-input, and quality classifications
  remain unchanged.

## Explicit exclusions

- no routing system-instruction changes;
- no multi-capability decision correction;
- no provider retry;
- no response-schema relaxation;
- no logging of model output or validation errors;
- no FastAPI, Firestore, expert, responder, or public response changes;
- no attempt to diagnose the separate Source-versus-clarify variation in the
  same source-changing pass.

## Manual verification

After focused automated checks pass, rerun only the failing scenario:

```bash
python3 tool_belt_routing_check.py --scenario cross-capability-boundary --repetitions 5; routing_exit=$?; printf 'exit=%s\n' "$routing_exit"
```

If invalid structured output recurs, the line must contain exactly one of the
three stable reason codes and no model or user content. The result identifies
the smallest subsequent provider-compatibility correction. Route mismatches
remain separately reported as quality findings.
