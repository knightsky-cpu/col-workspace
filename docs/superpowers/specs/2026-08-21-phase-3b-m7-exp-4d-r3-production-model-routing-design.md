# M7-EXP.4D-R3 Production Model-Controlled Routing Boundary Design

## Status and review gate

**Status:** Proposed for repository-owner review

This document is a design contract. It does not authorize production-code,
test, dependency, schema, API, or infrastructure changes. A bounded
implementation plan and separate explicit approval are required before source
changes begin under [`AGENTS.md`](../../../AGENTS.md).

The design is grounded in repository checkpoint `b7f7bb5`, the manually
accepted M7-EXP.4D-R2.1 Vertex compatibility evidence, the approved M7.2 core
expert contract, the existing ADK `SupervisorRuntime`, the Source and Research
expert boundaries, the governed-memory tool, and the chat-turn idempotency
contract.

This contract remains subordinate to:

- [`AGENT_COL_IDENTITY_AND_ALIGNMENT.md`](../../../AGENT_COL_IDENTITY_AND_ALIGNMENT.md);
- [`DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`](../../../DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md);
- [`2026-08-21-phase-3b-m7-2-core-expert-routing-design.md`](2026-08-21-phase-3b-m7-2-core-expert-routing-design.md);
- [`2026-08-21-phase-3b-m7-exp-4a-source-provider-compatibility-report.md`](2026-08-21-phase-3b-m7-exp-4a-source-provider-compatibility-report.md);
- [`turn-idempotency.md`](../../design/turn-idempotency.md).

If this document conflicts with those contracts, the stricter privacy,
provenance, idempotency, evidence, tool-restraint, or deterministic-authority
boundary wins unless the repository owner explicitly approves a revision.

## Governing decisions

This contract preserves these repository-owner decisions:

1. Agent_Col decides whether an expert materially improves the turn.
2. No keyword table, regular-expression policy, SQLite router, or application
   heuristic decides user intent.
3. Deterministic application code validates and enforces the decision after
   Agent_Col makes it.
4. Agent_Col remains the only user-facing conversational owner.
5. Direct, tool-free collaboration remains the default.
6. Experts are read-only, depth-one cognitive capabilities with no persistence
   authority and no ability to call other experts.
7. Firestore remains durable truth; ADK sessions remain invocation-scoped.
8. Governed memory remains a separate action plane requiring explicit user
   approval. Expert routing cannot write memory.
9. Google Search execution inside the Research Expert remains model-managed.
   A routed Research attempt is not proof that Search ran; ungrounded output
   still fails closed.
10. Deep Research, Antigravity, MCP, new infrastructure, Computational Expert,
    and Requirements Verification remain outside this pass.

This contract supersedes only the use of unconstrained ADK `AUTO` selection
for the Source and Research expert boundary. It does not revive the superseded
deterministic Research routing proposal.

## Evidence that motivates the change

M7-EXP.4D demonstrated two separate facts.

First, allowing the existing ADK supervisor to choose `analyze_source`
directly remained probabilistic. For the same explicit two-URL comparison,
the supervisor sometimes called Source and sometimes answered confidently
from model memory. Prompt strengthening did not make that boundary reliable.

Second, the isolated structured Agent_Col decision call reliably separated
the capability decision from execution after the output-budget correction:

- ten of ten repeated two-URL decisions returned `source`;
- all seven routing and restraint scenarios returned their expected routes;
- stable and incidental-URL cases returned `direct`;
- explicit no-tool instructions returned `direct`;
- ambiguous URL intent returned `clarify`;
- current externally verifiable intent returned `research`;
- every accepted run exited with status zero.

The R2.1 investigation also proved that a simple four-way routing decision can
consume most of the provider output budget through hidden thinking. The
production routing request therefore requires `ThinkingLevel.MINIMAL`, strict
local validation, and distinct provider-versus-model-output failure classes.

## Decision

