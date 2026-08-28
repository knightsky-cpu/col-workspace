# Frontend Work Notes

## 2026-08-28 - Accepted CSS Foundation Pass

Status: accepted after user visual verification.

Scope:
- Corrected frontend visual planning docs before implementation.
- Implemented the first bounded CSS-only visual foundation pass.
- Touched implementation source only in `frontend/styles.css`.
- Preserved the current expanded artifact `80vw` behavior.
- Did not modify frontend modules, `frontend/index.html`, tests, backend code, or Google Sign-In button internals.

CSS surface changed:
- `:root`
- `@media (prefers-color-scheme: dark) :root`
- `body`
- `button`
- `input`
- `select`
- `textarea`
- `button:focus-visible`
- `input:focus-visible`
- `select:focus-visible`
- `textarea:focus-visible`
- `main:focus-visible`
- `.workspace-shell`
- `.context-gate`
- `.google-signin`

Verification:
- `git diff --check` passed.
- `node --test tests/frontend/workspace-static.test.mjs` passed: 7 tests.
- `node --test tests/frontend/auth-view.test.mjs` passed: 7 tests.
- `node --test tests/frontend/chat-view.test.mjs` passed: 9 tests.
- `venv/bin/pytest tests/test_workspace_static.py -q` passed: 4 tests, with one existing `BaseAgentConfig` deprecation warning.

Screenshot:
- `/tmp/agent-col-shell-pass1.png`
- The screenshot used a temporary HTML preview generated from the real `frontend/index.html` and current `frontend/styles.css`, with app JavaScript removed because the sandbox denied binding the local FastAPI server to `127.0.0.1:8765`.

Deferred to later bounded passes:
- Top bar polish.
- Drawer and supporting panel surfaces.
- Chat transcript, turns, receipts, and composer.
- Artifact list/detail surfaces.
- Memory and notes drawer styling.
- Expanded artifact width changes only if a later plan explicitly updates and justifies `tests/test_workspace_static.py`.
- Activity styling remains dormant/non-visible in the current UI.

## 2026-08-28 - Accepted Top Bar Visual Pass

Status: accepted after user visual verification.

Scope:
- Implemented the second bounded CSS-only visual pass.
- Touched implementation source only in `frontend/styles.css`.
- Did not modify frontend modules, `frontend/index.html`, tests, backend code, drawer/chat/artifact selectors, or Google Sign-In internals.

CSS surface changed:
- `.top-bar`
- `.eyebrow`
- `.eyebrow::before`
- `.top-bar h1`
- `.top-bar [data-new-conversation]`

Verification:
- Temporary Pass 2 CSS assertion failed before implementation for the missing top bar treatment, then passed after the CSS patch.
- `git diff --check` passed.
- `node --test tests/frontend/workspace-static.test.mjs` passed: 7 tests.
- `node --test tests/frontend/auth-view.test.mjs` passed: 7 tests.
- `node --test tests/frontend/chat-view.test.mjs` passed: 9 tests.
- `venv/bin/pytest tests/test_workspace_static.py -q` passed: 4 tests, with one existing `BaseAgentConfig` deprecation warning.

Screenshot:
- `/tmp/agent-col-shell-pass2.png`
- The screenshot used a temporary HTML preview generated from the real `frontend/index.html` and current `frontend/styles.css`, with app JavaScript removed because the sandbox denied binding the local FastAPI server to `127.0.0.1:8765`.

Deferred to later bounded passes:
- Drawer and supporting panel surfaces.
- Chat transcript, turns, receipts, and composer.
- Artifact list/detail surfaces.
- Memory and notes drawer styling.
- Expanded artifact width changes only if a later plan explicitly updates and justifies `tests/test_workspace_static.py`.
- Activity styling remains dormant/non-visible in the current UI.

## 2026-08-28 - Accepted Workspace Indicator Pass

Status: accepted after user verification.

Scope:
- Implemented a minimal top-bar workspace indicator pass.
- Rendered the selected workspace as `Agent Col | <workspace name>`.
- Reused existing authoritative workspace state from `state.workspaces.items` and `state.workspaces.selectedWorkspaceId`.
- Did not create duplicate frontend state or add backend/API behavior.
- Preserved auth, workspace selection, Notes, Chats, Memory, artifacts, routing, persistence, layout behavior, request construction, and existing workspace list behavior.

