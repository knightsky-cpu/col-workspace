# Frontend Visual Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Agent Col browser workspace so its finished visual quality explicitly aligns with the root-level reference image at [`agent-col-visual-target.jpeg`](/Users/wifiknight/col-workspace/agent-col-visual-target.jpeg), while preserving current application behavior exactly.

**Architecture:** This is a visual-only frontend pass. The primary implementation surface is `frontend/styles.css`; the current four-region workspace structure remains unchanged: top bar, left drawer, chat surface, and right artifact drawer. HTML, JavaScript, backend routes, prompts, schemas, persistence, auth, memory, notes, artifacts, and working-state behavior are locked unless a later separately approved behavior pass changes that boundary.

**Tech Stack:** Static HTML, CSS, vanilla JavaScript modules, FastAPI static serving, Node frontend tests, Python static-route tests, browser/manual visual verification.

**Spec:** `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md`, [`agent-col-visual-target.jpeg`](/Users/wifiknight/col-workspace/agent-col-visual-target.jpeg), current `frontend/index.html`, current `frontend/styles.css`, current frontend static tests, and the official documentation references below.

## Official Documentation Evidence

- MDN CSS custom properties: `:root` tokens and `var()` reuse are appropriate for a centralized visual system.
  - https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Cascading_variables/Using_custom_properties
- MDN `color-scheme` and `prefers-color-scheme`: declaring supported schemes does not replace explicit color tokens; `@media (prefers-color-scheme: dark)` must stay coherent with the target palette.
  - https://developer.mozilla.org/en-US/docs/Web/CSS/color-scheme
  - https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme
- MDN CSS Grid `minmax()`: grid minimums can force overflow when their combined minimum track sizes exceed available viewport width.
  - https://developer.mozilla.org/en-US/docs/Web/CSS/minmax
- MDN `:has()`: useful for parent-state styling, but should be treated as progressive enhancement in this plan.
  - https://developer.mozilla.org/en-US/docs/Web/CSS/:has
- MDN `overflow-wrap`, `scrollbar-gutter`, `:focus-visible`, and `prefers-reduced-motion`: support safe wrapping, stable scrollbars, visible keyboard focus, and reduced-motion handling.
  - https://developer.mozilla.org/en-US/docs/Web/CSS/overflow-wrap
  - https://developer.mozilla.org/en-US/docs/Web/CSS/scrollbar-gutter
  - https://developer.mozilla.org/en-US/docs/Web/CSS/:focus-visible
  - https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion
- WCAG 2.2: preserve contrast, reflow, visible focus, and target sizing while restyling.
  - https://www.w3.org/TR/WCAG22/
- Google Identity Services: do not custom-restyle the Google-rendered sign-in button internals; only style the surrounding Agent Col container.
  - https://developers.google.com/identity/gsi/web/guides/display-button
  - https://developers.google.com/identity/branding-guidelines
- FastAPI and Starlette static files: CSS is served as a static frontend asset; this pass does not require backend static-serving changes.
  - https://fastapi.tiangolo.com/tutorial/static-files/
  - https://www.starlette.io/staticfiles/

## Corrections From Documentation Review

- The earlier draft proposed making `:root` dark but did not explicitly synchronize the existing dark-mode media block. The implementation must update both `:root` and `@media (prefers-color-scheme: dark)` in `frontend/styles.css`.
- The earlier draft's grid concept used desktop minimums that could over-constrain laptop and tablet-width viewports. The revised grid snippets use lower minimums and require viewport checks at 1440, 1280, 1024, 900, and 390 pixels.
- `:has([aria-expanded="true"])` is allowed only as CSS progressive enhancement behind `@supports selector(:has(*))`; do not add JavaScript classes or HTML hooks to support it.
- Generic app button styling must not target the Google-rendered button under `[data-google-button]`.
- If transitions or animations are added, include a `prefers-reduced-motion` guard. If no motion is added, the guard may be omitted.
- Artifact preview styling must not imply Markdown parsing, syntax highlighting, preview tabs, or content transformation. Current `.artifact-content` is raw preserved text.

