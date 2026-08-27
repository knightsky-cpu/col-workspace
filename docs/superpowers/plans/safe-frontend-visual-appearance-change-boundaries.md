# Safe Frontend Visual Appearance Change Boundaries

## Purpose

This document defines the safe boundary for user-facing frontend appearance work in Agent Col.

The intent is to allow visual polish without changing application behavior, response reliability, routing, request payloads, persistence, authentication, artifact behavior, Notes, Memory, or internal working-state behavior.

For this guide, a safe visual change means:

- the same user actions are available;
- the same requests are sent to the same backend routes;
- the same backend responses are rendered from the same data;
- the same hidden, disabled, selected, and expanded states still mean the same thing;
- the same artifacts, notes, memory records, chat sessions, and working-state data are created, updated, read, exported, or hidden exactly as before.

CSS-only changes are the default safe path. HTML and JavaScript changes are not visual-only unless they are explicitly limited as described below.

## Source-Backed Frontend Surface Map

### Primary Safe Visual Surface

- `frontend/styles.css`
  - Contains the visual system for colors, spacing, typography, borders, panel layout, scroll behavior, focus rings, dark theme variables, buttons, forms, chat turns, receipts, drawer sections, artifact viewer, Notes, Memory, activity, and continuity controls.
  - This is the preferred file for appearance-only work.

### Structure With Behavior Hooks

- `frontend/index.html`
  - Defines the workspace shell and static DOM anchors.
  - Contains behavior-critical `data-*` hooks such as `data-app-root`, `data-new-conversation`, `data-context-form`, `data-workspace`, `data-drawer-toggle`, `data-section`, `data-section-toggle`, `data-section-content`, `data-artifact-create-form`, and chat form hooks.
  - Contains form field names, `required`, `maxlength`, select options, button text, and script/style paths. These are not visual-only.

### Behavior-Bearing JavaScript Surfaces

These files should be treated as off-limits for visual-only work except for a separately approved behavior pass:

- `frontend/app.mjs`: application startup, event wiring, auth/session flow, workspace loading, chat submission, section rendering, and API orchestration.
- `frontend/state.mjs`: state transitions, selection, workspace/session/artifact/note/memory state, request tracking, and UI refresh decisions.
- `frontend/api.mjs`: backend paths, request methods, headers, payloads, same-origin checks, response parsing, and error normalization.
- `frontend/requests.mjs`: request identifiers, idempotency keys, chat/artifact/note/memory request construction, and frontend validation.
- `frontend/render.mjs`: DOM text helpers, hidden-state helpers, element creation, and label/value formatting.
- `frontend/workspace-layout.mjs`: side-panel and artifact-viewer layout modes.
- `frontend/chat-view.mjs`: transcript rendering, chat form handling, receipt rendering, continuity choices, feedback controls, and retry behavior.
- `frontend/work-view.mjs`: artifact list rendering, artifact creation, artifact detail rendering, export/download behavior, edit/save behavior, rename behavior, and artifact content presentation.
- `frontend/workspace-view.mjs`: workspace list rendering, workspace selection, workspace creation, and form behavior.
- `frontend/notes-view.mjs`: user-facing Notes rendering, proposal approval/rejection, archival, deletion, correction, and form behavior.
- `frontend/memory-view.mjs`: Memory rendering, approval/rejection, revocation, deletion confirmation, and feedback behavior.
- `frontend/chats-view.mjs`: chat-session list rendering and session selection.
- `frontend/activity-view.mjs`: activity rendering.

### Backend Static Serving Boundary

- `main.py`
  - Serves `/workspace` and mounts `/static/agent-col`.
  - Static file paths, cache headers, routes, auth, API handlers, schemas, persistence, model prompts, routing, memory, notes, artifacts, and working state are not visual-only surfaces.

## Explicitly Safe Visual Changes

Make these changes in `frontend/styles.css` unless a separate approved plan says otherwise.

### Color Scheme

Safe:

- change CSS custom properties in `:root`;
- change CSS custom properties inside `@media (prefers-color-scheme: dark)`;
- adjust background, surface, muted surface, text, muted text, border, accent, and danger colors;
- adjust hover, active, disabled, selected, and error colors when using existing selectors;
- improve contrast and focus visibility.

Expected result:

- the application has a different visual theme;
- all buttons, forms, panels, lists, chat turns, receipts, artifact cards, Notes, Memory, and errors still render from the same data and trigger the same behavior.

Do not:

- change JavaScript state names to support a theme;
- add theme persistence;
- add new settings UI;
- change auth/session behavior;
- change generated model prompts or memory preferences based on visual colors.

### Typography

Safe:

- change font-family in CSS;
- adjust font size, font weight, line height, and text color for existing selectors;
- style headings, labels, helper text, chat turns, artifact previews, code blocks, and receipt chips.

Expected result:

- the same text appears with different typography.

Do not:

- change response text;
- change labels that correspond to actions;
- change `humanLabel`, `humanValue`, receipt construction, generated adaptation labels, or artifact display text logic;
- hide required labels unless accessibility is preserved and separately verified.

### Spacing, Borders, Density, and Shape

Safe:

- adjust margins, padding, gaps, borders, border radius, shadows, outlines, and divider styles;
- tune card density for repeated items such as artifacts, notes, memory cards, chat sessions, receipts, and activity entries;
- adjust button and input padding as long as controls remain usable and text does not overflow.

Expected result:

- the UI feels denser, more spacious, sharper, softer, or more visually grouped without changing workflow.

Do not:

- remove controls;
- move controls into different forms;
- change button `type`;
- change input `name`, `id`, `required`, `maxlength`, or selected options;
- change disabled or hidden behavior.

### Layout-Only CSS

Safe with manual verification:

- adjust grid column widths in `.workspace-grid`;
- adjust expanded/collapsed visual widths for existing layout classes;
- tune panel padding, min-widths, max-widths, and scroll containers;
- adjust responsive CSS breakpoints;
- adjust sticky or overflow presentation where the same content remains reachable.

Expected result:

- the same panels and controls remain present, but the workspace feels better proportioned across viewport sizes.

Do not:

- change `workspace-layout.mjs`;
- rename layout state constants;
- change `data-layout-*` attributes;
- change `hidden`, `aria-expanded`, selected artifact/session state, or collapse/expand event handlers;
- make a collapsed panel visually appear active while it is behaviorally hidden.

### Chat Transcript and Response Presentation

Safe:

- style `.chat-transcript`, `.turn`, `.turn-user`, `.turn-model`, `.receipt-list`, `.receipt-item`, `.composer`, and `.chat-error`;
- change visual grouping, borders, spacing, max width, line wrapping, code-block appearance, and receipt-chip appearance;
- style existing error states without changing error classification text.

Expected result:

- the same chat content, receipts, retries, forms, and errors render with improved visual formatting.

Do not:

- modify prompt construction;
- modify responder instructions;
- modify working-state injection or hidden context;
- modify how receipts are created;
- modify retry request construction;
- modify chat request payloads;
- modify model output, memory output, adaptation receipts, or continuity receipts;
- add logic that changes when Agent Col asks clarifying questions.

### Artifact Viewer Presentation

Safe:

- style artifact list items, selected states, artifact detail panels, artifact content blocks, code blocks, export controls, edit fields, and rename fields;
- adjust wrapping and scroll behavior for artifact previews;
- improve readability of JSON, Markdown, Python, Bash, HTML, and text previews through CSS.

Expected result:

- artifacts look clearer while stored content, versions, filenames, summaries, export output, and lifecycle behavior remain unchanged.

Do not:

- change artifact family or format options;
- change artifact schema validation;
- change `summary`, `display_label`, filename, content, or version handling;
- change export file generation, MIME types, download names, Markdown conversion, print behavior, or save-version behavior;
- sanitize, transform, truncate, or rewrite artifact content as a visual workaround.

### Notes, Memory, Activity, and Continuity Presentation

Safe:

- style existing Notes cards, Memory cards, activity events, continuity choices, proposal cards, approval/rejection buttons, archive/delete buttons, and correction forms;
- adjust empty-state presentation and card density.

Expected result:

- user-facing Notes, Memory, activity, and continuity surfaces look different but preserve the same data and approval flows.

Do not:

- change note proposal lifecycles;
- change memory approval/rejection/revocation behavior;
- change delete confirmation text or behavior without a behavior pass;
- change continuity receipt logic;
- expose private working state or hidden model context;
- rename Notes as internal model state or merge Notes with working state.

### Accessibility-Safe Visual Work

Safe:

- improve color contrast;
- strengthen visible focus rings;
- preserve or improve keyboard-visible states;
- add CSS-only `prefers-reduced-motion` handling;
- improve readable line heights and touch target spacing.

Expected result:

- the application remains keyboard navigable and easier to see.

Do not:

- remove focus outlines without replacing them with equally visible focus styling;
- hide labels, buttons, or controls from keyboard users;
- change ARIA attributes or roles as part of visual work unless covered by an accessibility behavior pass;
- add motion that obscures state changes, delays controls, or changes workflow timing.

### Existing State Class Styling

Safe:

- style already-existing classes and attributes that represent selected, active, muted, expanded, collapsed, error, disabled, archived, or empty states.

