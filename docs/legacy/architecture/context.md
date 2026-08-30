# Project Context: Agent_Col Workspace

> **Archived August 21, 2026.** This snapshot predates the accepted governed
> memory lifecycle and chat-turn idempotency work. Its phase status and data
> model are no longer authoritative. Use the root `README.md`, current design
> contracts, and current source instead.

## Product Goal

Agent_Col is a Collaborative Partner web application for the Devpost All
Things Agentic Hackathon. It helps students and builders turn messy notes,
brainstorms, rubrics, and project documents into structured, verifiable
project blueprints. It asks clarifying questions, captures explicit feedback,
and adapts later recommendations to approved user preferences.

## Contest Positioning

- **Category:** Collaborative Partner
- **Core proof:** Agent_Col actively transforms unstructured source material;
  it does not merely summarize or chat about it.
- **Agent workflow:** Agent_Col supervises the interaction and invokes a
  specialized Synthesizer through a strict tool boundary.
- **Learning proof:** User feedback becomes allowlisted, editable profile
  signals that visibly affect later blueprints.
- **Execution proof:** Firestore artifacts, job-state changes, application UI,
  and Cloud Run logs show the work being performed.

## Technology Stack

- **Frontend:** HTML5, TailwindCSS or compiled static CSS, and Vanilla
  JavaScript served by FastAPI
- **Backend:** Asynchronous FastAPI on Python
- **Agent orchestration:** Google GenAI SDK with Gemini 3.6 Flash
- **Database and memory:** Google Cloud Firestore
- **Durable background work:** Google Cloud Tasks invoking a private Cloud Run
  worker endpoint
- **Containerization:** Docker
- **Hosting:** Google Cloud Run
- **Judge access:** Firebase anonymous authentication before public deployment

Cloud Run can scale to zero and the application is designed to remain within
available free tiers or hackathon credits. Free operation is not guaranteed.

## System Boundaries

### Agent_Col supervisor

Owns conversation, clarification, feedback, and the decision to invoke a
specialized tool. It does not write arbitrary Firestore data directly.

### Synthesizer worker

Uses Gemini structured output to convert untrusted source material and bounded
context into a locally validated `SynthesisBlueprint`.

### MemoryEngine

Is a deterministic Firestore persistence service, not an LLM agent. It owns
sessions, messages, projects, blueprints, jobs, feedback events, and profile
records.

### Profile updater

Is a deterministic allowlisted service. It records only explicit user
preferences with provenance and never invents permanent traits from casual
conversation.

## Canonical Firestore Model

```text
users/{user_id}
projects/{project_id}
projects/{project_id}/blueprints/{blueprint_id}
projects/{project_id}/feedback/{feedback_id}
projects/{project_id}/jobs/{job_id}
sessions/{session_id}
sessions/{session_id}/messages/{message_id}
```

Sessions reference their owning project. Blueprints belong to projects and
record the session that supplied their conversational context.

## Development Status

- **Phase 1 — Local foundation:** Backend health and Gemini chat work. A static
  frontend shell and bounded chat context remain.
- **Phase 2 — Durable memory:** Asynchronous Firestore message and profile
  operations work and have offline tests. Project ownership, feedback events,
  and the actual profile-learning loop remain.
- **Phase 3A — Structured synthesis core:** Implemented, tested, and manually
  verified with live Gemini generation and Firestore persistence.
- **Phase 3B — Supervisor and feedback loop:** Hybrid ADK runtime and
  supervisor-controlled chat are implemented. Blueprint schema v2 validation
  is in progress; synthesis delegation and the feedback loop remain.
- **Phase 3C — Durable background synthesis:** Planned.
- **Phase 4 — Judge-facing workspace:** Not started.
- **Phase 5 — Security, Cloud Run deployment, and submission:** Not started.

## Security Gate

Local development may temporarily accept request-provided identifiers. No
public deployment is permitted until authenticated identity, project and
session ownership, request limits, upload limits, idempotency, safe logging,
and cost controls are in place.

## Working Method

Every source-changing pass follows the repository's approval-gated TDD
workflow in [`AGENTS.md`](../../../AGENTS.md). Accepted work is manually verified
before any Git checkpoint or push.
