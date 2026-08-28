# Frontend Visual Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Agent Col browser workspace so its finished visual quality matches the reference image at `agent-col-visual-target.jpeg`, while preserving the current application behavior exactly.

**Architecture:** This is a visual-only frontend pass. The primary implementation surface is `frontend/styles.css`; the current four-region workspace structure remains unchanged: top bar, left drawer, chat surface, and right artifact drawer. HTML, JavaScript, backend routes, prompts, schemas, persistence, auth, memory, notes, artifacts, and working-state behavior are locked unless a later separately approved behavior pass changes that boundary.

**Tech Stack:** Static HTML, CSS, vanilla JavaScript modules, FastAPI static serving, Node frontend tests, browser/manual visual verification.

**Spec:** `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md`, `agent-col-visual-target.jpeg`, current `frontend/index.html`, current `frontend/styles.css`.

## Global Constraints

- Use `agent-col-visual-target.jpeg` as the visual benchmark.
- Default implementation surface is `frontend/styles.css`.
- Do not change backend routes, request payloads, schemas, prompts, auth, persistence, memory, notes, artifacts, working state, or model behavior.
- Do not change JavaScript state, event handlers, request builders, render logic, export behavior, retry behavior, or hidden/disabled/expanded semantics.
- Do not change `frontend/index.html` unless a later approved pass allows purely presentational classes.
- Do not expose hidden working state or private context.
- Preserve all existing user actions, routes, response data, records, receipts, and lifecycle behavior.
- CSS-only visual work requires focused automated checks plus manual visual acceptance; automated tests do not replace visual review.

---

## Source-Backed Boundary Findings

### Safe Primary File

`frontend/styles.css` is the primary safe file because the safe visual guide explicitly assigns it responsibility for colors, spacing, typography, borders, panel layout, scroll behavior, focus rings, dark theme variables, buttons, forms, chat turns, receipts, drawer sections, artifact viewer, Notes, Memory, Activity, and continuity controls.

Verified current source:
- Theme tokens exist in `:root`: `--background`, `--surface`, `--surface-muted`, `--text`, `--muted`, `--border`, `--accent`, `--danger`, `--radius`.
- Dark-mode variables exist under `@media (prefers-color-scheme: dark)`.
- Four-region layout is controlled through `.workspace-grid`, `.supporting-panel`, `.conversation`, and `.work-panel`.
- Chat presentation is controlled through `.chat-transcript`, `.turn`, `.turn-user`, `.turn-model`, `.receipt-list`, `.receipt-item`, `.composer`, and `.chat-error`.
- Artifact/side panels are controlled through `.work-list-item`, `.export-controls`, `.feedback-form`, `.artifact-create-form`, `.artifact-content`, `.memory-card`, `.notes-card`, `.activity-event`, and related selectors.
- Responsive behavior currently starts at `@media (max-width: 900px)`.

### Locked HTML Boundary

`frontend/index.html` defines the application skeleton and behavior hooks. It contains:
- `.workspace-shell` and `.top-bar`;
- `data-app-root`;
- `data-new-conversation`;
- `data-context-form`;
- `data-workspace`;
- `data-drawer-toggle`;
- `data-section`;
- `data-section-toggle`;
- `data-section-content`;
- `data-artifact-create-form`;
- `data-chat-form`;
- `data-chat-input`;
- `data-chat-submit`;
- `data-work-detail`.

These are unsafe to change in this visual-only plan because JavaScript and tests depend on them.

### Locked JavaScript Boundary

The safe guide identifies the JavaScript modules as behavior-bearing. Do not edit:
- `frontend/app.mjs`
- `frontend/state.mjs`
- `frontend/api.mjs`
- `frontend/requests.mjs`
- `frontend/render.mjs`
- `frontend/workspace-layout.mjs`
- `frontend/chat-view.mjs`
- `frontend/work-view.mjs`
- `frontend/workspace-view.mjs`
- `frontend/notes-view.mjs`
- `frontend/memory-view.mjs`
- `frontend/chats-view.mjs`
- `frontend/activity-view.mjs`

