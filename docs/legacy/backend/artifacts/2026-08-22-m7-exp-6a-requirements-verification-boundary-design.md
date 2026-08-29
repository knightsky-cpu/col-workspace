# M7-EXP.6A Requirements Verification Boundary Design

## Status

Proposed for repository-owner review. This pass changes documentation only and
authorizes no production-code, test, schema, dependency, API, or persistence
change.

## Governing directives

This design is subordinate to:

- [`AGENTS.md`](../../../AGENTS.md)
- [`AGENT_COL_IDENTITY_AND_ALIGNMENT.md`](../../../AGENT_COL_IDENTITY_AND_ALIGNMENT.md)
- [`DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`](../../../DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md)
- [`2026-08-21-phase-3b-m7-2-core-expert-routing-design.md`](2026-08-21-phase-3b-m7-2-core-expert-routing-design.md)
- [`2026-08-21-phase-3b-m7-exp-4d-r3-production-model-routing-design.md`](2026-08-21-phase-3b-m7-exp-4d-r3-production-model-routing-design.md)
- [`2026-08-21-phase-3b-m7-exp-4d-r3-3-production-routing-integration-design.md`](2026-08-21-phase-3b-m7-exp-4d-r3-3-production-routing-integration-design.md)
- [`2026-08-22-phase-3b-m7-exp-5c-computational-routing-provenance-design.md`](2026-08-22-phase-3b-m7-exp-5c-computational-routing-provenance-design.md)

Agent_Col remains a general collaborative partner and the only user-facing
conversational owner. Requirements Verification is one bounded cognitive
capability. It does not redefine Agent_Col as a software reviewer, project
manager, grading system, or compliance authority.

## Executive decision

Requirements Verification will use a hybrid application boundary:

1. deterministic local code projects immutable requirement and subject block
   candidates from the current user message;
2. the existing routing model may select only server-issued candidate IDs;
3. a dedicated structured Gemini service assesses the fixed requirements
   against the fixed subject;
4. deterministic local validation decides whether the candidate result is
   contract-complete and safe to expose;
5. the deterministic expert executor derives receipts;
6. responder-only Agent_Col interprets the validated result and owns the final
   response.

Requirements Verification is not an ADK `LlmAgent`, is not wrapped in
`AgentTool`, and has no tools of its own. It cannot call Research, Source,
Computation, memory operations, Firestore, or another expert.

The production routing-v2 boundary currently executes zero or one expert route
per turn. That stricter rule is authoritative. The older M7.2 two-delegation
limit remains a ceiling, not a requirement to use two experts. The M7.2 example
that chains Source and Requirements Verification in one turn is superseded for
the current production architecture.

## Why this capability exists

Structured output can prove that a response has the expected shape. It cannot
prove that each supplied requirement was considered or that evidence actually
supports the assigned status.

Requirements Verification addresses a narrower question:

> Given an explicit, bounded requirement set and an explicit, bounded subject,
> what does the supplied subject demonstrably cover, partially cover, omit,
> contradict, or leave unsupported?

Cross-domain examples include:

- an assignment submission against a rubric;
- an architecture against a specification;
- a proposal against an RFP;
- an experiment against a protocol;
- a project plan against stakeholder requirements;
- a draft policy against stated organizational constraints.

The capability assists human judgment. It does not issue legal, regulatory,
academic, safety, or contractual certification.

## Verified current production boundary

The design must extend the repository that exists now, not the earlier
conceptual topology:

- `AgentColRoute` currently allows `direct`, `clarify`, `source`, `research`,
  and `computation`;
- `AgentColRoutingInput` contains the current message plus locally projected
  URL and numeric candidates;
- the routing provider returns exactly one structured directive;
- `AgentColExpertExecutorV2` executes zero or one selected expert and forbids
  chaining;
- `AgentColTurnService` gives one expert a bounded portion of the turn deadline
  while reserving time for the responder;
- `AgentColResponderContextV2` accepts only a route-matching validated expert
  result and locally derived receipts;
