# Unsafe Frontend Visual Polishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the Agent Col workspace visual and interaction polish requested on August 28, 2026, while making every HTML, JavaScript, backend, schema, accessibility, file-handling, and security-policy change explicit and approval gated.

**Architecture:** The accepted safe CSS-only sequence is complete. This plan crosses that boundary only in named passes where current source proves CSS cannot implement the requested behavior: iconized drawer rows, card-level disclosure mechanics, workspace deletion, direct user-authored note proposals, attachment drag-and-drop, character-count state coloring, safe Markdown rendering, and artifact viewer structural fidelity. Every pass preserves existing auth, persistence, request ownership, idempotency, memory, notes, artifacts, receipts, routing, prompts, model behavior, Google Sign-In, and hidden working-state boundaries unless that pass explicitly says otherwise.

**Tech Stack:** Static HTML, CSS, browser-native JavaScript ES modules, FastAPI, Firestore-backed services, Node `node --test` frontend tests, pytest backend tests, manual browser verification, and approved vendored frontend assets only when a pass explicitly authorizes them.

**Spec:** `AGENTS.md`, `docs/notes/frontend-work-notes.md`, `docs/deployment/post-deployment-handoff.md`, `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md`, `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md`, current frontend/backend source, current tests, user-provided local screenshot recorded in the original plan, and root visual target `agent-col-visual-target.jpeg`.

## Current Boundary

- Safe CSS-only visual work is complete and manually accepted.
- Remaining target fidelity requires source changes outside the visual-only boundary.
- This plan is not implementation approval. Approve only one bounded pass at a time.
- Every source-changing pass must follow `AGENTS.md`: investigate, propose, wait for approval, write a failing test first, verify RED, implement GREEN, refactor only after GREEN, run focused verification, report as `implemented, pending manual verification`, and wait for user acceptance.
- Do not checkpoint any pass until the user accepts manual verification.

## User Requirements Captured For This Revision

### Global

- Do not put emoji in code, UI copy, tests, fixtures, screenshots, or generated documentation examples for this application. Icons are allowed; emoji are not.
- The provided screenshot and `agent-col-visual-target.jpeg` are visual targets, not permission to invent behavior or expose hidden state.
- The existing chat conversation structure and layout are preferred and must not be broadly restructured during visual polish.
- Right drawer Artifact Viewer should move toward the screenshot structure and quality.

### Left Drawer

- Replace text section `Expand` / `Collapse` controls with arrow or chevron icon treatment while preserving accessible expanded/collapsed state.
- Parent menu cards are expandable disclosure containers, not selectable items. Selection/highlight styling belongs to child subcards that actually select or open records.
- Add icons to the left of parent menu card titles. Requested icons should match the screenshot as closely as practical:
  - Workspace: folder-like icon.
  - Artifacts: cube/package-like icon.
  - Notes: document/list icon.
  - Memory: brain/network-like icon, implemented as an icon, not emoji.
  - Chats: message bubble icon.
- Change highlighted child-subcard selection color toward translucent neon amber. This remains subject to later visual tuning.
- Add workspace deletion: workspaces need a delete action like memory, artifacts, and notes. Workspaces must have delete only, no archive option. Any owned workspace, including the original/default workspace, may be deleted as long as at least one workspace remains.
- Move the manual Create Artifact form below the artifact list inside the Artifacts drawer section.
- Add a Create Note button and functionality for user-authored authoritative note proposals. Direct create must bypass the model but must not bypass the collaborative-note security/policy contract; it must create a pending proposal for approval, not an immediately active note.
- Make memory cards collapsible and collapsed by default. Clicking the card itself expands it to reveal revoke/delete settings; there should be no separate per-card expand button.
- Use the same card-click-to-expand convention for left drawer parent cards and for Notes, Memory, and Chat child subcards where practical.
- Drawer-level collapse/expand can be iconized, but drawer behavior must remain intact.

### Chat Surface

- Preserve current chat surface structure and layout.
- Add an icon to the `Start a conversation` title.
- Change New conversation button icon treatment to a pencil-in-box or close equivalent.
- Keep model and user cards differentiated. Move model message accents toward purple; keep user prompt accents amber.
- Model response text and user prompt text may be tuned toward amber if readability and contrast remain acceptable.
- Add an Agent Col icon next to the Agent Col name/title in model response cards when that structural pass is approved.
- User prompt cards should use a computer-with-keyboard icon when that structural pass is approved.
- While a prompt is waiting on Agent Col, keep the text `Waiting for Agent Col` but add a three-dot wave animation and make the status text move in a gentle sine-wave-like vertical motion.
- Adaptation receipts/cards should live inside a parent disclosure card that is collapsed by default so profile adaptation proof remains inspectable without distracting from the conversation.
- Clean up visible model response formatting so Markdown markers such as heading hashes, asterisks, and table syntax render as structure rather than raw symbols. This means safe Markdown rendering, not changing stored response text or model output.
- Wire drag-and-drop file/image attachments into the chat box through an explicit attachment pass.
- Keep the send button treatment close to the screenshot.
- Keep character count underneath if desired, but color it:
  - green under 5,000 characters;
  - yellow from 5,000 through 8,999 characters;
  - red from 9,000 through 10,000 characters.
- Show a paperclip attachment affordance.
- Do not add an emoji menu.
- Remove or omit the `@` affordance.

### Right Drawer - Artifact Viewer

- The screenshot's Artifact Viewer is the target direction.
- Add artifact header/card, metadata chips, preview/info structure, Markdown/code/table readability, and compact action bar only through explicit source-backed passes.

## Official Documentation Evidence