Source changed:
- `frontend/index.html`: added a hidden top-bar indicator span beside `Agent Col`.
- `frontend/workspace-indicator.mjs`: added a small renderer that derives the selected display name from existing workspace state.
- `frontend/app.mjs`: refreshed the indicator during workspace render and after workspace list load.
- `frontend/styles.css`: added compact muted indicator styling.
- `tests/frontend/workspace-indicator.test.mjs`: covered selected-workspace display updates and hidden unknown selection state.
- `tests/test_workspace_static.py`: updated the stale exact `<h1>` assertion and checked that the indicator placeholder exists.

Verification:
- `node --test tests/frontend/workspace-indicator.test.mjs` failed before implementation with `ERR_MODULE_NOT_FOUND`, then passed after implementation: 2 tests.
- `git diff --check` passed.
- `node --check frontend/app.mjs` passed.
- `node --test tests/frontend/workspace-static.test.mjs` passed: 7 tests.
- `node --test tests/frontend/workspace-view.test.mjs` passed: 2 tests.
- `node --test tests/frontend/state.test.mjs` passed: 42 tests.
- `node --test tests/frontend/auth-view.test.mjs` passed: 7 tests.
- `node --test tests/frontend/chat-view.test.mjs` passed: 9 tests.
- `venv/bin/pytest tests/test_workspace_static.py -q` passed: 4 tests, with one existing `BaseAgentConfig` deprecation warning.

Screenshot:
- `/tmp/agent-col-workspace-indicator.png`
- The screenshot used a temporary HTML preview with current real HTML/CSS and injected sample indicator text.

## 2026-08-28 - Accepted Composer Keyboard Submit Pass

Status: accepted after user verification.

Scope:
- Implemented a minimal composer keyboard-submit behavior pass.
- Pressing Enter or Return while the message textarea is focused submits through the existing form submit path.
- Pressing Shift+Enter remains normal textarea newline behavior and does not submit.
- Reused the existing `createChatView` form submit listener and `app.mjs` submit path instead of adding a second chat-request path.
- Preserved request construction, idempotency, auth, retry behavior, character limit display, pending-turn rules, Send button behavior, persistence, and backend behavior.

Source changed:
- `frontend/chat-view.mjs`: added a textarea `keydown` listener that calls `elements.form.requestSubmit()` for Enter/Return without Shift.
- `tests/frontend/chat-view.test.mjs`: added focused tests for Enter submitting once through the existing form path and Shift+Enter not submitting.

Verification:
- `node --test tests/frontend/chat-view.test.mjs` failed before implementation because the keydown handler was absent, then passed after implementation: 11 tests.
- `git diff --check` passed.
- `node --test tests/frontend/state.test.mjs` passed: 42 tests.
- `node --test tests/frontend/requests.test.mjs` passed: 19 tests.
- `node --test tests/frontend/workspace-static.test.mjs` passed: 7 tests.

## 2026-08-28 - Accepted Chat Transcript And Model Response Styling Pass

Status: accepted after corrected user visual verification.

Scope:
- Implemented the fifth bounded CSS-only visual pass.
- Corrected the initial visual miss by removing the card treatment from `.turn`.
- Kept `.turn` structural so the user message and Agent Col response are not visually wrapped into one shared card.
- Applied the raised response surface, border, radius, padding, readable line-height, and teal rail to `.turn-model` itself.
- Kept `.turn-user` compact and visually minimal.
- Kept receipt chips underneath as compact secondary metadata.
- Did not modify Markdown rendering, response text, JavaScript, HTML, prompts, receipt construction, submit behavior, backend behavior, or selectors outside the approved Pass 5 boundary.

CSS surface changed:
- `.conversation`
- `.chat-transcript`
- `.turn`
- `.turn-user`
- `.turn-model`
- `.turn-receipts`
- `.receipt-list`
- `.receipt-item`

Verification:
- Temporary Pass 5 CSS assertion failed before implementation for the missing chat transcript treatment, then passed after implementation.
- Manual verification rejected the first attempt because `.turn` incorrectly grouped user and model content in one visual card.
- Correction assertion failed before the fix because `.turn` still owned the card surface and `.turn-model` did not; the corrected assertion passed after moving the surface to `.turn-model`.
- `git diff --check` passed.
- `node --test tests/frontend/chat-view.test.mjs` passed: 11 tests.
- `node --test tests/frontend/workspace-static.test.mjs` passed: 7 tests.
- `node --test tests/frontend/state.test.mjs` passed: 42 tests.

