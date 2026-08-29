# M7-EXP.5E.1-R2 Multi-Capability Routing Contract Correction

**Status:** Implemented, pending manual verification

**Date:** 2026-08-22

**Scope:** Production routing-v2 policy instruction only

## Verified problem

The unified routing evaluation repeatedly produced a locally valid `source`
directive for a request that required Source analysis, current Research, and
Computation in one response. The directive schema permits exactly one route,
but the production routing instruction previously described each capability
independently without defining the multi-capability conflict rule.

The result was a quality failure rather than a schema or execution failure:
Source was relevant but insufficient to satisfy the complete request.

## Corrected policy

The routing-v2 provider instruction now establishes:

- one routing directive can select at most one expert capability;
- when the complete request materially requires two or more distinct expert
  capabilities, Agent_Col chooses `clarify`;
- the clarification asks which capability to prioritize or whether to proceed
  in stages;
- multiple URLs handled by one Source request remain one capability;
- incidental numeric text requiring no calculation does not create a
  Computation requirement;
- when one expert can satisfy the complete request, Agent_Col selects it.

This remains model-controlled routing. No keyword matcher, deterministic route
override, forced expert call, or multi-expert execution was introduced.

## TDD boundary

The provider-boundary test captures the real `GenerateContentConfig` sent by
`request_agent_col_routing_v2_directive` and verifies that the emitted system
instruction contains the complete bounded policy. The test failed before the
instruction correction and passed after the minimum prompt change.

Offline verification proves that Vertex receives the policy. It cannot prove
probabilistic model compliance, so the targeted live evaluation remains the
manual acceptance gate.

## Explicit exclusions

- no routing or response schema changes;
- no field-constraint correction;
- no provider retries or output repair;
- no deterministic route enforcement;
- no expert, responder, FastAPI, Firestore, or idempotency changes;
- no multi-expert execution;
- no Requirements Verification or Deep Research implementation.

The separately observed intermittent
`schema_validation_failed:field_constraint_failed` remains unresolved and may
still prevent a clean live evaluation independently of this correction.

## Manual verification

Run the targeted decision-only evaluation:

```bash
python3 tool_belt_routing_check.py --scenario cross-capability-boundary --repetitions 5; routing_exit=$?; printf 'exit=%s\n' "$routing_exit"
```

Routing acceptance requires five valid `clarify` decisions whose questions
meaningfully ask the user to prioritize or stage the requested capabilities.
Any provider or schema error remains an execution failure and must not be
counted as routing success.

If targeted routing passes, run the complete one-repetition regression:

```bash
python3 tool_belt_routing_check.py --repetitions 1; routing_exit=$?; printf 'exit=%s\n' "$routing_exit"
```
