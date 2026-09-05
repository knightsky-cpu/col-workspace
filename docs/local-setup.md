# Agent Col Local Setup

Last reconciled: September 5, 2026.

This guide is for a developer starting from a fresh clone with their own
Google Cloud project. It avoids production-specific project IDs, account
emails, service URLs, image digests, OAuth IDs, and secrets.

For the full source map, see [Repository map](repo-map.md). For the maintained
Cloud Run runbook used by the canonical service, see
[Google Cloud Run deployment instructions](deployment/google-cloud-run-deployment-instructions.md).

## Prerequisites

- macOS or Linux.
- Python 3.14. The production Docker image uses `python:3.14-slim`.
- Node.js 20+ or a current LTS for frontend module tests.
- Google Cloud CLI.
- Docker. On Apple Silicon macOS, the documented deployment path uses Colima
  and builds a `linux/amd64` image.
- A Google Cloud project where you can enable APIs, use Firestore Native mode,
  create Artifact Registry repositories, deploy Cloud Run, and bind IAM roles.
- A Google OAuth Web Client ID if using `google_oidc` mode.

There is no frontend dependency install and no frontend build step. The UI is
static ES modules in `frontend/` served by FastAPI.

## Clone And Install

```bash
git clone git@github.com:knightsky-cpu/col-workspace.git
cd col-workspace
python3.14 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

If your system exposes Python 3.14 as `python3`, use:

```bash
python3 -m venv venv
```

## Configure Placeholders

Set shell placeholders for your own infrastructure:

```bash
export PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
export REGION="<YOUR_GCP_REGION>"
export SERVICE_NAME="<YOUR_CLOUD_RUN_SERVICE_NAME>"
export REPOSITORY="<YOUR_ARTIFACT_REGISTRY_REPOSITORY>"
export IMAGE_NAME="<YOUR_IMAGE_NAME>"
export GOOGLE_CLIENT_ID="<YOUR_GOOGLE_OAUTH_CLIENT_ID>"
export RUNTIME_SERVICE_ACCOUNT="<YOUR_RUNTIME_SERVICE_ACCOUNT_EMAIL>"
```

Do not commit `.env`, OAuth client secrets, service-account keys, access
tokens, refresh tokens, or Application Default Credential files.

## Enable Google Cloud Services

```bash
gcloud config set project "$PROJECT_ID"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  orgpolicy.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  logging.googleapis.com \
  serviceusage.googleapis.com \
  speech.googleapis.com \
  texttospeech.googleapis.com \
  --project="$PROJECT_ID"
```

Create or verify Firestore Native mode in the project. This repository does
not create or delete the Firestore database automatically.

## Local Credentials

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project "$PROJECT_ID"
```

Server-side Vertex AI, Firestore, Speech-to-Text, and Text-to-Speech calls use
Application Default Credentials locally. Browser Google OIDC is separate: it
authenticates the end user to Agent Col and does not replace ADC for backend
Google Cloud clients.

## Local Environment

Create an ignored `.env` in the repository root or export these variables in
your shell:

```dotenv
GOOGLE_CLOUD_PROJECT=<YOUR_GCP_PROJECT_ID>
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_ENTERPRISE=True
GOOGLE_OAUTH_CLIENT_ID=<YOUR_GOOGLE_OAUTH_CLIENT_ID>
AGENT_COL_STT_LANGUAGE_CODES=en-US
AGENT_COL_STT_MODEL=latest_short
```

Runtime variables consumed by current source:

| Variable | Required | Purpose |
| --- | --- | --- |
| `AGENT_COL_AUTH_MODE` | Launch-time | `local_dev` or `google_oidc`; defaults to `local_dev` if omitted. |
| `GOOGLE_CLOUD_PROJECT` | Yes | Google Cloud project for Vertex AI, Firestore, STT, and TTS. |
| `GOOGLE_CLOUD_LOCATION` | Yes | Current source expects `global` for Gemini and defaults STT recognizer location to `global`. |
| `GOOGLE_GENAI_USE_ENTERPRISE` | Yes | Must be `True` for the current Vertex/Gemini Enterprise configuration. |
| `GOOGLE_OAUTH_CLIENT_ID` | Google mode | Public Google OAuth Web Client ID. |
| `GOOGLE_CLIENT_ID` | Optional fallback | Alternate env name accepted for the same public OAuth client ID. |
| `AGENT_COL_STT_LANGUAGE_CODES` | Optional | Comma-separated STT languages; defaults to `en-US`. |
| `AGENT_COL_STT_MODEL` | Optional | STT model; defaults to `latest_short`. |
| `AGENT_COL_SPEECH_MAX_AUDIO_BYTES` | Optional | Speech upload size limit override. |

The older `GOOGLE_GENAI_USE_VERTEXAI` name is not the current repository
configuration. Use `GOOGLE_GENAI_USE_ENTERPRISE=True`.

## OAuth Local Origin

For Google OIDC local testing, add this authorized JavaScript origin to the
OAuth Web Client:

