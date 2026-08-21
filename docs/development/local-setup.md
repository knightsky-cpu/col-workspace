# Local Development Setup

## What this setup provides

These steps run the current synchronous FastAPI application locally. Chat and
synthesis requests call Gemini directly during the HTTP request, while
Firestore stores collaboration memory, chat history, durable chat turns, and
blueprints. Google Cloud Tasks, a browser UI, authentication, and Cloud Run
deployment are not part of the current local runtime.

## Prerequisites

- macOS or Linux;
- Python 3.13 or newer (the current repository is verified with Python 3.14);
- a Google Cloud project with Firestore in Native mode;
- the Vertex AI API enabled in that project;
- the Google Cloud CLI;
- Application Default Credentials with Firestore and Vertex AI access.

## Clone and create the environment

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
the runtime file and pins the offline test dependencies.

## Configure environment variables

Create `.env` in the repository root. It is ignored by Git.

```dotenv
GOOGLE_CLOUD_PROJECT=replace-with-your-project-id
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_ENTERPRISE=True
```

`GOOGLE_CLOUD_PROJECT` identifies the project used by Firestore and Vertex AI.
Gemini 3.6 Flash is served through the `global` Vertex AI location, and
`GOOGLE_GENAI_USE_ENTERPRISE=True` selects the current Google Cloud model
backend used by the pinned GenAI SDK and ADK versions. The older
`GOOGLE_GENAI_USE_VERTEXAI` name is a deprecated alias in those versions. This
naming change does not switch Agent_Col away from the Vertex/Aiplatform
endpoint. The application fails startup instead of falling back to the Gemini
Developer API when these values are missing or invalid. Never commit `.env`,
credential JSON, or copied tokens.

## Configure Google Cloud credentials

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="user:YOUR_ACCOUNT_EMAIL" \
    --role="roles/aiplatform.user"
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

The first command sets the active CLI project. The second enables Vertex AI.
The third grants the local development identity the narrow Vertex AI user
role; an existing project owner already has broader access but should retain
that broad role only when it is actually needed. The fourth command supplies
local Application Default Credentials. The final command attributes
client-library quota and billing to the project.

Local model calls authenticate through ADC. No long-lived Gemini API key is
required or supported by this application configuration. Cloud Run will use a
dedicated service identity instead of a copied local credential file.

To verify Vertex AI independently before starting Agent_Col:

```bash
curl --fail-with-body --silent --show-error \
    --request POST \
    --header "Authorization: Bearer $(gcloud auth print-access-token)" \
    --header "Content-Type: application/json" \
    --data '{"contents":[{"role":"user","parts":[{"text":"Reply with exactly:vertex-online"}]}]}' \
    "https://aiplatform.googleapis.com/v1/projects/YOUR_PROJECT_ID/locations/global/publishers/google/models/gemini-3.6-flash:generateContent"
```

The response should contain `vertex-online` and report
`"modelVersion": "gemini-3.6-flash"`.

Firestore must already exist in Native mode. This repository does not create
or delete a Firestore database automatically.

## Start and verify the application

```bash
source venv/bin/activate
uvicorn main:app --reload
```

In a second terminal:

```bash
curl --fail-with-body --silent --show-error http://127.0.0.1:8000/
```

Expected response:

```json
{"status":"online"}
```

The browser may request `/favicon.ico` and receive 404. That does not affect
the health endpoint.

## Verify retry-safe chat

Keep Uvicorn running, activate the virtual environment in the second terminal,
and run:

```bash
python3 smoke_test_chat_idempotency.py
```

The runner performs a new chat request, an identical replay, and a changed-body
conflict using one generated key. It should print one structural line containing
`first=200 replay=200 conflict=409 replay_equal=true` plus generated Firestore
locators. It does not print the prompts, key, or model response.

To verify a future hosted URL without changing code:

```bash
python3 smoke_test_chat_idempotency.py --base-url https://YOUR_HOST
```

Do not use this against a public deployment until authentication and ownership
checks are implemented.

## Other live checks

Direct structured synthesis:

```bash
python3 smoke_test_synthesis.py
```

That script makes a live Gemini call and prints the generated blueprint, so it
is not a privacy-minimized or quota-free check.

Run offline tests before spending provider quota:

```bash
pytest -q
```

## Stop the application

Press `Control-C` in the Uvicorn terminal. The FastAPI lifespan closes the
GenAI clients and Firestore client. Deactivate the environment when finished:

```bash
deactivate
```