## Global Constraints

- Use [`agent-col-visual-target.jpeg`](/Users/wifiknight/col-workspace/agent-col-visual-target.jpeg) as the explicit visual benchmark.
- Default implementation surface is `frontend/styles.css`.
- Do not change backend routes, request payloads, schemas, prompts, auth, persistence, memory, notes, artifacts, working state, or model behavior.
- Do not change JavaScript state, event handlers, request builders, render logic, export behavior, retry behavior, or hidden/disabled/expanded semantics.
- Do not change `frontend/index.html` unless a later approved pass allows purely presentational classes.
- Do not expose hidden working state or private context.
- Preserve all existing user actions, routes, response data, records, receipts, and lifecycle behavior.
- CSS-only visual work requires focused automated checks plus manual visual acceptance; automated tests do not replace visual review.

## Source-Backed Boundary Findings

### Safe Primary File

`frontend/styles.css` is the primary safe file because the safe visual guide explicitly assigns it responsibility for colors, spacing, typography, borders, panel layout, scroll behavior, focus rings, dark-theme variables, buttons, forms, chat turns, receipts, drawer sections, artifact viewer, Notes, Memory, Activity, and continuity controls.

Verified current source:

```css
/* frontend/styles.css */
:root {
  color-scheme: light dark;
  --background: #f7f8f8;
  --surface: #ffffff;
  --surface-muted: #eef1f1;
  --text: #1d2525;
  --muted: #617070;
  --border: #cbd5d5;
  --accent: #235c67;
  --danger: #9d2c2c;
  --radius: 8px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --background: #111616;
    --surface: #182020;
    --surface-muted: #202b2b;
    --text: #edf2f2;
    --muted: #a6b5b5;
    --border: #334343;
    --accent: #7db7c2;
    --danger: #ff8c8c;
  }
}
```

Current source also defines:

- four-region layout through `.workspace-grid`, `.supporting-panel`, `.conversation`, and `.work-panel`;
- chat presentation through `.chat-transcript`, `.turn`, `.turn-user`, `.turn-model`, `.receipt-list`, `.receipt-item`, `.composer`, and `.chat-error`;
- artifact and side-panel presentation through `.work-list-item`, `.export-controls`, `.feedback-form`, `.artifact-create-form`, `.artifact-content`, `.memory-card`, `.notes-card`, `.activity-event`, and related selectors;
- responsive behavior at `@media (max-width: 900px)`;
- print behavior that depends on `[data-work-detail]`.

### Locked HTML Boundary

`frontend/index.html` defines the application skeleton and behavior hooks. Do not alter these anchors in this visual-only pass:

```html
<!-- frontend/index.html -->
<div class="workspace-shell" data-app-root>
  <header class="top-bar" aria-label="Workspace">
    <p class="eyebrow" data-auth-mode-label>Loading authentication</p>
    <button type="button" data-new-conversation disabled>
      New conversation
    </button>
  </header>

  <div class="google-signin" data-google-signin hidden>
    <div data-google-button></div>
  </div>

  <div class="workspace-grid" data-workspace hidden>
    ...
    <div class="chat-transcript" data-chat-transcript aria-live="polite"></div>
    ...
    <div class="work-panel__body" data-work-detail></div>
  </div>
</div>
```

Locked HTML includes:

- all `data-*` hooks;
- `id`, `name`, `type`, `required`, `maxlength`, and `rows`;
- `aria-*` attributes;
- select options;
- script and stylesheet paths;
- action-linked visible text.

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

Source confirms the risk: `frontend/app.mjs` mutates layout classes and `aria-expanded`; `frontend/chat-view.mjs` constructs transcript turns, receipts, retry controls, memory clarification controls, and continuity controls; `frontend/work-view.mjs` constructs artifact detail, metadata, export, edit, save, rename, and feedback surfaces.

