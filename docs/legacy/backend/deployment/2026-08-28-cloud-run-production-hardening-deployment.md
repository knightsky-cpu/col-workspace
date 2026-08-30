# Cloud Run Production Hardening And Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining Cloud Run deployment-readiness work for Agent Col by hardening the existing request-bound FastAPI application, deploying one public Cloud Run service with Google OIDC, and capturing hosted proof without adding Cloud Tasks, a private worker, durable async jobs, or broad architecture rewrites.

**Architecture:** Agent Col is already a FastAPI application with Google OIDC support, Vertex AI/Gemini configuration validation, Firestore persistence, governed memory, governed notes, working state, specialists, and request-bound artifacts. The deployment plan should therefore close perimeter and hosting gaps around the existing architecture rather than rebuild production authentication or ownership from scratch. Cloud Run should use its own runtime signals, especially `K_SERVICE` and `PORT`, while local development keeps the documented launch path on `127.0.0.1:8000`.

**Tech Stack:** Python 3.14, FastAPI, Uvicorn, Pydantic, Google GenAI SDK, Google ADK, Firestore, Vertex AI, Google Identity Services, Cloud Run, Artifact Registry, Google Cloud buildpacks or Docker, pytest, Node test runner.

**Spec:** `docs/deployment/PRODUCTION_HARDENING_CHECKLIST.md`, `docs/final-checklist-planning.md`, `docs/superpowers/plans/2026-08-28-updated-finalization-handoff.md`, current source files listed below, and current official Cloud Run / Google Identity documentation.

## Global Constraints

- Do not add Cloud Tasks, private worker execution, durable async artifact jobs, or a generalized planner before submission.
- Preserve the existing `AGENT_COL_AUTH_MODE=local_dev|google_oidc` configuration contract.
- Do not add a second generic environment-mode abstraction such as `AGENT_COL_ENVIRONMENT=production` unless later source evidence proves it is necessary.
- In Cloud Run, detected by `K_SERVICE`, fail startup unless `AGENT_COL_AUTH_MODE=google_oidc` and required Google/OAuth/Vertex configuration is present.
- Preserve the current local Google OIDC development launch command: `AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000`.
- Do not warp local development around Cloud Run's runtime port contract.
- In Cloud Run, the production entrypoint must listen on `0.0.0.0:$PORT`; Cloud Run injects `PORT` and defaults request traffic to `8080`.
- Do not set `GOOGLE_APPLICATION_CREDENTIALS` on Cloud Run; use a user-managed service account as service identity.
- Preserve existing internal identity mappings such as `google--{subject}` unless an approved ownership audit proves a migration is required.
- Trace frontend and API consumers before removing or changing `subject`, `email`, `display_name`, `user_id`, or `workspace_project_id` from public responses.
- Treat in-memory rate limiting as best-effort abuse/cost protection only: per Cloud Run instance, non-durable, and reset on instance restart.
- Use small Cloud Run max instances, ideally `1` or another deliberately small value for the hackathon deployment, if relying on in-process rate limiting.
- Every source-changing pass requires AGENTS.md approval, TDD, focused automated verification, manual verification, and checkpoint approval.

---

## Corrected Deployment-Readiness Picture

The previous draft made Agent Col look farther from deployment readiness than the source supports. Current source and tests show that production authentication and core application architecture are already substantially present.

```text
ALREADY WORKING
------------------------------
Google OIDC authentication       yes
Google ID-token verification     yes
OAuth client configuration       yes
Google-mode ownership controls   yes, foundation present
Vertex AI config validation      yes
Firestore persistence            yes
Application/schema limits        yes
FastAPI production-shaped app    yes

ACTUAL REMAINING WORK
------------------------------
Cloud Run fail-closed guard       pending
Full ownership coverage audit     pending
Public identity minimization      pending
Raw HTTP body protection          pending
Bounded rate limiting             pending
Browser security headers          pending
Production logging audit          pending
Deployment packaging choice       pending
Cloud Run service identity/IAM    pending
OAuth deployed-origin config      pending
Hosted deployment                 pending
End-to-end hosted proof           pending
Latency measurement               pending
```

This means the work is not "build production authentication and deployment architecture." The work is "close bounded Cloud Run, perimeter security, packaging, and evidence gaps around an existing application."

## Official Documentation Evidence

Current official documentation establishes:

- Cloud Run service containers must listen on `0.0.0.0` on the request port; Cloud Run injects `PORT` into the ingress container and defaults request traffic to `8080`.
  - <https://docs.cloud.google.com/run/docs/container-contract>
- Cloud Run injects `K_SERVICE`, `K_REVISION`, and `K_CONFIGURATION` for services, making `K_SERVICE` the correct runtime signal for "this process is running on Cloud Run."
  - <https://docs.cloud.google.com/run/docs/container-contract>
- Cloud Run services can deploy directly from source with buildpacks. If a `Dockerfile` is present, source deployment uses it; if no `Dockerfile` is present, Python buildpacks can build the container. Therefore, a user-authored `Dockerfile` is useful for reproducibility/control but is not a Cloud Run admission ticket.
  - <https://docs.cloud.google.com/run/docs/deploying-source-code>
  - <https://docs.cloud.google.com/docs/buildpacks/python>
- Python Cloud Run source deployments with `requirements.txt` containing FastAPI/Uvicorn can default to `uvicorn main:app --host 0.0.0.0 --port 8080`; a `Procfile` or `GOOGLE_ENTRYPOINT` can override the entrypoint.
  - <https://docs.cloud.google.com/docs/buildpacks/python>
  - <https://docs.cloud.google.com/docs/buildpacks/about-procfile>
- Cloud Run service identity should use a user-managed service account for least privilege. When Cloud Run code uses service identity to call Google Cloud APIs, do not set `GOOGLE_APPLICATION_CREDENTIALS` on the service.
  - <https://docs.cloud.google.com/run/docs/configuring/services/service-identity>
  - <https://docs.cloud.google.com/run/docs/securing/service-identity>
- Cloud Run max instances can cap cost and protect backing services, but scaling settings are not the same as distributed rate limiting.
  - <https://docs.cloud.google.com/run/docs/configuring/max-instances>
- Google ID tokens must be verified server-side for signature, audience, issuer, and expiry.
  - <https://developers.google.com/identity/gsi/web/guides/verify-google-id-token>

## Source-Backed Evidence

