# M7-EXP.7B.4 Bounded Live End-to-End Evaluation Plan

## Pass status

Approved for implementation on 2026-08-23.

## Goal

Add one bounded live HTTP evaluation that exercises Agent_Col's complete core
tool belt through the production FastAPI boundary and produces a synthetic
manual-review package without changing production routing or expert behavior.

## User-visible outcome

The repository owner can run one command against a running local application
and receive:

- metadata-only terminal results for every fixed probe;
- exit `0`, `1`, or `2` using the accepted evaluation taxonomy;
- a local JSON report containing only the fixed synthetic requests and their
  public `ChatResponse` outputs for qualitative review;
- exact synthetic Firestore paths for optional manual inspection.

## Fixed live sample

The runner performs exactly nine HTTP requests and never adds automatic
retries:

1. direct tool-restraint turn;
2. clarification turn;
3. successful Source turn against `https://example.com/`;
4. successful Research turn for a current Python release, checked through
   returned citations rather than a hard-coded release value;
5. successful Computation turn using `12, 15, 18, 21, 24, 27`;
6. successful Requirements Verification turn with one covered and one missing
   requirement;
7. controlled failed-Source turn against the reserved `.invalid` domain;
8. exact replay of request 3 with the same idempotency key;
9. changed request using request 3's key, which must return HTTP 409.

The failed-Source case is not route-forced. If the live provider cannot return
a bounded noncompleted expert response, the case is inconclusive rather than
silently retried or relabeled as successful.

## Technical approach

- Add a standalone `tool_belt_live_e2e_check.py` runner using the public
  `/api/chat` contract and `httpx.AsyncClient`.
- Require an explicit bounded `--run-id`; derive unique synthetic user,
  session, and idempotency identifiers from it.
- Parse successful responses through `schemas.ChatResponse`.
- Validate only public, observable invariants at this layer:
  - no expert receipts for direct and clarification turns;
  - exact completed action names for each successful expert;
  - Source and Research citations are present and attached to response text;
  - Computation exposes no citations and contains the locally known results
    `19.5000` and `5.1235`;
  - Requirements Verification exposes no external citations and has its
    authoritative completed receipt;
  - failed expert output has no completed expert action or citation and states
    a limitation;
  - replay JSON is byte-for-structure identical to the stored response;
  - changed request returns the exact public conflict contract.
- Record internal-evidence checks already proven by 7B.3 as a separate layer;
  do not falsely claim the HTTP response exposes hidden expert evidence or
  exact provider-call counts.
- Label the failed-Source probe as a public safe-failure-contract check rather
  than proof that the live expert route executed. A noncompleted expert
  intentionally emits no success receipt, and the current HTTP contract has no
  route receipt. Exact controlled failed-expert execution remains covered by
  7B.3; adding live route observability would be a separate production pass.
- Write a bounded JSON report to an explicit path, or to a run-specific file
  under `/tmp` when omitted. The report is not persisted in the repository.

## Expected files

- `tool_belt_live_e2e_check.py`: bounded live runner and report writer.
- `tests/test_tool_belt_live_e2e_check.py`: pure transport, evaluator,
  reporting, and exit-taxonomy coverage.
- This implementation plan.

No production application, routing prompt, expert service, persistence schema,
dependency, or environment contract changes are authorized.

## Preserved invariants

- Agent_Col remains the sole orchestrator and user-facing responder.
- Zero-or-one cognitive expert executes per turn.
- Expert depth remains one.
- Firestore remains durable truth.
- Idempotent replay performs no duplicate downstream work.
- Model-authored claims never create authoritative action receipts.
- Default terminal output remains free of raw prompt and response content.
- Synthetic evidence is never silently hard-deleted.

## TDD cycles

1. RED: missing bounded scenario catalog and identifier derivation.
   GREEN: fixed immutable catalog and validated synthetic identifiers.
2. RED: successful route receipts, citations, and response evidence are not
   evaluated.
   GREEN: public-contract evaluators for all six route outcomes.
3. RED: failed expert, replay, and conflict invariants are not enforced.
   GREEN: typed failure classification and exact retry checks.
4. RED: output/report safety and exit precedence are absent.
   GREEN: metadata-only terminal output, bounded JSON report, and `0/1/2`
   aggregation.
5. RED: live HTTP status and response parsing are unclassified.
   GREEN: bounded `httpx` adapter with no retries.

## Focused verification

- `venv/bin/pytest -q tests/test_tool_belt_live_e2e_check.py`
- `venv/bin/python -m py_compile tool_belt_live_e2e_check.py`
- A controlled offline smoke using injected HTTP responses; no live provider,
  network, Firestore, or code-execution call during implementation verification.
- `git diff --check`

The full suite is not required because the pass adds an isolated evaluation
harness and does not alter production behavior. Existing routing and
orchestration checks may be added only if the new runner imports a shared
contract that makes them material.

## Manual runtime verification

With the application running, execute the generated single-line command using
a new run ID. Confirm:

- all nine requests are reported exactly once;
- terminal output contains metadata only;
- the report path exists and contains only the fixed synthetic cases;
- automatable checks pass, while qualitative cases remain labeled
  `manual_review_required`;
- optional Firestore inspection shows only the reported synthetic session,
  turn, and message paths;
- no memory proposal or adaptation appears for any case.

## Stop conditions

Stop and propose a correction pass rather than modifying routing policy if:

- a production route, receipt, citation, replay, or conflict invariant fails;
- the controlled failed-expert case cannot be classified safely;
- the public API lacks evidence required by this layer;
- report generation risks exposing non-synthetic content;
- implementation would require a production debug hook, forced route, new
  infrastructure, schema change, or dependency.
