# M9-MEM.1 Governed Profile Memory Scope and Natural Request Design

## Status and authority

Approved by the repository owner for design work on August 24, 2026. This
document defines the target contract but authorizes no runtime source, test,
schema, prompt, persistence, API, frontend, dependency, or deployment change.

This design is subordinate to:

- [`AGENTS.md`](../../../AGENTS.md);
- [`AGENT_COL_IDENTITY_AND_ALIGNMENT.md`](../../../AGENT_COL_IDENTITY_AND_ALIGNMENT.md);
- [`DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`](../../../DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md);
- [`2026-08-20-phase-3b-trusted-memory-design.md`](2026-08-20-phase-3b-trusted-memory-design.md);
- [`2026-08-24-m9-cont-1-continuity-domain-and-collaborative-notes-design.md`](2026-08-24-m9-cont-1-continuity-domain-and-collaborative-notes-design.md);
- [`features-plan-revisions.md`](../../legacy/features-plan-revisions.md);
- [`frontend-plan-revision.md`](../../legacy/frontend-plan-revision.md).

Agent Col remains a general collaborative partner. Profile memory is one
governed adaptation domain. It is not a transcript archive, a generic personal
database, a workspace notebook, or autonomous learning.

## Executive decision

The current trusted-memory lifecycle is structurally sound and must be
preserved: one explicit candidate becomes one pending proposal, the user
approves or rejects it, and only an approved signal can adapt a later turn.
The defect is the gap between that lifecycle and the product contract:

- the version-1 policy accepts only ten categories;
- several safe, promised collaboration preferences cannot be represented;
- the supervisor requires brittle exact restatement after clarification;
- unsupported values can produce conversational acknowledgement without a
  durable proposal;
- the browser cannot display a proposal the backend refused to create.

M9-MEM will correct that gap through a versioned, bounded policy rather than
arbitrary string memory. Version 2 will:

1. preserve every accepted version-1 category and value;
2. add narrowly bounded explanation pace, learning approach, accessibility
   support, development-environment preference, and self-reported domain
   experience;
3. recognize ordinary durable language such as `remember`, `save`, `store`,
   `keep for later`, `use going forward`, `make this my default`, and semantic
   equivalents without requiring one magic phrase;
4. keep profile memory separate from workspace notes and session-only
   instructions;
5. permit one bounded follow-up selection after Agent Col asks the user to
   choose among multiple eligible candidates, without requiring the user to
   repeat the full original value;
6. retain explicit review before activation;
7. require application-derived receipts before Agent Col may claim that a
   durable proposal or active memory exists;
8. read existing version-1 records without destructive migration.

The model may make bounded semantic judgments and propose one canonical
candidate. Application code remains the authority for categories, values,
normalization, evidence, ownership, provenance, lifecycle, and instructions.
No generic model-facing Firestore write tool is introduced.

## Verified current baseline

This design was reconciled against repository commit
`48bf8f6c5ef0abfa90c63f7bff1c63fb699727a2`, which was aligned with
`origin/main` when the design review began. The following pre-existing
worktree changes were explicitly excluded from this design pass:

- `frontend/state.mjs`;
- `tests/frontend/state.test.mjs`;
- `scrnshot-evidence/memory.png`;
- `features-plan-revisions.md`;
- `frontend-plan-revision.md`.

The two plan-revision documents were read as subordinate planning context;
this pass does not accept, stage, or alter their uncommitted state.

The repository already provides:

- a strict version-1 policy and schema;
- eight enum-based collaboration preferences;
- preferred-name and broad-role identity context;
- a server-owned proposal command derived from the authenticated turn;
- current-message grounding for preferred names;
- deterministic proposal identifiers and a 24-hour proposal lifetime;
- at most one proposal receipt per chat response;
- explicit approve and reject decisions;
- atomic correction and supersession when an approved replacement changes an
  active category;
- revoke and hard-delete operations;
- bounded inspection of profile, unresolved proposals, and events;
- cross-session adaptation receipts derived from active signals;
- user-global profile memory shared across the user's workspaces;
- frontend controls for approve, reject, revoke, and delete.

The version-1 categories are:

| Domain | Categories |
| --- | --- |
| Preferences | `response_length`, `explanation_structure`, `example_usage`, `question_style`, `planning_granularity`, `progress_check_ins`, `tool_use_style`, `formatting_style` |
| Identity context | `preferred_name`, `broad_roles` |

The verified limitations are:

- `MEMORY_SCHEMA_VERSION` and `MEMORY_POLICY_VERSION` are fixed to `1.0`;
- the Pydantic models accept only policy/schema `1.0`;
- the profile caps identity context at two categories and preferences at eight;
- a proposal and event record only one originating source message;
- the proposal tool can submit only a scalar string or a broad-role list;
- `macOS and Linux development environments` is outside the policy even when
  the user explicitly asks Agent Col to remember it;
- explanation pace, learning approach, accessibility support, and approved
  domain experience promised by the identity document are not represented;
- the prompt requires exact value restatement after a multi-candidate
  clarification;
- local validation cannot currently distinguish a supported durable request,
  a session-only accommodation, a workspace note, and an unsupported personal
  fact as explicit outcomes.

## Goals

M9-MEM must:

1. align governed profile memory with Agent Col's accepted identity;
2. preserve explicit user authority and approval before activation;
3. let users request memory in normal conversational language;
4. keep canonical storage deterministic and allowlisted;
5. keep workspace-specific facts out of the user-global profile;
6. keep temporary instructions out of durable memory;
7. reject sensitive or unsupported personal data truthfully;
8. support correction without removing the old active value until the
   replacement is approved;