- WAI-ARIA accordion pattern: accordion headers are controls for showing/hiding panels, and expanded panels require accurate `aria-expanded`. This controls drawer row and card disclosure design. https://www.w3.org/WAI/ARIA/apg/patterns/accordion/
- MDN `aria-expanded`: a focusable control that toggles content should expose current expanded/collapsed state, commonly with `aria-controls`. https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-expanded
- MDN button role and accessible names: prefer native `button`; icon-only buttons need an accessible name. https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/button_role and https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-label
- MDN CSS animations: keyframes and animation properties can animate visual values such as transforms over time. https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Animations
- MDN CSS transforms and `translateY()`: vertical wave motion should use transform translation so the animation does not change document flow. https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/transform and https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/transform-function/translateY
- MDN `prefers-reduced-motion`: nonessential motion must respect reduced-motion preferences. https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/%40media/prefers-reduced-motion
- MDN File API: web apps access files only when the user provides them through file input or drag and drop; files expose metadata and content through `File`/`FileList`. https://developer.mozilla.org/en-US/docs/Web/API/File_API
- MDN DataTransfer.files: dropped files are available through `DataTransfer.files`, but only during `drop` and `paste` events because other phases use protected mode. https://developer.mozilla.org/en-US/docs/Web/API/DataTransfer/files
- MDN `<input type="file">`: file input supports `accept`, `multiple`, and user-selected `files`; the value does not expose the true local path. https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/file
- OWASP File Upload Cheat Sheet: file upload must use allowlisted extensions/types, size limits, generated storage names, authorization, non-webroot or mediated storage, and content validation appropriate to risk. https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- MDN `innerHTML` and Trusted Types: generated strings assigned to HTML sinks are injection risks; prefer text APIs or sanitized `TrustedHTML`. https://developer.mozilla.org/en-US/docs/Web/API/Element/innerHTML and https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API
- DOMPurify README: DOMPurify sanitizes dirty HTML and warns that post-sanitization mutation can void sanitization. https://github.com/cure53/DOMPurify/blob/main/README.md
- markdown-it README: `html: false` default plus table support is the preferred browser Markdown path if vendored and approved. https://github.com/markdown-it/markdown-it
- Google Identity Services: do not replace the Google-rendered sign-in button with a custom button. https://developers.google.com/identity/gsi/web/guides/display-button
- Lucide: if the project approves vendored icon SVGs, Lucide provides consistent SVG icons under permissive licenses, but it adds license attribution and source-tracking obligations. https://lucide.dev/ and https://github.com/lucide-icons/lucide/blob/main/LICENSE

## Source-Backed Evidence

### Current Static Shell

- `frontend/index.html:12-26` has auth status, `Agent Col`, workspace indicator, and a New conversation button with an approved non-emoji inline SVG icon.
- `frontend/index.html:75-227` has parent drawer cards for Workspace, Artifacts, Notes, Memory, and Chats. Each parent card header is now one native full-width `button.section-heading[data-section-toggle]` with an icon, label, integrated chevron, and `aria-expanded`.
- `frontend/index.html:108-163` still places the `Create Artifact` form before `<div data-work-list>`, so moving Create Artifact below artifacts remains HTML work.
- `frontend/index.html:184-213` contains the conversation intro, transcript, composer, character counter, and send button. There is no start-title icon, attachment input, drop target, paperclip button, or attachment state.
- `frontend/index.html:217-227` has a right artifact drawer heading and detail target. It has no selected-artifact header card, metadata chips, Preview/Info tabs, Markdown rendering, or bottom action bar.

### Current Drawer Behavior

- `frontend/app.mjs:343-395` owns drawer and section `aria-expanded` updates. Parent drawer card disclosure is implemented through the full-card `data-section-toggle` button, not through separate small Expand buttons.
- `frontend/app.mjs:1179-1186` attaches click behavior to every `data-section-toggle` button.
- `frontend/workspace-layout.mjs` owns left/right drawer and independent section expansion state. It intentionally does not own a selected/highlighted parent drawer state.
- Parent drawer cards are expandable containers. They are not selectable menu items. Visual active/current highlighting belongs to selectable child subcards and should use the existing selected/current signals, such as `aria-current`.

### Current Workspace Behavior

- `main.py:1488-1565` exposes only list and create workspace routes.
- `database.py:463-579` exposes only `list_workspaces(...)` and `create_workspace(...)`.
- `database.py:513-524` currently synthesizes the default workspace into the returned list when no stored workspace document with that ID exists, so preserving the original/default workspace forever would conflict with the disposable-workspace model.
- `frontend/workspace-view.mjs:23-35` renders each workspace as a selectable child button and marks the selected workspace with `aria-current="true"`.
- `frontend/workspace-view.mjs:37-56` renders only a create form.
- No delete workspace route, API helper, state transition, or frontend button exists today.
- Firestore official documentation states that document deletes are supported in transactions, but deleting a document does not automatically delete documents in subcollections. This pass must therefore treat workspace data cleanup as an explicit server-side contract rather than assuming parent-document deletion removes all workspace-owned data. Sources: https://firebase.google.com/docs/firestore/manage-data/transactions and https://firebase.google.com/docs/firestore/manage-data/delete-data.

### Current Notes Behavior