Source confirms why: `chat-view.mjs` constructs receipt DOM, transcript turns, memory clarification buttons, continuity buttons, retry state, and submit behavior. `work-view.mjs` constructs artifact exports, artifact rendering, metadata forms, version forms, feedback controls, and download behavior. These are not paint-only surfaces.

### Locked Backend Boundary

Do not edit:
- `main.py`
- `schemas.py`
- `database.py`
- memory, notes, artifact, working-state, auth, responder, routing, or prompt files.

The safe guide explicitly excludes backend static paths, cache headers, routes, auth, API handlers, schemas, persistence, model prompts, routing, memory, notes, artifacts, and working state from visual-only work.

---

## Visual Target Interpretation

The reference image establishes the desired visual direction:

- dark app shell, not a light theme;
- near-black blue/green background with subtle panel separation;
- strong but restrained teal primary accent;
- amber secondary accents for user/status/artifact emphasis;
- thin borders and divider lines with low contrast;
- 8px-or-less radius language for panels and repeated cards;
- denser professional workspace layout;
- top bar with clearer app identity and prominent primary action;
- left drawer section rows that feel like navigation surfaces, not plain lists;
- chat surface with clearer turn hierarchy, model card treatment, vertical teal accent rail, readable receipt chips;
- composer that feels integrated and polished;
- right artifact drawer with stronger artifact card, metadata chips, preview tabs, code/markdown/table readability, and compact bottom controls.

This is a visual benchmark, not a source of new behavior. The final application does not need to pixel-copy the mockup, but it should meet its quality bar.

---

## Suspected Touched File

Expected touched file:
- `frontend/styles.css`

Expected unchanged files:
- `frontend/index.html`
- `frontend/*.mjs`
- `main.py`
- backend/application Python modules
- tests, unless a later approved visual-regression/static test pass is added

Reference image file:
- `agent-col-visual-target.jpeg`

---

## Pass 1: Theme Tokens And Global App Shell

**Goal:** Move the whole app toward the dark polished reference without touching structure.

**Safe selectors:**
- `:root`
- `@media (prefers-color-scheme: dark)`
- `body`
- `button`
- `input`
- `select`
- `textarea`
- `button:focus-visible`, `input:focus-visible`, `textarea:focus-visible`
- `.workspace-shell`

**Current source references:**
- `frontend/styles.css` defines root theme tokens and dark-mode variables.
- `frontend/styles.css` defines global control and focus styles.

**Conceptual CSS direction:**

```css
:root {
  color-scheme: dark;
  --background: #071014;
  --surface: #0d171d;
  --surface-muted: #101d24;
  --text: #eef7f4;
  --muted: #91a5a2;
  --border: #233740;
  --accent: #36d6c2;
  --accent-strong: #42e0ca;
  --accent-soft: rgba(54, 214, 194, 0.14);
  --amber: #f6b84a;
  --danger: #ff8c8c;
  --radius: 8px;
}
```

Preserve:
- no new theme toggle;
- no persisted theme setting;
- no JS changes;
- no text changes.

Manual target:
- App should read as a dark, focused workspace similar to the image.
- Borders must remain visible without becoming high-contrast grid lines.

---

## Pass 2: Top Bar Visual Treatment

**Goal:** Make the top bar match the visual hierarchy in the image: auth status left, Agent Col identity prominent, New Conversation as primary action.

**Safe selectors:**
- `.top-bar`
- `.top-bar > div`
- `.eyebrow`
- `h1`
- `.top-bar button`
- general `button` states if needed

**Current source anchor:**
- Top bar markup is fixed in `frontend/index.html`: auth label, `Agent Col`, `New conversation`.

**Conceptual CSS direction:**

```css
.top-bar {
  min-height: 4.75rem;
  padding: 1rem 1.25rem;
  background: linear-gradient(180deg, #0a141a, #081116);
  border-bottom: 1px solid var(--border);
}

.eyebrow {
  color: var(--muted);
  font-size: 0.875rem;
}

.eyebrow::before {
  content: "";
  inline-size: 0.65rem;
  block-size: 0.65rem;
  border-radius: 999px;
  background: var(--accent);
  display: inline-block;
  margin-inline-end: 0.5rem;
}

.top-bar h1 {
  font-size: 1.15rem;
  font-weight: 720;
}

.top-bar [data-new-conversation] {
  background: var(--accent);
  color: #03110f;
  border-color: transparent;
}
```

