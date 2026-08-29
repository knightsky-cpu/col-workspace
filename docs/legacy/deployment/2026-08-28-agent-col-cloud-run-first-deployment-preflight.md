# Agent Col Cloud Run First Deployment Preflight

Date: 2026-08-28

Purpose: record the exact deployment-critical state for the first Agent Col Cloud Run deployment attempt. This is a preflight document only. It does not implement source changes, create Google Cloud resources, deploy a service, or change local configuration.

Selected submission deployment path:

```text
Dockerfile
-> build Agent Col container image
-> push image to Artifact Registry
-> deploy that image to Cloud Run
```

Do not use `gcloud run deploy --source` or Google Buildpacks for the submission deployment. Source deployment remains an unselected alternative for future work.

## Verification Scope

### Source and repo checks

- `git status --short --branch`
- `rg` scan for deployment/auth/runtime variables and Cloud Run references
- `docs/development/local-setup.md`
- `docs/superpowers/plans/2026-08-28-cloud-run-production-hardening-deployment.md`
- `auth.py`
- `main.py`
- `vertex_config.py`
- `requirements.txt`
- `.gitignore`
- tracked deployment-file inventory for `Dockerfile`, `.dockerignore`, `.gcloudignore`, `Procfile`, `cloudrun.yaml`, `service.yaml`, and `app.yaml`
- `gcloud meta list-files-for-upload`

### Live Google Cloud checks

- `gcloud config list --format=json`
- `gcloud firestore databases describe --database="(default)" --project=project-e1e2a890-4566-48a8-a32 --format=json`
- `gcloud services list --enabled --project=project-e1e2a890-4566-48a8-a32 --filter="config.name:(run.googleapis.com OR cloudbuild.googleapis.com OR artifactregistry.googleapis.com OR firestore.googleapis.com OR aiplatform.googleapis.com OR logging.googleapis.com OR cloudresourcemanager.googleapis.com OR serviceusage.googleapis.com)" --format="value(config.name)"`
- `gcloud run services list --project=project-e1e2a890-4566-48a8-a32 --platform=managed --format=json`
- `gcloud iam service-accounts list --project=project-e1e2a890-4566-48a8-a32 --format=json`
- `gcloud projects get-iam-policy project-e1e2a890-4566-48a8-a32 --flatten="bindings[].members" --filter="bindings.members:ritroy16@gmail.com" --format=json`
- `gcloud projects get-iam-policy project-e1e2a890-4566-48a8-a32 --flatten="bindings[].members" --filter="bindings.members:serviceAccount" --format=json`
- `gcloud billing projects describe project-e1e2a890-4566-48a8-a32 --format=json`
- `gcloud resource-manager org-policies list --project=project-e1e2a890-4566-48a8-a32 --format=json`
- `gcloud org-policies describe constraints/run.managed.requireInvokerIam --project=project-e1e2a890-4566-48a8-a32 --format=json`
- `gcloud org-policies describe constraints/iam.allowedPolicyMemberDomains --project=project-e1e2a890-4566-48a8-a32 --format=json`

### Official documentation checked

- Cloud Run container runtime contract: <https://docs.cloud.google.com/run/docs/container-contract>
- Cloud Run deploy container images: <https://docs.cloud.google.com/run/docs/deploying>
- Cloud Run deploy from source code: <https://docs.cloud.google.com/run/docs/deploying-source-code>
- Cloud Run service identity: <https://docs.cloud.google.com/run/docs/configuring/services/service-identity>
- Cloud Run build service account for source deploy: <https://docs.cloud.google.com/run/docs/configuring/services/build-service-account>
- Cloud Run IAM roles: <https://docs.cloud.google.com/run/docs/reference/iam/roles>
- Cloud Run access control: <https://docs.cloud.google.com/run/docs/securing/managing-access>
- Cloud Run security overview: <https://docs.cloud.google.com/run/docs/securing/security>
- `gcloud run deploy`: <https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy>
- `.gcloudignore`: <https://docs.cloud.google.com/sdk/gcloud/reference/topic/gcloudignore>
- Google Identity Services OAuth client ID setup: <https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid>
- Google ID token verification: <https://developers.google.com/identity/gsi/web/guides/verify-google-id-token>
- Firestore locations: <https://firebase.google.com/docs/firestore/locations>
- Firestore best practices: <https://docs.cloud.google.com/firestore/native/docs/best-practices>

