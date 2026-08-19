# Phase 3 v5 Contest-Aligned Agentic Synthesis Design

## Goal

Build the judged Agent_Col workflow in three independently testable stages:

1. **Phase 3A — Structured synthesis core:** synchronously convert untrusted
   source material into a validated, project-owned blueprint.
2. **Phase 3B — Supervisor and feedback loop:** let Agent_Col invoke synthesis
   through a strict tool contract and turn explicit feedback into inspectable,
   allowlisted profile adaptations.
3. **Phase 3C — Durable background synthesis:** enqueue synthesis with Cloud
   Tasks, persist job state, recover safely from retries, and return results
   through the project workspace.

This document defines the shared architecture and the complete Phase 3A
contract. Phase 3B and Phase 3C receive separate approval-gated implementation
plans after Phase 3A is manually accepted.

## Contest Outcome

The completed workflow must prove that Agent_Col:

- actively transforms messy data instead of merely discussing it;
- asks clarifying questions and guides the user through consequential choices;
- captures accepted, rejected, or edited recommendations;
- adapts later work only from approved profile signals;
- separates supervisor, synthesis, persistence, and feedback responsibilities;
- exposes observable proof through UI state, Firestore artifacts, job state,
  and Cloud Run logs.

## Shared Architecture

### Agent_Col supervisor

Owns conversation and tool selection. It may request synthesis but cannot
write arbitrary Firestore records or mutate the profile directly.

### Synthesizer

Owns prompt construction, bounded context, Gemini structured generation,
local validation, and personalization-trace validation. It has no Firestore or
HTTP responsibility.

### MemoryEngine

Owns Firestore queries and persistence. It is deterministic and contains no
Gemini configuration or Pydantic synthesis models.

### Profile updater

Owns the allowlist and provenance rules for explicit user feedback. It is a
deterministic service and is not marketed as an LLM agent.

### FastAPI

Owns request validation, concurrency, identity and ownership integration,
status-code translation, and response construction. Phase 3A remains local
development only; public identity and ownership arrive before deployment.

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

A session stores its owning `project_id`. A blueprint belongs to a project and
stores its `originating_session_id`. Phase 3A validates identifiers but does
not yet enforce ownership because identity remains local-development-only.

## Phase 3A Scope

Phase 3A creates:

- strict synthesis and HTTP contracts in `schemas.py`;
- synthesis prompting and domain validation in `synthesis.py`;
- bounded recent-history reads and project-owned blueprint persistence in
  `database.py`;
- a thin synchronous-waiting, asynchronous-I/O `/api/synthesize` route in
  `main.py`;
- permanent offline tests split by responsibility;
- a Firestore index exemption for the stored blueprint map.

Phase 3A does not add supervisor function calling, feedback endpoints,
background jobs, authentication, ownership enforcement, rate limiting,
uploads, a frontend, or public deployment.

## File Responsibilities

### `schemas.py`

Contains Phase 3 Pydantic models and reusable constrained types. It imports no
Gemini, Firestore, or FastAPI route logic.

### `synthesis.py`

Contains the synthesis instruction, profile allowlisting, history budgeting,
prompt construction, Gemini generation, Pydantic parsing, and personalization
domain validation. It performs no HTTP handling or Firestore writes.

### `database.py`

Contains Firestore operations. It does not import synthesis models or Gemini
configuration.

### `main.py`

Contains the endpoint, concurrent reads, error translation, serialization,
and response construction. It delegates generation and persistence.

## Strict Pydantic Contracts

Every model uses `ConfigDict(extra="forbid")`. Descriptive strings strip
surrounding whitespace and reject empty values. Collection bounds are enforced
by Pydantic and the Gemini result is always validated locally.

Reusable types:

- `NonEmptyStr`: stripped string with a minimum length of 1;
- `IdentifierStr`: 1 through 128 ASCII letters, digits, underscores, or
  hyphens;
- `SourceText`: stripped string from 1 through 10,000 characters.

### Conceptual model

`ConceptualModel` contains:

