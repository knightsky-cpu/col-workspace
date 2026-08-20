# Agent_Col Documentation and Reproducibility Contract

## Status and authority

Documentation is a first-class submission artifact. It is part of the product,
not cleanup performed after implementation.

Every documented command, feature, architecture claim, and test result must be
verified against the repository revision being described. Planned behavior
must be labeled as planned. Secrets, credentials, private identifiers, and raw
user data must never appear in committed examples.

## Purpose

Agent_Col must be reproducible by a technically competent developer who has
never seen the repository. Documentation must explain:

- what the system does;
- why each architectural boundary exists;
- what problem the boundary solves;
- what is implemented versus planned;
- how trustworthy collaboration and memory work;
- how the behavior is tested;
- how to reproduce it from a clean clone.

The documentation supports hackathon judging, public repository review,
portfolio presentation, future maintenance, and incident recovery.

## Required documentation structure

The target maintained structure is:

```text
README.md
docs/
├── architecture/
│   ├── system-architecture.md
│   ├── diagrams/
│   └── data-flow.md
├── development/
│   ├── local-setup.md
│   ├── testing.md
│   └── troubleshooting.md
├── design/
│   ├── agent-identity.md
│   ├── memory-model.md
│   ├── tool-contracts.md
│   └── security-boundaries.md
├── deployment/
│   ├── cloud-run.md
│   ├── firestore.md
│   └── environment.md
└── submission/
    ├── demo-script.md
    ├── judging-checklist.md
    └── technology-summary.md
```

This tree is a delivery target, not a claim about the current checkout. It
must be introduced through bounded documentation passes so that placeholders
and duplicated, contradictory documents are not created merely to fill paths.

## README contract

`README.md` must contain the following verified sections.

### 1. Project overview

Use the general collaborative-partner identity:

> Modern AI systems are powerful but often lack continuity. Agent_Col creates
> a persistent collaborative relationship by remembering approved user
> preferences, adapting future interactions, and orchestrating specialized
> capabilities while maintaining user control.

Do not describe Agent_Col as only a coding assistant.

### 2. Features

Document implemented and planned capabilities separately.

Core collaboration:

- conversational partner behavior;
- clarifying questions;
- iterative refinement;
- explicit feedback collection.

Memory:

- cross-session continuity;
- explicit preference learning;
- provenance tracking;
- user inspection, correction, revocation, and deletion;
- explainable adaptation.

Agent capabilities:

- supervisor orchestration;
- synthesis workflows;
- specialist tools;
- evidence-backed responses;
- tool restraint.

Infrastructure:

- Firestore persistence;
- Cloud Run deployment;
- Google ADK and Google GenAI SDK integration.

### 3. Architecture overview

Include and explain this responsibility flow:

```text
Browser or client
        ↓
FastAPI application boundary
        ↓
Agent_Col supervisor
        ↓
Bounded tools and specialists
        ↓
Deterministic application services
        ↓
Firestore source of truth
```

The explanation must distinguish temporary ADK execution state from durable
Firestore memory.

### 4. Technology stack

Document exact supported or pinned versions for:

- Python;
- FastAPI;
- Google GenAI SDK;
- Google ADK;
- the Gemini model identifier;
- Google Cloud Firestore;
- Google Cloud Run runtime configuration;
- pytest and pytest-asyncio.

Versions must come from the tested dependency and deployment files, not human
memory.

### 5. Local development

Provide tested commands for:

1. cloning the repository;
2. creating and activating the virtual environment on macOS and Linux;
3. installing production and development dependencies;
4. configuring the environment without committing secrets;
5. configuring Firestore emulator or development credentials;
6. running focused and complete test suites;
7. starting the application;
8. checking the health endpoint;
9. stopping and cleaning up local services safely.

### 6. Environment variables

Document every environment variable in a table containing:

- name;
- purpose;
- required or optional status;
- safe example format;
- local, test, and deployed behavior;
- secret-management expectations.

Never include a real key, token, credential path, user identifier, project
identifier, or copied `.env` content.

### 7. Testing

Explain the exact commands and protection boundaries for:

