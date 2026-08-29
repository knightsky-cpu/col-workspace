# M7-EXP.4D-R3.3 Production Routing Service Integration Design

## Status and authority

**Status:** Proposed for repository-owner review

This document defines how the manually accepted R3.1 routing contracts and
R3.2 Vertex provider boundary can enter Agent_Col's production chat lifecycle.
It changes no application behavior. Every implementation pass derived from
this design requires its own bounded plan, TDD cycle, manual verification, and
repository-owner acceptance.

This design is grounded in checkpoint `b64b73f` and the current behavior of:

- `main.py` and its idempotent `/api/chat` lifecycle;
- `chat_turns.py` and Firestore-backed turn claims;
- `supervisor.py` and its currently unrestricted cognitive expert catalog;
- `supervisor_runtime.py` and its invocation-scoped ADK sessions;
- `agent_col_routing.py` and `agent_col_routing_provider.py`;
- the Source and Research expert validation boundaries;
- the governed-memory decision and proposal lifecycle.

The stricter privacy, provenance, idempotency, receipt, and deterministic
authority rule wins if an implementation detail conflicts with an earlier
contract.

## Decision summary

The production change must be an explicit three-phase Agent_Col turn:

```text
Agent_Col routing decision
        |
        v
deterministic selected-expert execution (zero or one expert in v1)
        |
        v
responder-only Agent_Col final response
```

The existing ADK supervisor cannot remain the production responder unchanged.
It currently exposes the Source Expert as a tool and Research Expert as a
sub-agent. Calling the structured router and then invoking that supervisor
would permit a second probabilistic routing decision. Agent_Col could skip the
selected expert, invoke an unselected expert, or repeat a completed expert.
That would invalidate R3's authoritative routing boundary.

Production cutover therefore occurs only after all of these are available:

1. a responder-only Agent_Col application with no cognitive expert tools or
   sub-agents;
2. a deterministic executor for the router-selected Source or Research
   capability;
3. a turn orchestration service enforcing one outer deadline and returning
   normalized receipts;
4. FastAPI integration preserving idempotent claims, memory actions, and
   failure recovery.

No interim pass may wire the router into `/api/chat` while leaving the current
supervisor's cognitive expert catalog active.

## Existing production lifecycle

The current `/api/chat` order is:

```text
validate request
  |
  +-- optional idempotent claim
  |     `-- completed replay returns immediately
  |
  +-- load bounded history and collaboration profile
  +-- validate stored history and render approved memory
  +-- persist or recover deterministic user message ID
  +-- execute an explicit memory decision when present
  +-- renew an owned turn lease
  +-- invoke SupervisorRuntime
  +-- build ChatResponse
  `-- save headerless response or atomically complete claimed turn
```

This ordering is fundamentally correct. Routing belongs after authoritative
context loading, user-message persistence, any explicit memory decision, and
lease renewal—but before the final Agent_Col runtime invocation.

The completed replay remains before every model or expert call.

## Target lifecycle

```text
validated ChatRequest (message <= 10,000 characters)
  |
  +-- claim/replay idempotent turn
  |     `-- replay: return stored ChatResponse; zero provider calls
  |
  +-- load profile and bounded history
  +-- validate history and render approved memory context
  +-- persist/recover user message
  +-- execute and record explicit memory decision, if present
  +-- renew turn lease
  |
  v
AgentColTurnService.run_turn(command)           outer deadline: 90 seconds
  |
  +-- project public URLs from current + recent user messages
  +-- build minimal AgentColRoutingInput
  +-- request and locally validate RoutingDirective
  |
  +-- direct/clarify: execute no cognitive expert
  |
  +-- source: deterministic Source execution once
  |
  +-- research: deterministic Research execution once
  |
  +-- build bounded server-validated responder context
  +-- invoke responder-only Agent_Col
  `-- return response + server-derived actions/citations/proposals
  |
  v
save response or complete claimed turn atomically
```

