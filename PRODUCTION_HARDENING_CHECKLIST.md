# Agent Col Production Hardening Checklist

Status: approved for creation.

This checklist controls the next deployment-focused phase for Agent Col. Target A
and Target B are considered demo-ready; remaining pre-submission priority is
single-service production hardening, Cloud Run deployment proof, and targeted
latency measurement without broad refactoring.

## Scope

- Harden the existing request-bound FastAPI application for one public Cloud Run service.
- Require Google OIDC for production access.
- Preserve Firestore as durable truth and Vertex AI/Gemini as the model backend.
- Preserve the responder-only Agent Col architecture and existing governed memory, notes, working-state, specialist, and artifact boundaries.
- Defer Cloud Tasks, private worker execution, durable async artifact jobs, and generalized planner work.

## Approval And Checkpoint Rules

- Every source-changing pass requires a bounded plan, explicit approval, TDD, focused automated verification, and manual verification.
- Do not checkpoint unaccepted source changes.
- After manual acceptance, checkpoint directly to `origin/main` with explicit path staging.
- Documentation-only updates may be checkpointed after user approval.

## 1. Production Configuration Gate

- [ ] Add explicit production environment mode.
- [ ] Fail closed when production-required environment variables are missing.
- [ ] Reject `local_dev` auth mode in production.
- [ ] Require `google_oidc` in production.
- [ ] Reject placeholder project, origin, OAuth, or deployment values.
- [ ] Preserve existing local startup behavior for `local_dev` and local `google_oidc`.

Focused verification:
- [ ] Auth/settings tests prove unsafe production startup fails.
- [ ] Local-mode regression test proves local development still starts.

Manual verification:
- [ ] Confirm local development still works at `/workspace`.
- [ ] Confirm intentionally incomplete production env fails before serving traffic.

## 2. Production Identity And Ownership

- [ ] Derive production-safe opaque user identifiers from verified Google identity.
- [ ] Do not expose raw Google subject identifiers in public responses.
- [ ] Establish canonical workspace ownership records.
- [ ] Deny cross-owner workspace, chat, note, memory, artifact, and feedback access.
- [ ] Return bounded public errors for ownership failures.
- [ ] Preserve local-development identity behavior outside production.

Focused verification:
- [ ] Auth tests for opaque identity.
- [ ] API tests for cross-owner denial.
- [ ] Database/service tests for owner record enforcement.

Manual verification:
- [ ] Sign in as one Google account and create/use a workspace.
- [ ] Attempt access with a second account and confirm denial without private details.

## 3. Request Limits, Rate Limits, And Browser Security Headers

- [ ] Enforce total request-body size limits before JSON parsing.
- [ ] Add bounded per-principal or per-IP rate limiting.
- [ ] Add production CSP.
- [ ] Add frame, MIME sniffing, referrer, permissions, and transport security headers.
- [ ] Preserve same-origin browser API behavior.
- [ ] Keep public error responses bounded and content-safe.

Focused verification:
- [ ] Middleware tests for oversized body rejection.
- [ ] Rate-limit tests for repeated requests.
- [ ] Header tests for `/workspace`, static assets, and API responses.

Manual verification:
- [ ] Load `/workspace` successfully with production headers.
- [ ] Confirm normal chat still works after headers are enabled.
- [ ] Confirm rate-limit failures are understandable and safe.

## 4. Privacy-Safe Logging

- [ ] Audit logging call sites that can include prompt, memory, note, source, artifact, or feedback content.
- [ ] Remove content-bearing validation error strings from logs.
- [ ] Log only safe metadata: operation, status, exception class, safe IDs, counts, and timing.
- [ ] Add log canary tests for rejected private content.
- [ ] Document what production logs may contain.

Focused verification:
- [ ] Log privacy tests prove private content is absent from captured logs.
- [ ] Existing failure-path tests still pass.

Manual verification:
- [ ] Trigger a controlled validation failure.
- [ ] Inspect Cloud Logging and confirm no prompt, memory, note, artifact, or source text appears.

## 5. Retention And Deletion Policy

- [ ] Define production retention behavior for users, workspaces, sessions, messages, turns, memory, notes, artifacts, feedback, and activity receipts.
- [ ] Confirm existing hard-delete and revoke/delete semantics are documented accurately.
- [ ] Identify any data surfaces that need future retention automation.
- [ ] Avoid adding background deletion infrastructure before submission unless explicitly approved.

Focused verification:
- [ ] Policy/static tests verify documented surfaces are listed.
- [ ] Existing memory, note, and artifact deletion tests still pass.