### Locked Backend Boundary

Do not edit:

- `main.py`
- `schemas.py`
- `database.py`
- memory, notes, artifact, working-state, auth, responder, routing, or prompt files.

The safe guide explicitly excludes backend static paths, cache headers, routes, auth, API handlers, schemas, persistence, model prompts, routing, memory, notes, artifacts, and working state from visual-only work.

## Visual Target Interpretation

The reference image establishes the required finished quality bar:

- dark app shell, not a light theme;
- near-black blue/green background with subtle panel separation;
- strong but restrained teal primary accent;
- amber secondary accents for user/status/artifact emphasis;
- thin borders and divider lines with low contrast;
- 8px-or-less radius language for panels and repeated cards;
- dense professional workspace layout;
- top bar with clearer app identity and prominent primary action;
- left drawer section rows that feel like navigation surfaces, not plain lists;
- chat surface with clearer turn hierarchy, model card treatment, vertical teal accent rail, and readable receipt chips;
- composer that feels integrated and polished;
- right artifact drawer with stronger artifact card treatment, metadata readability, and compact controls.

This is a visual benchmark, not a source of new behavior. The final application does not need to pixel-copy the mockup, but it should visibly move toward this quality bar.

## Suspected Touched Files

Expected touched file:

- `frontend/styles.css`

Expected unchanged files:

- `frontend/index.html`
- `frontend/*.mjs`
- `main.py`
- backend/application Python modules
- tests, unless a later approved visual-regression/static test pass is added

Reference image file:

- [`agent-col-visual-target.jpeg`](/Users/wifiknight/col-workspace/agent-col-visual-target.jpeg)

## Implementation Tasks

### Pass 1: Theme Tokens And Global App Shell

**Goal:** Move the app toward the dark polished reference image without changing structure.

**Safe selectors:**

- `:root`
- `@media (prefers-color-scheme: dark)`
- `body`
- `button`
- `input`
- `select`
- `textarea`
- `button:focus-visible`, `input:focus-visible`, `select:focus-visible`, `textarea:focus-visible`, `main:focus-visible`
- `.workspace-shell`
- `.context-gate`
- `.google-signin`, but not `[data-google-button]` internals

**Conceptual CSS direction:**

```css
:root {
  color-scheme: dark;
  --background: #071014;
  --surface: #0b151b;
  --surface-muted: #101c23;
  --surface-raised: #14232b;
  --text: #edf7f4;
  --muted: #94a8a5;
  --border: #263a43;
  --border-soft: rgba(148, 168, 165, 0.18);
  --accent: #36d6c2;
  --accent-strong: #45e3cf;
  --accent-soft: rgba(54, 214, 194, 0.13);
  --amber: #f3b64b;
  --amber-soft: rgba(243, 182, 75, 0.14);
  --danger: #ff9b9b;
  --radius: 8px;
}

@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --background: #071014;
    --surface: #0b151b;
    --surface-muted: #101c23;
    --surface-raised: #14232b;
    --text: #edf7f4;
    --muted: #94a8a5;
    --border: #263a43;
    --border-soft: rgba(148, 168, 165, 0.18);
    --accent: #36d6c2;
    --accent-strong: #45e3cf;
    --accent-soft: rgba(54, 214, 194, 0.13);
    --amber: #f3b64b;
    --amber-soft: rgba(243, 182, 75, 0.14);
    --danger: #ff9b9b;
  }
}

body {
  background: var(--background);
  color: var(--text);
}

.workspace-shell {
  background: var(--background);
}
```

**Preserve:**

- no new theme toggle;
- no persisted theme setting;
- no JavaScript changes;
- no text changes;
- no Google Identity button customization.

**Manual target:**

- App should read as a dark, focused workspace similar to the target image.
- Borders must remain visible without becoming high-contrast grid lines.