- `auth.py` already defines `AuthMode = Literal["local_dev", "google_oidc"]`, `AuthSettings`, and `load_auth_settings(environ)`.
- `auth.py` currently defaults missing `AGENT_COL_AUTH_MODE` to `local_dev`. This is acceptable for current local behavior but unsafe if Cloud Run starts without explicit auth mode.
- `auth.py` already verifies Google ID tokens through `google.oauth2.id_token.verify_oauth2_token(...)`.
- `auth.py` already rejects missing bearer tokens in Google mode, missing Google OAuth client ID, Google user mismatch, and Google project mismatch.
- `auth.py` currently derives internal Google user IDs as `google--{subject}`.
- `auth.py` currently exposes `subject`, `email`, and `display_name` in `AuthenticatedPrincipal.public_dict()`.
- `main.py` calls `load_dotenv()` at module import and builds the production-shaped app through a FastAPI lifespan.
- `main.py` loads strict Vertex settings in lifespan before serving app state.
- `main.py` exposes `/api/auth/config` and `/api/auth/session`.
- `main.py` already adds `Cache-Control: no-store` for `/workspace` and `/static/agent-col/*`.
- `main.py` routes already call `_resolve_effective_user_id(...)` and `_resolve_effective_project_id(...)` across many user/project-scoped surfaces.
- `vertex_config.py` already requires `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, and `GOOGLE_GENAI_USE_ENTERPRISE=True`.
- `tests/test_auth.py` already covers Google bearer-token requirement, token verifier use, Google user mismatch, Google project mismatch, secondary owned workspace IDs, and missing OAuth client ID.
- `tests/test_main.py` already covers Google auth session behavior, project artifact mismatch denial before service access, Google chat idempotency requirements, and chat message size rejection before service access.
- `frontend/auth-view.mjs`, `frontend/app.mjs`, `frontend/state.mjs`, and `frontend/api.mjs` consume `user_id` and `workspace_project_id` as application routing/context identifiers. These fields cannot be removed or renamed without a contract-aware frontend/backend pass.
- `frontend/auth-view.mjs` currently presents a generic "Signed in with Google" label rather than directly rendering Google subject to the visible UI.
- `docs/development/local-setup.md` documents local Google OIDC launch with `AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000`.
- `.gitignore` ignores `.env`.
- The current repository has no tracked `Dockerfile`, `.dockerignore`, `Procfile`, `cloudrun.yaml`, or Cloud Run deploy script.

## Discrepancies Corrected From The Previous Draft

- Previous bad assumption: add a new `AGENT_COL_ENVIRONMENT=local|production` mode. Corrected: use Cloud Run's injected `K_SERVICE` signal first and keep the existing `AGENT_COL_AUTH_MODE` contract.
- Previous bad framing: local development needs a different auth path. Corrected: local development already runs in Google OIDC with the documented terminal command; `.env` does not need to contain `AGENT_COL_AUTH_MODE` if the launch command supplies it.
- Previous overstatement: production ownership needs to be built from scratch. Corrected: Google-mode ownership controls already have a foundation; the next work is route coverage audit plus gap closure.
- Previous ordering problem: identity minimization before ownership proof. Corrected: audit and close cross-user access first; then minimize the public identity surface without breaking consumers.
- Previous risky assumption: replace internal `google--{subject}` IDs for public neatness. Corrected: preserve internal identity mapping unless source evidence proves a production risk that justifies migration.
- Previous Docker assumption: a `Dockerfile` is required for Cloud Run. Corrected: Cloud Run can deploy from source with buildpacks; Dockerfile/Procfile/buildpack entrypoint is a deliberate packaging choice.
- Previous request-limit ambiguity: schema limits and HTTP body limits were conflated. Corrected: application/schema limits already exist in places; the remaining perimeter gap is raw HTTP body rejection before JSON parsing.
- Previous rate-limit ambiguity: in-memory rate limiting was treated like production distributed enforcement. Corrected: in-process limits are per instance, non-durable, and reset on restart; use small max instances to make the behavior more predictable for the hackathon.
- Previous deployment bundling: packaging and cloud deployment were mixed. Corrected: local packaging/build proof and IAM/OAuth/Cloud Run deployment are separate failure domains and separate passes.
- Previous hosted proof was too shallow. Corrected: hosted proof must demonstrate Google sign-in -> authenticated session -> workspace -> chat -> ADK/Vertex response -> Firestore persistence -> later-session continuity.

## Pass 1: Cloud Run Fail-Closed Config Guard

**Goal:** Prevent a Cloud Run revision from serving if required deployment configuration is missing or unsafe, while preserving existing local development behavior.

**Files:**
- Modify: `auth.py`
- Possibly modify: `main.py` if startup validation belongs beside lifespan construction
- Test: `tests/test_auth.py`
- Possibly test: `tests/test_main.py`

**Interfaces:**
- Consumes: `load_auth_settings(environ)`
- Produces: Cloud Run-aware auth/config validation without adding a competing environment mode

- [ ] Write RED tests showing that `load_auth_settings({"K_SERVICE": "agent-col"})` rejects missing `AGENT_COL_AUTH_MODE`.
- [ ] Write RED tests showing that `load_auth_settings({"K_SERVICE": "agent-col", "AGENT_COL_AUTH_MODE": "local_dev"})` rejects local-dev auth in Cloud Run.
- [ ] Write RED tests showing that Cloud Run with `AGENT_COL_AUTH_MODE=google_oidc` rejects missing or blank `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_CLIENT_ID`.
- [ ] Write GREEN implementation that detects Cloud Run with `K_SERVICE` and requires existing `AGENT_COL_AUTH_MODE=google_oidc`.
- [ ] Preserve local behavior: absent `K_SERVICE`, absent `AGENT_COL_AUTH_MODE` still follows the current local default unless separately approved for change.
- [ ] Preserve local Google OIDC launch: `AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000`.
- [ ] Run focused auth tests.
- [ ] Manual check: local Google OIDC startup still reaches `/workspace`.
- [ ] Manual check: simulated Cloud Run env with unsafe auth config fails before serving traffic.

**Important exclusion:** Do not introduce `AGENT_COL_ENVIRONMENT` in this pass.

## Pass 2: Ownership Audit And Gap Closure

**Goal:** Prove cross-user data boundaries across all public user/project-scoped routes, then patch only missing ownership checks.

**Files:**
- Inspect: `main.py`
- Inspect: `auth.py`
- Inspect: `database.py`
- Inspect: `tests/test_auth.py`
- Inspect/modify tests: `tests/test_main.py`, focused database tests if needed
- Modify source only if a route coverage gap is proven

**Interfaces:**
- Consumes: `_resolve_effective_user_id(...)`, `_resolve_effective_project_id(...)`, `Authenticator.resolve_user_id(...)`, `Authenticator.resolve_project_id(...)`
- Produces: route-by-route evidence that another Google user cannot read or mutate workspace, chat, note, memory, artifact, or feedback data

- [ ] Create a route inventory table for every public route that accepts `user_id`, `project_id`, workspace ID, session ID, note ID, memory signal ID, artifact ID, or feedback ID.
- [ ] Map each route to its ownership guard: user guard, project guard, database ownership check, service ownership check, or currently unguarded.
- [ ] Write RED tests only for confirmed missing or weak boundaries.
- [ ] Implement the smallest source patch for each confirmed gap.
- [ ] Preserve existing hash-derived workspace IDs and accepted secondary workspace prefix behavior unless the audit proves the model is unsafe.
- [ ] Run focused ownership tests.
- [ ] Manual check: account A cannot read or mutate account B workspace, chat sessions, notes, memory, artifacts, or feedback.

**Why this comes before identity cleanup:** Broken authorization leaks data. Raw identifier exposure is also worth fixing, but it is lower risk than cross-user access.

## Pass 3: Public Identity Surface Minimization

**Goal:** Minimize public identity exposure without breaking existing frontend/session contracts or migrating persisted internal IDs.

**Files:**
- Inspect/modify: `auth.py`
- Inspect/modify: `main.py`
- Inspect/modify only if needed: `frontend/auth-view.mjs`, `frontend/app.mjs`, `frontend/state.mjs`, `frontend/api.mjs`
- Test: `tests/test_auth.py`, `tests/test_main.py`, `tests/frontend/auth-view.test.mjs`, `tests/frontend/api.test.mjs`, `tests/frontend/state.test.mjs`

**Interfaces:**
- Consumes: `AuthenticatedPrincipal.public_dict()`, `/api/auth/config`, `/api/auth/session`, `googleSessionToContext(...)`
- Produces: a production-safe public session contract

- [ ] Trace current consumers of `subject`, `email`, `display_name`, `user_id`, and `workspace_project_id`.
- [ ] Decide which fields are required public routing data and which are display-only.
- [ ] Write RED tests for production session responses omitting raw Google `subject`.
- [ ] Write RED tests for the frontend continuing to enter workspace with whatever public identifiers remain.
- [ ] Preserve internal `google--{subject}` and persisted records unless the ownership audit proves migration is necessary.
- [ ] Prefer stable opaque public IDs only if they can be introduced without destabilizing route ownership and existing persisted data.
- [ ] Run focused auth/session/frontend tests.
- [ ] Manual check: Google sign-in still enters the private workspace; visible UI does not display raw Google subject.

## Pass 4: Raw HTTP Body Limits, Best-Effort Rate Limiting, And Security Headers

**Goal:** Add perimeter protection at the HTTP layer without confusing it with existing schema limits.

**Files:**
- Modify: `main.py`
- Optionally create: `request_limits.py`
- Optionally create: `rate_limits.py`
- Optionally create: `security_headers.py`
- Test: `tests/test_main.py` or focused middleware tests

**Interfaces:**
- Consumes: ASGI request boundary, request headers, authenticated principal if safely available
- Produces: bounded body size, best-effort abuse/cost throttling, and browser security headers

- [ ] Preserve existing schema/input limits, including chat message `maxlength=10000` and backend 10,000-character validation.
- [ ] Write RED tests showing an oversized raw request body is rejected before JSON parsing/service access.
- [ ] Write RED tests showing normal request bodies still pass to routes.
- [ ] Write RED tests for rate limiting repeated requests by principal when authenticated, or by client IP when unauthenticated.
- [ ] Document in test names or comments that the in-memory limiter is per Cloud Run instance, non-durable, and reset on restart.
- [ ] Write RED tests for CSP, frame, MIME sniffing, referrer, permissions, and transport security headers.
- [ ] Ensure CSP remains compatible with Google Identity Services script loading from `https://accounts.google.com/gsi/client`.
- [ ] Implement minimal middleware.
- [ ] Run focused middleware tests.
- [ ] Manual check: `/workspace`, Google sign-in, chat, notes, memory, artifacts, and static assets still work.

