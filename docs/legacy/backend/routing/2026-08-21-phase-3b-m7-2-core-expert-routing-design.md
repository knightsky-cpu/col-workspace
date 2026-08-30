# Phase 3B M7.2 Core Expert Routing and Evidence Contract Design

## Status and review gate

This document is the M7.2 design deliverable. The repository owner **approved
this design on August 21, 2026**. That approval authorizes this design contract,
not a production-code, test, dependency, schema, API, provider, or
infrastructure change. A separate implementation plan and explicit approval
are required before source changes begin under
[`AGENTS.md`](../../../../AGENTS.md).

The design is grounded in repository commit
`780bdefe940bb0e75a77dcfa8e24e12f12c62f81`, the installed
`google-adk==2.7.0` and `google-genai==2.18.1` packages, the manually accepted
supervisor and chat-idempotency baseline, and the official Google interfaces
verified during the preceding M7 research pass.

## Governing contracts

M7.2 remains subordinate to:

- [`docs/design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md`](../../../design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md)
- [`docs/design/DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`](../../../design/DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md)
- [`2026-08-19-hybrid-adk-supervisor-contract-design.md`](../../architecture/2026-08-19-hybrid-adk-supervisor-contract-design.md)
- [`2026-08-20-phase-3b-trusted-memory-design.md`](../memory/2026-08-20-phase-3b-trusted-memory-design.md)
- [`2026-08-21-phase-3b-trusted-memory-m7-governed-proposal-tool-design.md`](../memory/2026-08-21-phase-3b-trusted-memory-m7-governed-proposal-tool-design.md)

If this document conflicts with those contracts, the stricter user-control,
privacy, provenance, idempotency, tool-restraint, or deterministic-authority
boundary wins unless the repository owner explicitly approves a revision.

## Decision

M7.2 defines exactly four core expert capabilities:

1. **Research Expert** using Google Search;
2. **Source Expert** using URL Context;
3. **Computational Expert** using ADK `BuiltInCodeExecutor`;
4. **Requirements Verification** using structured model reasoning followed by
   deterministic local validation.

Agent_Col remains the sole orchestrator and sole user-facing conversational
owner. Experts return bounded evidence to Agent_Col. They do not answer the
user directly, persist state, call another expert, authorize an action, or
become durable conversational identities.

The turn topology is fixed:

```text
User
  |
  v
Agent_Col
  |
  +-- zero, one, or two bounded expert delegations
  |      |
  |      +-- one assigned built-in capability or deterministic service
  |      `-- normalized result returned to Agent_Col
  |
  `-- one final response owned by Agent_Col
```

The maximum specialist-delegation depth is one. Agent_Col may delegate to an
expert; an expert may use only its assigned built-in capability. Google
Search, URL Context, and Code Execution are capabilities, not additional
expert agents, and therefore do not increase delegation depth.

## Necessary corrections to the proposed shape

The four requested capabilities are accepted, with four reliability
corrections.

### Requirements Verification is not a fourth free-running specialist

Requirements Verification is an expert capability, but it must not be
implemented as an unconstrained `LlmAgent` result. The model may perform
requirement interpretation and evidence mapping. Application code must then
enforce complete requirement-ID coverage, allowed statuses, evidence rules,
and summary counts. This is a hybrid deterministic service selected by
Agent_Col, not an autonomous specialist with persistence authority.

### Strict output means normalized and locally validated

Provider response schemas help shape model output; they do not establish
source provenance or semantic correctness. A result becomes a completed
expert result only after an application adapter validates its local schema and
the required provider evidence events. Search and URL citations are derived
from provider grounding metadata, and computation evidence is derived from
actual code-execution events. Agent-authored source URLs, execution claims, or
completion statements are not evidence.

### Delegation attempts consume the budget

The maximum of two applies to initiated delegation attempts, not only
successful results. A rejected, failed, invalid, or timed-out invocation still
consumes one slot. This prevents Agent_Col from looping through retries or
trying several experts until one produces a preferred answer.