- `main.py:1590-1905` exposes note list/detail/correction/archive/restore/delete routes.
- `main.py:1696-1762` creates correction proposals through the collaborative note service.
- `collaborative_note_service.py:157-174` routes corrections to `database.create_collaborative_note_proposal(...)`.
- `collaborative_note_service.py:176-219` creates model/natural note proposals after validating candidate evidence.
- `database.py:581-759` creates pending note proposals with session ownership validation, source-message validation, text normalization, conflict detection, and pending proposal cap.
- `collaborative_note_policy.py:11-17` restricts note kinds to `decision`, `requirement`, `constraint`, `task_state`, and `working_context`.
- `collaborative_note_policy.py:118-142` normalizes title/body text, limits title/body length, rejects control characters, requires note text to contain a letter, and reuses prohibited memory patterns plus note-specific blocked phrases.
- `frontend/notes-view.mjs:16-66` renders pending proposals with approve/reject.
- `frontend/notes-view.mjs:68-107` renders note-list child buttons and marks the selected note with `aria-current="true"`.
- `frontend/notes-view.mjs:172-215` renders selected note detail with Archive/Restore/Delete actions immediately visible.
- `frontend/notes-view.mjs:110-150` has correction proposal UI for selected notes.
- There is no direct Create Note button or direct user-authored note proposal route today.

### Current Memory Behavior

- `frontend/memory-view.mjs:58-95` renders active memory cards with visible Revoke/Delete actions immediately inside each card.
- `frontend/memory-view.mjs:97-133` renders pending proposal cards with visible Approve/Reject actions.
- `frontend/memory-view.mjs:158-195` renders pending proposals before identity context, active preferences, and recent events.
- `tests/frontend/memory-view.test.mjs` currently expects visible destructive buttons and confirmation behavior. Collapsible cards require test changes first.

### Current Chat Behavior

- `frontend/chats-view.mjs:39-59` renders chat-session child buttons and marks the selected session with `aria-current="true"`.
- `frontend/chat-view.mjs:69-82` renders each turn as `article.turn`, `p.turn-user`, `p.turn-model`, and `div.turn-receipts`.
- `frontend/chat-view.mjs:75-76` writes user/model text via `setText`.
- `frontend/render.mjs:1-3` writes `textContent`, preserving current HTML-injection safety.
- `frontend/chat-view.mjs:145-150` updates the character counter text only; no severity class or color state exists today.
- `frontend/chat-view.mjs:153-163` submits through the existing form path and supports Enter/Shift+Enter behavior.
- `frontend/app.mjs:589-624` sets `data-chat-status` to the static text `Waiting for Agent Col` while `/api/chat` is pending, then clears it after completion or failure.
- `frontend/index.html:196` renders chat status as `<p class="chat-status" data-chat-status role="status"></p>`.
- `frontend/chat-view.mjs:48-63` renders adaptation receipts as flat `li.receipt-item` entries inside the same receipt list as actions, citations, artifacts, memory, notes, continuity, and other proof.
- `frontend/app.mjs:627-678` wires only form, input, submit, retry, transcript, character count, clarification choices, and continuity choices into `createChatView`.
- No attachment route, attachment schema, file input, drop handler, upload store, or image preview pipeline exists today.

### Current Artifact Viewer Behavior

- `frontend/work-view.mjs:345-407` renders artifact-list child buttons and marks the selected artifact with `aria-current="true"`.
- `frontend/work-view.mjs:468-490` renders single-file artifact content as raw text in `<pre><code>` using `setText`.
- `frontend/work-view.mjs:719-763` renders artifact detail, export controls, content/detail, lifecycle/edit/version/feedback forms, and feedback history.
- `frontend/work-view.mjs:131-263` owns export strings and download behavior. Preview rendering must not alter exports.
- Existing artifact archive/restore/version/rename/feedback behavior must remain reachable if artifact detail is visually restructured.

### Dependency And Build Shape

- There is no `package.json` or frontend bundler.
- `frontend/index.html:7-8` loads only `/static/agent-col/styles.css` and `/static/agent-col/app.mjs`.
- Any icon library, Markdown library, sanitizer, or attachment dependency must be explicitly approved, vendored or pinned, licensed, and served through the existing static asset model.

## Global Invariants

- No emoji in application code, visible UI strings, CSS generated content, tests, fixtures, screenshots, or plan examples.
- No backend route, schema, prompt, model, routing, persistence, memory, notes, artifact lifecycle, idempotency, retry, auth, or working-state behavior changes except in the pass that explicitly owns that change.
- No generated/user content may enter the DOM through unsanitized HTML sinks.
- Markdown cleanup must be a presentation layer only: do not mutate stored model responses, request payloads, artifact content, exports, prompts, or responder instructions to remove symbols.
- Motion must be disabled or reduced under `prefers-reduced-motion`.
- Google Sign-In must remain Google-rendered.
- Direct user note creation must create a pending governed proposal. It must not create an active note directly.
- Workspace deletion must be permanent delete semantics, not archive semantics, and must be owner-scoped.
- Attachment support must not send arbitrary files to the model or storage without allowlist, size, type, authorization, and privacy decisions.
- Existing `/api/chat` text behavior, final responses, receipts, artifacts, notes, memory, continuity choices, retry, and persistence remain authoritative.
- Manual acceptance is required for every visual pass.

## Pass U1: Drawer And Top-Bar Structural Icons

**Goal:** Add the requested icon treatment to the drawer and New conversation/start title without changing drawer state, chat layout, Google Sign-In, or backend behavior.