## Pass 5: Production Logging Privacy Audit

**Goal:** Ensure production logs contain safe metadata rather than prompts, memory, notes, source text, artifacts, feedback, or full validation content.

**Files:**
- Inspect: all Python files with `logger.debug`, `logger.info`, `logger.warning`, `logger.error`, `logger.exception`, or `logger.critical`
- Known likely modify: `generic_artifact_service.py`
- Modify other source only if audit proves content-bearing logs
- Test: `tests/test_log_privacy.py` or focused existing tests

**Interfaces:**
- Consumes: exception/logging call sites
- Produces: privacy-safe log behavior

- [ ] Inventory logging call sites with `rg`.
- [ ] Classify each log as safe metadata, content-bearing, or uncertain.
- [ ] Write RED canary tests for any confirmed content-bearing logs.
- [ ] Replace content-bearing validation/log details with exception class, operation, status, safe IDs, counts, and timing where relevant.
- [ ] Preserve useful operational logs that already avoid private content.
- [ ] Run focused log privacy tests.
- [ ] Manual check after deployment: trigger controlled validation failures and inspect Cloud Logging for absence of prompt, memory, note, source, artifact, and feedback text.

## Pass 6: Deployment Packaging Choice

**Goal:** Produce a reproducible Cloud Run startup path, choosing either source deploy with buildpacks or an explicit Dockerfile based on evidence.