Production routing becomes an explicit cognitive phase of Agent_Col rather
than an incidental side effect of final-response generation.

```text
Validated chat turn
  |
  v
Agent_Col Routing Service
  |  tool-free, structured, MINIMAL thinking
  |  no user-facing answer and no persistence
  v
Strict RoutingDirective
  |
  v
Application Routing Executor
  |  validates directive and claims delegation budget
  |  invokes zero or one selected expert in v1
  v
Validated ExpertResult or safe failure envelope
  |
  v
Responder-mode Agent_Col
  |  original user message + bounded collaboration context
  |  validated routing/expert context
  |  governed-memory tool remains available
  |  cognitive expert tools are unavailable
  v
SupervisorTurnResult
  |
  v
ChatResponse + server-derived receipts
```

The routing model and responder model are two constrained phases of the same
Agent_Col product identity. The router is not a new conversational agent or a
profession-specific specialist. It chooses the smallest useful capability;
the responder interprets the result and owns the final collaboration.

The application does not choose the semantic route. It enforces the route
Agent_Col selected and prevents any unselected expert from executing.

## Why the routing directive must contain task arguments

A bare `source` or `research` label is insufficient for production execution.
If the application sent that label back to the unrestricted supervisor and
asked it to call the tool, the system would reintroduce the same probabilistic
selection failure that R2 exists to remove.

The routing phase must therefore produce a strict, capability-specific intent
alongside the route. Application code converts that validated intent directly
into the selected expert's existing input contract.

Conceptually:

```text
RoutingDirective
  schema_version: "1.0"
  route: direct | clarify | source | research
  clarifying_question: bounded text or null
  source_intent: SourceRoutingIntent or null
  research_intent: ResearchRoutingIntent or null

SourceRoutingIntent
  objective: bounded text
  selected_url_ids: one to three server-issued candidate IDs
  constraints: zero to five bounded strings

ResearchRoutingIntent
  question: bounded text
  objective: bounded text
  constraints: zero to five bounded strings
```

Cross-field validation is authoritative:

- `direct` has no question or expert intent;
- `clarify` has exactly one question and no expert intent;
- `source` has exactly one Source intent and nothing else;
- `research` has exactly one Research intent and nothing else;
- extra fields, unknown routes, duplicate URL IDs, or mismatched payloads are
  invalid model output;
- no hidden rationale, chain of thought, confidence score, server identifier,
  or persistence instruction is accepted.

The production directive is intentionally richer than the R2 compatibility
schema. Expanding it requires its own RED/GREEN provider compatibility pass
before orchestration integration.

## Routing input and context minimization

The routing request receives only information needed to choose a capability:

```text
RoutingInput
  current_message: validated bounded user text
  candidate_urls: bounded server-derived public URL references
  available_capabilities: source | research
```

It does not receive:

- the user profile or approved memory values;
- full chat history;
- project, user, session, turn, proposal, or signal identifiers;
- Firestore paths or documents;
- idempotency keys or hashes;
- credentials, cookies, authorization headers, or provider configuration;
- raw Search, URL Context, or expert output;
- model-authored URLs from prior responses.

### URL candidate projection

Application code may extract URL candidates from the current user message and
bounded recent **user-authored** history. It does not interpret whether those
URLs should be used. Each validated public HTTP or HTTPS URL receives an
invocation-scoped identifier such as `url-1`.

The router selects identifiers, never rewrites or invents URLs. The application
maps selected IDs back to their exact validated URLs before constructing
`SourceExpertInput`.

The projection must:

- reject credentials, localhost, private addresses, and disallowed hostnames;
- normalize and deduplicate URLs;
- preserve whether a candidate came from the current message or recent
  user-authored context;
- include at most a bounded number of candidates;
- never include a URL appearing only in an earlier model response;
- provide no surrounding historical prose beyond the current message.

When the requested Source task needs more than three URLs, refers to no usable
candidate, or is consequentially ambiguous, Agent_Col must choose `clarify`.
It may not silently omit URLs or fabricate a target.