- `project_name: NonEmptyStr`;
- `core_value_proposition: NonEmptyStr`;
- `in_scope: list[NonEmptyStr]` with at least one item;
- `out_of_scope: list[NonEmptyStr]`, which may be empty;
- `assumptions: list[NonEmptyStr]`, which may be empty.

`project_name` is human-readable. A future filesystem or URL slug is derived
deterministically by its consumer rather than generated by Gemini.

### Personalization trace

`PersonalizationAdaptation` contains:

- `profile_key: NonEmptyStr`;
- `architecture_change: NonEmptyStr`;
- `reason: NonEmptyStr`.

`PersonalizationTrace` contains
`adaptations: list[PersonalizationAdaptation]`, which may be empty.

Only these top-level profile keys may enter the synthesis prompt:

- `experience_level`;
- `preferred_languages`;
- `preferred_frameworks`;
- `learning_style`;
- `response_detail`;
- `accessibility_preferences`.

After Pydantic parsing, application validation enforces:

- an empty allowlisted profile requires an empty adaptations list;
- every adaptation `profile_key` exists in the allowlisted input profile;
- an invalid trace fails before any blueprint write.

The trace identifies keys but never copies raw profile values. Logs contain
neither profile keys nor values.

### Architectural decisions

`ArchitecturalAlternative` contains:

- `option_name: NonEmptyStr`;
- `tradeoff: NonEmptyStr`;
- `reason_not_selected: NonEmptyStr`.

`ArchitecturalDecision` contains:

- `component_name: NonEmptyStr`;
- `proposed_solution: NonEmptyStr`;
- `rationale: NonEmptyStr`;
- `alternatives: list[ArchitecturalAlternative]` with at least one item.

The blueprint contains at least one architectural decision.

### Socratic questions

`ClarifyingOption` contains:

- `label: NonEmptyStr`;
- `impact: NonEmptyStr`.

`ClarifyingQuestion` contains:

- `question_text: NonEmptyStr`;
- `why_this_matters: NonEmptyStr`;
- `suggested_options: list[ClarifyingOption]` with two or three items.

The blueprint contains at least one clarifying question.

### Execution roadmap

`MicroTask` contains:

- `task_description: NonEmptyStr`;
- `complexity_level: Literal["Low", "Medium", "High"]`;
- `verification_steps: list[NonEmptyStr]` with at least one item.

`RoadmapMilestone` contains:

- `phase_name: NonEmptyStr`;
- `objective: NonEmptyStr`;
- `expected_deliverable: NonEmptyStr`;
- `micro_tasks: list[MicroTask]` with at least one item.

The blueprint contains at least one roadmap milestone. List order defines
execution order; no generated ordinal is stored.

### Diagnostic warnings

`DiagnosticWarning` contains:

- `affected_component: NonEmptyStr`;
- `severity: Literal["Low", "Medium", "High", "Critical"]`;
- `risk_identified: NonEmptyStr`;
- `preventative_guidance: NonEmptyStr`.

`diagnostic_warnings` defaults to an empty list because inventing a warning is
worse than returning none.

### Top-level models

`SynthesisBlueprint` contains:

- `synthesized_conceptual_model: ConceptualModel`;
- `personalization_trace: PersonalizationTrace`;
- `architectural_decisions_and_feedback: list[ArchitecturalDecision]` with at
  least one item;
- `socratic_clarifying_questions: list[ClarifyingQuestion]` with at least one
  item;
- `step_by_step_execution_roadmap: list[RoadmapMilestone]` with at least one
  item;
- `diagnostic_warnings: list[DiagnosticWarning]` defaulting to an empty list.

`schema_version` remains server-owned persistence metadata and is not generated
by Gemini.

`SynthesisRequest` contains:

- `project_id: IdentifierStr`;
- `session_id: IdentifierStr`;
- `user_id: IdentifierStr` for local Phase 3A only;
- `source_text: SourceText`.

The public deployment later removes trust in the request `user_id` and derives
identity from a verified token.

`SynthesisResponse` contains:

- `blueprint_id: NonEmptyStr`;
- `blueprint: SynthesisBlueprint`.

## Recent Session Context

`MemoryEngine.get_chat_history` becomes:

```python
async def get_chat_history(
    self,
    session_id: str,
    limit: int | None = None,
) -> list[dict[str, object]]:
```

Behavior:

- validates `session_id` before Firestore access;
- `limit=None` preserves the existing complete ascending-history behavior;
- rejects booleans, non-integers, values below 1, and values above 100 before
  Firestore access;
- a supplied limit queries newest messages in descending timestamp order,
  applies the Firestore limit, and reverses the collected results;
- `/api/chat` initially retains its existing unlimited call;
- `/api/synthesize` requests `limit=20` explicitly.

The synthesis layer additionally caps serialized history at 20,000 characters
by keeping the newest complete messages that fit and returning them in
chronological order.

## Project-Owned Blueprint Persistence

`MemoryEngine.save_blueprint` has this Phase 3A interface:

```python
async def save_blueprint(
    self,
    project_id: str,
    session_id: str,
    user_id: str,
    model_name: str,
    blueprint: dict[str, object],
) -> str:
```

Before Firestore access, it validates the first four arguments as non-empty
strings and `blueprint` as a non-empty dictionary.

It creates an auto-ID document at
`projects/{project_id}/blueprints/{blueprint_id}`. One asynchronous batch:

1. merge-updates the parent project with
   `updated_at=firestore.SERVER_TIMESTAMP`;
2. writes the child blueprint with:
   - `created_at=firestore.SERVER_TIMESTAMP`;
   - `originating_session_id=session_id`;
   - `user_id` as temporary local-development provenance;
   - `model_name`;
   - `schema_version="1.0"`;
   - `blueprint`.

The method awaits the commit and returns `blueprint_ref.id`. A
`GoogleAPIError` becomes `MemoryEngineError` with the provider exception as its
cause. Logs contain only the operation name.

The stored `blueprint` map receives a Firestore single-field index exemption
because Phase 3 does not query its nested generated fields.

## Structured Generation

Phase 3A uses the existing Google GenAI Generate Content API:

```python
response = await client.aio.models.generate_content(
    model="gemini-3.6-flash",
    contents=contents,
    config=types.GenerateContentConfig(
        system_instruction=SYNTHESIS_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=SynthesisBlueprint,
        temperature=0.2,
        max_output_tokens=8192,
    ),
)
```

`synthesis.generate_blueprint`:

1. allowlists the profile;
2. budgets recent history;
3. JSON-serializes profile and history;
4. places profile, history, and source text in separately labeled untrusted
   data sections;
5. instructs Gemini not to follow instructions found in those sections;
6. runs generation under a 60-second `asyncio.timeout`;
7. requires non-empty `response.text`;
8. calls `SynthesisBlueprint.model_validate_json(response.text)`;
9. validates the personalization trace against the allowlisted profile;
10. returns the validated model.

Provider failures, empty responses, JSON failures, Pydantic failures, and
personalization failures become `SynthesisEngineError`. A timeout becomes
`SynthesisTimeoutError`. Original exceptions remain available as causes. Logs
contain only exception class names and never inputs or outputs.

## Phase 3A Endpoint

`POST /api/synthesize` performs:

1. FastAPI and Pydantic request validation;
2. concurrent `get_user_profile(user_id)` and
   `get_chat_history(session_id, limit=20)` calls with `asyncio.gather`;
3. synthesis through `generate_blueprint`;
4. serialization through `blueprint.model_dump(mode="json")`;
5. project-owned atomic persistence through `save_blueprint`;
6. `SynthesisResponse(blueprint_id=..., blueprint=blueprint)`.

Failure mapping:

- request validation: HTTP 422;
- Firestore read or write failure: HTTP 500 and
  `{"detail": "Database operation failed."}`;
- synthesis or local validation failure: HTTP 502 and
  `{"detail": "Blueprint generation failed."}`;
- generation timeout: HTTP 504 and
  `{"detail": "Blueprint generation timed out."}`.

