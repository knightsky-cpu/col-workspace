# Unsafe Frontend Work Notes

## 2026-08-28 - Accepted U6A/U6B Per-Letter Chat Pending Animation Correction

Status: accepted after user manual visual verification.

Scope:
- Corrected the accepted U6 pending chat animation before starting U7.
- Replaced the single-element `Waiting for Agent Col` wave with independent per-letter spans from `W` through `l`.
- Preserved the visible pending text and exposed the full phrase through the existing `role="status"` live region with `aria-label`.
- Marked individual animated letter spans `aria-hidden="true"` so screen readers receive one coherent status phrase instead of character-by-character output.
- Added per-letter animation index variables so CSS can stagger the sinewave-style motion.
- Removed the generated three-dot pending-status pseudo-element after manual verification showed the per-letter wave was good but the dots should go.
- Slowed the final accepted wave timing from the first correction to `1.65s` with an `85ms` per-letter stagger.
- Preserved `/api/chat`, request body shape, idempotency keys, retry behavior, pending-turn state, transcript rendering, memory, notes, artifacts, receipts, auth, and model behavior.

Source changed:
- `frontend/app.mjs`: added `renderChatStatusLetters(...)` and routed pending statuses through per-letter rendering while preserving normal text rendering for cleared/non-pending statuses.
- `frontend/styles.css`: added `.chat-status__letter`, per-letter `chat-status-letter-wave` animation, final `1.65s` duration, final `85ms` stagger, and removed the pending `::after` dot line.
- `tests/frontend/workspace-static.test.mjs`: added static regression coverage for per-letter rendering hooks, accessible live-region labeling, absence of whole-status animation, absence of pending dot pseudo-element, final timing, and reduced-motion behavior.

TDD evidence:
- RED 1: `node --test tests/frontend/workspace-static.test.mjs` failed because `renderChatStatusLetters(...)`, `.chat-status__letter`, and per-letter animation hooks did not exist.
- GREEN 1: added per-letter pending status rendering and CSS sinewave-style letter animation; focused checks passed.
- Manual correction: user confirmed the independent letter animation was good, then requested removal of the dot line and a slightly slower wave.
- RED 2: `node --test tests/frontend/workspace-static.test.mjs` failed because the old `.chat-status[data-chat-status-state="pending"]::after` dot rule still existed.
- GREEN 2: removed the pending dot pseudo-element and changed the timing to `1.65s` / `85ms`; focused checks passed.
- REFACTOR: no broad refactor; changes remained scoped to pending chat status rendering and styling.

Verification:
- `node --test tests/frontend/workspace-static.test.mjs` passed: 13 tests.
- `node --test tests/frontend/chat-view.test.mjs tests/frontend/workspace-static.test.mjs tests/frontend/state.test.mjs` passed: 69 tests.
- `node --check frontend/app.mjs` passed.
- `git diff --check` passed.

Manual verification result:
- User confirmed the corrected animation is good after the dot removal and slower wave adjustment.

Deferred:
- Add collapsed adaptation receipt disclosure.
- Tune chat icons/text colors/counter severity.
- Add secure attachment intake.
- Add safe Markdown response/artifact rendering.
- Restructure the Artifact Viewer toward the reference screenshot.

## 2026-08-28 - Accepted U6 Chat Pending Status Wave Animation Pass

Status: accepted after user manual visual verification.

Scope:
- Implemented Pass U6 for the active chat pending status only.
- Preserved the visible pending text `Waiting for Agent Col`.
- Added explicit `aria-atomic="true"` to the existing `role="status"` live region.
- Added a centralized `setChatStatus(message, statusState = "")` helper for status text and `data-chat-status-state`.
- Set `data-chat-status-state="pending"` only while a submitted chat request is waiting for Agent Col.
- Cleared pending status state after successful response, failed response, chat-session load, and New conversation.
- Added CSS-only pending text wave motion and generated dot animation using pseudo-elements.
- Added targeted reduced-motion handling so pending status remains readable without animation.
- Preserved `/api/chat`, request body shape, idempotency keys, retry behavior, pending-turn state, transcript rendering, memory, notes, artifacts, receipts, auth, and model behavior.
- User accepted the pass as functional but requested a follow-up correction: the current animation moves the status as one element, while the desired animation is a per-letter sinewave from `W` through `l` in `Waiting for Agent Col`.

