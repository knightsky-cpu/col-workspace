# Research Provider Compatibility Recheck Findings

## Purpose

This document records the corrected read-only findings from the August 27,
2026 Research tool failure review. It supersedes the narrow recommendation to
start with additional responder hardening. The next source-changing pass should
first determine whether the Research provider path itself is wrong or too
probabilistic for Agent Col's strict evidence contract.

## Corrected Verdict

The reported failure is a Research tool/provider evidence failure, not a
collaboration-state failure.

The immediate issue is not that Agent Col failed to keep conversation state.
The failed turns reached completed chat responses but had no completed
`google_search` action receipts and no citations. That points at the Research
provider boundary and final responder integration, not the working-state
collaboration path.

Adding more responder-side validation or another retry is not the best next
root-cause pass. It may improve containment, but it does not answer whether
the current ADK/Gemini Research implementation can reliably produce observable
Search execution and citations.

## Source-Backed Findings

### Current production topology

Current production wiring uses a server-routed expert service followed by a
responder-only Agent Col app:

- `main.py` constructs `ResearchExpertService.from_vertex_settings(...)`.
- `main.py` injects that service into `AgentColExpertExecutorV3`.
- `main.py` constructs the responder runtime from `create_responder_app(...)`.
- `agent_col_responder.py` creates a responder with governed memory and note
  tools only.
- `agent_col_responder.py` sets `sub_agents=[]`.

Therefore the active production failure is not literally Agent Col invoking a
Research `AgentTool`. The active path is:

```text
routing provider
  -> AgentColExpertExecutorV3
  -> isolated ResearchExpertService
  -> responder-only Agent Col
```

### Research still depends on ADK Google Search event conversion

`research_expert.py` configures Research as an ADK `Agent` with:

- `mode="single_turn"`;
- `tools=[google_search]`;
- `sub_agents=[]`;
- `include_contents="none"`;
- `temperature=0.0`;
- one retry for a final text response that has no grounding metadata, chunks,
  or supports.

`research_expert_service.py` runs the isolated ADK app through
`Runner.run_async(...)`, collects final `research_expert` events, and validates
only ADK `Event.grounding_metadata`.

This is bounded and defensible, but it inherits the core Google Search
limitation: the model decides whether Search is needed. A retry does not force
Search execution.

### Source already proved why direct provider compatibility matters

The prior Source compatibility report found that `google-adk==2.7.0` retained
`grounding_metadata` but dropped `url_context_metadata` when converting raw
GenAI responses into ADK `LlmResponse`. That made inline ADK Source unsuitable
for Agent Col's strict Source contract.

Current source reflects the accepted correction:

- `source_expert_service.py` uses direct `client.aio.chats.create(...)`.
- The retrieval stage enables only `types.Tool(url_context=types.UrlContext())`.
- `source_expert.py` reads raw `candidate.url_context_metadata`.
- `source_expert.py` reads raw `candidate.grounding_metadata`.
- The second Source stage is tool-free structured classification of already
  extracted grounded segments.

Research has not yet received the equivalent provider-compatibility proof.

### AgentTool concern is real but not sufficient

Official ADK documentation identifies `AgentTool` as the agent-as-tool surface
and documents `propagate_grounding_metadata=True` for preserving sub-agent
grounding metadata. The installed `google-adk==2.7.0` signature confirms:

```text
AgentTool(agent, skip_summarization=False, include_plugins=True,
          propagate_grounding_metadata=False)
```

However, installed ADK 2.7.0 also discourages direct `AgentTool` usage for
inline agents and recommends `mode="single_turn"` sub-agents attached through
`sub_agents=[...]`.

Because current production intentionally removed model-visible cognitive
experts from the responder, switching to `AgentTool` would be an architecture
change. It should not be the next implementation without a provider
compatibility spike showing that it improves metadata propagation and does not
reintroduce unwanted model-controlled routing.

### Direct ADK Interactions flip is not proven

Installed ADK 2.7.0 has an optional Interactions path in its Gemini wrapper,
but local source review showed the ADK conversion forwards tools and basic
generation config only. The reviewed local path did not show forwarding for
Interactions `tool_choice` or structured `response_format`.