Expected result:

- existing states are easier to visually distinguish.

Do not:

- add new state machines;
- change state transitions;
- change how selected records are computed;
- change event handlers;
- change whether an element is hidden, disabled, selected, expanded, archived, approved, rejected, or deleted.

## Limited HTML Changes

Avoid HTML changes for visual-only work. If absolutely necessary, the only generally safe HTML change is adding a purely presentational class to an existing static element.

Even then, do not change:

- `data-*` attributes;
- `id` values;
- `name` values;
- `type` values;
- `required`;
- `maxlength`;
- form structure;
- button text tied to actions;
- select options;
- script paths;
- stylesheet paths;
- `aria-*` attributes;
- route links;
- placeholders that communicate behavior;
- visible app copy that changes user expectations.

Expected result of a safe presentational class:

- CSS can target an element more precisely;
- JavaScript, tests, requests, forms, and backend behavior remain unchanged.

## Hard No List For Visual-Only Passes

Do not change any of the following in a visual-only pass:

- backend routes or API handlers;
- auth/session handling;
- Firestore persistence;
- request/response schemas;
- Pydantic models;
- artifact taxonomy, formats, summaries, display labels, filenames, versions, lifecycle, or exports;
- Notes creation, approval, correction, archive, delete, or proposal logic;
- Memory approval, rejection, revoke, delete, or continuity logic;
- internal working-state creation, update, hidden injection, persistence, or debugging;
- model prompts or responder policy;
- routing, synthesis, artifact intent policy, or error categorization;
- API URLs, HTTP methods, headers, body shapes, idempotency keys, or retry logic;
- JavaScript event handlers;
- state reducer behavior;
- `hidden`, `disabled`, `required`, `maxlength`, `selected`, or form validation semantics;
- `data-*` hooks used by JavaScript or tests;
- content parsing, Markdown generation, JSON generation, export/download generation, or print behavior;
- `innerHTML` insertion for display convenience.

## Response Formatting Boundary

Safe response formatting means visual styling of already-rendered response content.

Safe examples:

- make model responses easier to scan with CSS spacing;
- style user and model turns differently;
- style code blocks, inline code, tables, block quotes, and receipt chips;
- make error text more visible;
- improve wrapping and scrolling for long generated artifacts.

Unsafe examples:

- changing the model instruction text;
- changing the request sent to `/api/chat`;
- changing how model responses are parsed;
- changing how adaptation receipts are rendered from response data;
- changing hidden working-state context;
- changing markdown/export generation;
- changing whether Agent Col asks, answers, refuses, retries, or creates artifacts.

## Expected Results From Safe Visual Changes

After a safe visual change:

- `/workspace` loads at the same route;
- static assets still load from `/static/agent-col`;
- sign-in/session behavior is unchanged;
- workspace selection and creation still work;
- chat submit and retry still send the same payload structure;
- Agent Col responses are generated by the same backend behavior;
- artifact creation, selection, editing, renaming, versioning, exporting, and printing still work;
- Notes and Memory controls still behave the same;
- side-panel and artifact-viewer expand/collapse controls still behave the same;
- no private working-state data appears in the UI;
- no new network routes are introduced by visual changes.

## Required Verification For Visual-Only Changes

Run focused verification after any visual-only pass.

Minimum automated checks:

```bash
git diff --check
```

If `frontend/index.html` changes, also run the static frontend tests that cover DOM hooks.

If any JavaScript file changes, the pass is no longer CSS-only. Stop and reclassify it as a behavior-affecting pass unless the change is a narrowly approved presentational class addition with tests proving behavior hooks remain intact.

Manual runtime checks:

1. Open `/workspace` and verify the app shell, side panel, conversation area, and artifact viewer render correctly.
2. Toggle side panel collapse/expand and artifact viewer normal/expanded modes.
3. Send a normal chat request and confirm the same request flow, response area, receipts, and retry behavior remain available.
4. Create, select, rename, edit, save, export, and print/save an artifact using existing controls.
5. Open Notes, Memory, Chats, and Activity sections and verify controls still appear and behave normally.
6. Check visible focus styling by tabbing through buttons, inputs, textareas, selects, and links.
7. Check narrow and wide viewport layouts for overflow, inaccessible controls, clipped text, and hidden scroll areas.
8. Check light and dark system appearances if the change touched color variables.
9. Confirm no private working-state or hidden context appears anywhere in the user-facing UI.
10. Confirm browser network activity still targets existing application routes only.

## Checkpoint Rule

Visual-only frontend changes should not be checkpointed until the user has manually accepted the visual result. Green automated checks prove only that the files are syntactically clean; the user-facing visual result still requires manual verification.