Source changed:
- `frontend/index.html`: added `aria-atomic="true"` to the chat status live region.
- `frontend/app.mjs`: added `setChatStatus(...)` and replaced direct chat-status text mutations in pending, success, failure, chat-session load, and New conversation paths.
- `frontend/styles.css`: added pending status animation, generated dots, and targeted reduced-motion override.
- `tests/frontend/workspace-static.test.mjs`: added static coverage for the live-region attribute, pending status state wiring, CSS animation hooks, transform-based motion, and reduced-motion override.

TDD evidence:
- RED: `node --test tests/frontend/workspace-static.test.mjs` failed because `aria-atomic="true"` and the U6 pending animation/status hooks did not exist.
- GREEN: added the status live-region attribute, app helper, pending-state wiring, CSS keyframes, pseudo-element dots, and reduced-motion override.
- REFACTOR: no broad refactor; `app.mjs` remains the status owner because source inspection showed `chat-view.mjs` does not render `data-chat-status`.

Verification:
- `node --test tests/frontend/workspace-static.test.mjs` passed: 13 tests.
- `node --test tests/frontend/chat-view.test.mjs tests/frontend/workspace-static.test.mjs tests/frontend/state.test.mjs` passed: 69 tests.
- `node --check frontend/app.mjs` passed.
- `git diff --check` passed.
- `rg -n "setChatStatus|data-chat-status-state|chat-status-wave|chat-status-dots|aria-atomic" frontend tests/frontend/workspace-static.test.mjs` confirmed the intended hooks.

Manual verification result:
- User confirmed the pass works.
- User requested the next correction pass before U7: replace the single-element wave with independent per-letter sinewave animation across `Waiting for Agent Col`.

Deferred:
- Improve the pending status animation to animate each letter independently in a sinewave-like sequence.
- Add collapsed adaptation receipt disclosure.
- Tune chat icons/text colors/counter severity.
- Add secure attachment intake.
- Add safe Markdown response/artifact rendering.
- Restructure the Artifact Viewer toward the reference screenshot.

## 2026-08-28 - Accepted U5 Standard Subcard Disclosure And Compact Control Correction Pass

Status: accepted after user manual visual verification.

Scope:
- Implemented Pass U5 for the left-drawer child subcards in Notes, Memory, and Chats.
- Standardized child-subcard disclosure state using stable frontend-only IDs for pending notes, selected note details, memory proposals, memory signals, and chat sessions.
- Preserved the accepted parent drawer-card convention: the menu card/header itself remains the expand/collapse control.
- Removed the regressed parent menu-card arrows/chevrons after manual verification caught that they had been reintroduced.
- Preserved Workspace and Artifact child cards as simple select/open controls in this pass.
- Reduced oversized child action controls across Notes, Memory, Artifacts, export controls, feedback controls, and drawer action controls.
- Corrected the compact control size after manual verification: the first reduction was too small, so the final convention is slightly larger while still compact.
- Corrected the Notes selected-detail layout after manual verification: selected note details now expand in place above the `Create note` form and show Archive/Delete/correction controls inside the selected note subcard.
- Corrected the Chats interaction after manual verification: unselected chat cards open/select the chat, while the selected chat card collapses/expands metadata without reloading the session.
- Preserved destructive confirmation behavior for Memory Revoke/Delete and Notes Delete.
- Preserved backend routes, schemas, persistence, auth, ownership, proposal policy, artifact behavior, and model behavior.