## HTTP boundary and chat-message limit

`ChatRequest.message` currently uses the unbounded shared `NonEmptyStr` type.
The production routing input accepts at most 10,000 characters. The HTTP
contract must therefore introduce a dedicated `ChatMessageText` alias with:

- whitespace stripping;
- minimum length one;
- maximum length 10,000.

The shared `NonEmptyStr` alias must not be changed because it is used by other
response and schema surfaces. Oversized chat input returns FastAPI/Pydantic
HTTP 422 before idempotency, Firestore, routing, or provider access.

The normalized bounded message remains the value included in the idempotency
request fingerprint and persisted chat history.

## Routing input construction

The application constructs `AgentColRoutingInput`; the client and model never
construct it.

### Current message

Use the validated `ChatRequest.message` exactly once.

### URL candidates

Call `project_routing_url_candidates()` with:

- the current validated message; and
- text from only the `user` entries in the already validated, bounded session
  history, preserving chronological order at the call boundary.

The projection function then applies its accepted current-first and
newest-history-first ordering. Model-authored history must never contribute a
candidate.

For an idempotent claim, the existing history read already excludes the
deterministic current user-message ID. For a headerless turn, history is read
before the current message is saved. The current message therefore cannot be
duplicated through history in either path.

### Available capabilities

Capabilities are server configuration, not user input. Production version
1.0 exposes `source` and `research` only when their deterministic executor
adapters were constructed successfully from validated startup configuration.
Startup does not make a billable or failure-prone provider request merely to
declare a capability healthy. Runtime provider availability remains a
contained execution concern.

An unavailable capability is omitted. The application does not replace an
unavailable capability with another expert. Direct and clarify remain valid
with an empty capability set.

### Excluded context

Routing receives no profile, memory value, project ID, user ID, session ID,
turn ID, idempotency key, full history, model-authored URL, Firestore data,
expert output, credential, or authorization value.

## AgentColTurnService boundary

Create one application service responsible for cognitive orchestration but no
durable persistence:

```text
AgentColTurnCommand
  message
  recent_user_messages
  model_input_context
  source_message_id
  memory_decision_present
  turn_lease
  precompleted_actions
  precompleted_memory_proposals

AgentColTurnResult
  response
  actions
  artifacts
  citations
  memory_proposals
```

The command deliberately contains no database object or idempotency key. The
service cannot claim, renew, release, complete, or persist a turn. FastAPI and
the existing application services retain those authorities.

The service owns:

1. routing-input projection;
2. the structured Agent_Col routing request;
3. deterministic execution of the selected capability;
4. construction of bounded responder context;
5. responder-only Agent_Col invocation;
6. merging validated expert receipts with responder memory receipts.

It does not own:

- Firestore writes or reads;
- memory approval, revocation, or deletion;
- idempotency state;
- HTTP status mapping;
- authentication or ownership;
- artifact persistence;
- retries.

## Deterministic expert executor

The executor accepts only a locally validated directive and its exact routing
input. Version 1.0 permits zero or one expert attempt.

### Direct

No expert executes. The responder receives the validated route code.

### Clarify

No expert executes. The responder receives the validated clarification
question and is instructed to ask it naturally without adding unsupported
work.

### Source

The executor:

1. revalidates the directive against the exact routing input;
2. maps selected `url-N` identifiers to their server-owned public URLs;
3. constructs `SourceExpertInput` from the validated objective, mapped URLs,
   and constraints;
4. calls `SourceExpertService.analyze()` exactly once;
5. converts only a completed validated result into one `url_context` action
   and its provider-derived citations;
6. returns a content-free safe failure status otherwise.

The existing Source service is already directly callable and suitable for
this boundary. The ADK `FunctionTool` wrapper is not used by the deterministic
executor.

### Research

Research is currently coupled to ADK child-agent events inside
`SupervisorRuntime`. Production deterministic execution requires a dedicated
Research application adapter before cutover.

