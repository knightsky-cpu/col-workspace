# M9-NOTE.1A Collaborative Note Proposal and Active-Projection Models

## Status and authority

Approved by the repository owner on August 24, 2026, after manual acceptance
of M9-SEC.1. This plan is subordinate to:

- `AGENTS.md`;
- `docs/design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md`;
- `docs/design/DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`;
- `docs/superpowers/specs/2026-08-24-m9-cont-1-continuity-domain-and-collaborative-notes-design.md`.

This is the first bounded subpass of M9-NOTE.1. It does not complete the
collaborative-note lifecycle.

## Goal

Add strict, versioned, persistence-independent proposal and active-projection
models plus deterministic structural text validation. No runtime route,
persistence, chat, ledger, retrieval, or frontend behavior changes in this
pass.

## Global constraints

- Exact note kinds: `decision`, `requirement`, `constraint`, `task_state`,
  `working_context`.
- Exact proposal statuses: `pending`, `approved`, `rejected`, `expired`.
- Exact active-note statuses: `active`, `archived`.
- Proposal policy version is required and exactly `1.0`; it has no default.
- `note_contract_version` and `CollaborativeNoteEvent` are deferred to the
  event/persistence subpass.
- Title length is 1 through 120 Python Unicode code points after NFC
  normalization and whitespace collapse.
- Title raw input rejects every Unicode category beginning with `C`.
- Body raw input permits tab, LF, and CR but rejects every other Unicode
  category beginning with `C`.
- Body canonicalizes CRLF and CR to LF, applies NFC normalization, trims only
  outer whitespace, preserves internal whitespace, and is 1 through 2,000
  Python Unicode code points afterward.
- Structural validation does not claim secret detection or persistence
  eligibility.
- Source-message IDs contain 1 through 5 normalized, unique `IdentifierStr`
  values. Input order is preserved; duplicates are rejected.
- `expected_note_id` and `expected_revision` are either both present or both
  absent. A present revision is at least 1.
- Proposal timestamps are timezone-aware and exactly 24 elapsed hours apart
  after conversion to UTC.
- Active-note timestamps are timezone-aware and `updated_at` is not earlier
  than `created_at` after conversion to UTC.
- Schema validation cannot prove source existence, current-message inclusion,
  session ownership, or workspace ownership. Those checks are deferred to the
  service/persistence pass.
- No production behavior before valid RED evidence.
- No commit or push before user manual acceptance.

## Exact target models

`CollaborativeNoteProposal` fields:

- `proposal_id`, `note_kind`, `title`, `body`;
- `source_session_id`, `source_message_ids`;
- `expected_note_id`, `expected_revision`;
- `policy_version`, `status`, `created_at`, `expires_at`.

`CollaborativeNote` fields:

- `note_id`, `owner_user_id`, `workspace_id`;
- `note_kind`, `title`, `body`, `status`, `revision`;
- `source_session_id`, `source_message_ids`, `source_event_id`;
- `created_at`, `updated_at`.

No additional public fields belong in this pass.

## Task 1: Implement the bounded note policy and models through TDD

### Files

- Create `collaborative_note_policy.py`.
- Modify `schemas.py`.
- Create `tests/test_collaborative_note_policy.py`.
- Create `tests/test_collaborative_note_schemas.py`.

### RED cycles

Write one minimal test before each behavior. Keep imports inside tests until
the target exists so missing implementation produces an inspected assertion
failure rather than a collection error.

Required coverage:

- exact kind and status vocabularies;
- required exact policy version, including omitted and unsupported versions;
- NFC and idempotent normalization;
- title whitespace collapse and body multiline preservation;
- raw prohibited controls and CR/CRLF canonicalization;
- title bounds 0/1/120/121 and body bounds 0/1/2000/2001 after normalization;
- non-string policy inputs;
- strict unknown-field rejection;
- invalid kinds and statuses;
- source counts 0/1/5/6 and normalized duplicate rejection;
- expected-note/revision pairing and revision zero rejection;
- naive, reversed, 23-hour, 25-hour, differing-offset, and DST-boundary
  timestamp cases;
- exact normalized model serialization.

### GREEN

Implement only the behavior required by the current RED test. Reuse
`IdentifierStr`, `StrictModel`, `Field`, and existing Pydantic validator
patterns. Do not add event, persistence, request, receipt, or UI models.

### REFACTOR

Remove duplication only after focused tests are green. Do not broaden
validation into semantic eligibility or secret detection.

### Focused verification

```bash
venv/bin/pytest -q tests/test_collaborative_note_policy.py
venv/bin/pytest -q tests/test_collaborative_note_schemas.py
venv/bin/pytest -q \
  tests/test_collaborative_note_policy.py \
  tests/test_collaborative_note_schemas.py \
  tests/test_memory_policy.py \
  tests/test_memory_schemas.py \
  tests/test_schemas.py
venv/bin/python -m compileall -q collaborative_note_policy.py schemas.py
git diff --check
```

The full suite is unnecessary because this pass adds isolated policy/model
contracts without runtime consumers.

## Explicit deferrals

- `CollaborativeNoteEvent` and lifecycle relationships;
- persistence records, Firestore paths, and `note_contract_version`;
- source existence, current-message, owner, and workspace validation;
- proposal expiry transitions relative to an observed clock;
- sensitive-content eligibility policy;
- APIs, `ChatRequest`, turn effects, routing, retrieval, UI, and deployment.

## Manual acceptance

There is no browser behavior in this pass. Acceptance is based on exact model
serialization examples, normalized text examples, the four-file source/test
boundary, and inspected focused-test output.
