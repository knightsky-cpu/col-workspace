# Agent_Col

Agent_Col is a Collaborative Partner for the Devpost All Things Agentic
Hackathon. It is a persistent AI collaborator that uses user-approved working
preferences and low-sensitivity identity context to adapt across sessions.
Structured project synthesis is one demonstrated collaboration workflow, not
the complete identity of the system.

## Current status

Agent_Col is under active development and is not publicly deployed.

Implemented today:

- asynchronous FastAPI health and chat endpoints;
- Gemini 3.6 Flash through the Google GenAI SDK;
- asynchronous Firestore message and profile persistence;
- atomic session/message writes;
- optional retry-safe chat turns with durable claim, replay, conflict, lease,
  and atomic-completion behavior;
- project-owned, atomically persisted structured synthesis blueprints;
- a hybrid ADK runtime with model-controlled, locally validated routing and a
  responder-only Agent_Col boundary;
- strict local schema and semantic validation for blueprint version 2.0;
- governed memory proposals, approval/rejection, provenance, correction,
  revocation, bounded inspection, and hard deletion;
- ordinary-chat creation of one bounded, pending memory proposal when the user
  states an eligible reusable preference or allowed light identity detail;
- cross-session chat use of approved memory with explicit adaptation receipts;
- four bounded cognitive experts: Research with Google Search, Source with URL
  Context, Computation with code execution, and Requirements Verification with
  deterministic local validation;
- zero-or-one cognitive expert execution per turn, delegation depth one,
  application-derived receipts, and responder-owned final answers;
- layered decision-only, deterministic orchestration, and bounded live
  end-to-end tool-belt evaluations;
- offline API, orchestration, schema, database, and smoke-runner tests.

Not implemented yet:

- chat-routed synthesis, artifact retrieval, and artifact feedback workflows;
- governed-memory personalization for structured synthesis;
- durable background jobs;
- the browser workspace;
- authentication and public Cloud Run deployment.

## Contest category

**Collaborative Partner**

The intended judge-facing workflow is:

1. Ingest messy text, Markdown, or a PDF rubric.
2. Ask a consequential clarifying question.
3. Create a strict, validated project blueprint.
4. Save the artifact and execution state in Firestore.
5. Capture accepted, rejected, or edited recommendations.
6. Apply approved profile signals to a later blueprint.

## Technology

- Python and FastAPI
- Google GenAI SDK and Gemini 3.6 Flash on Vertex AI
- Google Cloud Firestore
- Google Cloud Tasks for the target durable asynchronous synthesis phase
- Docker and Google Cloud Run for the target deployment phase
- HTML, static CSS or TailwindCSS, and Vanilla JavaScript for the target browser
  workspace

See [Architecture](docs/architecture.md) for current and target data flows.

## Local setup

The complete reproducible setup is in
[Local development setup](docs/development/local-setup.md). The short path is:

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
```

Enable Vertex AI and configure Application Default Credentials for local
Firestore and model access:

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

The application does not use a Gemini API key. Vertex AI and Firestore use
the authenticated ADC identity. The pinned GenAI SDK calls its current Vertex
backend selector `enterprise`; the older `GOOGLE_GENAI_USE_VERTEXAI` alias is
deprecated and must not be configured.

Run the server:

```bash
uvicorn main:app --reload
```

The health endpoint is available at `http://127.0.0.1:8000/`.

With Uvicorn running, verify the durable chat-turn boundary from another
activated terminal:

```bash
python3 smoke_test_chat_idempotency.py
```

Success reports `first=200 replay=200 conflict=409 replay_equal=true` and safe
Firestore locators. It does not print the key, prompts, or model response.

## Tests

Run the offline automated suite:

```bash
pytest
```

See [Testing](docs/development/testing.md) for focused commands, test-layer
boundaries, live smoke checks, and the complete core tool-belt evaluation.

## Security status

The current API is local-development-only. Request-provided user and session
identifiers are not an authorization boundary. Do not expose this revision as
a public Cloud Run service.

## Submission material

- [Architecture](docs/architecture.md)
- [Chat turn idempotency](docs/design/turn-idempotency.md)
- [Local development setup](docs/development/local-setup.md)
- [Testing](docs/development/testing.md)
- [Core tool-belt evaluation closure](docs/superpowers/specs/2026-08-23-m7-exp-7c-core-tool-belt-evaluation-closure.md)
- [Troubleshooting](docs/development/troubleshooting.md)
- [Submission checklist](docs/submission-checklist.md)
- [Phase 3 design](docs/superpowers/specs/2026-08-19-phase-3-synthesis-engine-design.md)

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

Original-project attribution is recorded in [NOTICE](NOTICE).