Source changed:
- `frontend/state.mjs`: added frontend disclosure state and helper functions for toggling and idempotently expanding Notes, Memory, and Chats subcards.
- `frontend/app.mjs`: wired Notes, Memory, and Chats disclosure handlers; expanded selected note detail after note load; expanded a chat card before opening an unselected chat.
- `frontend/notes-view.mjs`: collapsed pending proposals until expanded, rendered selected note detail in-place, exposed lifecycle/correction controls only while expanded, and kept action clicks from collapsing the card.
- `frontend/memory-view.mjs`: collapsed pending memory proposals and active memory signals until expanded, while preserving Revoke/Delete confirmations.
- `frontend/chats-view.mjs`: rendered chat session cards as the card-level disclosure/open surface; selected-card clicks now toggle metadata only.
- `frontend/index.html`: removed parent menu-card chevron spans that manual verification identified as a regression.
- `frontend/styles.css`: added subcard disclosure styling, removed parent chevron styling, preserved selected amber card styling, and finalized the compact child-control sizing at `0.73rem` font size and `1.21rem` minimum height.
- `tests/frontend/state.test.mjs`: covered disclosure initial state, toggle behavior, and idempotent expand helpers.
- `tests/frontend/notes-view.test.mjs`: covered collapsed/expanded pending proposals, selected note detail in-place, lifecycle controls, Delete confirmation, and form placement.
- `tests/frontend/memory-view.test.mjs`: covered collapsed/expanded pending proposals, active memory actions, and destructive confirmations.
- `tests/frontend/chats-view.test.mjs`: covered chat card selection, selected-card metadata collapse/expand, and absence of a separate Details button.
- `tests/frontend/workspace-static.test.mjs`: covered no parent chevrons, no subcard pseudo-arrow regression, compact control selector coverage, and the final compact sizing convention.

TDD evidence:
- RED 1: `node --test tests/frontend/memory-view.test.mjs tests/frontend/notes-view.test.mjs tests/frontend/chats-view.test.mjs tests/frontend/state.test.mjs tests/frontend/workspace-static.test.mjs` failed because child-card disclosure state/rendering did not exist.
- GREEN 1: added disclosure state, view rendering, handlers, and compact action sizing; focused frontend checks passed.
- Manual verification failure 1: user reported that parent arrows were reintroduced and selected Notes detail opened as a separate card under `Create note`.
- RED 2: focused Notes/Chats/static tests failed because selected note detail was not the same in-list card, Chats used the wrong selected/toggle behavior, and parent arrow CSS/markup remained.
- GREEN 2: removed separate chat details behavior, rendered selected Notes detail in-place, and removed parent arrow/chevron markup and CSS; focused checks passed.
- Manual verification failure 2: user reported Notes lacked visible Delete controls and Chats were selectable but did not collapse/expand as expected.
- RED 3: focused tests failed because selected Notes could remain collapsed without controls and selected Chats still called select/load on collapse.
- GREEN 3: expanded selected Notes after load, made selected Notes card/header toggle in place, and made selected Chat clicks toggle metadata without reloading; focused checks passed.
- Manual verification correction: user reported `Create correction proposal` was still too large and the compact convention was slightly too small.
- RED 4: `node --test tests/frontend/workspace-static.test.mjs` failed because `.notes-correction-form button` was missing from the compact selector and the final sizing values were absent.
- GREEN 4: included correction-form submit in the compact convention, prevented it from stretching full-width, and raised compact controls to the final accepted size.
- REFACTOR: no broad refactor; changes stayed inside the approved U5 subcard disclosure and compact-control correction boundary.

