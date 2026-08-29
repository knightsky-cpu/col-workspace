# M7-EXP.7B.4-R2 Controlled Failure Scenario Contract Reconciliation

## Status

Approved for implementation on 2026-08-23.

## Decision

Remove the synthetic `failed-source` case from the default live HTTP gate.
Keep controlled failed-expert and timeout proof in the deterministic 7B.3
orchestration evaluator.

This is a layer correction, not reduced coverage. The live boundary cannot
observe whether a response without an expert receipt came from a direct route,
a clarification route, or a selected expert that did not complete. The
deterministic orchestration boundary can observe and control that distinction.

## Verified problem

The first 7B.4 live catalog used this reserved URL:

```text
https://agent-col-evaluation.example.invalid/
```

Production URL projection correctly rejects `.invalid` hosts before routing.
Consequently, that case cannot exercise Source.

Replacing it with an arbitrary public URL that is expected to fail would not
create a reproducible test:

- DNS, redirects, hosting, caching, and page contents can change;
- Vertex URL Context may classify or retrieve the same URL differently over
  time;
- Agent_Col retains model-controlled routing and may clarify or answer directly;
- a public `ChatResponse` intentionally carries no completed action or citation
  for a noncompleted expert;
- absence of a receipt therefore cannot prove that Source executed and failed.

The correct evaluator response is to stop claiming that the public boundary
can prove an internal failed-expert event.

## Evidence already owned by each layer

### Deterministic 7B.3 orchestration gate

The offline evaluator owns application-controlled failure invariants. It uses
the production turn service and expert executor with controlled collaborators
to prove:

- Source is selected and called exactly once;
- an unavailable Source result reaches Agent_Col as a typed noncompleted result;
- no fallback expert executes;
- no completed cognitive action or citation is emitted;
- Agent_Col still owns the final response;
- exhausted expert budget produces the same no-receipt boundary;
- idempotent replay and conflict handling perform no duplicate downstream work.

These assertions are deterministic and must remain a 100-percent gate.

### Live 7B.4 HTTP gate

The live evaluator owns behavior observable through the public FastAPI
contract:

- direct tool restraint;
- clarification when required input is missing;
- completed Source with validated citations;
- completed Research with validated citations;
- completed Computation with known numerical results;
- completed Requirements Verification with its authoritative action receipt;
- exact idempotent replay;
- changed-request conflict.

If any expected live expert returns no completed receipt and no citations, the
case remains `expert_outcome_unobservable` and the run exits `2`. This records
provider or expert degradation honestly without claiming an internal route.

## Considered approaches

### Option A: Separate deterministic failure proof from live success proof

**Decision: selected.**

Remove `failed-source` from the live catalog. Retain the existing deterministic
failed-expert and timeout probes in 7B.3. Keep spontaneous live expert failures
inconclusive.

Advantages:

- preserves reproducibility;
- measures only evidence visible at each boundary;
- retains Agent_Col's routing authority;
- requires no production debug surface or infrastructure;
- avoids consuming provider quota on a deliberately unreliable request.

Trade-off:

- one command does not prove every internal failure invariant. The submission
  must present 7B.3 and 7B.4 as complementary evaluation layers.

### Option B: Use a valid public URL expected to fail

**Rejected.**

A nonexistent path, paywalled page, blocked host, or intentionally unstable
site can change behavior and cannot guarantee that Source executes. It creates
a flaky availability probe rather than a deterministic contract test.

### Option C: Add route or failure receipts to the public response

**Deferred as a separate product decision.**

Public expert-attempt observability could be useful for user transparency, but
adding a route/failure receipt solely to satisfy an evaluator would change the
public schema and persistence contract. It requires its own product, privacy,
and compatibility review.

### Option D: Force Source or inject a failure in production mode

**Rejected.**

Route forcing, test-only production branches, and provider failure injection
would contradict model-controlled routing, increase attack surface, and make
the live result less representative of the real product.

## Reconciled live catalog

The next implementation pass should use exactly six primary live cases plus
two idempotency requests:

1. `direct-restraint`
2. `clarification`
3. `source`
4. `research`
5. `computation`
6. `requirements-verification`
7. `source-replay`
8. `source-conflict`

The planned and reported HTTP count must be derived from the validated catalog
plus the two idempotency probes. It must not remain a hard-coded `9`.

## Exit and evidence contract

- Exit `0`: every automatable public invariant passes; qualitative cases remain
  `manual_review_required` until repository-owner acceptance.
- Exit `1`: a valid public response violates an observable semantic contract.
- Exit `2`: configuration, transport, provider, timeout, invalid model output,
  or unobservable expert outcome prevents a conclusion.

The evaluator must continue to preserve every fixed attempt in its report. A
later success must not erase an earlier inconclusive outcome.

## Required implementation changes after approval

The follow-up implementation should remain limited to the evaluator:

- remove `failed-source` from `LIVE_E2E_CASES`;
- remove the `failed-source`-specific response heuristic and report label;
- derive planned and summary request counts from the catalog;
- update report notes to point to deterministic 7B.3 failure proof;
- require default-catalog preflight to pass;
- retain `expert_outcome_unobservable` for an expected successful expert that
  produces neither a completed action nor citations;
- update exact-sequence, report, output-safety, and exit-taxonomy tests;
- rerun the bounded live evaluator only after focused tests pass.

## Preserved invariants

- Agent_Col remains the sole user-facing orchestrator.
- Routing remains model-controlled.
- Expert delegation depth remains one.
- Zero or one cognitive expert executes per turn.
- No route forcing, fallback expert, or hidden retry is introduced.
- Only completed, locally validated experts produce action and citation
  receipts.
- Firestore remains durable truth.
- Idempotent replay performs no duplicate downstream work.
- Terminal output remains metadata-only.
- Reports contain only fixed synthetic inputs and public response data.

## Exclusions

- No production application or schema change.
- No Source, Research, Computation, or Requirements Verification change.
- No routing prompt change.
- No public debug receipt.
- No external test host or new infrastructure.
- No Deep Research work.
- No retry-policy change.

## Follow-up TDD targets

1. RED: the default catalog still contains `failed-source` and fails
   production URL preflight.
   GREEN: the six-case catalog passes every production projector.
2. RED: the runner and report still hard-code nine HTTP requests.
   GREEN: both derive eight requests from the catalog plus replay and conflict.
3. RED: failed-Source-only evaluator branches and report language remain.
   GREEN: live evaluation reports only observable public outcomes and cites
   7B.3 as the deterministic failure layer.
4. RED: an expected live expert without a receipt can be misclassified as a
   semantic failure.
   GREEN: it remains inconclusive with exit `2`.
5. GREEN regression: exact replay, conflict, metadata-only output, bounded
   report persistence, and zero memory interference remain unchanged.

## Acceptance criteria

- The default catalog passes local preflight before HTTP client construction.
- The unit-controlled runner performs exactly eight requests.
- The report derives and records the same count.
- No live case claims to prove a failed expert executed.
- Deterministic 7B.3 remains the authoritative failed-expert gate.
- All focused evaluator tests, syntax checks, and `git diff --check` pass.
- A subsequent live run is reported honestly as pass, semantic failure, or
  inconclusive without route forcing or hidden retries.