**Files:**
- Option A create: `Procfile` or documented `GOOGLE_ENTRYPOINT`
- Option B create: `Dockerfile`
- Create: `.dockerignore` if using Docker or source upload exclusions require it
- Possibly create: `scripts/deploy-cloud-run.sh`
- Test: static packaging tests or build/smoke checks

**Interfaces:**
- Consumes: FastAPI `main:app`, `requirements.txt`, Cloud Run `PORT`
- Produces: a deployable service command that binds `0.0.0.0:$PORT`

- [ ] Decide packaging path explicitly:
  - Source deploy/buildpack path: no user-authored Dockerfile required; verify buildpack entrypoint or set `Procfile` / `GOOGLE_ENTRYPOINT`.
  - Dockerfile path: user-authored image for reproducibility and local container smoke proof.
- [ ] Do not describe Dockerfile as required by Cloud Run.
- [ ] Ensure production entrypoint is Uvicorn `main:app` without `--reload`, binding `0.0.0.0` and `${PORT:-8080}` or buildpack equivalent.
- [ ] Ensure local development remains `127.0.0.1:8000` with `--reload`.
- [ ] Exclude `.env`, credentials, `.git`, `venv`, caches, screenshots, local evidence, and generated private data from uploaded/build context.
- [ ] Verify packaging with the focused command for the chosen path.
- [ ] Manual check: production-shaped local run or local container returns `{"status":"online"}` from `/`.

## Pass 7: IAM, Service Identity, OAuth, And Cloud Run Deployment

**Goal:** Create or configure the Google Cloud resources needed to run the existing application on one public Cloud Run service.

**Files:**
- Documentation/scripts only unless source gaps are discovered
- Expected Google Cloud resources: Cloud Run service, service account, Artifact Registry repository if needed, OAuth web client, Firestore Native database, enabled Vertex AI/API services

**Interfaces:**
- Consumes: Google Cloud project, region, OAuth client, deployer credentials
- Produces: deployed public Cloud Run service using application-level Google OIDC

- [ ] Confirm target project, region, billing, Firestore Native database, Vertex AI API, Firestore API, Cloud Run API, Artifact Registry API, and Cloud Build API as needed.
- [ ] Create/select a user-managed Cloud Run service account.
- [ ] Grant least-privilege access needed for Firestore and Vertex AI.
- [ ] Do not configure `GOOGLE_APPLICATION_CREDENTIALS` on Cloud Run.
- [ ] Deploy public Cloud Run service with required environment variables:
  - `AGENT_COL_AUTH_MODE=google_oidc`
  - `GOOGLE_OAUTH_CLIENT_ID=<public-web-client-id>`
  - `GOOGLE_CLOUD_PROJECT=<project-id>`
  - `GOOGLE_CLOUD_LOCATION=global`
  - `GOOGLE_GENAI_USE_ENTERPRISE=True`
- [ ] Configure small max instances, preferably `1` for the hackathon proof if acceptable, or another deliberately small value.
- [ ] Configure timeout and concurrency deliberately for request-bound chat behavior.
- [ ] Add the Cloud Run URL to Google OAuth authorized JavaScript origins.
- [ ] Verify `/`, `/workspace`, `/api/auth/config`, and `/api/auth/session`.
- [ ] Manual check: Google sign-in works from the deployed Cloud Run origin.

