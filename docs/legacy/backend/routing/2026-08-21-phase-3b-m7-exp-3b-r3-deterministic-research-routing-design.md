# M7-EXP.3B-R3 Deterministic Research Routing Design

**Status:** Superseded by repository-owner decision on 2026-08-21
**Pass type:** Architecture and provider-capability investigation only
**Evidence date:** 2026-08-21

## Superseding decision

This deterministic-routing proposal must not be implemented.

Agent_Col remains responsible for deciding whether ordinary Research is
materially useful. No keyword router, JSON routing policy, SQLite routing
database, or forced-Search compatibility spike will be introduced.

The accepted operating principle is:

> Agent_Col decides whether research is useful. Deterministic application
> code decides whether the returned evidence is trustworthy.

Ordinary Research closes with the documented provider limitation that current
Gemini Google Search execution is model-managed and is therefore not
guaranteed for every delegated request. The application must continue to
reject ungrounded output rather than claim that research succeeded.

Development proceeds through the remaining approved M7.2 experts in this
order:

1. Source Expert;
2. Computational Expert;
3. Requirements Verification;
4. cross-expert judgment and restraint evaluation;
5. Deep Research integration design.

The remainder of this document is retained as historical investigation and
must not be treated as an active implementation contract.

## 1. Decision summary

Agent_Col should add a deterministic routing policy in front of the model for
high-confidence research and restraint cases. The policy can guarantee that a
request enters, avoids, or clarifies the research path. It cannot, by itself,
guarantee that Gemini executes its built-in Google Search tool.

The current Google Search tool remains model-managed. Google's documentation
states that Gemini analyzes the prompt and searches only "if needed." The
provider behavior observed during M7-EXP.3B-R2 is therefore consistent with
the documented contract: even after Agent_Col delegates to the Research
Expert, the inner model can return text without executing Search.

The recommended target architecture is:

1. a deterministic, version-controlled routing policy for unambiguous cases;
2. one application-owned Research Service for every actual research attempt;
3. a forced Google Search provider call only if a focused compatibility spike
   proves that the current Interactions API can force the built-in
   `google_search` tool;
4. strict evidence validation before research reaches Agent_Col;
5. Agent_Col as the only component that produces the final conversational
   response.

The current evidence is insufficient to claim item 3 is supported. The
Interactions API exposes generic `tool_choice` configuration, including
`any`, but the official forced-tool examples demonstrate custom functions,
not the built-in Google Search tool. This must be tested before production
design depends on it.

## 2. Verified provider facts

### 2.1 Current Google Search is model-managed

With the current `google_search` built-in tool, Gemini decides whether Search
would improve the answer and executes one or more queries only if it considers
them necessary. Built-in tool execution occurs inside the provider request.

Consequences:

- adding `google_search` to a model does not guarantee a Search call;
- prompting the model to search does not create a deterministic guarantee;
- wrapping the model in an ADK specialist does not change that provider
  behavior;
- the application must reject an ungrounded result rather than mislabel it as
  researched.

Evidence:

