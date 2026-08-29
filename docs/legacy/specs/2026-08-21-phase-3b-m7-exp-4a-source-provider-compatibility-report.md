# M7-EXP.4A Source Expert Provider Compatibility Report

Status: compatibility spike complete; M7-EXP.4B-R1 implemented, pending manual
verification

Date: 2026-08-21

## Executive verdict

The original M7.2 selection of an ADK `LlmAgent` with the built-in
`url_context` tool is **not sufficient for Agent_Col's strict Source Expert
contract with the currently pinned dependencies**.

URL Context itself works with Gemini 3.6 Flash through Agent_Col's configured
Vertex AI / Gemini Enterprise client. The raw Google Gen AI response contains:

- one retrieval result per requested URL;
- the retrieved URL;
- an explicit retrieval status;
- grounding chunks;
- grounding supports that map output segments to grounding chunks.

The blocking issue is the ADK conversion boundary. `google-adk==2.7.0`
converts a Gen AI `GenerateContentResponse` into `LlmResponse`, but
`LlmResponse` has no `url_context_metadata` field. The conversion retains
`grounding_metadata` while dropping the per-URL retrieval results. That makes
an inline ADK Source specialist unable to prove which requested URLs failed,
were paywalled, or were rejected as unsafe.

M7-EXP.4B live verification found one additional provider constraint: the
pinned Vertex GenerateContent structured-output configuration did not
reliably return claim grounding when URL Context and JSON output were requested
in the same call. The strict validator correctly rejected that response.

The corrected Source Expert boundary is therefore:

```text
Agent_Col ADK supervisor
        |
        | bounded model-selected FunctionTool invocation
        v
application-owned async Source Expert service
        |
        | one-turn natural-language retrieval request
        v
Gemini 3.6 Flash + URL Context
        |
        | raw URL statuses and provider-grounded segments
        v
deterministic evidence extraction
        |
        | bounded grounded corpus
        v
tool-free structured classification request
        |
        v
exact-match deterministic validation and normalization
        |
        v
structured result returned to Agent_Col
```

Agent_Col remains the sole conversational owner. The Source Expert service has
no persistence authority and cannot call another expert.

## Scope

This pass compared four provider/runtime surfaces without modifying production
code:

1. Google Gen AI `models.generate_content()` with URL Context;
2. a one-turn Google Gen AI Chat with URL Context;
3. Gemini Enterprise Agent Platform Interactions API;
4. ADK `LlmResponse.create()` conversion of the successful raw response.

The probes used only these fixed public URLs:

- `https://example.com/`
- `https://example.com/agent-col-source-expert-missing-page`

Probe output was limited to metadata presence, counts, URLs, statuses, and
error classes. Retrieved page bodies, generated response text, credentials,
identifiers, and hidden reasoning were not printed or stored.

## Verified environment

| Component | Verified value |
| --- | --- |
| Python ADK | `google-adk==2.7.0` |
| Google Gen AI SDK | `google-genai==2.18.1` |
| Model | `gemini-3.6-flash` |
| Provider mode | Vertex AI / Gemini Enterprise Agent Platform |
| Location | `global` |
| Authentication | Application Default Credentials |

No API key was used.

## Official API evidence

Google's [URL Context guide](https://ai.google.dev/gemini-api/docs/url-context)
states that URL Context can retrieve supplied public URLs, supports Gemini 3.6
Flash, permits up to 20 URLs per request, and reports inline URL citations plus
URL retrieval-result steps on the Gemini API Interactions surface. It also
documents public-access and content-type limitations.