Preserve:
- `data-new-conversation`;
- button text and disabled behavior;
- auth behavior and Google sign-in status.

Manual target:
- New Conversation should be the clearest primary action.
- Auth status should look like a status indicator, not a form label.

---

## Pass 3: Left Drawer Density And Navigation Rows

**Goal:** Make the drawer section list feel like the reference: compact, scannable, with clear active/expanded affordances.

**Safe selectors:**
- `.supporting-panel`
- `.supporting-panel__body`
- `.drawer-heading`
- `.drawer-toggle`
- `.drawer-section`
- `.section-heading`
- `.section-heading h2`
- existing state selectors such as `[aria-expanded="true"]` if already present

**Current source anchor:**
- Left drawer sections are static `section.drawer-section` nodes with `data-section` and `data-section-toggle`.
- Do not change section labels or hook names.

**Conceptual CSS direction:**

```css
.supporting-panel {
  background: #0b151b;
  border-inline-end: 1px solid #21343d;
}

.drawer-section {
  border: 1px solid transparent;
  border-block-end: 1px solid var(--border);
  margin: 0;
  padding: 0.85rem 0.75rem;
}

.drawer-section:has([aria-expanded="true"]) {
  border-color: rgba(54, 214, 194, 0.35);
  background: var(--accent-soft);
}

.section-heading h2 {
  font-size: 0.98rem;
  font-weight: 650;
}
```

Risk note:
- `:has()` is modern browser CSS. If browser compatibility is a concern, avoid it and style only `.drawer-section` plus existing buttons. Do not add JS classes just to support active styling in this pass.

Preserve:
- Hide/Refresh actions;
- Expand semantics;
- `aria-expanded`;
- `data-section` values;
- collapsed/expanded behavior.

Manual target:
- Drawer sections should feel like polished navigation rows.
- The drawer should remain independently scrollable.

---

## Pass 4: Workspace Grid Proportions

**Goal:** Rebalance the four regions toward the reference image without changing layout state logic.

**Safe selectors:**
- `.workspace-grid`
- `.workspace-grid--left-collapsed`
- `.workspace-grid--right-collapsed`
- `.workspace-grid--artifacts-expanded`
- `.supporting-panel`, `.conversation`, `.work-panel`

**Current source anchor:**
- Grid columns currently use left `minmax(16rem, 22rem)`, chat `1fr`, right `minmax(18rem, 26rem)`.

**Conceptual CSS direction:**

```css
.workspace-grid {
  grid-template-columns:
    0
    minmax(17rem, 22rem)
    minmax(34rem, 1fr)
    minmax(22rem, 28rem)
    0;
}

.supporting-panel,
.conversation,
.work-panel {
  padding: 1.25rem;
}
```

Preserve:
- grid-template areas;
- collapse classes;
- artifact expanded mode;
- restore buttons;
- mobile breakpoint behavior.

Manual target:
- On wide desktop, chat remains primary but artifact viewer has enough width for reading.
- On narrower screens, no controls clip or become unreachable.

---

## Pass 5: Chat Transcript And Model Response Styling

**Goal:** Match the reference's chat hierarchy: user turn compact, model turns carded, Agent Col responses visually anchored with teal accents and readable receipts.

**Safe selectors:**
- `.conversation`
- `.conversation-intro`
- `.chat-transcript`
- `.turn`
- `.turn-user`
- `.turn-model`
- `.turn-receipts`
- `.receipt-list`
- `.receipt-item`

**Current source anchor:**
- `chat-view.mjs` renders each turn as `article.turn`, `p.turn-user`, `p.turn-model`, then `.turn-receipts`.
- It sets text via safe text helpers, so CSS can style only the existing rendered text.

**Conceptual CSS direction:**

```css
.chat-transcript {
  gap: 1rem;
  padding-block: 0.75rem;
}

.turn {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(12, 24, 31, 0.72);
  padding: 1rem;
}

.turn-model {
  border-inline-start: 3px solid var(--accent);
  padding-inline-start: 0.9rem;
  color: var(--text);
  line-height: 1.55;
}

.turn-user {
  color: var(--text);
  background: transparent;
}

.receipt-item {
  background: rgba(54, 214, 194, 0.08);
  border-color: rgba(54, 214, 194, 0.25);
  color: #bceee6;
}
```