```text
http://127.0.0.1:8000
```

The OAuth client ID is public browser configuration. It is not a client secret.

## Run Locally

Local-development auth mode:

```bash
AGENT_COL_AUTH_MODE=local_dev venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Google OIDC auth mode:

```bash
AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/workspace
```

Health check:

```bash
curl -fsS http://127.0.0.1:8000/
```

Expected response:

```json
{"status":"online"}
```

In `local_dev`, enter a local user/project context in the UI. In
`google_oidc`, sign in with Google; the backend verifies the ID token and maps
the Google principal to opaque public locators.

## Speech Verification

Speech-to-Text and Text-to-Speech are backend-owned.

- Browser dictation posts `audio/webm` or `audio/webm;codecs=opus` to
  `/api/speech/transcribe`.
- Spoken responses call `/api/users/{user_id}/speech/synthesize` for completed
  assistant messages.

Current defaults from `speech_service.py`:

- STT language: `en-US`.
- STT model: `latest_short`.
- TTS female voice: `en-GB-Chirp3-HD-Kore`.
- TTS male voice: `en-GB-Chirp3-HD-Alnilam`.
- TTS audio: MP3.
- TTS speaking rate: `1.0`.

If local STT/TTS fails, verify `speech.googleapis.com` and
`texttospeech.googleapis.com` are enabled, ADC is configured, and the quota
project is set.

## Local Verification Commands

Offline backend suite:

```bash
venv/bin/python -m pytest -q
```

Frontend ES module tests:

```bash
node --test tests/frontend/*.test.mjs
```

Focused deployment packaging check:

```bash
venv/bin/python -m pytest -q tests/test_deployment_packaging.py
```

Live local chat idempotency smoke, with Uvicorn already running:

```bash
python3 live-tests/smoke_test_chat_idempotency.py
```

Live smoke tests require configured Google credentials and may create real
Firestore records.

## Deploy Your Own Cloud Run Instance

The repository deployment model is local Docker build, Artifact Registry push,
and Cloud Run deploy. On Apple Silicon macOS, use Colima and build for
`linux/amd64`.

Create or verify an Artifact Registry Docker repository:

```bash
gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker \
  --location="$REGION" \
  --project="$PROJECT_ID"
```

Create a runtime service account if needed:

```bash
gcloud iam service-accounts create "$SERVICE_NAME-cloud-run" \
  --display-name="$SERVICE_NAME Cloud Run runtime" \
  --project="$PROJECT_ID"

export RUNTIME_SERVICE_ACCOUNT="$SERVICE_NAME-cloud-run@$PROJECT_ID.iam.gserviceaccount.com"
```

Grant the runtime roles used by current backend code:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SERVICE_ACCOUNT" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SERVICE_ACCOUNT" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SERVICE_ACCOUNT" \
  --role="roles/serviceusage.serviceUsageConsumer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SERVICE_ACCOUNT" \
  --role="roles/speech.client"
```

`roles/speech.client` grants Speech-to-Text access.
Text-to-Speech is covered by enabling `texttospeech.googleapis.com` plus service
usage access in the documented role set.

On macOS with Colima:

```bash
colima status
colima list
docker context ls
colima start
docker version --format '{{.Server.Version}}'
```

Build, inspect, and push an immutable image tag:

```bash
export COMMIT_SHA="$(git rev-parse HEAD)"
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:$COMMIT_SHA"

gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet
docker build --platform linux/amd64 -t "$IMAGE" .
docker image inspect "$IMAGE" --format '{{.Architecture}}'
docker push "$IMAGE"
gcloud artifacts docker images describe "$IMAGE" --project="$PROJECT_ID"
```

Deploy:

```bash
gcloud run deploy "$SERVICE_NAME" \
  --image="$IMAGE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
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
  --set-env-vars="AGENT_COL_AUTH_MODE=google_oidc,GOOGLE_OAUTH_CLIENT_ID=$GOOGLE_CLIENT_ID,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_ENTERPRISE=True,AGENT_COL_STT_LANGUAGE_CODES=en-US,AGENT_COL_STT_MODEL=latest_short"
```

Add the resulting Cloud Run URL as an authorized JavaScript origin on the
OAuth Web Client.

Verify the deployed service:

```bash
export SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format='value(status.url)')"

curl -fsS "$SERVICE_URL/"
curl -fsS "$SERVICE_URL/api/auth/config"
curl -sS -o /tmp/agent-col-auth-session.json -w '%{http_code}\n' "$SERVICE_URL/api/auth/session"

gcloud run services describe "$SERVICE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format='yaml(status.latestReadyRevisionName,status.traffic,status.url)'
```

Unauthenticated `/api/auth/session` should return `401` in Google OIDC mode.
Use the browser UI at `$SERVICE_URL/workspace` for authenticated chat, memory,
notes, continuity, artifacts, microphone transcription, and spoken-response
verification.

## Stop Local Development

Press `Control-C` in the Uvicorn terminal, then deactivate the environment:

```bash
deactivate
```