## Executive Status

First deployment attempt status: **no-go today until the items below are resolved.**

This no-go status is not evidence that Agent Col lacks production authentication or core architecture. Current source already has Google OIDC mode, Google ID-token verification, Firestore persistence, Vertex AI configuration validation, request-bound FastAPI startup, and a cheap health endpoint. The remaining blockers are deployment infrastructure, least-privilege runtime identity, packaging/upload hygiene, and the first Cloud Run hardening pass.

Current blockers for the selected Dockerfile/image deployment path:

- Cloud Run Admin API is disabled.
- Artifact Registry API is disabled.
- No dedicated Agent Col Cloud Run runtime service account is selected or created. Cloud Run can technically deploy with a default identity, but that violates the least-privilege deployment contract for this project.
- Public Cloud Run invocation policy is not fully proven because the newer Org Policy API is disabled; the older resource-manager policy list returned no project policies, but that does not prove inherited org/folder policy state.
- No tracked `Dockerfile` exists yet.
- No tracked `.dockerignore` exists yet.
- No tracked `.gcloudignore` exists yet; this matters if any source upload command is used later.
- `gcloud meta list-files-for-upload` currently includes `.agents/`, `.pytest_cache/`, and screenshot evidence. It excludes `.env`, which is the critical security win, but the upload set is still too noisy for deployment.
- Current source does not yet fail closed on Cloud Run when `K_SERVICE` is present and `AGENT_COL_AUTH_MODE` is missing or unsafe.

Conditional blockers only if the unselected source deployment path is revived:

- Cloud Build API is disabled.
- Source deploy would need a build service account and `roles/run.builder` as documented by Cloud Run source deployment docs.

## Google Cloud Project And Cloud Run Region

### Verified Current State

- Active gcloud account: `ritroy16@gmail.com`.
- Active gcloud project: `project-e1e2a890-4566-48a8-a32`.
- Billing is enabled for `project-e1e2a890-4566-48a8-a32`.
- Firestore default database is in `us-east4`.
- No Cloud Run service inventory could be read because `run.googleapis.com` is disabled.

### Required Configuration

- Use project `project-e1e2a890-4566-48a8-a32` unless the user explicitly chooses a different deployment project.
- Choose a Cloud Run region near Firestore `us-east4`.
- For the first attempt, prefer `us-east4` if Cloud Run and Artifact Registry support the selected service configuration there. If not, choose the closest supported region after checking official region support.

### Unresolved Decision

- Final Cloud Run region is not selected yet.
- Candidate should start with `us-east4` because the Firestore database is already there.

### Failure Risk

- Deploying far from Firestore can add visible latency to chat, memory, notes, artifact persistence, and continuity retrieval.
- Changing Firestore location is not an option for this database; Firestore location is immutable after creation.

## Firestore Database Location And Region Proximity

### Verified Current State

- Database name: `projects/project-e1e2a890-4566-48a8-a32/databases/(default)`.
- Type: `FIRESTORE_NATIVE`.
- Location: `us-east4`.
- Edition: `STANDARD`.
- Free tier: `true`.
- Created: `2026-08-19T14:02:38.208641Z`.

### Required Configuration

- Deploy Cloud Run as close to `us-east4` as practical.
- Runtime service account needs Firestore permissions for Agent Col's database operations.

### Unresolved Decision

- Exact least-privilege Firestore role still needs to be selected. For the first hackathon deployment, `roles/datastore.user` is the likely project-level role for application reads/writes unless narrower custom permissions are created and tested.

### Failure Risk

- Missing Firestore permissions will show up after successful login, typically on workspace, chat session, memory, notes, artifact, or continuity operations.
- Wrong region choice can make first-response latency look like an application performance issue.

## Cloud Run Service Account And IAM Roles

### Verified Current State

The deployment has three different identities to account for:

```text
Deployer identity
  -> creates/updates Cloud Run service
  -> attaches runtime service account
  -> pushes or references container image

Runtime service account
  -> identity used by the running Agent Col container
  -> calls Firestore and Vertex AI

Build service account
  -> only relevant for source deployment or Cloud Build image builds
  -> not required by Cloud Run itself when deploying an already-built image
```

- Deployer identity: `ritroy16@gmail.com`.
- Deployer project IAM roles observed:
  - `roles/owner`
  - `roles/aiplatform.user`
- Existing service accounts:
  - `994154906699-compute@developer.gserviceaccount.com`
  - `firebase-adminsdk-fbsvc@project-e1e2a890-4566-48a8-a32.iam.gserviceaccount.com`
- No dedicated Agent Col runtime service account was found.
- No existing `roles/run.builder` binding was observed for the Compute Engine default service account in the checked IAM output.

### Required Configuration

For the selected Dockerfile/image path:

- Create or select a dedicated runtime service account, for example:
  - `agent-col-cloud-run@project-e1e2a890-4566-48a8-a32.iam.gserviceaccount.com`
- Grant the deployer `roles/iam.serviceAccountUser` on the runtime service account, or equivalent `iam.serviceAccounts.actAs`.
- Grant the runtime service account the minimum permissions Agent Col needs:
  - Firestore read/write access, likely `roles/datastore.user` for the first bounded deployment.
  - Vertex AI model invocation access, likely `roles/aiplatform.user` for the first bounded deployment.
- Deploy Cloud Run with `--service-account` set to the dedicated runtime identity.

For image build/push:

- A local Docker build plus Docker push to Artifact Registry uses the deployer/local credential path and Artifact Registry permissions.
- If Cloud Build is later used to build the Dockerfile, then Cloud Build API and build service-account permissions become required for that build step.

### Unresolved Decision

- Final runtime service account name.
- Exact IAM roles for Firestore and Vertex AI.
- Whether image build happens locally with Docker or through Cloud Build using the explicit Dockerfile.

### Failure Risk

- Missing `iam.serviceAccounts.actAs` can prevent attaching the runtime service account to the Cloud Run revision.
- Missing runtime Firestore or Vertex AI permissions can make the app deploy and load but fail on first real chat or persistence call.
- Using the default compute identity would likely work only if it has enough permissions, but it weakens least privilege and violates the project deployment contract.

## OAuth Client And Cloud Run Authorized Origin

### Verified Current State

- Local `.env` contains `GOOGLE_OAUTH_CLIENT_ID=994154906699-jh6jkqprffr941im0mhq09efa3kj2p0a.apps.googleusercontent.com`.
- `auth.py` accepts `GOOGLE_OAUTH_CLIENT_ID` or fallback `GOOGLE_CLIENT_ID`.
- `docs/development/local-setup.md` states Google OIDC local mode requires the exact local origin `http://127.0.0.1:8000` in the OAuth client's authorized JavaScript origins.
- No Cloud Run URL exists yet because no service has been deployed.

### Required Configuration

- After Cloud Run creates the service URL, add the exact deployed origin to the OAuth Web Client's Authorized JavaScript Origins:
  - `https://<cloud-run-hostname>`
- Keep the same OAuth client ID configured in Cloud Run as `GOOGLE_OAUTH_CLIENT_ID`.

### Unresolved Decision

- Final Cloud Run service name and region, which determine the generated `run.app` hostname unless a custom domain is later configured.

### Failure Risk

- OAuth origin is not required to create the Cloud Run service.
- OAuth origin is required before hosted Google sign-in proof.
- If the deployed origin is missing, `/workspace` can load but Google Sign-In will fail before the app gets an authenticated session.

## Required Cloud Run Environment Variables

### Verified Current State

Local `.env` currently contains:

```dotenv
GOOGLE_CLOUD_PROJECT=project-e1e2a890-4566-48a8-a32
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_ENTERPRISE=True
GOOGLE_OAUTH_CLIENT_ID=994154906699-jh6jkqprffr941im0mhq09efa3kj2p0a.apps.googleusercontent.com
```