### Pass 2: Top Bar Visual Treatment

**Goal:** Make the top bar match the visual hierarchy in the reference image: auth status left, Agent Col identity prominent, New Conversation as primary action.

**Current source anchor:**

```html
<header class="top-bar" aria-label="Workspace">
  <div>
    <p class="eyebrow" data-auth-mode-label>Loading authentication</p>
    <h1>Agent Col</h1>
  </div>
  <button type="button" data-new-conversation disabled>
    New conversation
  </button>
</header>
```

**Safe selectors:**

- `.top-bar`
- `.top-bar > div`
- `.eyebrow`
- `.eyebrow::before`
- `h1`
- `.top-bar [data-new-conversation]`

**Conceptual CSS direction:**

```css
.top-bar {
  min-height: 4.5rem;
  padding: 0.95rem 1.25rem;
  background: linear-gradient(180deg, #0b151b 0%, #081116 100%);
  border-bottom: 1px solid var(--border);
}

.eyebrow {
  color: var(--muted);
  font-size: 0.84rem;
  line-height: 1.2;
}

.eyebrow::before {
  content: "";
  display: inline-block;
  inline-size: 0.65rem;
  block-size: 0.65rem;
  margin-inline-end: 0.5rem;
  border-radius: 999px;
  background: var(--accent);
}

.top-bar h1 {
  font-size: 1.15rem;
  font-weight: 720;
}

.top-bar [data-new-conversation] {
  background: linear-gradient(180deg, var(--accent-strong), #2aa998);
  color: #03110f;
  border-color: transparent;
}
```

**Preserve:**

- `data-new-conversation`;
- disabled behavior;
- auth status text source;
- Google sign-in behavior.

**Manual target:**

- New Conversation should be the clearest primary action.
- Auth status should look like a status indicator, not a form label.

### Pass 3: Workspace Grid Proportions

**Goal:** Rebalance the four persistent regions toward the target image without changing layout state logic.

**Current source anchor:**

```css
.workspace-grid {
  grid-template-columns: 0 minmax(16rem, 22rem) minmax(20rem, 1fr) minmax(18rem, 26rem) 0;
}
```

**Safe selectors:**

- `.workspace-grid`
- `.workspace-grid--left-collapsed`
- `.workspace-grid--right-collapsed`
- `.workspace-grid--left-collapsed.workspace-grid--right-collapsed`
- `.workspace-grid--artifacts-expanded`
- `.workspace-grid--left-collapsed.workspace-grid--artifacts-expanded`
- `.supporting-panel`
- `.conversation`
- `.work-panel`

**Conceptual CSS direction:**

```css
.workspace-grid {
  grid-template-columns:
    0
    minmax(14rem, 20rem)
    minmax(24rem, 1fr)
    minmax(16rem, 26rem)
    0;
}

.workspace-grid--left-collapsed {
  grid-template-columns: 3rem 0 minmax(24rem, 1fr) minmax(16rem, 26rem) 0;
}

.workspace-grid--right-collapsed {
  grid-template-columns: 0 minmax(14rem, 20rem) minmax(24rem, 1fr) 0 3rem;
}

.workspace-grid--left-collapsed.workspace-grid--right-collapsed {
  grid-template-columns: 3rem 0 minmax(24rem, 1fr) 0 3rem;
}

.workspace-grid--artifacts-expanded {
  grid-template-columns: 0 minmax(14rem, 18rem) minmax(20rem, 1fr) minmax(30rem, 78vw) 0;
}

.supporting-panel,
.conversation,
.work-panel {
  padding: 1.25rem;
}
```

**Preserve:**

- `grid-template-areas`;
- collapse classes and semantics;
- artifact expanded mode;
- restore buttons;
- independent scroll ownership;
- mobile behavior unless separately verified.

**Manual target:**

