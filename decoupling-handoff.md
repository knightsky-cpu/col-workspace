# Agent Col Chat / Background Decoupling Handoff

Last stable pushed checkpoint on `main` before this uncommitted pass:

- `630af70`
- artifact creation generation/persistence moved behind AgentJob/report ownership.

## User-required end state

Do not ask for manual verification until chat/background-work decoupling is complete end-to-end.

Required behavior:

- Chat is an independent backend/frontend surface.
- An active Agent Col chat turn must not block unrelated application actions.
- Notes and memory proposals can be created/reviewed/approved/rejected while chat is active.
- Artifact/background task requests, execution, completion, failures, and status operate independently of `/api/chat` or `/api/chat/stream`.
- Frontend drawers and non-chat controls remain interactive during chat.
- Do not use chat `pendingTurn`, global busy state, or `selectCanSubmit` to gate unrelated resource surfaces.
- Backend resource/job ownership must not serialize behind a chat request.
- Automated tests are the acceptance mechanism until the entire concurrency boundary is complete.

## Completed in the current uncommitted pass

### Direct collaborative-note decisions

Implemented:

- `CollaborativeNoteDecisionResponse` in `schemas.py`.
- direct endpoint:
  `/api/users/{user_id}/projects/{project_id}/notes/proposals/{proposal_id}/{decision}`
- endpoint calls the existing collaborative note service directly rather than routing through a chat turn.
- public note/event redaction is preserved.
- expired proposals map to HTTP 410.
- frontend `decideNoteProposal(...)` wrapper added.
- normal note approve/reject UI path moved away from the chat request builder.
- note/artifact mutations had unrelated `pendingTurn` / `selectCanSubmit` gating removed.
- notes state now hydrates `pending_proposals` from the authoritative notes API instead of requiring chat receipts to seed the drawer.

Verification reached GREEN for the focused direct-note/API/runtime boundary.

### Artifact responder ownership

Changed `agent_col_turn_service.py` so queued artifact jobs remain structured runtime receipts but are no longer inserted into model-visible responder context.

Focused artifact turn-service tests were changed RED then GREEN.

### Tests/docs already modified

Current dirty tree includes relevant updates to:

- `tests/frontend/api.test.mjs`
- `tests/frontend/app-runtime.test.mjs`
- `tests/frontend/state.test.mjs`
- `tests/test_agent_col_turn_service_artifacts.py`
- `tests/test_main.py`
- `docs/async-work/async-work-notes.md`
- `docs/async-work/async-revision-plan.md`

The docs already record the completed note/UI/artifact-responder portion of this pass.

## IMPORTANT: artifact feedback slice is currently WIP

Codex started the final remaining Work-surface coupling point and hit usage limits before finishing it.

Goal:

Artifact feedback must no longer use a chat request builder and must remain usable while a chat stream is active.

Work already added:

### `tests/test_main.py`

The fake artifact-feedback service was extended with a record path.

A backend test was started:

`test_direct_artifact_feedback_does_not_use_chat_turn`

It expects direct feedback persistence without chat-turn ownership.

### `schemas.py`

Added:

- `ArtifactFeedbackRecordRequest`
  - `session_id`
  - `user_id`
  - existing artifact feedback decision fields inherited from `ArtifactFeedbackDecisionRequest`

- `BlueprintArtifactFeedbackRecordResponse`
  - feedback contract version
  - action receipt
  - feedback reference

### `main.py`

Added imports for direct artifact feedback.

Added POST endpoint:

`/api/projects/{project_id}/blueprints/{blueprint_id}/feedback`

It is intended to invoke the existing artifact feedback service directly.

An incorrect temporary hardcoded user shortcut was immediately corrected; the endpoint now uses `payload.user_id`.

Review this route carefully before considering it complete, particularly auth/ownership, idempotency, request/session/source identifiers, service command construction, error mapping, and public response behavior.

### `frontend/api.mjs`

Added:

`recordBlueprintFeedback(...)`

This wrapper targets the new direct feedback endpoint.

## NOT FINISHED

Do not assume the artifact feedback slice is complete.

Codex ran out immediately after adding `recordBlueprintFeedback(...)`.

Still required:

1. Inspect the current diff before changing anything.
2. Finish/confirm RED frontend API coverage for `recordBlueprintFeedback`.
3. Add/finish runtime coverage proving Work-detail artifact feedback can submit while `/api/chat/stream` is still active.
4. Switch the normal artifact-feedback UI handler in `frontend/app.mjs` from `buildArtifactFeedbackChatRequest` / chat submission to `recordBlueprintFeedback`.
5. Artifact feedback must not use `selectCanSubmit` or `pendingTurn`.
6. Normal artifact feedback submission must not create a chat turn.
7. Refresh authoritative artifact/feedback/job/report state through their own surfaces afterward as appropriate.
8. Preserve legacy request-builder helpers only if existing recovery/tests still require them; normal UI behavior must not use them.
9. Run the direct backend feedback test and fix any route/service issues it exposes.
10. Run focused frontend API/runtime/state tests.
11. Run focused artifact/job/report/backend tests.
12. Run static checks and `git diff --check`.
13. Inspect the complete diff for accidental unrelated changes.

## After artifact feedback is GREEN

Do NOT stop and ask for manual testing yet.

Continue auditing for remaining chat/global-busy coupling consistent with the approved end-to-end requirement.

Search especially for:

- `selectCanSubmit`
- `pendingTurn`
- `buildArtifactFeedbackChatRequest`
- other `build*ChatRequest` helpers used by Notes, Memory, Work, Agents, Artifacts, status/actions
- `/api/chat`
- `/api/chat/stream`
- resource operations whose progress/status depends on chat completion

Intentional chat/session-history coupling can remain.

Notes, Memory, Agents/background tasks, Artifacts/Work, status/actions, and other unrelated resource surfaces must remain independent during a running chat turn.

Only after automated coverage proves that complete concurrency boundary should manual end-to-end verification be requested.

## Current working-tree rule

This handoff branch contains intentional WIP.

Do not revert or recreate the current changes.

Continue from the existing diff using TDD.

Before merging/checkpointing back to `main`, make the complete intended pass GREEN and inspect the final diff.