Provider-internal search queries or code retries remain part of one expert
invocation. The application does not perform an orchestration-level automatic
retry inside the same turn.

### Existing receipts cannot hold arbitrary raw evidence

The existing `ChatResponse` has `actions`, `artifacts`, `citations`, and
`adaptations`; it has no generic execution-evidence field. M7.2 does not
overload `artifacts` or `citations` with code logs or requirement reports.
Completed expert use maps to a server-derived action receipt, valid public
URLs map to citation receipts, and Agent_Col incorporates the bounded expert
result into `response`. Raw provider events remain internal. A future public
evidence envelope would require a separate schema decision.

## Goals

M7.2 must:

1. preserve direct, tool-free answers as the default behavior;
2. expose only the four approved expert capabilities;
3. make every expert input minimal, typed, bounded, and task-specific;
4. prevent user, project, session, memory, and history identifiers from
   becoming model-selected expert arguments;
5. enforce at most two delegation attempts per turn and at most one invocation
   of any capability per turn;
6. enforce delegation depth one and prevent expert-to-expert calls;
7. normalize every expert result through a strict local adapter;
8. derive citations and execution evidence from provider events rather than
   model prose;
9. keep all four experts read-only and free of persistence authority;
10. let Agent_Col integrate, qualify, and explain expert results in its final
    response;
11. distinguish recoverable expert failure from fatal supervisor failure;
12. preserve the existing FastAPI, Firestore, chat, memory, idempotency, and
    final-response ownership boundaries.

## Non-goals

M7.2 does not:

- implement any expert or modify any source file;
- add Deep Research, Deep Research Max, Antigravity, MCP, Data Agents, Cloud
  Tasks, queues, workers, or other infrastructure;
- add a generic web browser, shell, arbitrary Python function, filesystem, or
  network tool;
- permit experts to call specialists, transfer control, or converse directly
  with the user;
- permit expert access to generic Firestore reads or writes;
- persist research, source analyses, calculations, or verification reports as
  artifacts;
- add file upload or file-based Code Execution;
- combine Search and URL Context inside one expert;
- add automatic cross-provider fallback or orchestration-level retries;
- guarantee that external sources are accurate merely because they were
  retrieved;
- alter the M7 governed-memory proposal design;
- change the current 90-second whole-turn timeout or four-call model budget
  without a later measured implementation decision.

## Considered approaches

### Approach A: one generic analysis expert

One expert would receive a mode such as `research`, `source`, `compute`, or
`verify` and gain all capabilities.

Decision: rejected. It expands the model-visible argument space, makes routing
and evidence attribution ambiguous, weakens least privilege, and makes tool
restraint harder to evaluate.

### Approach B: four equivalent ADK `LlmAgent` specialists

Each capability would be implemented as a single-turn agent.

Decision: rejected. This fits Search, URL Context, and computation, but it does
not make requirement completeness authoritative. A valid-looking model report
may omit requirements or label unsupported claims as covered.

### Approach C: three single-turn specialists plus one hybrid service

Search, source analysis, and computation use isolated `LlmAgent` specialists
with exactly one assigned built-in capability. Requirements Verification uses
a deterministic function boundary around structured model generation and
local validation.

Decision: selected. It gives the three provider-native capabilities natural
ADK isolation while preserving deterministic authority where completeness is
the product requirement.

## Authority model

| Concern | Authoritative component |
| --- | --- |
| Whether an expert is materially needed | Agent_Col, constrained by routing policy |
| Delegation budget and depth | invocation-scoped application guard |
| User-facing conversation and final answer | Agent_Col |
| Expert task arguments | Agent_Col within strict local schemas |
| Server-owned identifiers and turn state | FastAPI and `SupervisorRuntime` |
| Search and URL execution | Google built-in tools inside isolated specialists |
| Code execution | ADK `BuiltInCodeExecutor` inside the Computational Expert |
| Requirement interpretation | structured Gemini generation |
| Requirement coverage and status validity | deterministic local validator |
| Citation URI and source provenance | provider metadata plus local adapter |
| Code execution evidence | ADK/provider execution events plus local adapter |
| Public receipts | `SupervisorRuntime` from validated completed events |
| Durable history, memory, and artifacts | Firestore through application services |