9. preserve version-1 signals and immutable event provenance;
10. prevent model prose from overstating persistence;
11. define the minimum stable contract needed by later memory UI controls;
12. remain compatible with cross-session adaptation and synthesis projection.

## Non-goals

M9-MEM.1 does not:

- implement the design;
- add note persistence, note APIs, or cross-chat retrieval;
- store arbitrary user-authored profile text;
- store project decisions, requirements, task state, or artifact content in
  profile memory;
- infer preferences from behavior, history, artifacts, searches, expert
  results, or model-authored text outside the Target A governed preference
  learning boundary;
- create active memory from Target A observation evidence or hypotheses without
  user confirmation and the existing governed approval lifecycle;
- store sensitive PII, credentials, health facts, financial facts, protected
  traits, exact employer/school, precise location, or account identifiers;
- make Google identity attributes available as model memory;
- remove proposal approval, correction, revocation, or deletion controls;
- activate more than one memory signal in one user decision;
- add semantic/vector memory or unbounded transcript retrieval;
- let the browser or model write Firestore directly;
- redesign the collaborative-note contract;
- claim that all allowed memory is PII-free;
- add autonomous background memory extraction.

Target A may add bounded, workspace-scoped observation evidence and
non-authoritative preference hypotheses from user corrections, explicit
feedback patterns, or repeated collaboration preferences. This does not allow
silent active memory, raw transcript mining, broad profiling, autonomous
background extraction, or direct response adaptation from hypotheses. A
hypothesis can only feed the existing governed memory path after user
confirmation.

## Domain classification

Every candidate must be classified into exactly one of four domains before a
durable profile proposal can be created.

| Domain | Definition | Example | Required behavior |
| --- | --- | --- | --- |
| Governed profile memory | A reusable, user-global collaboration preference or narrowly allowed identity/context signal | “Remember that I prefer macOS and Linux commands.” | Create one pending proposal when the value is supported and explicit |
| Collaborative workspace note | A decision, constraint, requirement, task state, or agreed takeaway specific to the active workspace | “Keep a note that this API must remain backward compatible.” | Route to the note workflow when available; never store as profile memory |
| Session-only accommodation | A temporary instruction limited by the user's wording to this answer, task, chat, or day | “For this answer, keep it short.” | Honor in the current turn/session; do not propose durable memory |
| Unsupported or sensitive data | A value outside the allowlist or prohibited by the identity/privacy boundary | “Remember my password” | Do not persist or propose; explain the boundary without falsely claiming memory |

### Classification precedence

The following precedence prevents ambiguous phrases from crossing domains:

1. prohibited sensitive data is never eligible;
2. explicit temporary scope remains session-only;
3. explicit workspace/project scope belongs to collaborative notes;
4. only then may a supported user-global collaboration or identity candidate
   enter the profile-memory workflow.

The words `remember`, `save`, or `note` do not override this precedence. “Save
the API requirement” is a note request, not a profile preference. “Remember my
password” remains prohibited.

## Version-2 policy contract

### Preserved version-1 categories

Every version-1 category and canonical value remains valid with identical
meaning. Version 2 does not rename stored category keys or reinterpret old
values.

| Stored category | Human label | Canonical value shape |
| --- | --- | --- |
| `preferred_name` | Preferred name | One bounded, explicitly supplied name |
| `broad_roles` | Broad roles | One through three of Student, Professional, Educator, Researcher, Hobbyist, Retired, Career transition |
| `response_length` | Response length | Concise, Balanced, Detailed |
| `explanation_structure` | Explanation structure | Answer then steps, Step by step, Concept then example |
| `example_usage` | Example use | No added examples, Examples when helpful, Always include a practical example |
| `question_style` | Question style | Ask before assuming, Recommend then ask, Minimal follow-up |
| `planning_granularity` | Planning detail | Milestones, Tasks, Micro-steps |
| `progress_check_ins` | Progress check-ins | Only when blocked, At milestones, Frequent |
| `tool_use_style` | Tool use | Ask before external tools, Use when needed, Minimize tools |
| `formatting_style` | Formatting | Prose, Bullets, Mixed |

Accepted identity terms map to existing categories as follows:

| Identity term | Governed category |
| --- | --- |
| response length | `response_length` |
| example style | `example_usage` |
| planning cadence | `planning_granularity` and `progress_check_ins` |
| formatting | `formatting_style` |
| check-in style | `progress_check_ins` |
| approved tool-use preference | `tool_use_style` |
| preferred/display name | `preferred_name` |
| broad role context | `broad_roles` |

### New preference categories

#### `explanation_pace`

Controls how quickly an explanation unfolds, not how much information it
contains.

Allowed values:

- `deliberate` — introduce concepts gradually and pause at meaningful stages;
- `balanced` — use a normal explanatory pace;
- `brisk` — lead quickly to the result and minimize transitional explanation.

Human label: **Explanation pace**. Value labels: **Deliberate**,
**Balanced**, and **Brisk**.

This category does not replace `response_length`. A detailed response may
still be briskly organized, and a concise explanation may still be deliberate.
The current request always overrides both preferences.

#### `learning_approach`

Controls the default teaching sequence for explanatory work.

Allowed values:

- `concept_first` — establish the governing idea before application;
- `example_first` — begin with a concrete example, then explain the rule;
- `practice_first` — begin with a small guided exercise;
- `question_guided` — use bounded Socratic questions when useful.

Human label: **Learning approach**. Value labels: **Concept first**,
**Example first**, **Practice first**, and **Question guided**.

It does not authorize quizzes, grading, or extra follow-up when the current
request asks for a direct answer.