Preserve:
- actual model response text;
- receipt construction;
- retry behavior;
- memory clarification rendering;
- continuity choice behavior.

Manual target:
- Agent Col responses should feel deliberately presented, not raw paragraphs.
- Receipt chips should be readable and compact.

---

## Pass 6: Composer Polish

**Goal:** Make the message composer feel integrated with the dark workspace and clearly actionable.

**Safe selectors:**
- `.conversation-footer`
- `.composer`
- `.composer label`
- `.composer textarea`
- `.composer-actions`
- `[data-character-count]`
- `[data-chat-submit]`

**Current source anchor:**
- Composer markup and submit behavior live in `frontend/index.html` and `chat-view.mjs`; do not edit those.

**Conceptual CSS direction:**

```css
.composer {
  padding-block-start: 1rem;
  border-top: 1px solid var(--border);
}

.composer textarea {
  background: #0b151b;
  border-color: #2b4650;
  min-height: 5.5rem;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
}

.composer-actions [data-chat-submit] {
  background: linear-gradient(180deg, #40d9c8, #2ba997);
  color: #03110f;
  border-color: transparent;
}
```

Preserve:
- textarea `name`, `id`, `maxlength`, `required`, `rows`;
- submit button text and behavior;
- character counter logic.

Manual target:
- Composer should remain easy to find and use.
- Text must not clip at 10,000 counter or button labels.

---

## Pass 7: Artifact Viewer And Content Readability

**Goal:** Make the right drawer visually closer to the reference artifact card and readable markdown/code panel.

**Safe selectors:**
- `.work-panel`
- `.work-panel__body`
- `.work-list-item`
- `.work-heading`
- `.artifact-content`
- `.export-controls`
- `.feedback-form`
- `.feedback-event`
- `.button-link`
- `.work-panel h3`, `.work-panel h4`, `.work-panel p`, `.work-panel li`

**Current source anchor:**
- `work-view.mjs` generates artifact exports, artifact content, metadata, feedback forms, and buttons. Do not edit it in this visual pass.
- `.artifact-content` already exists and is safe to style.

**Conceptual CSS direction:**

```css
.work-panel {
  background: #0a141a;
  border-inline-start: 1px solid #21343d;
}

.work-list-item,
.export-controls,
.feedback-form,
.artifact-content {
  background: #101c23;
  border: 1px solid #263c45;
  border-radius: var(--radius);
}

.artifact-content {
  color: #e8f2ef;
  line-height: 1.55;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
```

Preserve:
- artifact selection;
- artifact content;
- export/download/print behavior;
- artifact edit/save/version/rename behavior;
- feedback decisions.

Manual target:
- Markdown/code/data artifacts should be more readable.
- Long content should wrap or scroll correctly without changing stored content.

---

## Pass 8: Notes, Memory, Chats, Activity, Continuity, Empty/Error States

**Goal:** Make secondary panels and state surfaces match the polished visual system.

**Safe selectors:**
- `.memory-card`
- `.memory-event`
- `.notes-card`
- `.notes-event`
- `.activity-event`
- `.memory-actions`
- `.notes-actions`
- `.continuity-choices`
- `.continuity-choice`
- `.memory-clarification-choices`
- `.memory-clarification-choice`
- `.form-error`
- `.muted`

**Current source anchor:**
- These cards are generated by JS modules, but the classes already exist for CSS styling.
- Do not change note/memory lifecycle behavior.

**Conceptual CSS direction:**

```css
.memory-card,
.memory-event,
.notes-card,
.notes-event,
.activity-event {
  background: #101c23;
  border-color: #263c45;
}

.form-error {
  color: #ff9b9b;
  background: rgba(255, 140, 140, 0.08);
  border: 1px solid rgba(255, 140, 140, 0.25);
  border-radius: var(--radius);
  padding: 0.5rem 0.65rem;
}

.continuity-choice,
.memory-clarification-choice {
  background: rgba(246, 184, 74, 0.1);
  border-color: rgba(246, 184, 74, 0.35);
}
```