Local Google OIDC development launch currently supplies `AGENT_COL_AUTH_MODE=google_oidc` in the terminal command rather than `.env`:

```bash
AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

`vertex_config.py` requires:

- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION=global`
- `GOOGLE_GENAI_USE_ENTERPRISE=True`

`auth.py` requires an OAuth client ID when Google mode is used.

### Required Configuration

Configure the Cloud Run revision with:

```text
AGENT_COL_AUTH_MODE=google_oidc
GOOGLE_OAUTH_CLIENT_ID=994154906699-jh6jkqprffr941im0mhq09efa3kj2p0a.apps.googleusercontent.com
GOOGLE_CLOUD_PROJECT=project-e1e2a890-4566-48a8-a32
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_ENTERPRISE=True
```

Use `--update-env-vars` for incremental changes or apply a complete deterministic service spec. Do not casually use `--set-env-vars` with one key because it removes previously configured environment variables not included in that invocation.

### Unresolved Decision

- Whether the first deployment command will use `--update-env-vars` or a deterministic full service YAML / script.

### Failure Risk

- Missing `AGENT_COL_AUTH_MODE=google_oidc` currently falls back to `local_dev` unless Pass 1 is implemented first.
- Missing OAuth client ID breaks `/api/auth/config` and authenticated sessions in Google mode.
- Missing or wrong Vertex env vars fail startup during lifespan initialization.

## K_SERVICE, PORT, And Production Startup Behavior

### Verified Current State

- Current source does not reference `K_SERVICE`.
- `auth.py` defaults missing `AGENT_COL_AUTH_MODE` to `local_dev`.
- Local development uses `127.0.0.1:8000` and `--reload`.
- Cloud Run docs state:
  - ingress container must listen on `0.0.0.0`;
  - Cloud Run injects `PORT`;
  - default request port is `8080`;
  - Cloud Run injects `K_SERVICE`, `K_REVISION`, and `K_CONFIGURATION`.
- No tracked `Dockerfile` exists yet to define production startup.

### Required Configuration

- Dockerfile must start Uvicorn without reload and bind to Cloud Run's runtime port:

```text
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
```

- Pass 1 should add a fail-closed guard:

```text
if K_SERVICE is present:
    require AGENT_COL_AUTH_MODE=google_oidc
    require OAuth client ID
    rely on existing Vertex config validation for Google Cloud/Vertex env
```

### Unresolved Decision

- Exact Docker base image and production command form.
- Whether to use shell-form command for `${PORT:-8080}` expansion or a small startup script.

### Failure Risk

- Binding to `127.0.0.1` in Cloud Run fails the runtime contract.
- Using `--reload` in Cloud Run is development behavior and should not ship.
- Without `K_SERVICE` fail-closed guard, a misconfigured revision could serve in local-dev auth mode.

## Public Cloud Run Invocation Vs Application-Level Google OIDC

### Verified Current State

- Agent Col already enforces Google OIDC inside FastAPI when `AGENT_COL_AUTH_MODE=google_oidc`.
- `auth.py` verifies bearer tokens with Google's verifier and checks user/project ownership.
- `main.py` routes call the authenticator on protected APIs.
- Cloud Run Admin API is disabled, so no live Cloud Run service IAM state could be checked.
- `gcloud resource-manager org-policies list --project=...` returned `[]`.
- `gcloud org-policies describe constraints/run.managed.requireInvokerIam ...` could not run because `orgpolicy.googleapis.com` is disabled.

### Required Configuration

- Cloud Run service should be publicly reachable.
- Agent Col should enforce user auth inside FastAPI through Google OIDC.
- Intended request path:

```text
Internet
-> public Cloud Run endpoint
-> Agent Col Google OIDC
-> protected user data
```

Not:

```text
Internet
-> Cloud Run IAM gate
-> Agent Col Google OIDC
```

### Unresolved Decision

- Exact public access mechanism for the first service:
  - `--allow-unauthenticated`, or
  - disable Cloud Run Invoker IAM check if using the newer access-control model.
- Need to verify no inherited org/folder/project policy prevents public invocation.

### Failure Risk

