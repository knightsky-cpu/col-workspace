# Unsafe Frontend Handoff

## Current status

The unsafe frontend visual polishing work is proceeding through approval-gated bounded passes. The safe CSS-only sequence is complete. Passes U1, U2, U3, the Workspace Create button compactness fix, and Pass U4 have been manually accepted by the user.

The latest accepted pass is Pass U4, Direct User-Authored Note Proposal Creation. The Notes drawer now has a `Create note` form under saved notes. Direct note creation bypasses the model but still creates only a pending collaborative-note proposal, preserves real chat-session/source-message provenance, and does not change the collaborative-note policy contract.

The next proposed implementation pass is Pass U5, the standard collapsed-by-default subcard disclosure convention for Notes, Memory, and Chats, in `docs/superpowers/plans/unsafe-frontend-visual-polishing-plan.md`. This pass is not yet approved for implementation.

## Required documentation

Read these before source changes:

- `AGENTS.md`: repository workflow, TDD, approval gates, focused verification, GitHub checkpoint rules.
- `docs/notes/frontend-work-notes.md`: prior frontend evidence and known visual-state regressions.
- `docs/superpowers/plans/unsafe-frontend-visual-polishing-plan.md`: controlling pass plan and remaining roadmap.
- `docs/notes/unsafe-frontend-work-notes.md`: accepted unsafe frontend pass history.
- `docs/deployment/post-deployment-handoff.md`: deployment and runtime context.

## Next pass boundary

Pass U5 should be proposed for approval before implementation within this scope:

- Establish one standard child-card disclosure convention for Notes, Memory, and Chats.
- Cards should be collapsed by default where practical.
- Clicking the collapsed card/header should expand details and action controls.
- Pending note proposal cards should collapse by default and expand to show Approve/Reject.
- Selected note detail should be collapsed by default and expand to show Archive/Restore/Delete and correction controls.
- Active memory cards should collapse by default and expand to show Revoke/Delete.
- Pending memory proposal cards should collapse by default and expand to show Approve/Reject.
- Chat-session cards should keep their preview/title visible and expand to reveal metadata or future actions.
- Workspace child buttons remain simple select buttons in this pass.
- Artifact child buttons remain select/open controls in this pass.
- Preserve existing selected/current state, auth, ownership, proposal policy, notes, memory, artifacts, chats, receipts, model behavior, and drawer mechanics unless the approved U5 plan explicitly requires a change.

## Key evidence

- `docs/superpowers/plans/unsafe-frontend-visual-polishing-plan.md` defines Pass U5 as the standard child-card disclosure pass for Notes, Memory, and Chats.
- The plan explicitly says Workspace child buttons remain simple select buttons and Artifact child buttons do not get an added collapse layer in U5.
- `frontend/notes-view.mjs` currently renders pending proposal cards, saved note buttons, selected note detail, and correction controls.
- `frontend/memory-view.mjs` currently renders pending memory proposals and active memory cards with visible actions.
- `frontend/chats-view.mjs` currently renders chat-session child cards.
- Existing layout tests cover drawer section expansion state; U5 should add focused child-card disclosure tests without broadening unrelated behavior.
- Pass U4 source evidence: direct note proposals use `CollaborativeNoteProposalRequest`, `CollaborativeNoteProposalCommand`, and `createNoteProposal(...)`; direct submissions save real source provenance before pending proposal creation.
- Policy evidence: `collaborative_note_policy.py` remains unchanged at contract/policy version `1.0`.

## Implementation cautions

- Follow AGENTS.md exactly: investigate, propose if the implementation boundary changes, write RED tests first, verify RED, implement GREEN, run focused verification, then report as implemented pending manual verification.
- Do not take screenshots. The user will manually inspect visual behavior.
- Do not put emoji in the application or code. Requested symbols must be icons, not emoji.
- Use explicit path staging for checkpoints. Do not use `git add -A`.
- Do not checkpoint unaccepted source behavior. Documentation checkpoints are allowed when explicitly requested, as in this handoff.

## Manual verification targets for completed Pass U4

Already verified by the user:

1. `Create note` appears below saved notes in the Notes drawer.
2. A direct note submission no longer returns `500 Internal Server Error`.
3. The submitted note appears as a pending proposal first.
4. Approving the proposal makes it an active saved note.

## Manual verification targets for proposed U5

After implementation, ask the user to verify:

1. Open Notes; pending proposals and selected-note detail are collapsed by default, with title/summary visible.
2. Expand a pending note proposal; Approve/Reject appear only after expansion and still work.
3. Expand selected note detail; Archive/Restore/Delete and correction controls appear only after expansion and still work.
4. Open Memory; active memory and pending proposal cards are collapsed by default and expand to reveal their actions.
5. Open Chats; session preview/title remains visible while expansion reveals metadata without breaking session opening.
6. Confirm Workspace and Artifact child buttons remain simple select/open controls.