**Expected files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/workspace-static.test.mjs`
- Test: `tests/frontend/workspace-layout.test.mjs`
- Test: `tests/frontend/auth-view.test.mjs`

**Implementation outline:**
- Add inline SVG icon spans or an approved small local icon helper for Workspace, Artifacts, Notes, Memory, Chats, Hide, Refresh, New conversation, and Start a conversation.
- Use decorative icons with `aria-hidden="true"` where visible text remains.
- Use `aria-label` only for icon-only buttons where no visible text remains.
- Replace section toggle visible text with chevron/arrow visual treatment only if tests prove `aria-expanded` still changes and the accessible name remains meaningful.
- Use no emoji. Do not use Unicode emoji as icons.
- Keep Google `[data-google-button]` untouched.

**RED tests:**
- Assert drawer section headings include decorative icon nodes while preserving `data-section`, `data-section-toggle`, and section title text.
- Assert New conversation keeps `data-new-conversation`, has accessible text/name, and includes a decorative icon.
- Assert Start a conversation includes a decorative icon without changing the `data-chat-transcript` or composer hooks.
- Assert Google Sign-In initialization still calls `accounts.renderButton`.

**Verification:**
- `node --test tests/frontend/workspace-static.test.mjs tests/frontend/workspace-layout.test.mjs tests/frontend/auth-view.test.mjs`
- `git diff --check`

**Manual targets:**
1. Expand/collapse each drawer section with mouse and keyboard; chevrons/arrows must reflect state.
2. Collapse/restore the left drawer and right drawer; controls remain reachable.
3. Start a new conversation; behavior remains unchanged.
4. Confirm no emoji appears anywhere in the UI.

## Pass U2: Drawer Subcard Selection Color, Compact Actions, And Artifact Form Position

**Goal:** Move active/current visual emphasis from parent drawer cards to selectable child subcards, tune those selected child subcards to translucent neon amber, reduce drawer action-button size, and move manual Create Artifact below the artifact list.

**Expected files:**
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/workspace-static.test.mjs`
- Test: `tests/frontend/work-view.test.mjs`
- Test: `tests/frontend/workspace-view.test.mjs`
- Test: `tests/frontend/chats-view.test.mjs`
- Test: `tests/frontend/notes-view.test.mjs`
- Test: `tests/frontend/memory-view.test.mjs`

**Implementation outline:**
- Move `<form data-artifact-create-form>` below `<div data-work-list>`.
- Preserve all form fields, names, `required`, `maxlength`, select options, and `data-artifact-create-form`.
- Treat parent drawer cards as expandable disclosure containers only. Do not add parent selection/highlight state.
- Update selected/current child subcard treatment toward translucent neon amber using existing selected signals such as `aria-current="true"`.
- Apply child subcard amber selected styling to workspace buttons, artifact buttons, note buttons, and chat-session buttons where they are currently selectable.
- Keep expanded parent drawer cards visually open but not selected. If expanded-parent styling remains, it must be subordinate to child selected/current styling and must not use the stronger selected-card treatment.
- Reduce visible drawer action buttons inside child/detail cards to approximately half their current visual weight using compact sizing. This applies to existing note, memory, artifact, and drawer secondary action buttons where the pass can do so with CSS only.
- Do not hide action buttons in this pass; hiding actions behind collapsed cards belongs to Pass U5.
- Do not change artifact request construction or backend routes.

**RED tests:**
- Static test proves `data-work-list` appears before `data-artifact-create-form`.
- Existing artifact create request tests remain unchanged and pass after the DOM move.
- CSS/static assertion proves selected child subcards use amber selected/current styling keyed to `aria-current="true"`.
- CSS/static assertion proves parent drawer-card expanded styling is not described as selectable and does not use the primary selected subcard selector.
- CSS/static assertion proves compact drawer action button styles apply to `.notes-actions`, `.memory-actions`, export/action controls, and drawer list/detail controls without changing handlers.

**Verification:**
- `node --test tests/frontend/workspace-static.test.mjs tests/frontend/work-view.test.mjs tests/frontend/workspace-view.test.mjs tests/frontend/chats-view.test.mjs tests/frontend/notes-view.test.mjs tests/frontend/memory-view.test.mjs`
- `git diff --check`

**Manual targets:**
1. Open Artifacts drawer; list appears above Create Artifact.
2. Create a manual artifact; payload and result remain unchanged.
3. Select a workspace, artifact, note, or chat subcard; the selected child subcard reads as translucent amber rather than teal.
4. Parent menu cards expand/collapse but do not read as selected menu items.
5. Existing action buttons in drawer cards/details are visibly smaller and less dominant.

## Pass U3: Workspace Permanent Deletion

**Goal:** Add owner-scoped workspace deletion with no archive option and a last-workspace protection rule.

**Approval status:** Approved by the user on August 28, 2026, after revision from default-workspace protection to last-workspace protection. Implementation is authorized for this bounded pass only; later passes still require separate approval.

**Expected files:**
- Modify: `schemas.py`
- Modify: `database.py`
- Modify: `main.py`
- Modify: `frontend/api.mjs`
- Modify: `frontend/state.mjs`
- Modify: `frontend/workspace-view.mjs`
- Modify: `frontend/app.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/test_main.py`
- Test: `tests/test_database.py`
- Test: `tests/frontend/api.test.mjs`
- Test: `tests/frontend/state.test.mjs`
- Test: `tests/frontend/workspace-view.test.mjs`

**Implementation outline:**
- Add `DELETE /api/users/{user_id}/workspaces/{workspace_id}`.
- Require resolved effective user ownership exactly like list/create routes.
- Enforce the invariant server-side: deletion is allowed for any owned workspace, including the original/default workspace, when at least one other owned workspace remains; deletion is rejected when it would leave zero workspaces.
- Do not make `is_default` or the derived original workspace ID a deletion blocker. The default/original workspace is disposable; only the final remaining workspace is protected.
- Use a Firestore transaction or equivalent server-side read-before-delete guard for the workspace-count check so two concurrent deletes cannot both pass based on stale list state.
- Define deletion semantics explicitly: remove the workspace metadata record and fail closed if dependent workspace data would be orphaned without a documented cleanup strategy.
- Because workspace subcollections may include notes/artifacts/chat state, do not implement broad recursive deletion until the data-retention and orphaning contract is approved and testable.
- Add frontend Delete action to workspace child cards with confirmation.
- Disable or omit Delete when the current list has one workspace, while keeping the backend as the authority for the last-workspace rule.
- If the deleted workspace was selected, refresh the workspace list and select a surviving workspace through the existing `selectWorkspace(...)` context-reset path.
- Do not add archive.

