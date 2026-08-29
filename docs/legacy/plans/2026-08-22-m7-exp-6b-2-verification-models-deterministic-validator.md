# M7-EXP.6B.2 Verification Models and Deterministic Validator Plan

**Goal:** Add the provider-independent Requirements Verification contracts and
an atomic local validator without enabling a live provider or production route.

**Spec:**
`docs/superpowers/specs/2026-08-22-m7-exp-6a-requirements-verification-boundary-design.md`

## Approved boundary

- Add strict immutable input, candidate, normalized payload, evidence, and
  result models.
- Assign and validate request-scoped `REQ-*` and `SUBJECT-*` identities
  locally.
- Enforce the accepted per-field and aggregate text bounds.
- Validate complete requirement coverage, exact subject-block evidence,
  status coherence, and duplicate rejection.
- Normalize assessments into input order and derive counts and provenance
  metadata locally.
- Reject an invalid candidate atomically as `invalid_output`.
- Add an offline, content-safe smoke harness.

## Explicit exclusions

- No Vertex or Gemini call.
- No ADK agent, tool, or executor integration.
- No production routing or FastAPI change.
- No Firestore access or persistence.
- No responder projection, public receipt, citation, or artifact change.
- No dependency change.

## TDD sequence

1. RED/GREEN strict input and candidate contracts.
2. RED/GREEN complete identity and exact evidence validation.
3. RED/GREEN status coherence and atomic rejection.
4. RED/GREEN local ordering, counts, and evidence derivation.
5. RED/GREEN offline smoke harness and exit behavior.

## Verification

```bash
venv/bin/pytest -q tests/test_requirements_verification.py tests/test_smoke_test_requirements_verification.py tests/test_expert_contracts.py
venv/bin/python -m py_compile requirements_verification.py smoke_test_requirements_verification.py
git diff --check
```

Manual acceptance:

```bash
source venv/bin/activate && python3 smoke_test_requirements_verification.py; printf 'exit=%s\n' "$?"
```

The expected result is a content-safe `pass` line proving all five statuses,
local counts, exact evidence validation, and atomic rejection of an ungrounded
candidate, followed by exit code `0`.

## Deferred next boundary

M7-EXP.6B.3 adds the isolated Vertex structured provider service. This pass
does not begin that work.