- On wide desktop, chat remains primary and artifact viewer remains readable.
- On narrower screens, no controls clip or become unreachable.

### Pass 4: Left Drawer Density And Navigation Rows

**Goal:** Make drawer sections feel like polished navigation rows while preserving existing Expand/Hide behavior.

**Current source anchor:**

```html
<section class="drawer-section" aria-labelledby="workspace-title" data-section="workspace">
  <div class="section-heading">
    <h2 id="workspace-title">Workspace</h2>
    <button type="button" class="drawer-toggle" data-section-toggle="workspace" aria-expanded="false">
      Expand
    </button>
  </div>
</section>
```

**Safe selectors:**

- `.supporting-panel`
- `.supporting-panel__body`
- `.drawer-heading`
- `.drawer-toggle`
- `.drawer-section`
- `.section-heading`
- `.section-heading h2`
- optional `@supports selector(:has(*))` state selectors

**Conceptual CSS direction:**

```css
.supporting-panel {
  background: #0b151b;
  border-inline-end: 1px solid var(--border);
}

.drawer-section {
  margin: 0 0 0.55rem;
  padding: 0.75rem;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.015);
}

@supports selector(:has(*)) {
  .drawer-section:has([aria-expanded="true"]) {
    border-color: rgba(54, 214, 194, 0.38);
    background: var(--accent-soft);
  }
}

.section-heading h2 {
  font-size: 0.98rem;
  font-weight: 650;
}
```

**Preserve:**

- Hide/Refresh actions;
- Expand semantics;
- `aria-expanded`;
- `data-section` values;
- collapsed/expanded behavior.

**Manual target:**

- Drawer sections should visually match the target image's structured navigation.
- The drawer should remain independently scrollable.

### Pass 5: Chat Transcript And Model Response Styling

**Goal:** Match the reference's chat hierarchy: user turns compact, model turns deliberate and readable, Agent Col responses anchored with a teal accent rail, receipts compact.

**Current source anchors:**

```html
<div class="chat-transcript" data-chat-transcript aria-live="polite"></div>
```

```css
.turn-user,
.turn-model {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
```

`frontend/chat-view.mjs` renders each turn as `article.turn`, `p.turn-user`, `p.turn-model`, then receipts. It sets text through safe DOM text APIs. Do not edit this behavior in the visual pass.

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

**Conceptual CSS direction:**

```css
.conversation {
  background:
    radial-gradient(circle at 50% 0%, rgba(54, 214, 194, 0.05), transparent 30%),
    var(--background);
}

.chat-transcript {
  gap: 1rem;
  padding-block: 0.75rem;
}

.turn {
  border: 1px solid var(--border-soft);
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
}

.receipt-item {
  background: rgba(54, 214, 194, 0.08);
  border-color: rgba(54, 214, 194, 0.25);
  color: #bceee6;
}
```

**Preserve:**

- actual model response text;
- `textContent` rendering and HTML-injection safety;
- receipt construction;
- retry behavior;
- memory clarification rendering;
- continuity choice behavior;
- `aria-live="polite"`.

**Manual target:**

- Agent Col responses should feel deliberately presented, not raw paragraphs.
- Receipt chips should be readable and compact.
- The chat region should look materially closer to the target screenshot while behaving identically.

### Pass 6: Composer Polish

**Goal:** Make the message composer feel integrated with the dark workspace and clearly actionable.

**Current source anchor:**

```html
<form class="composer" data-chat-form>
  <label for="chat-message">Message</label>
  <textarea
    id="chat-message"
    name="message"
    data-chat-input
    rows="4"
    maxlength="10000"
    required
  ></textarea>
  <div class="composer-actions">
    <span data-character-count>0 / 10000</span>
    <button type="submit" data-chat-submit>Send</button>
  </div>
</form>
```

**Safe selectors:**

- `.conversation-footer`
- `.composer`
- `.composer label`
- `.composer textarea`
- `.composer-actions`
- `[data-character-count]`
- `[data-chat-submit]`

