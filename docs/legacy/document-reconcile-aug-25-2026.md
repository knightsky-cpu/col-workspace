# Documentation Reconciliation Findings - August 25, 2026

## TL;DR

The repository documentation is strongest in the governing identity, workflow,
and recent Winning Core planning documents, but the high-visibility setup,
architecture, integration, testing, troubleshooting, and submission documents
are stale against the current source.

The most important correction is to stop describing the browser workspace and
authentication foundation as missing. Current source serves `/workspace`,
mounts the `frontend/` application, exposes local-development and Google OIDC
auth configuration/session routes, supports workspace and chat-session APIs,
and provides blueprint plus generic artifact read and lifecycle APIs.

The immediate documentation goal should be a Phase 5 reconciliation pass that
makes the repository front door truthful for judges, future Codex sessions, and
clean-clone setup. Historical plans and archived docs should remain preserved
as provenance, but current README, architecture, local setup, testing,
troubleshooting, integration inventory, and submission docs must be reconciled
with executable source.

## Review Scope

This read-only review inspected all Markdown files in the project directory:

- `97` Markdown files total;
- root governance and product documents;
- development, architecture, troubleshooting, and submission documents;
- research audits;
- legacy documentation;
- Superpowers implementation plans and specs.

The review compared documentation claims against current source and
configuration surfaces, especially:

- `main.py`;
- `schemas.py`;
- `auth.py`;
- `vertex_config.py`;
- `requirements.txt`;
- `requirements-dev.txt`;
- `firestore.indexes.json`;
- `frontend/`;
- `tests/`.

Current source remains authoritative when older documentation conflicts with
implementation.

## Current Source Truth

Current `main.py` exposes the following implemented surfaces:

- same-origin browser workspace at `/workspace`;
- static frontend mount backed by `frontend/`;
- `GET /`;
- `GET /api/auth/config`;
- `GET /api/auth/session`;
- `GET /api/users/{user_id}/memory`;
- `GET /api/users/{user_id}/workspaces`;
- `POST /api/users/{user_id}/workspaces`;
- `GET /api/users/{user_id}/projects/{project_id}/chat-sessions`;
- `GET /api/users/{user_id}/projects/{project_id}/chat-sessions/{session_id}`;
- `POST /api/users/{user_id}/memory/signals/{signal_id}/revoke`;
- `DELETE /api/users/{user_id}/memory/signals/{signal_id}`;
- `POST /api/synthesize`;
- `GET /api/projects/{project_id}/blueprints`;
- `GET /api/projects/{project_id}/blueprints/{blueprint_id}`;
- `GET /api/projects/{project_id}/artifacts`;
- `POST /api/projects/{project_id}/artifacts`;
- `GET /api/projects/{project_id}/artifacts/{artifact_id}`;
- `POST /api/projects/{project_id}/artifacts/{artifact_id}/archive`;
- `POST /api/projects/{project_id}/artifacts/{artifact_id}/restore`;
- `PATCH /api/projects/{project_id}/artifacts/{artifact_id}/metadata`;
- `POST /api/projects/{project_id}/artifacts/{artifact_id}/versions`;
- `GET /api/projects/{project_id}/blueprints/{blueprint_id}/feedback`;
- `POST /api/chat`.

Current pinned stack from source and requirements:

- Python local/runtime target: Python 3.14.x, with Phase 4 planning targeting
  Python 3.14.7 for production;
- FastAPI `0.141.1`;
- Google ADK `2.7.0`;
- Google GenAI SDK `2.18.1`;
- Google Cloud Firestore `2.28.1`;
- Pydantic `2.13.4`;
- Uvicorn `0.52.4`;
- model constants use `gemini-3.6-flash`;
- Vertex configuration requires `GOOGLE_CLOUD_LOCATION=global`;
- Vertex configuration requires `GOOGLE_GENAI_USE_ENTERPRISE=True`;
- browser authentication supports `AGENT_COL_AUTH_MODE=local_dev` and
  `AGENT_COL_AUTH_MODE=google_oidc`;