#### `accessibility_support`

Stores explicit interface or communication accommodations, never a diagnosis
or inferred medical condition. The value is an ordered, unique list containing
one through three of:

- `plain_language`;
- `screen_reader_friendly`;
- `low_visual_density`;
- `reduced_motion`;
- `keyboard_first`.

Human label: **Accessibility support**. The application owns human labels for
each bounded behavior and never presents a diagnosis label.

Model context receives only bounded communication or artifact-design
instructions, not a claim about disability or health. M9-MEM does not claim
that the current browser UI automatically changes from these values; a later
frontend consumer requires its own deterministic state and receipt contract.

#### `development_environments`

Stores explicit preferences for host/tooling environments Agent Col should
favor when giving commands, paths, and package-manager guidance. The value is
an ordered, unique list containing one through three of:

- `macos`;
- `linux`;
- `windows`.

Human label: **Development environments**. Value labels use the conventional
platform names **macOS**, **Linux**, and **Windows**.

This category records a collaboration preference, not device ownership,
physical location, employer tooling, or verified technical expertise.
Target platforms such as iOS, Android, or Web are project/task constraints and
belong in the current request or a workspace note, not the user-global profile.
`cross_platform` is therefore not a version-2 profile value.

### New identity-context category

#### `domain_experience`

Stores up to three explicitly self-reported broad experience entries. Each
entry contains:

- one domain from `software_development`, `data_science`, `cybersecurity`,
  `research`, `writing`, `education`, `project_management`, `design`,
  `mathematics`, `science`, `business`, or `creative_work`;
- one level from `exploring`, `learning`, `practicing`, or `experienced`.

Domains must be unique. Entries are sorted in application-owned canonical
domain order:

1. `software_development`;
2. `data_science`;
3. `cybersecurity`;
4. `research`;
5. `writing`;
6. `education`;
7. `project_management`;
8. `design`;
9. `mathematics`;
10. `science`;
11. `business`;
12. `creative_work`.

Each serialized entry is exactly
`{"domain": <domain enum>, "level": <level enum>}`. The model must not infer
a level from vocabulary, occupation, artifacts, credentials, or prior
performance. The instruction calibrates examples and assumed vocabulary only;
it never asserts certification, seniority, employer, school, or competence.

Human label: **Domain experience**. Domain and level labels are
application-owned title-cased forms of the canonical enums.

### Version-2 capacity

Version 2 supports:

- three identity-context categories: `preferred_name`, `broad_roles`, and
  `domain_experience`;
- twelve available preference categories: the eight version-1 categories plus
  `explanation_pace`, `learning_approach`, `accessibility_support`, and
  `development_environments`;
- at most one active signal per category;
- at most ten total active signals across identity context and preferences;
- at most ten unresolved proposals in the existing bounded inspection page;
- at most one newly created proposal per chat turn.

The ten-signal total preserves the existing adaptation-receipt and bounded
context ceilings even though the available category vocabulary grows. These
limits are contract boundaries, not suggested UI defaults.

### Deterministic version-2 instruction rendering

The application, not the model, renders each version-2 value into one exact
bounded instruction. The literal templates are:

| Category/value | Deterministic instruction |
| --- | --- |
| `explanation_pace = deliberate` | When the current request permits, introduce concepts gradually and separate consequential stages so the user can follow each transition. |
| `explanation_pace = balanced` | When the current request permits, use a steady explanatory pace with enough transition to connect the main ideas. |
| `explanation_pace = brisk` | When the current request permits, move quickly to the result and minimize transitional explanation without omitting required evidence or limitations. |
| `learning_approach = concept_first` | For instructional requests, explain the governing concept before applying it. |
| `learning_approach = example_first` | For instructional requests, begin with one concrete example before explaining the governing rule. |
| `learning_approach = practice_first` | For instructional requests, begin with one small guided exercise when practice is appropriate. |
| `learning_approach = question_guided` | For instructional requests, use at most one bounded guiding question at a time when it helps the user reason without blocking a requested direct answer. |

`accessibility_support` values are serialized and rendered in this canonical
order regardless of user input order:

1. `plain_language` — Prefer plain language and define necessary technical
   terms.
2. `screen_reader_friendly` — Use linear headings, descriptive link text, and
   text equivalents; do not rely on spatial position alone.
3. `low_visual_density` — Keep sections visually separated and avoid
   unnecessarily dense presentation.
4. `reduced_motion` — When producing interface specifications or UI code,
   avoid nonessential motion and include reduced-motion behavior.
5. `keyboard_first` — When producing interface specifications or UI code,
   include complete keyboard operation.

The renderer concatenates the selected accessibility instructions in that
order with one space between sentences. It does not add a diagnosis or user
attribute.

`development_environments` values are serialized in the order `macos`,
`linux`, `windows`. The application renders one instruction using the human
labels joined by commas and `and`:

> When platform-specific commands or paths are needed and the current task
> does not specify another target, prefer guidance compatible with {human
> environment list}.

`domain_experience` entries use the canonical domain order defined above.
For each entry the application renders:

> For {Domain label} material, calibrate vocabulary and examples to the
> user's explicitly self-reported {Level label} experience; do not treat it
> as verified expertise.

Multiple domain instructions are concatenated in canonical domain order with
one space between sentences. Adaptation receipts serialize the same canonical
list/object value that the policy validator accepted; responder prose cannot
alter it.

### Cross-category precedence and compatibility

Stable category order is not permission to apply contradictory instructions.
The effective precedence is:

1. safety, authorization, privacy, tool, and evidence requirements;
2. the current user request;
3. application accessibility requirements where they conflict with
   presentation style;
