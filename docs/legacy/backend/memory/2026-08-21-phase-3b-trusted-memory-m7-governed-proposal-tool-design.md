# Phase 3B Trusted Memory M7 Governed Proposal Tool Contract Design

## Status and review gate

This document is the M7.1 design deliverable. The repository owner **approved
this design on August 21, 2026**. That approval authorizes this design contract,
not a production-code, test, dependency, API, or Firestore change. A separate
implementation plan and a separate explicit approval are required before
source changes begin under
[`AGENTS.md`](../../../../AGENTS.md).

The design is grounded in repository commit
`780bdefe940bb0e75a77dcfa8e24e12f12c62f81`, the manually accepted M6.2.3
turn-idempotency pass, the installed `google-adk==2.7.0` package, and the
official Google ADK public contracts linked below.

## Governing contracts

M7 remains subordinate to:

- [`docs/design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md`](../../../design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md)
- [`docs/design/DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md`](../../../design/DOCUMENTATION_AND_REPRODUCIBILITY_CONTRACT.md)
- [`2026-08-19-hybrid-adk-supervisor-contract-design.md`](../../architecture/2026-08-19-hybrid-adk-supervisor-contract-design.md)
- [`2026-08-20-phase-3b-trusted-memory-design.md`](2026-08-20-phase-3b-trusted-memory-design.md)
- [`2026-08-20-phase-3b-trusted-memory-m6-idempotency-design.md`](2026-08-20-phase-3b-trusted-memory-m6-idempotency-design.md)

If this document conflicts with those contracts, the stricter consent,
privacy, provenance, idempotency, or user-control boundary wins unless the
repository owner explicitly approves a revision.

## Product outcome

M7 gives Agent_Col one narrowly governed way to say:

> The user's current message may contain an explicit collaboration preference
> or allowed light identity detail. Create a pending proposal so the user can
> inspect and approve or reject it.

The tool does **not** let Agent_Col write active profile memory. A proposal is
operational confirmation state, not a learned fact. The value becomes active
only when a later request carries the existing structured
`memory_decision` authorization.

This distinction preserves the product claim:

> Agent_Col adapts from explicit, user-approved collaboration memory with
> visible provenance and user control.

It does not claim autonomous learning, inferred profiling, or secret memory.

## Verified implementation baseline

The repository already provides:

- a bounded ADK supervisor with fresh invocation-scoped in-memory sessions;
- Firestore as the sole durable history and collaboration-memory source;
- typed allowlisted memory categories and values;
- preferred-name normalization and current-message grounding rules;
- transactional pending-proposal slots by category;
- structured approval and rejection through `/api/chat`;
- correction, revocation, hard deletion, and bounded inspection;
- deterministic active-memory context plus adaptation receipts;
- optional durable chat-turn idempotency with deterministic message IDs,
  leases, completed-response replay, and conflict detection;
- server-derived action receipts for existing deterministic memory actions.

The repository does not yet provide:

- a proposal operation on `TrustedMemoryService`;
- an ADK `propose_memory_signal` function tool;
- source-message and turn provenance in `SupervisorTurnContext`;
- extraction of proposal receipts from ADK function-response events;
- `memory_proposals` in the live `ChatResponse` or turn-replay contract;
- typed partial-failure responses after a proposal commits;
- a durable one-proposal-per-source-message arbitration boundary;
- live tool-restraint and proposal-routing evidence.

The installed ADK version was inspected directly:

```text
google-adk 2.7.0
FunctionTool(func, *, require_confirmation=False)
ToolContext is google.adk.agents.context.Context
Context exposes state, function_call_id, invocation_id, session, and actions
```