### Chat-message bound

The current `ChatRequest.message` is non-empty but not length-bounded. A
production router cannot safely accept unlimited input. The implementation
plan must introduce a dedicated bounded chat-message type rather than changing
the shared `NonEmptyStr` alias. The proposed ceiling is 10,000 characters,
matching the existing synthesis-source boundary. This is an intentional HTTP
422 contract change and requires explicit implementation approval and tests.

## Route semantics

### Direct

Choose `direct` when Agent_Col can answer from stable knowledge, supplied text,
or ordinary collaborative reasoning without materially benefiting from a
current-evidence or URL-analysis expert.

Direct includes:

- ordinary conversation and emotional support;
- stable explanations;
- writing, transformation, brainstorming, and planning using supplied text;
- incidental URLs whose contents are unnecessary;
- explicit instructions not to use external tools;
- tasks that may still legitimately use the governed-memory proposal tool.

No cognitive expert executes.

### Clarify

Choose `clarify` when a consequential target, source, scope, or intent is
missing. The directive supplies one concise question. No cognitive expert
executes before the user answers.

The question is operational context for responder-mode Agent_Col, not a public
response returned directly by the routing service. This preserves one final
response path and allows existing governed-memory behavior to remain
consistent.

### Source

Choose `source` only when one to three supplied or clearly referenced public
URLs must be retrieved to satisfy the request. The validated Source intent is
converted directly to `SourceExpertInput`, and the existing
`SourceExpertService` executes once.

The application, not a second model decision, initiates the selected Source
execution. URL Context remains provider-managed inside the existing two-stage
Source service, and existing evidence validation remains authoritative.

### Research

Choose `research` when the task materially requires current, niche, or
externally verifiable public evidence that was not supplied through a specific
URL.

The Research intent is converted directly to `ResearchExpertInput`. A bounded
application adapter invokes the existing Research Expert once and normalizes
its ADK events through the existing grounding validator.

This route guarantees a Research **attempt**, not a Google Search execution.
Gemini still decides whether its built-in Search capability runs. A result
without provider grounding remains `invalid_output`, produces no completed
`google_search` receipt, and cannot support current factual claims.

## Deterministic routing executor

The executor is an application service, not another model and not a generic
tool router. It accepts only a locally validated `RoutingDirective` and the
server-owned turn execution context.

Its authority is limited to:

1. checking that the selected capability is enabled;
2. mapping server-issued URL IDs to validated URLs;
3. constructing the selected expert's strict input;
4. atomically claiming one specialist attempt at depth one;
5. invoking exactly the selected expert once;
6. returning a normalized `ExpertResult` or safe failure envelope;
7. deriving internal receipts from validated evidence.

It cannot:

- change `direct` into an expert route;
- select a different expert after failure;
- execute both Source and Research in routing version 1.0;
- retry at the orchestration level;
- call persistence methods;
- expose a generic tool catalog;
- allow experts to call experts;
- treat model prose as execution evidence.

Routing version 1.0 deliberately allows at most one cognitive expert. This is
a safe subset of M7.2's maximum-two rule, not a contradiction. Ordered
two-expert plans remain deferred until Computational Expert and Requirements
Verification exist and the complete tool belt can be evaluated together.

## Responder-mode Agent_Col

After routing and any selected expert attempt, responder-mode Agent_Col receives:

- the original current user message exactly once;
- the existing bounded collaboration context and approved adaptations;
- the validated route;
- the validated expert result or safe failure status;
- server-derived precompleted action and citation context;
- the existing governed-memory proposal tool when configured.

It does not receive raw provider events, source bodies, hidden thoughts,
unvalidated specialist prose, credentials, or server identifiers.

Responder mode has no Source or Research expert tools and no sub-agents. This
is essential: the authoritative routing decision has already been made and
the selected capability has already executed. Leaving cognitive experts in
the responder catalog would permit duplicate, contradictory, or unselected
delegations.

