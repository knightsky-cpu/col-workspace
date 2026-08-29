# ADK Gemini Tool Surface Mismatch Handoff

Date: 2026-08-27

Purpose: preserve the ADK/Gemini tool-call hypothesis, official-documentation contrast, local source evidence, and current solution direction so a fresh session does not burn context rediscovering it.

## Bottom Line

The initial hypothesis was credible: Agent Col's failures were related to Gemini/ADK tool surfaces and metadata propagation, not just collaboration-state handling.

The current evidence does not support an immediate AgentTool or Interactions migration as the smallest fix.

The current evidence supports this sequence instead:

1. Preserve failure reasons across service/executor/responder boundaries.
2. Reduce local normalization brittleness for valid provider-grounded output.
3. Add official-source policy enforcement for explicit official-documentation requests.
4. Revisit AgentTool only if a later source-backed pass proves the current server-routed Research service cannot satisfy citation/tool requirements.

## Official Documentation Signals

### ADK AgentTool grounding propagation

Official ADK docs describe `AgentTool(..., propagate_grounding_metadata=True)` as the way to forward grounding metadata such as Google Search citations from a specialist search agent to a parent agent's session state.

Reference:

- https://adk.dev/tools-custom/function-tools/

Local installed signature confirms the setting exists and defaults to `False`:

```text
AgentTool(agent, skip_summarization=False, *, include_plugins=True, propagate_grounding_metadata=False)
```

Implication:

- If Agent Col later moves to an AgentTool/sub-agent topology for Research, failing to set `propagate_grounding_metadata=True` would likely lose citation metadata.
- This does not prove the current server-routed service path is wrong, because the current production path does not expose Research as an AgentTool.

### Google Search grounding is model-managed

ADK and Gemini docs describe Google Search grounding as a tool available to the model, not a deterministic guarantee that every request will call Search. Adding the tool means the model can use Search when it decides Search improves the answer.

References:

- https://adk.dev/grounding/google_search_grounding/
- https://ai.google.dev/gemini-api/docs/google-search

Implication:

- Agent Col cannot assume `tools=[google_search]` always means Search ran.
- Local normalization still needs to inspect returned grounding metadata and fail closed when required metadata is missing.
- Adding retries can mask symptoms but does not fix the root tool-surface uncertainty.

### Gemini Interactions would be useful, but is unavailable here

Gemini Interactions docs describe step visibility and tool-use flows that would be useful for diagnosing Search calls and tool choice.

References:

- https://ai.google.dev/api/interactions-api-v1
- https://ai.google.dev/gemini-api/docs/function-calling

Live local evidence from `research_provider_compatibility_check.py` showed:

```text
interactions-basic-3.6: BadRequestError api_status=400
interactions-google-search-3.6: BadRequestError api_status=400
interactions-basic-3.7: BadRequestError api_status=400
interactions-google-search-3.7: BadRequestError api_status=400
interactions-forced-extra-body-google-search-3.7: BadRequestError api_status=400
```

Additional diagnostic output showed:

```text
Unsupported model interaction: gemini-3.6-flash
Unsupported model interaction: gemini-3.7-flash
Unsupported model interaction: models/gemini-3.7-flash
Unknown parameter 'tool_choice'
```

Implication:

- Interactions failed before Google Search mattered.
- The configured Vertex/Enterprise backend currently does not support the tested Interactions surface for these model names.
- A production Interactions migration would first require a provider/backend compatibility change, not just a code refactor.

## Current Production Topology

Current production path is server-routed Research service, not parent-agent AgentTool delegation.

Source evidence:

- `main.py` wires `ResearchExpertService.from_vertex_settings(...)`.
- `main.py` wires `create_responder_app(...)`.
- `agent_col_responder.py` exposes memory/note FunctionTools to the responder, not Research as a responder-visible tool.
- `agent_col_expert_executor_v3.py` calls `service.research(request)` directly for Research.

Current executor source after the failure-reason pass:

```python
try:
    result = await service.research(request)
except ResearchExpertServiceError as exc:
    result = ResearchExpertResult(
        status=exc.status,
        invalid_output_reason=_invalid_output_reason_value(exc),
    )
```

This topology is intentionally not the ADK AgentTool citation-propagation pattern. That is a mismatch with the official AgentTool citation-propagation example, but not automatically a defect because Agent Col performs its own server-side normalization and citation receipt creation.