4. governed profile defaults.

`response_length` controls amount, `explanation_pace` controls sequencing, and
`explanation_structure` controls order. `question_style` decides whether a
follow-up is appropriate; `learning_approach = question_guided` applies only
after the response is already instructional and cannot force a follow-up or
withhold a requested direct answer. Accessibility presentation requirements
override `formatting_style` when the two conflict. Development-environment
memory never overrides an explicit target platform in the current request or
workspace note.

The complete version-2 registry/serialization order is:
`preferred_name`, `broad_roles`, `domain_experience`, `response_length`,
`explanation_structure`, `explanation_pace`, `example_usage`,
`learning_approach`, `question_style`, `planning_granularity`,
`progress_check_ins`, `tool_use_style`, `formatting_style`,
`accessibility_support`, `development_environments`. This order does not make
one preference override another. Every allowed cross-category combination
must either coexist under the conditional instructions specified here or have
an explicit compatibility rule. An implementation encountering an unlisted
semantic conflict must ask for clarification or ignore the conflicting default
for that turn; it must not invent a winner.

## Natural durable-intent contract

### Explicit durable intent

Users do not need one exact command. A request is explicitly durable when the
current user-authored message clearly asks Agent Col to retain a supported
candidate beyond the present turn. Representative language includes:

- “remember …”;
- “save this preference …”;
- “store this in memory …”;
- “keep this for later/future chats …”;
- “use this going forward …”;
- “from now on …”;
- “make this my default …”;
- “add this to my profile/memory …”;
- semantically equivalent ordinary phrasing.

This is a semantic contract, not a case-sensitive keyword list. The structured
model boundary may classify the request, but it can output only one
application-owned category and canonical value. Application validation still
controls whether a proposal is legal.

A regular expression or keyword hit may support diagnostics, but it is not
proof of reusable intent and must not be presented as semantic understanding.

### Clear reusable preference without a persistence keyword

A direct reusable statement such as “I prefer detailed answers” may create a
pending proposal even when it does not contain `remember` or `save`. The
statement explicitly supplies a stable collaboration preference, while the
separate structured approve/reject decision remains the authority for durable
activation. The pending proposal is reviewable and is not yet memory.

Contextual feedback such as “that answer was too long”, “more detail please”,
or “use bullets here” does not by itself express reusable scope. Agent Col may
apply it to the current interaction and, when useful, ask whether the user
wants it saved. It must not silently create or activate durable memory.

### Temporary scope

Phrases such as `for this answer`, `in this chat`, or `this time` make the
instruction limited to the current turn or active chat even if the message also
uses a word such as `remember`. `For this task` is session-only only when the
task is contained in the active chat. `Today` is not a supported durable
duration: Agent Col must ask whether the user means the active chat or a
user-global default. It must not promise a temporary instruction across new
chat sessions because no time-bounded cross-chat memory exists.

### Natural alias normalization

Application-owned aliases map ordinary phrases to canonical values. The alias
catalog is versioned and tested. Examples include:

| User language | Canonical candidate |
| --- | --- |
| “long, detailed, informative answers” | `response_length = detailed` |
| “give me the answer first and steps after” | `explanation_structure = direct_then_steps` |
| “take explanations slowly” | `explanation_pace = deliberate` |
| “show me an example before the theory” | `learning_approach = example_first` |
| “format it so it works well with a screen reader” | `accessibility_support = [screen_reader_friendly]` |
| “favor macOS and Linux development environments” | `development_environments = [macos, linux]` |
| “I am learning software development” | `domain_experience = [{software_development, learning}]` |

Aliases may normalize spelling, casing, punctuation, common abbreviations,
and unambiguous synonyms. They must not infer an unstated level, platform,
identity, accessibility need, or persistence duration.

### Structured natural-memory decision

The private semantic provider returns exactly one discriminated decision. It
does not return chain-of-thought, free-form rationale, storage identifiers, or
provider-authored instructions. The result variants are:

```text
NoMemoryDecision(kind = "no_memory")
SessionOnlyDecision(
  kind = "session_only",
  scope = "current_turn" | "active_chat",
)
WorkspaceNoteDecision(kind = "workspace_note")
ProfileCandidateDecision(
  kind = "profile_candidate",
  category,
  canonical_value,
  evidence_text,
)
ClarifyDecision(
  kind = "clarify",
  candidates = [two through five ProfileCandidateDecision values],
)
UnsupportedDecision(kind = "unsupported", reason_code)
ProhibitedDecision(kind = "prohibited", reason_code)
```

`reason_code` is one application-owned enum value and never contains user
content. `UnsupportedDecision.reason_code` is exactly one of
`unsupported_category`, `unsupported_value`, or `unsupported_duration`.
`ProhibitedDecision.reason_code` is exactly one of `credential_or_secret`,
`account_identifier`, `contact_detail`, `precise_location`,
`exact_employer_or_school`, `health_or_financial_fact`, `protected_trait`,
`identity_provider_claim`, or `inferred_private_trait`.

`evidence_text` is an exact, case-sensitive substring of one allowed
user-authored evidence message, contains 1 through 500 Unicode scalar values,
and is validated before any proposal or clarification is written. It is not
stored in the proposal, event, or proposal-origin document and is never
logged. The durable record retains only the server-owned evidence message ID.

The semantic provider owns the judgment that ordinary language denotes one of
the bounded decisions and canonical candidates. The application-owned alias
catalog may normalize spelling, casing, common abbreviations, and exact
unambiguous synonyms after that judgment; it is not a keyword-based consent or
PII detector. Deterministic code validates the variant, canonical value,
evidence substring, current state, ownership, and lifecycle before executing
anything.

