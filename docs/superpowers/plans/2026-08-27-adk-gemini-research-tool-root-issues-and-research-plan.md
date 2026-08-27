# ADK/Gemini Research Tool Root Issues and Research Plan

## Purpose

This document captures the current evidence around Agent Col's failed research-tool behavior, the likely root issue clusters, the official Google documentation that must be reviewed in depth, and the local source files that must be compared against those docs before another source-changing implementation pass.

The immediate goal is not to patch code. The goal is to make the next implementation pass source-backed rather than speculative.

## Current Observed Failure

The user ran an end-to-end conversational flow in a new workspace:

- `project_id`: `project--eb3e1d02bb1c9e01c59957622341f107--end-to-end`
- `session_id`: `session--109ad178-eb1e-4572-b43e-6d81d906f7bf`

Two prompts explicitly required current or official-source verification:

1. `What are the current official OpenAI API model names and recommended Python SDK usage for FastAPI as of today, August 27, 2026? Please verify against the official OpenAI documentation before answering.`
2. `can you check the official documentation for installing omarchy on my linux machine`

Agent Col responded that the research lookup failed with `invalid_output`, then continued with general unsourced fallback guidance.

## Behavioral Evidence From Live Inspection

Read-only Firestore inspection found:

- Both reported research turns completed with saved model responses.
- Both turns had `status=completed`.
- Both turns had `completed_at` timestamps.
- Both turns had persisted model message IDs.
- Both turns had empty `actions`.
- Both turns had empty `citations`.

This matters because the earlier accepted fail-safe pass targeted a different failure mode: unexpected `/api/chat` exceptions leaving turns stuck in `in_progress`. The new end-to-end failure did not reproduce that symptom.

## Pass Verdict for Previous Fail-Safe Boundary

The previous pass succeeds for its intended error boundary.

Source evidence:

- `main.py` catches unexpected exceptions after `turn_service.run_turn`, logs only the exception type, releases the active chat-turn claim, and raises a bounded `500`.
- `tests/test_main.py::test_chat_releases_claim_after_unexpected_turn_exception` verifies claim release, no completion save, and bounded error output.
- Focused verification before checkpoint passed:
  - `venv/bin/pytest tests/test_main.py::test_chat_releases_claim_after_unexpected_turn_exception tests/test_main.py::test_chat_releases_claim_after_turn_service_failure tests/test_main.py::test_chat_does_not_update_working_state_when_completion_fails -q`
  - Result: `7 passed`

The current failure is therefore a new research/expert reliability boundary, not evidence that the stuck-turn fail-safe failed.

## Root Issue Cluster 1: Research Expert Fails Closed on Missing or Unmappable Grounding

### Local Source Evidence

`research_expert.py` defines the Research Expert as a bounded Google Search specialist:

- `RESEARCH_EXPERT_INSTRUCTION` requires Google Search grounding.
- The instruction requires every factual sentence to be supported by Google Search grounding.
- `create_research_expert(...)` configures:
  - `model=Gemini(...)`
  - `tools=[google_search]`
  - `include_contents="none"`
  - `temperature=0.0`
  - isolated transfer settings

`research_expert.py` also rejects outputs when local validation cannot prove grounding:

- missing response text;
- missing grounding metadata;
- missing grounding chunks;
- missing grounding supports;
- no valid public sources;
- no mappable grounding claims;
- grounded claim without source.

`research_expert_service.py` converts rejected normalized output into `ResearchExpertServiceError(ExpertStatus.INVALID_OUTPUT)` with a content-safe invalid-output reason.

### Interpretation

This failure status is expected defensive behavior if the provider returns output that cannot be locally validated. It is not automatically a bug by itself.

The bug is that the downstream system currently turns this failed expert result into a user-facing response that continues with non-source-backed fallback content after the user explicitly requested source verification.

## Root Issue Cluster 2: Failure Detail Is Lost Before Responder Handoff

### Local Source Evidence

`research_expert_service.py` preserves a content-safe invalid-output reason on `ResearchExpertServiceError`.

`agent_col_expert_executor_v3.py` catches `ResearchExpertServiceError`, but currently maps it to:

```python
ResearchExpertResult(status=exc.status)
```

That drops `exc.invalid_output_reason`.

`build_research_receipts(...)` returns empty receipts when the result is not completed or lacks payload. The observed Firestore turns match this: empty citations and empty actions.

### Interpretation

The responder receives only a broad failed expert status, not enough structured diagnostic detail to distinguish:

- no final event;
- no response text;
- no grounding metadata;
- no grounding chunks;
- no mappable grounding supports;
- service unavailable;
- timeout.

This weakens both user-facing behavior and future debugging.

## Root Issue Cluster 3: Responder Policy Is Directionally Correct but Not Enforced Strongly Enough

