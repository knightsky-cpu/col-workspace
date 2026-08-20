# Phase 3B Task 4B: Synthesis Schema v2 Design

## Status

This document records the schema and evaluation decisions approved in the
Phase 3B Task 4B discussion. It refines the Phase 3 synthesis design without
changing the supervisor, HTTP ownership, or Firestore collection layout.

## Goal

Make a generated blueprint bounded, semantically consistent, provider-safe,
and measurable before exposing synthesis as an ADK supervisor tool.

## Identity Contract

`project_id` remains the application-owned machine identifier. It is validated
as `IdentifierStr` and is the only project value used in Firestore paths.

`project_name` remains a Gemini-generated human-readable display-name proposal
captured in the conceptual model. It may contain spaces, capitalization,
punctuation, and Unicode. It never becomes a path, slug, ownership key, or an
automatic update to the parent project document.

## Schema Version and Naming

New blueprints use schema version `2.0`. Existing `1.0` development documents
remain untouched. Reading or migrating historical `1.0` artifacts is outside
Task 4B and must be resolved before the artifact-read endpoint is public.

The generated field `architectural_decisions_and_feedback` becomes
`architectural_decisions`. Generated rationale is not user feedback. Explicit
accepted, rejected, or edited feedback remains a separate future Firestore
record and profile-provenance workflow.

## Canonical Bounds

The authoritative local Pydantic contract uses these limits:

| Value | Limit |
| --- | --- |
| Project display name | 1-120 characters |
| Short label or component name | 1-160 characters |
| Explanatory generated text | 1-1,500 characters |
| Verification step | 1-500 characters |
| In-scope items | 1-10 |
| Out-of-scope items | 0-10 |
| Assumptions | 0-10 |
| Personalization adaptations | 0-8 |
| Architectural decisions | 1-8 |
| Alternatives per decision | 1-3 |
| Clarifying questions | 1-5 |
| Suggested options per question | 2-3 |
| Roadmap milestones | 1-8 |
| Micro-tasks per milestone | 1-10 |
| Verification steps per task | 1-5 |
| Diagnostic warnings | 0-10 |
| Serialized blueprint | At most 131,072 UTF-8 bytes |

The size policy is intentionally below Firestore's 1 MiB document maximum. It
protects model context, API payloads, browser rendering, and persistence from
pathological output rather than attempting to consume the provider limit.

All generated fields receive precise Pydantic `Field` descriptions. Optional
lists remain optional and default to empty. Small legitimate projects are not
forced to invent multiple decisions, phases, or warnings.

## Provider Schema Boundary

`SynthesisBlueprint` remains the single canonical model. Gemini does not
receive its raw `model_json_schema()` result.

A pure schema adapter deep-copies the canonical schema and recursively removes
the local-only string keywords `minLength`, `maxLength`, and `pattern` from
schema nodes before the request. It does not remove model properties or
definitions that happen to use one of those words as a name. It preserves the
proven object shape, required fields, `additionalProperties`, definitions and
references, enums, descriptions, and array `minItems` and `maxItems`
constraints.

Local parsing always uses `SynthesisBlueprint.model_validate_json()`. Provider
schema compliance never replaces local validation.

## Semantic Validation

A deterministic blueprint validator runs after Pydantic parsing and before
persistence. Comparison uses stripped, case-folded text.

It rejects:

- overlap between `in_scope` and `out_of_scope`;
- duplicate scope items or assumptions;
- duplicate architectural component names;
- duplicate alternatives inside one decision;
- duplicate option labels inside one clarifying question;
- duplicate roadmap phase names;
- duplicate micro-task descriptions inside one milestone;
- duplicate verification steps inside one micro-task;
- duplicate diagnostic risks;
- exact duplicate personalization adaptations;
- adaptations when no allowlisted profile context exists;
- adaptations that reference an absent allowlisted profile key;
- serialized blueprints larger than 131,072 UTF-8 bytes.

The validator does not use word matching to pretend it can prove whether prose
is insightful, Socratic, or technically correct.

## Persistence Contract

`MemoryEngine` remains synthesis-schema agnostic. `save_blueprint` receives a
validated `schema_version` argument rather than importing a Pydantic model or
hard-coding the active version. `SynthesisApplicationService` supplies `2.0`.

The existing atomic parent update and blueprint child write are preserved.

## Quality Evaluation

Quality is measured separately from validity. A permanent deterministic
evaluator consumes versioned scenario fixtures and checks:

- required concept groups, where any approved phrase may satisfy a concept;
- forbidden claims;
- expected personalization keys;
- minimum and maximum structural counts;
- the canonical schema and semantic validator.

The initial live scenarios cover a small API, contradictory requirements,
empty profile, profile-aware adaptation, prompt injection, known Agent_Col
architecture, ambiguity, and repetition. Offline tests use canned blueprints.
No network or model call runs in pytest.

A command-line runner invokes real Gemini only when explicitly launched,
prints one result per scenario, exits nonzero on any failed rule, and closes
the GenAI client on success or failure. Model-as-judge evaluation is excluded
from Task 4B.

## Delivery Boundaries

Task 4B is delivered as three independently accepted passes:

1. Provider-safe schema adapter with no public response-shape change.
2. Canonical v2 contract, semantic validator, and persistence version update.
3. Offline evaluator, versioned fixtures, and explicit live runner.

Task 4B does not register an ADK synthesis tool, add artifact retrieval,
migrate historical Firestore documents, change authentication, tune the
frontend, or introduce a second model as an acceptance judge.

## Stop Conditions

Stop and revise the design if:

- the installed GenAI SDK rejects the adapted provider schema;
- a v2 bound causes valid small or medium blueprints to fail repeatedly;
- local validation cannot distinguish generated content from server metadata;
- a schema-version change requires an unapproved historical-data migration;
- the quality fixtures require brittle exact prose instead of concepts;
- a pass would leave the live synthesis endpoint knowingly broken.
