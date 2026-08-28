# Unsafe Frontend Work Notes

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