**RED tests:**
- Backend route returns 404/403-style bounded error for non-owned or missing workspace.
- Backend route deletes an owned non-final workspace and list no longer returns it.
- Backend route deletes the original/default workspace when another workspace remains.
- Backend route rejects deletion of the last remaining workspace with a bounded error.
- Concurrent delete regression: two delete attempts against the final two workspaces cannot both succeed and leave zero workspaces.
- Frontend renders Delete for workspace child cards when more than one workspace exists and does not render Archive.
- Frontend omits or disables Delete for the final remaining workspace.
- Frontend deletion refreshes selected workspace safely when the deleted workspace was selected.

**Verification:**
- `venv/bin/pytest tests/test_main.py -k "workspace and delete" -q`
- `venv/bin/pytest tests/test_database.py -k "workspace and delete" -q`
- `node --test tests/frontend/api.test.mjs tests/frontend/state.test.mjs tests/frontend/workspace-view.test.mjs`
- `git diff --check`

**Manual targets:**
1. Create at least two workspaces, delete either workspace, and confirm it disappears.
2. Confirm no Archive option exists for workspaces.
3. Confirm the original/default workspace can be deleted when another workspace remains.
4. Confirm deleting the currently selected workspace lands on a surviving workspace and resets the visible workspace context.
5. Confirm the last remaining workspace cannot be deleted and presents a bounded user-facing error or disabled delete control.
6. Confirm chats, notes, memory, and artifacts for other workspaces are unchanged.

## Pass U4: Direct User-Authored Note Proposal Creation

**Goal:** Add a Create Note button/form that bypasses the model but does not bypass the governed collaborative-note proposal policy.

**Expected files:**
- Modify: `schemas.py`
- Modify: `collaborative_note_service.py`
- Modify: `database.py` only if the existing proposal primitive needs a source/provenance-safe extension
- Modify: `main.py`
- Modify: `frontend/api.mjs`
- Modify: `frontend/state.mjs`
- Modify: `frontend/notes-view.mjs`
- Modify: `frontend/app.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/test_collaborative_note_policy.py`
- Test: `tests/test_collaborative_note_service.py`
- Test: `tests/test_main.py`
- Test: `tests/frontend/api.test.mjs`
- Test: `tests/frontend/state.test.mjs`
- Test: `tests/frontend/notes-view.test.mjs`

**Implementation outline:**
- Add a user-authored note proposal request model with `note_kind`, `title`, and `body`.
- Validate `note_kind` through `CollaborativeNoteKind`.
- Validate title/body with existing collaborative note policy normalization and prohibited-content checks.
- Create a pending `CollaborativeNoteProposal`, never an active `CollaborativeNote`.
- Preserve 24-hour proposal lifetime and approval/rejection flow.
- Use the active browser session and a source message/provenance strategy approved for direct user-created notes. If no valid source message exists, stop and revise; do not invent provenance.
- Add Create Note UI under Notes with explicit pending-proposal language.
- After creation, show the proposal in Pending proposals and require user approval.

**RED tests:**
- Direct create returns a pending proposal for policy-valid note text.
- Prohibited note text is rejected by policy before persistence.
- Direct create does not call model/router/responder code.
- Direct create does not create an active note until approved.
- Frontend Create Note form submits through the new API helper and appends the returned proposal to pending proposals.

**Verification:**
- `venv/bin/pytest tests/test_collaborative_note_policy.py tests/test_collaborative_note_service.py -k "direct or user_authored or proposal" -q`
- `venv/bin/pytest tests/test_main.py -k "collaborative_note and direct" -q`
- `node --test tests/frontend/api.test.mjs tests/frontend/state.test.mjs tests/frontend/notes-view.test.mjs`
- `git diff --check`

**Manual targets:**
1. Create a safe note proposal from the Notes drawer.
2. Confirm it appears under Pending proposals.
3. Approve it and confirm it becomes an active note.
4. Try prohibited or overlong content and confirm it is rejected safely.
5. Confirm no model response is generated by direct note creation.

## Pass U5: Standard Collapsible Notes, Memory, And Chat Subcards

**Goal:** Establish one standard child-card disclosure convention for Notes, Memory, and Chats: cards are collapsed by default, clicking the collapsed card expands it, and each card's respective actions appear only while expanded.

**Expected files:**
- Modify: `frontend/memory-view.mjs`
- Modify: `frontend/notes-view.mjs`
- Modify: `frontend/chats-view.mjs`
- Modify: `frontend/state.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/memory-view.test.mjs`
- Test: `tests/frontend/notes-view.test.mjs`
- Test: `tests/frontend/chats-view.test.mjs`
- Test: `tests/frontend/state.test.mjs`

**Implementation outline:**
- Add frontend-only expanded-card state keyed by stable record IDs.
- Render each collapsible subcard with a native button header or a focusable card with a native button control. Prefer native buttons.
- Clicking the collapsed card/header toggles details and action controls.
- Set accurate `aria-expanded` and `aria-controls`.
- Keep destructive Revoke/Delete confirmation checks unchanged.
- Notes:
  - Note-list child buttons still select notes; selected note detail card becomes collapsed by default and expands to show Archive/Restore/Delete and correction controls.
  - Pending note proposal cards collapse by default and expand to show Approve/Reject.