- If Cloud Run itself requires IAM invocation, normal browser users can hit a Google 403 before FastAPI sees the request.
- If org policy blocks public access, deployment may succeed but hosted browser proof will fail at the platform boundary.

## Deployment Packaging Choice And Uploaded Files

### Verified Current State

- Selected path is explicit Dockerfile plus container image.
- No tracked `Dockerfile` exists.
- No tracked `.dockerignore` exists.
- No tracked `.gcloudignore` exists.
- `requirements.txt` includes runtime dependencies:
  - `fastapi==0.141.1`
  - `google-api-core==2.34.0`
  - `google-adk==2.7.0`
  - `google-cloud-firestore==2.28.1`
  - `google-genai==2.18.1`
  - `pydantic==2.13.4`
  - `python-dotenv==1.2.3`
  - `uvicorn==0.52.4`
- `.gitignore` excludes:
  - `venv/`
  - `__pycache__/`
  - `*.pyc`
  - `.env`
  - `.DS_Store`
- `gcloud meta list-files-for-upload` currently excludes `.env` but includes `.agents/`, `.pytest_cache/`, `scrnshot-evidence/`, broad tests, live tests, and docs.

### Required Configuration

For the selected Dockerfile/image path:

- Add a Dockerfile in a later approved implementation pass.
- Add `.dockerignore` in the same or a separate approved packaging pass.
- Build an image for Cloud Run's supported platform, including `linux/amd64`.
- Push the image to Artifact Registry.
- Deploy with `gcloud run deploy --image <artifact-registry-image>`.

For source upload hygiene:

- Even though source deployment is not selected, create or verify ignore behavior before any Google source upload command is used.
- Do not upload `.env`, credential files, screenshots, caches, local evidence, or unrelated agent tooling.

### Unresolved Decision

- Final Artifact Registry repository name and region.
- Whether image build is local Docker or Cloud Build using the explicit Dockerfile.
- Exact Docker ignore list.

### Failure Risk

- Without `.dockerignore`, local build context can include unnecessary or private material.
- Without Artifact Registry enabled and repository selected, image push/deploy cannot proceed.
- If Cloud Build is used for the Dockerfile build, Cloud Build API and build service-account IAM become required for the build step.

## Concurrency, Min/Max Instances, Timeout, And Cold-Start Settings

### Verified Current State

- Current source has request-bound chat orchestration.
- `agent_col_turn_service.py` sets:
  - `TURN_TIMEOUT_SECONDS = 90.0`
  - `TURN_ROUTING_TIMEOUT_SECONDS = 15.0`
- Other provider/service timeouts include:
  - synthesis generation: `60`
  - generic artifact generation: `60.0`
  - working-state update: `20.0`
  - computational expert service: `60.0`
- Cloud Run docs state:
  - default request timeout is 300 seconds unless configured otherwise;
  - timeout returns 504 to the client and container code may continue;
  - default concurrency for a new service can be much higher than one request per instance;
  - minimum instances default to zero;
  - max instances can limit cost and protect backing services;
  - startup CPU boost and minimum instances can reduce cold-start latency.

### Required Configuration

First hackathon settings should be deliberate and conservative:

- Concurrency: start below the Cloud Run default; `8` is a reasonable initial candidate to verify, but final value needs approval.
- Max instances: keep intentionally small, likely `1` or another small `N`, to bound spend and make in-memory rate limiting more predictable.
- Min instances:
  - `0` for cheapest deployment with possible cold starts;
  - `1` for warmer demo with small ongoing cost.
- Request timeout: must be greater than Agent Col's internal turn timeout. Candidate: `120s` or `180s`, both above the current `90s` turn timeout and below Cloud Run's default `300s`.
- Startup CPU boost: consider enabling for demo smoothness if cold-start latency is visible.

### Unresolved Decision

- Final concurrency value.
- Final max instances.
- Final min instances for demo recording.
- Final Cloud Run request timeout.
- Whether to enable startup CPU boost.

### Failure Risk

- Too much concurrency can expose shared-state/session behavior issues during judging.
- Concurrency `1` can increase instance fan-out and cold starts under simultaneous traffic.
- Min instances `0` can make first demo request look slow.
- Cloud Run timeout must remain above app/model timeouts so Agent Col aborts before Cloud Run returns 504.