Verification:
- `node --test tests/frontend/notes-view.test.mjs tests/frontend/chats-view.test.mjs tests/frontend/state.test.mjs tests/frontend/workspace-static.test.mjs` passed: 63 tests.
- `node --test tests/frontend/memory-view.test.mjs tests/frontend/notes-view.test.mjs tests/frontend/chats-view.test.mjs tests/frontend/state.test.mjs tests/frontend/workspace-static.test.mjs tests/frontend/work-view.test.mjs` passed: 97 tests.
- `node --check frontend/app.mjs` passed.
- `node --check frontend/state.mjs` passed.
- `node --check frontend/memory-view.mjs` passed.
- `node --check frontend/notes-view.mjs` passed.
- `node --check frontend/chats-view.mjs` passed.
- `git diff --check` passed.
- `rg -n "section-heading__chevron|chat-session-details-toggle|subcard-disclosure-toggle::after|content:\\s*\\\">\\\"|content:\\s*\\\"v\\\"" frontend tests/frontend` found only negative test assertions and no production matches.

Manual verification result:
- User confirmed the U5 pass successful after the correction-form button sizing adjustment.

Deferred:
- Add chat pending wave animation.
- Add collapsed adaptation receipt disclosure.
- Tune chat icons/text colors/counter severity.
- Add secure attachment intake.
- Add safe Markdown response/artifact rendering.
- Restructure the Artifact Viewer toward the reference screenshot.

## 2026-08-28 - Accepted Drawer Parent Card Disclosure And Icon Pass

Status: accepted after user manual visual verification.

Scope:
- Implemented the first approved unsafe frontend visual-structure pass.
- Added non-emoji inline SVG icon treatment to the New conversation button, the Start a conversation title, and the left drawer parent cards.
- Converted the left drawer parent rows into full-card/header disclosure buttons.
- Removed the separate small parent-card expand buttons.
- Removed the incorrect selected/highlighted drawer-section state that was introduced during the first correction attempt.
- Preserved the existing independent drawer-section expansion behavior: multiple parent cards can remain expanded.
- Preserved `aria-expanded`, `data-section`, `data-section-toggle`, `data-section-content`, drawer collapse/restore behavior, chat layout, Google Sign-In, backend routes, schemas, persistence, memory, notes, artifacts, and request behavior.
- Did not implement workspace deletion, direct note creation, attachment handling, Markdown rendering, artifact-viewer restructuring, chat pending animation, or chat response formatting changes.

Source changed:
- `frontend/index.html`: added decorative SVG icon hooks and made each left drawer parent card header a native disclosure button containing the icon, label, and chevron.
- `frontend/app.mjs`: preserved full-card disclosure button markup during layout renders while keeping drawer label updates for other dynamic drawer buttons.
- `frontend/styles.css`: added icon styles, full-card disclosure button styling, integrated chevron styling, and expanded-card visual treatment keyed to the full-card disclosure button state.
- `frontend/workspace-layout.mjs`: kept section expansion state only and removed the rejected highlighted-section state.
- `tests/frontend/workspace-static.test.mjs`: added static guards for non-emoji icon hooks, full-card disclosure structure, no separate parent expand buttons, and no drawer selected/highlight state.
- `tests/frontend/workspace-layout.test.mjs`: added a regression guard proving drawer expansion state has no separate selected/highlight state.

TDD evidence:
- RED 1: `node tests/frontend/workspace-static.test.mjs` failed because the drawer and chat shell did not contain persistent icon hooks.
- GREEN 1: added static decorative SVG icon hooks and CSS chevrons; focused static tests passed.
- User manual verification found a regression: Workspace appeared highlighted when another drawer section was expanded.
- Investigation found the wrong model: the drawer parent cards were not selectable; they were expandable containers with a separate small expand button.
- RED 2: `node --test tests/frontend/workspace-layout.test.mjs tests/frontend/workspace-static.test.mjs` failed because `highlightedSection` still existed and separate drawer expand buttons remained.
- GREEN 2: removed highlighted-section state, made drawer parent headers full-card disclosure buttons, and removed separate parent expand buttons; focused tests passed.

