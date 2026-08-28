# Unsafe Frontend Visual Polishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the Agent Col workspace visual polish toward the reference image while making the required HTML, JavaScript, rendering, accessibility, and dependency changes explicitly instead of hiding them inside CSS-only work.

**Architecture:** The safe CSS-only sequence is complete. This plan crosses the safe visual boundary only where current source proves CSS cannot create the target UI: drawer icons and chevrons, chat turn metadata/structure, rendered Markdown/code/table previews, artifact header/tabs/actions, and composer utility icons. Each pass must preserve existing backend routes, request payloads, idempotency, auth, persistence, workspace selection, Notes, Memory, Chats, artifact lifecycle, retry, and model behavior.

**Tech Stack:** Static HTML, CSS, browser-native JavaScript ES modules, FastAPI static serving, Node `node --test` frontend tests, Python static-route tests, manual browser verification, and one approved Markdown/sanitization dependency path before any HTML rendering.

**Spec:** `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md`, `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md`, `frontend-work-notes.md`, current frontend source, current frontend tests, and the reference image `agent-col-visual-target.jpeg`.

## Current Boundary

- Safe CSS-only visual work is complete and checkpointed at `eb1736b`.
- Remaining target fidelity requires non-safe frontend work because the current DOM/renderers do not contain the elements shown in the reference image.
- Plan status: approved for planning purposes.
- This plan does not authorize implementation by itself. Each pass requires separate explicit user approval before implementation and manual acceptance before checkpointing.

## Official Documentation Evidence

- WAI-ARIA accordion pattern: expansion controls must expose `aria-expanded`; an accordion header's button controls the related panel. This matters because the left drawer currently uses separate heading text and separate Expand buttons, so an iconized row/header rewrite is an accessibility/behavior structure pass, not CSS-only.
  - https://www.w3.org/WAI/ARIA/apg/patterns/accordion/
- WAI-ARIA tabs pattern: real Preview/Info tabs require tablist/tab/tabpanel semantics and keyboard behavior if implemented as tabs, not just visual labels.
  - https://w3c.github.io/wai-website/ARIA/apg/patterns/tabs/
- MDN `innerHTML`: assigning generated strings to HTML parses markup and is an XSS injection-sink risk; MDN recommends `TrustedHTML` plus Trusted Types enforcement, and notes `textContent` is appropriate when content should remain plain text.
  - https://developer.mozilla.org/en-US/docs/Web/API/Element/innerHTML
- MDN Trusted Types: Trusted Types centralize transformations for HTML injection sinks, but the application must still provide a sanitizer policy.
  - https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API
- DOMPurify official README: DOMPurify sanitizes dirty HTML strings and warns that post-sanitization mutation can void sanitization.
  - https://github.com/cure53/DOMPurify/blob/main/README.md
- CommonMark spec: Markdown includes raw HTML handling, so Markdown rendering is not automatically safe.
  - https://spec.commonmark.org/spec
- commonmark.js official README: the JavaScript reference implementation can render CommonMark, and its `safe` option suppresses raw HTML and unsafe URLs.
  - https://github.com/commonmark/commonmark.js/
- markdown-it official README: default JavaScript configuration has `html: false` and includes GFM table support; table support matters because the visual target artifact preview includes a Markdown table.
  - https://github.com/markdown-it/markdown-it
- MDN `<button>` accessibility: icon-only buttons need accessible names; visible text is safer when icon meaning may be unfamiliar.
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/button
- Google Identity Services integration docs: websites should not use their own Sign in with Google button; the Google-rendered button flow is handled by Google.
  - https://developers.google.com/identity/gsi/web/guides/integrate

## Source-Backed Evidence

### Safe Guide Boundary