- responder-only Agent_Col cannot reroute or call another expert;
- completed idempotent turns replay their stored result without repeating the
  expert operation;
- current action receipts include `google_search`, `url_context`, and
  `run_computation`, but not `verify_requirements`;
- `ExpertCapability.REQUIREMENTS_VERIFICATION` already exists as a reserved
  capability value but is not wired into production execution.

Therefore the next implementation cannot simply add an `AgentTool`. It must
extend the current routing, executor, responder, receipt, timeout, and replay
contracts as one coherent capability.

## Goals

The implementation derived from this design must:

1. select Requirements Verification only for an explicit comparison request;
2. require both an explicit requirement set and an explicit subject;
3. preserve the user's requirement wording instead of allowing the model to
   invent or silently rewrite it;
4. pass only the selected bounded material to the verification provider;
5. return exactly one assessment for every locally assigned requirement ID;
6. validate all subject evidence against immutable input blocks;
7. compute summary counts locally;
8. reject incomplete, duplicated, unknown, or contradictory result structures;
9. preserve uncertainty rather than manufacture coverage;
10. expose a completed receipt only after provider and local validation both
    succeed;
11. keep Agent_Col accountable for the final explanation;
12. preserve direct-answer restraint, current experts, memory governance,
    idempotency, and FastAPI ownership.

## Non-goals

This design does not:

- implement Requirements Verification;
- add Deep Research, Antigravity, MCP, Data Agents, or new infrastructure;
- add multi-expert execution or nested delegation;
- retrieve URLs, search the web, execute code, or inspect files;
- infer a requirement set from unrelated conversation history;
- add artifact retrieval or project-context tools;
- persist verification reports as project artifacts;
- mutate memory, feedback, projects, or Firestore records;
- accept file uploads or binary document ingestion;
- claim that local validation proves the semantic truth of a model judgment;
- replace human review for consequential decisions.

## Considered approaches

### Approach A: custom `LlmAgent` wrapped with `AgentTool`

Benefits:

- resembles the Research and Source specialist shape;
- allows a compact supervisor tool description.

Costs:

- adds an unnecessary conversational agent boundary;
- makes input minimization and exact coverage harder to enforce;
- encourages model-authored requirements and self-attested completeness;
- offers no provider-native tool that justifies an ADK specialist;
- weakens the deterministic application authority already established.

Decision: rejected.

### Approach B: give one model the raw chat and ask it to extract and assess

Benefits:

- smallest initial implementation;
- accepts loosely formatted user prompts.

Costs:

- the model chooses the requirements and judges its own selection;
- an omitted requirement can disappear without a detectable ID gap;
- unrelated history may leak into the comparison;
- evidence locators can be invented or detached from the supplied subject;
- the result cannot distinguish extraction failure from assessment failure.

Decision: rejected as the authoritative path.

### Approach C: deterministic candidate projection, model selection, structured
assessment, and local validation

Benefits:

- preserves exact user-authored material;
- keeps routing output small by selecting IDs instead of reproducing content;
- prevents unknown requirements and evidence blocks from entering execution;
- separates semantic reasoning from authoritative validation and receipts;
- fits the existing routing-v2 and executor/responder architecture;
- requires only one expert route and one bounded assessment generation.

Costs:

- initial input formatting must contain distinguishable requirement and subject
  blocks;
- completeness of the routing model's block selection remains probabilistic;
- natural-language semantic status assignment remains model-assisted;
- current-message-only scope is less convenient than future artifact retrieval.

Decision: selected.

### Approach D: fully deterministic lexical comparison

Benefits:

- reproducible and inexpensive;
- no provider dependency.

Costs:

- keyword overlap is not reliable evidence of semantic coverage;
- contradictions, partial satisfaction, and implicit fulfillment require
  contextual reasoning;
- would create false confidence while appearing more authoritative.

Decision: rejected as the primary evaluator. Deterministic logic validates
structure, provenance, and allowed status/evidence relationships; it does not
pretend to replace semantic reasoning.

## Invocation and restraint contract

### Select Requirements Verification

The routing model may select Requirements Verification only when the current
message contains all three elements:

1. an explicit comparison objective;
2. one or more distinguishable requirement candidates;
3. one or more distinguishable subject candidates to assess.

Examples of positive intent:

- "Compare this draft against these requirements and show every gap."
- "Evaluate my submission against this rubric."
- "Which RFP requirements are covered, partial, missing, or contradicted by
  this proposal?"

### Answer directly

Agent_Col should answer directly when the user asks for:

- a general explanation of requirements traceability;
- advice on writing a rubric or specification;
- a summary that does not request requirement-by-requirement verification;
- trivial observation that does not benefit materially from the expert.

### Clarify

The router must select `clarify` when:

- requirements are missing;
- the subject is missing;
- it cannot distinguish requirement material from subject material;
- the user refers only to an unavailable file, URL, artifact, or earlier
  context;
- the request requires both retrieval and verification;
- the requested comparison exceeds the bounded input contract;
- the requested outcome is consequential and the evaluation standard is
  ambiguous.

The clarification should request the smallest missing material. It must not
claim that verification ran.

### Cross-capability requests

The current one-expert production policy is preserved.

- A supplied URL plus a request to retrieve and verify does not silently run
  Source and then Requirements Verification.
- A request for current research plus a compliance comparison does not silently
  run Research and then Requirements Verification.
- A request to calculate results and compare them against a protocol does not
  silently run Computation and then Requirements Verification.

Such requests route to `clarify` so the user can choose or stage the work. The
first Requirements Verification release accepts only requirement and subject
content available in the current message. Future artifact and project-context
tools may provide server-authorized candidate blocks without changing the core
verification contract.

## Deterministic input projection

### Projection source

Only the current user message is eligible in the first implementation.
Profiles, model history, previous assistant prose, Firestore documents,
provider events, URLs, and inferred project state are excluded.

Local code projects bounded text blocks while retaining their exact character
spans. The projection recognizes structural boundaries such as:

- headings followed by content;
- numbered or bulleted list items;
- paragraphs separated by blank lines;
- fenced text blocks as opaque subject blocks.

Projection does not decide whether a block is a requirement or subject. It
only creates immutable candidates.

```text
RoutingTextBlockCandidate
  candidate_id: block-1 through block-N in source order
  text: exact non-empty substring of current_message, maximum 8,000 characters
  start_index: inclusive source index
  end_index: exclusive source index
  structural_kind: heading | list_item | paragraph | fenced_block
```

Proposed bounds:

- at most 64 candidates;
- at most 10,000 total source characters, matching the chat request boundary;
- no overlapping candidate spans;
- sequential candidate IDs;
- headings may provide context but cannot become standalone requirements or
  subject evidence.

If the projection cannot preserve the entire relevant material within these
bounds, it marks the projection incomplete. Requirements Verification cannot
be selected from an incomplete projection.

### Routing selection

The future routing directive adds a route-specific intent:

```text
RequirementsVerificationRoutingIntent
  objective: 1 through 1,000 characters
  requirement_block_ids: ordered unique block IDs, length 1 through 50
  subject_block_ids: ordered unique block IDs, length 1 through 32
  constraints: maximum 5 values, each 1 through 300 characters
```

The local directive validator enforces:

- every selected ID exists in the exact routing input;
- requirement and subject selections are disjoint;
- selections are unique and remain in source order;
- neither selection contains heading-only candidates;
- every selected requirement block is at most 1,000 characters;
- every selected subject block is at most 8,000 characters;
- selected requirement text is at most 6,000 aggregate characters, selected
  subject text is at most 8,000 aggregate characters, and their combined text
  is at most 9,000 characters;
- the projection is complete;
- Requirements Verification is advertised by the configured executor;
- no payload for another route is present.

The routing model cannot submit rewritten requirements, rewritten subject
content, raw character offsets, file paths, URLs, provider credentials, or
server identifiers.

### Locally assigned requirements

The executor resolves selected block IDs and assigns stable request-scoped IDs
in selected source order:

```text
RequirementInput
  requirement_id: REQ-001 through REQ-050
  text: exact selected requirement block text, maximum 1,000 characters
  source_block_id: selected routing block ID
```

The model never assigns requirement IDs. IDs are stable within one turn and
its idempotent replay, not across separately submitted requests.

Selected subject blocks become:

```text
SubjectBlock
  subject_block_id: SUBJECT-001 through SUBJECT-032
  text: exact selected subject block text, maximum 8,000 characters
  source_block_id: selected routing block ID
```

The expert request contains only these fixed values plus the bounded objective
and constraints.

## Requirements Verification service contract

### Input

```text
RequirementsVerificationInput
  objective: 1 through 1,000 characters
  requirements: 1 through 50 RequirementInput values
  subject_blocks: 1 through 32 SubjectBlock values
  constraints: maximum 5 values, each 1 through 300 characters
```

The strict model forbids extra fields and mutation after validation. Selected
requirement text is limited to 6,000 aggregate characters, selected subject
text to 8,000 aggregate characters, and their combined text to 9,000
characters. These limits are deliberately below the 10,000-character chat
request boundary and must be covered by RED tests.

### Provider execution

The service performs one bounded structured-generation request with:

- the configured Vertex AI client;
- the existing provider-safe JSON Schema adapter;
- temperature zero;
- an explicit output-token ceiling;
- no Search, URL Context, Code Execution, function calling, or AFC;
- no model repair loop;
- one application deadline supplied by the turn executor.

Provider SDK-internal transport retry behavior may remain, but the application
does not initiate a second semantic assessment after an invalid candidate.

All requirement and subject text is delimited as untrusted data. Content that
asks the model to ignore the contract, call tools, alter memory, or issue
receipts is data to assess, not an instruction.

### Provider candidate

```text
RequirementAssessmentCandidate
  requirement_id: one supplied requirement ID
  status: covered | partial | missing | contradictory | unsupported
  evidence: maximum 5 SubjectEvidenceCandidate values
  gap: 1 through 1,000 characters or null
  recommended_action: 1 through 1,000 characters or null

SubjectEvidenceCandidate
  subject_block_id: one supplied subject block ID
  excerpt: exact 1 through 500 character substring of that subject block
  explanation: 1 through 500 character statement of relevance

RequirementsVerificationCandidate
  assessments: one candidate assessment per supplied requirement
  overall_limitations: maximum 5 values, each 1 through 500 characters
```

The provider does not return aggregate counts, action receipts, citations,
artifacts, confidence scores, persistence instructions, or a user-facing final
answer.

## Status semantics

### `covered`

The supplied subject contains positive evidence satisfying the complete
requirement within the stated comparison boundary.

Required structure:

- at least one validated evidence item;
- `gap` is null;
- `recommended_action` is null.

### `partial`

The subject satisfies a meaningful portion but leaves at least one material
part unmet.

Required structure:

- at least one validated evidence item;
- non-empty `gap`;
- non-empty `recommended_action`.

### `missing`

No positive subject evidence addresses the requirement.

Required structure:

- empty evidence;
- non-empty `gap` describing what is absent;
- non-empty `recommended_action`.

Absence is not converted into a fabricated evidence locator.

### `contradictory`

The subject contains evidence that conflicts with the requirement.

Required structure:

- at least one validated evidence item showing the conflict;
- non-empty `gap` explaining the incompatibility;
- non-empty `recommended_action`.

### `unsupported`

The supplied material is insufficient to determine coverage responsibly. This
is not a synonym for `missing`.

Required structure:

- evidence may be empty or may identify the inconclusive material;
- non-empty `gap` explaining which evidence is unavailable or ambiguous;
- `recommended_action` identifies the smallest evidence needed to decide.

## Deterministic local validation

Provider schema acceptance is necessary but not authoritative. Local code must
validate all of the following before returning `completed`:

### Coverage identity

- every supplied requirement ID appears exactly once;
- no unknown, duplicate, or omitted requirement IDs exist;
- assessment order is normalized to the local requirement order;
- the provider cannot change requirement text or source block IDs.