### Model and application responsibilities

The model may supply:

- one durable-intent classification;
- one canonical category;
- one canonical value;
- a bounded evidence span copied from user-authored text;
- one clarification selection when a server-owned clarification envelope is
  available.

Application code must verify:

- the effective authenticated user and current session;
- no structured memory decision is already present;
- the category and value are valid for the declared policy version;
- the evidence span exists in the allowed user-authored source message;
- the candidate is user-global rather than workspace-specific or temporary;
- the decision is not `prohibited` and the candidate passes the bounded
  category-specific validators and explicitly supported known-pattern checks;
- the value is not already active;
- a matching pending proposal does not already exist;
- a conflicting active signal becomes a replacement proposal rather than an
  immediate mutation;
- at most one proposal is created.

The model never supplies user, workspace, session, source-message, proposal,
signal, event, Firestore, policy-version, or ownership identifiers.

This boundary is not a general sensitive-data detector. A prohibited decision
or recognized credential/account pattern is rejected from profile memory, but
the original user message still belongs to the separate chat-archive retention
domain. M9-MEM must not claim that rejecting a memory candidate removes the raw
message from chat history.

## Clarification without exact restatement

### Multiple eligible candidates

When one message contains more than one eligible candidate, Agent Col does not
choose. It asks one concise human-readable question and the application records
a durable, session-scoped `MemoryClarificationEnvelope`. Session-local means
scoped to one chat session, not process memory. The authoritative location is:

```text
sessions/{session_id}/memory_clarifications/{clarification_id}
```

The server owns `clarification_id` and derives it deterministically as the
bounded SHA-256 digest of a versioned namespace, authenticated user ID,
session ID, current evidence/source message ID, and clarification turn ID.
Provider output cannot supply or alter it. The session parent stores
`active_memory_clarification_id`, allowing exactly one open envelope per
session without a collection scan.

Clarification creation is a retry-safe turn effect. One transaction validates
the current turn lease, expires any different prior open envelope, writes the
new envelope, stores one application-owned `MemoryClarificationReceipt` in the
turn ledger, and updates the parent pointer. The receipt contains only the
clarification ID, human-labeled candidate choices, and expiry needed by the
client; it is not profile memory. `ChatResponse` carries at most one such
receipt. Exact replay of the same turn and identical ordered candidates returns
the stored envelope/receipt. The same turn identity with changed candidates
fails closed as a conflict.

The responder receives the application-owned question/choices. If response
generation fails after the transaction, the bounded partial-failure response
still exposes the stored clarification receipt. A retry reuses it. An envelope
must not become silently consumable without that persisted turn effect; if the
effect cannot be recorded, the transaction writes neither the envelope nor the
active pointer.

The version-1 clarification document contains exactly:

- `clarification_schema_version = "1.0"`;
- server-owned clarification ID;
- authenticated user ID, session ID, and active workspace/project ID;
- original `evidence_message_id` and clarification turn ID;
- two through five ordered, unique canonical category/value candidates;
- `created_at` and `expires_at`;
- status `open`, `consumed`, or `expired`;
- optional consuming turn/message ID and selected candidate index only after
  consumption.

Human labels are derived from the policy catalog when read and are not stored
as authority. The envelope is orchestration state, not active memory and not a
profile record. Canonical candidate values are stored only to preserve the
bounded next-turn choice; neither candidates, values, nor identifiers appear
in application logs.

An envelope is valid only for the first subsequent user turn in the same
authenticated user/session/workspace and for no longer than 15 minutes. The
first subsequent turn must transactionally do exactly one of the following:

1. resolve exactly one candidate and consume the envelope while creating the
   proposal and turn effect;
2. mark it expired when the response is ambiguous, unrelated, or prohibited.

No later user turn can consume it. A different user, session, or workspace
cannot observe or use it.

The system must not invent a composite category such as
`concise_with_examples` to bypass the one-proposal boundary. Each accepted
atomic category retains its own lifecycle and provenance.

### Follow-up selection

The next user message may select one offered candidate naturally, for example
`preferred name first` or `save the development environments`. The application
accepts the selection only when it resolves to exactly one candidate in the
unexpired server-owned envelope.

The existing `source_message_id` field keeps its retry-safe meaning: it is the
current user message that owns the proposal effect. Version 2 adds separate
evidence provenance:

- direct proposal: `source_message_id` and `evidence_message_id` are the same
  current user message, and `clarification_id` is absent;
- clarified proposal: `source_message_id` is the current selecting message,
  `evidence_message_id` is the original message containing the canonical
  candidate, and `clarification_id` identifies the consumed envelope.

The existing version-1 origin ID derivation remains unchanged: its digest uses
the versioned namespace, authenticated user, session, and current
`source_message_id`; category is not part of that digest. Category prefixes the
resulting proposal ID. Turn-lease validation and exact-retry equality use that
same current source/effect message. Proposal, event, and origin provenance
retain `evidence_message_id`; clarified records also retain
`clarification_id`. The original evidence message and the selecting message
must belong to the same authenticated user/session/workspace, and the evidence
must precede both clarification and selection.

Envelope consumption, proposal-slot creation, proposal-origin creation,
retry-safe turn-effect recording, session active-pointer clearing, and status
transition to `consumed` occur in one Firestore transaction. Exact replay of
the same selecting turn returns the same proposal receipt. A competing or
changed selection conflicts and fails closed; it cannot create a second
proposal or consume the envelope differently.

The user is not forced to repeat the full original value. An ambiguous,
unrelated, or late response expires the envelope and creates no proposal.
History outside this bounded envelope cannot become profile-memory evidence.