Screenshot:
- `/tmp/agent-col-pass5-corrected.png`
- The screenshot used a temporary HTML preview with current real HTML/CSS and sample chat content.

## 2026-08-28 - Accepted Left Drawer Density And Navigation Rows Pass

Status: accepted after user visual verification.

Scope:
- Implemented the fourth bounded CSS-only visual pass.
- Touched implementation source only in `frontend/styles.css`.
- Made left drawer sections read as structured navigation rows while preserving existing Expand/Hide behavior.
- Preserved Hide/Refresh actions, Expand semantics, `aria-expanded`, `data-section` values, collapsed/expanded behavior, and independent drawer scrolling.
- Did not modify frontend modules, `frontend/index.html`, tests, backend code, chat styling, artifact styling, memory/notes behavior, or Google Sign-In internals.

CSS surface changed:
- `.supporting-panel`
- `.drawer-heading`
- `.drawer-toggle`
- `.section-heading h2`
- `.drawer-section`
- `@supports selector(:has(*)) .drawer-section:has([aria-expanded="true"])`

Verification:
- Temporary Pass 4 CSS assertion failed before implementation for the missing drawer navigation-row treatment, then passed after the CSS patch.
- `git diff --check` passed.
- `node --test tests/frontend/workspace-static.test.mjs` passed: 7 tests.
- `node --test tests/frontend/auth-view.test.mjs` passed: 7 tests.
- `node --test tests/frontend/chat-view.test.mjs` passed: 9 tests.
- `venv/bin/pytest tests/test_workspace_static.py -q` passed: 4 tests, with one existing `BaseAgentConfig` deprecation warning.

Screenshot:
- `/tmp/agent-col-shell-pass4.png`
- The screenshot used a temporary HTML preview generated from the real `frontend/index.html` and current `frontend/styles.css`, with the workspace grid unhidden and one drawer section marked expanded to show the active `:has()` state.

Deferred to later bounded passes:
- Chat transcript, turns, receipts, and composer.
- Artifact list/detail surfaces.
- Memory and notes drawer styling.
- Expanded artifact width changes only if a later plan explicitly updates and justifies `tests/test_workspace_static.py`.
- Activity styling remains dormant/non-visible in the current UI.

## 2026-08-28 - Accepted Workspace Grid Proportions Pass

Status: accepted after user visual verification.

Scope:
- Implemented the third bounded CSS-only visual pass.
- Touched implementation source only in `frontend/styles.css`.
- Rebalanced persistent workspace columns without changing layout state logic.
- Preserved `grid-template-areas`, collapse class semantics, restore buttons, independent scroll ownership, and the expanded artifact `80vw` behavior.
- Did not modify frontend modules, `frontend/index.html`, tests, backend code, drawer row styling, chat styling, artifact styling, or Google Sign-In internals.

CSS surface changed:
- `.workspace-grid`
- `.workspace-grid--left-collapsed`
- `.workspace-grid--right-collapsed`
- `.workspace-grid--left-collapsed.workspace-grid--right-collapsed`
- `.supporting-panel, .conversation, .work-panel`

Verification:
- Temporary Pass 3 CSS assertion failed before implementation for the missing grid proportions, then passed after the CSS patch.
- `git diff --check` passed.
- `node --test tests/frontend/workspace-static.test.mjs` passed: 7 tests.
- `node --test tests/frontend/auth-view.test.mjs` passed: 7 tests.
- `node --test tests/frontend/chat-view.test.mjs` passed: 9 tests.
- `venv/bin/pytest tests/test_workspace_static.py -q` passed: 4 tests, with one existing `BaseAgentConfig` deprecation warning.

Screenshot:
- `/tmp/agent-col-shell-pass3.png`
- The screenshot used a temporary HTML preview generated from the real `frontend/index.html` and current `frontend/styles.css`, with the context gate hidden, the workspace grid unhidden, and app JavaScript removed because the sandbox denied binding the local FastAPI server to `127.0.0.1:8765`.

Deferred to later bounded passes:
- Drawer and supporting panel surfaces.
- Chat transcript, turns, receipts, and composer.
- Artifact list/detail surfaces.
- Memory and notes drawer styling.
- Expanded artifact width changes only if a later plan explicitly updates and justifies `tests/test_workspace_static.py`.
- Activity styling remains dormant/non-visible in the current UI.
