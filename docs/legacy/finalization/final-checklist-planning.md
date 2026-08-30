# Agent Col Final Checklist Planning

Last reconciled: August 27, 2026.

## Status And Authority

This document is the current strategic finalization reference for the All
Things Agentic Hackathon submission track. It supersedes the old Winning Core
execution order for pre-submission work.

The current finalization strategy is:

> Reconcile the roadmap to the current strategy, close the two remaining
> Collaborative Partner behavioral gaps, productionize the accepted
> request-bound application, polish only what affects judging, package the
> evidence, and freeze.

Older durable-async plans remain useful engineering provenance, but they are
not prerequisites for the judged build unless the repository owner explicitly
reopens them.

## Official Competition Anchors

Primary official sources:

- All Things Agentic Official Rules:
  <https://allthingsagentichackathon.devpost.com/rules>
- Official Resources and Collaborative Partner deep dive:
  <https://allthingsagentichackathon.devpost.com/resources>
- Hackathon overview and deadline:
  <https://allthingsagentichackathon.devpost.com/>
- Official FAQ:
  <https://allthingsagentichackathon.devpost.com/details/faqs>

Validated requirements and judging targets:

- Category: Collaborative Partner.
- Mandatory stack: Gemini 3.5 or newer, at least one listed Google agent
  framework, and at least one Google Cloud infrastructure service.
- Current stack fit: Gemini 3.6 Flash through Vertex AI, Google ADK, Google
  GenAI SDK, Firestore, and planned Cloud Run deployment proof.
- Collaborative Partner emphasis: lead the way, take notes, ask clarifying
  questions, guide step by step, capture feedback, and adapt to the user's way
  of thinking.
- Judging weights: Innovation and Operational Utility 40%, Architectural
  Discipline and Tech Stack 30%, Demo and Production Readiness 30%.
- Submission package: selected category, hosted URL if available, project
  description, repository, spin-up instructions, architecture diagram, and a
  public YouTube or Vimeo video of four minutes or less.
- Video proof: demonstrate the backend running on Google Cloud.
- Availability nuance: the app does not have to remain publicly live at the
  exact judging moment, but Google Cloud deployment proof is mandatory and the
  submitted repo/video/site state should be preserved for judging.

## Deferred From Pre-Submission Scope

Durable asynchronous artifact work, Google Cloud Tasks, private worker
execution, worker IAM, queue authentication, job retry/cancellation, and
durable job-state demonstration are deferred until after submission.

They remain legitimate future work, but they are not current blockers for:

- Target A;
- Target B;
- single-service production hardening;
- Cloud Run proof;
- documentation convergence;
- visual polish;
- demo/freeze.

## Current Accepted Core

The accepted implementation already includes:

- browser workspace at `/workspace`;
- Google OIDC/local auth foundation;
- persisted chat sessions and retry-safe chat turns;
- governed profile memory with explicit approval and adaptation receipts;
- governed workspace notes and receipt-backed continuity;
- hidden same-session working state;
- four bounded specialist capabilities: Research, Source, Computation, and
  Requirements Verification;
- synchronous synthesis and request-bound artifacts;
- artifact lifecycle, versioning, and feedback surfaces.

See [Current state](../../current-state.md) for the source-level inventory.

## Product Target A - Evidence-Governed Preference Learning

Goal:

> Observation/correction evidence -> non-authoritative preference hypothesis
> -> user confirmation -> existing governed memory -> later adaptation.

This is a deliberate revision to the old M9 memory boundary. M9 correctly
forbade behavioral inference when the priority was preventing silent profiling.
The final Collaborative Partner target now allows a narrower, governed evidence
layer.

The new authority distinction is:

```text
observation evidence != preference hypothesis != candidate memory != active memory
```

Required boundaries:

- observations are bounded, validated, and non-authoritative;
- observations are workspace-scoped by default;
- observations can come from user corrections, repeated collaboration
  preferences, or explicit feedback patterns;
- raw transcript mining and generic model study of everything remain out of
  scope;
- hypotheses are uncertain and can decay, expire, deduplicate, or lose
  confidence under contradiction;
