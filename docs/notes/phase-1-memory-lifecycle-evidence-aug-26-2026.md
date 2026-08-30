# Phase 1E Memory Lifecycle Closure Evidence

Status: Accepted after manual Google OIDC verification.

Date: August 26, 2026.
Baseline checkpoint: `eca80c3d6afb76b495e3f2a1bdeb919ca5a752ae`.

## Scope

Phase 1E closes the governed profile-memory lifecycle for Phase 1 without
changing backend memory contracts. The source-changing boundary is the browser
confirmation gate for destructive memory controls plus this evidence
reconciliation.

## Source-backed evidence

- Browser memory inspection exposes pending proposal approval and rejection
  controls.
- Browser active-memory Revoke and Delete controls now require explicit native
  confirmation before calling the existing revoke/delete handlers.
- Canceling Revoke or Delete does not call the handler and therefore does not
  start the API request.
- Confirming Revoke or Delete preserves the existing handler payload.
- Confirmation copy uses human labels such as `Response length · concise`, not
  signal IDs or source event IDs.
- List-valued memory labels render in confirmation copy as comma-separated
  values.
- Backend lifecycle regression tests still cover approval, rejection,
  revocation, deletion, ownership, conflicts, bounded deletion, proposal
  service behavior, context projection, and main API boundaries.
- Chat is still instructed not to delete or revoke active durable memory; users
  must use the dedicated memory UI for those operations.
- Explicit benign arbitrary memory requests, including favorite-color
  preferences, are accepted as governed `user_requested_memory` candidates.
- Deterministic policy rejects obvious phone, email, street-address,
  payment-card, credential, overbroad remember-everything, and chat
  revoke/delete memory attempts before they can become approvable.

## Automated verification

- `node --test tests/frontend/memory-view.test.mjs`:
  - RED before implementation: 5 passed, 3 failed.
  - Expected failure: Revoke/Delete called handlers immediately on cancel-path
    tests.
  - GREEN after implementation: 8 passed, 0 failed.
- `node --test tests/frontend/memory-view.test.mjs tests/frontend/chat-view.test.mjs tests/frontend/state.test.mjs`:
  - 52 passed, 0 failed.
- `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q tests/test_memory_approval_database.py tests/test_memory_rejection_database.py tests/test_memory_lifecycle_database.py tests/test_memory_context.py tests/test_memory_proposal_service.py tests/test_main.py`:
  - 287 passed, 0 failed.
  - Warning observed: ADK `BaseAgentConfig` deprecation warning.
- `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q tests/test_memory_policy_v2.py tests/test_memory_proposal_service.py tests/test_memory_proposal_tool.py tests/test_agent_col_responder.py tests/test_supervisor.py`:
  - 121 passed, 0 failed.
  - Warning observed: ADK `BaseAgentConfig` deprecation warning.

## Accepted manual evidence

Manual Google OIDC testing on August 26, 2026 showed:

- A benign arbitrary request to remember a favorite color created a pending
  `user_requested_memory` proposal.
- Approval activated the favorite-color memory.
- A later correction preferring red over blue created and activated a corrected
  proposal.
- The corrected memory superseded the prior favorite-color value.
- A fresh conversation adapted from the corrected memory and displayed the
  authoritative adaptation receipt.
- Password, personal email, recovery-phrase-hint, street-address, and deceptive
  fake-address memory requests were denied with no approvable proposal.

## Manual live verification script

Run Google auth mode:

```bash
AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/workspace
```

Capture screenshots or short clips for each step:

1. Send an explicit allowed memory request and capture the user request.
2. Capture the pending proposal in Memory.
3. Approve the proposal and capture the approval control/result.
4. Start a fresh conversation and capture changed adapted behavior.
5. Capture the authoritative adaptation receipt for that fresh conversation.
6. Send a second allowed memory request, reject it, and verify it does not
   become active.
7. Ask for a correction, approve the correction proposal, and verify a fresh
   conversation adapts to the corrected value.
8. Send prohibited memory content such as a password and verify no approvable
   proposal is created.
9. Click Revoke, cancel the confirmation, and verify the memory remains active.
10. Click Revoke, confirm, and verify a fresh conversation no longer uses that
    memory.
11. Click Delete, cancel the confirmation, and verify inspection is unchanged.
12. Click Delete, confirm, and verify the memory and owned lifecycle artifacts
    are absent from inspection.

## Evidence capture checklist

- [x] Explicit memory request screenshot or clip.
- [x] Pending proposal screenshot or clip.
- [x] Approval screenshot or clip.
- [x] Fresh-chat adaptation screenshot or clip.
- [x] Adaptation receipt screenshot or clip.
- [x] Rejected prohibited memory screenshot or clip.
- [x] Revoke removes future adaptation screenshot or clip.
- [x] Delete removes inspection artifacts screenshot or clip.

## Multi-slot decision

Phase 1 intentionally keeps the current profile storage shape: one active
`user_requested_memory` value at a time. Supporting multiple arbitrary
user-requested memory slots active together is deferred as a separate profile
storage-shape pass.

## Known limitations deferred to Phase 2+

- Workspace notes remain separate from profile memory and are not implemented
  by this pass.
- Multiple arbitrary active `user_requested_memory` slots are not part of
  Phase 1.
- Judge-grade screenshots or video are not committed here because they can
  contain private user content, OAuth identity state, or memory values.
- Phase 1 evidence remains conversation-held/private rather than committed
  repository media.
