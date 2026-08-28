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