- hypotheses never adapt responses directly;
- only a user-confirmed hypothesis may enter the existing governed memory
  proposal path;
- existing memory approval/rejection/correction/revocation/deletion remains
  authoritative;
- active memory remains user-approved durable truth.

This preserves the root identity directive: Agent Col must never turn casual
conversation into a permanent trait without confirmation.

## Product Target B - Visible Agent Leadership

Goal:

> Use existing working-state understanding to make Agent Col more visibly lead
> the collaboration.

This is not a new planner.

Current working state already tracks:

- current goal;
- intent hypothesis;
- active constraints;
- unresolved questions;
- clarification status;
- next-step hypothesis;
- confidence.

The final improvement should make Agent Col more often:

- recommend the next consequential step;
- continue obvious authorized work;
- identify blockers;
- guide decisions with clear options;
- avoid repeatedly asking "what next?" when the current state already implies
  a useful next step.

Required boundaries:

- working state remains hidden, same-session scoped, non-authoritative, and
  possibly stale;
- current user messages, approved memory, workspace notes, persisted artifacts,
  routing/expert context, and higher-priority instructions override it;
- working state cannot authorize tools, persistence, identity changes, memory,
  notes, artifacts, or actions;
- no generalized autonomous planner is introduced.

## Productionization Target

Production hardening should fork the useful single-service work from the old
Phase 4 plan and remove the Phase 3 worker dependency.

Preserve:

- fail-closed production configuration;
- `google_oidc` required in production;
- canonical workspace ownership and cross-owner denial;
- opaque user identity;
- request-size limits;
- rate limiting;
- CSP and security headers;
- privacy-safe logs;
- retention and deletion rules;
- Dockerfile and `.dockerignore`;
- pinned production runtime;
- Cloud Run configuration;
- least-privilege service account;
- maximum-instance and cost controls;
- hosted smoke and security verification.

Remove from pre-submission production scope:

- Cloud Tasks;
- private worker;
- job ownership;
- queue authentication;
- job retry/cancellation;
- worker deployment;
- worker failure proof.

## Visual Polish Target

Visual frontend work belongs after functional freeze and before demo capture.

Use the safe visual guide:
[Safe frontend visual appearance change boundaries](../frontend/visual-design/safe-frontend-visual-appearance-change-boundaries.md).

Default scope:

- CSS-only changes in `frontend/styles.css`;
- appearance, readability, spacing, hierarchy, visual coherence, and judge
  comprehension;
- no backend routes, request payloads, JavaScript state machines, prompts,
  persistence, auth, memory, notes, artifacts, or working-state behavior.

## Documentation And Evidence Target

After Target A, Target B, and production hardening are accepted:

- update README setup/deployment;
- update current-state and architecture around deployed components only;
- update submission checklist;
- create final Devpost copy;
- produce a clean architecture diagram;
- run clean-clone and hosted smoke evidence;
- audit licensing, ignored files, and secrets;
- record Google Cloud proof before services are shut down for cost control.

## Final Demo Story

The demo should be a Collaborative Partner story, not a feature tour:

```text
User gives Agent Col messy work.
Agent Col clarifies it.
Agent Col synthesizes something useful.
Agent Col records or retrieves relevant collaboration context.
User corrects Agent Col's collaboration approach.
Repeated evidence creates a possible preference hypothesis.
Agent Col asks whether it should remember the preference.
User approves through the governed memory lifecycle.
A new conversation visibly adapts to the approved preference.
Agent Col recommends the next useful step.
The video shows memory/receipt proof, Firestore, Cloud Run, and architecture.
```

## Current Ordered Path

1. Roadmap/documentation sanitation.
2. Target A: evidence-governed preference learning.
3. Target B: visible Agent Col leadership.
4. Regression acceptance for A/B only.
5. Single-service production hardening.
6. Cloud Run deployment and hosted proof.
7. Controlled frontend appearance pass.
8. Documentation convergence and submission package.
9. Architecture diagram.
10. Four-minute demo.
11. Submission verification.
12. Freeze.