Verification:
- `node --test tests/frontend/workspace-layout.test.mjs tests/frontend/workspace-static.test.mjs` passed.
- `node --check frontend/app.mjs` passed.
- `git diff --check -- frontend/app.mjs frontend/index.html frontend/styles.css frontend/workspace-layout.mjs tests/frontend/workspace-layout.test.mjs tests/frontend/workspace-static.test.mjs` passed.
- `LC_ALL=C rg -n "[^[:print:][:space:]]" frontend/app.mjs frontend/index.html frontend/styles.css frontend/workspace-layout.mjs tests/frontend/workspace-layout.test.mjs tests/frontend/workspace-static.test.mjs` found no matches.
- `timeout 45s venv/bin/pytest tests/test_workspace_static.py -q` timed out with exit `124` and emitted no failure output.

Manual verification result:
- User confirmed the full-card disclosure correction was successful.

Deferred:
- Move Create Artifact below the artifact list.
- Tune expanded drawer-card color toward translucent neon amber.
- Add workspace deletion.
- Add governed direct user-authored note proposal creation.
- Make memory and left-drawer subcards collapsed by default.
- Add chat pending wave animation.
- Add collapsed adaptation receipt disclosure.
- Tune chat icons/text colors/counter severity.
- Add secure attachment intake.
- Add safe Markdown response/artifact rendering.
- Restructure the Artifact Viewer toward the reference screenshot.

## 2026-08-28 - Accepted Direct User-Authored Note Proposal Pass

Status: accepted after user manual runtime verification.

Scope:
- Implemented Pass U4, direct user-authored note proposal creation.
- Added a `Create note` form in the Notes drawer under the saved notes list, matching the existing Artifacts drawer convention.
- Direct note creation bypasses the model but does not bypass the governed collaborative-note proposal policy.
- Direct note submissions create pending collaborative note proposals only; they do not become active saved notes until approved.
- Fixed the runtime `500 Internal Server Error` found during manual verification by preserving real chat-session/source-message provenance.
- Preserved the existing collaborative-note policy contract and did not modify `collaborative_note_policy.py`.

Source changed:
- `schemas.py`: added `CollaborativeNoteProposalRequest` with `session_id`, `note_kind`, `title`, and `body`, using the existing collaborative-note text normalizer.
- `main.py`: added `POST /api/users/{user_id}/projects/{project_id}/notes/proposals` with idempotency, auth/project resolution, and collaborative-note HTTP error mapping.
- `collaborative_note_service.py`: added `CollaborativeNoteProposalCommand`; direct proposals save a real user-authored source message in the current session before creating a pending proposal.
- `frontend/api.mjs`: added `createNoteProposal(...)`.
- `frontend/app.mjs`: wired Notes drawer submission to the direct proposal API and included the current `session_id`.
- `frontend/notes-view.mjs`: rendered the bottom `Create note` form with existing policy note kinds only.
- `frontend/styles.css`: styled the direct note form consistently with existing drawer forms.
- `tests/frontend/api.test.mjs`, `tests/frontend/notes-view.test.mjs`, `tests/test_collaborative_note_service.py`, and `tests/test_main.py`: added focused coverage for form placement, request shape, provenance, pending-only proposal creation, and policy rejection.

TDD evidence:
- RED: `node --test tests/frontend/notes-view.test.mjs` failed because the bottom note proposal form was missing.
- RED: `node --test tests/frontend/api.test.mjs` failed because `createNoteProposal(...)` did not exist.
- RED: `venv/bin/pytest tests/test_main.py -k "collaborative_note_proposal_returns_pending_proposal" -q` failed because the direct proposal schema/command did not exist.
- RED for reported runtime failure: `venv/bin/pytest tests/test_collaborative_note_service.py -k "direct_proposal" -q` failed because `CollaborativeNoteProposalCommand` had no `session_id`, and `venv/bin/pytest tests/test_main.py -k "collaborative_note_proposal" -q` failed with route-level `422` until the request carried session provenance.
- GREEN: added the direct proposal route/schema/API/form and then fixed provenance by saving a real user-authored source message before proposal creation; focused tests passed.
- REFACTOR: no broad refactor; changes stayed inside the approved U4 note proposal boundary.

