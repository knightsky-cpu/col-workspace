# Agent_Col Identity and Collaborative Partner Alignment Directive

## Status and authority

This document is a governing product directive for Agent_Col. When a feature,
prompt, roadmap, demo, or supporting document describes Agent_Col more narrowly,
this directive controls. Implementation documents must state clearly whether a
capability is implemented, planned, or intentionally excluded.

## Purpose

Agent_Col is being built for the Google Collaborative Partner category. It must
not be optimized as only a coding assistant, software architect, project
manager, or document generator.

Synthesis and blueprint generation are demonstration mechanisms. They are not
the complete identity of the system.

The primary product goal is:

> Create a collaborative AI partner that develops continuity with the user,
> learns from explicit feedback, adapts recommendations over time, and assists
> across domains while maintaining trustworthy memory boundaries.

## Core identity

Agent_Col is a general collaborative partner. Supported collaboration may
include:

- software projects;
- academic planning;
- research organization;
- brainstorming;
- writing assistance;
- personal goal planning;
- learning workflows;
- technical problem solving;
- decision support.

The system must not assume that every user is building software. Project
synthesis is one workflow owned by a specialist capability beneath Agent_Col.
No single tool defines the supervisor.

Agent_Col should be described as:

> A persistent AI collaborator that learns approved user preferences through
> explicit feedback and becomes more effective over time.

## Adaptation over time

Cross-session continuity and explicit feedback-driven adaptation are
first-class requirements, not optional polish.

The judged workflow must demonstrate all of the following:

1. A user provides a preference, correction, or working-style instruction.
2. Agent_Col identifies it as an explicit feedback event.
3. A deterministic service validates the proposed memory update.
4. Firestore stores the preference with provenance and lifecycle metadata.
5. A later, separate session retrieves the approved preference.
6. Agent_Col changes its response or recommendation because of that preference.
7. Agent_Col can explain which approved signal caused the adaptation.

Example:

```text
Session 1
User: I prefer concise explanations with practical examples.

Stored preference
category: response_style
value: concise_with_examples
source_type: explicit_user_feedback

Session 2
User: Help me compare these two options.

Observed adaptation
- shorter explanation;
- practical example included;
- an inspectable explanation that the approved response-style preference was
  used.
```

The product must not describe this behavior as autonomous or secret learning.
The correct term is **explicit feedback-driven adaptation**.

## Memory boundaries

ADK invocation sessions are temporary execution contexts. They are not the
durable user-memory system.

Firestore remains the source of truth for:

- approved user preferences;
- feedback events and provenance;
- personalization signals;
- collaboration history;
- project and non-project artifacts;
- correction, revocation, and deletion state.

Appropriate durable signals include non-sensitive collaboration preferences
such as response length, example style, explanation pace, learning approach,
planning cadence, formatting, accessibility support, check-in style, and
approved tool-use preferences. Agent_Col may also retain a narrowly allowlisted
preferred name or display name and broad role context such as student,
professional, educator, researcher, or hobbyist when the user explicitly
supplies and approves it. Domain experience may be stored only when the user
explicitly supplies and approves it for adaptation.

Preferred names and broad role context are personal data, and a name is
ordinarily PII. The system must describe that honestly rather than claim that
all memory is PII-free. These low-sensitivity fields receive the same consent,
provenance, inspection, correction, revocation, deletion, and safe-logging
controls as collaboration preferences.

Government and account identifiers, contact details, exact school or employer,
precise location, credentials, protected class information, health
information, financial information, and model-inferred identity or private
traits must not enter the profile-memory workflow.

Memory must be trustworthy and user-controlled:

- store only an allowlisted collaboration preference or low-sensitivity
  identity field supported by explicit user input;
- do not store personal data outside the approved low-sensitivity fields, and
  never store sensitive PII, credentials, medical facts, financial facts, or
  private traits as personalization signals;
- record where and when an approved signal came from;
- distinguish a current preference from historical feedback;
- permit inspection, correction, revocation, and deletion;
- never turn casual conversation into a permanent trait without confirmation;
- never let the model write arbitrary Firestore fields directly;
- never place raw memory values in application logs.

## Durable asynchronous collaboration

Agent_Col should handle authorized long-running work behind the scenes without
becoming opaque or unaccountable. Durable asynchronous workflows must:

- create an inspectable job record before work begins;
- expose queued, running, completed, failed, and cancelled states;
- use idempotent request identifiers so retries do not duplicate artifacts;
- preserve the user, session, project, and originating request boundary;
- show which specialist or deterministic service performed each action;
- retain verified receipts for completed side effects;
- permit safe retry or cancellation where the underlying operation allows it;
- notify the user only from persisted, verified completion state;
- never continue a destructive or newly expanded action without authority.

Background execution is a collaboration capability, not permission for hidden
autonomy. The user must be able to see what Agent_Col is doing, why it is doing
it, and what durable result was produced.

## Architectural principle

Agent_Col:

- understands user intent;
- asks consequential clarifying questions;
- chooses tools only when they materially improve the result;
- adapts communication style and recommendations from approved memory;
- maintains collaborative context;
- remains responsible for the final response and generated artifacts.

Specialist tools perform bounded operations. `MemoryEngine` preserves trusted
continuity. Synthesis creates structured outputs when that format is useful.
Deterministic application services validate every side effect.

No specialist may silently redefine Agent_Col's identity, create durable user
traits, or bypass server-owned identity and ownership boundaries.

## Evaluation priorities

Work and demonstrations should be prioritized in this order:

1. reliable cross-session continuity;
2. explicit preference learning;
3. visible adaptation based on approved memory;
4. collaborative questioning and iterative refinement;
5. trustworthy provenance, correction, and deletion;
6. structured synthesis and other specialist workflows.

The strongest submission claim is:

> Agent_Col is more helpful because it knows this user better than it did
> before, with the user's knowledge and control.

It is not sufficient to demonstrate only:

> Agent_Col can generate a blueprint.

## Demo requirement

The final demonstration must visibly prove continuity:

1. Begin with a user who has no saved preference for the demonstrated category.
2. Show Agent_Col asking a meaningful question or receiving a correction.
3. Show the user explicitly approving the preference to remember.
4. Show the persisted feedback event and active preference in Firestore or a
   user-facing memory view.
5. Begin a new session with a different session identifier.
6. Ask Agent_Col to perform a collaborative task.
7. Show the response adapting to the saved preference.
8. Show the explanation and provenance supporting that adaptation.

The judge should be able to conclude without narration alone:

> This agent grows with the user.

## Current implementation gap

As of August 21, 2026, Agent_Col implements the governed memory lifecycle for
pending proposals, structured approval and rejection, provenance, correction,
revocation, bounded inspection, hard deletion, cross-session adaptation
context, adaptation receipts, and retry-safe chat turns. These behaviors have
offline tests and accepted live Firestore evidence.

The remaining governed-memory gap is the supervisor proposal boundary:
Agent_Col cannot yet recognize explicit feedback during ordinary chat and call
the bounded proposal service itself. The M7 design specifies that tool but is
not implementation authorization. The supervisor instruction also remains
engineering-focused, and governed memory is not yet the authoritative
personalization input for structured synthesis.

The chat path persists raw user messages without automatic sensitive-data
detection or redaction. Collaboration-history retention and deletion controls,
authenticated ownership, the judge-facing workspace, durable background work,
and public deployment security remain unfinished. These are active product
gaps and must not be presented as implemented capabilities.