Preserve:
- approve/reject/revoke/delete/archive/restore actions;
- correction forms;
- continuity selection;
- memory clarification selection;
- activity data.

Manual target:
- Pending/choice surfaces should be visible without implying state changes not present in data.

---

## Pass 9: Responsive And Accessibility Verification

**Goal:** Keep the polished layout usable across viewport sizes and input methods.

**Safe selectors:**
- existing `@media (max-width: 900px)`
- focus-visible selectors
- scroll containers
- line-height and overflow rules

**Conceptual CSS direction:**

```css
@media (max-width: 900px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .top-bar {
    flex-wrap: wrap;
  }

  .conversation,
  .supporting-panel,
  .work-panel {
    padding: 1rem;
  }
}
```

Preserve:
- existing mobile collapse behavior;
- hidden states;
- drawer restore behavior.

Manual target:
- No overlap, clipped buttons, inaccessible composer, or hidden scroll traps.
- Keyboard focus must remain visible.
- Text must remain readable in left drawer, chat, and artifact viewer.

---

## Explicit Unsafe Modification Points

Do not touch in the visual-only implementation:

- `frontend/app.mjs`: startup, auth/session flow, workspace loading, chat submission, API orchestration.
- `frontend/state.mjs`: state transitions, selected records, pending turn/failure state, memory/note/artifact state.
- `frontend/api.mjs`: paths, methods, headers, response parsing, error normalization.
- `frontend/requests.mjs`: idempotency keys, payload construction, request validation.
- `frontend/render.mjs`: DOM helpers, labels, value formatting.
- `frontend/workspace-layout.mjs`: drawer mode state and class toggles.
- `frontend/chat-view.mjs`: transcript construction, receipt rendering, retry, clarification, continuity behavior.
- `frontend/work-view.mjs`: artifact export/download/print/edit/version/feedback behavior.
- `frontend/notes-view.mjs`: note lifecycle rendering and controls.
- `frontend/memory-view.mjs`: memory lifecycle rendering and controls.
- `frontend/chats-view.mjs`: chat-session list/detail selection.
- `frontend/activity-view.mjs`: activity rendering.
- `frontend/index.html`: `data-*`, `id`, `name`, `type`, `required`, `maxlength`, form structure, action text, ARIA, script/style paths.
- Backend Python files: all routes, schemas, persistence, prompts, model behavior, memory, notes, working state, artifact behavior.

---

## Verification Checklist For The Human Implementer

Run after each CSS pass:

```bash
git diff --check
```

If any HTML or JS is touched, stop and reclassify the work as behavior-affecting, then run:

```bash
node --test tests/frontend/*.test.mjs
```

Manual visual checks:

1. Open `/workspace`.
2. Confirm the target reference image is available at `agent-col-visual-target.jpeg`.
3. Compare top bar, left drawer, chat surface, composer, and artifact viewer against the reference image.
4. Toggle left drawer Hide/Show.
5. Toggle Artifacts Viewer Hide/Show and Expand/Normal modes.
6. Expand/collapse Workspace, Artifacts, Notes, Memory, and Chats sections.
7. Send a normal chat request.
8. Confirm receipts render and retry remains available after a failed turn.
9. Select an artifact and verify preview/detail readability.
10. Exercise artifact edit/save/export/print controls without behavior changes.
11. Open Notes, Memory, Chats, and Activity sections.
12. Confirm memory clarification and continuity choices remain selectable when present.
13. Tab through controls and confirm focus is visible.
14. Check narrow and wide viewport layouts.
15. Confirm no hidden working state, private prompt, or internal JSON appears.
16. Confirm browser network behavior still targets existing same-origin routes only.

---

## Pass Acceptance Criteria

The pass is acceptable only when:

- `frontend/styles.css` is the only behavior-affecting source file changed.
- The app visually approaches `agent-col-visual-target.jpeg`.
- The four persistent regions remain intact.
- Existing controls remain present and usable.
- Existing frontend tests pass if HTML/JS changed.
- Manual visual verification confirms no overlap, clipping, unreachable controls, hidden composer, broken drawer behavior, or misleading state styling.
- The user accepts the visual result before checkpointing.