## Health And Startup Probe Behavior

### Verified Current State

- `main.py` exposes `GET /` returning:

```json
{"status":"online"}
```

- The health route is cheap and does not call Vertex/Gemini.
- FastAPI lifespan initializes app services, Vertex settings, database, model client, and authenticator before serving normal app state.

### Required Configuration

- Use cheap health/startup behavior.
- Health/startup checks should prove:
  - process is running;
  - config loaded;
  - app initialized.
- Do not make health checks call Gemini, Vertex generation, expensive Firestore operations, or content-bearing workflows.

### Unresolved Decision

- Whether to rely on Cloud Run's default startup behavior for the first service or configure an explicit startup probe against `/`.

### Failure Risk

- Expensive health checks can burn Vertex quota/cost and create false deployment failures.
- A probe that depends on Firestore/Vertex can prevent the service from serving even when the web app process is healthy.

## Secrets And Credentials That Must Not Be Uploaded Or Configured

### Verified Current State

- `.env` exists locally and contains deployment-critical public/non-secret config plus project identifiers.
- `.gitignore` excludes `.env`.
- `gcloud meta list-files-for-upload` did not include `.env`.
- No tracked credential JSON was found in the deployment-file inventory, but this preflight did not perform a full secret scan of every file.
- Local setup docs explicitly say never to commit `.env`, credential JSON, OAuth client secrets, service-account keys, access tokens, or ADC credential files.

### Required Configuration

Must not upload, commit, bake into images, or configure in Cloud Run:

- `.env`
- OAuth client secret
- service-account key JSON
- Application Default Credentials files
- access tokens or refresh tokens
- screenshots or local evidence containing private data
- `.agents/`
- `.pytest_cache/`
- local virtual environments and caches

Must not configure in Cloud Run:

- `GOOGLE_APPLICATION_CREDENTIALS`

Cloud Run should use its service identity instead.

### Unresolved Decision

- Exact `.dockerignore` content.
- Whether a deploy-specific archive will be generated instead of relying only on Docker ignore rules.

### Failure Risk

- Missing `.dockerignore` can leak local tooling, caches, evidence screenshots, or credentials into build context.
- Setting `GOOGLE_APPLICATION_CREDENTIALS` in Cloud Run defeats the service-identity model and increases key-management risk.

## API And IAM Requirements By Packaging Path

### Selected Path: Dockerfile Image Deployment

Required APIs:

- `run.googleapis.com`: Cloud Run Admin API.
- `artifactregistry.googleapis.com`: Artifact Registry API.
- `aiplatform.googleapis.com`: Vertex AI API.
- `firestore.googleapis.com`: Firestore API.
- `logging.googleapis.com`: Cloud Logging API.
- `serviceusage.googleapis.com`: Service Usage API for API enablement checks.

Required identities and roles:

- Deployer identity with permission to deploy Cloud Run and manage or reference the Artifact Registry image.
- Deployer identity with `iam.serviceAccounts.actAs` on the chosen runtime service account.
- Runtime service account with Firestore and Vertex AI permissions.

Current status:

- Enabled: `aiplatform.googleapis.com`, `firestore.googleapis.com`, `logging.googleapis.com`, `serviceusage.googleapis.com`.
- Disabled/not enabled in live checks: `run.googleapis.com`, `artifactregistry.googleapis.com`.

### Unselected Alternative: `gcloud run deploy --source`

This path is not selected for the submission deployment.

Additional requirements if revived later:

- `cloudbuild.googleapis.com`.
- Source-build service account.
- `roles/run.builder` on the build service account.
- Cloud Run source deploy permissions such as `roles/run.sourceDeveloper` and `roles/serviceusage.serviceUsageConsumer`, unless covered by broader roles.
- `.gcloudignore` or `--ignore-file` upload hygiene.

Current status:

- `cloudbuild.googleapis.com` is disabled/not enabled in live checks.

### Unresolved Decision

- Whether local Docker build is sufficient or whether Cloud Build will be used only to build the explicit Dockerfile image.

### Failure Risk

