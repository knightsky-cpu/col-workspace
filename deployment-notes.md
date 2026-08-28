# Agent Col Deployment Notes

## 2026-08-28 - Pass 1: Cloud Run Fail-Closed Config Guard

Status: accepted by manual verification.

Previous checkpoint: `d5253e7ce0f85f174085f64a612e4180b63d3178`.

### Scope

- Implemented the first Cloud Run production-hardening pass from `docs/superpowers/plans/2026-08-28-cloud-run-production-hardening-deployment.md`.
- Preserved local development behavior when `K_SERVICE` is absent.
- Did not deploy to Cloud Run.
- Did not enable Google Cloud APIs.
- Did not add Dockerfile packaging.
- Did not change `.env`.

### Source Changes

- `auth.py`
  - `load_auth_settings()` now treats a nonblank `K_SERVICE` as the Cloud Run runtime signal.
  - When `K_SERVICE` is present, startup auth settings fail unless `AGENT_COL_AUTH_MODE=google_oidc`.
  - When `K_SERVICE` is present and Google OIDC mode is selected, startup auth settings fail unless `GOOGLE_OAUTH_CLIENT_ID` or `GOOGLE_CLIENT_ID` is configured with a nonblank value.

- `tests/test_auth.py`
  - Added coverage proving local default auth mode is preserved outside Cloud Run.
  - Added coverage proving Cloud Run rejects missing auth mode, `local_dev`, missing OAuth client ID, and blank OAuth client ID.
  - Added coverage proving Cloud Run accepts `google_oidc` with a trimmed OAuth client ID.

### TDD Evidence

- RED command:

```bash
venv/bin/pytest tests/test_auth.py -k "load_auth_settings" -q
```

Observed result before implementation: `4 failed, 2 passed, 7 deselected`. The failing cases were the unsafe Cloud Run configurations that did not raise `AuthConfigurationError`.

- GREEN command:

```bash
venv/bin/pytest tests/test_auth.py -k "load_auth_settings" -q
```

Observed result after implementation: `6 passed, 7 deselected`.

### Focused Verification

```bash
venv/bin/pytest tests/test_auth.py -q
```

Observed result: `13 passed`.

```bash
venv/bin/pytest tests/test_main.py -k "auth_session or auth_config or google_mode_rejects_project_artifact_mismatch_before_service or google_workspace_create_uses_subject_owned_workspace_prefix or google_chat_requires_idempotency_key_before_service_access or google_chat_propagates_verified_owner_to_claim_and_history or google_mode_rejects_generic_artifact_project_mismatch_before_generation" -q
```

Observed result: `8 passed, 195 deselected, 1 warning`.

```bash
git diff --check
```

Observed result: passed.

### Manual Acceptance

The user reported: "pass successful".

### Checkpoint State

Checkpointed to `origin/main` at `71b8d5b69246d99be76183afe0e70fd537cb01c4`.

## 2026-08-28 - Pass 4: HTTP Body Limits, Scoped Rate Limiting, And Security Headers

Status: accepted by manual verification.

Previous checkpoint: `cba0f7d77eb21b53365deec70cabd3f4060437f9`.

### Scope

- Implemented request perimeter hardening only.
- Did not change deployment configuration.
- Did not change Google auth behavior.
- Did not run or depend on live Google Sign-In or Cloud Run behavior checks; those remain deferred to the hosted integration verification phase.
- Preserved the existing schema-level 10,000-character chat message limit as a separate application validation layer.

### Source Changes

- `main.py`
  - Added a 64 KiB raw HTTP body cap enforced by ASGI middleware before FastAPI JSON parsing and before route/service execution.
  - Covered both `Content-Length` rejection and streamed/no-`Content-Length` request bodies.
  - Added deterministic `429 Too Many Requests` responses with `Retry-After`.
  - Added an in-memory rate limiter scoped to expensive or mutating API routes only:
    - `POST /api/chat`
    - `POST /api/synthesize`
    - `POST`, `PATCH`, and `DELETE` under `/api/users/...`
    - `POST`, `PATCH`, and `DELETE` under `/api/projects/...`
  - Left health, workspace, static assets, and cheap read-only API traffic outside the rate-limit bucket.
  - Added security headers to workspace, static assets, and API responses:
    - `Content-Security-Policy`
    - `X-Content-Type-Options`
    - `X-Frame-Options`
    - `Referrer-Policy`
    - `Permissions-Policy`
  - Preserved `/workspace` and `/static/agent-col/...` `Cache-Control: no-store` behavior.

