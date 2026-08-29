# M7-EXP.7C Core Tool-Belt Evaluation Closure

## Status and scope

Accepted implementation evidence consolidated on August 23, 2026. This is a
documentation-only closure. It changes no production code, tests, fixtures,
prompts, schemas, dependencies, APIs, persistence behavior, or infrastructure.

This document closes the bounded M7 core-expert evaluation sequence. It does
not claim universal routing accuracy, production readiness, or completion of
the judge-facing Agent_Col product.

## Executive conclusion

Agent_Col's four core cognitive experts are integrated behind one production
routing and response boundary:

- Research uses Google Search for current or externally verifiable public
  evidence;
- Source uses URL Context for user-supplied public URLs;
- Computation uses provider code execution with server-projected numerical
  inputs and execution evidence;
- Requirements Verification uses structured model reasoning followed by
  deterministic local validation.

The accepted production contract is stricter than the original M7.2 ceiling:
each turn executes zero or one cognitive expert, delegation depth is one, and
experts cannot call other experts. Agent_Col remains the only user-facing
responder. Its responder instance receives validated results and authoritative
application-derived receipts but no model-visible cognitive expert tools.

The complete layered evaluation passed after two evidence-backed corrections:
the live evaluator was corrected to trust public citation receipts instead of
requiring raw URLs in model prose, and the routing provider was hardened to
keep numerical provenance out of free-text computation fields. Neither change
forced a route, weakened local validation, added hidden retries, or expanded
expert authority.

## Implemented production boundary

```text
Validated ChatRequest
        |
        v
Deterministic URL, numeric, and text-block projection
        |
        v
Vertex structured routing decision
        |
        v
Strict local directive validation
        |
        +---- direct / clarify -------------------+
        |                                         |
        +---- exactly one selected expert ----+   |
        |                                     |   |
        |     deterministic expert executor   |   |
        |     validated result and receipts   |   |
        |                                     |   |
        +<------------------------------------+   |
                                                  v
                                     Responder-only Agent_Col
                                                  |
                                                  v
                                One ChatResponse and durable turn
```

Deterministic application code remains authoritative for projection,
validation, capability availability, expert execution, deadlines, action and
citation receipts, persistence, and idempotency. The routing and responding
models may reason over bounded data but cannot create authoritative receipts,
select unissued candidate identifiers, mutate Firestore directly, or authorize
another expert.

The responder may call only the existing governed memory-proposal tool. That
tool can persist one pending allowlisted proposal from an eligible statement
in the current user message. A proposal remains inactive until a later
structured user decision authorizes approval.

## Evaluation layers and accepted evidence

| Layer | What it proves | Accepted checkpoint |
| --- | --- | --- |
| Versioned scenarios and pure evaluators | Fixed route expectations, candidate provenance, finding taxonomy, and fixture integrity | `0d6010018aa9a169462bba749ea71e0186b562c7` |
| Decision-only live evaluation | Production routing-v3 provider decisions without expert execution, response generation, or Firestore access | `2910b259f3fb16a4121159065a1c337fbd030cae` |
| Deterministic orchestration evaluation | Six-route orchestration, controlled expert results, receipts, failures, timeouts, trust boundaries, replay, and conflicts | `b6965b22441c374985151ab7899a966e96722138` |
| Bounded live HTTP evaluation | Production FastAPI, Vertex routing, four live expert paths, Agent_Col response integration, replay, and conflict behavior | `69341cf6b662d508d1042b8a2b83cdb40699f2ca` plus accepted corrections below |
| Citation-receipt correction | Source and Research evaluation uses authoritative `ChatResponse.citations` receipts | `baeb51d77e6ed81a5776c79ba5eb46d96f6e6e36` |
| Numeric-provenance hardening | The exact series-and-precision request routes through Computation without moving numbers into free text | `7b724f7781a86f56ee5fcd0cdb8a598cab15f426` |

### Final decision-only evidence

The repository owner ran the exact computation regression scenario in declared
mode:

```bash
python3 tool_belt_routing_check.py --scenario computation-series-precision --mode declared
```

Accepted result:

- three planned provider calls;
- three `expected=computation actual=computation pass` results;
- no manual-review attempts;
- exit `0`.

This proves the corrected routing provider selected the server-issued six-item
series and separate precision candidate consistently in that bounded sample.
It does not prove that every future paraphrase will route identically.

### Final live HTTP evidence

The repository owner ran:

```bash
python3 tool_belt_live_e2e_check.py --run-id m7exp7b4-review-01
```

The accepted run made exactly eight HTTP requests and reported:

- Direct restraint: HTTP 200, pass;
- Clarification: HTTP 200, pass;
- Source: HTTP 200, completed `url_context` receipt and citation, pass;
- Research: HTTP 200, completed `google_search` receipt and citations, pass;
- Computation: HTTP 200, completed `run_computation` receipt and locally known
  results `19.5000` and `5.1235`, pass;
- Requirements Verification: HTTP 200, completed verification receipt, pass;
- exact Source replay: HTTP 200 with the stored response, pass;
- changed request using the Source idempotency key: HTTP 409, pass.

