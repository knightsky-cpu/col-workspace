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
