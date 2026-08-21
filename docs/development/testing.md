# Testing Agent_Col

## Test layers

The permanent suite is designed to run without live Gemini or Firestore
access. Tests substitute the provider, ADK runner, and Firestore references at
their application boundaries.

| Layer | Protects | Does not prove |
| --- | --- | --- |
| Schema and policy tests | Strict Pydantic shape, bounded memory values, blueprint semantics | Provider availability or live database permissions |
| Database adapter tests | Transactions, batches, deterministic paths, validation before Firestore access | A specific cloud project's IAM or indexes |
| Service/runtime tests | Orchestration order, context injection, receipts, timeouts, error translation | Live Gemini response quality |
| FastAPI tests | HTTP payloads, status mapping, memory decisions, idempotent replay | Network, Uvicorn, ADC, or live quota |
| Offline smoke-runner tests | Real HTTPX request construction and safe output parsing | A running server or cloud persistence |
| Live smoke runners | End-to-end local integration through real configured services | Production authentication, load, or universal exactly-once execution |

## Full offline suite

From the repository root with the virtual environment active:

```bash
pytest -q
```

Use this before a checkpoint when a shared contract, persistence boundary, or
documentation claim spans multiple modules. Inspect the exit code, failure
count, warnings, and skipped tests; a command merely starting is not evidence
of success.

## Focused chat idempotency checks

HTTP orchestration only:

```bash
pytest -q tests/test_main.py -k "idempotent or idempotency or claimed_turn"
```

Pure identifiers and Firestore persistence primitives:

```bash
pytest -q tests/test_chat_turns.py tests/test_chat_turn_database.py tests/test_database.py
```

Smoke runner without network access:

```bash
pytest -q tests/test_smoke_test_chat_idempotency.py
```

These checks prove claim/replay/conflict handling, deterministic message IDs,
lease ownership, atomic completion, error translation, request construction,
and privacy-safe structural output. They do not call Gemini or Firestore.

## Trusted memory checks

```bash
pytest -q tests/test_memory_policy.py tests/test_memory_schemas.py tests/test_trusted_memory_service.py
pytest -q tests/test_memory_database.py tests/test_memory_approval_database.py tests/test_memory_rejection_database.py tests/test_memory_lifecycle_database.py tests/test_memory_inspection_database.py
```

These protect the allowlist, explicit approval, provenance, correction,
rejection, revocation, hard deletion, bounded inspection, and adaptation
projection. They do not prove that the free-form model will always phrase a
response exactly as a user expects.

## Structured synthesis checks

```bash
pytest -q tests/test_synthesis_schema.py tests/test_blueprint_validation.py tests/test_synthesis.py tests/test_synthesis_service.py
pytest -q tests/test_synthesis_quality.py tests/test_synthesis_quality_check.py
```

The first group protects structured generation, strict local validation, and
persistence orchestration. The second protects bounded quality scenarios. A
live quality check remains probabilistic and can consume Gemini quota.

## Static checks for Python scripts

```bash
python -m py_compile smoke_test_chat_idempotency.py tests/test_smoke_test_chat_idempotency.py
python smoke_test_chat_idempotency.py --help
git diff --check
```

These catch syntax errors, a missing executable entrypoint, and whitespace
damage. They are supplements, not substitutes for behavioral tests.

## Live idempotency smoke

Start Uvicorn first, then run in another activated terminal:

```bash
python3 smoke_test_chat_idempotency.py
```

Passing output contains:

```text
trusted-memory-m6-2-3 pass first=200 replay=200 conflict=409 replay_equal=true
```

The same line supplies generated session, turn, and message IDs for manual
Firestore inspection. This executes one bounded supervisor turn under normal
operation; the replay must not execute another. A provider quota failure makes
the runner fail safely instead of proving the replay path.

Manual verification should confirm one completed turn and exactly one
deterministic user/model message pair under the generated session.
