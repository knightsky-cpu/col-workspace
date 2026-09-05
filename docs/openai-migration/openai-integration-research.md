# Agent Col: Source-Faithful OpenAI Integration Reconnaissance & Architecture

This document presents source-verified architectural reconnaissance for migrating **Agent Col**'s intelligence and inference layer from Google (Gemini, Vertex AI, Google ADK, Google Search grounding, Google STT/TTS) to **OpenAI**. Repository descriptions are marked **CURRENT SOURCE**; PostgreSQL/OpenAI components are **TARGET DESIGN**. Model and tool names are research candidates that must be revalidated against official OpenAI documentation and account availability at implementation time.

Official API baselines for this revision: [Models](https://developers.openai.com/api/docs/models), [Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create), [Web search](https://developers.openai.com/api/docs/guides/tools-web-search), and [data controls](https://developers.openai.com/api/docs/guides/your-data). These sources are temporally unstable; implementation must pin an SDK/API contract and rerun compatibility tests.

---

## A. Executive Recommendation

The recommended target architecture for Agent Col is a **Local-First, Application-Owned Provider Substitution** using the **OpenAI Responses API** (`AsyncOpenAI` SDK) behind a narrow provider adapter. Current source still uses Firestore, Google GenAI, and Google ADK.

```
                    ┌────────────────────────────────────────────────────────┐
                    │       TARGET AGENT COL APPLICATION                     │
                    │                                                        │
                    │  ┌──────────────────┐      ┌────────────────────────┐  │
                    │  │ PostgreSQL DB    │      │ AgentJob Orchestrator  │  │
                    │  │ (Auth & State)   │      │ (Leasing & Queues)     │  │
                    │  └─────────┬────────┘      └───────────┬────────────┘  │
                    │            │                           │               │
                    │  ┌─────────┴───────────────────────────┴────────────┐  │
                    │  │ AgentColTurnService                              │  │
                    │  │ (Session History, Governed Memory, Notes,        │  │
                    │  │  Working State, Subagent Routing)                │  │
                    │  └─────────────────────────┬────────────────────────┘  │
                    └────────────────────────────┼───────────────────────────┘
                                                 │ Application-Owned Prompt & Tools
                                                 ▼
                    ┌────────────────────────────────────────────────────────┐
                    │               OPENAI PROVIDER ADAPTER                  │
                    │               (OpenAIProviderAdapter)                  │
                    │                                                        │
                    │  • Assembles instructions & context                    │
                    │  • Maps Pydantic models to JSON Schema (text.format)   │
                    │  • Translates tool definitions                         │
                    │  • Translates OpenAI SSE deltas to Agent Col events    │
                    │  • Enforces store=false for local-first privacy        │
                    │  • Tracks token, cache, & reasoning usage              │
                    └────────────────────────────┬───────────────────────────┘
                                                 │ HTTPS / WSS
                                                 ▼
                    ┌────────────────────────────────────────────────────────┐
                    │                 OPENAI INFERENCE ENGINE                │
                    │                                                        │
                    │  • GPT-5.6 Model Family (Sol / Terra / Luna)           │
                    │  • Strict Structured Outputs (text.format)             │
                    │  • Function / Tool Selection                           │
                    │  • Built-in Web Search Grounding                       │
                    │  • Speech: gpt-transcribe & gpt-4o-mini-tts            │
                    └────────────────────────────────────────────────────────┘
```

### Key Architectural Principles

1. **Local-First Authority:** Agent Col remains the authoritative application runtime. PostgreSQL stores all sessions, chat turns, messages, governed memory, workspace notes, hidden `working_state`, artifacts, feedback, and `AgentJob` queue state.
2. **Application-Owned Conversation State:** Requests to OpenAI are inference over application-assembled context. `store=false` disables Responses application-state storage but does not itself guarantee Zero Data Retention or eliminate abuse-monitoring retention; ZDR/MAM eligibility remains an account/project control.
3. **Preservation of Core Boundaries:** Model-generated outputs and tool calls remain *proposals* evaluated by Agent Col's verification, authorization, and transactional persistence logic.
4. **Direct Responses API Adoption:** The direct OpenAI Responses API provides all required capabilities without introducing competing framework abstractions.

---

## B. Current Google Dependency Inventory

The table below catalogs the principal production Google/Gemini/Vertex/ADK dependencies. It must be regenerated from current production imports before dependency retirement; it is not an exhaustive list of compatibility checks, spikes, or tests.

| Source File Path | Google Dependency | Application Contract Depending On It | Classification | Current Responsibility & Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `vertex_config.py` / `main.py` | Vertex settings / `google.genai.Client` | `VertexAISettings`, FastAPI lifespan | `configuration`, `model client construction` | `vertex_config.py` validates settings and returns client keyword arguments; `main.py:1983-1988` instantiates the shared client. |
| `agent_col_responder.py` | `google.adk.Agent`, `google.adk.apps.App`, `google.adk.models.Gemini` | `create_responder_app` | `agent orchestration`, `model invocation` | Configures Google ADK application for primary conversational responder using `gemini-3.6-flash`. |
| `supervisor_runtime.py` | `google.adk.runner.Runner` | `SupervisorRuntime` | `agent orchestration`, `streaming` | Wraps ADK `Runner` to execute and stream turns, handle timeouts, and extract tool call events. |
| `supervisor.py` | ADK App Constants | `SUPERVISOR_APP_NAME` | `agent orchestration` | Constant definitions for ADK app initialization. |
| `agent_col_turn_service.py` | `google.genai.Client`, `google.genai.types` | `AgentColTurnService` | `agent orchestration`, `provider adapter` | Production turn orchestrator passing `genai.Client` to routing providers, specialists, and responders. |
| `agent_col_routing_provider_v4.py` | `google.genai.Client`, `genai.types` | `AgentColRoutingProviderV4` | `structured output`, `model invocation` | Structured-output routing provider using Vertex/GenAI SDK with Pydantic JSON schemas on `gemini-3.6-flash`. |
| `agent_col_routing_provider_v3.py` | `google.genai.Client`, `genai.types` | `AgentColRoutingProviderV3` | `structured output`, `model invocation` | Legacy/fallback structured-output routing provider using GenAI SDK. |
| `agent_col_artifact_executor.py` | `google.genai.Client`, `genai.types` | `AgentColArtifactExecutor` | `provider adapter`, `structured output` | Background worker queue handler executing blueprint artifact generation calls against `genai.Client`. |
| `agent_col_artifact_feedback_executor.py` | `google.genai.types` | Responder feedback projection | `provider-specific context type` | Deterministic chat-owned feedback boundary. It does not invoke a model or run as an AgentJob worker. |
| `generic_artifact_generation.py` | `google.genai.Client`, `genai.types` | `generate_generic_artifact` | `structured output`, `model invocation` | GenAI SDK caller for generating single-file code/document artifacts with structured outputs. |
| `synthesis_service.py` | `google.genai.Client`, `genai.types` | `SynthesisApplicationService` | `structured output`, `model invocation` | GenAI SDK caller for multi-file blueprint synthesis generation. |
| `research_expert.py` / `service.py` | `google.genai.Client`, `types.GoogleSearch` | `ResearchExpertService` | `web/research`, `model invocation` | Research specialist using Google Search grounding (`tools=[types.Tool(google_search=...)]`). |
| `computational_expert.py` / `service.py` | `google.genai.Client`, `genai.types` | `ComputationalExpertService` | `model invocation`, `structured output` | Computation specialist executing math/analysis prompts over GenAI SDK. |
| `source_expert.py` / `service.py` | `google.genai.Client`, `genai.types` | `SourceExpertService` | `model invocation`, `structured output` | Codebase/source evaluation specialist over GenAI SDK. |
| `requirements_verification_service.py` | `google.genai.Client`, `genai.types` | `RequirementsVerificationService` | `model invocation`, `structured output` | Requirements verification specialist over GenAI SDK. |
| `working_state_service.py` | `google.genai.Client`, `genai.types` | `WorkingStateService` | `structured output`, `model invocation` | Background worker updating hidden session working state snapshots via GenAI SDK. |
| `continuity_service.py` | `google.genai.Client`, `genai.types` | `ContinuityService` | `structured output`, `model invocation` | Expands user reference terms against historical context using GenAI SDK. |
| `speech_service.py` | Google Speech-to-Text & Text-to-Speech SDKs | `SpeechTranscriptionService` / `SpeechSynthesisService` | `speech` | Audio transcription (STT) and voice synthesis (TTS) edge service adapters. |
| `auth.py` | `google.oauth2.id_token`, `google.auth.transport.requests` | `Authenticator` | `authentication` | Verifies Google OIDC ID tokens when `AGENT_COL_AUTH_MODE=google_oidc`. |
| `database.py` | `google.cloud.firestore` | `MemoryEngine` | `persistence` | Firestore SDK database driver (targeted for PostgreSQL replacement). |
| `agent_job_repository.py`, `workspace_cleanup.py` | `google.cloud.firestore` | AgentJob persistence and workspace cleanup | `persistence` | Direct Firestore SDK use outside `database.py`. |
| `memory_proposal_tool.py`, `collaborative_note_tool.py`, `source_expert_tool.py` | `google.adk.tools` | Governed responder tool declarations | `agent orchestration` | ADK tool wrappers that must be migrated with the responder/tool loop. |
| `agent_col_responder_context*.py` | `google.genai.types` | Server-validated responder context | `provider-specific context type` | Constructs GenAI content objects even when no model call occurs in the module itself. |

---

## C. OpenAI Capability Mapping

The table below maps each Google/Gemini capability to its direct OpenAI equivalent:

```text
Current Source                  Current Google Capability                   Candidate OpenAI Replacement
──────────────────────────────  ─────────────────────────────────────────   ──────────────────────────────────────────────
vertex_config.py                VertexAISettings / genai.Client             OpenAISettings / AsyncOpenAI client
agent_col_responder.py          Google ADK Agent / App / Gemini             OpenAIResponderAdapter (Responses API)
supervisor_runtime.py           Google ADK Runner                           OpenAIRunnerAdapter (Stream & Tool Loop)
routing_provider_v4.py          GenAI SDK JSON Schema structured output    Responses API text.format: { type: "json_schema" }
synthesis_service.py            GenAI SDK Blueprint Generation              Responses API Pydantic Structured Output
generic_artifact_generation.py  GenAI SDK Artifact Generation               Responses API Pydantic Structured Output
research_expert_service.py      GenAI Google Search Grounding Tool          Responses API Built-in Web Search Tool
computational_expert_service.py GenAI SDK Code/Math Generation              Responses API + gpt-5.6-sol (reasoning: "high")
source_expert_service.py        GenAI SDK Source Analysis                   Responses API + gpt-5.6-sol / terra
requirements_verification_service.py GenAI SDK Requirements Validation       Responses API + candidate model + Schema
working_state_service.py        GenAI SDK Working State Extraction          Responses API + gpt-5.6-luna
continuity_service.py           GenAI SDK Term Expansion                    Responses API + gpt-5.6-luna
speech_service.py               Google Speech STT & TTS                    gpt-transcribe & gpt-4o-mini-tts
auth.py                         Google OIDC Token Verification              Agent Col Auth Mode + Optional ChatGPT OAuth
```

---

## D. Recommended Provider Architecture

Agent Col will replace the Google ADK and `genai.Client` runtime with an application-owned `OpenAIProviderAdapter`.

```text
                               AGENT COL APPLICATION CORE
   ┌────────────────────────────────────────────────────────────────────────────────┐
   │                                                                                │
   │  ┌───────────────────────┐   ┌──────────────────────┐   ┌───────────────────┐  │
   │  │ PostgreSQL Repository │   │ AgentJob Orchestrator│   │ Auth & Session    │  │
   │  └───────────┬───────────┘   └───────────┬──────────┘   └─────────┬─────────┘  │
   │              │                           │                        │            │
   │              └───────────────────────────┼────────────────────────┘            │
   │                                          │                                     │
   │                              ┌───────────▼────────────┐                        │
   │                              │ AgentColTurnService    │                        │
   │                              └───────────┬────────────┘                        │
   │                                          │                                     │
   └──────────────────────────────────────────┼─────────────────────────────────────┘
                                              │
                    ┌─────────────────────────▼─────────────────────────┐
                    │        OPENAI PROVIDER ADAPTER INTERFACE          │
                    │        (openai_provider_adapter.py)               │
                    │                                                   │
                    │  async def generate_response(...) -> ChatResponse │
                    │  async def stream_response(...) -> AsyncIterator  │
                    │  async def generate_structured(...) -> TModel      │
                    │  async def execute_web_search(...) -> CitationSet │
                    └─────────────────────────┬─────────────────────────┘
                                              │
                                              ▼
                    ┌───────────────────────────────────────────────────┐
                    │               OPENAI RESPONSES API                │
                    │            (AsyncOpenAI.responses.create)         │
                    │                                                   │
                    │  • Model: gpt-5.6-sol / terra / luna              │
                    │  • Instructions: Server-assembled system prompt  │
                    │  • Input: Assembled context & history             │
                    │  • Tools: Function schemas + web_search           │
                    │  • Format: text.format = { type: "json_schema" }  │
                    │  • Privacy: store=false                           │
                    └───────────────────────────────────────────────────┘
```

---

## E. Responses API vs. OpenAI Agents SDK Comparison

| Architectural Criteria | Option A: Direct Responses API + Agent Col (Recommended) | Option B: Embedded Agents SDK | Option C: Full Agents SDK Migration |
| :--- | :--- | :--- | :--- |
| **Session & History Authority** | **Agent Col (PostgreSQL)** | Agent Col (Supports local sessions) | Agent Col (Supports local sessions) |
| **Queue & Job Leasing** | **Agent Col (`AgentJobRepository`)** | Agent Col | Agents SDK Runner (Different scope) |
| **Tool Execution & Approval** | **Agent Col (Explicit policy gate)** | Agents SDK tool loop | Agents SDK tool loop |
| **Governed Memory & Notes** | **Agent Col (`TrustedMemoryService`)** | Agent Col | Agents SDK Memory |
| **Subagent Routing** | **Agent Col (`agent_col_routing_v4`)** | Agents SDK Handoffs | Agents SDK Handoffs |
| **Data Retention Control** | **Explicit `store=false`** | Client-side configurable | Client-side configurable |
| **Migration Risk** | **Low (Provider replacement only)** | Medium (Dual runtime complexity) | High (Redundant runtime abstractions) |

### Decision Rationale

The OpenAI Agents SDK supports client-side local session implementations and does not inherently require cloud session storage. Furthermore, the Agents SDK Runner is not a direct replacement for Agent Col's durable `AgentJob` queue and lease-locking layer.

**Option A (Direct Responses API behind `OpenAIProviderAdapter`)** is recommended because Agent Col already owns:
- Turn lifecycle & lease locking
- Tool dispatch & approval boundaries
- Subagent routing (`agent_col_routing_v4`)
- Persistence (PostgreSQL)
- Session history & transcript authority
- Governed memory & workspace notes
- `AgentJob` orchestration & retries

Using the Agents SDK would introduce overlapping higher-level runtime abstractions over capabilities Agent Col already owns, not because the SDK forces cloud persistence.

---

## F. Conversation-State Strategy & Stateless Reasoning Benchmark Evaluation

### Context Assembly & Privacy Controls

Agent Col will treat OpenAI API calls as **stateless inference evaluations** using `store: false`.

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AGENT COL BACKEND                                  │
│                                                                                 │
│   1. Fetch session transcript from PostgreSQL (messages table)                  │
│   2. Fetch governed profile memory (TrustedMemoryService)                      │
│   3. Fetch active collaborative notes (CollaborativeNoteService)               │
│   4. Fetch hidden working state snapshot (WorkingStateService)                  │
│   5. Assemble system instructions + message history payload                     │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │
                                         │  POST /v1/responses
                                         │  { "store": false, "input": [...] }
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             OPENAI RESPONSES API                                │
│                                                                                 │
│   • Evaluates inference over supplied input                                     │
│   • Executes reasoning and tool selection                                       │
│   • Returns model response text + tool call proposals                           │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │
                                         │  Response & Receipts
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AGENT COL BACKEND                                  │
│                                                                                 │
│   1. Validate model response & tool call receipts                               │
│   2. Apply transactional updates to PostgreSQL (chat_turns & messages)          │
│   3. Asynchronously trigger working state update if applicable                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Data Privacy & Retention Specifications (`store=false`, ZDR, MAM)

- **`store=false` Scope:** `store=false` disables provider-side application session storage in the Responses API.
- **Abuse Monitoring vs. ZDR:** `store=false` does **not** independently guarantee Zero Data Retention (ZDR). Default API abuse-monitoring retention (30 days) still applies unless Zero Data Retention or Modified Abuse Monitoring (MAM) is explicitly enabled on the OpenAI account/project level.
- **Third-Party Tool Exceptions:** Provider-side statelessness does not cover external third-party tool endpoints or hosted vector stores if invoked.

### Reasoning Continuation Benchmark Evaluation

Reasoning models may return opaque reasoning output items suitable for continuation without exposing private chain-of-thought. To determine the appropriate multi-turn strategy when `store=false` is active, Agent Col will benchmark two application-level approaches. The labels below are architecture names, not values for an OpenAI `reasoning.context` parameter.

#### Strategy A (Preferred Baseline): Application-Reconstructed Context
- **Mechanism:** Each request receives locally stored transcript, governed memory, and `working_state` context without replaying prior opaque reasoning items.
- **Benefits:** Simpler, fully local-first architecture. Eliminates the need to persist or echo opaque encrypted continuation tokens across API calls.

#### Strategy B (Benchmark Candidate): Encrypted Reasoning Replay
- **Mechanism:** Requests include `reasoning.encrypted_content` in provider output and the application locally persists/replays the opaque output items on subsequent calls. The exact `include` contract must be verified against the pinned Responses API/SDK.
- **Privacy Guarantee:** Agent Col never decrypts, exposes, or interprets encrypted reasoning content.

#### Recommendation Rule
Strategy A is recommended as the baseline architecture. Strategy B will be adopted only if representative multi-turn Agent Col benchmark evaluations demonstrate a material quality regression under Strategy A.

---

## G. Streaming Migration Architecture

Agent Col streams responses to the browser using Server-Sent Events (SSE) via `/api/chat/stream`. The `OpenAIProviderAdapter` will map current OpenAI Responses API stream events to Agent Col's event format:

```text
┌──────────────────────────────┐
│  OpenAI Stream Event         │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  OpenAIProviderAdapter       │
│                              │
│  • Filters reasoning tokens  │
│  • Maps text.delta events    │
│  • Handles completion & errs │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  AgentColTurnService         │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Existing SSE Transport      │
│  (/api/chat/stream)          │
│                              │
│  event: delta                │
│  data: {"text": "..."}       │
│                              │
│  event: final                │
│  data: ChatResponse JSON     │
└──────────────┬───────────────┘
```

### Corrected Responses Streaming Event Mapping

The `OpenAIProviderAdapter` listens for specific Responses API event objects:

- `response.output_text.delta`: Contains incremental text deltas (mapped to Agent Col `delta` SSE events).
- `response.output_text.done`: Marks completion of the text output part.
- `response.completed`: Signals full response completion.
- `response.failed` / `response.incomplete`: Triggers error and partial-failure handling.

*Note: Legacy Chat Completions events like `response.content_part.delta` are not used.*

---

## H. Structured Outputs & Function Calling

OpenAI **Structured Outputs** with `strict: true` constrain successful structured content to the supported JSON Schema subset. They do not guarantee that every request produces structured content: refusal, incomplete, failed, or otherwise unavailable output must still be handled. They also do not replace application-side Pydantic validation for local business invariants. In the Responses API, structured outputs are configured through `text.format`:

```json
{
  "text": {
    "format": {
      "type": "json_schema",
      "name": "AgentColRoutingDecisionV4",
      "schema": { ... },
      "strict": true
    }
  }
}
```

### Application-Side Pydantic Validation

Even with `strict: true` enabled on the API request, Agent Col will execute application-side Pydantic validation (`Model.model_validate(response_json)`) to enforce local business invariants, string length bounds, and sanitization rules.

| Subsystem | Existing Gemini Boundary | OpenAI Responses Structured Output Target |
| :--- | :--- | :--- |
| **v4 Routing** | `response_mime_type="application/json"` | `text.format` with Pydantic model `AgentColRoutingDecisionV4` |
| **Blueprint Synthesis** | GenAI SDK Structured Output | `text.format` with Pydantic model `SynthesisBlueprint` |
| **Generic Artifacts** | GenAI SDK SingleFileArtifact | `text.format` with Pydantic model `SingleFileArtifact` |
| **Working State** | GenAI SDK WorkingStateSnapshot | `text.format` with Pydantic model `WorkingStateSnapshot` |
| **Continuity** | GenAI SDK Term Expansion | `text.format` with Pydantic model `ContinuityExpansion` |
| **Preference Learning** | GenAI SDK PreferenceObservation | `text.format` with Pydantic model `PreferenceObservation` |

---

## I. GPT-5.6 Model Workload Matrix

The workload matrix records the GPT-5.6 candidates evaluated during this research (`gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`). It is not an exhaustive current-model catalog. Before implementation, recheck official model availability, account access, pricing, latency, and capability, then validate final selections through representative evaluations.

| Subsystem / Task | Recommended GPT-5.6 Candidate Model | Candidate Reasoning Effort (`reasoning.effort`) | Justification | Target Latency | User Facing? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary Conversational Responder** | `gpt-5.6-sol` | `medium` | Flagship reasoning and conversational synthesis; tool dispatch. | < 1.5s TTFT | Yes |
| **Complex Synthesis / Code Generation** | `gpt-5.6-sol` | `high` | Multi-file blueprint generation, complex refactoring, AST consistency. | < 3.0s | Yes |
| **v4 Intent Routing** | `gpt-5.6-luna` | `none` / `low` | Candidate low-latency structured classification; refusal/incomplete handling and local validation remain required. | < 350ms | No |
| **Computational Expert** | `gpt-5.6-sol` | `high` | Mathematical analysis, algorithmic problem solving. | < 4.0s | Indirect |
| **Requirements Verification** | `gpt-5.6-terra` | `medium` | Strict verification of generated code against user constraints. | < 3.0s | Indirect |
| **Source Code Expert** | `gpt-5.6-sol` | `medium` | Deep codebase analysis, pattern matching, structural review. | < 2.0s | Indirect |
| **Research Synthesis Expert** | `gpt-5.6-terra` + Web Search | `medium` | Fact synthesis with grounded search citations. | < 3.0s | Indirect |
| **Working State Analyst** | `gpt-5.6-luna` | `none` | Fast background JSON extraction of session state. | < 700ms | No |
| **Memory Analyst** | `gpt-5.6-luna` | `none` | Governed memory proposal extraction against policy rules. | < 500ms | No |
| **Collaborative Note Analyst** | `gpt-5.6-luna` | `none` | Fast workspace note proposal generation. | < 500ms | No |
| **Continuity Expansion** | `gpt-5.6-luna` | `none` | Term expansion against historical chat context. | < 400ms | No |
| **Preference Observation Extraction** | `gpt-5.6-luna` | `none` | Lightweight classification of user preferences. | < 400ms | No |

---

## J. Research & Web-Search Migration

Agent Col currently uses Google Search grounding inside `ResearchExpertService`. The target uses OpenAI's built-in **Web Search Tool**. Prefer the current non-preview `web_search` tool contract when supported by the pinned SDK/API; retain `web_search_preview` only as an explicitly tested compatibility path.

```python
response = await client.responses.create(
    model="gpt-5.6-terra",
    tools=[{"type": "web_search"}],
    input=user_query,
)
```

### Citation & Grounding Mapping

The adapter must map only fields established by the pinned Web Search annotation schema. URL/title and annotation offsets are the stable minimum to verify; do not require a `snippet` field unless the selected API response actually supplies it. Agent Col may derive a bounded display excerpt from application-owned response text when policy permits.

```python
# Citation mapping logic inside OpenAIProviderAdapter
CitationReceipt(
    url=annotation.url,
    title=annotation.title or annotation.url,
    snippet=verified_or_derived_excerpt,
)
```

---

## K. STT / TTS & Audio Model Catalog Migration

Speech capabilities in `speech_service.py` will be migrated through a two-phase strategy using current OpenAI model offerings:

```text
                                PHASE 1: HTTP REST EDGE ADAPTERS
                                      (Immediate Replacement)

       Browser Audio           ┌────────────────────────────┐          OpenAI API
   ──────────────────────────> │ SpeechTranscriptionService │ ───────> gpt-transcribe
                               └────────────────────────────┘          (POST /v1/audio/transcriptions)

       Audio Bytes             ┌────────────────────────────┐          OpenAI API
   <────────────────────────── │  SpeechSynthesisService    │ <─────── gpt-4o-mini-tts
                               └────────────────────────────┘          (POST /v1/audio/speech)


                                 PHASE 2: REALTIME VOICE TRACK
                                      (Future Interactive Option)

       Browser WebRTC / WS     ┌────────────────────────────┐          OpenAI Realtime API
   <═════════════════════════> │ Agent Col Realtime Bridge  │ <══════> gpt-realtime-2.1
                               └────────────────────────────┘          (wss://api.openai.com/v1/realtime)
```

- **Phase 1 (Immediate HTTP REST Edge Adapters):** Replace Google STT/TTS with `gpt-transcribe` (file/batch transcription) or `gpt-live-transcribe` (where incremental transcript deltas are required) for STT, and `gpt-4o-mini-tts` for TTS synthesis. Text chat remains canonical.
- **Phase 2 (Future Realtime Track):** Introduce an optional interactive voice bridge utilizing `gpt-realtime-2.1` via WebSockets/WebRTC.

### Audio Data Retention Notice

Using audio endpoints does not categorically guarantee "zero audio persistence." Audio payload retention is governed by the account's configured Data Control settings, Zero Data Retention (ZDR) status, and Modified Abuse Monitoring (MAM) agreements.

---

## L. Authentication & Billing Options

### Authentication vs. Authorization Clarification

- **Agent Col User Identity & Authentication:** Managed locally by Agent Col (session tokens, local dev authentication, or standard OIDC).
- **OpenAI Inference Authorization & Billing:** Managed via API Keys or project credentials. Supplying a Bring Your Own Key (BYOK) API key grants *API authorization/billing entitlement*, **not** Agent Col user authentication.
- **Sign in with ChatGPT:** A third-party OAuth/OIDC identity provider path. Third-party enrollment eligibility must be verified prior to deployment; it does not automatically grant API billing credits or API key access.

### Local Usage & Token Accounting Schema

Agent Col will record detailed usage metrics in PostgreSQL (`api_usage_logs` table) for every inference request, accurately tracking prompt caching and reasoning token metrics:

```sql
CREATE TABLE api_usage_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    response_id TEXT,
    session_id TEXT REFERENCES sessions(session_id) ON DELETE SET NULL,
    turn_id TEXT,
    job_id TEXT,
    provider TEXT NOT NULL DEFAULT 'openai',
    model_name TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cached_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    estimated_cost_usd NUMERIC(10, 6),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

---

## M. Privacy & Data Retention Analysis

| OpenAI Capability | Data Retention Status | Local-First Compatibility | Required Configuration |
| :--- | :--- | :--- | :--- |
| **Responses API (Inference)** | Application state is stored by default unless disabled; abuse-monitoring retention and ZDR/MAM controls are separate | **Compatible with controls** | Set `store=false`; verify project ZDR/MAM eligibility and endpoint-specific exceptions. |
| **Automatic Prompt Caching** | Provider-managed cache behavior and retention depend on model/account controls | **Conditionally compatible** | Track `cached_tokens`/`cache_write_tokens`; verify retention mode before enabling extended caching. |
| **Background Responses** | Provider retains response state temporarily so clients can poll | **Optional, conditionally compatible** | Use only when its retention and cancellation semantics are accepted; it does not replace local AgentJobs. |
| **Audio APIs (`gpt-transcribe` / `gpt-4o-mini-tts`)** | Governed by endpoint and account-level data controls | **Conditionally compatible** | Verify the selected endpoints under the deployed account policy. |
| **Conversations API** | Hosted conversation state | **Excluded by current product policy** | Keep authoritative history in PostgreSQL; reconsider only through a separate policy decision. |
| **OpenAI Vector Stores / File Search** | Hosted vector/file state | **Excluded by current product policy** | Keep authoritative project state local; use only after explicit data-governance approval. |
| **Agents SDK tracing** | Tracing behavior depends on SDK configuration and selected services | **Excluded by current product policy** | Keep authoritative audit logs local and verify tracing is disabled or appropriately configured. |

---

## N. Reliability & Responses Incomplete Semantics

Responses API status and errors map directly into Agent Col's exception hierarchy:

```text
OpenAI Responses API Status / Event     Agent Col Internal Exception         Handling / Retry Strategy
─────────────────────────────────────── ───────────────────────────────────  ───────────────────────────────────────
response.failed                         ProviderResponseFailedError         Retry with exponential backoff (max 3)
response.incomplete (max_output_tokens) PartialResponseTruncatedError       Resume turn or request continuation
response.incomplete_details (content)   PartialContentFilterError           Emit user-visible bounded content notice
openai.APITimeoutError                  ProviderTimeoutError                Retry with backoff
openai.RateLimitError (429)            ProviderRateLimitError              Retry using Retry-After header
openai.BadRequestError (400)            ProviderInvalidRequestError         Non-retryable (fail fast)
Malformed Structured Output             StructuredOutputValidationError     Retry once with corrective prompt
```

---

## O. Source-File Migration Inventory

| File Path | Responsibility | OpenAI Replacement | Migration Category | Risk |
| :--- | :--- | :--- | :--- | :--- |
| `vertex_config.py` | Environment config | `openai_config.py` (`OpenAISettings`) | Provider-only | Low |
| `agent_col_responder.py` | ADK Responder App | `OpenAIResponderAdapter` | Provider-only | Medium |
| `supervisor_runtime.py` | ADK Runner Wrapper | `OpenAIRunnerAdapter` | Provider-only | Medium |
| `agent_col_turn_service.py` | Turn Orchestrator | Update client dependency to `OpenAIProviderAdapter` | Interface | Medium |
| `agent_col_routing_provider_v4.py` | v4 Intent Routing | Update provider to OpenAI Strict Structured Output | Provider-only | Low |
| `synthesis_service.py` | Blueprint Synthesis | Update generator to OpenAI Pydantic Response Format | Provider-only | Low |
| `generic_artifact_generation.py` | Single-file Artifacts | Update generator to OpenAI Pydantic Response Format | Provider-only | Low |
| `agent_col_artifact_executor.py` | Background Workers | Update worker client call to OpenAI adapter | Provider-only | Low |
| `agent_col_artifact_feedback_executor.py` | Deterministic chat-owned responder projection using GenAI types | Replace provider-specific content type after responder migration; do not convert it into a background worker | Provider-context type | Low |
| `research_expert_service.py` | Research Specialist | Replace Google Search with OpenAI Web Search | Provider-only | Medium |
| `computational_expert_service.py` | Math/Logic Specialist | Update to OpenAI `gpt-5.6-sol` | Provider-only | Low |
| `source_expert_service.py` | Code Specialist | Update to OpenAI `gpt-5.6-sol` | Provider-only | Low |
| `requirements_verification_service.py` | Model-backed contract validation | Update to OpenAI Structured Output | Provider-only | Low |
| `requirements_verification.py` | Deterministic verification helpers/contracts | Preserve unless source evidence identifies a provider-specific dependency | Application logic | Low |
| `working_state_service.py` | Hidden State Extraction | Update to OpenAI `gpt-5.6-luna` | Provider-only | Low |
| `continuity_service.py` | Term Expansion | Update to OpenAI `gpt-5.6-luna` | Provider-only | Low |
| `memory_proposal_tool.py`, `collaborative_note_tool.py`, `source_expert_tool.py` | ADK tool declarations | Rebind governed tool contracts to the application-owned OpenAI tool loop | Provider orchestration | Medium |
| `agent_col_responder_context.py`, `agent_col_responder_context_v2.py`, `agent_col_responder_context_v3.py` | GenAI responder content objects | Convert bounded context builders to provider-neutral application data | Provider-context type | Low |
| `agent_job_repository.py`, `workspace_cleanup.py` | Direct Firestore access outside `database.py` | Move behind PostgreSQL persistence interfaces | Persistence | High |
| `speech_service.py` | STT / TTS Adapters | Replace Google STT/TTS with `gpt-transcribe` / `gpt-4o-mini-tts` | Interface | Low |
| `auth.py` | User Auth & OIDC | Retain local-dev auth; update OIDC if replacing Google login | Interface | Low |
| `requirements.txt` | Runtime Dependencies | Add the pinned OpenAI SDK after adapter contracts exist; remove Google packages only after production import audits reach zero | Deployment-only | Medium |

---

## P. Migration Sequencing Plan

```text
Phase 1: Environment & Settings
  └── Create openai_config.py and OpenAISettings dataclass.

Phase 2: Structured Output & Routing Providers
  └── Migrate agent_col_routing_provider_v4.py to OpenAI Strict Structured Outputs (text.format).

Phase 3: Utility & Specialist Services
  └── Migrate working_state_service.py, continuity_service.py, computational_expert_service.py,
      and requirements_verification_service.py to OpenAI.

Phase 4: Synthesis & Artifact Generators
  └── Migrate synthesis_service.py and generic_artifact_generation.py to OpenAI.

Phase 5: Research Expert & Web Search Grounding
  └── Migrate research_expert_service.py to OpenAI Web Search tool.

Phase 6: Responder & Supervisor Runtime (ADK Removal)
  └── Replace agent_col_responder.py and supervisor_runtime.py with OpenAIResponderAdapter.

Phase 7: Speech Edge Adapters & Final Cleanup
  └── Migrate speech_service.py to gpt-transcribe & gpt-4o-mini-tts; remove google-genai/google-adk.
```

---

## Q. Test & Verification Strategy

1. **Unit Test Verification:** Rerun existing test suites for routing (`tests/test_agent_col_routing_v4.py`), working state, continuity, and artifact synthesis using mocked OpenAI API responses.
2. **Schema Equivalence Validation:** For successful structured responses, verify that locally validated Pydantic models preserve the application contract expected from current GenAI outputs; separately test refusal, incomplete, failed, and malformed-provider cases.
3. **Integration Verification:** Run `live-tests/` scripts against OpenAI API sandbox endpoints to prove streaming SSE deltas, web search citations, and tool call formatting.

---

## R. Unresolved Questions & Testing Items

1. **GPT-5.6 Reasoning Benchmark:** Benchmark `gpt-5.6-sol` reasoning latency under high-complexity computational workloads to verify compliance with HTTP timeouts (< 10s).
2. **Multi-Turn Reasoning Benchmark:** Compare application-reconstructed context against locally persisted opaque encrypted-reasoning replay; do not encode these strategy names as undocumented API enum values.
3. **Prompt Cache Write vs. Read Cost:** Measure total cost dynamics comparing cache-write token overhead versus cache-read savings over typical 10-turn chat sessions.
4. **Web Search Citation Contract:** Verify the exact annotation fields and offsets returned by the pinned API/SDK and define a safe application-owned excerpt fallback without assuming `snippet` exists.

---

## S. Verification Corrections

The table below records every correction made during the verification passes:

| Item | Original Claim | Corrected Claim | Official OpenAI Source | Architectural Impact |
| :--- | :--- | :--- | :--- | :--- |
| **1. Model Family** | Hardcoded legacy GPT-4o / o3-mini matrix. | Records GPT-5.6 candidates without claiming they exhaust the current catalog; requires a fresh model/access/cost evaluation at implementation time. | OpenAI Models API Documentation | Implementation Detail |
| **2. Privacy Controls** | Claimed `store=false` equals Zero Data Retention. | `store=false` disables Responses session storage; ZDR and MAM are separate account/project controls. | OpenAI API Privacy & Data Policies | Implementation Detail |
| **3. Prompt Caching** | Claimed automatic caching has zero developer cost. | Prompt caching incurs cache-write costs (`cache_write_tokens`) and provides discounted cache reads (`cached_tokens`). | OpenAI Prompt Caching Guide | Implementation Detail |
| **4. Reasoning Context** | Treated `current_turn` and `all_turns` as `reasoning.context` enum values. | Reframed them as application-level strategies: reconstructed local context versus opaque encrypted-reasoning replay using the documented Responses include/output contract. | OpenAI Reasoning Models Guide | Implementation Detail |
| **5. Structured Outputs Syntax** | Used legacy `response_format` terminology. | Uses current Responses API `text.format` JSON Schema block with local Pydantic validation. | OpenAI Responses API Reference | Implementation Detail |
| **6. Streaming Event Names** | Used Chat Completions `response.content_part.delta`. | Uses Responses API events: `response.output_text.delta`, `response.output_text.done`, `response.completed`, `response.failed`. | OpenAI Responses API Streaming Guide | Implementation Detail |
| **7. Agents SDK Comparison** | Stated Agents SDK forces cloud sessions and acts as AgentJob runner. | Clarified Agents SDK supports client-side sessions; direct Responses API is preferred because Agent Col already owns state, routing, leases, and loops. | OpenAI Agents SDK Documentation | Architectural Detail |
| **8. Speech Catalog** | Used legacy `whisper-1` / `tts-1` / `gpt-4o-mini-audio`. | Updated catalog to `gpt-transcribe`, `gpt-live-transcribe`, `gpt-4o-mini-tts`, and `gpt-realtime-2.1`; preserved 2-phase edge adapter strategy. | OpenAI Audio Models Documentation | Implementation Detail |
| **9. Audio Retention** | Categorically claimed STT/TTS has "zero audio persistence." | Corrected to state audio retention is governed by account-level ZDR/MAM policies, not endpoint invocation alone. | OpenAI API Data Controls Guide | Implementation Detail |
| **10. Authentication Terms** | Conflated BYOK API key with user auth. | Explicitly separated Agent Col user authentication from OpenAI API authorization/billing. Noted ChatGPT sign-in eligibility requirements. | OpenAI Authentication & OAuth Docs | Architectural Detail |
| **11. Web Search Citations** | Assumed `snippet` is an annotation contract. | Requires verification against the pinned annotation schema and permits a bounded application-derived excerpt instead of depending on `snippet`. | OpenAI Web Search Tool Reference | Implementation Detail |
| **12. Reliability Concepts** | Used `finish_reason` for incomplete handling. | Uses Responses API `status`, `incomplete`, `incomplete_details`, and `response.failed` event objects. | OpenAI Responses API Errors Guide | Implementation Detail |
| **13. Local Usage Schema** | Used generic `prompt_tokens` / `completion_tokens`. | Updated to exact Responses usage fields: `input_tokens`, `output_tokens`, `cached_tokens`, `cache_write_tokens`, `reasoning_tokens`. | OpenAI Responses Usage Accounting Docs | Implementation Detail |
| **14. Current vs. Target State** | Diagrams presented PostgreSQL/OpenAI as if currently deployed. | Labels Firestore/Google as current source and PostgreSQL/OpenAI as target design. | Agent Col repository source | Architectural Detail |
| **15. Source Inventory** | Omitted active tool, context, repository, and cleanup dependencies and misclassified artifact feedback. | Expanded inventory and requires a production import scan before dependency retirement. | Agent Col repository source | Migration Safety |