### Local Source Evidence

`agent_col_responder.py` says:

- the server-validated routing context is authoritative;
- for Source/Research/Computation, integrate only completed validated results;
- if context reports a failed expert, explain the limitation or ask how to proceed;
- do not make unsupported current claims.

### Behavioral Evidence

In the live end-to-end session, Agent Col did explain that the lookup failed, but then continued with generic guidance after explicit official-documentation verification failed.

### Interpretation

The responder instruction is not strict enough for explicit verification requests. We need a stronger boundary:

- If the user explicitly asks to verify/check official/current documentation and the expert fails, the final answer should not continue with general factual fallback content.
- It should clearly state that verification failed and offer next actions: retry, provide a URL, or proceed explicitly without source verification.

## Root Issue Cluster 4: Current Research Path Is Not Actually Agent Col Calling an AgentTool

### Local Source Evidence

`agent_col_responder.py` creates Agent Col with no cognitive expert tools:

- It conditionally exposes memory and collaborative-note tools.
- It does not expose Research Expert, Source Expert, or Computation Expert as model-visible tools.
- `sub_agents=[]`.

`research_expert_service.py` constructs a separate one-node workflow:

- `Workflow(name=RESEARCH_EXPERT_WORKFLOW_NAME, edges=[("START", research_expert)])`
- `App(name=RESEARCH_EXPERT_APP_NAME, root_agent=workflow)`
- `InMemorySessionService()`

`agent_col_turn_service.py` performs server-side routing, executes the selected expert, renders a server-validated responder context, and then calls the responder.

### Interpretation

The current system is server-routed expert execution, not literal "Agent Col has a Research AgentTool and decides to call it."

This distinction matters:

- Agent Col does not directly decide to call Research Expert as an ADK `AgentTool`.
- The routing provider decides a route.
- The Research Expert's own Gemini model decides whether to invoke `google_search` inside its isolated run.

The failed `invalid_output` therefore likely occurred inside the Research Expert's Gemini/Search grounding path, not in Agent Col's parent responder tool-calling path.

## Root Issue Cluster 5: Official ADK AgentTool and Grounding Semantics May Point to a Better Topology

### Official Documentation Findings

Relevant official links:

- ADK Function Tools and Agent-as-a-Tool:
  - https://adk.dev/tools-custom/function-tools/
- ADK Google Search Grounding:
  - https://adk.dev/grounding/google_search_grounding/
- ADK Tool Limitations:
  - https://adk.dev/tools/limitations/
- ADK Runtime Event Loop:
  - https://adk.dev/runtime/event-loop/
- Google Gen AI Python SDK:
  - https://googleapis.github.io/python-genai/
- Gemini API Tools:
  - https://ai.google.dev/gemini-api/docs/tools
- Vertex/Gemini Enterprise function calling:
  - https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tools/function-calling

Official ADK docs state that:

- Google Search Grounding gives agents access to real-time public web information.
- The agent's underlying LLM decides whether to invoke `google_search`.
- Grounded responses should include source URLs and `groundingMetadata`.
- `AgentTool` is the official wrapper for using one agent as a tool of another agent.
- With Agent-as-a-Tool, the child agent's answer is passed back to the parent, and the parent retains user-facing control.
- `AgentTool` supports customization such as `skip_summarization`.
- The installed local `google-adk==2.7.0` `AgentTool` signature also includes `propagate_grounding_metadata=False` by default.

Official ADK tool limitations docs also show `AgentTool(agent=search_agent)` as a workaround pattern for using built-in tools through separate agents. This is relevant if the architecture moves toward model-visible expert tools.

### Interpretation

There are two plausible architecture paths:

1. Keep the current server-routed isolated Research Expert path and harden validation/failure handling.
2. Refactor toward a documented ADK `AgentTool` topology for search specialists, paying special attention to `propagate_grounding_metadata`.

The second path should not be adopted until we verify whether it improves grounding metadata propagation and whether it reintroduces unwanted model autonomy into tool selection.

## Root Issue Cluster 6: Gemini Model Decision-Making Is Part of the Research Failure Surface

Official docs say the underlying LLM determines when to invoke Google Search. That means even when the server routes to Research Expert, there is still a model-mediated decision inside the Research Expert run:

- The Research Expert receives a prompt.
- Its Gemini model decides whether and how to use `google_search`.
- ADK/Gemini returns final text and grounding metadata if grounding succeeds.
- The application validates grounding metadata before creating citations.

If Gemini answers from model knowledge instead of invoking Search, local validation can correctly return `invalid_output`.

This is not necessarily an application bug. It may be a model/tool-call reliability limitation that needs mitigation through:

- stronger Research Expert instruction;
- function/tool-calling mode configuration if available through ADK;
- direct Google Search grounding requests outside ADK;
- retry with a stricter prompt when the first response is ungrounded;
- topology changes that better propagate grounding metadata.