## Proposal, replacement, and activation semantics

### New category

A supported durable request with no active or matching pending signal creates
one pending proposal. The response includes a completed
`propose_memory_signal` action receipt and one proposal receipt. Agent Col says
that the proposal is pending review, not that the preference is remembered.

### Matching pending proposal

No duplicate is written. The response points the user to the existing pending
proposal. It must not emit a second completed create receipt.

### Already active value

No proposal is created. Agent Col may state that the preference is already
active only when the application supplies that authoritative state.

### Conflicting active value

The new value becomes a replacement proposal with `expected_signal_id` bound
to the currently active signal. The prior value remains active while the new
proposal is pending. Approval atomically:

1. creates a corrected event for the replacement;
2. creates a superseded event for the prior signal;
3. replaces the active projection;
4. increments the memory revision.

Rejection leaves the prior active value unchanged.

### Activation

Only an explicit structured approve decision may activate a pending proposal.
Free-form `yes`, positive sentiment, continued usage, or model reasoning does
not constitute approval.

## Truthful response contract

Public language must match application-owned state:

| Authoritative result | Permitted claim |
| --- | --- |
| Completed proposal receipt | “I created a pending memory proposal for your review.” |
| Completed approval receipt | “Your approved preference is now active.” |
| Existing active signal supplied by the application | “That preference is already active.” |
| Matching pending proposal supplied by the application | “That proposal is already waiting for review.” |
| Session-only, `current_turn` | “I will use that for this answer; it was not saved to your profile.” |
| Session-only, `active_chat` | “I will use that for this conversation; it was not saved to your profile.” |
| Workspace-note classification before note runtime exists | “That belongs to workspace notes; I cannot persist it there yet.” |
| Unsupported category/value | “That cannot be stored in governed profile memory.” |
| Sensitive/prohibited value | “I cannot store that as profile memory.” |
| Tool/service failure | “The proposal was not created.” |

Without a completed proposal or approval receipt, Agent Col must not say
`saved`, `stored`, `remembered`, `recorded`, or semantically equivalent durable
claims. Conversational accommodation and durable persistence must be described
separately.

## Versioning and migration

### Version identifiers

M9-MEM.2 will introduce:

- memory policy `2.0`;
- memory schema `2.0`;
- a policy registry that validates `1.0` and `2.0` records by each record's own
  declared version;
- proposal-origin schema `2.0`, while preserving a strict version-1 reader;
- clarification-envelope schema `1.0`.

### Compatibility rules

1. Existing version-1 category names and values keep their exact meaning.
2. Existing proposal, signal, and event identifiers do not change.
3. Existing immutable events are never rewritten in bulk.
4. A strict dual-version reader must be deployed and verified before any
   version-2 proposal, profile, signal, event, or origin write is enabled.
5. A version-1 profile is validated as version 1 and projected in memory into
   a version-2-compatible application view without writing during a read.
6. Existing version-1 pending proposals remain approvable or rejectable until
   expiry under version-1 validation.
7. Existing version-1 active signals retain `policy_version = 1.0` and render
   their original deterministic instructions.
8. After the version-2 write cutover, every successful governed profile
   mutation atomically writes the root profile as schema `2.0` after validating
   every retained signal under its own policy version. Reads alone never
   upgrade the root document.
9. Approving a version-1 pending proposal after cutover writes a schema-2.0
   root profile while the approved signal and immutable event retain policy
   `1.0`. The same approval works whether the root was still schema 1.0 or had
   already been upgraded to schema 2.0.
10. New proposals use policy `2.0` after the atomic production cutover.
11. A version-2 correction may supersede a version-1 signal while preserving
   the original linkage and immutable event provenance.
12. Correction, revoke, delete, and inspection resolve validation from the
   stored signal/proposal/event policy version, not only the current default.
13. Unknown or malformed future versions fail closed; they are not silently
   dropped or coerced.
14. Version-1 preferred-name and broad-role grounding/provenance remain intact.
15. New list and structured values are written only under policy/schema `2.0`.
16. Version-1 proposal-origin documents retain their exact six-field shape.
    Version-2 origins add required `evidence_message_id` and optional
    `clarification_id`; readers dispatch strictly by origin schema version.
17. Exact retry, origin cleanup, rejection, approval, revoke, delete, and
    transaction rollback must work for v1-only, v2-only, and mixed-version
    profile state.

### Source provenance evolution

Version-1 records retain `source_message_id`. Version-2 proposals, origins,
and events retain the same required current-effect field and add required
`evidence_message_id`. Direct proposals store the same ID in both fields.
Clarified proposals additionally store `clarification_id`, with the distinct
original evidence identity carried in `evidence_message_id`. No existing
identifier is rewritten.

### Rollback

The cutover must be atomic at the application configuration boundary. Before
new version-2 data is accepted, every production read/mutation path must
understand both versions. Rollback may stop new version-2 proposals, but it may
not deploy a reader that rejects already-written version-2 records.

## Persistence contract

Firestore locations remain unchanged:

```text
users/{user_id}  # root profile fields
users/{user_id}/memory_proposals/{category}
users/{user_id}/memory_proposal_origins/{origin_id}
users/{user_id}/memory_events/{event_id}
```

The bounded clarification flow adds orchestration state beneath the existing
owned session boundary:

```text
sessions/{session_id}/memory_clarifications/{clarification_id}
```

M9-MEM.2 must not create a parallel memory store merely to implement version
2. Historical category document slots and origin records remain locatable.