**Conceptual CSS direction:**

```css
.composer {
  padding-block-start: 1rem;
  border-top: 1px solid var(--border);
  background: var(--background);
}

.composer textarea {
  min-height: 5.5rem;
  background: #0b151b;
  border-color: #2b4650;
  color: var(--text);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.02);
}

.composer-actions [data-chat-submit] {
  min-height: 2.5rem;
  background: linear-gradient(180deg, var(--accent-strong), #2aa998);
  color: #03110f;
  border-color: transparent;
}
```

**Preserve:**

- textarea `name`, `id`, `maxlength`, `required`, `rows`;
- submit button text and behavior;
- character counter logic.

**Manual target:**

- Composer should remain easy to find and use.
- Text must not clip at the character counter or send button.

### Pass 7: Artifact Viewer And Content Readability

**Goal:** Make the right drawer visually closer to the target image's artifact panel while preserving raw content, artifact lifecycle, and export behavior.

**Current source anchor:**

```css
.artifact-content {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.75rem;
  white-space: pre-wrap;
}
```

`frontend/work-view.mjs` currently applies `artifact-content contain-text` to the content node. Do not edit that renderer in this pass.

**Safe selectors:**

- `.work-panel`
- `.work-panel__body`
- `.work-list-item`
- `.work-heading`
- `.artifact-content`
- `.export-controls`
- `.feedback-form`
- `.feedback-event`
- `.artifact-create-form`
- `.button-link`
- `.work-panel h3`, `.work-panel h4`, `.work-panel p`, `.work-panel li`

**Conceptual CSS direction:**

```css
.work-panel {
  background: #0a141a;
  border-inline-start: 1px solid var(--border);
}

.work-list-item,
.export-controls,
.feedback-form,
.artifact-create-form,
.artifact-content {
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.artifact-content {
  color: var(--text);
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
```

**Preserve:**

- artifact selection;
- artifact content;
- export/download/print behavior;
- artifact edit/save/version/rename behavior;
- feedback decisions.

**Do not add in this pass:**

- Markdown parsing;
- syntax highlighting;
- new tabs;
- content transformation;
- truncation;
- schema or export changes.

**Manual target:**

- Markdown/code/data artifacts should be more readable.
- Long content should wrap or scroll correctly without changing stored content.

### Pass 8: Notes, Memory, Chats, Activity, Continuity, Empty/Error States

**Goal:** Make secondary panels and state surfaces match the polished visual system.

**Current source anchors:**

- `.memory-card`, `.memory-event`, `.notes-card`, `.notes-event`, and `.activity-event` are existing CSS selectors.
- `.continuity-choices`, `.continuity-choice`, `.memory-clarification-choices`, and `.memory-clarification-choice` are existing CSS selectors.
- `.form-error` and `.muted` are existing CSS selectors.

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

**Conceptual CSS direction:**

```css
.memory-card,
.memory-event,
.notes-card,
.notes-event,
.activity-event {
  background: var(--surface-muted);
  border-color: var(--border);
}

.form-error {
  color: var(--danger);
  background: rgba(255, 155, 155, 0.08);
  border: 1px solid rgba(255, 155, 155, 0.25);
  border-radius: var(--radius);
  padding: 0.5rem 0.65rem;
}

.continuity-choice,
.memory-clarification-choice {
  background: var(--amber-soft);
  border-color: rgba(243, 182, 75, 0.35);
}
```

**Preserve:**

- approve/reject/revoke/delete/archive/restore actions;
- correction forms;
- continuity selection;
- memory clarification selection;
- activity data.

**Manual target:**

- Pending and choice surfaces should be visible without implying state changes not present in data.

### Pass 9: Responsive, Focus, Motion, And Accessibility Verification

**Goal:** Keep the polished layout usable across viewport sizes, keyboard navigation, and user motion preferences.

**Safe selectors:**

