# Agent_Col

Agent_Col is a Collaborative Partner for the Devpost All Things Agentic
Hackathon. It turns messy brainstorming, academic rubrics, notes, and project
documents into structured software-project blueprints, then uses explicit
feedback to adapt later recommendations.

## Current status

Agent_Col is under active development and is not publicly deployed.

Implemented today:

- asynchronous FastAPI health and chat endpoints;
- Gemini 3.6 Flash through the Google GenAI SDK;
- asynchronous Firestore message and profile persistence;
- atomic session/message writes;
- project-owned, atomically persisted structured synthesis blueprints;
- a hybrid ADK supervisor runtime controlling project-aware chat;
- strict local schema and semantic validation for blueprint version 2.0;
- offline API, orchestration, schema, and database tests.

Not implemented yet:

- supervisor tool invocation;
- feedback-driven profile learning;
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
- Google GenAI SDK and Gemini 3.6 Flash
- Google Cloud Firestore
- Google Cloud Tasks for durable asynchronous synthesis
- Docker and Google Cloud Run
- HTML, static CSS or TailwindCSS, and Vanilla JavaScript

See [Architecture](docs/architecture.md) for component and data-flow details.

## Local setup

Prerequisites:

- Python 3.13 or newer
- a Google Cloud project with Firestore in Native mode
- Google Cloud Application Default Credentials
- a Gemini API key

Create the environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Create an ignored `.env` file:

```dotenv
GOOGLE_API_KEY=replace-with-your-key
GOOGLE_CLOUD_PROJECT=replace-with-your-project-id
```

Configure local Firestore credentials and quota attribution:

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

Run the server:

```bash
uvicorn main:app --reload
```

The health endpoint is available at `http://127.0.0.1:8000/`.

## Tests

Run the automated suite:

```bash
pytest
```

## Security status

The current API is local-development-only. Request-provided user and session
identifiers are not an authorization boundary. Do not expose this revision as
a public Cloud Run service.

## Submission material

- [Architecture](docs/architecture.md)
- [Submission checklist](docs/submission-checklist.md)
- [Project context](context.md)
- [Phase 3 design](docs/superpowers/specs/2026-08-19-phase-3-synthesis-engine-design.md)

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

Original-project attribution is recorded in [NOTICE](NOTICE).