Version-2 profile-memory documents add only fields required for policy/schema
versioning, new canonical values, and evidence/clarification provenance.
Clarification envelopes are transient orchestration records and are not copied
into the profile. Profile memory remains user-global. No workspace ID becomes
part of the active profile key, and no workspace note is copied into it.

## Context and adaptation projection

Application code renders the instruction for every active value. The model
does not turn raw stored values into unrestricted instructions.

Projection rules are:

- current user request and safety constraints outrank memory;
- profile instructions are bounded collaboration defaults, not commands from
  a prior user message;
- `development_environments` affects platform choices only when the task permits;
- `accessibility_support` exposes requested presentation behavior, not a
  diagnosis;
- `domain_experience` calibrates vocabulary/examples and does not certify
  expertise;
- compatibility and precedence are resolved by the deterministic rules above;
- only active, non-revoked signals appear;
- every supplied signal produces an application-derived adaptation receipt;
- an adaptation receipt proves `provided_to_model`, not perfect model
  adherence or autonomous learning;
- memory content and identifiers remain absent from application logs.

## Frontend contract for later M9-UI.1

M9-MEM.1 does not change the browser. It establishes these requirements:

- human labels for every category and canonical value;
- category, value, ordering, and label metadata comes from one versioned
  application-owned catalog or an exact generated frontend mirror, never a
  separately invented browser allowlist;
- no raw category keys or long IDs as primary labels;
- Add memory offers only supported categories and values;
- list-valued controls enforce bounds and uniqueness;
- domain experience uses bounded domain and level choices;
- accessibility choices describe interface behavior rather than medical
  conditions;
- Add and Edit always create pending proposals;
- the old active value remains visible while a replacement is pending;
- approve, reject, revoke, and delete remain explicit;
- pending, active, session-only, unsupported, and failed states are visually
  distinct;
- clarification choices use human labels and do not require canonical tokens;
- a completed backend receipt, followed by canonical inspection refresh, is
  the only UI success authority.

## Security and privacy invariants

- Google token claims and internal account identifiers never become profile
  memory.
- Request-provided aliases do not determine memory ownership.
- Only the authenticated effective user can inspect or mutate their profile.
- The model cannot provide server-owned identifiers or Firestore paths.
- No memory proposal is created from assistant text, expert output, artifact
  content, URL content, or retrieved prior chats.
- No arbitrary free-text preference category is introduced.
- Preferred name remains bounded free text with current-message grounding.
- Domain experience is explicitly self-reported and allowlisted.
- Accessibility memory stores interface behavior, not health information.
- Credentials and sensitive PII are never stored even when explicitly
  requested.
- Logs contain bounded operation names, status classes, counts, durations, and
  non-content error codes only. They contain no user, workspace, session,
  message, clarification, proposal, signal, or event identifiers and no memory
  category values or user-authored content.
- Revoked or deleted signals cannot appear in later context.
- Workspace notes and profile memory remain separate ownership and lifecycle
  domains.

## Failure behavior

| Failure | Public behavior | Durable behavior |
| --- | --- | --- |
| Unsupported category or value | Truthful limitation or useful clarification | No proposal |
| Sensitive/prohibited value | Refuse durable storage without unnecessary repetition | No proposal |
| Temporary instruction | Acknowledge session-only use | No proposal |
| Workspace-specific fact | Route/describe note boundary | No profile proposal |
| Ambiguous candidate | Ask one concise question | Optional durable session-scoped clarification envelope only |
| Multiple candidates | Ask the user to choose one | No proposal until unambiguous selection |
| Expired clarification | Ask for a fresh choice or statement | No proposal |
| Matching pending proposal | Point to existing pending review | No duplicate write |
| Already active value | State authoritative active status | No write |
| Stale replacement target | HTTP 409 or bounded conflict response | Existing active value remains |
| Provider/tool validation failure | State that proposal was not created | No proposal |
| Persistence failure | Bounded database failure | Atomic write leaves no partial proposal |
| Responder failure after proposal persistence | Partial failure exposes verified completed effect | Proposal remains retry-safe |
| Unknown memory version | Fail closed as incompatible state | No silent coercion or data loss |

## Evaluation strategy

### Deterministic policy and schema tests

- every version-1 category/value remains valid under version 1;
- every new category accepts only its canonical values and shapes;
- list values enforce length, uniqueness, type, and canonical order;
- domain experience rejects duplicate domains and inferred/free-form levels;
- accessibility support rejects diagnoses and arbitrary text;
- platform aliases normalize to canonical values;
- every new canonical value renders the exact deterministic instruction
  specified by this design;
- list/structured receipt serialization uses canonical order and shape;
- version-1 records project into the version-2 application view without a
  write;
- mixed-version active signals validate from their own policy versions;
- unknown versions fail closed;
- replacement proposals preserve the prior active signal until approval;
- version-2 evidence provenance distinguishes direct and clarified proposals;
- version-1 pending approval works before and after root-schema upgrade;
- proposal-origin read, retry, cleanup, and rollback work for both versions.

### Deterministic routing and service tests

- `remember`, `save`, `store`, `keep for future chats`, `use going forward`,
  and semantic equivalents can create one supported pending proposal;
- explicit temporary scope creates no proposal;
- workspace decisions create no profile proposal;
- sensitive requests create no proposal;
- session-only decisions distinguish current-turn from active-chat scope and
  produce matching truthful language;
- unsupported and prohibited decisions accept only the enumerated reason
  codes;
- natural aliases map to exactly one canonical candidate;
- more than one candidate produces a clarification envelope, not a proposal;
- exact clarification-creation replay returns the same envelope and turn
  receipt, while changed candidates for that turn conflict;
