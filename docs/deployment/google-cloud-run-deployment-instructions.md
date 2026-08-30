# Google Cloud Run Deployment Instructions

Last reconciled: August 29, 2026.

## 1. Purpose And Deployment Target

This runbook updates the existing Agent Col Cloud Run service so the current
production URL runs the newest approved source from `origin/main`. It does not
create a second Cloud Run service.

Deployment target:

- Google Cloud project: `project-e1e2a890-4566-48a8-a32`
- Cloud Run service: `agent-col`
- Region: `us-east4`
- Production URL: `https://agent-col-994154906699.us-east4.run.app`
- Observed Cloud Run service/status URL:
  `https://agent-col-oc7iq4errq-uk.a.run.app`
- Artifact Registry repository: `agent-col`
- Artifact Registry location: `us-east4`
- Image naming convention:
  `us-east4-docker.pkg.dev/project-e1e2a890-4566-48a8-a32/agent-col/agent-col:${COMMIT_SHA}`
- Runtime service account:
  `agent-col-cloud-run@project-e1e2a890-4566-48a8-a32.iam.gserviceaccount.com`

Use the full Git commit SHA as the immutable image tag unless an operator
explicitly chooses a shorter tag and records the corresponding full SHA.

## 2. Preconditions

Run these checks before building or deploying.

Verify the expected repository and remote:

```bash
pwd
git remote -v
```

Expected repository root:

```text
<repo-root>
```

Expected remote:

```text
origin git@github.com:knightsky-cpu/col-workspace.git
```

Verify branch, Git state, and current commit:

```bash
git status
git branch --show-current
git log -1 --oneline
git rev-parse HEAD
```

Deployment should continue only from `main` and only from a clean or explicitly
reviewed local Git state. Do not discard local work automatically.

Verify `gcloud` authentication and project:

```bash
gcloud auth list
gcloud config get-value project
```

Expected active account:

```text
ritroy16@gmail.com
```

Expected active project:

```text
project-e1e2a890-4566-48a8-a32
```

Set the project if needed:

```bash
gcloud config set project project-e1e2a890-4566-48a8-a32
```

Verify required Google APIs:

```bash
gcloud services list --enabled \
  --project=project-e1e2a890-4566-48a8-a32 \
  --filter='config.name:(run.googleapis.com OR artifactregistry.googleapis.com OR orgpolicy.googleapis.com OR firestore.googleapis.com OR aiplatform.googleapis.com OR logging.googleapis.com OR serviceusage.googleapis.com)' \
  --format='value(config.name)'
```

Expected enabled APIs:

```text
aiplatform.googleapis.com
artifactregistry.googleapis.com
firestore.googleapis.com
logging.googleapis.com
orgpolicy.googleapis.com
run.googleapis.com
serviceusage.googleapis.com
```

Verify Docker is available:

```bash
docker version
```

Verify Artifact Registry access:

```bash
gcloud artifacts repositories describe agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --location=us-east4
```

Verify Cloud Run access:

```bash
gcloud run services describe agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4
```

The deployer must have permission to push to Artifact Registry, deploy Cloud
Run services, and act as the runtime service account.

## 3. Synchronize Newest Approved Source

Start from the approved repository state:

```bash
git status
git branch --show-current
git fetch origin
git pull --ff-only origin main
git log -1 --oneline
git rev-parse HEAD
```

Stop if the branch is not `main`, if the pull is not fast-forward-only, or if
the printed commit is not the approved commit intended for deployment.

## 4. Verify Google Cloud Target

Confirm the active authenticated account and project:

```bash
gcloud auth list
gcloud config get-value project
```

Confirm the existing Cloud Run service before changing it:

```bash
gcloud run services describe agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='yaml(metadata.name,metadata.annotations,status.url,status.latestCreatedRevisionName,status.latestReadyRevisionName,status.traffic,spec.template.spec.serviceAccountName,spec.template.spec.containers,spec.template.metadata.annotations)'
```

Verify the stable production URL:

```bash
curl -fsS https://agent-col-994154906699.us-east4.run.app/
curl -fsS https://agent-col-994154906699.us-east4.run.app/api/auth/config
```

Capture the current revision and image as rollback evidence:

```bash
ROLLBACK_REVISION="$(gcloud run services describe agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='value(status.latestReadyRevisionName)')"

ROLLBACK_IMAGE="$(gcloud run revisions describe "${ROLLBACK_REVISION}" \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='value(spec.containers[0].image)')"

printf 'Rollback revision: %s\n' "${ROLLBACK_REVISION}"
printf 'Rollback image: %s\n' "${ROLLBACK_IMAGE}"
```