### Evidence provenance

- every evidence block ID exists in the supplied subject blocks;
- every excerpt occurs as an exact, case-sensitive substring of the referenced
  subject block; fuzzy, semantic, case-folded, or whitespace-normalized matches
  are not accepted;
- excerpts are non-empty and bounded;
- duplicate evidence entries are rejected;
- evidence explanations cannot introduce new locators or external citations.

### Status coherence

- each status satisfies the structural rules in this document;
- `covered` cannot carry a gap;
- `partial` cannot omit positive evidence or its gap;
- `missing` cannot carry positive evidence;
- `contradictory` cannot omit conflicting evidence;
- `unsupported` must identify the missing or ambiguous basis;
- recommendations cannot change the validated status.

### Local derivation

Local code computes:

- count by each status;
- total requirement count;
- total validated evidence count;
- the set of referenced subject block IDs;
- whether all supplied requirements were assessed.

The model cannot provide or override these values.

### Honest limitation

These checks prove completeness, identity, evidence locality, and internal
contract coherence. They do not prove that the model interpreted the
requirement correctly or that the subject is true. Agent_Col must describe the
result as an evidence-backed assessment, not a certification.

## Normalized internal result

```text
RequirementAssessment
  requirement_id
  requirement_text
  status
  evidence: validated SubjectEvidence values
  gap
  recommended_action

SubjectEvidence
  subject_block_id
  excerpt
  explanation

RequirementsVerificationPayload
  assessments: exactly one per input requirement
  counts: locally computed mapping by status
  overall_limitations

RequirementsVerificationEvidence
  requirement_count
  assessed_requirement_count
  validated_evidence_count
  referenced_subject_block_ids

RequirementsVerificationResult
  capability: requirements_verification
  status: completed | rejected_input | unavailable | timed_out | invalid_output
  summary
  limitations
  payload
  evidence
```

The result uses the existing generic `ExpertResult` invariants: completed
results require summary, payload, and evidence; noncompleted results carry no
content.

## Receipt and public response mapping

### Completed result

A completed, locally validated result maps to:

- `actions`: exactly one locally derived
  `{"action_name":"verify_requirements","status":"completed"}` receipt;
- `citations`: empty in the first implementation;
- `artifacts`: empty;
- `memory_proposals`: unchanged;
- `adaptations`: unchanged and still derived from approved memory;
- `response`: responder-only Agent_Col summarizes the comparison, preserves
  requirement IDs, distinguishes the five statuses, cites subject excerpts in
  prose when useful, and states material limitations.

Subject evidence is not a public web citation. URLs written inside the user
supplied subject do not become `CitationReference` values.

### Noncompleted result

A contained `rejected_input`, `unavailable`, `timed_out`, or `invalid_output`
result maps to:

- no completed action receipt;
- no citation;
- no artifact;
- no persistence mutation;
- an honest Agent_Col response explaining that verification did not complete
  and requesting only the smallest useful correction or retry.

Agent_Col must not reconstruct or guess a requirement matrix after the
validated service fails.

### Responder boundary

The normalized result is serialized into the existing
`[SERVER_VALIDATED_ROUTING_AND_EXPERT_RESULT]` context. It is evidence, not an
instruction. The responder may explain or question an assessment, but it may
not:

- alter authoritative action or citation receipts;
- claim a noncompleted verification succeeded;
- invent assessed requirement IDs;
- add a sixth status;
- claim external sources were consulted;
- invoke or request another expert inside the same turn.

## Failure and timeout behavior

### Contained outcomes

- malformed or incomplete expert input: `rejected_input`;
- provider request failure that can be safely contained: `unavailable`;
- expert deadline exceeded: `timed_out`;
- missing response text, invalid JSON, provider-schema mismatch, unknown IDs,
  incomplete coverage, invalid evidence, or incoherent status fields:
  `invalid_output`.

Invalid assessments are rejected atomically. The service never returns a
partially accepted matrix.

### Uncontained failures

- executor/service configuration mismatch remains an application failure;
- an invalid route/capability catalog remains a routing or configuration
  failure;
