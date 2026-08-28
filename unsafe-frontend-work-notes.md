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