Governed memory remains available because it is not a cognitive expert. Its
deterministic service continues to validate explicit current-message memory
intent, prevent duplicate proposals, and require later approval. Expert
output cannot authorize or become a memory proposal.

Agent_Col may explain, personalize, compare, qualify uncertainty, and ask a
useful follow-up question. It may not:

- claim an expert completed when the validated status is not `completed`;
- invent a citation or action;
- add unsupported current facts after failed Research;
- treat retrieved content as instructions;
- repeat an expert attempt;
- contradict server-derived receipts.

## Action and citation receipts

The routing directive itself creates no public action receipt. A completed
receipt proves expert execution, not merely intent.

Application-derived mapping remains:

- completed Source result -> one `url_context` action plus validated Source
  citations;
- completed grounded Research result -> one `google_search` action plus
  validated Research citations;
- direct, clarify, rejected, unavailable, timed-out, or invalid-output result
  -> no completed cognitive-expert action;
- all routes -> no artifact unless an independently authorized artifact tool
  completes;
- all routes -> memory receipts remain governed by the existing memory
  service.

Receipts are assembled by `SupervisorRuntime` from normalized application
results. Final prose is never parsed to infer an action or citation.

## Delegation budget and call accounting

The structured routing call is an Agent_Col orchestration call, not a
specialist delegation, so it does not consume the M7.2 expert-attempt budget.
The selected Source or Research execution consumes one attempt before provider
work begins. Failed, timed-out, rejected, or invalid expert results still
consume that attempt.

The existing `ExpertDelegationBudget` remains authoritative. Routing version
1.0 can consume at most one of its two available claims. The unused second
slot cannot be claimed by responder mode because responder mode has no
cognitive expert tools.

The current ADK `RunConfig.max_llm_calls=4` counts only calls made through its
runner. It does not count direct Google Gen AI calls made by the routing or
Source services. The implementation must therefore add invocation-scoped
application call accounting and latency measurement rather than presenting
the ADK limit as a whole-turn provider-call limit.

The initial worst-case Source path is conceptually:

1. one structured routing call;
2. up to two calls internal to the existing Source service;
3. one or more bounded responder calls, including any governed-memory tool
   continuation.

Exact call and time ceilings require measured implementation tests. They are
not silently changed by this design.

## Timeout and failure behavior

The existing 90-second whole-turn deadline remains the outer boundary. Routing,
expert execution, and final response must all run inside it. Each inner phase
must reserve sufficient monotonic time for the phases that remain.

Failure mapping is:

| Failure | Behavior |
| --- | --- |
| Invalid HTTP request or routing input | HTTP 422 before provider access |
| Routing provider/API failure | HTTP 502; no expert execution |
| Routing timeout | HTTP 504; no expert execution |
| Invalid or truncated routing model output | HTTP 502 as a distinct internal classification |
| Contained expert failure | Agent_Col may return honest HTTP 200 degradation with no completed expert receipt |
| Escaped expert/runtime failure | HTTP 502 |
| Missing or multiple final Agent_Col responses | HTTP 502 |
| Whole-turn timeout | HTTP 504 |
| Firestore failure | Existing HTTP 500 contract |

There is no automatic orchestration retry and no fallback to unrestricted ADK
`AUTO` expert selection after a routing failure. Such fallback would bypass
the accepted decision boundary.

The production routing request retains:

- Vertex AI ADC through the existing shared Google Gen AI client;
- `gemini-3.6-flash`;
- JSON response MIME type and provider-safe response schema;
- strict local Pydantic validation;
- `temperature=0`;
- `max_output_tokens=256` unless the richer directive spike disproves it;
- `ThinkingLevel.MINIMAL`;
- a bounded timeout;
- no tools and no automatic function execution.

The current SDK emits an AFC warning even though the R2 request has no tools.
The implementation plan may test explicit AFC disabling as a separate
configuration assertion, but warning cleanup is not evidence that routing is
correct and must not replace live directive verification.

