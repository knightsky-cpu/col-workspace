# M7-EXP.6B.5 Atomic Production Requirements Verification Cutover

## Goal

Promote the already validated routing-v3, expert-executor-v3, and
responder-context-v3 boundaries into the production FastAPI chat path as one
atomic change. A qualifying chat turn may execute exactly one Requirements
Verification assessment and return one locally derived
`verify_requirements` receipt while preserving Agent_Col as the sole
user-facing responder.

## Approved production boundary

1. `AgentColTurnService` projects current-message text blocks alongside the
   existing URL and numeric candidates.
2. The production router becomes the structured v3 provider.
3. The zero-or-one expert set adds Requirements Verification.
4. Expert timeout handling returns a typed, receipt-free verification timeout.
5. The production responder receives the v3 server-validated context.
6. FastAPI lifespan creates one `RequirementsVerificationService` using the
   existing Vertex client and injects it into `AgentColExpertExecutorV3`.
7. Existing chat persistence and idempotent replay remain authoritative and
   unchanged; the action already fits the established typed receipt contract.

## Expected source changes

- `agent_col_turn_service.py`: switch production routing, projections,
  executor error handling, responder projection, and timeout contexts to v3.
- `main.py`: construct the verification provider and v3 executor in lifespan.
- `agent_col_responder.py`: teach responder-only Agent_Col how to explain a
  validated assessment without representing it as certification.
- `smoke_test_agent_col_turn_service.py`: migrate the offline production
  orchestration smoke collaborator from v2 to v3 contracts.
- `tests/test_agent_col_turn_service.py`: prove v3 text projection, one-call
  verification execution, timeout behavior, and existing expert parity.
- `tests/test_main.py`: prove lifespan injects the existing Vertex client into
  Requirements Verification and composes all four experts.

No schema, database, endpoint, request, response, dependency, memory,
artifact, or authentication change is authorized.

## TDD sequence

1. RED/GREEN production turn input includes exact bounded text candidates and
   v3 capability availability without leaking history or private context.
2. RED/GREEN a completed verification turn reaches responder-only Agent_Col,
   returns exactly one `verify_requirements` receipt, and returns no citation.
3. RED/GREEN verification shares the existing expert deadline and produces a
   typed receipt-free timeout without calling another expert.
4. RED/GREEN lifespan creates one verification service from the existing
   Vertex client and injects all four services into `AgentColExpertExecutorV3`.
5. Run focused turn-service, lifespan, chat idempotency, routing-v3,
   executor-v3, responder-v3, and existing expert regression tests.

## Preserved invariants

- Agent_Col remains the only conversational owner.
- Zero or one expert executes; no fallback or chaining.
- Requirements and subject content come only from selected current-message
  blocks.
- Failed or timed-out verification produces no action or citation.
- Completed verification produces exactly one application-derived action and
  no web citation.
- Memory decisions, governed proposals, action persistence, idempotent replay,
  Firestore ownership, and partial-failure behavior remain unchanged.
- Source, Research, Computation, direct, clarify, and explicit no-tool behavior
  remain available.

## Focused verification

- New named RED/GREEN tests in `tests/test_agent_col_turn_service.py` and
  `tests/test_main.py`.
- Directly related routing-v3, executor-v3, responder-v3, requirements service,
  chat-turn persistence, and FastAPI tests.
- Python compilation and `git diff --check`.
- Manual live FastAPI checks for Requirements Verification, restraint,
  idempotent replay, and conflicting-key rejection.

## Stop conditions

Stop and revise before expanding scope if the cutover requires a second expert
per turn, changes persisted chat schemas, bypasses local evidence validation,
introduces another Vertex client, leaks history into verification inputs,
alters memory behavior, or breaks the established direct/Source/Research/
Computation paths.