Therefore simply switching ADK `Gemini(use_interactions_api=True)` is not a
proven Research fix.

The cleaner experiment is a direct Google GenAI Interactions compatibility
probe outside the production app.

## Official Documentation Findings

Current official Gemini and ADK documentation supports the need for a focused
provider spike:

- Google Search grounding says the model decides whether Search can improve
  the answer, then executes one or more Search queries if needed.
- Successful Interactions Google Search responses expose
  `google_search_call`, `google_search_result`, and model output annotations.
- Interactions API documents `tool_choice` values including `auto`, `any`,
  `none`, and `validated`.
- Structured outputs with built-in tools are documented for Gemini 3 series on
  the Interactions surface.
- URL Context and Google Search can be combined on the Interactions surface.
- ADK `AgentTool` grounding propagation is opt-in.
- ADK built-in tool limitations must be considered when mixing Search, Code
  Execution, and function tools in one agent.

The unresolved question is whether `tool_choice={"allowed_tools":{"mode":"any",
"tools":["google_search"]}}` actually forces the built-in `google_search` tool
for the current installed SDK, auth mode, and model. Official examples for
forced tool choice focus on custom function tools, so production design cannot
assume this works until tested.

## Automated Backend Testing Available

There are two useful automated layers.

### Cheap local tests

These tests do not make provider calls. They verify that local adapters,
validators, smoke harnesses, and turn-service contracts remain coherent:

```bash
venv/bin/pytest tests/test_research_expert.py \
  tests/test_research_expert_service.py \
  tests/test_source_expert_service.py \
  tests/test_smoke_test_source_expert.py \
  tests/test_tool_belt_live_e2e_check.py -q

venv/bin/pytest tests/test_agent_col_expert_executor_v3.py \
  tests/test_agent_col_responder_context_v3.py \
  tests/test_agent_col_turn_service.py::test_failed_expert_context_adds_no_cognitive_receipt -q

git diff --check
```

Observed result during recheck:

- `110 passed`, one existing ADK `BaseAgentConfig` deprecation warning.
- `20 passed`, one existing ADK `BaseAgentConfig` deprecation warning.
- `git diff --check` passed.

These tests cannot prove live Gemini Search execution.

### Metadata-only live provider spike

The next pass should create a metadata-only backend probe that avoids browser
and full application testing. It should spend a small, explicit number of
provider calls and report only content-safe diagnostics:

- status or error class;
- candidate count;
- Search call step count;
- Search result step count;
- model output step count;
- citation annotation count;
- `grounding_metadata` presence;
- grounding chunk count;
- grounding support count;
- normalized invalid-output reason where applicable.

It must not print raw user prompts, model answers, retrieved page bodies,
credentials, hidden context, project IDs, user IDs, or session IDs.

## Recommended Next Pass

Proceed with a Research provider compatibility spike before more production
hardening.

The spike should compare:

1. current ADK `ResearchExpertService`;
2. direct GenAI `models.generate_content(...)` with `google_search`;
3. direct GenAI `interactions.create(...)` with only `google_search`;
4. direct GenAI `interactions.create(...)` with `tool_choice` forcing
   `google_search`;
5. optionally, direct GenAI Interactions with `google_search` plus structured
   output.

Pass/fail interpretation:

- If Interactions forced tool choice reliably produces Search steps and
  citations, the next implementation should replace the current Research
  provider path with an app-owned direct Interactions service.
- If Interactions is rejected, skips Search, or returns no usable citations,
  first-party Gemini Search remains probabilistic for this use case and more
  local validation/retry is not a real fix.
- If ADK drops metadata that direct GenAI preserves, Research should follow
  the same direct-provider pattern as Source.
- If all paths are probabilistic, Agent Col must keep fail-closed behavior and
  either ask for a supplied URL or adopt a different search provider in a
  separately approved pass.

## Exclusions

This recheck does not approve:

- production Research refactoring;
- responder hardening;
- additional retries;
- adding third-party search;
- changing credentials;
- broad end-to-end application testing as the first diagnostic step.

The next action is the bounded metadata-only Research provider compatibility
spike.