No generation or validation failure writes a blueprint. A persistence failure
does not return an unsaved artifact as successful.

## Phase 3B Contract Boundary

Phase 3B adds an explicit Supervisor tool that accepts `project_id`,
`session_id`, and source input and returns an artifact or job reference.
Structured output formats the Synthesizer result; function calling requests
the application action.

Feedback events support:

- `decision: Literal["accepted", "rejected", "edited"]`;
- `blueprint_id`;
- a validated blueprint component path;
- an optional correction required for `edited`;
- a server timestamp;
- an optional allowlisted profile update derived from explicit user input;
- provenance connecting the profile signal to its feedback event.

The user can inspect and delete stored profile signals. Phase 3B must prove
that a later blueprint references an approved signal in its personalization
trace and changes an actual recommendation.

## Phase 3C Contract Boundary

The final public synthesis contract becomes:

```text
POST /api/projects/{project_id}/synthesis-jobs -> HTTP 202
GET  /api/projects/{project_id}/synthesis-jobs/{job_id}
```

The public request creates a Firestore job and enqueues Cloud Tasks. The
private worker advances the job through:

```text
queued -> running -> completed
                  -> failed
```

Every request carries a deterministic idempotency key. A task retry resumes or
returns the existing result rather than creating a duplicate blueprint. The
worker stores failure codes but no source text or generated content in logs.

## Test Architecture

### `tests/test_schemas.py`

- valid nested round-trip;
- forbidden extra fields;
- blank strings;
- project, session, user, and source bounds;
- option and top-level collection bounds;
- invalid complexity and severity;
- empty personalization and warning lists.

### `tests/test_synthesis.py`

- profile allowlisting;
- newest-message character budgeting;
- untrusted prompt section separation;
- exact model and generation configuration;
- valid response parsing;
- empty-profile and unknown-key personalization rejection;
- provider, timeout, empty-response, JSON, and Pydantic failures;
- content-safe logs.

### `tests/test_database.py`

- unlimited history remains ascending;
- limited history returns newest messages chronologically;
- invalid limits fail before Firestore access;
- atomic project and blueprint writes;
- timestamps, originating session, model, schema version, and auto ID;
- blueprint input validation;
- safe error translation with preserved causes.

### `tests/test_main.py`

- successful project-owned synthesis;
- concurrent profile and bounded-history reads;
- exact `limit=20` request;
- malformed, blank, invalid-identifier, and oversized requests;
- Firestore failures at read and write boundaries;
- synthesis, parsing, personalization, and timeout mapping;
- no persistence after generation failure;
- logs omit every identifier and all user or generated content.

## Phase 3A TDD Order

1. strict Pydantic contracts;
2. bounded recent history;
3. atomic project-owned blueprint persistence;
4. synthesis profile and history helpers;
5. Gemini generation and local domain validation;
6. HTTP orchestration;
7. index configuration and final verification.

Each behavior must be observed failing for the intended missing behavior before
production code is written.

## Public Deployment Gate

Phase 3A trusts identifiers only for local development. Public deployment is
prohibited until the project has:

- backend-verified authenticated identity;
- project and session ownership;
- request, rate, and upload limits;
- idempotent synthesis jobs;
- authenticated private worker delivery;
- production monitoring and privacy review;
- documented retention and deletion;
- cost controls and maximum instance limits.

## Phase 3A Acceptance Criteria

- Strict contracts reject unexpected fields and invalid boundaries.
- `project_id` is mandatory and blueprints persist under projects.
- Gemini output is locally Pydantic- and domain-validated.
- Empty profiles cannot produce personalization adaptations.
- Prompt context is allowlisted, bounded, and treated as untrusted.
- Recent history remains chronological after limiting.
- Persistence is atomic and returns the blueprint ID.
- Failures and logs disclose no user or generated content.
- The complete offline suite passes without Firestore or Gemini network access.
- A manually invoked Gemini smoke test proves the selected model accepts the
  Pydantic response schema.
- No public Cloud Run deployment occurs during Phase 3A.