- [Gemini Google Search workflow](https://ai.google.dev/gemini-api/docs/google-search)
- [Gemini built-in tool flow](https://ai.google.dev/gemini-api/docs/tools)

### 2.2 Legacy forced retrieval is not a supported Gemini 3.6 solution

The API schema still describes the older `google_search_retrieval` tool and a
dynamic-retrieval mode whose unspecified mode always triggers retrieval.
However, the current Google Search guide explicitly directs all current models
to use `google_search`; `google_search_retrieval` is for older models.

Agent_Col must not use a legacy field with Gemini 3.6 merely because its type
still exists in the SDK.

Evidence:

- [Current model and tool guidance](https://ai.google.dev/gemini-api/docs/google-search)
- [GenerateContent tool schema](https://ai.google.dev/api/generate-content)

### 2.3 `generateGroundedContent` is not a viable replacement

An Agent Search documentation page still contains examples for
`generateGroundedContent`, including an always-grounded configuration. The
current Agent Search release notes are authoritative for lifecycle status and
state that this API is no longer available. They direct applications to the
GA `generateContent` API instead.

Agent_Col must not adopt `generateGroundedContent`.

Evidence:

- [Agent Search release notes](https://cloud.google.com/generative-ai-app-builder/docs/release-notes)

### 2.4 Interactions API is the only credible first-party forcing candidate

The current Interactions API supports Gemini 3.6 Flash, `google_search`,
observable Search call/result steps, URL citations, and generic tool-choice
configuration. The tool-choice contract contains an `any` mode and a bounded
allowed-tools list.

What is not yet proven is whether `any` plus only `google_search` forces the
built-in Search tool. Google's forced-tool examples apply to custom function
calling. The Google Search guide still describes Search as model-decided.

Therefore:

- Interactions API is a valid candidate for a focused live spike;
- forced Google Search through it is not yet an approved assumption;
- migration from the ADK Research Expert must not begin before the spike.

Evidence:

- [Interactions API reference](https://ai.google.dev/api/interactions-api-v1)
- [Interactions function-calling modes](https://ai.google.dev/gemini-api/docs/function-calling)
- [Interactions Google Search response steps](https://ai.google.dev/gemini-api/docs/google-search)

## 3. SQLite decision

### Decision: do not use SQLite for research routing

A local SQLite database does not solve the hard problem. It can make routing
lookup deterministic, but a simple immutable rules document can do the same
without database schema, migrations, connection management, or query logic.

SQLite is also the wrong persistence assumption for Cloud Run. A Cloud Run
container has a writable in-memory filesystem, and data written there does not
persist when an instance stops. Multiple instances would also have independent
local copies. A mutable SQLite routing database would therefore diverge or
disappear.

A read-only SQLite file bundled in the container image would be stable, but it
would still require a deployment to change and offers no benefit over a small,
version-controlled JSON policy.

Use a strictly validated, version-controlled policy document instead. This is
more reviewable for judges, easier to test, and easier to reproduce.

Evidence:

- [Cloud Run container filesystem contract](https://cloud.google.com/run/docs/container-contract)

## 4. Deterministic routing policy

### 4.1 Policy result

The policy returns exactly one typed route:

```text
RESEARCH_REQUIRED
RESEARCH_PROHIBITED
SOURCE_REQUIRED
CLARIFICATION_REQUIRED
MODEL_DECIDES
```

The result also contains a versioned server reason code. It must not include
raw user content in logs.

### 4.2 Precedence

Rules execute in this order:

1. **Explicit prohibition** — phrases such as "do not search," "do not browse,"
   or "use only the information I supplied" return
   `RESEARCH_PROHIBITED`.
2. **Supplied-source boundary** — a request to analyze only one or more
   supplied public URLs returns `SOURCE_REQUIRED`, not broad research.
3. **Incomplete research request** — an explicit research request without a
   concrete subject returns `CLARIFICATION_REQUIRED`.
4. **Explicit research request** — a concrete request to search, research,
   browse, look up, verify with current sources, or cite current evidence
   returns `RESEARCH_REQUIRED`.
5. **High-confidence currentness requirement** — a bounded combination of a
   temporal qualifier and a concrete factual subject can return
   `RESEARCH_REQUIRED`.
6. **No deterministic match** — return `MODEL_DECIDES`.

Negative rules always outrank positive research rules. A single keyword such
as `current`, `latest`, `research`, or `source` must never force a route by
itself.

### 4.3 Policy representation

The recommended policy artifact is a small JSON document validated at startup
with a strict Pydantic schema. Each rule contains:

```text
rule_id
priority
route
required_phrase_groups
excluded_phrase_groups
reason_code
```

Application code owns normalization and evaluation order. The policy document
contains no executable expressions, SQL, or model-authored content.

### 4.4 What the policy does not do

The policy does not:

- decide whether a claim is true;
- generate a search query;
- select sources;
- persist user data;
- bypass Agent_Col;
- turn every mention of a recent concept into a research call;
- guarantee provider Search execution.

## 5. Target routing architecture

```text
User
  |
  v
FastAPI Chat Turn + Idempotency Claim
  |
  v
Deterministic Research Policy
  |
  +-- RESEARCH_PROHIBITED ------> Agent_Col without Research capability
  |
  +-- SOURCE_REQUIRED ----------> Source Expert boundary (later M7 pass)
  |
  +-- CLARIFICATION_REQUIRED ---> Agent_Col with a server-owned route hint
  |
  +-- RESEARCH_REQUIRED --------> Research Service
  |                                  |
  |                                  v
  |                         forced Search candidate
  |                         (only after compatibility proof)
  |                                  |
  |                                  v
  |                         validated ResearchExpertResult
  |                                  |
  +<---------------------------------+
  |                                  |
  v                                  |
Agent_Col <--------------------------+
  |
  +-- integrates evidence with memory and conversation context
  +-- chooses wording, explanation depth, and follow-up question
  +-- does not invent or replace provider citations
  |
  v
ChatResponse + server-derived action/citation receipts
```

For `MODEL_DECIDES`, Agent_Col may answer directly, ask a question, or request
the same Research Service through one bounded model-visible function. The
function is an application capability, not a second conversational agent.

## 6. Agent_Col ownership and evidence handoff

The original user message remains the conversational input to Agent_Col. The
Research Service returns only a validated, bounded evidence object:

```text
question
findings[]
  claim
  evidence_summary
  source_ids[]
  confidence
  uncertainty
sources[]
  source_id
  uri
  label
unresolved_questions[]
execution_evidence
  provider
  search_call_count
  grounded_finding_count
```

The object is injected as untrusted operational context. Agent_Col is told to
answer the user's original request using only the supported findings for
externally verifiable claims. It may explain, compare, personalize, and ask a
follow-up question, but it may not add unsupported current facts.

The application, not Agent_Col, derives:

- the `google_search` action receipt;
- citation URLs and labels;
- provider failure status;
- delegation count;
- idempotent replay behavior.

This preserves Agent_Col's conversational accountability without granting the
model authority over evidence receipts.

## 7. Delegation, timeout, and idempotency rules

- Research remains depth 1.
- A pre-routed Research Service call counts as one specialist delegation.
- Agent_Col may not request Research again after pre-routed research completed.
- A model-requested Research call uses the same Research Service and consumes
  the same delegation budget.
- Experts may not call other experts.
- The whole turn retains the maximum of two specialist delegations established
  by M7.2.
- Research receives a bounded provider timeout and must leave time for
  Agent_Col to integrate the result.
- The idempotency claim must occur before Research executes.
- A completed idempotent replay returns the stored ChatResponse without
  repeating Search or Agent_Col generation.
- Provider timeouts, missing Search steps, missing citations, invalid URLs, or
  unsupported claim mappings fail closed.

For an explicit research request, a failed Research Service must not silently
fall back to an ungrounded answer. The current safe HTTP behavior remains a
provider failure response until a separate graceful-degradation contract is
designed and approved.

## 8. Options rejected in this pass

### Keep only the current ADK Research Expert and retry again

Rejected as the reliability solution. It is supported and bounded, but the
provider still decides whether to execute Search. A third retry would spend
more quota without creating a guarantee.

### Deterministic router plus current ADK Research Expert

Useful for routing restraint but insufficient as a full correction. It forces
delegation, not Search execution.

### Legacy `google_search_retrieval`

Rejected for Gemini 3.6. Current documentation directs current models to
`google_search`.

### Agent Search `generateGroundedContent`

Rejected because current release notes state that the API is no longer
available.

### Custom Search JSON API

Rejected as a new Agent_Col dependency. Google's current documentation says it
is unavailable to new customers and existing customers must transition before
its January 1, 2027 discontinuation.

Evidence:

- [Custom Search JSON API overview](https://developers.google.com/custom-search/v1/overview)

### Third-party search provider

Not inherently invalid, but excluded from this Google-first hackathon pass. It
would add a new credential, dependency, cost model, terms boundary, and source
normalization surface. It should be considered only if the first-party forced
Search spike fails and the user explicitly approves the scope change.

## 9. Acceptance criteria for a future implementation

A production implementation may proceed only if all of these are true:

1. Explicit no-search requests cannot reach Research.
2. Supplied-URL-only requests cannot be broadened into web research.
3. Concrete explicit research requests deterministically enter Research.
4. Ambiguous research requests produce one useful clarification.
5. Stable explanations remain direct.
6. Every successful Research result contains a provider Search call, grounded
   findings, and valid public citations.
7. Agent_Col produces the final response and receives the original prompt plus
   validated evidence.
8. Server-derived receipts match the evidence actually used.
9. An idempotent replay performs no second Search call.
10. Routing policy changes are versioned, tested, and reproducible.
11. No local mutable database is introduced.
12. Provider noncompliance fails closed and is classified separately from a
    routing failure.

## 10. Superseded next-pass proposal — do not execute

### M7-EXP.3B-R3.1 — Forced Google Search compatibility spike

This experiment was proposed before the superseding decision above and is
cancelled. It is retained only to preserve the design history.

Use the installed Google Gen AI SDK, Vertex AI ADC, Gemini 3.6 Flash, and the
Interactions API with:

- `store=false`;
- only the `google_search` tool;
- `tool_choice`/allowed tools configured to `any` and `google_search`;
- a small fixed set of current-fact prompts;
- repeated calls sufficient to expose nondeterminism;
- inspection of Search call steps, Search result steps, model annotations, and
  citations.

The spike passes only if every valid call demonstrably executes Google Search
and returns usable citation annotations. An invalid-argument response, ignored
tool choice, missing Search step, or ungrounded successful response disproves
the candidate.

If the spike passes, the next design pass can specify replacement of the ADK
Research sub-agent with an application Research Service plus deterministic
routing. If it fails, Agent_Col must either retain honest probabilistic Search
with fail-closed validation or explicitly adopt another search provider; no
additional prompt/retry patch should be proposed as a guarantee.
