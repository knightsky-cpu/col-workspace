# Contest Finalization Single-Service Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Harden and deploy Agent Col as one request-bound public Cloud Run
service for the judged Collaborative Partner build.

**Architecture:** Fork the reusable single-service controls from the old Phase
4 plan and remove Cloud Tasks/private-worker dependencies. Keep FastAPI as the
public service, Firestore as durable truth, Vertex AI/Gemini as provider
backend, Google OIDC as the user identity boundary, and deterministic
application code as authority for persistence, limits, receipts, and ownership.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, Uvicorn, Google ADK, Google
GenAI SDK, Vertex AI, Firestore, Google OIDC, Cloud Run, Artifact Registry,
Bash, pytest, Node test runner, and vanilla JavaScript ES modules.

**Spec:** `docs/final-checklist-planning.md`

## Global Constraints

- Do not add Google Cloud Tasks, a private worker, queue authentication, job
  retry/cancellation, or worker failure proof in this pre-submission plan.
- Keep the app request-bound for the judged build.
- Production must fail closed when required environment is missing or unsafe.
- Production must require `google_oidc`; `local_dev` is local-only.
- Do not expose raw Google subject identifiers in production user IDs or public
  responses.
- Firestore remains durable truth.
- Browser calls only same-origin FastAPI routes.
- No service-account keys, OAuth secrets, tokens, prompt text, memory values,
  note text, artifact content, or source text may be committed or logged.
- Every source-changing pass requires AGENTS.md approval, TDD, focused
  automated verification, manual verification, and checkpoint approval.

---

### Task 1: Production Configuration Gate

**Files:**
- Modify: `auth.py`
- Modify: `main.py`
- Create or modify tests: `tests/test_auth.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: current `load_auth_settings()` and FastAPI lifespan startup.
- Produces: explicit production-mode validation that refuses unsafe defaults.

- [ ] **Step 1: Write RED tests**

Add tests proving production startup rejects:

- missing production environment marker;
- absent `AGENT_COL_AUTH_MODE`;
- `AGENT_COL_AUTH_MODE=local_dev`;
- missing Google OAuth client ID;
- placeholder project/origin values.

- [ ] **Step 2: Verify RED**

Run focused auth/startup tests and confirm they fail for missing production
validation.

- [ ] **Step 3: Implement fail-closed settings**

Add explicit production settings with safe defaults only for local mode. Keep
current local startup commands working.

- [ ] **Step 4: Verify GREEN**

Run the focused auth/startup tests and one local mode regression.

### Task 2: Opaque Production Principal And Ownership Gate

**Files:**
- Modify: `auth.py`
- Modify: `main.py`
- Modify: `database.py` if canonical owner records require persistence changes.
- Create or modify tests: `tests/test_auth.py`, `tests/test_main.py`,
  `tests/test_database.py`

**Interfaces:**
- Consumes: current Google ID token verification and workspace-project
  derivation.
- Produces: production-safe principal IDs and canonical workspace ownership
  checks.

- [ ] **Step 1: Write RED tests**

Add tests proving production mode:

- derives opaque user IDs instead of `google--{subject}`;
- does not expose raw `subject` in public session responses;
- denies cross-user and cross-workspace reads/writes with bounded public errors;
- preserves accepted local-dev behavior outside production.

- [ ] **Step 2: Verify RED**

Run the focused auth/main/database tests and inspect expected failures.

- [ ] **Step 3: Implement principal and owner hardening**

Hash or otherwise opaque production user IDs. Add or verify canonical owner
records for workspace-scoped operations.

- [ ] **Step 4: Verify GREEN**

Run focused auth, ownership, chat, note, memory, artifact, and workspace tests.

### Task 3: Request Limits, Rate Limits, And Security Headers

**Files:**
- Modify: `main.py`
- Create optional focused modules: `request_limits.py`, `rate_limits.py`,
  `security_headers.py`
- Create or modify tests: `tests/test_main.py`,
  `tests/test_request_limits.py`, `tests/test_rate_limits.py`

**Interfaces:**
- Consumes: FastAPI middleware boundary.
- Produces: bounded public request behavior and browser-safe headers.

- [ ] **Step 1: Write RED middleware tests**

Add tests for:

- oversized body rejection before JSON parsing;
- per-principal or per-IP rate limiting;
- CSP and security headers on `/workspace`, static assets, and API responses;
- auth-expired and rate-limited public error envelopes.

- [ ] **Step 2: Verify RED**

Run focused middleware tests and confirm current behavior lacks these controls.

- [ ] **Step 3: Implement middleware**

Add deterministic middleware with explicit limits and bounded public responses.

- [ ] **Step 4: Verify GREEN**

Run middleware tests plus focused frontend static tests if headers affect the
browser workspace.

### Task 4: Privacy-Safe Logging And Retention Policy

**Files:**
- Modify: `generic_artifact_service.py`
- Modify other logging call sites found by source audit.
- Create: `retention_policy.py`
- Create or modify tests: `tests/test_log_privacy.py`,
  `tests/test_retention_policy.py`

**Interfaces:**
- Consumes: current exception logging and lifecycle services.
- Produces: logs that contain only safe metadata and documented retention
  behavior.

- [ ] **Step 1: Write RED tests**

Add tests proving validation errors do not log artifact content, prompts,
notes, memory values, feedback text, or source text.

- [ ] **Step 2: Verify RED**

Run log privacy tests and confirm current full validation error logging fails.

- [ ] **Step 3: Implement safe logging and retention rules**

Log only operation, status, exception class, safe IDs, and bounded counters.
Document retention behavior in code and docs.

- [ ] **Step 4: Verify GREEN**

Run log privacy and retention tests.

### Task 5: Container And Cloud Run Configuration

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create or modify: deployment docs/scripts as approved.
- Modify: `README.md`, `docs/development/local-setup.md`,
  `docs/architecture.md` after deployment behavior is accepted.

**Interfaces:**
- Consumes: production settings and application startup.
- Produces: reproducible one-service Cloud Run deployment path.

- [ ] **Step 1: Write RED static/container checks**

Add focused checks for:

- no credential files copied into the image;
- Cloud Run `PORT` support;
- production command uses `0.0.0.0`;
- required env vars are documented.

- [ ] **Step 2: Verify RED**

Run focused static/container checks and confirm missing Docker configuration.

- [ ] **Step 3: Add container and deployment configuration**

Create one web-service image and deploy only the public request-bound app.

- [ ] **Step 4: Verify GREEN**

Build locally, run the container locally, and run focused HTTP checks.

### Task 6: Hosted Proof And Submission Evidence

**Files:**
- Modify: `README.md`
- Modify: `docs/current-state.md`
- Modify: `docs/architecture.md`
- Modify: `docs/submission-checklist.md`
- Create deployment evidence notes under an approved docs path.

**Interfaces:**
- Consumes: deployed Cloud Run service.
- Produces: judge-readable proof and final repository documentation.

- [ ] **Step 1: Run hosted smoke/security checks**

Verify:

- `/workspace` loads on the deployed URL;
- Google OIDC works;
- cross-owner checks deny access;
- request limits and rate limits trigger safely;
- logs exclude private content;
- Firestore/Vertex/Cloud Run proof is visible.

- [ ] **Step 2: Update docs from accepted hosted behavior**

Document exact local and hosted commands, env vars, architecture, and proof
locations without secrets.

- [ ] **Step 3: Run final documentation verification**

Run:

```bash
git diff --check
rg -n "Cloud Tasks|private worker|durable job-state" README.md docs -S -g '!docs/legacy/**'
```

Expected: remaining matches are historical or explicitly deferred.