- `tests/test_main.py`
  - Added coverage for raw oversized request rejection before JSON parsing.
  - Added coverage for streamed oversized request rejection before JSON parsing.
  - Added coverage proving the existing 10,000-character chat schema limit remains distinct from the raw body limit.
  - Added coverage proving scoped rate limiting returns deterministic `429` plus `Retry-After` while health/workspace requests remain unaffected.
  - Added coverage proving security headers apply to workspace, static, and API responses while allowing Google Identity Services script/frame origins and same-origin future streaming/fetch.

### TDD Evidence

- RED command:

```bash
venv/bin/pytest tests/test_main.py -k "oversized_raw_body or schema_chat_limit_remains_distinct or scoped_rate_limiter or security_headers"
```

Observed result before implementation: `3 failed, 1 passed, 206 deselected`. Failures proved the raw body limit constant, in-memory limiter, and security headers did not exist. The schema-limit test already passed, proving the existing application/schema limit was separate and should remain unchanged.

- Additional RED command after the first body-limit implementation:

```bash
venv/bin/pytest tests/test_main.py -k "streamed_oversized_raw_body"
```

Observed result before the ASGI receive-path fix: failed with `422` instead of `413`, proving streamed oversized bodies could still reach FastAPI JSON/validation handling.

- GREEN command:

```bash
venv/bin/pytest tests/test_main.py -k "streamed_oversized_raw_body"
```

Observed result after the ASGI middleware fix: `1 passed, 210 deselected`.

- GREEN command:

```bash
venv/bin/pytest tests/test_main.py -k "oversized_raw_body or schema_chat_limit_remains_distinct or scoped_rate_limiter or security_headers"
```

Observed result after implementation: `5 passed, 206 deselected`.

### Focused Verification

```bash
venv/bin/pytest tests/test_main.py
```

Observed result: `211 passed, 1 warning`.

```bash
git diff --check
```

Observed result: passed.

The one warning is the existing dependency/runtime `BaseAgentConfig` deprecation warning and was not introduced by this pass.

### Limitations

- The rate limiter is explicitly best-effort, in-memory, per-process, and per Cloud Run instance. It is not distributed, durable, or globally authoritative across scaled Cloud Run instances.
- Google Sign-In/CSP behavior and real Cloud Run behavior remain deferred to hosted integration verification, where they provide meaningful evidence.

### Manual Acceptance

The user reported: "Pass 4: accepted."

### Checkpoint State

Checkpointed to `origin/main` at `5554d28bd5f662a0bc6e3aebc75d792e088e33de`.

## 2026-08-28 - Pass 2: Ownership Audit And Gap Closure

Status: accepted by manual verification.

Previous checkpoint: `71b8d5b69246d99be76183afe0e70fd537cb01c4`.

### Scope

- Audited public ownership-sensitive FastAPI routes against `auth.py`, `main.py`, `database.py`, and focused tests.
- Produced a route-by-route ownership matrix for user, workspace, memory, note, chat, blueprint, artifact, feedback, synthesis, and chat-turn surfaces.
- Made no Pass 2 source-code changes because no source-backed cross-user ownership gap was proven.

### Source-Backed Findings

- `main.py` routes that accept `user_id` use `_resolve_effective_user_id(...)`.
- `main.py` routes that accept `project_id` use `_resolve_effective_project_id(...)`.
- Mixed `user_id` and `project_id` routes use both guards before downstream service/database access.
- `auth.py` rejects Google user mismatches through `Authenticator.resolve_user_id(...)`.
- `auth.py` rejects Google workspace/project mismatches through `Authenticator.resolve_project_id(...)`.
- Chat session operations validate stored `user_id` and `project_id` through `MemoryEngine._validate_chat_session_owner(...)`.
- Collaborative notes are stored under `users/{user_id}/workspaces/{workspace_id}` and validate stored note/event ownership on read and mutation.
- Project artifact routes are guarded by the Google-owned `project_id` invariant before artifact service/database access.

