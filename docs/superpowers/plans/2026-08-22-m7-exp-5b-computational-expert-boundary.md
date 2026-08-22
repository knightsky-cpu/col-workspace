# M7-EXP.5B Computational Expert Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline. Do not use
> subagents for this repository-owner-approved pass.

**Goal:** Convert the proven Vertex/ADK built-in code-execution combination
into an isolated Computational Expert service with strict input validation,
native execution-evidence validation, safe failures, and a reproducible live
smoke runner.

**Architecture:** A bounded `single_turn` `LlmAgent` with
`BuiltInCodeExecutor` runs beneath a one-node ADK `Workflow`. The application
collects native `executable_code` and `code_execution_result` parts, validates
ordered Python execution pairs plus one final response, and returns the shared
`ExpertResult` contract. The service owns temporary invocation lifecycle only;
it has no persistence or public routing authority.

**Tech Stack:** Python 3.14, Pydantic v2, Google ADK 2.7.0, Google Gen AI SDK
2.18.1, Vertex AI global, Gemini 3.6 Flash, pytest, pytest-asyncio

**Spec:**
`docs/superpowers/specs/2026-08-21-phase-3b-m7-2-core-expert-routing-design.md`

## Global constraints

- Work directly on `main` because the repository owner explicitly approved
  inline execution; do not create a branch or PR.
- Use RED, verify RED, GREEN, verify GREEN, then refactor for each behavior.
- Do not modify production routing, FastAPI, Firestore, dependencies,
  idempotency, memory, public action receipts, or other experts.
- Accept only bounded numeric/mathematical task data; reject explicit code,
  URLs, paths, credentials, non-finite numbers, and unbounded collections.
- The model receives no profile, history, user/session/project identifiers,
  files, URLs, credentials, or persistence authority.
- Completed output requires ordered Python code/result pairs, one non-empty
  final response, at least one success, and no failed or deadline execution.
- Code and output are each capped at 8,000 characters and never logged.
- `limitations` remains on the shared `ExpertResult`; do not duplicate it in
  the payload.

---

### Task 1: Strict computation contracts and native event normalization

**Files:**
- Create: `computational_expert.py`
- Create: `tests/test_computational_expert.py`

**Interfaces:**
- Produces `ComputationExpertInput` with `objective`, structured `inputs`,
  optional `required_precision`, and zero-to-five `constraints`.
- Produces `ComputationExpertResult`, `ComputationExpertPayload`,
  `ExecutionRunEvidence`, and `ComputationExpertEvidence`.
- Produces `normalize_computation_events(request, events)`.
- Produces `create_computational_expert(vertex_settings)` and
  `create_computational_expert_app(vertex_settings)`.

- [x] Write a failing schema test covering extra fields, empty text,
  non-finite values, empty input sets, oversized series, code fences, URLs,
  paths, credential-shaped text, and invalid mathematical expressions.
- [x] Verify RED because `computational_expert` does not exist.
- [x] Implement the minimal strict Pydantic input models and validators.
- [x] Verify GREEN for the schema tests.
- [x] Write failing native-event tests for prose-only, wrong-author, missing or
  multiple final responses, unpaired/non-Python/oversized evidence, provider
  failure/deadline, and valid bounded success.
- [x] Verify RED because event normalization does not exist.
- [x] Implement ordered native evidence normalization. Use the fixed method
  label `Provider-executed Python computation.`; echo only validated structured
  inputs; use the bounded final response as the result.
- [x] Verify GREEN for event normalization.
- [x] Write a failing topology test for the one-node workflow, no tools,
  no sub-agents/transfers, `single_turn`, global Vertex settings, and
  `BuiltInCodeExecutor(timeout_seconds=30)`.
- [x] Implement the minimal expert/workflow factories and verify GREEN.

### Task 2: Isolated provider service lifecycle

**Files:**
- Create: `computational_expert_service.py`
- Create: `tests/test_computational_expert_service.py`

**Interfaces:**
- Produces `ComputationalExpertService.from_vertex_settings(settings)`.
- Produces `await service.compute(request) -> ComputationExpertResult`.
- Raises `ComputationalExpertServiceError(status)` with only shared safe
  statuses.

- [x] Write a failing service test proving exact JSON request projection,
  maximum two LLM calls, temporary session creation/deletion, and completed
  normalization from real ADK `Event` objects.
- [x] Verify RED because the service does not exist.
- [x] Implement the minimum isolated `App`/`Runner`/in-memory-session service.
- [x] Verify GREEN for the successful lifecycle.
- [x] Write failing tests for invalid output, provider exception, application
  timeout, and cleanup after every terminal path. Assert logs contain only
  exception type/status and never request, code, output, identifiers, or
  provider exception content.
- [x] Implement minimal status translation and safe logging; verify GREEN.

### Task 3: Reproducible live smoke runner

**Files:**
- Create: `smoke_test_computational_expert.py`
- Create: `tests/test_smoke_test_computational_expert.py`

**Interfaces:**
- `python3 smoke_test_computational_expert.py` runs one fixed non-sensitive
  statistics request through the real service.
- Exit `0`: completed locally validated execution.
- Exit `1`: provider responded but result was non-completed.
- Exit `2`: configuration/provider/service failure.

- [x] Write failing tests for exit `0`, `1`, and `2`, deterministic `.env`
  loading, and safe output that contains the fixed result/evidence but no
  provider exception content.
- [x] Verify RED because the smoke runner does not exist.
- [x] Implement the minimal runner and verify GREEN.

### Task 4: Focused verification and manual gate

**Files:**
- Verify all files above and this plan.

- [ ] Run:
  `venv/bin/pytest -q tests/test_computational_expert.py tests/test_computational_expert_service.py tests/test_smoke_test_computational_expert.py tests/test_vertex_config.py`
- [ ] Compile all new Python files.
- [ ] Run whitespace and `git diff --check` validation.
- [ ] Report as implemented, pending manual verification.
- [ ] Require:
  `python3 smoke_test_computational_expert.py; printf 'exit=%s\n' "$?"`
  and accept only a completed result with native successful execution evidence
  and exit `0`.
