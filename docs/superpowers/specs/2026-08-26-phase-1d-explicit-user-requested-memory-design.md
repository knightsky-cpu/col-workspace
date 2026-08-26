# Phase 1D - Explicit User-Requested Memory

## Status

Approved design reference for implementation planning.

## Goal

When a user explicitly asks Agent Col to remember something about themselves,
their collaboration with Col, their goals, preferences, interests, standing
instructions, or relevant working context, Agent Col constructs a governed
memory candidate regardless of whether the content fits an existing structured
memory category.

The persistence boundary then determines whether that candidate may become
approvable durable memory.

Allowed candidate:

```text
pending proposal
-> user approves
-> active memory
```

Prohibited candidate:

```text
policy-rejected candidate
-> clear human-facing explanation
-> cannot be approved
```

Existing structured memory categories should be used when they accurately fit,
but failure to match a predefined category must never itself cause rejection of
an explicit user memory request.

## Core Contract

The memory contract is intent-first, not taxonomy-first.

```text
User explicitly asks Agent Col to remember X
-> Agent Col constructs a governed memory candidate
-> deterministic policy validates whether the candidate is allowed
-> allowed candidate becomes a pending proposal
-> user approval in the Memory UI makes it active
```

The user's explicit request to remember is not rejected merely because the
content does not match a predefined structured category. The system gates
whether the resulting candidate may become approvable durable memory.

The contract is default-permissive for explicit memory intent and
deny-by-exception for prohibited content.

## Candidate Outcomes

### Allowed Candidate

An allowed explicit user-requested memory candidate becomes one pending
proposal. It is not active until the user approves it through the existing
Memory UI.

Agent Col may say that a pending proposal was created. Agent Col must not say
the memory was saved, remembered, or active until there is an authoritative
approval receipt from the application.

### Prohibited Candidate

A prohibited candidate is rejected by policy. It cannot become approvable
memory and cannot be approved through the UI.

Agent Col should give a clear, human-facing explanation that the requested
memory cannot be stored because it falls outside the safety boundary.

### Structured Category Match

If an existing structured category accurately fits the explicit request, Agent
Col should use that category.

Examples:

- `preferred_name` for a low-sensitivity preferred name.
- `development_environments` for macOS/Linux/Windows development preferences.
- `response_length` for concise/detailed response preferences.
- `explanation_structure` for step-by-step or concept-first explanation
  preferences.

Failure to match one of these categories is not itself a reason to reject an
explicit user request.

## User-Requested Memory Coverage

Explicit user-requested memory may cover:

- user preferences;
- user interests;
- user goals;
- collaboration style;
- standing instructions;
- low-risk identity context already allowed by the current contract;
- domain or project interests;
- user-described working context that is about the user rather than a workspace
  fact.

Examples that should be eligible for allowed candidates when no prohibited
content is present:

```text
Remember that I like security-focused software projects.
Remember that I prefer practical real-world examples.
Remember that I want you to explain tradeoffs before coding.
Remember that I am building Agent Col for a hackathon.
Remember that I prefer Linux and macOS development environments.
Remember that I like local-first tools when possible.
Remember that I prefer examples involving automation.
```

## Preserved Low-Sensitivity PII Allowance

The existing low-sensitivity identity allowance remains part of the contract.

Allowed low-sensitivity identity examples include:

```text
Remember my preferred name is wifiknight.
Remember that I am an experienced software developer.
```

This allowance remains bounded and narrow. It exists to reduce conversational
friction for useful, user-authored, low-risk identity context that is not
sufficient for identity theft or serious harm.

The low-sensitivity allowance does not permit unrestricted PII storage.

## Prohibited Memory Boundary

Explicit user intent does not override safety policy.

The system must reject memory candidates involving:

- passwords;
- API keys;
- tokens;
- credentials;
- government identifiers;
- bank or payment details;
- exact home address;
- phone or email unless explicitly added to a future low-risk allowlist;
- sensitive health facts;
- sensitive legal facts;
- sensitive financial facts;
- protected-class traits or inferences;
- other people's private information;
- instructions to remember secrets;
- broad surveillance-style requests such as "remember everything I say";
- hidden or non-consensual behavioral tracking.