## Idempotency and persistence order

The existing idempotency claim occurs before routing or expert execution.

```text
Claim or replay chat turn
  |
  +-- completed replay -> return stored ChatResponse immediately
  |
  `-- owned turn -> load context, persist deterministic user message,
                    renew lease, route, execute selected expert,
                    generate final response, complete turn transaction
```

Consequences:

- a completed replay performs no routing, expert, or responder call;
- the stored `ChatResponse` replays identical action and citation receipts;
- the routing directive is invocation state and is not a competing durable
  source of user intent or memory;
- a process failure after read-only expert work but before turn completion may
  repeat provider computation and cost on retry;
- deterministic message IDs and transactional turn completion still converge
  on one durable model response for an idempotent turn;
- future side-effecting tools require their own idempotency contract;
- headerless requests retain existing non-replay behavior.

Routing metadata is not added to the user profile, collaboration memory, or
artifact collections. A later observability pass may store or aggregate only
bounded operational route codes after separate privacy review.

## Security and trust boundaries

- User text, history-derived URL references, retrieved content, Search output,
  and expert results are untrusted data.
- Routing has no tools, persistence access, profile access, or server IDs.
- URL selection is restricted to server-derived, public, user-authored
  candidates.
- Expert inputs contain no raw profile, full history, credentials, or
  unrelated text.
- Experts have no sub-experts, transfer capability, memory authority, or
  artifact authority.
- Responder mode receives only normalized results and safe status values.
- Logs may include route code, capability code, safe outcome class, bounded
  call counts, and latency. They exclude messages, URLs, source bodies,
  findings, memory values, identifiers, provider payloads, and hidden
  reasoning.
- No route or expert result becomes durable user memory without the separate
  governed-memory proposal and approval lifecycle.

## Considered approaches

### Keep unrestricted ADK `AUTO` expert selection

Rejected as the production reliability boundary. It preserves natural model
choice, but repeated live evidence showed that the same explicit Source task
can skip Source and receive an unsupported answer from model memory.

### Add deterministic keyword or database routing

Rejected by repository-owner decision. It would move semantic intent judgment
from Agent_Col into brittle application policy and create prompting friction.

### Use the structured decision only as an advisory prompt

Rejected. Telling a second unrestricted model that Source was selected does
not guarantee that it will invoke Source and permits contradictory routing.

### Force ADK function mode `ANY`

Rejected for the shared supervisor. `ANY` requires a function call, which
breaks direct restraint and can select the wrong tool from a catalog that also
contains governed memory. Post-tool final response also requires returning to
natural-language generation. A dynamic callback could attempt to toggle these
modes, but it is more coupled to ADK request internals than the selected
application dispatcher.

### Structured Agent_Col directive plus deterministic executor

Selected. The model owns semantic capability selection and minimal task
formulation. Application code validates the decision, executes only the
selected capability, derives receipts, and returns normalized evidence to the
same Agent_Col identity for the final response.

## Required TDD and evaluation contract

A later implementation plan must begin with RED tests proving:

### Directive schema

- every route accepts only its matching payload;
- extra fields and hidden rationale are forbidden;
- Source selects only known, unique URL IDs;
- Research input is bounded and locally valid;
- direct and clarify cannot carry expert intents;
- a richer structured directive remains provider-compatible under MINIMAL
  thinking across repeated live calls;
- provider, timeout, model-output, and local-validation failures remain
  distinct and content-safe.

### Routing input

- only current message and bounded user-authored URL references enter routing;
- profile, full history, server IDs, credentials, and model-authored URLs are
  absent;
- public URL validation and normalization occur before provider access;
- oversized chat input receives HTTP 422 rather than truncation;
- invalid or unavailable URL references cannot execute Source.

### Execution

- direct and clarify execute no cognitive expert;
- Source executes exactly once when selected;
- Research attempts exactly once when selected;
- an unselected expert cannot execute;
- failed expert execution consumes its claim;
- responder mode exposes no cognitive expert tools;
- experts cannot call experts;
- routing version 1.0 cannot consume a second specialist slot.

### Response ownership and receipts

- Agent_Col produces exactly one final response;
- only completed validated evidence produces an action or citation;
- failed Research cannot support current factual claims;
- expert output cannot authorize memory;
- governed-memory behavior remains available in responder mode;
- final prose cannot fabricate receipts;
- normalized evidence is bounded and treated as untrusted context.

### Idempotency and failure

- completed replay bypasses router, expert, and responder;
- same-key conflict and in-progress behavior remain unchanged;
- provider failure releases the owned turn lease as today;
- completed receipts replay identically;
- headerless chat remains operational;
- routing and expert work never write profile or artifact state.

### Live evaluation

- repeated explicit one- and multi-URL tasks choose and execute Source;
- current-evidence tasks choose Research and either return grounded evidence or
  an honest fail-closed result;
- stable, incidental-URL, no-tool, and ambiguous cases preserve restraint;
- action and citation receipts match actual expert events;
- no test claims Search completion when provider grounding is absent.

## Implementation decomposition after design approval

This architecture must not land as one source-changing pass.

1. **R3.1 — Directive and routing-input contracts:** define the richer strict
   directive, URL candidate projection, and offline validation tests. No
   production orchestration.
2. **R3.2 — Provider-compatible routing service:** evolve the accepted R2
   spike into an injectable service and repeat the live decision evaluation.
   No expert execution.
3. **R3.3 — Application routing executor for Source:** execute the selected
   Source service directly, derive receipts, and introduce responder mode with
   all cognitive expert tools removed. Preserve existing direct and governed-
   memory behavior.
4. **R3.4 — Research execution adapter:** expose the current bounded Research
   Expert through the same executor contract while retaining fail-closed
   grounding validation.
5. **R3.5 — Responder-mode supervisor and FastAPI/idempotency integration:**
   wire the full route-execute-respond lifecycle under one whole-turn deadline
   and prove replay behavior.
6. **R3.6 — Live routing, restraint, evidence, and replay evaluation:** run the
   complete production path repeatedly before checkpoint acceptance.

Each implementation pass requires its own plan, RED evidence, focused tests,
manual acceptance, and checkpoint authorization.

## Stop and revise conditions

Implementation must stop for a new design decision if evidence shows:

- the richer directive cannot remain provider-compatible under bounded output;
- responder mode cannot exclude cognitive expert tools without breaking
  governed memory;
- direct application invocation cannot preserve validated ADK/provider events;
- Research cannot be adapted without creating a second durable session or
  bypassing grounding validation;
- current-message and URL-reference context is insufficient for correct route
  selection;
- the change requires a new dependency, queue, worker, datastore, public
  endpoint, or authentication model;
- the 90-second whole-turn boundary cannot leave time for routing, one expert,
  and final response;
- idempotent replay would repeat a completed expert operation;
- any implementation grants the router or expert persistence authority.

## Design acceptance criteria

The repository owner should approve this contract only if it correctly states
that:

1. Agent_Col, not application keywords, decides the semantic route.
2. The structured directive is authoritative after strict local validation.
3. The application executes only the selected expert and does not ask a second
   model to make the same selection again.
4. Responder-mode Agent_Col remains the sole final conversational owner.
5. Direct answers remain the default and execute no cognitive expert.
6. Routing version 1.0 permits at most one expert, depth one.
7. Source URLs can only come from server-validated user-authored candidates.
8. Research routing guarantees only an attempt; provider grounding still
   determines whether Research completed.
9. Governed memory remains separate, explicit, and available to responder
   mode.
10. Receipts derive from validated execution rather than routing intent or
    final prose.
11. Firestore and chat-turn idempotency remain authoritative.
12. Production integration is decomposed into separately approved TDD passes.