## Research Provider Surfaces Tested

The compatibility probe tests these surfaces:

- ADK Research Service.
- Direct `models.generate_content` with `google_search`.
- Interactions basic no-tool calls.
- Interactions with `google_search`.
- Interactions with forced `tool_choice` through `extra_body`.

Source evidence:

- `research_provider_compatibility_check.py` lines around `run_adk_research_service_probe`.
- `research_provider_compatibility_check.py` lines around `run_generate_content_probe`.
- `research_provider_compatibility_check.py` lines around `run_interactions_probe`.
- `research_provider_compatibility_check.py` lines around `run_interactions_forced_extra_body_probe`.

Most recent live result class:

```text
ADK Research Service: completed with grounding metadata
Direct generate_content + google_search: completed with grounding metadata
Interactions: HTTP 400 for basic/search/forced variants
```

Implication:

- The provider can return grounding metadata through generateContent-era surfaces.
- The provider/backend cannot currently run the tested Interactions surface.
- The current smallest fixes should stay on the working generateContent-era path.

## Mismatches And Risks To Preserve

### Mismatch 1: Official docs show AgentTool propagation; production does not use AgentTool

Official docs:

- `AgentTool(..., propagate_grounding_metadata=True)` preserves specialist grounding metadata.

Local production:

- Research is executed server-side through `ResearchExpertService`.
- The responder never calls Research as an ADK tool.

Risk:

- If future work converts Research to AgentTool without `propagate_grounding_metadata=True`, citations may be lost.

Current solution:

- Do not migrate yet.
- Preserve and normalize citations server-side.
- Document AgentTool as a future topology option only after provider evidence justifies it.

### Mismatch 2: Official docs show Interactions step visibility; configured backend rejects Interactions

Official docs:

- Interactions exposes steps and is attractive for tool-call observability.

Local live result:

- Basic Interactions requests return HTTP 400.
- Search Interactions requests return HTTP 400.
- Forced `tool_choice` through top-level kwargs errors locally; through `extra_body` returns HTTP 400 unknown parameter.

Risk:

- A migration based only on docs would burn implementation time and still fail against the current backend.

Current solution:

- Keep Interactions out of production.
- Retain `research_provider_compatibility_check.py` as the backend compatibility gate before any future Interactions work.

### Mismatch 3: Official-documentation user intent is stricter than current public-source validation

Official docs requests from the user mean "use official project/vendor documentation", not "any public page about the topic."

Local production:

- Research validates public grounding sources.
- It does not currently enforce request-specific official domains.

Manual result evidence:

- OpenAI official-docs prompt included non-official domains in the citation/action list.
- Omarchy official-install prompt included social/video/blog/vendor domains.
- Python official-release prompt succeeded on retry with `python.org`, which is the desired official-source shape.

Risk:

- Agent Col can produce a cited answer that is technically grounded but does not satisfy the official-source requirement.

Current solution:

- Next pass should add request-scoped official-source policy enforcement.
- Do not solve this with more retries or generic stricter validation.

## Recommended Next Implementation

Implement:

- `docs/superpowers/plans/2026-08-27-research-official-source-policy-plan.md`

Do not implement:

- AgentTool migration.
- Interactions migration.
- new provider backend.
- broad citation ranking/refactoring.
- another validation layer around invalid output.

## Verification Commands To Reuse

For Research normalization and provider-surface safety:

```bash
venv/bin/pytest tests/test_research_expert.py tests/test_research_expert_service.py tests/test_research_provider_compatibility_check.py -q
git diff --check
venv/bin/python research_provider_compatibility_check.py
```

For failure handoff and responder context:

```bash
venv/bin/pytest tests/test_expert_contracts.py tests/test_agent_col_expert_executor_v3.py tests/test_agent_col_responder_context_v3.py tests/test_agent_col_turn_service.py::test_failed_expert_context_adds_no_cognitive_receipt -q
```

## Stop Conditions For A Fresh Session

Stop and ask for approval if source review shows any of these:

- Research is now wired as an AgentTool in production.
- The configured backend now supports Interactions successfully.
- Manual evidence shows official-source-only requests already reject mixed unofficial sources.
- The uncommitted grounded-claim normalization work was reverted or materially changed before implementation review.

## Rollback

If this handoff checkpoint is the latest commit and needs to be removed:

```bash
git revert HEAD
```

Check first:

```bash
git log -1 --oneline
```