- existing `@media (max-width: 900px)`
- focus-visible selectors
- scroll containers
- line-height and overflow rules
- optional `@media (prefers-reduced-motion: reduce)` if transitions or animations are introduced

**Conceptual CSS direction:**

```css
button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
main:focus-visible {
  outline: 3px solid var(--accent-strong);
  outline-offset: 2px;
}

@media (max-width: 900px) {
  .workspace-grid {
    grid-template-columns: 1fr;
    overflow: auto;
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

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

Only include the reduced-motion block if the implementation adds transitions, animations, or smooth scrolling.

**Preserve:**

- existing mobile collapse behavior;
- hidden states;
- drawer restore behavior;
- independent scroll ownership;
- visible focus.

**Manual target:**

- No overlap, clipped buttons, inaccessible composer, or hidden scroll traps.
- Keyboard focus must remain visible.
- Contrast must remain readable against the dark target palette.

## Focused Automated Verification

Run after implementation:

```bash
git diff --check
node --test tests/frontend/workspace-static.test.mjs
node --test tests/frontend/chat-view.test.mjs
pytest tests/test_workspace_static.py
```

Why these checks:

- `workspace-static.test.mjs` protects critical HTML/style hooks, Google auth boundaries, print stylesheet expectations, Notes, Memory, and continuity anchors.
- `chat-view.test.mjs` protects transcript text safety and receipt rendering behavior while CSS changes the appearance.
- `tests/test_workspace_static.py` verifies `/workspace`, static CSS/JS serving, cache headers, layout CSS invariants, independent scroll ownership, and static route expectations.
- `git diff --check` catches whitespace and patch hygiene issues.

Do not run the full suite by default for this CSS-only pass unless focused verification reveals a broader regression or the implementation unexpectedly touches shared behavior.

## Manual Visual And Runtime Verification Targets

1. Open `/workspace` and compare the whole application against [`agent-col-visual-target.jpeg`](/Users/wifiknight/col-workspace/agent-col-visual-target.jpeg).
2. Verify the four-region structure remains intact: top bar, left drawer, chat surface, right artifact drawer.
3. Verify the target-image qualities are visible: dark shell, teal primary accent, amber secondary accents, subtle borders, dense professional layout, polished drawer rows, model response rail, readable receipts, integrated composer, and clearer artifact panel.
4. Verify drawer Hide/Show, section Expand/Collapse, and artifact viewer Expand/Hide still work.
5. Verify the Google sign-in screen still uses the official Google-rendered sign-in button and that only the surrounding Agent Col container is restyled.
6. Verify chat submission, retry, receipts, memory clarification choices, continuity choices, notes, memory, and artifact viewing still behave unchanged.
7. Verify no text or controls clip at 1440, 1280, 1024, 900, and 390 pixel widths.
8. Verify keyboard focus is visible on buttons, form fields, drawer controls, composer, and artifact controls.
9. Verify scroll ownership remains intact: left drawer, chat transcript, and right drawer scroll independently.
10. Verify artifact print/export behavior remains unchanged, including the `[data-work-detail]` print surface.

## Stop Conditions

Stop and revise the plan before implementation continues if:

- any required visual change cannot be done in `frontend/styles.css`;
- implementation appears to require changing `frontend/index.html`, JavaScript, backend routes, prompts, schemas, persistence, auth, memory, notes, artifacts, or working state;
- CSS changes break existing static tests;
- the Google sign-in button internals would need custom styling;
- viewport testing reveals inaccessible controls or unavoidable two-dimensional scrolling;
- visual work starts changing response contents, artifact contents, receipt labels, or lifecycle behavior.

## Completion Condition

This plan is complete only when the application visually aligns with [`agent-col-visual-target.jpeg`](/Users/wifiknight/col-workspace/agent-col-visual-target.jpeg) while preserving all existing behavior verified by focused automated checks and user manual acceptance.