That adapter must:

1. accept only `ResearchExpertInput` constructed from the validated directive;
2. invoke the existing bounded Research agent in an isolated invocation;
3. normalize the final event through the existing grounding validators;
4. require completed provider grounding before returning content;
5. derive `google_search` and citation receipts only through
   `build_research_receipts()`;
6. expose no transfer, persistence, or nested-expert authority;
7. close its invocation-scoped session on success, error, timeout, or
   cancellation.

The executor may not treat the routing decision as proof that Google Search
ran. Research without validated provider grounding remains a contained
`invalid_output` failure and creates no completed action receipt.

### Expert failure

Source or Research failures do not trigger another expert and do not return to
model-controlled routing. If enough outer-deadline time remains, responder
mode receives only the capability, safe status, and a statement that no
validated evidence is available. Agent_Col may explain the limitation or ask
the user how to proceed, but may not provide unsupported current claims.

## Responder-only Agent_Col

Create a responder application separate from the existing cognitive-tool
supervisor definition.

The responder retains:

- Agent_Col's general collaborative identity;
- approved memory context and bounded session history;
- the governed `propose_memory_signal` tool when configured;
- one final user-facing response;
- explicit feedback and collaborative questioning behavior.

The responder exposes:

- no Source tool;
- no Research sub-agent;
- no cognitive expert transfer path;
- no generic Firestore or artifact write tool.

The existing `SupervisorRuntime` session lifecycle and memory-proposal receipt
handling may be reused only with a responder-only ADK `App`. Cognitive expert
trackers may remain temporarily inert, but no expert tool or sub-agent may be
reachable from the responder model. A later cleanup may remove obsolete
trackers after production cutover; that cleanup is not part of integration.

### Responder context

Server-generated context is appended to existing `model_input_context` and is
separate from the original user message. It contains:

- routing schema version and route;
- clarification question when applicable;
- selected capability and normalized safe status;
- a completed, locally validated expert result when available;
- server-derived action and citation summaries;
- explicit instructions not to repeat or contradict the route.

Raw provider events, source bodies, hidden reasoning, credentials, routing
input URLs unrelated to the selected Source task, and unvalidated model output
are excluded.

Expert results and retrieved content remain untrusted evidence even after
structural validation. They cannot authorize memory or application actions.

The original current user message is sent to the responder exactly once as
the ADK `new_message`. It is not duplicated inside server context.

## Receipts and final response ownership

Only application-derived receipts enter `ChatResponse`:

```text
completed Source   -> action: url_context + validated Source citations
completed Research -> action: google_search + validated Search citations
failed expert      -> no completed expert action or citations
direct/clarify     -> no cognitive expert action or citations
```

The responder cannot add, remove, or fabricate receipts. The turn service
merges expert receipts, explicit memory-decision receipts, and responder
memory-proposal receipts with the existing stable deduplication behavior.

Agent_Col remains responsible for interpreting evidence and writing the final
response. Specialists never become user-facing conversational owners.

## Deadline and lease contract

The full cognitive turn—routing, optional expert, and responder—runs under one
90-second monotonic outer deadline. The existing 120-second Firestore turn
lease therefore retains a 30-second safety margin for application overhead and
turn completion.

Inner constraints are:

- routing provider: maximum 15 seconds;
- Source or Research: existing bounded expert deadline, maximum 45 seconds;
- responder: receives the remaining outer time;
- expert execution begins only when at least the expert's required budget plus
  a 20-second responder reserve remains.

If routing consumes too much time to preserve the reserve, the selected expert
does not start. If an expert times out but at least the responder reserve
remains, responder mode may return an honest degraded answer. If the outer
deadline expires, the application returns the existing timeout classification
and releases an owned idempotent lease.

There is no orchestration retry. Provider SDK-internal retry behavior remains
outside application control and does not authorize a second logical expert
attempt.

## Idempotency and durable state

The existing durable ordering remains authoritative:

```text
claim/replay
  |
  +-- completed replay: stored response, zero routing/expert/responder calls
  |
  `-- owned turn: deterministic user message -> route -> optional expert
                  -> responder -> atomic completion
```

Routing directives and expert results are invocation state. They are not
stored in the user profile or treated as durable collaboration memory.

A process failure after read-only routing or expert execution but before turn
completion may repeat provider computation after lease expiry. That can repeat
cost but cannot duplicate authoritative state because:

- routing and cognitive experts are read-only;
- user/model message IDs remain deterministic for idempotent turns;
- governed memory actions retain their own turn-effect ledger;
- completed replays bypass all downstream calls;
- `complete_chat_turn()` remains the only durable response completion.

No route code or expert content is added to the chat-turn Firestore document
in this integration pass. Operational routing telemetry requires a later
privacy-reviewed observability design.

## Explicit memory-decision turns

A structured memory decision remains an authoritative application action and
executes before cognitive routing, as it does today. The subsequent message
still routes because the user may combine confirmation with a new request.

The responder receives the completed decision receipt and updated approved
profile. It cannot repeat the decision or propose the same memory again.

If routing fails after a memory decision completed, the existing partial
failure contract remains required: return the completed action safely, record
it in the idempotent turn ledger when applicable, and do not claim rollback.

## Failure mapping

| Failure boundary | HTTP behavior | Expert execution | Lease behavior |
| --- | --- | --- | --- |
| Invalid/oversized chat request | 422 | none | no claim |
| Completed idempotent replay | stored 200 response | none | unchanged |
| Routing provider failure | 502 | none | release owned lease |
| Routing timeout | 504 | none | release owned lease |
| Invalid routing output | 502 | none | release owned lease |
| Directive/input mismatch | 502 | none | release owned lease |
| Contained expert failure | honest 200 degradation when time remains | selected attempt consumed | complete normally |
| Responder provider/runtime failure | existing 502 contract | no repeat | release owned lease |
| Outer turn timeout | 504 | no repeat | release owned lease |
| Firestore failure | existing 500/409 contract | no new fallback | existing handling |

When a memory action completed before a routing or responder failure, the
existing partial-failure response and turn-effect recovery rules apply.

Logs may include only safe class names, route/capability codes, bounded attempt
counts, and latency. They exclude messages, URLs, IDs, profile values, expert
content, provider payloads, and model output.

## Lifespan composition

FastAPI lifespan continues to create one application-owned shared Vertex
`genai.Client` and one `MemoryEngine`. The shared GenAI client serves direct
SDK application services such as synthesis, routing, and Source. ADK
`Gemini` model wrappers for Research and responder runtimes create and own
their provider clients from the same validated `VertexAISettings`; they are
not the application-owned GenAI client.

Target composition is:

```text
application-owned shared Vertex GenAI client
  +-- routing provider boundary
  +-- SourceExpertService
  `-- synthesis service

validated VertexAISettings
  +-- isolated Research ADK application adapter
  `-- responder-only ADK App / SupervisorRuntime

MemoryEngine
  +-- synthesis service
  +-- trusted memory service
  `-- FastAPI idempotent chat lifecycle

AgentColTurnService
  +-- routing provider
  +-- deterministic expert executor
  `-- responder runtime