No expert can declare its own output authoritative. Agent_Col can use an
expert result only in the manner allowed by its normalized status and
evidence.

## Delegation policy

### Default restraint

Agent_Col answers directly when the supplied context is sufficient and an
expert would not materially improve correctness, evidence, or completion.

No expert is justified for:

- greetings, ordinary conversation, or emotional support;
- explanations based on stable general knowledge;
- simple transformations, summaries, or writing help using supplied text;
- simple arithmetic Agent_Col can safely compute without executable
  verification;
- ambiguous tasks missing a consequential input;
- requests where the user asks Agent_Col not to use external tools;
- a second opinion that would merely restate the first expert result.

When consequential input is missing, Agent_Col asks one concise clarifying
question instead of delegating speculatively.

### Invocation order

Agent_Col should normally use no expert or one expert. A second expert is
allowed only when it resolves a distinct evidence gap that materially affects
the answer. Examples include:

- Source Expert to interpret a supplied specification, then Requirements
  Verification to compare an artifact against it;
- Research Expert for current facts, then Computational Expert to calculate a
  result from the retrieved figures;
- Source Expert for a public dataset description, then Computational Expert
  for a bounded calculation using values explicitly returned or supplied.

Agent_Col must not use two experts merely to increase apparent activity,
confirm an already adequate answer, or circumvent a failed expert.

### Enforced budget

The invocation owns a concurrency-safe budget with these invariants:

- maximum delegation attempts: two;
- maximum invocation of the same capability: one;
- maximum delegation depth: one;
- a failed, rejected, invalid, or timed-out attempt consumes its claimed slot;
- a provider-internal query or execution retry does not claim another slot;
- experts have no sub-agents, transfer tools, or access to the parent tool
  catalog;
- the Requirements Verification service cannot invoke another expert;
- a second call is denied if insufficient whole-turn time remains for a final
  Agent_Col response.

An instruction is required for behavior, but it is not the enforcement
boundary. Installed ADK code can execute multiple selected calls
concurrently, so the budget guard must claim slots atomically before provider
work begins.

## Shared expert result envelope

All four capabilities return an internal normalized envelope:

```text
ExpertResult
  capability: research | source | computation | requirements_verification
  status: completed | rejected_input | unavailable | timed_out | invalid_output
  summary: bounded non-empty text when completed
  limitations: bounded list of non-empty text
  payload: capability-specific validated payload when completed
  evidence: capability-specific server-derived evidence when completed
```

The envelope is internal. It is not returned wholesale through the public API.
Only `completed` results may create a completed action receipt, citation
receipt, or evidence-backed claim in the final response.

Failure results contain an allowlisted safe status and generic explanation.
They exclude raw prompts, provider responses, stack traces, user content,
identifiers, credentials, source bodies, code-executor internals, and hidden
reasoning.

## Research Expert contract

### Purpose and invocation rule

Invoke the Research Expert when the user's task materially depends on current,
externally verifiable, or niche public information that is not already present
in validated turn context.

Examples:

- current API capabilities or model availability;
- recent laws, schedules, product information, or public events;
- verification of a factual claim against external sources;
- finding multiple credible sources for a research question.

Do not invoke it for a supplied URL; use the Source Expert. Do not invoke it
for computation or for checking coverage against an already supplied rubric.

### ADK boundary

The selected abstraction is an ADK `LlmAgent` configured as an inline
`mode="single_turn"` sub-agent with exactly one built-in capability:
`google_search`. Direct `AgentTool` wrapping is not selected because installed
ADK 2.7.0 explicitly discourages direct `AgentTool` usage in favor of
single-turn sub-agents.

The specialist has no sub-agents, no transfer tools, no function tools, no URL
Context, no Code Execution, and no persistence access.

### Minimal input