- Memory:
  - Active memory cards collapse by default and expand to show Revoke/Delete.
  - Pending memory proposal cards collapse by default and expand to show Approve/Reject.
- Chats:
  - Chat-session cards collapse by default. The collapsed surface should still show the preview/title; expansion reveals timestamp/metadata and any future chat-session actions.
  - Selecting/opening a chat must remain reachable and unambiguous. If one click cannot safely both select and expand, split the card into a primary Select/Open button plus a details disclosure button and return for approval.
- Exclusions:
  - Workspace child buttons remain simple select buttons; they do not expand in this pass.
  - Artifact child buttons already select/open artifact detail and do not get an additional collapse layer in this pass.
  - Action-button size reduction is handled in Pass U2 and should be preserved here.

**RED tests:**
- Memory active preference actions are absent/hidden before expansion.
- Clicking a memory card reveals Revoke/Delete controls and keeps confirmation behavior.
- Pending memory proposal card expansion reveals Approve/Reject controls.
- Pending note proposal card expansion reveals Approve/Reject controls.
- Selected note detail card expansion reveals Archive/Restore/Delete and correction controls.
- Chat session collapsed card shows the human preview; expansion reveals metadata without breaking session opening.
- Keyboard activation toggles the same state where the card is a disclosure control.
- Existing human label, selected/current state, and ID-secondary tests still pass.

**Verification:**
- `node --test tests/frontend/memory-view.test.mjs tests/frontend/notes-view.test.mjs tests/frontend/chats-view.test.mjs tests/frontend/state.test.mjs`
- `git diff --check`

**Manual targets:**
1. Open Memory; cards are collapsed by default.
2. Click a memory card; Revoke/Delete settings appear and still require confirmation.
3. Open Notes; pending proposal and selected-note detail actions are hidden until the relevant card is expanded.
4. Open Chats; chat cards are not visually overwhelming, and metadata/details appear only after expansion.
5. Confirm Workspace child buttons still only select workspaces.
6. Confirm Artifact child buttons still only select/open artifacts.

## Pass U6: Chat Pending Status Wave Animation

**Goal:** Keep the pending text `Waiting for Agent Col` while adding a three-dot wave animation and gentle sine-wave-like text motion during active model wait only.

**Expected files:**
- Modify: `frontend/app.mjs`
- Modify: `frontend/index.html` only if a static status child structure is approved
- Modify: `frontend/styles.css`
- Test: `tests/frontend/workspace-static.test.mjs`
- Test: `tests/frontend/chat-view.test.mjs` only if status rendering moves into `chat-view.mjs`

**Implementation outline:**
- Preserve the visible text `Waiting for Agent Col`.
- Add a pending-state attribute such as `data-chat-status-state="pending"` when `submitRequest(...)` is waiting, and clear it when status is cleared.
- Add three decorative dot elements only if the static text cannot be animated cleanly with CSS pseudo-elements.
- Use CSS keyframes and `transform: translateY(...)` for the wave motion so layout does not reflow.
- Use staggered animation delays for the dots and status text spans to approximate a sine-wave motion.
- Add or preserve a `prefers-reduced-motion: reduce` rule that disables the wave animation and leaves readable static text.
- Do not change `/api/chat`, request timing, submit/retry behavior, pending-turn state, or final response rendering.

**RED tests:**
- Pending submit path sets a pending status state while preserving the exact text `Waiting for Agent Col`.
- Successful completion clears the pending status state and text.
- Failure clears or removes the pending animation state before showing the error.
- Static/CSS test proves a reduced-motion guard exists for the pending animation.

**Verification:**
- `node --test tests/frontend/chat-view.test.mjs tests/frontend/workspace-static.test.mjs`
- `git diff --check`

**Manual targets:**
1. Submit a chat request; `Waiting for Agent Col` appears with wave text and three-dot motion.
2. Enable reduced motion in the browser/OS and confirm the status remains readable without motion.
3. Confirm retry, errors, and successful responses still behave unchanged.

## Pass U7: Chat Receipt And Adaptation Disclosure

**Goal:** Make adaptation proof collapsible by default inside a parent receipt/disclosure card so it remains inspectable without distracting from the conversation.

**Expected files:**
- Modify: `frontend/chat-view.mjs`
- Modify: `frontend/state.mjs` only if disclosure state must persist across render cycles
- Modify: `frontend/styles.css`
- Test: `tests/frontend/chat-view.test.mjs`
- Test: `tests/frontend/state.test.mjs` only if disclosure state is stored outside the DOM

**Implementation outline:**
- Keep action, citation, artifact, memory proposal, note, and continuity receipts visible as currently approved unless this pass explicitly scopes additional receipt disclosure.
- Group only adaptation receipts under a native disclosure control or an accessible button with `aria-expanded` and `aria-controls`.
- Default the adaptation parent card to collapsed.
- Use the visible label `Adaptations` or `Verified adaptations` and include a count when available.
- Keep individual adaptation values text-safe through `humanLabel(...)`, `humanValue(...)`, and text nodes.
- Do not remove adaptation data from responses or activity projection.
- Do not hide memory or continuity proof needed for user trust; this pass only reduces visual distraction.

**RED tests:**
- `renderReceipts(...)` renders adaptation receipts inside one collapsed parent when adaptations exist.
- The collapsed parent exposes a count and no raw signal IDs as primary text.
- Expanding the parent reveals individual adaptation labels and values.
- Non-adaptation receipts remain visible and unchanged.
- Malicious adaptation values remain text-safe.

