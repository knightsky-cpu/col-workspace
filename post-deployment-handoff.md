# Agent Col Post-Deployment Handoff

Last updated: August 28, 2026.

## Authoritative State

Cloud Run deployment phase is complete and accepted.

Passes 1 through 8 are complete:

- Pass 1: Cloud Run fail-closed config guard.
- Pass 2: ownership audit and gap closure.
- Pass 3: public/internal user identity split.
- Pass 4: HTTP body limits, scoped rate limiting, and security headers.
- Pass 5: privacy-safe logging review and hardening context.
- Pass 6: deployment packaging with `Dockerfile` and `.dockerignore`.
- Pass 7: Artifact Registry, IAM, and Cloud Run deployment.
- Pass 8: hosted OAuth and authenticated integration proof.

The deployment-complete checkpoint at the time this file was created is:

```text
afa6efbe85db07d203dd583b1277d1a4b13b86d0
```

Use the checkpoint SHA provided by the user at the start of the next session as
the authoritative expected baseline. Do not assume the SHA above is still
current if the user provides a newer deployment-complete checkpoint.

The next work sequence is:

1. frontend visual improvements;
2. the separately planned streaming behavior pass;
3. final hosted visual verification and submission evidence.

## Required Start Procedure For The Next Session

Before editing any file, the next session must:

1. Verify the current local `HEAD` matches the deployment-complete checkpoint
   SHA provided by the user when the session begins.
2. Confirm a clean tracked worktree.
3. Read `AGENTS.md` completely.
4. Thoroughly review all current frontend visual planning documents and the
   visual target asset listed below.
5. Inspect the current frontend source and relevant tests against the plans'
   claims, assumptions, file boundaries, selectors, responsive behavior, and
   stated constraints.
6. Report any stale assumptions, discrepancies, or source-plan mismatches before
   editing.
7. If revisions are needed, present a revised visual improvement plan for user
   approval.
8. If no revision is needed, explicitly report that the existing visual plan is
   still source-valid and present the first bounded implementation pass for user
   approval.
9. Do not begin implementation without explicit user approval in either case.

## Binding Visual-Only Boundary

The frontend visual phase is appearance-only unless the user separately approves
a broader plan.

Do not modify backend behavior, auth, persistence, memory, notes, artifacts,
working state, model prompts, routing, deployment configuration, IAM, Google
Cloud APIs, Artifact Registry, or Cloud Run settings during the visual-only
phase.

Default expected implementation surface:

- `frontend/styles.css`

Locked unless a separately approved plan changes the boundary:

- `frontend/index.html`
- `frontend/*.mjs`
- `main.py`
- backend/application Python modules
- schemas, persistence, auth, memory, notes, artifacts, working state, routing,
  prompts, and deployment files

The visual pass must preserve:

- the same user actions;
- the same routes;
- the same request payloads and headers;
- the same backend responses and rendered data;
- the same hidden, disabled, expanded, selected, and error semantics;
- the same Notes, Memory, artifacts, chats, receipts, working-state behavior,
  auth behavior, and persistence behavior.

## Review These Documents First

Start with these exact files, in this order:

1. `AGENTS.md`
2. `post-deployment-handoff.md`
3. `deployment-notes.md`
4. `README.md`
5. `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md`
6. `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md`
7. `docs/superpowers/plans/2026-08-28-updated-finalization-handoff.md`
8. `docs/final-checklist-planning.md`
9. `docs/superpowers/plans/2026-08-28-chat-response-streaming-plan.md`
10. `agent-col-visual-target.jpeg`

Important status note: `docs/superpowers/plans/2026-08-28-updated-finalization-handoff.md`
contains useful frontend and streaming guidance, but its deployment-pending
language is stale. `deployment-notes.md`, `README.md`, and this handoff are
newer for Cloud Run deployment status.

## Inspect These Frontend Source Files First

Primary visual source:

- `frontend/styles.css`

Frontend structure and behavior boundaries:

- `frontend/index.html`
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

Relevant frontend/static tests:

- `tests/frontend/workspace-static.test.mjs`
- `tests/frontend/workspace-layout.test.mjs`
- `tests/frontend/chat-view.test.mjs`
- `tests/frontend/work-view.test.mjs`
- `tests/frontend/workspace-view.test.mjs`
- `tests/frontend/notes-view.test.mjs`
- `tests/frontend/memory-view.test.mjs`
- `tests/frontend/chats-view.test.mjs`
- `tests/frontend/activity-view.test.mjs`
- `tests/frontend/api.test.mjs`
- `tests/frontend/requests.test.mjs`
- `tests/frontend/state.test.mjs`
- `tests/test_workspace_static.py`

If a listed test file is missing or renamed, report that discrepancy before
planning edits.

## Current Visual Plan To Validate

The current visual improvement plan is:

```text
docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md
```

The safe visual boundary guide is:

```text
docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md
```

The visual target asset is:

```text
agent-col-visual-target.jpeg
```

The next session must verify that the plan is still source-valid against the
current `frontend/styles.css`, `frontend/index.html`, JavaScript behavior
modules, selectors, responsive breakpoints, and tests. Do not rely on the plan's
embedded source snippets without checking the live files.

Known visual target direction from the plan:

- dark app shell;
- near-black blue/green surfaces;
- restrained teal primary accent;
- amber secondary accents;
- subtle borders;
- 8px-or-less radius;
- dense professional workspace;
- polished top bar, drawers, chat surface, composer, and artifact panel.

This target is a visual benchmark, not authorization to change behavior.

## Streaming Pass Boundary

The streaming plan is separate:

```text
docs/superpowers/plans/2026-08-28-chat-response-streaming-plan.md
```

Do not implement streaming during the visual-only phase. Streaming is a
behavior-changing pass involving backend streaming, frontend request/rendering
changes, tests, and hosted Cloud Run streaming verification. It requires its own
approval under `AGENTS.md`.

## Expected Next Report

After reading and source inspection, the next session should report:

- verified checkpoint SHA and worktree cleanliness;
- which documents and source files were reviewed;
- stale assumptions or mismatches found, if any;
- whether the existing visual plan remains source-valid;
- the first bounded visual implementation pass proposed for approval, or a
  revised plan if the current one is stale;
- expected touched files;
- locked files and behaviors;
- focused automated verification commands;
- manual hosted visual verification targets.

Stop after that report and wait for explicit approval before implementation.