- `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md:19` says CSS-only changes are the default safe path and HTML/JavaScript changes are not visual-only unless explicitly limited.
- `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md:43-58` marks `frontend/app.mjs`, `frontend/auth-view.mjs`, `frontend/state.mjs`, `frontend/api.mjs`, `frontend/requests.mjs`, `frontend/render.mjs`, `frontend/workspace-layout.mjs`, `frontend/chat-view.mjs`, `frontend/work-view.mjs`, `frontend/workspace-view.mjs`, `frontend/notes-view.mjs`, `frontend/memory-view.mjs`, `frontend/chats-view.mjs`, and dormant `frontend/activity-view.mjs` as behavior-bearing surfaces.
- `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md:284-305` forbids API, event-handler, reducer, hidden/disabled/expanded, content parsing, Markdown generation, and `innerHTML` changes in visual-only passes.
- `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md:307-327` distinguishes styling already-rendered content from changing response parsing, Markdown/export generation, or model behavior.

### Existing Visual Plan Boundary

- `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md:5-8` defines the first visual plan as behavior-preserving and locks HTML, JavaScript, backend routes, prompts, schemas, persistence, auth, memory, notes, artifacts, and working-state behavior.
- `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md:38-45` already corrected stale assumptions around dark tokens, `:has()`, Google Sign-In internals, and raw artifact previews.
- `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md:528-607` says Pass 5 preserved `textContent` and did not implement Markdown rendering.
- `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md:685-759` says Pass 7 styled raw artifact content but did not add Markdown parsing, syntax highlighting, tabs, content transformation, or truncation.
- `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md:766-833` keeps Activity styling dormant because the current app has no Activity section.

### Current Source Gaps Against The Reference Image

- Static shell:
  - `frontend/index.html:12-20` has a top bar with auth text, `Agent Col | <workspace>`, and a plain New conversation button. The reference image's plus icon is not a real DOM/icon element today.
  - `frontend/index.html:58-180` has left drawer rows with text headings and text Expand buttons. There are no leading icons or chevron controls like the reference image.
  - `frontend/index.html:217-227` has the right artifact panel heading and two text buttons. There is no selected-artifact header card, no metadata-chip row, no Preview/Info tab structure, and no bottom icon action bar in static HTML.
- Drawer behavior:
  - `frontend/workspace-layout.mjs:1-19` defines only left/right drawer state and five drawer sections: workspace, work, notes, memory, chats.
  - `frontend/app.mjs:343-384` toggles layout classes and writes `aria-expanded` plus visible text for drawer and section controls. Replacing Expand/Collapse text with chevrons or making the entire row a button touches behavior/accessibility logic.
- Chat transcript:
  - `frontend/chat-view.mjs:69-82` renders each turn as `article.turn`, `p.turn-user`, `p.turn-model`, then receipts. It does not render avatars, actor labels, timestamp elements, nested message bodies, or model-card headers.
  - `frontend/chat-view.mjs:75-76` uses `setText(...)`, and `frontend/render.mjs:1-3` writes `textContent`. This preserves safety but exposes raw Markdown syntax.
  - `frontend/state.mjs:263-301` stores a live completed turn as `{ request, response }` without display timestamp metadata.
  - `schemas.py:903-908` includes `ChatMessageRecord.timestamp`, and `database.py:1450-1476` returns persisted session messages ordered by timestamp, but `frontend/state.mjs:487-543` rebuilds reopened transcript without preserving timestamps.
- Artifact viewer:
  - `frontend/work-view.mjs:719-763` renders artifact detail as export controls followed by content/detail/forms/feedback. It does not create the target image's artifact-header card, Preview/Info tab model, or action toolbar.
  - `frontend/work-view.mjs:468-490` renders single-file artifact content as raw `<pre class="artifact-content"><code>...</code></pre>` with `setText`, not rendered Markdown.
  - `frontend/work-view.mjs:131-263` already builds Markdown/Text/HTML export links. Changing preview rendering must not change these export payloads.
  - `schemas.py:198-225` supports code, document, and data artifact formats including Markdown, HTML, Bash, JSON, and text, so renderer selection must be format-aware.
- Google Sign-In:
  - `frontend/auth-view.mjs:42-70` initializes Google Identity Services and calls `accounts.renderButton(...)`.
  - `tests/frontend/auth-view.test.mjs:98-134` asserts that initialization calls `renderButton` and passes credentials through. The plan must not replace this with a custom Google button.