- Google browser sign-in requires `GOOGLE_OAUTH_CLIENT_ID`.

## Highest Priority Stale Documents

### `README.md`

Stale claims:

- It says the browser workspace is not implemented.
- It says authentication is not implemented, grouping implemented local/Google
  OIDC auth foundation with still-missing public Cloud Run deployment.
- It omits workspace APIs, chat-session APIs, generic artifact APIs, artifact
  lifecycle controls, memory clarification support, and `/workspace`.
- It only shows a bare `uvicorn main:app --reload` launch path.

Required corrections:

- Replace the implemented/not-implemented lists with the current source truth.
- Add `/workspace` as the primary local UI entry point.
- Document both launch modes:
  - `AGENT_COL_AUTH_MODE=local_dev venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000`
  - `AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000`
- Explain that Google OIDC foundation exists, while production deployment,
  complete ownership hardening, limits, retention, and hosted proof remain
  pending.

### `docs/architecture.md`

Stale claims:

- It describes the browser workspace as planned.
- Its current architecture diagram omits the implemented same-origin browser.
- Its Firestore model omits workspace records, chat-session metadata, generic
  artifacts, artifact lifecycle/versioning, feedback details, and memory
  clarification state.
- Its Phase 3B/Phase 4 status is behind current implementation.

Required corrections:

- Rewrite the current implemented architecture around browser workspace,
  FastAPI, ADK/Gemini, deterministic services, Firestore, and authoritative
  receipts.
- Keep Cloud Tasks/private worker as planned until Phase 3 implementation
  lands.
- Update the Firestore model with current workspace, session, memory,
  artifact, feedback, and turn-effect entities.

### `BACKEND_FRONTEND_INTEGRATION_CONTRACT_INVENTORY.md`

Stale claims:

- It says there is no frontend application or static-file mount.
- It says the public route count is nine.
- It omits current workspace, chat-session, generic artifact, artifact
  lifecycle, and memory clarification contracts.
- It includes older missing-contract entries that source has since
  implemented.

Required corrections:

- Replace the route inventory with the current `main.py` route list.
- Acknowledge `/workspace` and the `frontend/` same-origin application.
- Add current request and response models for workspace, chat session, generic
  artifact, lifecycle, and memory clarification selection.
- Keep true gaps only: governed workspace notes, durable jobs, full production
  ownership, retention/deletion policy, and async status APIs.

### `docs/development/local-setup.md`

Stale claims:

- It says browser UI and authentication are not part of the current local
  runtime.
- It does not document `AGENT_COL_AUTH_MODE`.
- It does not document `GOOGLE_OAUTH_CLIENT_ID`.
- It does not direct the developer to `/workspace`.

Required corrections:

- Add an environment-variable table for:
  - `GOOGLE_CLOUD_PROJECT`;
  - `GOOGLE_CLOUD_LOCATION`;
  - `GOOGLE_GENAI_USE_ENTERPRISE`;
  - `AGENT_COL_AUTH_MODE`;
  - `GOOGLE_OAUTH_CLIENT_ID`.
- Distinguish ADC for Firestore/Vertex from browser Google OIDC.
- Add local-dev and Google OIDC launch commands.
- Add OAuth authorized JavaScript origin requirement for
  `http://127.0.0.1:8000`.

### `docs/development/testing.md`

Incomplete or stale areas:

- It does not include the frontend Node test surface.
- It does not include current auth, workspace static, generic artifact,
  chat-session, and memory clarification focused checks.

Required corrections:

- Add focused commands for:
  - `tests/test_auth.py`;
  - `tests/test_workspace_static.py`;
  - `tests/test_generic_artifact_*`;
  - `tests/frontend/*.test.mjs`;
  - memory clarification tests;
  - chat-session list/detail tests in `tests/test_main.py`.
- Add a surface-based test matrix for source-changing passes.

### `docs/development/troubleshooting.md`