Verification:
- `node --test tests/frontend/notes-view.test.mjs tests/frontend/api.test.mjs tests/frontend/workspace-static.test.mjs` passed: 39 tests.
- `venv/bin/pytest tests/test_main.py -k "collaborative_note_proposal" -q` passed: 4 tests, 214 deselected, with one existing `BaseAgentConfig` deprecation warning.
- `venv/bin/pytest tests/test_collaborative_note_service.py -k "direct_proposal or creates_correction" -q` passed: 2 tests.
- `venv/bin/python -m py_compile main.py collaborative_note_service.py schemas.py && node --check frontend/app.mjs && node --check frontend/api.mjs && node --check frontend/notes-view.mjs` passed.
- `git diff --check` passed.

Policy and privacy evidence:
- `collaborative_note_policy.py` was not modified.
- The direct form exposes only the existing policy note kinds: `decision`, `requirement`, `constraint`, `task_state`, and `working_context`.
- Invalid note kind and prohibited note text are rejected with `422` before service mutation.
- The storage path still creates proposals with `policy_version="1.0"` and `status="pending"`.
- The storage path still verifies an owned chat session and source message before writing the proposal.

Runtime evidence:
- User-provided screenshot showed the `Create note` form under saved notes.
- Initial manual submission produced `500 Internal Server Error` because the direct route used synthetic idempotency-key provenance instead of a real owned session/message.
- The approved fix saved a real user-authored source message in the current chat session before proposal creation.
- User confirmed the corrected pass was successful after manual runtime verification, including approval into an active saved note.

Deferred:
- Establish standard collapsed-by-default subcard disclosure for Notes, Memory, and Chats.
- Add chat pending wave animation.
- Add collapsed adaptation receipt disclosure.
- Tune chat icons/text colors/counter severity.
- Add secure attachment intake.
- Add safe Markdown response/artifact rendering.
- Restructure the Artifact Viewer toward the reference screenshot.

## 2026-08-28 - Accepted Workspace Create Button Compactness Pass

Status: accepted after user manual visual verification.

Scope:
- Implemented a small CSS-only visual fix for the New Workspace form in the Workspace drawer.
- Reduced the New Workspace `Create` button from the global default button scale to compact drawer scale.
- Kept the `Create` button below the input and aligned to the start of the form so it no longer crowds or overlaps the text input.
- Preserved existing workspace creation behavior, workspace deletion behavior, backend/API behavior, drawer mechanics, and auth behavior.

Source changed:
- `frontend/styles.css`: added scoped `.workspace-create-form` layout, input sizing, and compact button styling.
- `tests/frontend/workspace-static.test.mjs`: added static coverage for the compact create-form CSS and updated the compact drawer action selector assertion to include the accepted workspace delete action.

TDD evidence:
- RED: `node --test tests/frontend/workspace-static.test.mjs` failed on the new create-form compactness assertion because `.workspace-create-form` CSS did not exist.
- GREEN: added scoped create-form CSS; `node --test tests/frontend/workspace-static.test.mjs` passed.
- REFACTOR: no production refactor; refreshed one stale static assertion from the accepted workspace deletion pass.

Verification:
- `node --test tests/frontend/workspace-static.test.mjs` passed: 12 tests.
- `node --test tests/frontend/workspace-view.test.mjs` passed: 4 tests.
- `git diff --check` passed.

Screenshot/manual evidence:
- User-provided screenshot showed the oversized `Create` button interfering with the New Workspace input field before the pass.
- User confirmed the compact create-button pass was successful after implementation.

Deferred:
- Add governed direct user-authored note proposal creation.
- Establish standard collapsed-by-default subcard disclosure for Notes, Memory, and Chats.
- Add chat pending wave animation.
- Add collapsed adaptation receipt disclosure.
- Tune chat icons/text colors/counter severity.
- Add secure attachment intake.
- Add safe Markdown response/artifact rendering.
- Restructure the Artifact Viewer toward the reference screenshot.

