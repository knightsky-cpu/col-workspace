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
- the Google Cloud CLI;
- Application Default Credentials with Firestore access;
- a Google AI Gemini API key.

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
GOOGLE_API_KEY=replace-with-a-Google-AI-key
GOOGLE_CLOUD_PROJECT=replace-with-your-project-id
```

`GOOGLE_API_KEY` is required at application startup. `GOOGLE_CLOUD_PROJECT`
lets the Firestore client resolve the project explicitly. Never commit `.env`,
API keys, credential JSON, or copied tokens.

## Configure Google Cloud credentials

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

The first command supplies local Application Default Credentials. The second
sets the active CLI project. The third attributes client-library quota to that
project and removes the common end-user-credentials quota warning when the
account has permission.

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