## 5. Build The New Container

The canonical Agent Col deployment method is a local Docker build from the
checked-in `Dockerfile`, followed by an Artifact Registry push and Cloud Run
image update. Do not switch to source deploy or buildpacks unless that change
is explicitly approved.

Authenticate Docker to the regional Artifact Registry host:

```bash
gcloud auth configure-docker us-east4-docker.pkg.dev --quiet
```

Construct the immutable image tag from the full Git commit SHA:

```bash
COMMIT_SHA="$(git rev-parse HEAD)"
IMAGE="us-east4-docker.pkg.dev/project-e1e2a890-4566-48a8-a32/agent-col/agent-col:${COMMIT_SHA}"
printf 'Building image: %s\n' "${IMAGE}"
```

Build the container:

```bash
docker build -t "${IMAGE}" .
```

Optionally inspect the local image platform:

```bash
docker image inspect "${IMAGE}" --format '{{.Os}}/{{.Architecture}}'
```

Expected platform for the existing deployment path:

```text
linux/amd64
```

## 6. Push The Container Image

Push the immutable image tag:

```bash
docker push "${IMAGE}"
```

Verify the image exists in Artifact Registry before deploying:

```bash
gcloud artifacts docker images describe "${IMAGE}" \
  --project=project-e1e2a890-4566-48a8-a32 \
  --format='yaml(image_summary.fully_qualified_digest,image_summary.digest,image_summary.tags,image_summary.update_time)'
```

## 7. Deploy The New Revision To The Existing Service

This command updates the existing `agent-col` service to the exact image in
`${IMAGE}`. It preserves the currently observed runtime configuration.

Important: `--set-env-vars` replaces the service's environment variable set
with the variables supplied in the command. Because omitted variables can be
removed, this command includes the complete required Agent Col runtime set.

```bash
gcloud run deploy agent-col \
  --image="${IMAGE}" \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --service-account=agent-col-cloud-run@project-e1e2a890-4566-48a8-a32.iam.gserviceaccount.com \
  --no-invoker-iam-check \
  --ingress=all \
  --port=8080 \
  --cpu=1 \
  --memory=512Mi \
  --concurrency=8 \
  --timeout=180s \
  --max-instances=1 \
  --min-instances=0 \
  --cpu-boost \
  --set-env-vars=AGENT_COL_AUTH_MODE=google_oidc,GOOGLE_OAUTH_CLIENT_ID=994154906699-jh6jkqprffr941im0mhq09efa3kj2p0a.apps.googleusercontent.com,GOOGLE_CLOUD_PROJECT=project-e1e2a890-4566-48a8-a32,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_ENTERPRISE=True
```

The service is intentionally public at the Cloud Run invocation layer using
`run.googleapis.com/invoker-iam-disabled: "true"` / `--no-invoker-iam-check`.
Agent Col protects user data at the application layer with Google OIDC.

Scaling note: Stage 1 inspection found service metadata
`run.googleapis.com/maxScale: "20"` and current revision template annotation
`autoscaling.knative.dev/maxScale: "1"`. Treat these as separate observed
service-level and revision-level scaling controls. For source-only
redeployment, preserve the current effective revision-level maximum of one
instance with `--max-instances=1` unless a scaling change is explicitly
approved.

## 8. Verify Revision Rollout

Describe the service after deployment:

```bash
gcloud run services describe agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='yaml(metadata.name,metadata.annotations,status.url,status.latestCreatedRevisionName,status.latestReadyRevisionName,status.conditions,status.traffic,spec.template.spec.serviceAccountName,spec.template.spec.containers,spec.template.metadata.annotations)'
```

List recent revisions:

```bash
gcloud run revisions list \
  --service=agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='table(metadata.name,status.conditions[0].type,status.conditions[0].status,spec.containers[0].image,spec.serviceAccountName,spec.containerConcurrency,spec.timeoutSeconds)' \
  --limit=10
```

Verify the newest ready revision uses the intended image:

```bash
LATEST_REVISION="$(gcloud run services describe agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='value(status.latestReadyRevisionName)')"

DEPLOYED_IMAGE="$(gcloud run revisions describe "${LATEST_REVISION}" \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='value(spec.containers[0].image)')"

printf 'Latest ready revision: %s\n' "${LATEST_REVISION}"
printf 'Deployed image: %s\n' "${DEPLOYED_IMAGE}"
printf 'Expected image tag: %s\n' "${IMAGE}"
```

Verify traffic allocation:

```bash
gcloud run services describe agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='yaml(status.traffic)'
```

Expected result: `100%` of traffic on the newest healthy revision.

## 9. Hosted Application Smoke Test

Verify the public health and auth configuration endpoints:

```bash
curl -fsS https://agent-col-994154906699.us-east4.run.app/
curl -fsS https://agent-col-994154906699.us-east4.run.app/api/auth/config
curl -fsS -o /tmp/agent-col-auth-session.json -w '%{http_code}\n' \
  https://agent-col-994154906699.us-east4.run.app/api/auth/session
```

Expected unauthenticated `/api/auth/session` status: `401`.

Manual browser smoke test:

1. Open `https://agent-col-994154906699.us-east4.run.app/workspace`.
2. Verify Google OIDC sign-in works.
3. Verify existing workspace access.
4. Send a normal chat turn.
5. Verify Agent Col returns a response.
6. Verify chat persistence/history by refreshing or reopening the chat session.
7. Verify the Memory section loads and shows expected state.
8. Verify collaborative notes can be viewed and a representative note flow used
   by the demo still works.
9. Verify continuity from a prior chat or note.
10. Verify a representative specialist flow with receipts or citations.
11. Verify artifact creation/read behavior used by the demo.

Read recent Cloud Run service logs:

```bash
gcloud run services logs read agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --limit=100
```

Focused log query for errors:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="agent-col" AND severity>=ERROR' \
  --project=project-e1e2a890-4566-48a8-a32 \
  --freshness=1h \
  --limit=50 \
  --format='table(timestamp,severity,textPayload,jsonPayload.message)'
```

Focused log query for hosted chat:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="agent-col" AND httpRequest.requestMethod="POST" AND httpRequest.requestUrl:"/api/chat"' \
  --project=project-e1e2a890-4566-48a8-a32 \
  --freshness=1h \
  --limit=20 \
  --format='table(timestamp,httpRequest.status,httpRequest.latency,httpRequest.requestUrl,httpRequest.responseSize,httpRequest.userAgent)'
```

## 10. Confirm Deployed Commit

The deployment tag is the Git commit SHA:

```bash
git rev-parse HEAD
printf '%s\n' "${IMAGE}"
```

After rollout, verify that the deployed revision image contains the same tag:

```bash
LATEST_REVISION="$(gcloud run services describe agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='value(status.latestReadyRevisionName)')"

gcloud run revisions describe "${LATEST_REVISION}" \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='value(spec.containers[0].image)'
```

Record the full Git SHA, image tag, image digest, latest ready revision, and
verification timestamp in the deployment notes or release evidence.

## 11. Rollback

Do not delete the failed revision during emergency rollback. Preserve it for
inspection unless there is a specific operational reason to remove it.

List recent revisions:

```bash
gcloud run revisions list \
  --service=agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='table(metadata.name,status.conditions[0].status,spec.containers[0].image,metadata.creationTimestamp)' \
  --limit=10
```

Route traffic back to the previous healthy revision captured before deployment:

```bash
gcloud run services update-traffic agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --to-revisions="${ROLLBACK_REVISION}=100"
```

If the previous healthy image is known but the revision is not usable, redeploy
the previous known-good image while preserving the same runtime settings:

```bash
gcloud run deploy agent-col \
  --image="${ROLLBACK_IMAGE}" \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --service-account=agent-col-cloud-run@project-e1e2a890-4566-48a8-a32.iam.gserviceaccount.com \
  --no-invoker-iam-check \
  --ingress=all \
  --port=8080 \
  --cpu=1 \
  --memory=512Mi \
  --concurrency=8 \
  --timeout=180s \
  --max-instances=1 \
  --min-instances=0 \
  --cpu-boost \
  --set-env-vars=AGENT_COL_AUTH_MODE=google_oidc,GOOGLE_OAUTH_CLIENT_ID=994154906699-jh6jkqprffr941im0mhq09efa3kj2p0a.apps.googleusercontent.com,GOOGLE_CLOUD_PROJECT=project-e1e2a890-4566-48a8-a32,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_ENTERPRISE=True
```

Verify rollback:

```bash
gcloud run services describe agent-col \
  --project=project-e1e2a890-4566-48a8-a32 \
  --region=us-east4 \
  --format='yaml(status.latestReadyRevisionName,status.traffic)'

curl -fsS https://agent-col-994154906699.us-east4.run.app/
```

## 12. MacBook Deployment Notes With Colima

On the MacBook, Docker is provided by Colima, not Docker Desktop. A plain
Docker command may fail if the default Docker context still points at
`unix:///var/run/docker.sock`.