## 2026-08-28 - Accepted Drawer Subcard Selection And Artifact Form Position Pass

Status: accepted after user manual visual verification.

Scope:
- Implemented the second approved unsafe frontend visual-structure pass.
- Revised the unsafe frontend plan to clarify that parent menu cards are expandable disclosure containers, not selectable items.
- Assigned selected/highlight styling to selectable child subcards that already expose current state through `aria-current="true"`.
- Moved the Artifacts drawer list above the manual Create Artifact form.
- Reduced existing drawer action buttons with CSS-only compact sizing.
- Preserved parent drawer card click-to-expand behavior, independent expansion state, artifact form field names, form validation attributes, artifact creation request construction, workspace/artifact/note/chat selection behavior, backend routes, schemas, persistence, memory, notes, artifacts, chat, and Google Sign-In.
- Did not hide action buttons behind collapsible subcards; that remains assigned to the later standard subcard disclosure pass.
- Did not implement workspace deletion, direct note creation, attachment handling, Markdown rendering, artifact-viewer restructuring, chat pending animation, or chat response formatting changes.

Source changed:
- `docs/superpowers/plans/unsafe-frontend-visual-polishing-plan.md`: updated source-backed evidence and pass boundaries for child-subcard selection/highlight, compact actions, and later collapsible Notes/Memory/Chats subcards.
- `frontend/index.html`: moved `data-work-list` before `data-artifact-create-form` inside the Artifacts parent drawer card.
- `frontend/styles.css`: changed selected child subcards from teal to amber using existing `aria-current="true"` selectors, removed parent expanded-card selected-looking tint, and compacted existing drawer action buttons.
- `tests/frontend/workspace-static.test.mjs`: added guards for artifact list/form ordering, amber child-subcard selected styling, no teal selected child-card rail, and compact action-button sizing.

TDD evidence:
- RED: `node tests/frontend/workspace-static.test.mjs` failed because `data-work-list` still appeared after `data-artifact-create-form` and selected child subcards still used teal accent styling.
- GREEN: moved the artifact list before the form and changed selected child-card/action-button CSS; focused frontend tests passed.
- REFACTOR: removed parent expanded-card tint entirely so expansion no longer reads as selection.

Verification:
- `node --test tests/frontend/workspace-static.test.mjs tests/frontend/work-view.test.mjs tests/frontend/workspace-view.test.mjs tests/frontend/chats-view.test.mjs tests/frontend/notes-view.test.mjs tests/frontend/memory-view.test.mjs` passed.
- `node --check frontend/app.mjs` passed.
- `git diff --check -- frontend/index.html frontend/styles.css tests/frontend/workspace-static.test.mjs docs/superpowers/plans/unsafe-frontend-visual-polishing-plan.md` passed.
- `LC_ALL=C rg -n "[^[:print:][:space:]]" frontend/index.html frontend/styles.css tests/frontend/workspace-static.test.mjs docs/superpowers/plans/unsafe-frontend-visual-polishing-plan.md` found no matches.
- `timeout 45s venv/bin/pytest tests/test_workspace_static.py -q` timed out with exit `124` and emitted no failure output.

Manual verification result:
- User confirmed the drawer subcard selection, compact action, and artifact form-position pass was successful.

Deferred:
- Add workspace deletion.
- Add governed direct user-authored note proposal creation.
- Establish standard collapsed-by-default subcard disclosure for Notes, Memory, and Chats.
- Add chat pending wave animation.
- Add collapsed adaptation receipt disclosure.
- Tune chat icons/text colors/counter severity.
- Add secure attachment intake.
- Add safe Markdown response/artifact rendering.
- Restructure the Artifact Viewer toward the reference screenshot.

## 2026-08-28 - Accepted Workspace Permanent Deletion Pass

Status: accepted after user manual runtime verification.

