# Local Development Setup

These steps run the current FastAPI application and same-origin browser
workspace locally. The local app can use either local-development identity or
browser Google OIDC. Firestore and Vertex AI calls use Application Default
Credentials in both modes.

The current runtime is still request-bound. Cloud Tasks and a private worker
are deferred until after submission; Docker and Cloud Run deployment remain
production-hardening work. None are current local runtime requirements.

## Prerequisites

- macOS or Linux;
- Python 3.14 recommended;
- a Google Cloud project with Firestore in Native mode;
- Vertex AI enabled in that project;
- Google Cloud CLI;
- Application Default Credentials with Firestore and Vertex AI access;
- a Google OAuth web client if testing Google OIDC mode.

## Clone And Create The Environment

```bash
git clone git@github.com:knightsky-cpu/col-workspace.git
cd col-workspace
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

`requirements.txt` pins runtime dependencies. `requirements-dev.txt` includes
the runtime file and pins offline test dependencies.

## Environment Variables

Create `.env` in the repository root. It is ignored by Git.

```dotenv
GOOGLE_CLOUD_PROJECT=replace-with-your-project-id
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_ENTERPRISE=True
GOOGLE_OAUTH_CLIENT_ID=replace-with-public-oauth-client-id
```

| Variable | Required | Purpose |
| --- | --- | --- |
| `GOOGLE_CLOUD_PROJECT` | Yes | Firestore and Vertex AI project. |
| `GOOGLE_CLOUD_LOCATION` | Yes | Gemini model location; current source expects `global`. |
| `GOOGLE_GENAI_USE_ENTERPRISE` | Yes | Selects the current Vertex/Gemini Enterprise backend used by pinned SDKs. |
| `AGENT_COL_AUTH_MODE` | Yes when launching | `local_dev` or `google_oidc`. Defaults to `local_dev` if omitted. |
| `GOOGLE_OAUTH_CLIENT_ID` | Google mode | Public browser OAuth client ID. |
| `GOOGLE_CLIENT_ID` | Optional fallback | Alternate env name accepted for the same public OAuth client ID. |

The older `GOOGLE_GENAI_USE_VERTEXAI` name is deprecated for this repository's
pinned SDK versions and should not be configured.

Never commit `.env`, credential JSON, OAuth client secrets, service-account
keys, access tokens, or ADC credential files.

## Configure Google Cloud Credentials

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

Local model and Firestore calls authenticate through ADC. Browser Google OIDC
is separate: it verifies the end user for application requests but does not
replace ADC for server-side Google Cloud clients.

To verify Vertex AI independently before starting Agent Col:

```bash
curl --fail-with-body --silent --show-error \
    --request POST \
    --header "Authorization: Bearer $(gcloud auth print-access-token)" \
    --header "Content-Type: application/json" \
    --data '{"contents":[{"role":"user","parts":[{"text":"Reply with exactly:vertex-online"}]}]}' \
    "https://aiplatform.googleapis.com/v1/projects/YOUR_PROJECT_ID/locations/global/publishers/google/models/gemini-3.6-flash:generateContent"
```

The response should contain `vertex-online` and report model version
`gemini-3.6-flash`.

Firestore must already exist in Native mode. This repository does not create
or delete a Firestore database automatically.

## Start The Application

Local-development auth mode:

```bash
AGENT_COL_AUTH_MODE=local_dev venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Google OIDC auth mode:

```bash
AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open the browser workspace:

```text
http://127.0.0.1:8000/workspace
```

Health endpoint:

```bash
curl --fail-with-body --silent --show-error http://127.0.0.1:8000/
```

Expected response:

```json
{"status":"online"}
```

For Google OIDC mode, ensure the OAuth client's authorized JavaScript origins
include the exact local origin:

```text
http://127.0.0.1:8000
```

## Verify Retry-Safe Chat

Keep Uvicorn running, activate the virtual environment in a second terminal,
and run:

```bash
python3 smoke_test_chat_idempotency.py
```

The runner performs a new chat request, an identical replay, and a changed-body
conflict using one generated key. It should print a structural line containing
`first=200 replay=200 conflict=409 replay_equal=true` plus generated Firestore
locators. It does not print the prompt, key, or model response.

To verify a future hosted URL without changing code:

```bash
python3 smoke_test_chat_idempotency.py --base-url https://YOUR_HOST
```

Do not use this against a public deployment until Phase 4 authentication,
ownership, limits, and hosted verification have been accepted.

## Other Checks

Offline suite:

```bash
pytest -q
```

Frontend tests:

```bash
node --test tests/frontend/*.test.mjs
```

Direct structured synthesis smoke:

```bash
python3 smoke_test_synthesis.py
```

That script makes a live Gemini call and may print generated blueprint content,
so it is not a privacy-minimized or quota-free check.

## Stop The Application

Press `Control-C` in the Uvicorn terminal. The FastAPI lifespan closes GenAI
clients and the Firestore client. Deactivate the environment when finished:

```bash
deactivate
```