- schemas and semantic validation;
- memory persistence and provenance;
- synthesis and requirement coverage;
- supervisor routing and restraint;
- tool contracts and action receipts;
- security boundaries and safe logging;
- API integration;
- explicit live tests that are excluded from pytest.

### 8. Reproduction guide

A new developer must be able to:

1. clone the repository;
2. configure the supported environment;
3. start required local or Google Cloud services;
4. create a user, session, and project through documented interfaces;
5. send a chat request;
6. invoke an appropriate specialist workflow;
7. provide explicit feedback;
8. inspect the saved provenance;
9. begin a new session;
10. observe and explain memory-based adaptation.

## Agent identity documentation

`docs/design/agent-identity.md` must expand the governing root directive
without contradicting it. It must state that Agent_Col is not only a coding
assistant, project manager, or document generator.

## Memory documentation

`docs/design/memory-model.md` must distinguish:

Temporary state:

- one ADK invocation;
- transient tool arguments and intermediate results;
- request-scoped context.

Persistent state:

- explicitly approved preferred name and broad role context;
- approved preferences;
- feedback history and provenance;
- active and revoked collaboration signals;
- bounded collaboration history;
- artifacts and their ownership metadata.

It must answer what is remembered, why it is remembered, who approved it, how
it affected behavior, and how it is inspected, corrected, revoked, or deleted.

It must classify preferred names as PII and broad roles as personal data,
explain why those low-sensitivity fields are allowed, and distinguish them from
prohibited sensitive PII, contact details, credentials, exact institutions,
health, finances, precise location, and inferred private traits.

Use **explicit feedback-driven adaptation**. Never claim that the agent
secretly or autonomously learns private facts about users.

## Architecture decision records

Major irreversible or cross-cutting decisions require ADRs. The initial set is:

- ADR-001: FastAPI remains the application boundary;
- ADR-002: Firestore remains the durable source of truth;
- ADR-003: ADK supervision is hybrid rather than replacing the application;
- ADR-004: deterministic services validate model-selected actions;
- ADR-005: durable memory requires explicit user feedback and provenance.

Each ADR must record context, decision, alternatives, consequences, security
effects, migration impact, and verification evidence.

## Demo documentation

`docs/submission/demo-script.md` must prove:

1. Agent_Col asks a meaningful question.
2. The user provides or corrects a preference.
3. The user approves the durable adaptation.
4. Agent_Col stores the feedback event and provenance.
5. A new session begins.
6. Agent_Col retrieves the approved preference.
7. Agent_Col changes a collaborative response because of that preference.
8. The UI and Firestore evidence show why the change occurred.

The demo must not depend on claims that the viewer cannot observe.

## Documentation quality rules

Every component document must answer:

- What does this component do?
- Why does it exist?
- What problem does it solve?
- What does it trust and not trust?
- What are its side effects and failure boundaries?
- How is it tested?
- How can another developer reproduce its behavior?

Documentation must also:

- use repository-relative links;
- name exact routes, commands, files, and schema versions;
- label platform-specific steps for macOS and Linux;
- use copy-safe one-line commands when shell continuation is unnecessary;
- show expected output or falsifiable pass criteria;
- identify commands that incur cloud cost or mutate live data;
- distinguish offline automated verification from live manual evidence;
- record the revision or release to which generated evidence applies;
- avoid aspirational language in implemented-feature lists;
- remain consistent with tests and current source.

## Documentation verification gate

Before a documentation checkpoint:

1. Validate internal links and referenced paths.
2. Run every changed non-destructive command from the documented environment.
3. Mark destructive, billable, credentialed, or deployment commands for manual
   approval instead of executing them automatically.
4. Compare implemented-feature claims against source and tests.
5. Confirm secrets and private runtime values are absent.
6. Run Markdown and diagram validation when the repository provides it.
7. Record anything that could not be verified and why.

## Current documentation gap

As of August 20, 2026, the repository contains a useful README, architecture
summary, submission checklist, and detailed implementation specifications. It
does not yet contain the complete target structure, clean-clone reproduction
evidence, ADR set, deployment runbooks, memory lifecycle guide, or finished
cross-session demo script required by this contract. Those are planned
deliverables and must not be marked complete prematurely.
