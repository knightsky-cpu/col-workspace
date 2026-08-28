# Agent Col

Agent Col is a persistent collaborative partner for the Devpost All Things
Agentic Hackathon. It keeps user-approved continuity, takes governed workspace
notes, routes to bounded specialist capabilities, and records inspectable
receipts for durable side effects.

Structured synthesis and artifacts are demonstration workflows beneath the
larger product identity. Agent Col is not only a coding assistant or blueprint
generator.

For the detailed source-level status, see
[Agent Col Current State](docs/current-state.md).

## Current Status

Agent Col is under active development and is not publicly deployed.

Implemented in the current source:

- same-origin browser workspace at `/workspace`;
- local-development and Google OIDC authentication foundation;
- workspace list/create flows;
- persisted chat sessions and retry-safe chat turns;
- governed profile memory with proposal, clarification, approval, rejection,
  correction, revocation, deletion, inspection, and adaptation receipts;
- governed workspace notes with proposal, approval/rejection, correction,
  archive, restore, deletion, active projection, and continuity receipts;
- hidden internal working state for same-session collaboration continuity;
- four bounded specialist capabilities:
  - Research with Google Search grounding;
  - Source with URL Context;
  - Computation with Python code execution;
  - Requirements Verification with local evidence validation;
- zero-or-one expert execution per turn and responder-owned final answers;
- synchronous structured synthesis;
- persisted blueprint and generic artifacts;
- artifact lifecycle, versioning, and feedback surfaces;
- frontend panels for Workspace, Work, Notes, Memory, Chats, Activity, and
  conversation receipts;
- offline API, orchestration, schema, database, frontend, and smoke-runner
  tests.

Still planned:

- evidence-governed preference learning from corrections through user-confirmed
  memory;
- stronger visible collaboration leadership using existing working state;
- production hardening for ownership, limits, logging, retention, startup, and
  hosted security;
- Dockerfile, production startup scripts, Cloud Run service configuration, and
  hosted deployment evidence;
- hosted reproducibility/submission evidence and demo freeze.

Durable asynchronous artifact jobs, Google Cloud Tasks, and private worker
execution are deferred until after submission under the current finalization
strategy.

## Contest Category

**Collaborative Partner**

The judged workflow is intended to demonstrate:

1. approved profile learning and new-session adaptation;
2. governed workspace notes;
3. consequential clarification;
4. bounded specialist work;
5. artifact creation and feedback;
6. controlled failure or retry behavior;
7. inspectable Firestore and Google Cloud evidence once deployed.

## Technology

Pinned runtime stack:

- Python 3.14 local/runtime target;
- FastAPI `0.141.1`;
- Google ADK `2.7.0`;
- Google GenAI SDK `2.18.1`;
- Google Cloud Firestore `2.28.1`;
- Pydantic `2.13.4`;
- Uvicorn `0.52.4`;
- Gemini `gemini-3.6-flash` through Vertex AI / Gemini Enterprise.

The frontend is static HTML, CSS, and vanilla JavaScript ES modules served by
FastAPI.

## Local Setup

Create and activate the virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Create an ignored `.env` file:

```dotenv
GOOGLE_CLOUD_PROJECT=replace-with-your-project-id
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_ENTERPRISE=True
GOOGLE_OAUTH_CLIENT_ID=replace-with-public-oauth-client-id
```

`GOOGLE_OAUTH_CLIENT_ID` is public browser configuration, not a client secret.
Do not commit `.env`, OAuth client secrets, service-account keys, access
tokens, or ADC credential files.

Configure local Application Default Credentials for Firestore and Vertex AI:

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

The application does not use a Gemini API key. Vertex AI and Firestore use the
authenticated ADC identity. Browser Google OIDC is a separate end-user
authentication boundary.

## Running Locally

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

```text
http://127.0.0.1:8000/
```

Expected response:

```json
{"status":"online"}
```

## Tests

Run the offline automated suite:

```bash
pytest
```

Run frontend tests:

```bash
node --test tests/frontend/*.test.mjs
```

Run the retry-safe chat smoke check against a local server:

```bash
python3 smoke_test_chat_idempotency.py
```

See [Testing](docs/development/testing.md) for focused commands and test-layer
boundaries.

## Documentation

- [Current state](docs/current-state.md)
- [Final checklist planning](docs/final-checklist-planning.md)
- [Architecture](docs/architecture.md)
- [Local development setup](docs/development/local-setup.md)
- [Testing](docs/development/testing.md)
- [Troubleshooting](docs/development/troubleshooting.md)
- [Winning Core checklist](docs/aug-25-2026-final-checklist.md)
- [Safe frontend visual change boundaries](docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md)
- [Submission checklist](docs/submission-checklist.md)

Historical snapshots live under [docs/legacy](docs/legacy/README.md).

## Security Status

Do not expose the current local-development configuration as a public service.
Google OIDC support exists, but the full Phase 4 production hardening and
Cloud Run deployment work is still pending.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

Original-project attribution is recorded in [NOTICE](NOTICE).