Manual verification:
- [ ] Exercise memory revoke/delete, note delete/archive, and artifact archive/restore paths.
- [ ] Confirm UI language matches actual retained or deleted data.

## 6. Container And Cloud Run Configuration

- [ ] Add `Dockerfile`.
- [ ] Add `.dockerignore`.
- [ ] Support Cloud Run `PORT`.
- [ ] Use a production startup command binding to `0.0.0.0`.
- [ ] Pin or document the production Python runtime.
- [ ] Document required Cloud Run environment variables without secrets.
- [ ] Configure maximum instances, timeout, and cost controls.
- [ ] Use least-privilege service account permissions for Firestore and Vertex AI.

Focused verification:
- [ ] Static checks prove credentials and virtual environments are not copied.
- [ ] Local container build succeeds.
- [ ] Local container health check returns `{"status":"online"}`.

Manual verification:
- [ ] Deploy one public Cloud Run service.
- [ ] Confirm `/workspace` loads on the Cloud Run URL.
- [ ] Confirm Google OIDC sign-in works on the deployed origin.
- [ ] Confirm chat can reach Firestore and Vertex AI through the service account.

## 7. Hosted Smoke And Security Proof

- [ ] Run hosted health check.
- [ ] Run hosted retry-safe chat smoke check.
- [ ] Run hosted auth/session check.
- [ ] Run hosted ownership denial check.
- [ ] Run hosted request-limit and rate-limit checks.
- [ ] Capture Cloud Run, Firestore, Vertex AI, and log evidence for the submission package.
- [ ] Preserve evidence without secrets or private user content.

Focused verification:
- [ ] Hosted smoke command exits successfully.
- [ ] Security checks produce expected denial or bounded failure responses.

Manual verification:
- [ ] Open the hosted app and complete the demo-critical flow.
- [ ] Confirm submitted video can show backend running on Google Cloud.

## 8. Latency Measurement Without Broad Refactoring

Goal: identify user-prompt-to-model-response bottlenecks before choosing any optimization work.

- [ ] Add or run a measurement pass before refactoring.
- [ ] Measure server-side timing for request validation, auth/session resolution, Firestore turn claim, memory/profile loading, routing, expert execution, responder generation, working-state update, preference-learning capture, Firestore persistence, and response serialization.
- [ ] Measure client-observed latency from submit click to first completed response render.
- [ ] Keep measurements content-safe; do not log prompt, response, memory, note, source, or artifact text.
- [ ] Prefer temporary/local diagnostic output first if it avoids production behavior changes.
- [ ] Only optimize after the bottleneck is measured.
- [ ] Avoid broad architecture refactors before submission unless measurement proves they are necessary.

Focused verification:
- [ ] Timing tests or smoke output show named phases with durations.
- [ ] Logs remain privacy-safe.
- [ ] Existing chat behavior remains unchanged.

Manual verification:
- [ ] Send a normal demo-sized prompt locally and record phase timings.
- [ ] Send the same prompt on Cloud Run and compare phase timings.
- [ ] Decide whether latency is dominated by model routing, responder generation, Firestore, working-state update, or network/container overhead.

## 9. Documentation And Submission Updates

- [ ] Update README with production startup and Cloud Run deployment commands.
- [ ] Update current-state after production hardening is accepted.
- [ ] Update architecture with only deployed components actually used.
- [ ] Update submission checklist with completed hardening evidence.
- [ ] Record hosted smoke/security evidence in an approved docs path.
- [ ] Confirm no secrets, credential files, virtual environments, or generated private data are tracked.

Focused verification:
- [ ] `git diff --check`
- [ ] Search docs for stale claims that make Cloud Tasks/private worker appear pre-submission required.
- [ ] Confirm deployment docs contain no secrets.

Manual verification:
- [ ] Fresh reader can follow setup/deployment docs.
- [ ] Demo runbook maps to the accepted hosted behavior.

## 10. Freeze Criteria

- [ ] Target A and Target B remain demo-ready.
- [ ] Production config fails closed.
- [ ] Google OIDC works on Cloud Run.
- [ ] Ownership denial is proven.
- [ ] Request limits, rate limits, and headers are active.
- [ ] Logs are privacy-safe.
- [ ] Hosted smoke checks pass.
- [ ] Latency bottlenecks are measured and any accepted low-risk improvements are complete.
- [ ] README, architecture, submission checklist, and evidence docs are current.
- [ ] Four-minute demo can be recorded without relying on deferred async worker behavior.