- Dependency/build shape:
  - There is no `package.json` or frontend bundler in the current repo.
  - `requirements.txt:1-8` and `requirements-dev.txt:1-4` only pin Python/runtime/test dependencies.
  - `frontend/index.html:7-8` loads one CSS file and one JavaScript module from `/static/agent-col`.
  - Existing project specs repeatedly avoid package dependencies for the lightweight browser workspace. A Markdown/sanitizer dependency must therefore be separately approved and pinned or vendored deliberately.

## Required Unsafe Work

1. Add real presentational structure for drawer/top/action icons while preserving accessible names and existing controls.
2. Restructure chat turn rendering enough to show actor labels, optional timestamps, avatar/identity marks, model headers, message bodies, and receipt attachment without changing request/response content.
3. Preserve or project chat timestamps from existing persisted message records where available; decide explicitly how live newly submitted turns display time without changing backend behavior.
4. Add a safe Markdown rendering pipeline for model responses and Markdown artifacts, including sanitizer policy, XSS tests, and raw-text fallback.
5. Add artifact viewer structure for a header card, metadata chips, Preview/Info affordance, preview body, details body, and compact action controls while preserving selection, export, print, edit, rename, version, archive, restore, and feedback behavior.
6. Add visual affordances for composer utility controls only if real behavior exists or the controls are explicitly disabled/non-interactive with accessible explanation. Do not fake upload, mention, or emoji behavior.
7. Keep Google Sign-In as the Google-rendered button; style only the surrounding app shell.

## Global Invariants

- No backend route, schema, prompt, model, routing, persistence, memory, notes, artifact lifecycle, idempotency, retry, auth, or working-state behavior changes unless a later pass explicitly says so and receives approval.
- No private working-state or hidden model context may become visible.
- No generated/user content may be inserted with unsanitized `innerHTML`.
- No custom Sign in with Google button may replace the Google-rendered button.
- Every JavaScript/HTML pass must start with a failing focused test and report RED/GREEN evidence.
- The user manually accepts each visual pass before checkpointing.

## Pass U1: Drawer And Top-Bar Structural Icons

**Goal:** Match the reference image's drawer row affordances and top-bar action icon treatment without changing drawer state behavior.