### Caveat

Project-only artifact routes currently rely on the invariant that Google-owned `project_id` values are hash-derived workspace IDs enforced by `Authenticator.resolve_project_id(...)`. That is acceptable under the current architecture. If project IDs later become user-chosen or human-readable, those routes will need an additional persisted project-owner check.

### Focused Verification

```bash
venv/bin/pytest tests/test_auth.py -q
```

Observed result: `13 passed`.

```bash
venv/bin/pytest tests/test_main.py -k "google_mode_rejects_project_artifact_mismatch_before_service or google_workspace_create_uses_subject_owned_workspace_prefix or google_mode_rejects_generic_artifact_project_mismatch_before_generation or google_chat_requires_idempotency_key_before_service_access or google_chat_propagates_verified_owner_to_claim_and_history or chat_translates_session_ownership_errors_to_uniform_not_found or chat_clarification_selection_hides_ownership_mismatch" -q
```

Observed result: `10 passed, 193 deselected, 1 warning`.

```bash
venv/bin/pytest tests/test_database.py -k "ownership_mismatch or malformed_session_ownership" -q
```

Observed result: `6 passed, 38 deselected`.

```bash
venv/bin/pytest tests/test_chat_turn_database.py -k "ownership_mismatch or request_mismatch or rejects_reclaimed_owner or rejects_expired_owner or mismatched_stored_owner or mismatched_stored_metadata" -q
```

Observed result: `9 passed, 72 deselected`.

```bash
git diff --check
```

Observed result: passed.

### Manual Acceptance

The user accepted Pass 2 after reviewing the explicit route-by-route ownership matrix.

### Checkpoint State

Checkpointed to `origin/main` at `50b1951f33b7bdaf916b47dcf279301f93b577c0`.

## 2026-08-28 - Pass 3: Public/Internal User Identity Split

Status: accepted from automated verification. Live Google/OIDC integration confirmation deferred to hosted/browser verification.

Previous checkpoint: `50b1951f33b7bdaf916b47dcf279301f93b577c0`.

### Scope

- Replaced public Google-mode browser/API `user_id` exposure with a deterministic opaque locator.
- Preserved internal persisted user IDs as `google--{subject}`.
- Made no Firestore migration.
- Kept frontend identity behavior simple: the browser stores and sends the backend-provided `user_id` unchanged.
- Patched only source-proven public response leak surfaces.

### Source Changes

- `auth.py`
  - Added deterministic public locator generation as `user--{sha256(subject)[:32]}`.
  - `/api/auth/session` public output now uses the opaque locator and does not include `subject` or `google--{subject}`.
  - Google-mode `resolve_user_id()` now validates the supplied opaque public locator and returns the existing internal `google--{subject}` ID to downstream services and Firestore.
  - Local-dev behavior remains unchanged.

- `main.py`
  - Added public response shapers for chat session list/detail `user_id`.
  - Added public response shapers for collaborative note/detail/lifecycle `owner_user_id`.
  - Added public response shaping for chat `collaborative_note_events`.
  - Kept downstream service/database calls on the internal effective user ID.

- Frontend tests
  - Updated fixtures to use opaque public locators.
  - No frontend identity translation logic was added.

### TDD Evidence

- RED command:

```bash
venv/bin/pytest tests/test_auth.py -k "public_session_uses_opaque_user_locator or resolves_public_user_locator_to_internal_id or rejects_raw_internal_user_locator" -q
```

Observed result before implementation: `3 failed, 13 deselected`. Failures proved the public session still returned `google--109876543210`, opaque locators were rejected, and raw internal locators were still accepted.

- RED command:

```bash
venv/bin/pytest tests/test_main.py -k "auth_session_returns_google_principal or google_workspace_create_uses_subject_owned_workspace_prefix or google_mode_rejects_raw_internal_user_locator or list_chat_sessions_returns_project_user_sessions or get_chat_session_detail_returns_chronological_messages or google_collaborative_note_responses_hide_internal_owner or google_chat_propagates_verified_owner_to_claim_and_history or google_chat_note_event_receipts_hide_internal_owner" -q
```