**Verification:**
- `node --test tests/frontend/chat-view.test.mjs`
- `node --test tests/frontend/state.test.mjs` only if disclosure state changes state projection.
- `git diff --check`

**Manual targets:**
1. Trigger a response with adaptations; adaptation proof is collapsed by default.
2. Expand the adaptation parent card; individual adaptation proof appears.
3. Confirm other receipts remain readable and no raw internal IDs become primary labels.

## Pass U8: Chat Icons, Text Colors, And Counter Severity

**Goal:** Add requested chat icons, amber/purple text and accent tuning, and character-count severity colors while preserving the current chat structure/layout.

**Expected files:**
- Modify: `frontend/index.html`
- Modify: `frontend/chat-view.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/workspace-static.test.mjs`
- Test: `tests/frontend/chat-view.test.mjs`

**Implementation outline:**
- Add a decorative icon to `Start a conversation`.
- Add an Agent Col icon next to model author labeling only if the pass adds a minimal label wrapper without changing message order.
- Add a user computer/keyboard icon only if it can be added without changing turn ordering or request text rendering.
- Change `.turn-model` accent color toward purple.
- Change `.turn-user` accent and/or text color toward amber.
- Optionally tune model text toward amber only after checking contrast against the dark model card and purple accent.
- Update character counter to set one of `data-character-count-level="safe" | "warn" | "danger"` based on length thresholds.
- Do not add an emoji menu or `@` affordance.
- Keep `setText`/`textContent` for all user/model message content until the safe Markdown pass is approved.

**RED tests:**
- Character counter starts safe, becomes warn at 5,000 characters, and danger at 9,000 characters.
- Counter text remains `N / 10000`.
- Transcript still renders text safely for malicious strings.
- Static test proves no emoji-menu or at-sign control is introduced.
- Static/CSS test proves model and user color/accent variables are distinct.

**Verification:**
- `node --test tests/frontend/chat-view.test.mjs tests/frontend/workspace-static.test.mjs`
- `git diff --check`

**Manual targets:**
1. Type under 5,000 characters; counter is green.
2. Type 5,000 through 8,999 characters; counter is yellow.
3. Type 9,000 through 10,000 characters; counter is red.
4. Confirm model and user text/accent colors are readable.
5. Confirm no emoji menu or `@` control appears.
6. Confirm chat layout still matches the accepted current structure.

## Pass U9: Chat Attachment Input And Drag-Drop Intake

**Goal:** Add paperclip/file and image drag-and-drop intake to the chat box through a security-bounded attachment contract.

**Expected files:**
- Modify: `schemas.py`
- Modify: `main.py`
- Modify: `frontend/index.html`
- Modify: `frontend/api.mjs`
- Modify: `frontend/requests.mjs`
- Modify: `frontend/state.mjs`
- Modify: `frontend/chat-view.mjs`
- Modify: `frontend/app.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/test_main.py`
- Test: `tests/frontend/api.test.mjs`
- Test: `tests/frontend/requests.test.mjs`
- Test: `tests/frontend/state.test.mjs`
- Test: `tests/frontend/chat-view.test.mjs`

**Implementation outline:**
- First decision required before implementation: attachment mode.
  - Option A: local-only attachment chips for copied filename/content into the prompt.
  - Option B: server-uploaded attachments with storage, malware-risk policy, and model/context projection.
  - Option C: defer upload/storage and add disabled paperclip only.
- Recommended first pass: Option C or a narrow Option A for text files only. Image upload is higher risk and needs a storage/model contract.
- Use a real `<input type="file">` behind a paperclip button if active attachments are approved.
- Use `accept` allowlists and explicit size/count limits.
- Handle `dragenter`, `dragover`, `dragleave`, and `drop`; read `DataTransfer.files` only during `drop`.
- Reject unsupported types locally and server-side.
- Do not send binary/image data to the model unless a separate model-projection policy is approved.
- Do not log filenames or file contents in production logs.

**RED tests:**
- Dropping no files does not submit.
- Dropping unsupported file types shows a bounded error and does not call chat submit.
- Dropping allowed files records attachment chips/state without changing message text until the approved projection path runs.
- Sending a chat with attachments uses the approved request shape and preserves idempotency key behavior.
- Server rejects over-limit attachment payloads before model/service execution.

**Verification:**
- `venv/bin/pytest tests/test_main.py -k "attachment or upload" -q`
- `node --test tests/frontend/api.test.mjs tests/frontend/requests.test.mjs tests/frontend/state.test.mjs tests/frontend/chat-view.test.mjs`
- `git diff --check`

**Manual targets:**
1. Click paperclip and choose an allowed file; chip appears.
2. Drag an allowed file onto the composer; chip appears.
3. Try unsupported or oversized files; bounded error appears and no request is sent.
4. Send a normal no-attachment chat; unchanged behavior.
5. Confirm no emoji or `@` controls exist.

## Pass U10: Safe Markdown Response And Artifact Rendering Foundation

**Goal:** Render model responses and Markdown artifacts as readable headings, lists, code blocks, and tables so raw Markdown markers are not visually distracting, without XSS, stored text changes, prompt changes, or export changes.

**Expected files:**
- Create: `frontend/markdown-renderer.mjs`
- Create: `frontend/vendor/markdown-it.min.js`
- Create: `frontend/vendor/purify.min.js`
- Create: `frontend/vendor/THIRD_PARTY_NOTICES.md`
- Modify: `frontend/index.html`
- Modify: `frontend/chat-view.mjs`
- Modify: `frontend/work-view.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/markdown-renderer.test.mjs`
- Test: `tests/frontend/chat-view.test.mjs`
- Test: `tests/frontend/work-view.test.mjs`
- Test: `tests/test_workspace_static.py`