- Treating Cloud Build as required for Cloud Run itself is wrong for the selected path.
- Treating Cloud Build as irrelevant is also wrong if the build step is moved to Google Cloud.

## First Hosted Smoke-Test Sequence

### Verified Current State

- Local smoke tooling exists for idempotent chat and can target `--base-url`.
- Current docs warn not to run the hosted chat smoke against a public deployment until auth, ownership, limits, and hosted verification are accepted.
- `/` is a cheap health endpoint.
- `/workspace` serves the same-origin browser workspace.
- `/api/auth/config` and `/api/auth/session` exist.

### Required Configuration

After deployment and OAuth origin authorization:

1. Open Cloud Run service URL.
2. Verify `GET /` returns `{"status":"online"}`.
3. Open `/workspace`.
4. Complete Google Sign-In from the deployed origin.
5. Verify `/api/auth/session` returns authenticated Google-mode app session.
6. Create or select workspace.
7. Send demo-safe chat prompt.
8. Confirm Agent Col returns a response through ADK/Vertex.
9. Confirm Firestore persistence by closing/opening a later session and retrieving continuity.
10. Confirm account A cannot read or mutate account B's workspace data if a second Google account is available.
11. Verify security headers once Pass 4 is implemented.
12. Verify raw body limits and best-effort rate limiting once Pass 4 is implemented.
13. Inspect Cloud Logging for absence of prompt, memory, note, source, artifact, and feedback content once Pass 5 is implemented.

### Unresolved Decision

- Which Google account(s) will be used for hosted proof.
- Which prompt is safe enough for judge evidence.
- Whether the hosted proof will use only manual browser verification or also a sanitized smoke script.

### Failure Risk

- Smoke tests that stop at `/api/auth/session` do not prove the Google-backed Collaborative Partner path.
- A successful Cloud Run deployment does not prove Vertex, Firestore, OAuth, ownership, persistence, or continuity.

## Go / No-Go Checklist For First Deployment Attempt

Current status: **NO-GO**.

Go requires every selected-path item below:

- [ ] Cloud Run Admin API enabled: `run.googleapis.com`.
- [ ] Artifact Registry API enabled: `artifactregistry.googleapis.com`.
- [ ] Artifact Registry repository selected or created in the chosen region.
- [ ] Cloud Run region chosen, starting from Firestore proximity to `us-east4`.
- [ ] Dedicated Agent Col runtime service account selected or created.
- [ ] Deployer can attach runtime identity with `iam.serviceAccounts.actAs`.
- [ ] Runtime service account has Firestore permission.
- [ ] Runtime service account has Vertex AI permission.
- [ ] Public Cloud Run invocation is allowed by service config and not blocked by org/folder/project policy.
- [ ] Dockerfile exists and starts Uvicorn on `0.0.0.0:$PORT` without reload.
- [ ] `.dockerignore` excludes `.env`, credentials, `.agents/`, `.pytest_cache/`, screenshots, local evidence, virtualenvs, and caches.
- [ ] Image build path chosen: local Docker or Cloud Build for explicit Dockerfile image.
- [ ] If Cloud Build is used for image build, Cloud Build API and build service-account IAM are verified.
- [ ] Cloud Run env vars configured exactly for Google OIDC and Vertex:
  - `AGENT_COL_AUTH_MODE=google_oidc`
  - `GOOGLE_OAUTH_CLIENT_ID`
  - `GOOGLE_CLOUD_PROJECT`
  - `GOOGLE_CLOUD_LOCATION=global`
  - `GOOGLE_GENAI_USE_ENTERPRISE=True`
- [ ] No `GOOGLE_APPLICATION_CREDENTIALS` configured on Cloud Run.
- [ ] Cloud Run concurrency, max instances, min instances, request timeout, and startup CPU boost decision recorded.
- [ ] Cloud Run URL added to OAuth Authorized JavaScript Origins before hosted Google sign-in proof.
- [ ] First hosted smoke-test sequence ready.

The next source-changing pass should still be Pass 1 from the Cloud Run production hardening plan: implement the `K_SERVICE` fail-closed guard under TDD before deploying.