Observed result before implementation/refinement: route tests failed because the backend rejected opaque locators or returned internal `google--{subject}` IDs in public responses. The chat note-event receipt test failed because `collaborative_note_events[0].owner_user_id` exposed `google--109876543210`.

- GREEN command:

```bash
venv/bin/pytest tests/test_auth.py -k "public_session_uses_opaque_user_locator or resolves_public_user_locator_to_internal_id or rejects_raw_internal_user_locator" -q
```

Observed result after implementation: `3 passed, 13 deselected`.

- GREEN command:

```bash
venv/bin/pytest tests/test_main.py -k "auth_session_returns_google_principal or google_workspace_create_uses_subject_owned_workspace_prefix or google_mode_rejects_raw_internal_user_locator or list_chat_sessions_returns_project_user_sessions or get_chat_session_detail_returns_chronological_messages or google_collaborative_note_responses_hide_internal_owner or google_chat_propagates_verified_owner_to_claim_and_history or google_chat_note_event_receipts_hide_internal_owner" -q
```

Observed result after implementation: `8 passed, 198 deselected, 1 warning`.

### Focused Verification

```bash
venv/bin/python -m py_compile auth.py main.py
```

Observed result: passed.

```bash
venv/bin/pytest tests/test_auth.py -q
```

Observed result: `16 passed`.

```bash
venv/bin/pytest tests/test_main.py -q
```

Observed result: `206 passed, 1 warning`.

```bash
node --test tests/frontend/auth-view.test.mjs tests/frontend/state.test.mjs tests/frontend/api.test.mjs tests/frontend/requests.test.mjs tests/frontend/workspace-static.test.mjs
```

Observed result: `98 passed`.

```bash
git diff --check
```

Observed result: passed.

### Public Leak Audit

- Patched `/api/auth/session` so Google mode returns an opaque public `user_id` and never returns `subject`.
- Patched chat session list/detail responses so persisted internal `user_id` values are replaced by the public route locator.
- Patched collaborative note list/detail/lifecycle responses so persisted `owner_user_id` values are replaced by the public route locator.
- Patched chat responses and partial-failure responses so `collaborative_note_events` do not expose internal `owner_user_id`.
- Left inbound request schema fields unchanged because they now carry the public locator and are translated at the auth boundary.
- Left artifact response models unchanged because the audited artifact metadata responses do not serialize `user_id`.

### Manual Acceptance

The user accepted Pass 3 from automated verification and explicitly deferred live Google/OIDC integration confirmation to the existing hosted/browser verification phase.

### Checkpoint State

Checkpointed to `origin/main` at `cba0f7d77eb21b53365deec70cabd3f4060437f9`.

## 2026-08-28 - Pass 5: Production Logging Privacy Audit

Status: accepted by manual verification.

Previous checkpoint: `5554d28bd5f662a0bc6e3aebc75d792e088e33de`.

### Scope

- Audited production Python logging call sites for content-bearing or identity-bearing logs.
- Patched only two source-proven leak surfaces.
- Did not change Cloud Logging configuration, retention policy, deployment configuration, Google auth behavior, or hosted verification.
- Left frontend behavior unchanged; `frontend/` has no `console.*` logging call sites in the audited source.

### Source Changes

- `preference_learning_service.py`
  - Preference extraction failure logs no longer include `user_id`, `project_id`, `session_id`, or `turn_id`.
  - Preference capture failure logs no longer include `user_id`, `project_id`, `session_id`, or `turn_id`.
  - Logs preserve the exception class for operational diagnosis.

- `generic_artifact_service.py`
  - Stored artifact content validation warnings no longer stringify full Pydantic `ValidationError` objects.
  - Stored artifact metadata validation warnings no longer stringify full Pydantic `ValidationError` objects.
  - Logs preserve the failure location and exception class without including stored artifact values.

- `tests/test_preference_learning_service.py`
  - Added canary coverage proving preference extraction/capture failure logs omit internal Google-style user IDs, project/session/turn/source-message IDs, user messages, model responses, and backend exception text.

- `tests/test_generic_artifact_service.py`
  - Added canary coverage proving generic artifact content/metadata validation logs omit artifact IDs, project IDs, artifact content, filenames, display labels, and invalid stored metadata values.

### TDD Evidence

- RED command:

```bash
venv/bin/pytest tests/test_preference_learning_service.py tests/test_generic_artifact_service.py -k "extraction_failure_is_no_effect or capture_failure_logs_without_private_identifiers_or_content or generic_artifact_content_validation_logs_no_private_data or generic_artifact_metadata_validation_logs_no_private_data"
```

Observed result before implementation: `4 failed, 13 deselected`. Failures proved:

- preference-learning logs exposed `google--109876543210`, project ID, session ID, and turn ID;
- generic artifact validation logs exposed Pydantic input values including artifact content and invalid metadata.

- GREEN command:

```bash
venv/bin/pytest tests/test_preference_learning_service.py tests/test_generic_artifact_service.py -k "extraction_failure_is_no_effect or capture_failure_logs_without_private_identifiers_or_content or generic_artifact_content_validation_logs_no_private_data or generic_artifact_metadata_validation_logs_no_private_data"
```

Observed result after implementation: `4 passed, 13 deselected`.

### Focused Verification

```bash
venv/bin/pytest tests/test_preference_learning_service.py tests/test_generic_artifact_service.py
```

Observed result: `17 passed`.

```bash
venv/bin/pytest tests/test_main.py -k "preference_learning or generic_artifact or logs"
```

Observed result: `22 passed, 189 deselected, 1 warning`.

```bash
git diff --check
```

Observed result: passed.

The one warning is the existing dependency/runtime `BaseAgentConfig` deprecation warning and was not introduced by this pass.

### Logging Audit Findings

- Fixed: `preference_learning_service.py` logged request identifiers on failure.
- Fixed: `generic_artifact_service.py` logged full validation error details that can include persisted artifact input values.
- Verified source-backed: `main.py`, `synthesis.py`, `generic_artifact_generation.py`, `source_expert_service.py`, `working_state_service.py`, `requirements_verification_service.py`, `computational_expert_service.py`, `research_expert_service.py`, `supervisor_runtime.py`, `agent_col_turn_service.py`, and `database.py` production logs use fixed messages plus exception class, bounded counts, operation labels, or allowlisted enum reasons.
- Verified source-backed: no `console.*` logging call sites exist in `frontend/`.

### Limitations

- Hosted Cloud Logging canary verification is still required after Cloud Run deployment because source tests cannot prove what Cloud Run request/container logs will contain.
- Cloud Logging retention, exclusions, sinks, and log-bucket settings remain infrastructure decisions for the deployment phase.

### Manual Acceptance

The user reported: "pass 5 is successful".

### Checkpoint State

Checkpointed with this accepted Pass 5 handoff update. Use `git rev-parse HEAD`
or the final checkpoint SHA reported after push as the authoritative commit.

## 2026-08-28 - Pass 6: Deployment Packaging

Status: accepted by manual verification.

Previous checkpoint: `47dd6f1b95536eb050438128ed241874e7491060`.

### Scope

- Implemented the selected explicit Dockerfile/container-image packaging path.
- Added a reproducible local Docker build for the existing FastAPI app.
- Configured the production container to start Uvicorn on `0.0.0.0:$PORT`
  without reload.
- Used `sh -c` only for `${PORT:-8080}` expansion and `exec uvicorn` so
  Cloud Run signals reach the server process.
- Excluded local credentials, repository metadata, agent workspace state,
  caches, tests, docs, screenshots, and evidence from the Docker build context.
- Did not push an image to Artifact Registry.
- Did not deploy to Cloud Run.
- Did not enable Google Cloud APIs.
- Did not change IAM, OAuth settings, Cloud Run service configuration, runtime
  environment variables, application source behavior, or frontend code.

### Source Changes

- `Dockerfile`
  - Added a `python:3.14-slim` runtime image.
  - Installs runtime dependencies from `requirements.txt`.
  - Copies the application into `/app`.
  - Runs as non-root `appuser`.
  - Exposes port `8080`.
  - Starts with:

```dockerfile
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

- `.dockerignore`
  - Excludes `.env`, `.env.*`, credential-looking files, `.git`, `.agents`,
    virtual environments, Python caches, test directories, docs, screenshots,
    evidence, logs, images, and broad JSON files.
  - Allows the tracked `firestore.indexes.json` file back into the context.

- `tests/test_deployment_packaging.py`
  - Added focused static packaging contract tests for the Dockerfile startup
    command, non-root user, runtime dependency install, absence of reload mode,
    absence of `GOOGLE_APPLICATION_CREDENTIALS` in the Dockerfile, and required
    `.dockerignore` exclusions.

### TDD Evidence

- RED command:

```bash
venv/bin/pytest tests/test_deployment_packaging.py -q
```

Observed result before implementation: `2 failed`. Both failures were expected:
`Dockerfile` and `.dockerignore` did not exist.

- GREEN command:

```bash
venv/bin/pytest tests/test_deployment_packaging.py -q
```

Observed result after implementation: `2 passed`.

### Focused Verification

```bash
venv/bin/pytest tests/test_deployment_packaging.py -q
```

Observed result: `2 passed`.

```bash
docker build -t agent-col:pass6 .
```

Observed result: image built and tagged successfully as `agent-col:pass6`.
The Docker build context was `1.774MB`. Docker emitted only the local
legacy-builder deprecation warning.

```bash
docker run --rm --entrypoint sh agent-col:pass6 -c 'test ! -e /app/.env && test ! -d /app/.git && test ! -d /app/.agents && test ! -d /app/venv && test ! -d /app/.pytest_cache && test ! -d /app/scrnshot-evidence && test -d /app/frontend && test -f /app/main.py && test -f /app/requirements.txt'
```

Observed result: passed. The built image contains required application files and
does not contain local secrets, repository metadata, agent workspace state,
virtualenvs, pytest cache, or screenshot evidence.

```bash
docker run --rm --name agent-col-pass6-smoke -p 8080:8080 -e PORT=8080 -e K_SERVICE=agent-col -e AGENT_COL_AUTH_MODE=google_oidc -e GOOGLE_OAUTH_CLIENT_ID=pass6-local-client -e GOOGLE_CLOUD_PROJECT=project-e1e2a890-4566-48a8-a32 -e GOOGLE_CLOUD_LOCATION=global -e GOOGLE_GENAI_USE_ENTERPRISE=True -e GOOGLE_APPLICATION_CREDENTIALS=/var/run/secrets/google/application_default_credentials.json -v /home/sigmaknight/.config/gcloud/application_default_credentials.json:/var/run/secrets/google/application_default_credentials.json:ro agent-col:pass6
```

Then, from the host:

```bash
curl -fsS http://127.0.0.1:8080/
```

Observed result:

```json
{"status":"online"}
```

```bash
git diff --check
```

Observed result: passed.

### Limitations

- Starting the container without ADC failed during FastAPI lifespan startup
  because `MemoryEngine()` constructs a Firestore `AsyncClient()` and Google
  auth could not find default credentials.
- The successful local smoke used a read-only host ADC file mount. No ADC file,
  OAuth client secret, service-account key, access token, or refresh token was
  copied or baked into the image.
- Artifact Registry push, Cloud Run deployment, service-account/IAM setup,
  OAuth deployed-origin configuration, and hosted Google OIDC proof remain
  deferred to later approved passes.

### Manual Acceptance

The user reported: "pass 6 accepted".

### Checkpoint State

Checkpointed with this accepted Pass 6 deployment packaging update. Use
`git rev-parse HEAD` or the final checkpoint SHA reported after push as the
authoritative commit.

## 2026-08-28 - Pass 7: Artifact Registry, IAM, And Cloud Run First Deploy

Status: accepted by manual verification.

Previous checkpoint: `7f3e3daa9593fc1a57e9b42ab82a9def11851164`.

### Scope

- Performed the approved deployment-plumbing pass for the selected explicit
  Dockerfile/image path.
- Enabled the approved Google Cloud APIs.
- Stopped after API enablement and re-read Cloud Run, Artifact Registry, and
  effective org-policy state before continuing.
- Created the approved Artifact Registry Docker repository in `us-east4`.
- Created the approved dedicated Cloud Run runtime service account.
- Applied the approved runtime IAM roles for Firestore and Vertex AI.
- Applied the approved deployer `Service Account User` binding on the runtime
  service account.
- Configured Docker authentication for the regional Artifact Registry hostname.
- Verified the local image platform before push.
- Tagged and pushed the accepted Pass 6 image to Artifact Registry.
- Verified the pushed image and digest.
- Deployed one public Cloud Run service using application-level Google OIDC.
- Did not change repository source code.
- Did not configure Google OAuth authorized JavaScript origins.
- Did not perform authenticated browser login or hosted chat proof.

### Google Cloud Changes

- Enabled APIs in project `project-e1e2a890-4566-48a8-a32`:
  - `run.googleapis.com`
  - `artifactregistry.googleapis.com`
  - `orgpolicy.googleapis.com`

- Created Artifact Registry repository:
  - Name: `agent-col`
  - Location: `us-east4`
  - Format: Docker

- Created runtime service account:
  - `agent-col-cloud-run@project-e1e2a890-4566-48a8-a32.iam.gserviceaccount.com`

- Granted runtime service account project roles:
  - `roles/datastore.user`
  - `roles/aiplatform.user`

- Granted deployer binding:
  - Principal: `user:ritroy16@gmail.com`
  - Role: `roles/iam.serviceAccountUser`
  - Resource:
    `agent-col-cloud-run@project-e1e2a890-4566-48a8-a32.iam.gserviceaccount.com`

- Pushed Artifact Registry image:
  - Tag:
    `us-east4-docker.pkg.dev/project-e1e2a890-4566-48a8-a32/agent-col/agent-col:7f3e3daa959`
  - Digest:
    `sha256:3c219a6cd592b5d3ebfe7da8a7c59cdb06e019efb103cc507c523e0e08102e6e`
  - Size reported by Artifact Registry: `84652173` bytes

- Deployed Cloud Run service:
  - Name: `agent-col`
  - Region: `us-east4`
  - Revision: `agent-col-00001-bft`
  - Stable service URL:
    `https://agent-col-994154906699.us-east4.run.app`
  - Status URL:
    `https://agent-col-oc7iq4errq-uk.a.run.app`
  - Runtime service account:
    `agent-col-cloud-run@project-e1e2a890-4566-48a8-a32.iam.gserviceaccount.com`
  - Public access mode: `run.googleapis.com/invoker-iam-disabled: "true"`
  - Ingress: `all`
  - Port: `8080`
  - Concurrency: `8`
  - Max instances: `1`
  - Min instances: `0`
  - Request timeout: `180s`
  - Startup CPU boost: `true`
  - Traffic: `100%` to `agent-col-00001-bft`

