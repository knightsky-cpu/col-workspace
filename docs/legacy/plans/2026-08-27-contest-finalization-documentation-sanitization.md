# Contest Finalization Documentation Sanitization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this documentation-only plan task-by-task. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Reconcile Agent Col's roadmap and submission documentation around the
current contest-finalization strategy.

**Architecture:** Documentation only. Create one controlling finalization
reference, mark old async-first Winning Core documents as historical or
deferred, and retarget current README/current-state/submission docs to the
single-service judged-build path.

**Tech Stack:** Markdown, local source inspection, official Devpost links, `rg`,
and `git diff --check`.

**Spec:** `docs/final-checklist-planning.md`

## Global Constraints

- Do not change application source, tests, dependencies, configuration, or
  runtime behavior in this pass.
- Treat official Devpost pages as authority for competition requirements.
- Treat current source as authority for implemented behavior.
- Treat durable async artifacts, Cloud Tasks, and private worker execution as
  post-submission deferred work unless explicitly reopened by the repository
  owner.
- Preserve old plans as provenance; do not rewrite historical implementation
  evidence to pretend it was always the current strategy.
- Keep Target A explicit: observation evidence is not a preference hypothesis,
  a candidate memory, or active memory.
- Keep Target B explicit: visible leadership uses existing working state and
  does not introduce a planner.

---

### Task 1: Create The Current Finalization Reference

**Files:**
- Create: `docs/final-checklist-planning.md`

**Interfaces:**
- Consumes: official Devpost requirements and current source-state docs.
- Produces: the current strategic authority for pre-submission work.

- [x] **Step 1: Write the finalization reference**

Create `docs/final-checklist-planning.md` with:

- official competition anchors;
- deferred async/Cloud Tasks/private-worker statement;
- current accepted core;
- Target A;
- Target B;
- single-service productionization target;
- visual polish boundary;
- documentation/evidence target;
- final demo story;
- ordered final path.

- [x] **Step 2: Verify the file exists**

Run:

```bash
test -f docs/final-checklist-planning.md
```

Expected: exit `0`.

### Task 2: Retarget Current State And README

**Files:**
- Modify: `docs/current-state.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `docs/final-checklist-planning.md`.
- Produces: front-door docs that no longer present old Phase 3 async work as a
  pre-submission blocker.

- [x] **Step 1: Update current-state roadmap**

Replace the old "Remaining Winning Core Phases" section with a "Contest
Finalization Track" that points to `docs/final-checklist-planning.md`.

- [x] **Step 2: Update README roadmap link**

Add `docs/final-checklist-planning.md` to the documentation list and make clear
that durable async artifacts are post-submission deferred work.

### Task 3: Mark Old Roadmap Plans As Superseded For Submission

**Files:**
- Modify: `docs/aug-25-2026-final-checklist.md`
- Modify: `docs/superpowers/plans/2026-08-25-winning-core-phase-3-async-artifact-work.md`
- Modify: `docs/superpowers/plans/2026-08-25-winning-core-phase-4-production-deployment.md`

**Interfaces:**
- Consumes: `docs/final-checklist-planning.md`.
- Produces: old plans that remain available as provenance but cannot be
  mistaken for current pre-submission authority.

- [x] **Step 1: Add superseded-strategy notices**

Add top-of-file notices pointing to `docs/final-checklist-planning.md`.

- [x] **Step 2: Preserve reusable engineering notes**

Do not delete the old implementation detail. Label durable async/worker
dependencies as deferred or historical.

### Task 4: Rewrite Submission Checklist Around Official Devpost Requirements

**Files:**
- Modify: `docs/submission-checklist.md`

**Interfaces:**
- Consumes: official Devpost rules and FAQ.
- Produces: a practical checklist for the actual judged submission.

- [x] **Step 1: Remove obsolete Cloud Tasks requirements**

Remove private-worker, queue-auth, job-ownership, and durable job-state proof
from current submission requirements.

- [x] **Step 2: Add official-submission proof items**

Include hosted URL if available, repository access, spin-up instructions,
architecture diagram, public video, four-minute limit, Google Cloud proof,
Devpost copy, licensing, secrets, and availability/freeze notes.

### Task 5: Verify Documentation Sanitation

**Files:**
- Inspect: changed Markdown files.

**Interfaces:**
- Consumes: all changed docs.
- Produces: verification evidence for the pass report.

- [x] **Step 1: Check whitespace**

Run:

```bash
git diff --check
```

Expected: exit `0`.

- [x] **Step 2: Search stale blockers outside historical context**

Run:

```bash
rg -n "Phase 3 acceptance|sequentially through Phases 1-6|durable job-state|private worker|Cloud Tasks" README.md docs -S -g '!docs/legacy/**'
```

Expected: any remaining matches are explicitly deferred, historical, or inside
old plans with superseded-strategy notices.

- [x] **Step 3: Inspect changed-file status**

Run:

```bash
git status --short
```

Expected: only documentation files from this approved pass are changed.