The installed implementation also executes multiple function calls from one
model response with `asyncio.gather()`. Therefore an instruction saying
"call this tool once" is not a concurrency control. The same behavior is
visible in the official ADK
[`functions.py` execution path](https://github.com/google/adk-python/blob/main/src/google/adk/flows/llm_flows/functions.py).

Official ADK source confirms that `FunctionTool` supports async callables,
automatically injects its context parameter without exposing that parameter
to the model, and returns structured function responses. See the official
[`FunctionTool` implementation](https://github.com/google/adk-python/blob/main/src/google/adk/tools/function_tool.py)
and [ADK context documentation](https://github.com/google/adk-docs/blob/main/docs/context/index.md).

## Normative refinements to the parent trusted-memory design

M7.1 preserves the parent design's product and consent boundaries but narrows
four implementation details now that M6.2 turn idempotency and ADK 2.7.0 are
live:

1. the proposal ID changes from a random suffix to a deterministic,
   source-message-derived suffix so an incomplete idempotent turn can retry
   without creating a different proposal;
2. at-most-one proposal changes from an instruction-only rule to a
   transactional source-message origin guard because ADK can run tool calls
   concurrently;
3. a successful proposal on an idempotent turn is recorded on the turn ledger
   in the same transaction as the proposal so process failure cannot erase
   side-effect evidence;
4. ADK's built-in tool confirmation is not used because the existing durable
   Firestore proposal and structured next-turn decision are the authoritative
   cross-session consent mechanism.

These are deliberate corrections, not incidental implementation choices. The
repository owner must approve this document before they supersede the parent
design's random-ID and instruction-only details.

## Goals

M7 must:

1. expose one narrow proposal tool to Agent_Col;
2. accept only a model-selected allowlisted category and bounded value;
3. derive identity, provenance, proposal identity, timestamps, and correction
   state from application-owned context and Firestore;
4. create pending proposals without changing the active profile projection;
5. enforce at most one distinct proposal per persisted user message even when
   ADK executes calls concurrently;
6. make an identical idempotent retry return the original stored proposal;
7. reject a retry that changes the proposal category or value for the same
   logical source message;
8. emit proposal and action receipts only from validated ADK function-response
   events backed by successful persistence;
9. durably record completed proposal receipts on idempotent turn ledgers so a
   later model, process, or turn-completion failure cannot erase evidence of
   the side effect;
10. keep ordinary chat and existing memory-decision behavior compatible;
11. prove that Agent_Col does not call the tool for ordinary conversation,
    temporary instructions, ambiguity, sensitive content, or unsupported
    inferred facts;
12. keep logs and safe HTTP details free of messages, memory values, profiles,
    identifiers, idempotency keys, and provider payloads.

## Non-goals

M7 does not:

- activate a proposal without a later structured user decision;
- parse prose such as "yes" or "remember that" as persistence authority;
- add arbitrary personal facts or arbitrary profile fields;
- store contact, location, credential, health, financial, government,
  demographic, political, religious, sexual, biometric, or similarly
  sensitive information;
- treat a preferred name as verified legal identity;
- infer a broad role from a project, employer, school, URL, profile, history,
  search result, or tool result;
- add synthesis, Search, URL Context, or blueprint-feedback tools;
- add authentication, ownership enforcement, rate limiting, background jobs,
  or public deployment authorization;
- make headerless chat requests retry-safe;
- replace Firestore with ADK session state;
- introduce ADK-native durable memory;
- guarantee that a model will always follow an approved preference perfectly.

## Considered approaches

### Approach A: parse a proposal from Agent_Col's final prose

The model would emit JSON or markup in its answer and FastAPI would parse it.

Decision: rejected. Prose is not a trustworthy action boundary. This approach
weakens typing, makes receipts ambiguous, and cannot distinguish a claimed
write from a completed write.

### Approach B: let the model call a generic profile-write tool

The model would select user ID, profile path, field, and value.

Decision: rejected. It gives the model ownership, authorization, provenance,
and schema authority that belong to the application. It also permits prompt
injection to expand the memory surface.

### Approach C: use ADK `FunctionTool(require_confirmation=True)`

ADK supports confirmation-gated function tools. The current official
[tool-confirmation contract](https://github.com/google/adk-python/blob/main/src/google/adk/tools/function_tool.py)
pauses a run and expects a later confirmation response.

Decision: rejected for M7. The proposal tool creates inactive confirmation
state; it does not activate memory. Requiring confirmation before creating the
confirmation state adds a redundant consent step. More importantly, the
current Agent_Col runtime deletes each in-memory ADK session at the end of the
HTTP turn, while the trusted-memory decision may occur in another session or
after a restart. The existing Firestore proposal plus structured
`memory_decision` is durable, inspectable, and already manually accepted.

M7 therefore uses `FunctionTool(..., require_confirmation=False)`. ADK
confirmation may be reconsidered only for a future side effect whose
authorization must occur before that tool executes and whose resumable session
contract is durably implemented and tested.

### Approach D: rely on the supervisor instruction for one-call restraint

The instruction would tell Agent_Col to call the tool at most once.

Decision: rejected as the enforcement boundary. It remains a required
behavioral instruction and evaluation target, but installed ADK 2.7.0 can run
multiple model-selected function calls concurrently. Prompt adherence cannot
provide atomicity.

### Approach E: FunctionTool plus deterministic guarded service

The model selects only category and value. A standard async `FunctionTool`
reads server-owned context, calls `TrustedMemoryService`, and returns a compact
dict. Firestore transactionally claims the persisted source message as the
origin for at most one proposal.

Decision: selected. This preserves ADK-native tool routing while keeping
identity, provenance, consent, idempotency, and persistence authoritative in
application code.

## Authority model

| Concern | Authoritative component |
| --- | --- |
| Whether a tool might be useful | Agent_Col supervisor |
| LLM-visible category and proposed value | `propose_memory_signal` function declaration |
| Category-value compatibility | `memory_policy.py` and Pydantic validation |
| Preferred-name current-message grounding | `TrustedMemoryService` using server-owned source text |
| User, session, and source-message identity | FastAPI and `SupervisorTurnContext` |
| Proposal and origin IDs | deterministic application helper |
| Current active signal for correction | Firestore transaction |
| At-most-one proposal per source message | Firestore origin-guard transaction |
| Idempotent turn side-effect evidence | Firestore turn ledger |
| Pending proposal persistence | `MemoryEngine` |
| Active-memory authorization | structured user `memory_decision` only |
| Tool result extraction | `SupervisorRuntime` from ADK function-response events |
| Public action/proposal receipts | validated application schemas |
| Final conversational response | Agent_Col supervisor |
| HTTP status and partial-failure body | FastAPI |

Agent_Col may suggest a candidate. It may not decide that the candidate is
true, approved, active, owned by a particular user, or safe to persist outside
the allowlist.

## Public tool contract

### Name and type

```text
propose_memory_signal
```

Type: asynchronous ADK `FunctionTool` wrapping an application-owned callable.

Conceptual Python signature:

```python
async def propose_memory_signal(
    category: MemoryCategory,
    proposed_value: str | list[BroadRole],
    tool_context: ToolContext,
) -> dict[str, object]:
    ...
```

`tool_context` is injected by ADK and excluded from the model declaration.
The tool description must state that it creates a pending, user-reviewable
proposal and never activates memory.

### Model-visible arguments

The model controls exactly two values:

- `category`: one of the ten version-1 `MemoryCategory` values;
- `proposed_value`: a candidate value that must pass the category-specific
  local policy.

The provider declaration is an input-shaping aid. Local validation remains
authoritative because the relationship between category and value is a
cross-field rule and `preferred_name` is bounded free text.

### Server-owned inputs

The tool reads these values from invocation state initialized by
`SupervisorRuntime`:

- `user_id`;
- `session_id`;
- `source_message_id`;
- `source_message_text`.
- whether the public request already contains a structured
  `memory_decision`.

For an idempotent request, the tool also receives a server-owned bounded turn
lease context containing the turn ID and current owner token. Those values are
never exposed in the function declaration, tool result, log, or public
response. A headerless request has no turn lease context.

The model never supplies or overrides them. `project_id` may remain in shared
invocation state but is not consumed by this tool.

The source message text is already the current user input. It remains only in
the invocation-scoped in-memory ADK session and the existing Firestore chat
message; it is not copied into a proposal, origin guard, event, profile, log,
receipt, or error body.

### Successful tool result

The callable returns a JSON-serializable dict:

```json
{
  "status": "pending",
  "action": {
    "action_name": "propose_memory_signal",
    "status": "completed"
  },
  "memory_proposal": {
    "proposal_id": "bounded server-derived identifier",
    "category": "allowlisted category",
    "proposed_value": "validated bounded value",
    "expires_at": "RFC 3339 timestamp"
  }
}
```

The adapter builds this envelope from a validated service result. It never
returns raw Firestore snapshots, source text, user/session/message IDs,
expected signal IDs, stack traces, provider payloads, or internal exception
messages.

### Rejected tool result

A policy-invalid or ungrounded call performs no write and returns a bounded
error envelope to Agent_Col:

```json
{
  "status": "rejected",
  "error_code": "invalid_memory_candidate"
}
```

This is not an HTTP `422`; the public chat request may be valid while the
model-selected tool arguments are not. Agent_Col may correct the call within
the existing LLM-call bound or explain that it cannot propose that memory.
No completed action or proposal receipt is emitted.

Persistence and state conflicts use typed internal outcomes so
`SupervisorRuntime` and FastAPI can preserve the error contract without
exposing private details.

## Proposal eligibility and restraint

Agent_Col may call the tool only when the **current user message** explicitly
states a reusable collaboration preference or allowed light identity detail.
History, active profile data, artifacts, URLs, search results, and other tool
results may not originate a proposal.

Eligible examples include:

- "I prefer concise explanations."
- "Please use practical examples when useful."
- "Ask before using external tools."
- "Call me Avery."
- "I'm a student; please remember that context."

The tool remains only a proposal even when the message says "remember."
Structured approval is still required before activation.

The tool must not be called for:

- ordinary questions, greetings, thanks, or factual statements;
- a one-turn formatting or response instruction such as "keep this answer
  short";
- ambiguous wording that might be temporary or situational;
- a preference inferred only from the user's behavior;
- a role inferred from a project, school assignment, profession-specific
  question, or prior context;
- sensitive or unsupported personal data;
- a value already active and unchanged;
- a matching unexpired pending proposal already shown to the user, except an
  exact retry of the same logical HTTP turn;
- model-authored content, hidden reasoning, or tool output.

When intent is ambiguous, Agent_Col asks one concise question and does not call
the tool. Good tool judgment is evaluated as both correct use and correct
non-use.

## Light identity boundary

M7 preserves the approved identity allowance:

- `preferred_name`: the user's chosen form of address, not verified legal
  identity;
- `broad_roles`: one through three policy enums such as `student`,
  `professional`, or `hobbyist`.

A preferred name must pass the existing normalization rules and occur in the
normalized current source message. A broad role may map the user's explicit
wording to the bounded enum, but it remains inactive until approval.

Exact employer, school, job title, address, email, telephone number, account
identifier, government identifier, credentials, financial information,
health information, protected demographic traits, and other sensitive or
privacy-relevant details remain excluded. Adding another identity field
requires a separately reviewed policy version, retention rule, control path,
and tests.

## Application-service contract

M7 adds one immutable command and one result to `trusted_memory_service.py`:

```python
@dataclass(frozen=True, slots=True)
class ProposeMemorySignalCommand:
    user_id: str
    session_id: str
    source_message_id: str
    source_message_text: str
    memory_decision_present: bool
    category: MemoryCategory
    proposed_value: object
    turn_lease: ProposalTurnLease | None = None


@dataclass(frozen=True, slots=True)
class ProposalTurnLease:
    turn_id: str
    owner_token: str


@dataclass(frozen=True, slots=True)
class TrustedMemoryProposalResult:
    action: AgentActionReceipt
    proposal: MemoryProposalReceipt
```

The broad `object` annotation on the service command is intentional: the
service validates untrusted tool input through the policy before constructing
a domain model. The public result contains no source locator.

`TrustedMemoryService.propose_memory_signal()` must:

1. validate all server-owned identifiers before Firestore access;
2. validate and normalize the category-value pair;
3. reject proposal creation when the same request already carries a structured
   memory decision;
4. enforce preferred-name grounding against `source_message_text`;
5. derive the proposal and origin IDs deterministically;
6. obtain one `observed_at` from its injected clock;
7. call one atomic `MemoryEngine` proposal-origin operation;
8. when a turn lease is present, atomically store the completed action and
   proposal receipt on that owned in-progress turn;
9. build a completed action receipt and pending proposal receipt only from the
   stored result;
10. preserve typed conflict and persistence failures without logging content.

The service does not interpret general natural language, infer preferences,
decide consent, invoke Gemini, inspect ADK events, or map HTTP status codes.

## Deterministic identifiers

### Proposal origin ID

One persisted user message is the durable source boundary. The application
derives:

```text
origin_digest = SHA-256(
  "memory-proposal-origin-v1\0" +
  user_id + "\0" +
  session_id + "\0" +
  source_message_id
)
origin_id = first 32 lowercase hexadecimal characters of origin_digest
```

The 128-bit suffix is deterministic path derivation, not authentication and
not a privacy hash of message content. Raw message text is not included. A
stored origin-ID collision with different source metadata is a conflict and
is never overwritten.

### Proposal ID

The proposal ID is:

```text
{category}--{origin_id}
```

Including the category preserves the existing validated locator contract.
Including user, session, and source-message identity in the digest prevents
the same idempotency key reused in another session from colliding under the
same user's proposal slot.

The application derives both IDs before a Firestore transaction. A Firestore
transaction callback performs no hashing, UUID generation, clock reads,
logging, or other external side effect.

## Firestore proposal-origin guard

M7 adds a non-value-bearing arbitration document:

```text
users/{user_id}/memory_proposal_origins/{origin_id}
```

Version 1 fields:

```json
{
  "schema_version": "1.0",
  "proposal_id": "server-derived proposal identifier",
  "category": "allowlisted category",
  "source_session_id": "server-owned identifier",
  "source_message_id": "server-owned identifier",
  "created_at": "server timestamp"
}
```

It intentionally stores no memory value and no raw chat text. It exists to
arbitrate concurrent model calls and stable retries. Its identifiers remain
private and are excluded from logs and public proposal receipts.

### Atomic creation algorithm

The `MemoryEngine` transaction reads, before any write:

1. the proposal-origin guard;
2. the category proposal slot;
3. the root collaboration profile when a new proposal may be created.
4. the idempotent turn document when a turn lease is present.

The outcomes are:

- **No origin exists:** derive the active category signal from the validated
  root profile, create one pending category proposal with that
  `expected_signal_id`, create the origin guard, and record the turn receipt
  when applicable, all atomically.
- **The candidate equals the active category value:** return a typed
  already-active result and write nothing. A no-op correction must not become
  a pending proposal.
- **Identical origin and proposal exist:** return the stored proposal without
  replacing it. The first persisted expiry wins; a retry does not extend it.
  When an owned idempotent turn lacks the identical receipt, add that receipt
  in the same transaction.
- **Origin exists with another category, value, or proposal identity:** raise a
  typed proposal-origin conflict and write nothing.
- **Origin exists but its referenced proposal is missing or malformed:** raise
  a typed stored-state error and write nothing.
- **Another unexpired proposal occupies the category:** preserve the existing
  category conflict and write nothing.
- **The category slot is resolved or expired and no origin exists:** replace
  it according to the existing pending-proposal contract.

This guard enforces at most one distinct proposal for one persisted source
message even if ADK launches parallel calls or another Cloud Run instance
handles a retry.

### Idempotent turn effect

For an idempotent request, proposal creation also updates the already-owned
turn document:

```text
sessions/{session_id}/turns/{turn_id}
```

The transaction verifies all of the following before writing:

- the turn is `in_progress`;
- its stored `user_id` and `user_message_id` match the proposal source;
- its `lease_owner` equals the server-owned owner token;
- its lease is unexpired at the supplied `observed_at`;
- any existing `propose_memory_signal` action and `memory_proposals` receipt
  are identical to the operation being retried.

It then stores one completed proposal action and one validated proposal
receipt on the turn. A differing pre-existing receipt is a typed turn-effect
conflict. `complete_chat_turn()` must preserve and validate this precompleted
effect rather than overwrite it with a response that omits or changes it.

This atomic write closes the crash window between proposal persistence and
turn-effect evidence. Firestore cannot contain a new proposal for an
idempotent turn without the same transaction also recording its public
receipt. Headerless chat has no durable turn ledger and retains its explicit
non-retry-safe guarantee.

When an expired lease or changed owner is detected, the transaction writes
nothing and raises the existing typed ownership boundary. A stale worker
cannot create a proposal after another request owns the turn.

The existing proposal comparison must treat an identical deterministic
proposal ID, category, normalized value, expected signal ID, policy version,
and source locators as the same logical proposal. A retry-generated local
clock value must not extend or conflict with the stored expiry.

### Lifecycle cleanup

When a proposal becomes an active signal, its deterministic origin ID can be
parsed from the validated `{category}--{origin_id}` signal ID. Hard deletion
of that signal must delete its origin guard in the same bounded transaction as
the proposal and lifecycle artifacts. No collection query is required.

Rejected and expired proposal-origin guards contain no user value but still
require an explicit retention/cleanup policy before public deployment. M7
does not silently add Firestore TTL configuration. Removing a guard too early
would permit a stale incomplete turn to recreate a proposal, so cleanup must
be designed together with turn-ledger retention.

## ADK runtime and receipt contract

`SupervisorTurnContext` gains server-owned:

```python
source_message_id: str
turn_lease: ProposalTurnLease | None
precompleted_actions: tuple[AgentActionReceipt, ...]
precompleted_memory_proposals: tuple[MemoryProposalReceipt, ...]
```

The current `message` is reused as `source_message_text`; it is not duplicated
in the public request or model input. `SupervisorRuntime` places both source
fields in the fresh invocation session state before running Agent_Col.

For a resumed idempotent claim, the database validates and returns any
precompleted turn effects. FastAPI supplies them to the runtime and renders a
small application-owned operational context telling Agent_Col that the
proposal was already created and must not be recreated. If the referenced
proposal is no longer pending, the retry conflicts rather than asking the
user to approve stale state. A completed turn still takes the existing replay
path and never invokes ADK.

`SupervisorRuntime` inspects each ADK event's public
`get_function_responses()` result. For the exact
`propose_memory_signal` function name, it:

1. validates the response envelope with local Pydantic schemas;
2. records a completed action and proposal receipt only for `status=pending`;
3. deduplicates an identical repeated response by proposal ID;
4. treats two distinct successful proposal receipts in one invocation as an
   internal contract violation;
5. translates typed persistence or stored-state failures without returning
   tool internals;
6. ignores Agent_Col prose as receipt evidence.

Precompleted receipts are included in the result before new ADK events are
processed. A repeated identical tool response deduplicates against them. A
different response conflicts.

The runtime result becomes conceptually:

```python
@dataclass(frozen=True)
class SupervisorTurnResult:
    response: str
    actions: tuple[AgentActionReceipt, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    citations: tuple[CitationReference, ...] = ()
    memory_proposals: tuple[MemoryProposalReceipt, ...] = ()
```

The list bound is one. A model sentence such as "I will remember that" never
creates a receipt.

## Supervisor instruction amendment

The Agent_Col instruction must retain the existing default-to-no-tool rule and
add these exact behavioral requirements in substance:

1. propose memory only from an explicit reusable preference or allowed light
   identity detail in the current user message;
2. do not infer a preference or identity detail from behavior or context;
3. do not propose sensitive or unsupported personal information;
4. do not use the tool for a temporary one-turn instruction;
5. do not propose a second memory signal in a turn that already carries a
   structured approval or rejection decision;
6. when intent is ambiguous, ask one concise question without calling the
   tool;
7. make at most one proposal tool call per user turn;
8. after a successful receipt, state that the proposal is pending and ask the
   user to approve or reject it;
9. never claim the proposal is active until the application supplies a
   completed approval receipt;
10. do not call the tool when no tool is needed.

These instructions guide behavior. The application schemas, transactional
origin guard, structured decision, and receipt extraction remain the
enforcement boundaries.

## Public response contract

M7 activates the previously designed response field:

```python
class ChatResponse(StrictModel):
    response: NonEmptyStr
    actions: list[AgentActionReceipt] = Field(default_factory=list)
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    citations: list[CitationReference] = Field(default_factory=list)
    memory_proposals: list[MemoryProposalReceipt] = Field(
        default_factory=list,
        max_length=1,
    )
    adaptations: list[AdaptationReceipt] = Field(
        default_factory=list,
        max_length=10,
    )
```

`AgentActionReceipt.action_name` adds `propose_memory_signal`.

For idempotent chat turns, the proposal transaction persists
`memory_proposals` immediately with its completed action. Later,
`complete_chat_turn()` verifies that the final response contains the same
precompleted effect and persists the remaining response receipts. Replay
validates and returns the original proposal receipt without invoking ADK or
Firestore proposal creation again.

Headerless requests retain their current non-retry-safe transport behavior,
but one execution still receives a persisted source message ID and the
transactional origin guard still prevents multiple proposals within that
execution.

## Partial-failure contract

A proposal write can complete before Agent_Col produces its final response or
before an idempotent turn completes. The application must not hide that
side effect and must not claim rollback.

M7 adds:

```python
class ChatPartialFailureResponse(StrictModel):
    detail: Literal[
        "Agent_Col response failed after a completed action.",
        "Agent_Col response timed out after a completed action.",
    ]
    actions: list[AgentActionReceipt]
    memory_proposals: list[MemoryProposalReceipt] = Field(
        default_factory=list,
        max_length=1,
    )
```

Rules:

- no completed side effect: preserve the existing content-free `502` or `504`;
- proposal completed, final response/provider failed: return `502` plus the
  validated action and proposal receipt;
- proposal completed, whole-turn deadline expired: return `504` plus the
  validated action and proposal receipt;
- release an idempotent turn lease after retryable provider/runtime failure;
- retain the precompleted turn effect while releasing only its lease;
- retrying with the same idempotency key and same tool result returns the
  stored proposal and does not extend expiry;
- retrying with a changed category or value conflicts rather than mutating the
  original side effect;
- a Firestore proposal write failure returns `500` with no completed receipt;
- a stored proposal/origin conflict returns `409` with a safe detail;
- invalid model-selected candidate data creates no receipt and is not exposed
  as a user request-validation error.

Typed persistence, turn-ownership, and origin/category conflicts propagate
out of the tool call so `SupervisorRuntime` can preserve their class and cause
when mapping `500`, `409`, or existing turn-ownership errors. Only expected
policy rejection is returned to the model as a recoverable function response.

The partial response never includes source message text, internal ADK event
data, exception messages, hidden prompts, or provider payloads.

## Error mapping

| Condition | Public result |
| --- | --- |
| Invalid public chat request or idempotency key | existing `422` |
| Model selects invalid or ungrounded candidate, then recovers | normal chat response, no proposal receipt for failed call |
| Model cannot recover from invalid tool interaction | `502` |
| Proposal origin or category slot conflicts | `409` |
| Firestore proposal operation fails | `500` |
| Provider/runtime failure before a side effect | existing `502` |
| Whole-turn timeout before a side effect | existing `504` |
| Provider/runtime failure after proposal persistence | typed partial `502` |
| Whole-turn timeout after proposal persistence | typed partial `504` |
| Completed idempotent turn retried identically | replayed `200`, no provider or tool call |

All details are content-free and identifier-free.

## Security, privacy, and logging

- Tool arguments cannot select a user, session, source message, proposal ID,
  expected signal ID, timestamp, policy version, confirmation channel, or
  active status.
- The model cannot call approval, rejection, revocation, or deletion tools.
- A prompt injection cannot add a category or bypass local value validation.
- Raw source text is stored only in the existing chat message and temporary
  invocation context.
- Proposal and origin documents do not copy raw chat text.
- The origin guard stores no memory value.
- Pending proposals are not injected into unrelated turns as active context.
- Rejected or expired values do not become lifecycle events.
- Preferred names and broad roles remain user-supplied context, not verified
  identity.
- Logs exclude raw messages, values, profile data, project/user/session/message
  identifiers, proposal/origin/signal/event IDs, idempotency keys, tool
  arguments, tool responses, and provider errors.
- Safe logs may contain only operation labels and exception class names.
- Public deployment remains blocked until authenticated identity and ownership
  checks replace request-provided `user_id`.

## TDD and evaluation contract

M7 implementation must proceed in smaller approved passes. Every production
behavior begins with a focused RED test.

### M7.2 — proposal persistence and service boundary

Initial RED targets:

- deterministic origin and proposal IDs are stable and domain separated;
- model-controlled data cannot set provenance or identity;
- preferred-name proposal fails when not grounded in the current message;
- a turn already containing a structured memory decision rejects proposal
  creation before Firestore access;
- transaction reads origin, category slot, and profile before writes;
- active signal ID is derived transactionally as `expected_signal_id`;
- proposing the already-active value writes nothing;
- concurrent distinct calls for one source produce one proposal and one
  conflict;
- idempotent proposal persistence atomically records the identical turn action
  and proposal receipt;
- an expired or changed turn owner cannot persist a proposal;
- an existing differing turn receipt conflicts without mutation;
- identical retry returns the stored proposal and original expiry;
- changed retry value or category conflicts without mutation;
- hard deletion removes the signal's origin guard;
- Firestore and validation failures log no identifiers or values.

Expected source surfaces:

- `trusted_memory_service.py`;
- `database.py`;
- `schemas.py` or a small pure identifier module;
- focused memory database/service tests.

### M7.3 — ADK tool adapter and supervisor event collection

Initial RED targets:

- the function declaration exposes only category and proposed value;
- ADK injects `ToolContext`; server-owned fields are absent from the function
  declaration;
- the tool is async and returns the strict success envelope;
- invalid candidate calls write nothing and emit no receipt;
- supervisor application registers exactly the governed proposal tool;
- ordinary supervisor instruction retains default-to-no-tool restraint;
- runtime extracts receipts from function-response events, not prose;
- duplicate identical responses deduplicate to one receipt;
- multiple distinct successes cause a typed contract failure;
- invocation sessions are still deleted safely.

Expected source surfaces:

- a focused memory proposal tool adapter module;
- `supervisor.py`;
- `supervisor_runtime.py`;
- focused tool and runtime tests.

### M7.4 — FastAPI, idempotency replay, and partial failure

Initial RED targets:

- current source message ID reaches `SupervisorTurnContext` on headerless and
  idempotent paths;
- resumed idempotent claims recover precompleted proposal receipts before ADK
  invocation;
- successful chat returns one action and one proposal receipt;
- no-tool chat response remains unchanged except for an empty default field;
- completed turn persistence and replay preserve the proposal receipt;
- proposal persistence and idempotent turn-effect persistence are atomic;
- same idempotency key does not re-invoke the provider or tool after success;
- partial `502` and `504` expose only completed receipts;
- no-side-effect failures keep the current safe error bodies;
- persistence conflict and database failure map to `409` and `500`;
- legacy memory-decision approval, rejection, adaptation, and headerless chat
  regressions remain green.

M7.4 also records a completed structured memory-decision action on an
idempotent in-progress turn before invoking ADK. The approval/rejection
operation remains independently idempotent, so a process crash before that
turn-effect write is recovered by repeating the same decision with the same
deterministic confirmation message ID. This closes the already-designed
partial-failure receipt boundary without coupling the memory-decision
transaction to the proposal tool.

Expected source surfaces:

- `main.py`;
- `schemas.py`;
- `database.py` turn completion/replay;
- focused main and idempotency tests.

### M7.5 — restraint evaluations and live acceptance

Offline deterministic cases must assert the expected routing decision for:

- explicit reusable preference -> propose;
- explicit preferred name -> propose;
- explicit broad role with memory intent -> propose;
- temporary one-turn formatting request -> no proposal;
- ordinary explanation -> no tool;
- ambiguous possible preference -> ask, no proposal;
- sensitive personal data -> no proposal;
- inferred role from a software or academic task -> no proposal;
- already-active identical preference -> no proposal;
- prompt injection requesting arbitrary profile write -> no proposal;
- two candidate preferences in one message -> ask which one to remember or
  select no tool, never create two proposals.
- a structured approval/rejection turn -> no new proposal tool call.

Live acceptance must use a fresh test user and inspect Firestore:

1. explicit preference creates one pending proposal and one origin guard;
2. profile revision and active maps remain unchanged;
3. exact idempotent replay returns byte-equivalent typed receipts without a
   second model/tool invocation;
4. a new session approves the proposal through structured
   `memory_decision`;
5. another new session returns an adaptation receipt and visibly follows the
   preference;
6. ordinary chat creates no proposal;
7. revocation stops future adaptation;
8. hard deletion removes proposal, origin, signal, and owned lifecycle
   artifacts while preserving unrelated chat history.

Provider behavior is probabilistic, so a single live run does not prove tool
restraint. M7.5 must define a small repeated evaluation set and report each
provider error separately from a genuine routing or quality failure.

## Compatibility and preserved invariants

M7 must preserve:

- `POST /api/chat` request fields and the optional idempotency header;
- headerless chat behavior for existing clients;
- one current user message in model context;
- bounded chronological Firestore history;
- Firestore as the only durable collaboration-memory source;
- existing M6 approval, correction, rejection, adaptation, revocation,
  deletion, inspection, and replay semantics;
- existing synthesis contracts;
- one final Agent_Col response when the turn succeeds;
- content-free safe errors and logs;
- direct pushes to the owner-controlled repository only after explicit manual
  acceptance; no pull request is required.

Adding the empty `memory_proposals` response field is an intentional additive
API change. Existing typed consumers must tolerate the field before the
future UI is built.

## Known limitations

- The model performs semantic classification of explicit preference wording;
  deterministic code constrains and confirms the result but does not fully
  understand natural language.
- User approval protects against a bad proposal but does not make the original
  model classification infallible.
- Headerless requests remain non-idempotent across separate HTTP attempts.
- A proposal receipt proves persistence, not activation.
- An adaptation receipt proves that approved context was provided to the
  model, not perfect behavioral compliance.
- Origin-guard retention and turn-ledger retention require a later bounded
  policy before public deployment.
- Request-provided user identity remains local-development-only.
- Version 1 remains limited to eight collaboration preferences, a preferred
  name, and bounded broad roles.
- M7 does not yet connect synthesis, Search, or URL Context to the supervisor.

## Stop conditions

Implementation must stop for design revision if:

- installed ADK cannot expose only the two approved model arguments;
- function-response events cannot be validated without private ADK internals;
- a successful tool result cannot be preserved when the later run fails;
- multiple concurrent calls can create more than one proposal for one source
  message;
- retrying can extend proposal expiry or change the stored value silently;
- current-message grounding requires model-supplied source text;
- an active signal can be derived without reading authoritative Firestore
  state;
- partial failures would hide a completed side effect;
- any path activates memory without structured user authorization;
- hard deletion cannot remove the origin guard and every value-bearing
  artifact owned by the signal;
- logs or errors would expose content, memory values, identity, provenance, or
  provider payloads;
- public deployment would trust request-provided ownership.

## Final M7.1 verdict

The governed proposal tool is implementation-feasible with the pinned ADK
version, but the original prompt-only one-call rule is insufficient. The
approved implementation direction should be:

> Standard async ADK FunctionTool for model selection, deterministic
> TrustedMemoryService for policy and receipts, and a transactional Firestore
> source-message guard for concurrency and retry safety.

This preserves Agent_Col's judgment while ensuring the model never owns
consent, identity, provenance, active memory, or proof of persistence.