```text
ResearchExpertInput
  question: non-empty, bounded research question
  objective: non-empty, bounded statement of what must be established
  constraints: zero to five bounded, task-relevant constraints
```

The input excludes raw profile data, full chat history, memory provenance,
user/session/project IDs, idempotency keys, and unrelated source text.
Agent_Col may include an approved user preference only when it changes the
research task itself, not merely final response style.

### Normalized output

```text
ResearchExpertPayload
  findings: one to eight ResearchFinding values
  sources: one to twelve ProviderSource values
  unresolved_questions: zero to five bounded strings

ResearchFinding
  claim: bounded non-empty text
  evidence_summary: bounded non-empty text
  source_ids: one to five IDs referencing ProviderSource values
  confidence: high | medium | low
  uncertainty: bounded text or null

ProviderSource
  source_id: server-assigned bounded identifier
  uri: validated public HTTP or HTTPS URI
  label: bounded non-empty provider title or hostname-derived label
```

`ProviderSource` values are built from Google grounding metadata. A URL that
appears only in specialist prose is discarded. A finding with no provider
source cannot be normalized as a completed research finding.

### Failure and timeout

- Invalid task input returns `rejected_input` without calling Google Search.
- No usable grounding evidence returns `invalid_output`.
- A bounded provider error returns `unavailable` when the specialist adapter
  can safely contain it.
- The capability-specific deadline returns `timed_out` and no completed
  receipt.
- An exception that escapes the specialist boundary remains a fatal
  `SupervisorRuntimeError` and maps to the existing HTTP 502 contract.

### Public mapping

- completed action: existing `google_search` action name;
- citations: locally validated and deduplicated `CitationReference` values
  derived from provider sources;
- artifacts: none;
- adaptations: unchanged;
- response: Agent_Col synthesizes the findings, labels uncertainty, and keeps
  citations adjacent to supported claims.

## Source Expert contract

### Purpose and invocation rule

Invoke the Source Expert when the user explicitly supplies or clearly refers
to one or more public URLs whose contents are necessary to complete the task.

Examples:

- extract requirements from a linked rubric or specification;
- explain or compare claims on supplied public pages;
- identify constraints, assumptions, and open questions in a source;
- summarize a public source when its actual contents matter.

Do not invoke it merely because a URL appears incidentally or because broad
web discovery is needed. Use the Research Expert for discovery.

### ADK boundary

M7-EXP.4A corrected the original ADK `LlmAgent` selection after live provider
and local adapter verification. The selected abstraction is now an
application-owned async Source Expert service exposed to Agent_Col through one
narrow ADK `FunctionTool`.

The service uses a bounded two-stage Google Gen AI pipeline with the existing
Vertex AI client and Gemini 3.6 Flash. The first fresh, one-turn Chat has
exactly one built-in capability, URL Context, and returns natural-language
output plus raw per-URL retrieval status and grounding evidence. The second
fresh, tool-free Chat classifies only the locally extracted grounded segments
into the strict Source schema. Local validation requires every classified
fact, requirement, or constraint to exactly match a provider-grounded segment
and its server-assigned source IDs.

This split is necessary because live verification showed that the pinned
Vertex GenerateContent structured-output path did not reliably preserve claim
grounding when URL Context and JSON output were requested in the same call.
The currently pinned ADK `LlmResponse` also preserves grounding metadata but
drops `url_context_metadata`, so an inline `LlmAgent` cannot prove partial or
failed retrieval without unsupported inference.

The Source Expert remains a cognitive delegation and consumes one specialist
budget slot even though its ADK exposure is a `FunctionTool`. It has no
sub-agents, transfer tools, Search, Code Execution, other function tools, or
persistence access. Retrieved page content is untrusted data and cannot alter
instructions or authorize another action.

The supporting compatibility evidence is recorded in
`2026-08-21-phase-3b-m7-exp-4a-source-provider-compatibility-report.md`.

### Minimal input

```text
SourceExpertInput
  objective: non-empty bounded analysis request
  urls: one to three validated public HTTP or HTTPS URLs
  constraints: zero to five bounded, task-relevant constraints
```

