# Agent Col Deployment Handoff

Date: 2026-08-28

Purpose: preserve the exact deployment work state after accepted production-hardening Pass 5 and define the next required workflow boundary. This document does not authorize implementation by itself.

## Current State

- Branch: `main`
- Latest pushed checkpoint before this handoff update: `5554d28bd5f662a0bc6e3aebc75d792e088e33de`
- Accepted production-hardening passes:
  - Pass 1: Cloud Run fail-closed auth configuration guard
  - Pass 2: ownership audit and gap closure
  - Pass 3: public/internal user identity split
  - Pass 4: raw HTTP body limits, scoped in-memory rate limiting, and security headers
  - Pass 5: production logging privacy audit
- Known untracked workspace item: `.agents/`
- `.agents/` is repository-local agent tooling context and must not be staged by broad Git commands.

## What Work We Are Doing

The active deployment track is the single-service Agent Col Cloud Run deployment path.

The selected submission deployment path is:

```text
Dockerfile
-> build Agent Col container image
-> push image to Artifact Registry
-> deploy that image to one public Cloud Run service
-> application-level Google OIDC protects user data inside FastAPI
```

Do not switch the submission path to `gcloud run deploy --source` or Google Buildpacks unless the user explicitly revises the deployment strategy. Source deploy and buildpacks remain documented alternatives, not the selected path.

The application already has Google OIDC mode, Google ID-token verification, OAuth client configuration, Firestore persistence, Vertex configuration validation, ownership checks, public identity minimization, perimeter request limits, security headers, and logging privacy hardening. The remaining work is deployment packaging and Google Cloud deployment plumbing around the existing architecture.

## Mandatory Documents To Review Before The Next Report

Before reporting readiness for the next pass or proposing implementation, review these documents in this order:

1. `AGENTS.md`
   - Required workflow, TDD, manual acceptance, and GitHub checkpoint rules.
2. `docs/deployment/deployment-handoff.md`
   - This current handoff and selected deployment path.
3. `docs/deployment/deployment-notes.md`
   - Accepted pass history, verification evidence, checkpoint history, and limitations.
4. `docs/superpowers/plans/2026-08-28-updated-finalization-handoff.md`
   - Current project/submission alignment and superseding handoff context.
5. `docs/superpowers/plans/2026-08-28-cloud-run-production-hardening-deployment.md`
   - Current Cloud Run production hardening and deployment implementation plan.
6. `docs/deployment/2026-08-28-agent-col-cloud-run-first-deployment-preflight.md`
   - First deployment preflight state, blockers, required configuration, and go/no-go checklist.
7. Current source files expected to be touched by the proposed pass.
   - For Pass 6, this includes packaging/startup files that exist or are missing, dependency manifests, `main.py`, and repository ignore files.
8. Current official Google Cloud Run, Artifact Registry, and container runtime documentation.
   - Verify any claim that could drift before proposing commands or implementation.

Do not rely on older Phase 4 documents alone. They contain useful context but may include superseded assumptions such as Cloud Tasks/private-worker work or buildpack/source-deploy alternatives.

## Immediate Next Pass

Proposed next pass: Pass 6, deployment packaging with explicit Dockerfile and container image path.

Expected goal:

- Add a reproducible local container packaging path for the existing FastAPI app.
- Make the production container start Uvicorn on `0.0.0.0:$PORT` without reload.
- Exclude local secrets, caches, screenshots, evidence, and workspace debris from the Docker build context.
- Prove the container can build locally and answer cheap local health/workspace checks.
- Do not push an image.
- Do not deploy to Cloud Run.
- Do not create or modify Google Cloud resources.
- Do not change OAuth, IAM, Artifact Registry, Cloud Run service configuration, or runtime environment variables.

Expected files or surfaces to inspect before proposing Pass 6:

- `pyproject.toml`
- dependency lock or requirements files, if present
- `main.py`
- `frontend/`
- existing ignore files: `.gitignore`, `.dockerignore`, `.gcloudignore`
- existing deployment files, if any: `Dockerfile`, `Procfile`, `cloudrun.yaml`, `service.yaml`, `app.yaml`
- `docs/deployment/2026-08-28-agent-col-cloud-run-first-deployment-preflight.md`
- `docs/superpowers/plans/2026-08-28-cloud-run-production-hardening-deployment.md`

Expected implementation proposal shape:

- Present source-backed current packaging state.
- Present official-doc-backed Cloud Run container contract requirements.
- Propose the exact Dockerfile and ignore-file boundary.
- Identify the RED tests or build checks that will fail first.
- Identify focused verification commands.
- Identify manual local container verification targets.
- Wait for explicit user approval before editing source or packaging files.

## Pass 6 Acceptance Boundary

Pass 6 should be treated as packaging only.

In scope:

- `Dockerfile`
- `.dockerignore`
- optional minimal packaging/startup tests or docs directly needed to prove the container boundary
- local container build and local container smoke verification

Out of scope:

- `gcloud run deploy`
- Artifact Registry push
- enabling Google APIs
- IAM/service-account changes
- OAuth authorized-origin changes
- Cloud Run concurrency, min/max instances, timeout, probe, or environment-variable configuration
- hosted Google Sign-In verification
- hosted Firestore/Vertex proof
- latency measurement

Those belong to later deployment passes after Pass 6 is accepted.

## Known Risks To Preserve In Reports

- The in-memory rate limiter is per Cloud Run instance only. It is best-effort, non-durable, and reset on instance restart.
- Google Sign-In/CSP behavior must be proven in hosted/browser verification, not treated as complete from local tests.
- Cloud Logging canary verification is still required after deployment; source tests cannot prove platform request/container logs are clean.
- Cloud Run public invocation must remain separate from application-level Google OIDC.
- OAuth Cloud Run origin is required before authenticated hosted smoke testing, but not before the first service can be created.
- Dedicated runtime service account is a project security/governance requirement, not a Cloud Run technical admission requirement.
- Artifact Registry and Cloud Run region should stay aligned with Firestore location as closely as supported.

## Required Next Response Behavior

At the start of the next deployment-work turn:

1. Read the mandatory documents listed above.
2. Inspect current source/package/ignore state.
3. Verify any current Google Cloud Run or Artifact Registry documentation needed for Pass 6.
4. Report source-backed current state and discrepancies.
5. Propose the bounded Pass 6 implementation plan.
6. Wait for user approval before editing files.