**Expected files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/workspace-static.test.mjs`
- Test: `tests/frontend/workspace-layout.test.mjs`
- Test: `tests/frontend/auth-view.test.mjs`

**Implementation outline:**
- Add decorative icon spans with `aria-hidden="true"` inside existing drawer section headings and top-bar New conversation button.
- Keep visible text labels: Workspace, Artifacts, Notes, Memory, Chats, Hide, Refresh, New conversation.
- Keep the existing `data-section-toggle`, `data-drawer-toggle`, `data-left-refresh`, and `data-new-conversation` hooks.
- Do not replace Google Sign-In internals or `[data-google-button]`.
- If replacing Expand/Collapse text with a chevron, keep an accessible text label in the button and test that `aria-expanded` still changes in `frontend/app.mjs:377-384`.

**RED tests:**
- Add an assertion that drawer sections contain decorative icon elements without removing `data-section` and `data-section-toggle`.
- Add an assertion that top-bar New conversation still has visible/accessible text and the same data hook.
- Preserve `initializeGoogleSignIn` tests proving Google button rendering still uses `accounts.renderButton`.

**Verification:**
- `node --test tests/frontend/workspace-static.test.mjs tests/frontend/workspace-layout.test.mjs tests/frontend/auth-view.test.mjs`
- `git diff --check`
- Manual: expand/collapse each left drawer section, collapse/restore left drawer, start a new conversation, verify no custom Google button was introduced.

## Pass U2: Chat Turn Structure, Metadata, And Receipt Attachment

**Goal:** Give user and Agent Col turns the structural pieces visible in the reference image while preserving request construction and response content.

**Expected files:**
- Modify: `frontend/chat-view.mjs`
- Modify: `frontend/state.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/chat-view.test.mjs`
- Test: `tests/frontend/state.test.mjs`

**Implementation outline:**
- Replace the current `p.turn-user`/`p.turn-model` direct pair with nested DOM that keeps the same text but adds presentational wrappers:
  - user row with actor label "You", body, and optional timestamp;
  - model row with actor label "Agent Col", body container, optional timestamp, and receipt region under the model body.
- Preserve `setText` for user/model body content in this pass; Markdown rendering waits for Pass U3.
- Preserve `aria-live="polite"` on the existing transcript container.
- Preserve `createChatView` submit, Enter/Shift+Enter, retry, memory clarification, and continuity behavior.
- Preserve persisted session timestamps from `ChatMessageRecord.timestamp` when `completeChatSessionDetailLoad(...)` rebuilds transcript.
- For live just-completed turns, either omit timestamps or add a frontend-only display timestamp through an approved state field. Do not invent server authority.

**RED tests:**
- `renderTranscript` produces actor labels, separate user/model body nodes, and receipts attached beneath the model row.
- `renderTranscript` still uses text-safe rendering for malicious user/model strings.
- `completeChatSessionDetailLoad` preserves existing message timestamps if timestamp display is approved for this pass.

**Verification:**
- `node --test tests/frontend/chat-view.test.mjs tests/frontend/state.test.mjs tests/frontend/workspace-static.test.mjs`
- `git diff --check`
- Manual: send a normal message, verify one request is sent, receipts still appear, retry still works after a forced failure, and reopened chat sessions still load.

## Pass U3: Safe Markdown Rendering Foundation

**Goal:** Render model responses and Markdown artifacts as readable headings, lists, code blocks, and tables without introducing XSS or changing stored/exported content.

**Expected files for the recommended path:**
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
- Use vendored browser-ready `markdown-it` and DOMPurify assets under `frontend/vendor/` after explicit approval to fetch, pin, verify license text, and record source URLs/checksums in `frontend/vendor/THIRD_PARTY_NOTICES.md`.
- Configure `markdown-it` with `html: false`, because the target preview needs tables and the official README documents table support while keeping raw HTML disabled by default.
- Add a renderer helper that returns sanitized DOM or `TrustedHTML` output using DOMPurify before any insertion into an HTML sink.
- Add a raw-text fallback for missing parser/sanitizer so the app fails closed.
- Do not change model prompts, API response text, artifact storage, export/download payloads, or print behavior.
- Do not render raw HTML from Markdown unless the sanitizer policy explicitly allows it and tests prove unsafe attributes/elements are removed.

**Rejected path for this plan:**
- Do not add `package.json`, a bundler, or runtime CDN dependencies in this pass. That would expand the build/deploy surface beyond the current static module app.
- Do not use `commonmark.js` for the recommended path unless the user accepts losing table fidelity or approves a separate table plugin/renderer decision.

**RED tests:**
- Markdown headings, bold text, lists, fenced code, and table syntax render into structured DOM.
- `<img onerror>`, `<script>`, `javascript:` URLs, and raw HTML payloads do not execute and do not survive into unsafe output.
- Export builders still emit the same Markdown/Text/HTML download strings as before.
- Existing `renderTranscript uses textContent...` test is revised into a safety test for sanitized Markdown rendering, with RED evidence before production code changes.

**Verification:**
- `node --test tests/frontend/markdown-renderer.test.mjs tests/frontend/chat-view.test.mjs tests/frontend/work-view.test.mjs tests/frontend/workspace-static.test.mjs`
- `venv/bin/pytest tests/test_workspace_static.py -q`
- `git diff --check`
- Manual: verify raw `###`, `**`, and `---` no longer show in model Markdown responses, artifact Markdown preview renders headings/table/code, and malicious sample text is displayed harmlessly.

## Pass U4: Artifact Viewer Header, Tabs, Details, And Action Bar

**Goal:** Match the reference image's artifact drawer structure: selected artifact card, metadata chips, Preview/Info tabs, preview body, detail body, and compact action bar.

**Expected files:**
- Modify: `frontend/work-view.mjs`
- Modify: `frontend/styles.css`
- Test: `tests/frontend/work-view.test.mjs`
- Test: `tests/frontend/workspace-static.test.mjs`

**Implementation outline:**
- Split current `renderWorkDetail(...)` into explicit sub-renderers:
  - selected artifact header;
  - metadata chip row;
  - tab controls;
  - Preview panel;
  - Info panel;
  - action toolbar;
  - existing edit/rename/version/lifecycle/feedback controls.