```

The application-owned GenAI client is closed once during application
shutdown. Invocation session resources owned by Research and responder
runtimes are deleted before shutdown completes. ADK-owned provider-client
cleanup must follow the public lifecycle exposed by the installed ADK version;
the implementation must not reach into private ADK attributes to force it.

The current unrestricted supervisor may remain as an unreferenced migration
surface until cutover is manually accepted. It must not run alongside the new
turn service for the same production request.

## Required TDD coverage

### Responder-only boundary

- responder app exposes governed memory only;
- Source tool and Research sub-agent are absent;
- original message appears exactly once;
- validated route/expert context is present and bounded;
- direct and clarify produce no cognitive receipts;
- responder cannot create expert receipts;
- existing memory proposal receipt behavior remains intact.

### Expert executor

- direct and clarify execute zero experts;
- Source maps selected IDs in directive order and calls Source once;
- unknown Source IDs fail before expert access;
- Research maps its exact intent and invokes Research once;
- Source cannot run for Research and Research cannot run for Source;
- failed expert attempts do not trigger fallback or a second expert;
- only completed validated results create receipts;
- cancellation and timeout release invocation resources.

### Turn orchestration

- routing input includes current message and only recent user-authored URLs;
- profile, server IDs, model-authored URLs, and full history are absent;
- direct, clarify, Source, and Research reach responder mode correctly;
- route failure prevents expert and responder access;
- outer timeout contains every phase;
- responder reserve prevents late expert startup;
- no route executes more than one expert in version 1.0.

### FastAPI and idempotency

- messages over 10,000 characters return 422 before service access;
- completed replay performs zero routing, expert, and responder calls;
- owned turn order remains claim, context, renewal, turn service, completion;
- routing failures release owned leases and save no model response;
- headerless routing failures save no model response;
- completed memory actions survive later routing failure;
- successful responses replay identical expert actions and citations;
- no duplicate user or model messages are written.

### Security and logging

- failures do not log messages, URLs, IDs, memory values, expert output, or
  provider payloads;
- prompt injection in messages or URLs cannot select an unavailable capability
  or bypass exact-input validation;
- retrieved expert content cannot call tools or propose memory;
- responder has no cognitive expert catalog.

## Implementation sequence

Production cutover is intentionally decomposed:

### R3.3A — Responder-only Agent_Col boundary

Create and test the responder-only ADK application and bounded responder
context. Do not modify `/api/chat` or execute cognitive experts.

### R3.3B — Deterministic expert executor

Add the direct Source adapter, isolated Research application adapter, exact
directive mapping, contained expert failures, and application-derived
receipts. Do not modify `/api/chat`.

### R3.3C — Turn orchestration service

Compose routing, expert execution, responder mode, deadline accounting, and
safe service errors behind one persistence-free `AgentColTurnService`. Do not
modify `/api/chat`.

### R3.3D — FastAPI and idempotent cutover

Add the 10,000-character chat bound, lifespan composition, `/api/chat`
integration, failure mapping, lease recovery, and replay regressions. Remove
the current unrestricted supervisor from the live request path only after the
new path is fully green.

Each stage must be independently reviewed and manually accepted. R3.3D must
not begin until R3.3A through R3.3C are accepted.

## Rejected partial integrations

### Router followed by the current unrestricted supervisor

Rejected because the supervisor can make a second cognitive routing decision.

### Prompt the current supervisor to obey the route

Rejected because a prompt is advisory and cannot prevent unselected or
duplicate tool execution.

### Keep expert tools but disable them through session state

Rejected because runtime state is not an authoritative tool-catalog boundary
and increases ADK-internal coupling.

### Deterministically route only Source while leaving Research model-managed

Rejected because it creates two competing expert authority models and makes
receipts, budgets, and failure behavior inconsistent.

### Persist routing directives in Firestore

Rejected because routing is invocation state, not user memory or durable
business truth. Persisting it adds privacy surface without improving turn
idempotency.

### Fall back to unrestricted `AUTO` after routing failure

Rejected because it bypasses the exact boundary the structured router exists
to enforce.

## Acceptance criteria for this design

The design is ready for implementation planning only if the repository owner
agrees that:

1. no production cutover occurs until responder-only and deterministic expert
   boundaries exist;
2. Agent_Col remains the semantic route decision-maker and final responder;
3. application code executes only the validated selected route;
4. version 1.0 permits at most one cognitive expert;
5. Firestore and FastAPI retain durable authority;
6. governed memory remains separately controlled;
7. the implementation sequence is R3.3A, R3.3B, R3.3C, then R3.3D.