Incomplete or stale areas:

- No Google OIDC troubleshooting.
- No `/workspace` static/frontend troubleshooting.
- No generic artifact lifecycle troubleshooting.
- No memory clarification selection troubleshooting.
- Firestore console link is maintainer-specific and hardcodes
  `project-e1e2a890-4566-48a8-a32`.

Required corrections:

- Add missing OAuth client ID, invalid Google token, user/workspace mismatch,
  `/workspace` asset, generic artifact, and clarification selection sections.
- Replace the hardcoded Firestore link with `YOUR_PROJECT_ID`, or label it as
  maintainer-local evidence only.

### `docs/submission-checklist.md`

Stale or too narrow:

- The runbook remains blueprint-heavy.
- It does not reflect the approved Winning Core path.
- It treats verified auth as entirely missing instead of splitting auth
  foundation from production hardening.
- It still implies PDF-like input as central, while the approved path requires
  pasted messy text and treats PDF upload as optional.

Required corrections:

- Reframe around Collaborative Partner proof:
  - cross-session memory continuity;
  - governed workspace notes;
  - consequential clarification;
  - durable async artifact job;
  - Cloud Run/Firestore/Cloud Tasks evidence;
  - controlled failure proof.
- Split status into implemented locally, production pending, and final
  evidence pending.
- Make pasted messy text the required ingestion boundary.

### `docs/aug-25-2026-final-checklist.md`

Stale status:

- Phase 4 plan is now approved and checkpointed at `ce0a6be`.
- Phase 2 plan is checkpointed at `f7d20e0`.
- Phase 3 plan is checkpointed at `c889a99`.
- The completion record still says Phases 2, 3, and 4 are pending plan.

Required corrections:

- Update Phase 2, Phase 3, and Phase 4 plan checkpoint status.
- Keep implementation status pending until accepted implementation exists.
- Preserve the Phase 4 stop gate requiring accepted Phases 1-3 and final
  source re-audit before implementation.

## Snapshot Documents To Treat Carefully

### `features-plan-revisions.md`

This is useful, source-grounded review material from commit `609e993...`, but
it is not current source truth.

Potential stale claims:

- It reports a Python baseline of `5 failed, 1935 passed`; that must be
  reverified before repeating as current.
- It references August 24 unaccepted local changes that may no longer apply.
- Some memory/category findings may have changed after later memory lifecycle
  passes.

Recommended correction:

- Keep it as a snapshot review artifact.
- Do not use its test failure count in current README/submission material
  unless freshly reverified.

### `frontend-plan-revision.md`

This is also useful as an August 24 frontend review snapshot.

Potential stale claims:

- It may understate later memory clarification and lifecycle work.
- It references older unaccepted local frontend state.

Recommended correction:

- Keep it as a snapshot review artifact.
- Use it as rationale for Phase 5 reconciliation and future frontend passes,
  not as judge-facing current status.

### `AGENT_COL_IDENTITY_AND_ALIGNMENT.md`

The identity, memory-boundary, and evaluation-priority sections remain strong
and should stay authoritative.

Stale section:

- The "Current implementation status and gaps" section says the
  judge-facing artifact workflow remains unfinished and synthesis is still
  separate rather than chat-routed. Current source now includes chat-routed
  artifacts, artifact feedback, generic artifacts, and browser workspace
  foundations.

Required correction:

- Update only the current-status section.
- Keep the governing product identity unchanged.
- Shift current gaps to:
  - Phase 1 clarification UI and cross-session proof;
  - Phase 2 governed workspace notes;
  - Phase 3 durable async jobs;
  - Phase 4 production hardening;
  - Phase 5/6 submission evidence.

### `DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`

This remains the correct documentation standard.

Stale section:

- "Current documentation gap" is dated August 20, 2026.

Required correction:

- Refresh the gap statement during Phase 5.
- Decide whether to create the target doc tree now or keep a smaller
  submission-focused structure until after the hackathon.

## Correctly Historical Documentation