Scope:
- Implemented the third approved unsafe frontend behavior pass.
- Added owner-scoped permanent workspace deletion.
- Preserved the rule that at least one workspace must remain.
- Allowed deletion of any owned workspace, including the synthesized original/default workspace, when another visible workspace remains.
- Used a deleted-default tombstone so a deleted synthesized default workspace does not reappear through automatic default synthesis.
- Added workspace Delete actions only when more than one workspace is visible.
- Preserved the existing workspace selection/reset path when the deleted workspace was selected.
- Preserved auth, ownership resolution, notes, memory, artifacts, chats, receipts, model behavior, drawer mechanics, and existing workspace creation behavior.
- Did not add workspace Archive semantics.
- Did not recursively delete workspace-scoped subcollections.

Source changed:
- `database.py`: added workspace deletion errors, hidden deleted-default tombstone handling in workspace listing, and a transaction-backed `delete_workspace(...)` method.
- `main.py`: added `DELETE /api/users/{user_id}/workspaces/{workspace_id}` returning `204 No Content` with bounded `404` and `409` errors.
- `frontend/api.mjs`: added `deleteWorkspace(...)`.
- `frontend/state.mjs`: added `completeWorkspaceDelete(...)` and reused `selectWorkspace(...)` for surviving-workspace context reset.
- `frontend/workspace-view.mjs`: added separate workspace Delete action rendering with confirmation and no Archive action.
- `frontend/app.mjs`: wired workspace deletion, refresh, and selected-workspace recovery.
- `frontend/styles.css`: added compact workspace action styling.
- `tests/test_main.py`, `tests/test_database.py`, `tests/frontend/api.test.mjs`, `tests/frontend/state.test.mjs`, and `tests/frontend/workspace-view.test.mjs`: added focused U3 regression coverage.

TDD evidence:
- RED: `venv/bin/pytest tests/test_main.py -k "workspace and delete" -q` initially failed because the workspace deletion errors and route did not exist.
- RED: `venv/bin/pytest tests/test_database.py -k "workspace and delete" -q` initially failed because deleted-default suppression, `delete_workspace(...)`, and workspace deletion errors did not exist.
- RED: `node --test tests/frontend/api.test.mjs tests/frontend/state.test.mjs tests/frontend/workspace-view.test.mjs` initially failed because `deleteWorkspace(...)`, `completeWorkspaceDelete(...)`, and workspace Delete UI did not exist.
- GREEN: implemented the backend route, database tombstone/delete transaction, frontend helper/state/view/app wiring, and compact workspace action styling; focused tests passed.
- REFACTOR: no broader refactor; implementation stayed inside the approved U3 boundary.

Verification:
- `venv/bin/pytest tests/test_main.py -k "workspace and delete" -q` passed: 4 tests, 211 deselected, with one existing `BaseAgentConfig` deprecation warning.
- `venv/bin/pytest tests/test_database.py -k "workspace and delete" -q` passed: 4 tests, 44 deselected.
- `node --test tests/frontend/api.test.mjs tests/frontend/state.test.mjs tests/frontend/workspace-view.test.mjs` passed: 72 tests.
- `venv/bin/python -m py_compile main.py database.py` passed.
- `node --check frontend/app.mjs`, `node --check frontend/api.mjs`, `node --check frontend/state.mjs`, and `node --check frontend/workspace-view.mjs` passed.
- `git diff --check` passed.

Screenshot evidence:
- User-provided manual verification screenshot showed the workspace Delete action working but also revealed that the Create button in the New Workspace form is too large and interferes with the input field.

Manual verification result:
- User confirmed the workspace permanent deletion pass was successful.

Deferred:
- Reduce the New Workspace Create button size and layout so it no longer interferes with the input field.
- Add governed direct user-authored note proposal creation.
- Establish standard collapsed-by-default subcard disclosure for Notes, Memory, and Chats.
- Add chat pending wave animation.
- Add collapsed adaptation receipt disclosure.
- Tune chat icons/text colors/counter severity.
- Add secure attachment intake.
- Add safe Markdown response/artifact rendering.
- Restructure the Artifact Viewer toward the reference screenshot.