The [GenerateContent API reference](https://ai.google.dev/api/generate-content)
defines `Candidate.urlContextMetadata`, containing a `urlMetadata` entry for
each retrieval. Each entry has `retrievedUrl` and `urlRetrievalStatus`. The
documented statuses are success, error, paywall, and unsafe.

The [Gemini Enterprise Agent Platform Interactions API](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/interactions-api)
is explicitly experimental. Its current public model-option list does not
offer Gemini 3.6 Flash as a model interaction on the Vertex/Enterprise surface,
which matches the live rejection observed in this pass.

## Live compatibility results

### Raw `models.generate_content()`

Result: provider-compatible, but warning-prone for automatic tool use.

The two-URL probe returned:

```text
candidate_count = 1
text_present = true
url_context_metadata_present = true
https://example.com/ = URL_RETRIEVAL_STATUS_SUCCESS
https://example.com/agent-col-source-expert-missing-page = URL_RETRIEVAL_STATUS_ERROR
grounding_metadata_present = true
grounding_chunk_count = 1
grounding_support_count = 1
grounding_uri = https://example.com/
citation_metadata_present = false
```

This proves that the raw GenerateContent candidate exposes both successful and
failed retrieval status in one response. It also proves that grounded source
attribution arrives through `grounding_metadata`, not `citation_metadata`, for
this URL Context response.

The SDK emitted its automatic-function-calling warning recommending Chat
`send_message()` rather than direct `models.generate_content()`.

### One-turn Chat `send_message()`

Result: provider-compatible and preferred for the retrieval stage.

The one-URL Chat probe returned the same required evidence:

```text
url_context_metadata_present = true
retrieval_status = URL_RETRIEVAL_STATUS_SUCCESS
grounding_metadata_present = true
grounding_chunk_count = 1
grounding_support_count = 1
grounding_uri = https://example.com/
```

It did not emit the direct-generate automatic-function-calling warning. The
Source service therefore creates a fresh, one-turn async Chat for the
retrieval stage and calls `send_message()`. It then uses a separate,
tool-free structured call to classify only locally extracted grounded
segments.

The live response-shape probe used the synchronous Chat client to isolate the
provider contract. Local SDK inspection separately confirmed that
`client.aio.chats.create()` returns `AsyncChat` and its awaited
`send_message()` returns the same `GenerateContentResponse` type. Production
implementation must use that async surface.

The Chat object is invocation-local only. It does not become a second durable
session or memory source.

### Gemini Enterprise Interactions API

Result: not compatible with Agent_Col's current model/provider combination.

The SDK call used:

```text
model = gemini-3.6-flash
tools = [{type: url_context}]
store = false
```

The live endpoint returned HTTP 400 and the SDK surfaced `BadRequestError`
because the model interaction was unsupported. This is not a URL retrieval
failure; the model/API combination was rejected before the requested Source
workflow could run.

The Gemini API documentation shows a richer Interactions URL Context contract,
including `url_context_result` steps and inline `url_citation` annotations, but
that Gemini API surface uses API-key authentication. Agent_Col has intentionally
standardized on Vertex ADC and should not reintroduce an API key merely to use
that response shape.

### ADK `LlmResponse` conversion

Result: partial metadata survives, but the strict contract cannot be met.

Local type inspection and conversion of the successful live response proved:

```text
ADK LlmResponse has url_context_metadata field = false
converted grounding_metadata_present = true
converted content_present = true
converted citation_metadata_present = false
```

The ADK event path can retain grounded source chunks and claim supports. It
cannot retain the authoritative per-URL retrieval status because that field is
absent from the current `LlmResponse` contract.

Inferring retrieval success from the presence of a grounding chunk would be
incorrect. In the two-URL probe, one URL succeeded and one failed while only
the successful source produced a grounding chunk. Once the retrieval results
are dropped, the missing URL's exact outcome cannot be reconstructed.

## Compatibility matrix

| Surface | Gemini 3.6 Flash + Vertex ADC | URL statuses | Claim grounding | Recommended |
| --- | --- | --- | --- | --- |
| Direct `models.generate_content()` | Works | Preserved | Preserved | No; emits AFC guidance warning |
| One-turn Chat `send_message()` | Works | Preserved | Preserved | Yes; Source service provider call |
| Enterprise Interactions API | Rejected | Not returned | Not returned | No for current model/provider |
| ADK `LlmAgent` event | Model call can work | Dropped | Preserved | No for strict Source contract |

## Corrected Source Expert design boundary

### Invocation ownership

Agent_Col still decides whether a Source delegation is materially needed. The
application does not force URL analysis from keyword rules.

The ADK supervisor exposes one narrowly described async `FunctionTool`. The
tool calls an application-owned Source Expert service. This service is
model-backed, but the application owns:

- URL validation and allowlisting;
- input bounds;
- timeout enforcement;
- provider-response validation;
- evidence normalization;
- action and citation receipt construction.

The service owns no Firestore writes and returns its validated result to
Agent_Col rather than answering the user directly.

### Provider invocation

Each Source invocation creates a fresh retrieval Chat configured with:

- the existing shared Vertex AI client;
- `gemini-3.6-flash`;
- only the URL Context built-in tool;
- no Search, Code Execution, functions, sub-agents, or persistent session;
- a bounded prompt created from the server-validated objective, constraints,
  and allowed URLs;
- no provider-enforced JSON output, because that combination did not reliably
  preserve grounding in the verified Vertex configuration.

The retrieval Chat is single-turn and discarded after its grounded segments
are extracted. A second fresh Chat has no tools and receives only the bounded
objective, constraints, grounded segment text, and server-assigned source IDs.
Its structured output is accepted only when every source-backed statement is
an exact match for a grounded segment with the same source IDs.

### Authoritative metadata

The service treats these raw candidate fields as authoritative:

- `url_context_metadata.url_metadata` for each URL and retrieval status;
- `grounding_metadata.grounding_chunks` for source URLs;
- `grounding_metadata.grounding_supports` for claim-to-source relationships.

The model's prose or structured output is not authoritative for URLs,
retrieval status, or citations.

### Status normalization

The internal Source result should preserve provider meaning:

| Provider status | Internal status |
| --- | --- |
| `URL_RETRIEVAL_STATUS_SUCCESS` | `retrieved` |
| `URL_RETRIEVAL_STATUS_ERROR` | `error` |
| `URL_RETRIEVAL_STATUS_PAYWALL` | `paywall` |
| `URL_RETRIEVAL_STATUS_UNSAFE` | `unsafe` |
| missing or unspecified | `invalid_output` for the invocation |

This is more accurate than collapsing all failures into `unsupported` or
`inaccessible`. Agent_Col may explain those statuses in user-friendly language
without altering the receipt.

### Citation construction

Public `CitationReference` values must be created deterministically from
grounding chunks referenced by grounding supports. A citation is accepted only
when:

1. its normalized URI matches a server-validated input URL;
2. that URL has a successful retrieval status;
3. at least one grounding support references the chunk;
4. the final Agent_Col response actually uses the supported Source result.

`citation_metadata` is not the Source evidence channel. The live response left
it empty, and the GenerateContent reference describes it separately from URL
Context and grounding metadata.

### Delegation accounting

Although the Source Expert is exposed through `FunctionTool` instead of
`AgentTool`, it remains a cognitive expert delegation for policy purposes. It
must consume one of the existing maximum two specialist slots. It has depth
one and cannot call another expert.

## Rejected alternatives

### Keep the ADK `LlmAgent` and infer status

Rejected. Grounding proves which sources supported output, not why another
requested URL failed. Inference would violate the strict evidence contract.

### Patch or subclass ADK to preserve the dropped field

Rejected. A private adapter override would couple Agent_Col to undocumented ADK
internals and could break during routine upgrades.

### Reintroduce a Gemini API key for Interactions

Rejected. Vertex ADC already satisfies local and Cloud Run authentication,
billing, and deployment requirements. A second credential path would increase
secret management and deployment complexity for no required product benefit.

### Weaken the Source contract

Rejected. Per-URL retrieval truth is necessary to report partial and failed
retrieval honestly. The provider already exposes it through the viable Chat
response; discarding it would be an avoidable reliability regression.

## M7-EXP.4B-R1 implementation boundary

M7-EXP.4B-R1 implements only the provider and evidence boundary, not supervisor
routing:

1. strict Source input and output schemas;
2. public URL validation and allowlist construction;
3. an async Source service using a URL Context retrieval turn followed by a
   tool-free structured-classification turn;
4. deterministic extraction of URL statuses, grounding chunks, and supports;
5. exact-match local output validation and safe error translation;
6. offline tests using synthetic raw provider responses, including mixed
   success/error retrieval and missing metadata.

Supervisor registration, live routing, and restraint evaluation should remain
separate later passes.

## Risks and unresolved implementation questions

- URL Context is provider-dependent and must be covered by a small live smoke
  check in addition to offline tests.
- The provider permits more URLs than Agent_Col should expose. M7.2's stricter
  one-to-three URL limit remains appropriate.
- Retrieved content is untrusted and may contain prompt injection. The provider
  prompt and local result validator must prevent source content from changing
  instructions or authorizing tools.
- URL normalization must be strict enough to compare provider-returned URIs to
  the allowlist without accepting attacker-controlled lookalikes or redirects.
- Grounding support indices and text segments must be validated before they are
  used to construct public citations.
- Provider quotas, latency, and supported-model behavior can change. The report
  records the verified 2026-08-21 environment, not a permanent guarantee.

## Pass boundary confirmation

This compatibility spike changed documentation only. It did not modify:

- application or test code;
- dependencies;
- provider configuration;
- schemas;
- ADK tools or routing;
- Firestore behavior;
- runtime contracts.