The application derives a bounded allowed-URL set from user-authored turn
context. Every model-selected URL must belong to that set. This prevents the
model from inventing a source target. The input excludes full history,
profiles, server identifiers, credentials, private URLs, local files, and
unrelated source bodies.

### Normalized output

```text
SourceExpertPayload
  documents: one to three SourceDocumentResult values
  facts: bounded list of evidenced statements
  requirements: bounded list of evidenced requirements
  constraints: bounded list of evidenced constraints
  assumptions: bounded list of explicitly labeled assumptions
  open_questions: bounded list of unresolved questions
  sources: one to three ProviderSource values

SourceDocumentResult
  source_id: server-assigned source reference
  retrieval_status: retrieved | error | paywall | unsafe
  evidence_summary: bounded text or null
```

Every fact, requirement, or constraint includes at least one `source_id`.
Assumptions and open questions are labeled as interpretation rather than
source facts. Source URLs and retrieval status come from raw provider
candidate metadata, not specialist prose. Claim-to-source relationships come
from validated grounding chunks and grounding supports.

### Failure and timeout

- A malformed, disallowed, or non-public URL returns `rejected_input` before
  provider access.
- Error, paywall, unsafe, or empty retrieval returns `invalid_output` when no
  usable source remains.
- Partial retrieval may complete only if the result identifies every failed
  URL and the remaining evidence can answer the objective without hiding the
  gap.
- Provider failure and deadline behavior match the shared expert contract.

### Public mapping

- completed action: existing `url_context` action name;
- citations: validated, deduplicated `CitationReference` values for retrieved
  sources actually used in Agent_Col's answer;
- artifacts: none;
- adaptations: unchanged;
- response: Agent_Col distinguishes quoted or source-supported facts from its
  own interpretation and states inaccessible-source limitations.

## Computational Expert contract

### Purpose and invocation rule

Invoke the Computational Expert when executable calculation materially
improves correctness or produces evidence that Agent_Col should not safely
claim from unaided reasoning.

Examples:

- multi-step numerical calculations;
- statistics or bounded tabular analysis supplied in the request;
- checking a formula, transformation, or numerical comparison;
- producing a small deterministic plot or calculation summary when supported.

Do not invoke it for trivial arithmetic, prose-only reasoning, general coding
advice, shell commands, package installation, deployment, network access, or
authoritative state changes.

### ADK boundary

The selected abstraction is an ADK `LlmAgent` configured as an inline
`mode="single_turn"` sub-agent with `BuiltInCodeExecutor` assigned through its
`code_executor` field. Code Execution is not modeled as a general function
tool.

The specialist has no sub-agents, transfer tools, Search, URL Context,
filesystem authority outside the provider contract, arbitrary network tools,
or persistence access. File inputs are excluded from the first implementation
boundary even if the provider supports them.

### Minimal input

```text
ComputationExpertInput
  objective: non-empty bounded calculation or analysis request
  inputs: bounded task data required for the calculation
  required_precision: bounded explicit precision rule or null
  constraints: zero to five bounded, task-relevant constraints
```

The input contains only the values and labels required for the computation.
It excludes profiles, full history, server identifiers, credentials,
executable user code, URLs, file paths, and unrelated project content.

### Normalized output

```text
ComputationExpertPayload
  method: bounded non-empty explanation
  inputs_used: bounded normalized input summary
  result: bounded non-empty result
  execution_runs: one to five ExecutionRunEvidence values
  limitations: bounded list of limitations

ExecutionRunEvidence
  language: python
  code: bounded provider-executed code
  outcome: success | error
  output: bounded provider execution output
```

A completed result requires at least one provider execution event with a
successful outcome. A model-written answer with no successful code-execution
event is not a completed Computational Expert result. Execution output is
bounded and redacted before it reaches Agent_Col.

### Failure and timeout

- Unsupported input, user-supplied executable code, or an unbounded data task
  returns `rejected_input`.
