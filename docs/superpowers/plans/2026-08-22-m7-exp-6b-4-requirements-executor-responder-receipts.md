# M7-EXP.6B.4 Requirements Executor, Responder Projection, and Receipts

## Goal

Convert a validated routing-v3 Requirements Verification directive into one
bounded provider execution, derive an authoritative completion receipt, and
serialize only the locally validated result for responder-only Agent_Col.

This pass remains disconnected from production chat. M7-EXP.6B.5 owns the
atomic routing, turn-service, lifespan, idempotency, and FastAPI cutover.

## Architecture

Follow the accepted computation-integration pattern with parallel v3 modules:

1. deterministic code validates the routing directive against its exact input;
2. selected current-message block IDs resolve to exact source text;
3. local code assigns ordered `REQ-*` and `SUBJECT-*` identities;
4. `RequirementsVerificationService` performs one bounded assessment;
5. the existing local validator remains authoritative;
6. a completed result derives one `verify_requirements` action and no citation;
7. responder-only Agent_Col receives the validated result and receipts as
   untrusted evidence, not as instructions or conversational ownership.

## Files and responsibilities

- Modify `requirements_verification.py`: add pure receipt derivation.
- Modify `schemas.py`: allow `verify_requirements` as a typed action.
- Create `agent_col_expert_executor_v3.py`: deterministic request construction
  and zero-or-one v3 expert execution.
- Create `agent_col_responder_context_v3.py`: route/result/receipt validation
  and bounded responder serialization.
- Create `smoke_test_agent_col_requirements_verification_pipeline.py`: one
  fixed live provider pipeline without FastAPI or Firestore.
- Add or modify only the directly corresponding focused tests.

## TDD sequence

1. RED/GREEN completed-versus-failed receipt derivation and schema allowlist.
2. RED/GREEN exact block-to-request construction with locally assigned IDs.
3. RED/GREEN one-call executor success, contained documented failures,
   capability order, restraint, no fallback, and fatal unexpected failures.
4. RED/GREEN responder route/capability matching, exact receipt parity,
   contentless failures, no citations, and bounded serialization.
5. RED/GREEN injectable smoke runner and one live Vertex acceptance request.

## Invariants

- Zero or one expert executes per directive; no chaining or fallback.
- Requirements Verification receives current-message selected blocks only.
- Completed locally validated results alone derive one receipt.
- Failure results carry no content, receipt, citation, artifact, or mutation.
- Subject excerpts are comparison evidence, not web citations.
- No raw current message, profile, history, IDs, credentials, provider payload,
  memory, persistence, artifact, URL, Search, or computation authority crosses
  the responder boundary.
- Existing direct, clarify, Source, Research, and Computation behavior remains
  unchanged.

## Focused verification

Run new receipt, executor-v3, responder-v3, smoke, schema, routing-v3,
provider-service, and existing executor/responder parity tests. Compile every
new module and run `git diff --check`. The manual command must prove one
completed verification, one exact receipt, zero citations, and bounded
responder context with exit code zero.

## Stop conditions

Stop and revise before expanding scope if exact selected block text cannot be
preserved, a failed result can derive a receipt, responder serialization leaks
excluded context, Source/Research/Computation parity regresses, or this work
requires changing production turn service, lifespan, FastAPI, Firestore,
idempotency, dependencies, or active timeout budgeting.