- Use current artifact detail fields only: reference display label, filename, format, family, byte size, summary, lifecycle status, and content.
- Add tab state only in frontend view state if required; do not call new backend routes.
- Keep export/download/print actions wired to existing export builders and handlers.
- Keep archive/restore/edit/rename/version forms available even if moved under Info.

**RED tests:**
- `renderWorkDetail` renders selected artifact title, metadata chips, Preview and Info controls, and one preview panel.
- Switching tabs changes visible panel only and does not fetch, save, export, rename, edit, archive, restore, or submit feedback.
- Existing artifact export, print, rename, version, archive, restore, feedback tests still pass.

**Verification:**
- `node --test tests/frontend/work-view.test.mjs tests/frontend/workspace-static.test.mjs`
- `git diff --check`
- Manual: select a Markdown artifact, switch Preview/Info, export/download/print, rename, save a version, archive/restore, and verify the right drawer visually matches the target more closely.

## Pass U5: Composer Utility Icon Boundary

**Goal:** Decide whether the paperclip, mention, and emoji affordances in the reference image are real controls, disabled placeholders, or excluded from the product.

**Expected files:**
- Modify only after approval: `frontend/index.html`, `frontend/chat-view.mjs`, `frontend/styles.css`
- Test: `tests/frontend/chat-view.test.mjs`
- Test: `tests/frontend/workspace-static.test.mjs`

**Implementation outline:**
- If no upload/mention/emoji behavior is approved, do not render active controls that imply unavailable features.
- If disabled visual placeholders are approved, render disabled buttons with accessible names and no event handlers.
- If real utility behavior is approved, split it into separate behavior plans; this visual plan must not add upload, mention, or emoji workflows.

**RED tests:**
- Disabled utility placeholders, if approved, are disabled, have accessible names, and do not call submit.
- Enter/Shift+Enter and Send button behavior remain unchanged.

**Verification:**
- `node --test tests/frontend/chat-view.test.mjs tests/frontend/workspace-static.test.mjs`
- `git diff --check`
- Manual: verify utility icons do not imply working upload/mention/emoji behavior unless those behaviors are separately implemented and accepted.

## Pass U6: Final Visual Fidelity And Accessibility Audit

**Goal:** Verify the unsafe visual polish against the target image after structural passes land.

**Expected files:**
- Modify: `frontend/styles.css` only if audit fixes are CSS-only.
- Modify behavior-bearing files only with a new approved fix plan if audit finds structural/accessibility regressions.
- Test: directly affected frontend tests.

**Implementation outline:**
- Compare live `/workspace` against `agent-col-visual-target.jpeg` at desktop and narrow widths.
- Verify keyboard focus order through drawer, transcript controls, artifact tabs/actions, and composer.
- Verify reduced motion, overflow, focus visibility, and target size.
- Verify Google sign-in still uses the Google-rendered button.
- Verify no private working-state data appears.

**Verification:**
- `node --test tests/frontend/*.test.mjs` only if the prior passes touched multiple shared frontend modules.
- `venv/bin/pytest tests/test_workspace_static.py -q`
- `git diff --check`
- Manual: target-image comparison on the same browser/viewport the user uses for acceptance.

## Stop Conditions

- Stop if implementation requires backend route/schema/model/prompt changes.
- Stop if Markdown rendering cannot be made safe without a dependency or CSP decision.
- Stop if a dependency cannot be pinned, vendored, licensed, and served through the existing static asset model.
- Stop if changing drawer rows breaks keyboard or screen-reader semantics.
- Stop if artifact tabs hide existing edit/export/archive/version/feedback actions.
- Stop if Google Sign-In would require a custom button.
- Stop if tests cannot reproduce the intended behavior before production changes.

## Approval Request

Approve only the next bounded pass, not the whole unsafe plan. Recommended first unsafe pass is **Pass U1: Drawer And Top-Bar Structural Icons**, because it improves visible fidelity while avoiding Markdown sanitization and artifact view-state decisions.