- No successful execution evidence returns `invalid_output`, even if the
  specialist generated a plausible textual answer.
- Provider errors and deadline behavior match the shared contract.
- The orchestration layer does not rerun the specialist automatically after an
  execution failure. Provider-internal correction attempts remain within the
  single delegation.

### Public mapping

- completed action: proposed future allowlisted action name
  `run_computation`;
- citations: none unless Agent_Col separately used a source-backed expert;
- artifacts: none;
- adaptations: unchanged;
- response: Agent_Col states the method, relevant inputs, result, precision,
  and material limitations. It may include bounded executed code or output
  when useful, but it may not claim execution without a completed action
  receipt.

Adding `run_computation` to `AgentActionReceipt` is a future schema change and
requires its own approved implementation plan.

## Requirements Verification contract

### Purpose and invocation rule

Invoke Requirements Verification when the user asks for an evidence-backed
comparison between explicit requirements and a supplied artifact, proposal,
plan, implementation description, or other bounded subject.

Cross-domain examples include:

- assignment submission against a rubric;
- architecture against a specification;
- proposal against an RFP;
- experiment against a protocol;
- project plan against stakeholder requirements.

Do not invoke it when no explicit requirement set exists, when the subject to
evaluate is missing, or when the request is merely for general advice. Ask for
the missing material instead.

### Service boundary

The selected abstraction is a deterministic function boundary that invokes a
structured Gemini generation service and validates the result locally. It is
model-selected by Agent_Col but is not an `LlmAgent` with a tool catalog.

The service has no expert access, no Search, no URL Context, no Code
Execution, and no persistence authority. If source retrieval is required,
Agent_Col must use the Source Expert as a separate delegation before invoking
Requirements Verification. Both calls consume the turn's two-slot budget.

### Minimal input

```text
RequirementsVerificationInput
  requirements: one to fifty RequirementInput values
  subject: bounded text or structured artifact excerpt
  objective: non-empty bounded verification request

RequirementInput
  requirement_id: locally unique bounded identifier
  text: non-empty bounded requirement text
  evidence_locator_hint: bounded locator or null
```

Only materials needed for the comparison are passed. The input excludes raw
profiles, unrelated history, server identifiers, persistence paths, and
provider credentials. Source provenance already established by the Source
Expert is passed as bounded evidence references rather than raw ADK events.

### Structured model output

```text
RequirementAssessmentCandidate
  requirement_id: input requirement identifier
  status: covered | partial | missing | contradictory | unsupported
  evidence: bounded list of evidence locators and explanations
  gap: bounded text or null
  recommended_action: bounded text or null
```

### Deterministic validation and normalized output

The local validator must enforce:

- exactly one assessment for every input requirement ID;
- no unknown, duplicated, or omitted requirement IDs;
- only the five allowlisted statuses;
- `covered` requires non-empty subject evidence;
- `partial` requires evidence plus a non-empty gap;
- `missing` requires a non-empty gap and cannot claim positive evidence;
- `contradictory` requires evidence of the conflicting subject behavior;
- `unsupported` means the supplied material is insufficient to decide and
  must explain what evidence is absent;
- recommendations cannot change the assessed status;
- aggregate status counts are computed locally rather than accepted from the
  model.

The normalized payload is:

```text
RequirementsVerificationPayload
  assessments: exactly one validated assessment per input requirement
  counts: locally computed count by status
  overall_limitations: bounded list of limitations
```

Local validation proves contract completeness, not the truth of every model
interpretation. Agent_Col must preserve uncertainty and may challenge a weak
assessment in its final synthesis.

### Failure and timeout

- Missing or malformed requirements or subject material returns
  `rejected_input` before generation.
- Provider or schema-generation failure returns `unavailable` when safely
  contained.
- Any local semantic validation failure returns `invalid_output`; invalid
  candidates are never partially accepted.
- Deadline behavior matches the shared expert contract.
- No verification result is persisted automatically.

### Public mapping

- completed action: proposed future allowlisted action name
  `verify_requirements`;