The following documentation should stay historical rather than be rewritten as
current truth:

- `docs/legacy/README.md`;
- `docs/legacy/context.md`;
- older `docs/superpowers/plans/*`;
- older `docs/superpowers/specs/*`.

The legacy directory is already correctly marked as archived. Many old plans
and specs contain obsolete assumptions by design, including older auth,
browser, API-key, and deployment claims. They are acceptable as provenance as
long as current docs do not point to them as current implementation status.

## Current Winning Core Plan Documents

The Phase 1-4 Winning Core plan documents are useful and directionally aligned:

- `docs/superpowers/plans/2026-08-25-winning-core-phase-1-memory-continuity.md`;
- `docs/superpowers/plans/2026-08-25-winning-core-phase-1-remaining-work.md`;
- `docs/superpowers/plans/2026-08-25-winning-core-phase-2-workspace-notes.md`;
- `docs/superpowers/plans/2026-08-25-winning-core-phase-3-async-artifact-work.md`;
- `docs/superpowers/plans/2026-08-25-winning-core-phase-4-production-deployment.md`.

Status corrections needed:

- Phase 2 plan should reflect that the plan was approved and checkpointed,
  while implementation remains pending.
- Phase 3 plan should reflect that the plan was checkpointed, while
  implementation remains pending Phases 1-2 and separate approval.
- Phase 4 plan should reflect that the plan was approved and checkpointed,
  while implementation remains pending Phases 1-3 and final re-audit.

Do not alter their implementation boundaries without a separate approved
planning pass.

## Recommended Documentation Reconciliation Order

1. Update `docs/aug-25-2026-final-checklist.md` status and checkpoint records.
2. Update `README.md` so the repository front door is truthful.
3. Rewrite `docs/development/local-setup.md` around `/workspace`, local-dev
   mode, Google OIDC mode, ADC, and exact environment variables.
4. Rewrite `docs/architecture.md` against current source.
5. Replace `BACKEND_FRONTEND_INTEGRATION_CONTRACT_INVENTORY.md` with a current
   route and model inventory.
6. Refresh `docs/development/testing.md`.
7. Refresh `docs/development/troubleshooting.md`.
8. Refresh `docs/submission-checklist.md`.
9. Refresh the current-status section of
   `AGENT_COL_IDENTITY_AND_ALIGNMENT.md`.
10. Refresh `DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md` only where it
    describes the current gap.

## Proposed Phase 5 Documentation Pass Boundary

Goal: reconcile the current documentation set with executable source and the
approved Winning Core path so a judge or fresh developer can understand,
install, run, test, and evaluate the actual project.

Expected files:

- `README.md`;
- `docs/architecture.md`;
- `docs/development/local-setup.md`;
- `docs/development/testing.md`;
- `docs/development/troubleshooting.md`;
- `BACKEND_FRONTEND_INTEGRATION_CONTRACT_INVENTORY.md`;
- `docs/submission-checklist.md`;
- `docs/aug-25-2026-final-checklist.md`;
- `AGENT_COL_IDENTITY_AND_ALIGNMENT.md`;
- `DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`.

Preserved behavior:

- documentation-only unless the user separately approves source changes;
- no credential, token, `.env`, ADC file, raw chat content, memory values, or
  private Firestore document content may be committed;
- historical docs remain preserved as historical provenance;
- current source remains authoritative over older specs.

Verification targets:

- `git diff --check`;
- link/path spot checks for every changed repository-relative link;
- command review for every launch/test command;
- secret scan of changed documentation for private values;
- no source files changed during the documentation-only pass unless separately
  approved.

## Stop Conditions

Stop and request a revised plan if:

- source behavior must change to make the docs true;
- a documented command cannot be verified and would mislead clean-clone setup;
- a credential or private identifier would need to be shown;
- Phase 1-4 implementation status changes before the reconciliation pass
  begins;
- the documentation pass starts expanding into demo recording, deployment, or
  code changes without separate approval.
