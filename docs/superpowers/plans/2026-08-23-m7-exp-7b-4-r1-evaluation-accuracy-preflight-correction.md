# M7-EXP.7B.4-R1 Evaluation Accuracy and Preflight Correction

## Status

Approved for implementation on 2026-08-23 after the first bounded live run
returned exit `2`.

## Verified root causes

- The clarification response requested exactly the missing operands but the
  evaluator required a literal question mark.
- Research executed but returned `missing_grounding_chunks`; the public API
  correctly omitted a completed action, while the evaluator called that a
  semantic failure instead of an unobservable/inconclusive expert outcome.
- The computation numeric projection was complete, but the provider directive
  failed local input cross-validation. The current exception does not expose a
  content-safe reason code.
- The reserved `.invalid` failed-Source URL is intentionally rejected by the
  production public-URL projector, so the fixture never reached Source.

## Bounded correction

1. Remove punctuation-based clarification judgment. A receipt-free,
   citation-free clarification remains `manual_review_required`.
2. Classify a 200 response with no expected expert success receipt and no
   citations as `expert_outcome_unobservable` with exit `2`, not as a semantic
   route failure.
3. Preflight the fixed catalog through the production URL, numeric, and text
   projectors before any HTTP request. The `.invalid` case must return
   `configuration_error` with zero requests.
4. Add allowlisted `RoutingDirectiveInputReason` values to routing-v3 input
   validation and log only the reason code at the turn-service boundary.
5. Preserve generic exception text and generic public HTTP errors. Do not log
   prompts, directives, candidate values, IDs, or provider payloads.

## Files expected to change

- `tool_belt_live_e2e_check.py`
- `agent_col_routing_v3.py`
- `agent_col_turn_service.py`
- `tests/test_tool_belt_live_e2e_check.py`
- `tests/test_agent_col_routing_v3.py`
- `tests/test_agent_col_turn_service.py`
- This plan document

## Exclusions

- No routing prompt changes.
- No route forcing or retry policy.
- No replacement failed-Source fixture yet.
- No public response-schema change.
- No Research or Computation expert implementation change.
- No new provider call during automated verification.

## Acceptance evidence

- Focused RED/GREEN evidence for each correction.
- The fixed default catalog fails preflight before HTTP because its controlled
  failed-Source fixture is invalid under production policy.
- A valid injected catalog still executes the exact bounded sequence in unit
  tests.
- Safe routing mismatch reasons are asserted without private content leakage.
- All directly related evaluator, routing-v3, turn-service, and idempotency
  tests pass.