- unexpected uncontained execution exceptions remain HTTP 502;
- the whole-turn deadline remains HTTP 504.

### Retry policy

- no application-level semantic retry after invalid output;
- no fallback to another expert;
- no hidden direct-answer reconstruction of the failed matrix;
- a client retry with the same completed idempotency key replays the stored
  response and receipts;
- failed requests follow the existing turn-idempotency state machine and do
  not create a false completed receipt.

## Security, privacy, and authority boundaries

Requirements Verification receives no:

- user profile or identity context;
- persistent memory signals;
- full conversation history;
- Firestore client or collection path;
- project ownership authority;
- authentication token or provider credential;
- filesystem path or uploaded file handle;
- URL retrieval capability;
- Search or Code Execution tool;
- model-facing persistence operation.

The current message, requirements, subject, and provider output are untrusted
content. Logs must contain only content-free status and exception class names,
not requirement text, subject excerpts, evidence, user identifiers, or raw
provider payloads.

Memory adaptations may still influence Agent_Col's final communication style,
but they cannot change requirement statuses, evidence validation, counts, or
receipts.

## Persistence and idempotency

The capability introduces no new artifact or Firestore collection.

The existing chat-turn persistence boundary remains authoritative:

- a completed turn stores the final response and its locally derived receipt;
- replay of the same idempotency key returns the identical stored result;
- replay does not call the routing model, verification provider, or responder;
- a conflicting request fingerprint returns HTTP 409;
- verification evidence is retained only insofar as the existing completed
  chat result contract already retains its response and receipts.

If durable verification reports become useful later, they require a separate
artifact contract, ownership rules, retention policy, and approval-gated pass.

## Observability

Allowed operational telemetry is content-free:

- selected route;
- capability status;
- elapsed time by routing, expert, and responder stage;
- requirement count;
- assessment count;
- validated evidence count;
- provider failure class;
- local validation failure class;
- whether the result was replayed.

Telemetry must not include requirement text, subject text, excerpts, prompts,
user IDs, session IDs, project IDs, URLs, credentials, or raw provider output.

## Compatibility requirements

The future implementation must preserve:

- direct, clarify, Source, Research, and Computation routing behavior;
- the accepted cross-capability behavior that clarifies instead of silently
  choosing one part of a multi-expert request;
- one selected expert route per turn;
- responder-only Agent_Col ownership;
- source citations derived only from provider grounding evidence;
- computation receipts derived only from successful execution evidence;
- memory proposal and decision governance;
- approved-memory adaptation visibility;
- headerless chat behavior;
- idempotent replay and HTTP 409 conflicts;
- current synthesis and artifact endpoints;
- existing FastAPI and Firestore authority boundaries.

## Proposed implementation decomposition after approval

This design does not authorize implementation. After repository-owner
acceptance, the smallest safe TDD sequence is:

### M7-EXP.6B.1 — Text-block projection and routing contracts

- add deterministic block projection;
- add Requirements Verification routing input and directive types;
- extend the provider schema and local route validation;
- keep production capability disabled;
- begin with RED tests for grounding, disjoint selection, incomplete
  projection, missing material, restraint, and cross-capability clarification.

### M7-EXP.6B.2 — Verification models and deterministic validator

- add strict input, candidate, normalized payload, and evidence models;
- implement exact requirement coverage and evidence validation without a live
  provider;
- begin with RED tests for omitted, duplicate, unknown, incoherent, and
  ungrounded assessments.

### M7-EXP.6B.3 — Vertex structured provider service

- add one tool-free structured-generation boundary;
- reuse provider-safe schema adaptation and Vertex configuration;
- classify missing text, schema errors, provider errors, and timeouts;
- keep the service disconnected from production routing;
- verify with offline tests, then one bounded live smoke test.

### M7-EXP.6B.4 — Executor, responder projection, and receipts

- wire the service into the deterministic executor behind explicit
  configuration;
- add `verify_requirements` to the action allowlist;
- extend the responder result union and receipt derivation;
- preserve zero/one expert execution and no citations.