- Cloud Run environment variables configured:
  - `AGENT_COL_AUTH_MODE=google_oidc`
  - `GOOGLE_OAUTH_CLIENT_ID=994154906699-jh6jkqprffr941im0mhq09efa3kj2p0a.apps.googleusercontent.com`
  - `GOOGLE_CLOUD_PROJECT=project-e1e2a890-4566-48a8-a32`
  - `GOOGLE_CLOUD_LOCATION=global`
  - `GOOGLE_GENAI_USE_ENTERPRISE=True`

### Gate Evidence After API Enablement

After enabling Cloud Run, Artifact Registry, and Org Policy APIs, the required
stop-and-recheck gate produced:

```bash
gcloud services list --enabled --project=project-e1e2a890-4566-48a8-a32 --filter='config.name:(run.googleapis.com OR artifactregistry.googleapis.com OR orgpolicy.googleapis.com OR firestore.googleapis.com OR aiplatform.googleapis.com OR logging.googleapis.com OR serviceusage.googleapis.com)' --format='value(config.name)'
```

Observed enabled services:

```text
aiplatform.googleapis.com
artifactregistry.googleapis.com
firestore.googleapis.com
logging.googleapis.com
orgpolicy.googleapis.com
run.googleapis.com
serviceusage.googleapis.com
```

```bash
gcloud run services list --project=project-e1e2a890-4566-48a8-a32 --region=us-east4 --platform=managed --format=json
```

Observed result before deployment: `[]`.

```bash
gcloud artifacts repositories list --project=project-e1e2a890-4566-48a8-a32 --location=us-east4 --format=json
```

Observed result before repository creation: `[]`.

```bash
gcloud org-policies describe constraints/run.managed.requireInvokerIam --project=project-e1e2a890-4566-48a8-a32 --effective --format=json
```