## Source Files Requiring Detailed Review

### Routing and Turn Lifecycle

- `agent_col_turn_service.py`
  - Review server-side routing, expert execution, timeout handling, responder-context handoff, and result merging.
  - Confirm where failed expert statuses become model-visible context.
  - Confirm whether route/expert diagnostic metadata should be persisted on turn records.

- `agent_col_routing_provider_v4.py`
  - Review whether explicit "official docs/current/as of today/verify" prompts reliably route to Research.
  - Confirm whether broader assumption/currentness detection should route before responder-only behavior.

- `agent_col_routing_v3.py`
  - Review route schema and whether Research intent has enough fields to express official-source constraints.

- `agent_col_expert_executor_v3.py`
  - Review exception-to-result mapping.
  - Preserve content-safe failure reasons from services.
  - Verify Source/Research/Computation/Requirements parity.

### Research Expert

- `research_expert.py`
  - Review Research Expert instruction.
  - Review `tools=[google_search]`.
  - Review retry logic in `BoundedResearchAgent`.
  - Review `include_contents="none"`.
  - Review grounding metadata normalization.
  - Review whether strict sentence/support mapping is too brittle for current ADK/Gemini output.

- `research_expert_service.py`
  - Review isolated workflow construction.
  - Review event capture: only final events from `research_expert`.
  - Review `final_events[0].model_copy(update={"output": None})`; this intentionally discards structured output before normalization, and must be rechecked against current ADK event semantics.
  - Review whether service logs enough content-safe diagnostic data.

- `tests/test_research_expert.py`
  - Review current assumptions around grounded event normalization.
  - Add or update tests for current ADK metadata shapes if docs/source inspection reveals a mismatch.

- `tests/test_research_expert_service.py`
  - Review current service failure tests.
  - Add tests for preserving invalid-output reasons and classifying no-search vs malformed-search cases.

### Source Expert

- `source_expert.py`
  - Review similar grounding metadata extraction and validation.
  - Determine whether Source failures carry content-safe invalid-output reasons.

- `source_expert_service.py`
  - Review whether Source service loses detailed failure reasons similarly.

### Responder Boundary

- `agent_col_responder.py`
  - Strengthen explicit verification failure behavior.
  - Ensure failed Source/Research routes cannot produce generic factual fallback answers.

- `agent_col_responder_context_v3.py`
  - Add explicit model-context wording for failed expert results:
    - no validated citations;
    - no source-backed facts available;
    - ask user to retry/provide URL/proceed without verification.

- `tests/test_agent_col_responder_context_v3.py`
  - Add regression tests for failed Research context rendering.

- `tests/test_agent_col_turn_service.py`
  - Add regression tests around failed Research context handoff, empty citations, and non-stuck completion.

### ADK/Gemini Configuration

- `vertex_config.py`
  - Review client configuration, API version, project/location, and whether enterprise/Vertex settings match official current SDK docs.

- `requirements.txt`
  - Current pins:
    - `google-adk==2.7.0`
    - `google-genai==2.18.1`
  - Compare installed package behavior against current official docs.

- Installed package source under `venv/lib/python3.14/site-packages/google/adk/...`
  - Inspect `google.adk.tools.agent_tool.AgentTool`.
  - Inspect `google.adk.tools.google_search_tool.GoogleSearchTool`.
  - Inspect `google.adk.models.google_llm.Gemini`.
  - Inspect ADK event fields for grounding metadata propagation.

## Specific Implementation Changes Likely Needed

### Likely Change 1: Preserve content-safe expert failure reasons

Preserve `invalid_output_reason` from `ResearchExpertServiceError` into `ResearchExpertResult` or a parallel safe diagnostic field carried by `AgentColResponderContextV3`.

Why:

- The service already computes a safe reason.
- The executor currently discards it.
- Without it, the responder and persisted diagnostics cannot distinguish model no-search behavior from metadata validation mismatch.

### Likely Change 2: Make explicit verification failures fail closed at responder level

When route is Source or Research and expert status is not `completed`, the responder context should instruct:

- no source-backed/current facts are available;
- do not continue with general factual fallback for explicit verification requests;
- ask whether to retry, use a provided URL, or proceed without source verification.

Why:

- Live behavior shows current instruction is insufficient.
- The user explicitly asked for official documentation verification.
- Generic fallback content undermines the source-backed collaboration goal.

### Likely Change 3: Add structured diagnostic persistence for expert execution

Persist content-safe expert status and reason on turn records or a bounded internal diagnostic surface.

Why:

- Current Firestore turn records show completed turns with empty actions/citations but do not show why Research failed.
- Future debugging should not rely on model prose saying `invalid_output`.

### Likely Change 4: Re-evaluate Research Expert topology