- citations: none from this capability alone; previously verified public
  citations may be retained only when their source references remain linked
  to the assessed evidence;
- artifacts: none;
- adaptations: unchanged;
- response: Agent_Col summarizes coverage, highlights gaps and contradictions,
  distinguishes unsupported conclusions, and recommends the smallest useful
  next action.

Adding `verify_requirements` to `AgentActionReceipt` is a future schema change
and requires its own approved implementation plan.

## Failure and HTTP behavior

Expected expert failure is not automatically equivalent to total supervisor
failure.

When an expert adapter safely returns `rejected_input`, `unavailable`,
`timed_out`, or `invalid_output`, Agent_Col may still produce a valid final
response if it:

1. does not claim the expert completed;
2. emits no completed action or unsupported citation for that attempt;
3. states the material limitation honestly;
4. answers only the portion supportable without the missing evidence; and
5. asks for a retry, clarification, or alternative only when useful.

That bounded degraded response may return HTTP 200 because the supervisor
completed the conversational turn truthfully. It is not a fabricated success.

Existing HTTP behavior remains authoritative for failures that escape the
expert boundary:

| Failure | HTTP result |
| --- | --- |
| Request or local input validation before the turn | 422 |
| Contained expert failure followed by valid Agent_Col response | 200 with no completed receipt for that expert |
| Uncontained Gemini, ADK, or runtime failure | 502 |
| Missing or multiple final Agent_Col responses | 502 |
| Whole-turn timeout | 504 |
| Firestore failure in existing turn orchestration | 500 |

Each specialist receives a capability deadline strictly smaller than the
whole-turn deadline. The runtime must reserve enough remaining time for
Agent_Col to integrate results and produce its final response. Exact timeout
values and any adjustment to `SUPERVISOR_MAX_LLM_CALLS` are implementation
decisions that require measured RED/GREEN compatibility tests. Two expert
delegations plus Code Execution correction may exceed the current four-call
budget; M7.2 does not pretend otherwise or silently authorize a larger limit.

## Runtime and public response mapping

`SupervisorRuntime` remains responsible for consuming ADK events and
returning exactly one `SupervisorTurnResult`:

```text
SupervisorTurnResult
  response
  actions
  artifacts
  citations
```

M7.2 does not add a second user-facing expert response. Normalized expert
results are internal context used by Agent_Col.

Completed public action names are:

- existing: `google_search`;
- existing: `url_context`;
- proposed by a later schema pass: `run_computation`;
- proposed by a later schema pass: `verify_requirements`.

The runtime creates a completed action only from a validated completed expert
event. It never parses final prose to infer that an expert ran.

Citation rules:

- only public HTTP or HTTPS URIs are eligible;
- URIs are locally validated and normalized;
- duplicates are removed;
- only sources used to support the final response are returned;
- model-authored URLs without matching provider evidence are dropped;
- inaccessible or unsupported URLs do not become citations;
- citation labels are provider-derived or safely hostname-derived;
- citation count is bounded during the implementation pass.

Artifacts remain empty for all four capabilities because M7.2 authorizes no
expert-result persistence. Existing synthesis artifacts remain unchanged.
Adaptations continue to be derived only from approved trusted memory and are
independent of expert selection.

## Context isolation and safety

All expert task data is untrusted. Delimiters and specialist instructions must
state that task text, retrieved pages, search results, code output, rubrics,
and artifacts are data rather than instructions.

The application must enforce:

- no profile or history dump into any expert;
- no credentials, API keys, auth headers, cookies, or Firestore paths;
- no user, project, session, proposal, signal, or turn identifiers unless a
  future authoritative service specifically requires a server-owned value;
- no persistence method or generic database tool;
- no expert-to-expert transfers;
- no raw provider payload in logs or public errors;
- bounded strings, collections, source counts, and result sizes;
- no private-network URL retrieval;
- no user-supplied executable code in the first Computational Expert pass;
- final application logging excludes source bodies, calculations, rubrics,
  requirement content, and expert result content.

