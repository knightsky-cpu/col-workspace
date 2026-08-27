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

## Frontend module checks

The browser workspace is implemented as static HTML plus vanilla ES modules
under `frontend/`. Focused frontend checks can be run without a browser:

```bash
node --test tests/frontend/*.test.mjs
```

Use this when a documentation or implementation claim depends on frontend
request construction, state transitions, DOM-hook preservation, layout-mode
state, rendering helpers, or workspace module behavior. A CSS-only visual pass
normally needs `git diff --check` plus manual `/workspace` inspection; HTML or
JavaScript changes require the relevant frontend tests.

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

## Complete core tool-belt evaluation

The M7 core-expert evaluation is intentionally layered. One green command does
not substitute for the other boundaries.

### Decision-only live routing

Run one named production routing-v3 scenario with its fixture-declared attempt
count:

```bash
python3 tool_belt_routing_check.py --scenario computation-series-precision --mode declared
```

This calls the configured Vertex routing provider but does not execute an
expert, generate the final response, or access Firestore. Exit `0` means every
planned decision matched the versioned route and candidate-provenance
contract. Exit `1` means a semantic contract mismatch. Exit `2` means the run
was inconclusive or invalid, including provider or schema-output failure.

### Deterministic orchestration

```bash
python3 tool_belt_orchestration_check.py
```

This executes the production turn service, expert executor, responder-context
construction, failures, timeouts, trust probes, replay, and conflict behavior
with controlled collaborators. It makes no provider, network, or Firestore
calls. Exit `0` is the authoritative offline gate for deterministic
orchestration invariants.

### Bounded live end-to-end evaluation

Start Uvicorn and then run, from a second activated terminal, with a new
lowercase synthetic identifier:

```bash
python3 tool_belt_live_e2e_check.py --run-id m7exp7b4-review-01
```

The runner makes exactly eight HTTP requests and performs no automatic retry.
It exercises Direct, Clarify, all four cognitive experts, exact replay, and a
changed-request conflict. Passing output reports zero automatable failures,
zero inconclusive failures, and exit `0`. The replay must return HTTP 200; the
changed request must return HTTP 409. That 409 is required success evidence,
not a failed probe.

The generated JSON report is written under `/tmp` unless `--report-path` is
provided. Review every case marked `manual_review_required`; the aggregate exit
code proves only automatable public-contract invariants. The live run consumes
Vertex quota and writes fixed synthetic chat state to the configured Firestore
database.

See the
[M7 core tool-belt evaluation closure](../superpowers/specs/2026-08-23-m7-exp-7c-core-tool-belt-evaluation-closure.md)
for accepted evidence, limitations, and correction history.

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