**Implementation outline:**
- Vendored `markdown-it` and DOMPurify require explicit approval to fetch, pin, checksum, license, and serve static assets.
- Configure Markdown rendering with raw HTML disabled.
- Sanitize rendered HTML before insertion.
- Fail closed to text rendering if parser/sanitizer is unavailable.
- This is the pass that addresses visible asterisks, heading markers, table pipes, and other Markdown syntax by rendering structure.
- Do not strip symbols out of model output strings.
- Do not change stored response text, artifact content, export/download strings, print behavior, prompts, or model output.

**RED tests:**
- Markdown headings, lists, fenced code, and tables render as structured DOM.
- Script tags, event attributes, and `javascript:` URLs are removed or rendered harmlessly.
- Existing export builders produce unchanged output strings.
- Missing renderer dependency falls back to text-safe output.

**Verification:**
- `node --test tests/frontend/markdown-renderer.test.mjs tests/frontend/chat-view.test.mjs tests/frontend/work-view.test.mjs tests/frontend/workspace-static.test.mjs`
- `venv/bin/pytest tests/test_workspace_static.py -q`
- `git diff --check`

**Manual targets:**
1. Markdown response renders headings, emphasis, lists, code blocks, and tables as structure instead of raw markers where safe.
2. Markdown artifact preview shows heading/table/code structure.
3. Malicious sample text is harmless.
4. Exported artifact content is unchanged.

## Pass U11: Artifact Viewer Header, Preview/Info, Metadata, And Action Bar

**Goal:** Move the right Artifact Viewer toward the screenshot's exact structure while preserving all artifact lifecycle behavior.

**Expected files:**
- Modify: `frontend/work-view.mjs`
- Modify: `frontend/state.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/work-view.test.mjs`
- Test: `tests/frontend/workspace-static.test.mjs`

**Implementation outline:**
- Add selected artifact header card with icon, title, metadata chips, and lifecycle status.
- Add Preview/Info tabs only with proper tab semantics and keyboard behavior, or implement them as segmented buttons if full tab semantics are not approved.
- Add compact action bar for copy/download/open/print-style actions, wired only to existing supported actions.
- Preserve export/download/print, edit, rename, version, archive, restore, feedback, and feedback history.
- Do not hide existing controls without a replacement path.
- Do not change artifact storage, schemas, MIME types, filenames, export payloads, or lifecycle routes.

**RED tests:**
- Detail renders artifact header, metadata chips, Preview and Info controls, one visible panel, and action bar.
- Switching Preview/Info changes only visible panel state and does not fetch, save, export, rename, edit, archive, restore, or submit feedback.
- Existing artifact export/print/rename/version/archive/restore/feedback tests still pass.

**Verification:**
- `node --test tests/frontend/work-view.test.mjs tests/frontend/workspace-static.test.mjs`
- `git diff --check`

**Manual targets:**
1. Select a Markdown artifact; right drawer visually matches the screenshot direction.
2. Switch Preview/Info.
3. Export/download/print, rename, save version, archive/restore, and feedback still work.
4. Long content remains readable and contained.

## Pass U12: Final Visual Fidelity And Accessibility Audit

**Goal:** Verify the completed unsafe polish against the screenshot and `agent-col-visual-target.jpeg`.

**Expected files:**
- Modify: `frontend/styles.css` only for CSS-only corrections.
- Modify behavior-bearing files only under a new approved fix plan if audit finds structural or accessibility regressions.
- Test: directly affected frontend/backend tests.

**Implementation outline:**
- Compare live `/workspace` against the provided screenshot and target image at desktop and narrow widths.
- Verify keyboard focus order through drawer controls, card disclosures, chat composer, attachment affordances, artifact viewer controls, tabs/buttons, and destructive actions.
- Verify no emoji, no `@` control, no fake unavailable controls, and no private working state.
- Verify Google sign-in remains Google-rendered.
- Verify reduced motion, overflow, focus visibility, and target sizes.

**Verification:**
- Run directly affected focused frontend tests.
- Run `venv/bin/pytest tests/test_workspace_static.py -q` if static serving or HTML changed.
- Run `git diff --check`.
- Broader `node --test tests/frontend/*.test.mjs` only if multiple shared frontend modules changed across prior accepted unsafe passes.

**Manual targets:**
1. Inspect `/workspace` against the screenshot at the user's browser/viewport.
2. Confirm no emoji appears.
3. Confirm no chat layout regression.
4. Confirm drawers, workspace delete, note proposal creation, memory disclosure, attachments, and artifact viewer behavior all match accepted pass behavior.

## Stop Conditions

- Stop if implementation would add emoji.
- Stop if workspace deletion cannot avoid orphaning or cross-owner data risk under a clear policy.
- Stop if direct note creation cannot produce a governed pending proposal with valid provenance.
- Stop if attachment support cannot be made secure with allowlists, limits, authorization, and privacy-safe logging.
- Stop if Markdown rendering cannot be made safe without a pinned, licensed, sanitized dependency path.
- Stop if drawer/card disclosure breaks keyboard or screen-reader semantics.
- Stop if artifact viewer tabs/action bars hide existing lifecycle controls.
- Stop if Google Sign-In would require a custom button.
- Stop if any pass cannot produce a valid failing test before production changes.

## Recommended Next Approval Request

Recommended first pass: **Pass U1: Drawer And Top-Bar Structural Icons**.

Reason: it implements visible target-alignment work from the user's screenshot while avoiding the larger backend deletion, governed note creation, attachment security, and Markdown sanitization decisions. It still requires source changes and TDD because iconized controls affect HTML, JavaScript-rendered labels, and accessibility semantics.
