# Cloud Run Production Hardening And Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Agent Col for one request-bound public Cloud Run service, deploy it with Google OIDC, and capture hosted proof without adding Cloud Tasks, a private worker, or broad refactoring.

**Architecture:** Keep the existing FastAPI app as the only public Cloud Run service. Use Google OIDC for browser user identity, Cloud Run service identity for Firestore and Vertex AI access, Firestore as durable truth, and deterministic application code for auth, ownership, limits, receipts, and persistence. Add latency measurement before optimization so deployment work does not become an unbounded refactor.

**Tech Stack:** Python 3.14, FastAPI, Uvicorn, Pydantic, Google GenAI SDK, Google ADK, Firestore, Vertex AI, Google Identity Services, Cloud Run, Artifact Registry, Docker, pytest, Node test runner.

**Spec:** `PRODUCTION_HARDENING_CHECKLIST.md`, `docs/final-checklist-planning.md`, official Cloud Run and Google Identity documentation.

## Global Constraints

- Do not add Cloud Tasks, private worker execution, durable async artifact jobs, or a generalized planner.
- Production must fail closed when required environment is missing or unsafe.
- Production must require `AGENT_COL_AUTH_MODE=google_oidc`.
- Do not set `GOOGLE_APPLICATION_CREDENTIALS` on Cloud Run.
- Use a user-managed Cloud Run service account with least-privilege access.
- Container must listen on `0.0.0.0:$PORT`.
- Preserve existing local `local_dev` and local `google_oidc` workflows.
- Preserve Target A and Target B demo-ready behavior.
- Every source-changing pass requires AGENTS.md approval, TDD, focused verification, manual verification, and checkpoint approval.

---

## Research And Source Evidence

Official Cloud Run and Google Identity documentation establishes:

- Cloud Run ingress containers must listen on `0.0.0.0` and the injected `PORT`, with `8080` as the default request port.
- Cloud Run services should use a user-managed service account as service identity, and Cloud Client Libraries use ADC from that identity.
- Cloud Run services that use service identity must not set `GOOGLE_APPLICATION_CREDENTIALS`.
- Cloud Run environment variables are revision-scoped; `gcloud run deploy --set-env-vars` replaces prior variables not included in the command.
- Cloud Run request timeout defaults to 300 seconds and can be configured.
- Cloud Run maximum instances can cap costs and protect backing services.
- Google ID tokens must be server-verified for signature, `aud`, issuer, and expiry.

Current source establishes:

- `auth.py` defaults absent `AGENT_COL_AUTH_MODE` to `local_dev`, which is unsafe for production.
- `auth.py` exposes `subject` and `email` through `AuthenticatedPrincipal.public_dict()`.
- `auth.py` derives Google user IDs as `google--{subject}`.
- `main.py` only adds `Cache-Control` headers for `/workspace` and static files.
- `vertex_config.py` requires `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, and `GOOGLE_GENAI_USE_ENTERPRISE=True`.
- `generic_artifact_service.py` logs full validation errors for invalid stored generic artifacts.
- The repository currently has no `Dockerfile`, `.dockerignore`, `cloudrun.yaml`, or service descriptor.

---

## Task 1: Production Configuration Gate

**Files:**
- Modify: `auth.py`
- Modify: `main.py` if startup validation belongs in lifespan
- Test: `tests/test_auth.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: `load_auth_settings(environ)`
- Produces: production-safe auth/config settings

- [ ] Write RED tests proving production rejects missing environment marker, absent auth mode, `local_dev`, missing OAuth client ID, and placeholder project values.
- [ ] Verify RED with focused auth/startup tests.
- [ ] Add explicit environment mode, likely `AGENT_COL_ENVIRONMENT=local|production`.
- [ ] Require `google_oidc` and OAuth client ID in production.
- [ ] Preserve current local defaults only outside production.
- [ ] Verify GREEN with focused auth/startup tests.
- [ ] Manual check: local startup still works; intentionally incomplete production env fails before traffic.

## Task 2: Opaque Identity And Ownership Hardening

**Files:**
- Modify: `auth.py`
- Modify: `main.py`
- Modify: `database.py` if canonical owner records require persistence support
- Test: `tests/test_auth.py`, `tests/test_main.py`, focused database tests

**Interfaces:**
- Consumes: verified Google ID token claims
- Produces: opaque production principal and stronger workspace ownership checks

- [ ] Write RED tests proving production user IDs do not embed Google `sub`.
- [ ] Write RED tests proving `/api/auth/session` omits raw `subject` and private identity fields in production.
- [ ] Write RED tests proving cross-owner workspace/chat/note/memory/artifact access is denied.
- [ ] Implement opaque production user ID derivation.
- [ ] Add or enforce canonical workspace ownership records.
- [ ] Verify GREEN with focused auth, API, and ownership tests.
- [ ] Manual check: two Google accounts cannot read or mutate each other's workspace.

## Task 3: Request Limits, Rate Limits, And Security Headers

**Files:**
- Modify: `main.py`
- Optionally create: `request_limits.py`, `rate_limits.py`, `security_headers.py`
- Test: `tests/test_main.py`, optional focused middleware tests