Compare three possible patterns:

1. Current server-routed isolated Research Expert workflow.
2. Documented ADK `AgentTool(agent=search_agent, propagate_grounding_metadata=True)` topology.
3. Direct Gemini/Google Search grounding call outside ADK for research-only requests.

Why:

- Official docs identify `AgentTool` as the agent-as-tool pattern.
- Official docs say grounded responses include `groundingMetadata`.
- Current source manually normalizes ADK final events and may be losing or misinterpreting metadata.

### Likely Change 5: Add a targeted retry or forced-grounding mitigation

The current `BoundedResearchAgent` retries once only when it detects a final response with text but no grounding metadata/chunks/supports.

Need to review:

- Whether it retries on the right event.
- Whether the retry changes prompt/tool-call pressure enough.
- Whether ADK/Gemini exposes a config to require or bias tool use for Search.

Why:

- Official docs state the LLM decides when to search.
- Explicit official-doc requests should not depend solely on a weak implicit search decision.

## Further Research Plan

### Phase 1: Official Documentation Deep Review

Review these docs in detail and capture exact implementation implications:

- ADK Function Tools and Agent-as-a-Tool:
  - https://adk.dev/tools-custom/function-tools/
  - Focus: `AgentTool`, `skip_summarization`, `propagate_grounding_metadata`, child/parent responsibility.

- ADK Google Search Grounding:
  - https://adk.dev/grounding/google_search_grounding/
  - Focus: metadata shape, source attribution, when the model decides to search.

- ADK Tool Limitations:
  - https://adk.dev/tools/limitations/
  - Focus: built-in tool restrictions, AgentTool workaround, `bypass_multi_tools_limit`.

- ADK Runtime Event Loop:
  - https://adk.dev/runtime/event-loop/
  - Focus: how events are yielded, final responses, tool results, state/action commit timing.

- Google Gen AI Python SDK:
  - https://googleapis.github.io/python-genai/
  - Focus: automatic function calling, manual function calling, async chat vs `generate_content`, grounding metadata fields.

- Gemini API Tools:
  - https://ai.google.dev/gemini-api/docs/tools
  - Focus: built-in tools vs custom tools, model-owned tool decisions, structured outputs with tools.

- Vertex/Gemini Enterprise function calling:
  - https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tools/function-calling
  - Focus: function-calling model support, tool configuration, API limitations.

### Phase 2: Installed Package Source Review

Review installed ADK/GenAI code, because package behavior can differ from docs:

- `venv/lib/python3.14/site-packages/google/adk/tools/agent_tool.py`
- `venv/lib/python3.14/site-packages/google/adk/tools/google_search_tool.py`
- `venv/lib/python3.14/site-packages/google/adk/models/google_llm.py`
- `venv/lib/python3.14/site-packages/google/adk/models/llm_request.py`
- `venv/lib/python3.14/site-packages/google/adk/flows/llm_flows/*`
- `venv/lib/python3.14/site-packages/google/genai/types.py`
- `venv/lib/python3.14/site-packages/google/genai/models.py`

Questions to answer:

- Where is `grounding_metadata` attached to ADK events?
- Does `AgentTool(..., propagate_grounding_metadata=True)` preserve child grounding metadata into parent context?
- Does `google_search` support forcing tool use or only model-decided use?
- Does the current `Gemini` wrapper use `generate_content`, chat APIs, or interactions API?
- Is the warning about direct AFC usage relevant to ADK's internal call path or only direct SDK usage?

### Phase 3: Local Source Comparison

Compare docs/package behavior to:

- `research_expert.py`
- `research_expert_service.py`
- `agent_col_expert_executor_v3.py`
- `agent_col_responder_context_v3.py`
- `agent_col_responder.py`
- `agent_col_turn_service.py`
- `vertex_config.py`

Questions to answer:

- Is current isolated workflow supported and appropriate for Google Search grounding?
- Does `final_events[0].model_copy(update={"output": None})` discard useful structured data?
- Is normalization too strict for real ADK grounding metadata?
- Should failed research result details be persisted before responder generation?
- Should the responder be prevented from answering at all when source-backed verification fails?

### Phase 4: Bounded Implementation Proposal

After the research phases, propose one bounded source-changing pass.

The likely first pass remains:

- preserve invalid-output reasons;
- strengthen responder failure behavior;
- add focused tests.

The topology change should be a separate pass unless source review proves the current topology is the direct root cause.

## Current Recommendation

Do not jump straight to an AgentTool refactor.

First, preserve failure reasons and make failed verification fail closed in the responder. This improves user-visible reliability regardless of whether the eventual research backend remains isolated, moves to `AgentTool`, or becomes a direct Gemini/Search grounding call.

Then perform the deeper ADK/Gemini topology review before changing architecture.