## Pass 8: Hosted Functional And Security Proof

**Goal:** Prove the deployed application exercises the whole Google-backed Collaborative Partner path, not just a shallow dashboard or health endpoint.

**Files:**
- Create/modify: approved docs evidence file after hosted behavior is accepted
- Possibly create: hosted smoke script if it avoids private content
- Test: live smoke/security checks

**Interfaces:**
- Consumes: deployed Cloud Run URL and safe test account/session
- Produces: judge-safe proof of hosted behavior

- [ ] Verify hosted health endpoint.
- [ ] Verify hosted `/workspace` loads.
- [ ] Verify Google Sign-In from the Cloud Run origin.
- [ ] Verify authenticated `/api/auth/session` returns a usable app session.
- [ ] Create or select a workspace.
- [ ] Send a demo-safe chat prompt.
- [ ] Prove the chat path reaches ADK/Vertex and returns an Agent Col response.
- [ ] Prove Firestore persistence by closing or starting a later session and retrieving prior context/continuity.
- [ ] Prove ownership denial with another Google account if available.
- [ ] Verify request-body limit and best-effort rate-limit behavior.
- [ ] Verify security headers on `/workspace`, static assets, and API responses.
- [ ] Inspect Cloud Logging for absence of prompt, memory, note, source, artifact, and feedback content.
- [ ] Capture Cloud Run, Firestore, Vertex AI, and application evidence without secrets or private user content.

## Pass 9: Latency Measurement Before Optimization

**Goal:** Measure local and hosted request latency before choosing any optimization work.

**Files:**
- Prefer create: `latency_measurement.py` or `request_timing.py`
- Modify: `main.py` only if optional/content-safe timing middleware is approved
- Test: focused timing/log-safety tests

**Interfaces:**
- Consumes: `/api/chat` lifecycle
- Produces: content-safe timing evidence

- [ ] Write RED tests proving timing output includes phase names but no prompt, response, memory, note, source, artifact, or feedback text.
- [ ] Measure request validation, auth/session resolution, Firestore turn claim, memory/profile loading, routing, expert execution, responder generation, working-state update, preference-learning capture, Firestore persistence, and response serialization where source seams allow.
- [ ] Measure client-observed latency from submit click to first completed response render.
- [ ] Keep measurement optional or production-safe.
- [ ] Run one local demo-sized prompt and record timings.
- [ ] Run the same prompt on Cloud Run and compare timings.
- [ ] Only propose optimization after evidence identifies the bottleneck.

## Recommended First Implementation Pass

Start with **Pass 1: Cloud Run Fail-Closed Config Guard** only.

That pass should be genuinely small:

```text
Cloud Run detected with K_SERVICE
-> require existing AGENT_COL_AUTH_MODE=google_oidc
-> require OAuth client ID
-> rely on existing Vertex validation for Google Cloud/Vertex config
-> unsafe config fails before serving traffic
```

This protects deployment without changing the local Google OIDC development path and without introducing a duplicate environment abstraction.

##Potential conflicts:

Yes. Most of the dragons are dead, but there are still a few Cloud Run-specific goblins I would expect. None look like architectural blockers.

The ones I’d put red circles around are:

1. Cloud Run IAM auth vs Agent Col’s Google OIDC. Your Cloud Run service itself should be publicly invokable while Agent Col enforces user authentication inside FastAPI. If you accidentally require Cloud Run IAM authentication, a normal browser Google ID token is not the same thing as Cloud Run invocation authorization, and judges/users may hit a Google 403 before Agent Col ever sees the request. Your intended architecture is:

Internet → public Cloud Run endpoint → Agent Col Google OIDC → protected user data

    not:

Internet → Cloud Run IAM gate → Agent Col OIDC

2. The first deployed URL will break Google Sign-In until you authorize its origin. Localhost already works because it is registered. Once Cloud Run gives you something like https://agent-col-....run.app, add that exact scheme + hostname to the OAuth Web Client’s Authorized JavaScript Origins. Google explicitly requires the site origin there.  Expect the first deployment to load fine while login complains about the origin; that is a configuration issue, not an Agent Col bug.
3. --set-env-vars is a nasty little goblin. On Cloud Run, gcloud run deploy --set-env-vars ... replaces previously configured environment variables that aren’t included in that invocation. Google documents this as destructive.  So this:

gcloud run deploy ... --set-env-vars AGENT_COL_AUTH_MODE=google_oidc

    can unintentionally erase other env vars from the previous revision. For incremental changes, prefer --update-env-vars, or maintain the complete production configuration deterministically.
4. Source-upload leakage if you choose --source. .dockerignore protects Docker build context, but gcloud run deploy --source . uses .gcloudignore for source upload. If .gcloudignore is absent, gcloud normally derives rules from the repository .gitignore, which helps because your .env is already ignored.  Still, before the first deployment I would explicitly inspect:

gcloud meta list-files-for-upload

    and make damn sure .env, screenshots, credentials, caches, and local evidence aren’t on the wagon headed to Google.
5. Cloud Run’s default concurrency is much higher than “one request at a time.” A new CLI-deployed service can default to concurrency based on CPU, commonly effectively around 80 concurrent requests per instance. Google actually recommends starting lower, around 8, when you’re unsure about application concurrency behavior.  I would not deploy Agent Col at 80 and discover a shared-state gremlin during judging. Start deliberately conservative, verify concurrent chat/session behavior, then increase if necessary.
6. Don’t blindly set concurrency to 1 either. That sounds safest, but it can force Cloud Run to create more instances under simultaneous traffic and amplify cold starts.  Something like a deliberately small concurrency is probably the saner hackathon starting point. Measure it rather than treating 1 as magically correct.
7. Cold starts can look like Agent Col latency. Cloud Run scales to zero by default, so the first request after idleness may include container startup. Google specifically recommends minimum instances or startup CPU boost when cold-start latency matters.  For the demo, you have two choices:

min instances = 0 → cheapest, occasional cold start
min instances = 1 → warmer demo, small ongoing cost

    I would decide intentionally before recording the demo rather than diagnosing a mysterious slow first response five minutes before submission.
8. Don’t make the health check summon Gemini. A health/startup endpoint should answer, essentially, “the FastAPI process is alive and correctly initialized.” It should not perform a Vertex generation or expensive Firestore operation. Cloud Run supports startup/liveness/readiness probes, and a failing startup probe prevents the instance from serving traffic.  Keep the probe cheap:

process running?
config loaded?
app initialized?
→ healthy

    Then your hosted smoke tests separately prove Firestore and Vertex.
9. Request timeout and model timeout are different. Cloud Run currently defaults to a 300-second request timeout. If that expires, the client gets a 504, but Google warns that the container’s code may continue processing afterward.  Your internal Gemini/turn timeouts should therefore remain shorter than the Cloud Run request timeout so Agent Col aborts cleanly first:

model/service timeout
      <
application turn timeout
      <
Cloud Run request timeout

    You don’t want the browser giving up while the wizard is still burning Vertex tokens underground.
10. Firestore geography may become visible as latency. Firestore recommends locating compute near the database and notes that the database location cannot later be changed.  Before choosing the Cloud Run region, check where the existing Firestore database lives. Don’t casually deploy Agent Col across the continent from its database because us-whatever sounded fine. This is one I would check before creating the Cloud Run service.

A couple more small ones: keep max-instances intentionally bounded so a traffic spike cannot spawn a small army of Gemini-spending clones—Google explicitly positions maximum instances as both cost and abnormal-traffic protection.  And use the dedicated Cloud Run service account rather than the broad default compute identity; that’s where your least-privilege Firestore/Vertex access belongs.

What I would expect the first deployment experience to look like

Probably something like:

Deploy
  ↓
container/start command issue?       maybe
  ↓
service becomes healthy
  ↓
/workspace loads                     likely
  ↓
Google Sign-In origin complaint      very plausible
  ↓
authorize Cloud Run origin
  ↓
login works
  ↓
first Vertex/Firestore call
  ↓
missing IAM role?                    plausible
  ↓
fix service-account role
  ↓
chat works
  ↓
discover cold-start/concurrency UX
  ↓
tune
  ↓
hosted proof

That’s normal deployment debugging, not evidence the architecture was wrong.

The three goblins I would be most alert for are OAuth origin configuration, Cloud Run service-account permissions, and concurrency/cold-start behavior. Everything else is mostly deterministic plumbing.

And before the first actual deployment command, I would have Codex produce a “first deployment preflight” containing the exact project, region, Firestore location, service account, IAM roles, environment-variable names, OAuth client, concurrency/max-instance settings, and files that will be uploaded. That gives you one final dungeon map before pulling the lever.