Check Colima first:

```bash
colima status
colima list
docker context ls
```

If Colima is stopped, start it:

```bash
colima start
```

Expected result after startup:

```text
Current context is now "colima"
```

Verify Docker is using the Colima socket:

```bash
docker context ls
docker version --format '{{.Server.Version}}'
```

Expected Docker endpoint:

```text
unix://<user-home>/.colima/default/docker.sock
```

Important: in the managed Codex sandbox, Colima and Docker commands that touch
`~/.colima`, `~/.docker`, or the Colima Docker socket require elevated
permission. Sandboxed commands can fail even when the local machine is
configured correctly. Observed sandbox failures include:

```text
colima is not running
error writing yaml file: open <user-home>/.colima/default/colima.yaml: operation not permitted
permission denied while trying to connect to the docker API at unix://<user-home>/.colima/default/docker.sock
```

Use elevated execution for the Colima startup and Docker build/push steps when
running through Codex. Do not reinterpret those sandbox permission failures as
Cloud Run, Dockerfile, Artifact Registry, or application defects without
checking Colima state directly.

Because this MacBook's Colima profile is `aarch64`, build the Cloud Run image
explicitly for `linux/amd64`:

```bash
COMMIT_SHA="$(git rev-parse HEAD)"
IMAGE="us-east4-docker.pkg.dev/project-e1e2a890-4566-48a8-a32/agent-col/agent-col:${COMMIT_SHA}"

docker build --platform linux/amd64 -t "${IMAGE}" .
docker image inspect "${IMAGE}" --format '{{.Os}}/{{.Architecture}}'
```

Expected platform:

```text
linux/amd64
```

After the platform check passes, continue with the Artifact Registry push,
Cloud Run deployment, and hosted verification sections above.

## 13. Common Failure Cases

- Wrong active project: run `gcloud config get-value project`; set
  `project-e1e2a890-4566-48a8-a32` before any build, push, deploy, or log
  command.
- Wrong region: all Cloud Run and Artifact Registry commands in this runbook
  use `us-east4`.
- Unauthenticated `gcloud`: run `gcloud auth list`; authenticate as an account
  with Artifact Registry, Cloud Run, and service-account-user permissions.
- Artifact Registry auth failure: rerun
  `gcloud auth configure-docker us-east4-docker.pkg.dev --quiet` and confirm
  Docker can use the `gcloud` credential helper.
- Image push failure: confirm `${IMAGE}` starts with
  `us-east4-docker.pkg.dev/project-e1e2a890-4566-48a8-a32/agent-col/agent-col:`
  and that the deployer can write to the `agent-col` repository.
- Cloud Run permission failure: confirm the deployer can deploy Cloud Run and
  can act as
  `agent-col-cloud-run@project-e1e2a890-4566-48a8-a32.iam.gserviceaccount.com`.
- Missing environment variables: compare the service template env vars with the
  complete required set in this runbook; redeploy with the full `--set-env-vars`
  list if needed.
- Google OIDC misconfiguration: verify `/api/auth/config` returns
  `google_oidc`, the expected OAuth client ID, `google_signin_required: true`,
  and `local_development: false`. Also confirm the production URL is in the
  OAuth Web Client Authorized JavaScript origins.
- Vertex or ADC failures: confirm the runtime service account has the required
  Vertex AI and Firestore permissions and that env vars include
  `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, and
  `GOOGLE_GENAI_USE_ENTERPRISE=True`.
- Revision not becoming ready: inspect
  `gcloud run services logs read agent-col --project=project-e1e2a890-4566-48a8-a32 --region=us-east4 --limit=100`
  and `gcloud run services describe agent-col ...` conditions.
- HTTP 500 after deployment: inspect Cloud Run logs, confirm env vars, confirm
  Firestore/Vertex permissions, and rollback if user-visible behavior is
  broken.
- Source deployed from the wrong Git commit: compare the deployed image tag
  with `git rev-parse HEAD`, then rebuild/push/deploy from the intended
  approved commit.

## 14. Safety Rules

- Never deploy with unresolved local source changes unless they are explicitly
  intended and reviewed.
- Never use `git reset --hard` or destructive cleanup as part of normal
  deployment.
- Never create a second Cloud Run service when the intent is to update the
  existing Agent Col service.
- Never silently change auth mode, service account, environment variables, or
  production runtime settings during a source-only deployment.
- Always identify the Git commit being deployed.
- Always verify the newly deployed revision before considering deployment
  complete.
- Always preserve a known-good rollback target.