The policy gate protects what may become approvable durable memory. It does not
prevent Agent Col from acknowledging the user's request and explaining why the
candidate cannot be stored.

## Deletion And Revocation Rule

Chat may not delete or revoke active durable memory.

Deletion and revocation must remain UI-only destructive actions. The Memory UI
should require explicit confirmation before durable deletion or revocation.

Chat may acknowledge a user's deletion or revocation intent and direct the user
to the Memory UI, but chat must not execute the destructive state mutation.

```text
User asks chat to delete/revoke memory
-> Agent Col explains that deletion/revocation must be confirmed in the UI
-> user uses Memory UI revoke/delete controls
-> confirmation gate
-> durable state mutation
```

This keeps destructive actions deliberate and auditable.

## Proposed Fallback Category

The implementation should add a governed fallback category for explicit
user-requested memory that does not fit a structured category.

Preferred name:

```text
user_requested_memory
```

The category should preserve:

- bounded user-authored text;
- source as explicit user request;
- a model- or policy-derived memory kind for display and instruction
  generation;
- deterministic safety validation result;
- normal proposal, approval, adaptation, revocation, and deletion lifecycle.

Possible memory kinds:

```text
preference
interest
goal
standing_instruction
identity_context
working_context
```

The memory kind helps display and instruction generation. It must not bypass
the safety gate.

## Authority Invariants

The authoritative lifecycle is:

```text
explicit user request creates a candidate
policy decides whether the candidate is approvable
user approval decides whether it becomes active
```

Agent Col may construct or explain candidates. The application owns validation,
persistence, approval receipts, and destructive-state controls.

Agent Col must not:

- claim memory is active without an approval receipt;
- delete or revoke durable memory through chat;
- store prohibited content because the user asked explicitly;
- reject an explicit request solely because it does not match a predefined
  category.

## Expected Acceptance Target

After implementation, this prompt:

```text
Col please remember that I like security focused software projects
```

should produce one pending proposal similar to:

```text
User-requested memory: Likes security-focused software projects
```

It should not produce an unsupported-category refusal.

After UI approval, a later fresh conversation can adapt from this memory and
show an authoritative adaptation receipt.

## Reasoning For The Contract Revision

The previous memory contract was too taxonomy-first. It protected the system by
allowing only predefined categories, but that created friction when the user
made a clear, explicit, low-risk request to remember something useful.

That friction conflicts with Agent Col's collaborative-partner goal. A user
should not need to guess the application's internal taxonomy before Agent Col
can remember a reasonable preference. Natural conversation should remain
natural.

The revised contract separates two concerns that were previously blended:

```text
Did the user explicitly ask Agent Col to remember this?
```

and:

```text
Is the resulting memory candidate safe and appropriate to become durable
memory?
```

The first question should be permissive. If the user explicitly asks to
remember something about themselves, their preferences, interests, goals,
collaboration style, standing instructions, or relevant working context, Agent
Col should construct a candidate.

The second question must remain strict. The application must reject prohibited
content, including secrets, security-sensitive data, high-risk PII, SPII,
protected-class traits or inferences, and other people's private information.

This preserves security while removing unnecessary friction:

- the user controls what they ask Agent Col to remember;
- the application controls what may become approvable durable memory;
- the user controls final activation through explicit UI approval;
- the user controls removal through deliberate UI revoke/delete confirmation;
- Agent Col remains truthful because it cannot claim active memory without an
  application receipt.

The design also avoids an unscalable category chase. Agent Col should continue
using structured categories when they fit, but the product cannot rely on
predefining every possible user preference. A governed fallback category keeps
the system practical without weakening safety.

The low-sensitivity identity allowance remains intentionally narrow. It avoids
needless friction for harmless identity context such as preferred name and
broad role while continuing to reject identity details that could create
security, privacy, or impersonation risk.

This contract better fits the hackathon and product objective: Agent Col should
become easier to collaborate with because it remembers what the user explicitly
wants it to remember, while durable memory remains governed, auditable,
revocable, and safe.