### M7-EXP.6B.5 — Atomic production cutover

- construct the service during application lifespan;
- advertise the capability only when configured;
- extend the turn-service route set and timeout mapping;
- preserve idempotency and existing experts;
- manually verify completed, restrained, clarification, failure, conflict, and
  replay paths before checkpointing.

### M7-EXP.6C — Complete four-capability judgment evaluation

- extend the unified evaluation matrix with requirements verification;
- evaluate direct, clarify, Source, Research, Computation, and Requirements
  Verification together;
- include repeated cross-capability and restraint scenarios;
- classify provider failures separately from routing or semantic failures;
- use the accepted results as the gate before Deep Research design.

Each source-changing pass requires its own proposed plan, explicit approval,
RED/GREEN TDD evidence, focused verification, manual acceptance, and GitHub
checkpoint.

## Required RED targets for the later plan

At minimum, the later persistent suite must prove:

### Routing and restraint

- explicit bounded comparison selects Requirements Verification;
- general advice remains direct;
- missing requirements clarifies;
- missing subject clarifies;
- ambiguous block roles clarify;
- incomplete projection clarifies;
- URL retrieval plus verification clarifies;
- computation plus verification clarifies;
- no-tools instruction remains direct;
- existing routes remain unchanged.

### Input authority

- projected block spans match the current message exactly;
- candidate IDs are sequential and unique;
- requirement and subject selections are disjoint;
- selected IDs resolve only from the supplied routing input;
- requirement IDs are assigned locally in source order;
- provider input excludes raw history, profile, server identifiers, and
  credentials.

### Validation

- every requirement is assessed exactly once;
- missing, duplicate, and unknown IDs fail atomically;
- evidence IDs must reference supplied subject blocks;
- evidence excerpts must occur in the referenced block;
- all five status/evidence combinations are enforced;
- counts are computed locally;
- invalid output produces no completed receipt.

### Runtime and receipts

- completed verification creates exactly one `verify_requirements` receipt;
- contained failures create no receipt or citation;
- responder context matches the selected capability;
- expert timeout preserves responder reserve;
- uncontained configuration errors remain application failures;
- identical idempotent replay does not rerun verification;
- changed input with the same key returns HTTP 409.

## Manual verification targets for future implementation

No runtime verification applies to this documentation-only pass. The future
production cutover must provide exact one-line commands for:

1. a successful multi-requirement comparison returning one completed receipt;
2. a missing-subject request that asks a precise clarifying question;
3. an ordinary explanation that uses no expert;
4. a cross-capability request that clarifies rather than partially executing;
5. an identical idempotent replay;
6. a conflicting request returning HTTP 409;
7. a Firestore check confirming no new verification artifact or memory record
   was created.

## Acceptance criteria for this design

The repository owner should approve M7-EXP.6A only if all of the following are
correct:

1. Requirements Verification is a hybrid application service, not an
   `AgentTool` specialist.
2. Agent_Col remains the sole orchestrator and final conversational owner.
3. The current production rule remains zero or one expert route per turn.
4. Requirements and subject material come only from immutable current-message
   candidates in the first implementation.
5. The routing model selects candidate IDs but cannot rewrite their content.
6. Gemini performs bounded semantic assessment without tools.
7. local validation is authoritative for identity, completeness, evidence
   locality, status coherence, counts, and receipts.
8. a completed result requires exactly one assessment per requirement.
9. contained failure never creates a success receipt or guessed matrix.
10. citations remain empty because user-supplied subject evidence is not public
    retrieval evidence.
11. no memory, Firestore, artifact, file, URL, Search, computation, or nested
    expert authority is introduced.
12. cross-capability requests clarify instead of silently executing one part.
13. existing idempotency, timeout, responder, memory, synthesis, and expert
    behavior remains unchanged.
14. Deep Research remains deferred until all four core capabilities pass the
    complete judgment evaluation.

## Review decision requested

Approval of this document authorizes preparation of the bounded
M7-EXP.6B.1 TDD implementation plan only. It does not authorize source changes.