Observed effective policy: `enforce: false`.

```bash
gcloud org-policies describe constraints/iam.allowedPolicyMemberDomains --project=project-e1e2a890-4566-48a8-a32 --effective --format=json
```

Observed effective policy: `allowAll: true`.

### Focused Verification

```bash
gcloud auth configure-docker us-east4-docker.pkg.dev --quiet
```

Observed result: Docker configuration was updated. The first push attempt then
failed because `docker-credential-gcloud` was not on this shell's `PATH`; the
helper existed at `/home/sigmaknight/.local/google-cloud-sdk/bin/docker-credential-gcloud`.
The push was retried with that Cloud SDK bin directory scoped into `PATH`.

```bash
docker image inspect agent-col:pass6 --format '{{.Os}}/{{.Architecture}}'
```

Observed result:

```text
linux/amd64
```

```bash
docker push us-east4-docker.pkg.dev/project-e1e2a890-4566-48a8-a32/agent-col/agent-col:7f3e3daa959
```

Observed result after scoped `PATH` retry: push succeeded with digest
`sha256:3c219a6cd592b5d3ebfe7da8a7c59cdb06e019efb103cc507c523e0e08102e6e`.

```bash
gcloud artifacts docker images describe us-east4-docker.pkg.dev/project-e1e2a890-4566-48a8-a32/agent-col/agent-col:7f3e3daa959 --project=project-e1e2a890-4566-48a8-a32 --format=json
```

Observed result: Artifact Registry reported the same digest and fully qualified
digest.

```bash
gcloud run deploy agent-col --image=us-east4-docker.pkg.dev/project-e1e2a890-4566-48a8-a32/agent-col/agent-col:7f3e3daa959 --region=us-east4 --service-account=agent-col-cloud-run@project-e1e2a890-4566-48a8-a32.iam.gserviceaccount.com --no-invoker-iam-check --port=8080 --concurrency=8 --max-instances=1 --min-instances=0 --timeout=180s --update-env-vars=AGENT_COL_AUTH_MODE=google_oidc,GOOGLE_OAUTH_CLIENT_ID=994154906699-jh6jkqprffr941im0mhq09efa3kj2p0a.apps.googleusercontent.com,GOOGLE_CLOUD_PROJECT=project-e1e2a890-4566-48a8-a32,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_ENTERPRISE=True --project=project-e1e2a890-4566-48a8-a32 --quiet
```

Observed result: service `agent-col` revision `agent-col-00001-bft` deployed
and served `100%` of traffic.

```bash
curl -fsS https://agent-col-994154906699.us-east4.run.app/
```

Observed result:

```json
{"status":"online"}
```

```bash
curl -fsS -o /tmp/agent-col-workspace.html -w '%{http_code} %{content_type}\n' https://agent-col-994154906699.us-east4.run.app/workspace
```

Observed result:

```text
200 text/html; charset=utf-8
```

```bash
curl -fsS https://agent-col-994154906699.us-east4.run.app/api/auth/config
```

Observed result: `auth_mode` was `google_oidc`,
`google_signin_required` was `true`, and `local_development` was `false`.

```bash
curl -fsS -o /tmp/agent-col-auth-session.json -w '%{http_code}\n' https://agent-col-994154906699.us-east4.run.app/api/auth/session
```

Observed result: `401`, expected for unauthenticated Google OIDC mode.

### Limitations

- Google browser login is not expected to work until
  `https://agent-col-994154906699.us-east4.run.app` is added to the OAuth Web
  Client's Authorized JavaScript Origins.
- Hosted authenticated chat, Firestore persistence, Vertex response proof,
  ownership proof, and Cloud Logging privacy canary verification remain deferred
  to Pass 8.
- Cloud Run `metadata.annotations["run.googleapis.com/maxScale"]` displayed
  `"20"` at the service metadata level, while the revision template annotation
  `autoscaling.knative.dev/maxScale` displayed `"1"`. The template annotation is
  the configured revision scaling control applied by the deploy command.

### Manual Acceptance

The user reported: "Pass 7 accepted."

### Checkpoint State

Checkpointed with this accepted Pass 7 deployment update. Use `git rev-parse
HEAD` or the final checkpoint SHA reported after push as the authoritative
commit.
