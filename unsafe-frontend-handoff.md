# Unsafe Frontend Handoff

## Current status

The unsafe frontend visual polishing work is proceeding through approval-gated bounded passes. The safe CSS-only sequence is already complete. Passes U1 and U2 have been manually accepted by the user and checkpointed to `origin/main`.

The next approved implementation pass is Pass U3, Workspace Permanent Deletion, in `docs/superpowers/plans/unsafe-frontend-visual-polishing-plan.md`. The user approved the revised U3 rule: workspaces are disposable, including the original/default workspace, but the last remaining workspace must not be deleted.

## Required documentation

Read these before source changes:

- `AGENTS.md`: repository workflow, TDD, approval gates, focused verification, GitHub checkpoint rules.
- `frontend-work-notes.md`: prior frontend evidence and known visual-state regressions.
- `docs/superpowers/plans/unsafe-frontend-visual-polishing-plan.md`: controlling pass plan and remaining roadmap.
- `unsafe-frontend-work-notes.md`: accepted unsafe frontend pass history.
- `post-deployment-handoff.md`: deployment and runtime context.

## Next pass boundary

Pass U3 is approved for implementation only within this scope:

- Add owner-scoped permanent workspace deletion.
- Do not add archive semantics for workspaces.
- Allow deletion of any owned workspace, including the original/default workspace, when another workspace remains.
- Reject deletion when it would leave zero workspaces.
- Keep the backend authoritative for the last-workspace rule.
- If the deleted workspace is selected, refresh and land on a surviving workspace using the existing workspace selection/reset path.
- Preserve existing auth, ownership, notes, memory, artifacts, chats, receipts, model behavior, and drawer mechanics unless the U3 plan explicitly requires a change.

## Key evidence

- `main.py:1488-1565` currently exposes only list/create workspace routes.
- `database.py:463-579` currently exposes only `list_workspaces(...)` and `create_workspace(...)`.
- `database.py:513-524` synthesizes the default workspace into the returned list when no stored default workspace document exists. Do not treat this synthesized default as immortal.
- `frontend/workspace-view.mjs:23-35` renders workspace child buttons and uses `aria-current="true"` for selected subcard highlighting.
- `frontend/state.mjs:175-232` already has the workspace selection/create state-reset path to preserve when handling delete.
- Firestore official docs state that deleting a document does not delete subcollection documents. Workspace deletion must not assume parent deletion cleans up notes/artifacts/chats.

## Implementation cautions

- Follow AGENTS.md exactly: investigate, propose if the implementation boundary changes, write RED tests first, verify RED, implement GREEN, run focused verification, then report as implemented pending manual verification.
- Do not take screenshots. The user will manually inspect visual behavior.
- Do not put emoji in the application or code. Requested symbols must be icons, not emoji.
- Use explicit path staging for checkpoints. Do not use `git add -A`.
- Do not checkpoint unaccepted source behavior. Documentation checkpoints are allowed when explicitly requested, as in this handoff.

## Manual verification targets for U3

After implementation, ask the user to verify:

1. Create at least two workspaces, delete either workspace, and confirm it disappears.
2. Confirm no Archive option exists for workspaces.
3. Confirm the original/default workspace can be deleted when another workspace remains.
4. Confirm deleting the currently selected workspace lands on a surviving workspace and resets the visible workspace context.
5. Confirm the last remaining workspace cannot be deleted and presents a bounded user-facing error or disabled delete control.
6. Confirm chats, notes, memory, and artifacts for other workspaces are unchanged.