**Interfaces:**
- Consumes: ASGI request boundary
- Produces: bounded public request behavior

- [ ] Write RED tests for oversized body rejection before JSON parsing.
- [ ] Write RED tests for per-principal or per-IP rate limiting.
- [ ] Write RED tests for CSP, frame, MIME sniffing, referrer, permissions, and transport security headers.
- [ ] Implement minimal middleware.
- [ ] Ensure Google Identity Services scripts remain compatible with CSP.
- [ ] Verify GREEN with focused middleware tests.
- [ ] Manual check: `/workspace`, sign-in, chat, notes, memory, and artifacts still work.

## Task 4: Privacy-Safe Logging

**Files:**
- Modify: `generic_artifact_service.py`
- Modify other logging call sites found by `rg`
- Test: `tests/test_log_privacy.py` or focused existing tests

**Interfaces:**
- Consumes: exception/logging call sites
- Produces: content-safe production logs

- [ ] Write RED tests proving prompt, memory, note, source, artifact, and feedback content are not logged.
- [ ] Replace full validation-error logging with exception class, operation, status, safe IDs, and counts.
- [ ] Verify GREEN with log privacy tests.
- [ ] Manual check: controlled validation failures in Cloud Logging contain no private content.

## Task 5: Container And Deployment Configuration

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: optional `cloudrun.yaml` or `scripts/deploy-cloud-run.sh`
- Modify docs only after behavior is accepted
- Test: static/container checks

**Interfaces:**
- Consumes: FastAPI `main:app`
- Produces: reproducible Cloud Run image/service config

- [ ] Write RED static checks proving Docker config is missing.
- [ ] Add Dockerfile using installed pinned dependencies and Uvicorn command with `--host 0.0.0.0 --port ${PORT:-8080}`.
- [ ] Add `.dockerignore` excluding `.env`, credentials, `.git`, `venv`, caches, test artifacts, screenshots, and local evidence.
- [ ] Add Cloud Run env-var reference without secrets.
- [ ] Verify local image build.
- [ ] Run container locally with safe env and health check.
- [ ] Manual check: container starts locally and `/` returns `{"status":"online"}`.

## Task 6: Cloud Project, IAM, OAuth, And Deployment Steps

**Files:**
- Documentation/scripts only unless source gaps are discovered
- Expected user-side resources: Cloud Run service, Artifact Registry repo, service account, OAuth web client

**Interfaces:**
- Consumes: Google Cloud project and OAuth client
- Produces: deployed Cloud Run service

- [ ] Confirm target project, region, billing, Firestore Native database, Vertex AI API, Firestore API, Cloud Run API, Artifact Registry API, and Cloud Build API.
- [ ] Create or select Artifact Registry Docker repository.
- [ ] Create user-managed Cloud Run service account.
- [ ] Grant minimum required roles for Firestore and Vertex AI.
- [ ] Deploy public Cloud Run service with application-level Google OIDC.
- [ ] Add Cloud Run URL to OAuth authorized JavaScript origins.
- [ ] Verify `/workspace`, `/api/auth/config`, and `/api/auth/session`.
- [ ] Manual check: Google sign-in works from the Cloud Run URL.

## Task 7: Hosted Smoke And Security Proof

**Files:**
- Modify: docs/evidence file after hosted behavior is accepted
- Test: live smoke scripts or focused hosted checks

**Interfaces:**
- Consumes: deployed service URL
- Produces: hosted proof for Devpost/demo

- [ ] Run hosted health check.
- [ ] Run hosted retry-safe chat smoke check.
- [ ] Run ownership denial check with separate account/state if available.
- [ ] Run request-limit and rate-limit checks.
- [ ] Capture Cloud Run, Firestore, Vertex AI, and log proof without secrets/private content.
- [ ] Update README/current-state/submission checklist only after hosted behavior is accepted.

## Task 8: Latency Measurement Before Optimization

**Files:**
- Prefer create: `latency_measurement.py` or `request_timing.py`
- Modify: `main.py` only for low-risk middleware/span timing
- Test: focused timing/log-safety tests

**Interfaces:**
- Consumes: `/api/chat` request lifecycle
- Produces: content-safe phase timing for local and Cloud Run comparison

- [ ] Write RED tests proving timing output includes phase names but no prompt/response/memory/note/artifact/source content.
- [ ] Measure request validation, auth, Firestore turn claim, memory/profile load, routing, expert execution, responder generation, working-state update, preference capture, Firestore persistence, and serialization where seams are available.
- [ ] Keep instrumentation optional or production-safe.
- [ ] Run one local demo-sized chat and record timings.
- [ ] Run the same prompt on Cloud Run and compare.
- [ ] Only propose optimization after evidence identifies the bottleneck.

## Recommended First Implementation Pass

Start with Task 1 only: production configuration gate. It is the highest-risk deployment blocker because current source can default to `local_dev` when `AGENT_COL_AUTH_MODE` is absent. This pass is narrow, testable, and prevents accidentally exposing the local-dev identity mode.