The HTTP 409 is required success evidence. It proves the existing key cannot
be reused for a different logical request. The aggregate result contained zero
automatable failures, zero inconclusive failures, six qualitative review
cases, and exit `0`.

Manual Firestore inspection also confirmed the accepted run's bounded durable
state. The live report deliberately does not claim that provider-call counts
are observable at the public HTTP boundary.

### Closure verification

The documentation closure was checked against the accepted source revision
with:

```bash
python3 tool_belt_orchestration_check.py
pytest -q
git diff --check
```

The deterministic runner passed all 14 route, failure, trust, replay, and
conflict probes with zero provider, network, or Firestore calls. The complete
offline suite passed 1,670 tests. The suite retained one upstream ADK
`BaseAgentConfig` deprecation warning, which is recorded below rather than
silently treated as clean output.

## Qualitative findings

The accepted live responses demonstrated:

- direct answers did not fabricate expert actions or citations;
- missing numerical inputs produced a clarification rather than a guessed
  calculation;
- Source used the supplied URL and returned an application-derived citation;
- Research returned current evidence with an authoritative `python.org`
  source;
- Computation used the supplied values and reported the requested precision;
- Requirements Verification distinguished covered and missing requirements
  and did not claim certification;
- expert turns did not create memory proposals or adaptation receipts;
- completed replay did not repeat downstream work;
- a conflicting retry failed explicitly rather than returning unrelated state.

The Research response also included a secondary Wikipedia citation in addition
to official Python evidence. That is not a contract failure because the
authoritative source was present and the receipts were valid, but minimizing
secondary sources when primary evidence is available remains a response-quality
target.

## Corrections and what they revealed

### Public citation receipt evaluation

The first live evaluator treated a valid Source response as a citation
mismatch because it required the raw citation URI to appear inside model prose.
That was an evaluator defect. `ChatResponse.citations` is assembled from
validated provider evidence and is the public authoritative receipt; model
prose is not. R3A corrected the evaluator without relaxing Source or Research
evidence requirements.

### Computation routing provenance

The first live computation attempt failed before expert execution because the
routing provider placed numeric-like content in free-text computation fields.
The local validator correctly rejected it. R3B preserved the validator and
strengthened the provider instruction and provider-safe schema descriptions so
operands and precision remain represented only by server-issued candidate
identifiers.

## Known limitations and warnings

- Live model behavior remains probabilistic. These bounded samples do not
  establish universal semantic routing accuracy.
- No hidden retry converts a provider failure into a semantic pass. Provider
  errors remain separately classified.
- Direct use of automatic function calling through
  `AsyncModels.generate_content` emits an upstream recommendation to use the
  chat API. The accepted evaluation remains functional, but the warning should
  be revisited during dependency maintenance.
- ADK currently emits an experimental JSON-schema-for-function-declarations
  warning for the governed memory tool.
- ADK exposes a `BaseAgentConfig` deprecation warning through the installed
  version. Agent_Col does not depend on that class directly.
- Local macOS live runs may emit gRPC fork diagnostics while ADK and provider
  clients are active. They did not change the accepted HTTP results.
- Vertex grounding citations may be returned as Google redirect URLs rather
  than canonical publisher URLs. The application preserves the validated
  receipt and publisher label.
- The public HTTP response proves observable actions, citations, content, and
  idempotency behavior. It does not expose hidden provider-call counts or raw
  expert events.
- The current API remains local-development-only. Request-provided user,
  session, and project identifiers are not authentication or authorization.

## M7 closure decision

The four-expert core tool belt has passed its accepted architecture gate. No
additional routing heuristic, keyword database, fallback router, nested expert,
or second-decision model is justified by this evidence.

Deep Research is now eligible for a separate design investigation, but it is
not the highest-priority contest implementation. Agent_Col still lacks the
judge-facing collaborative artifact loop, browser workspace, authenticated
ownership, durable background execution, and public Cloud Run deployment.
Adding another expert before those surfaces would increase capability breadth
without completing the product's visible continuity story.

The smallest recommended next architecture pass is therefore:

> **M8-COL.1 — Judge-Facing Collaborative Artifact Loop Boundary Design**

That design should reconcile chat-controlled synthesis, artifact retrieval,
accepted/rejected/edited artifact feedback, governed preference effects on a
later artifact, and the receipts required by the future workspace. It should
decide which work must become durable before adding infrastructure. Deep
Research should remain a later bounded design pass unless the core judged
workflow, deployment, and demo schedule have sufficient margin.

## Explicitly unfinished work

M7 closure does not implement or prove:

- chat-routed synthesis or artifact management;
- governed-memory personalization of structured synthesis;
- artifact feedback and version comparison;
- durable background jobs;
- document or PDF ingestion;
- collaboration-history retention and deletion;
- authenticated identity or ownership;
- rate limiting or production security controls;
- browser UI, Cloud Run deployment, hosted smoke testing, or the final demo;
- Deep Research, Antigravity, MCP, Data Agents, or other optional integrations.