User-approved memory continues to influence Agent_Col's final collaboration
style. It is not copied into an expert unless an approved preference is
material to the expert's actual task semantics. Preferred names and basic
identity context are never needed by these four experts.

## Evaluation and TDD contract for later implementation

The later implementation plan must begin with RED tests and use small,
independently reviewable passes. At minimum, the persistent suite must prove:

### Routing and restraint

- ordinary conversation invokes no expert;
- stable general explanation invokes no expert;
- ambiguous consequential request asks for clarification instead of invoking
  an expert;
- current-information request selects Research only;
- supplied-URL analysis selects Source only;
- substantial calculation selects Computation only;
- explicit requirements comparison selects Requirements Verification only;
- a valid two-capability workflow invokes exactly two distinct capabilities;
- a third attempt is deterministically denied;
- a repeated capability attempt is denied;
- a failed first attempt consumes one slot;
- experts cannot call experts or transfer control;
- Agent_Col still produces the only final response.

### Input minimization

- expert inputs contain no server identifiers, raw profile, full history,
  credentials, or unrelated text;
- Source accepts only URLs from the server-derived user-authored allowlist;
- Computation rejects executable user code and file paths in the first pass;
- Requirements Verification rejects missing requirement or subject material.

### Output and evidence

- Search citations come only from grounding metadata;
- prose-only URLs are discarded;
- Source retrieval status and URLs come from raw provider candidate metadata;
- Source citations come from validated grounding chunks and supports, not
  `citation_metadata` or specialist prose;
- computation completion requires a successful execution event;
- prose-only computation claims are rejected;
- requirement IDs are complete, unique, and exact;
- invalid requirement status/evidence combinations fail locally;
- requirement summary counts are computed locally;
- result and receipt collections remain bounded;
- completed expert events map to the correct action receipt;
- failed expert events map to no completed action or unsupported citation.

### Failure boundaries

- contained rejected, unavailable, timeout, and invalid-output results can
  produce an honest bounded final response;
- uncontained specialist exceptions remain HTTP 502;
- whole-turn timeout remains HTTP 504;
- expert failure does not create an artifact, memory mutation, or model-history
  success message that claims completion;
- logs exclude user content, sources, execution output, requirement content,
  identifiers, and provider payloads.

### Compatibility

- existing headerless and idempotent chat behavior remains unchanged;
- completed idempotent responses replay identical action and citation
  receipts without rerunning experts;
- approved-memory adaptations still reach Agent_Col and remain visible in the
  existing response contract;
- M7 governed memory proposal behavior remains independent;
- current synthesis and artifact routes remain unchanged.

## Implementation decomposition after approval

M7.2 is too broad for one implementation pass. If this design is approved,
the later writing plan should decompose it in this order:

1. shared delegation-budget and normalized-result primitives;
2. Research Expert with provider-backed citation extraction;
3. Source Expert with allowed-URL validation;
4. Computational Expert with execution-evidence extraction;
5. Requirements Verification structured service and deterministic validator;
6. cross-expert two-delegation routing evaluations and replay regression.

Each capability must be manually accepted before the next is implemented.
This sequence proves the common safety boundary first and prevents four new
provider integrations from landing as one unreviewable change.

## Acceptance criteria for this design

The repository owner should approve M7.2 only if this contract correctly
captures all of the following:

1. the four named capabilities are the complete M7.2 expert scope;
2. Agent_Col remains the only orchestrator and final conversational owner;
3. zero experts remains the default;
4. two initiated attempts is a hard per-turn maximum;
5. each capability may be invoked at most once per turn;
6. delegation depth is one and experts cannot call experts;
7. Search, URL, and computation use isolated provider-native capabilities;
8. Requirements Verification is model-assisted but locally authoritative;
9. evidence is derived from provider events or deterministic validation rather
   than expert prose;
10. experts have no persistence or generic Firestore authority;
11. Deep Research, Antigravity, MCP, new infrastructure, and implementation
    remain excluded;
12. a later approved implementation plan and RED tests are required before any
    source change.