- responder failure after clarification persistence exposes the stored bounded
  receipt and does not leave an unseen consumable envelope;
- a valid next-turn selection creates the selected proposal without exact
  restatement;
- clarification creation enforces one open envelope per owned session;
- clarification consumption, proposal creation, turn effect, and active-pointer
  clearing commit atomically;
- exact selection replay returns the same proposal, while changed, competing,
  unrelated, or late selections fail closed;
- same active value and matching pending value do not duplicate writes;
- conflicting active value creates a replacement proposal;
- no completed receipt means no durable success language.

### Controlled orchestration

- direct conversation remains natural and does not call memory by default;
- one ordinary durable request calls the proposal tool exactly once;
- a memory decision cannot create another proposal;
- artifact, note, expert, and memory operations remain mutually bounded;
- tool rejection is presented truthfully;
- model-authored or retrieved content cannot become proposal evidence;
- profile context renders every new active category deterministically.

### Bounded live proof

1. In session A, say: `Please save that I prefer detailed answers.` Verify one
   pending `Response length: Detailed` proposal appears.
2. Approve it and verify the active value appears.
3. In session B, request an explanation and verify a completed adaptation
   receipt for response length.
4. Say: `Remember that I prefer macOS and Linux development environments.`
   Verify one pending platform proposal appears, then approve it.
5. In session C, request shell guidance and verify macOS/Linux-aware output and
   a platform adaptation receipt.
6. Say: `For this answer only, keep it concise.` Verify no durable proposal is
   created.
7. Say: `Remember that this workspace must use API version 2.` Verify no
   profile proposal is created and the note boundary is explained/routed.
8. Say: `Remember my password is synthetic-example-secret.` Verify durable
   storage is refused and the synthetic token does not appear in logs. The raw
   user message remains in chat history under that domain's separate retention
   contract; this test does not claim chat deletion.
9. State two supported durable preferences in one message. Select one in the
   next turn using its human label and verify the proposal is created without
   restating the original value.
10. Correct an active preference and verify the old value stays active until
    approval, then becomes superseded.
11. Revoke and delete representative new values; verify new sessions no longer
    receive them.
12. Repeat inspection/mutation as another authenticated user and verify it
    fails closed without revealing state.

Manual review remains decisive for whether Agent Col sounds like a natural
collaborative partner, asks only useful clarifications, distinguishes temporary
help from durable memory, and never overstates what it learned or stored.

## Implementation decomposition after design acceptance

The source implementation should be divided into separately reviewable TDD
passes if one combined M9-MEM.2 pass is too large:

### M9-MEM.2A — Versioned Policy and Schema Compatibility

- add policy/schema version registries;
- preserve exact version-1 validation;
- add version-2 categories and canonical value models;
- add mixed-version read projection and unknown-version failure;
- add optional selection provenance models;
- do not change production routing yet.

### M9-MEM.2B — Natural Candidate Normalization and Clarification State

- add bounded alias normalization;
- add domain classification outcomes;
- add durable session-scoped clarification envelopes;
- validate evidence and next-turn selection;
- preserve one-proposal discipline;
- do not cut production orchestration over yet.

### M9-MEM.2C — Atomic Production Routing and Truthful Response Cutover

- update the proposal tool/provider schema;
- integrate version-2 validation with the trusted memory service;
- cut over supervisor/responder behavior atomically;
- preserve retry-safe proposal effects and decision exclusion;
- add controlled orchestration regression coverage.

### M9-MEM.2D — Cross-Session Proof and Closure

- exercise representative new categories in genuinely separate sessions;
- prove correction, revoke, delete, and mixed-version behavior;
- reconcile canonical status documentation and live evaluation fixtures.

M9-UI.1 remains separate and begins only after the production memory contract
is accepted.

## Acceptance criteria

The design is accepted when the repository owner confirms that it:

1. preserves explicit pending proposal and approval authority;
2. keeps profile memory user-global and workspace notes workspace-scoped;
3. adds only bounded, identity-aligned collaboration categories;
4. supports the observed macOS/Linux preference safely;
5. accepts normal durable language without a magic command;
6. may turn a clear reusable preference statement into a pending proposal but
   never treats it as activation consent;
7. removes the exact-restatement requirement through bounded clarification
   state;
8. prevents arbitrary text and sensitive data from entering profile memory;
9. defines truthful language for every result state;
10. preserves version-1 data and immutable provenance;
11. fails closed on unknown versions and ownership conflicts;
12. preserves current-turn ownership while retaining original evidence for
    clarified proposals;
13. defines atomic, expiring, retry-safe clarification persistence;
14. defines exact decision variants and evidence-span bounds;
15. defines deterministic rendering and cross-category precedence;
16. defines deterministic v1-to-v2 mutation and origin compatibility;
17. preserves the ten-active-signal bound and one-proposal-per-turn rule;
18. keeps memory identifiers, content, and values out of logs;
19. defines a narrow, testable implementation sequence.

## Stop conditions

Implementation must stop and return to design review if:

- natural language cannot be supported without accepting arbitrary profile
  strings;
- a model-visible generic persistence tool becomes necessary;
- workspace decisions must be copied into profile memory;
- a proposal can activate without explicit structured approval;
- existing version-1 events would need destructive rewriting;
- rollback would deploy a reader unable to understand already-written version
  2 records;
- sensitive personal data must be stored to satisfy a category;
- memory evidence must come from assistant, expert, artifact, URL, or retrieved
  transcript content;
- one user turn must create multiple proposals;
- application-derived receipts cannot remain the authority for public claims;
- authenticated ownership cannot be enforced on every memory path.
