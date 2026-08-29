# Research Official Source Evidence Findings

Date: 2026-08-27

Purpose: document official documentation evidence and local source evidence for the hypothesis that official-documentation failures are caused by accepted mixed Google Search grounding sources, not by missing Research tool execution or fabricated responder citations.

## Scope

This was a read-only research and source-check pass, except for this documentation artifact and the plan cross-reference that points to it.

Questions checked:

1. Does official Gemini/ADK documentation guarantee that Google Search grounding will use only official/vendor sources when the prompt asks for official documentation?
2. Does Agent Col currently preserve provider grounding metadata and validate public citations?
3. Does Agent Col currently have a request-scoped official-source policy that can reject mixed public sources?
4. Does the evidence justify stricter source-policy implementation before any AgentTool or Interactions migration?

## Official Documentation Evidence

### Gemini Google Search grounding

Source: https://ai.google.dev/gemini-api/docs/google-search

Findings:

- Gemini Google Search grounding connects the model to current web content and returns citations for grounded responses.
- The documented workflow says the model analyzes the prompt, decides if Google Search can improve the answer, generates one or more search queries if needed, processes search results, and returns citations/annotations.
- The official example itself shows a grounded answer with citations from more than one domain, including a news site and an official sports-domain source. That is evidence that Search grounding is not an official-domain-only retrieval mechanism.
- The docs describe citation metadata and search-call/result steps, but this page does not document a source-domain allowlist for plain Google Search grounding.

Interpretation:

- The tool can work correctly while still returning mixed public sources.
- Application code must inspect and enforce source suitability when the user asks for official documentation, official install instructions, official release data, or equivalent authoritative-source constraints.

### ADK Google Search grounding

Source: https://adk.dev/grounding/google_search_grounding/

Findings:

- ADK documents Google Search grounding as a tool added to an agent.
- ADK says the agent automatically decides when to search.
- ADK's data-flow description says the grounding service sends one or more queries to Google Search, retrieves relevant pages/snippets, injects them into model context, and returns source URLs plus `groundingMetadata`.
- ADK does not describe an official-domain filter for the `google_search` tool.

Interpretation:

- ADK grounding metadata is the right boundary to validate.
- The source-quality requirement is application-specific. For official-doc requests, accepting any public source that appears in grounding metadata is too weak.

### ADK AgentTool grounding propagation

Source: https://adk.dev/tools-custom/function-tools/

Findings:

- ADK documents `AgentTool(..., propagate_grounding_metadata=True)` for preserving citations from a specialist search agent to the parent agent's session state.
- The setting matters only for an AgentTool/sub-agent topology.
- This confirms a future migration would need explicit grounding propagation, but it does not prove the current server-routed Research service is defective.

Interpretation:

- AgentTool migration is not the next smallest source-backed fix for the observed problem.
- If Research is later converted into an AgentTool, the migration must include grounding propagation tests.

### Gemini Interactions API

Sources:

- https://ai.google.dev/gemini-api/docs/google-search
- https://ai.google.dev/api/interactions-api

Findings:

- Current Gemini docs show Interactions examples for `tools=[{"type": "google_search"}]`.
- The Interactions API includes tool-choice configuration and reports grounding tool counts such as `google_search`.
- Interactions would be useful for step-level observability, but prior local compatibility evidence in this repo shows the configured backend returned HTTP 400 for the tested Interactions surfaces.

Interpretation:

- Interactions may be a future observability/backend option, but a production migration is not justified until the local provider compatibility gate passes.

## Source-Backed Findings

### Current Research agent uses Google Search

Source: `research_expert.py:369-397`

Evidence:

- `create_research_expert()` constructs a bounded single-turn Research agent.
- The agent uses `model=Gemini(...)`.
- The agent is configured with `tools=[google_search]`.
- The instruction says factual sentences must be supported by Google Search grounding, while the application validates grounding and attaches citations separately.

Conclusion:

- The current Research tool surface is configured to use Google Search grounding.
- The observed mixed-source issue is not explained by Research lacking the Google Search tool.

### Current service path is server-routed, not AgentTool delegation

Sources:

- `main.py:918-935`
- `agent_col_expert_executor_v3.py:255-283`
- `agent_col_responder.py:19-36`

Evidence:

- `main.py` builds `ResearchExpertService.from_vertex_settings(...)` and injects it into `AgentColExpertExecutorV3`.
- `_execute_research()` builds a `ResearchExpertInput` and calls `service.research(request)` directly.
- The responder instruction treats server-validated routing context and application-derived receipts as authoritative; it is not the component that calls Research as a tool.

Conclusion:

- Agent Col's production Research path does not use ADK `AgentTool` for Research.
- AgentTool grounding propagation is relevant future topology knowledge, not the current root boundary.

### Current Research input has no source policy

Sources:

- `research_expert.py:115-123`
- `agent_col_expert_executor_v3.py:265-269`
- `agent_col_routing_v3.py:213-230`

Evidence:

- `ResearchExpertInput` currently contains only `question`, `objective`, and `constraints`.
- `_execute_research()` passes only those fields from `directive.research_intent`.
- The routing directive has a `research_intent` object for a Research route, but no first-class source-policy field.

Conclusion:

- Official-source intent may exist as plain text in question/objective/constraints, but it is not converted into a typed policy.
- Normalization cannot enforce official-domain requirements because no such policy reaches it.

### Current normalization validates public grounded sources, not official domains

Sources:

- `research_expert.py:174-198`
- `research_expert.py:428-468`
- `research_expert.py:620-728`

Evidence:

- `ProviderSource.validate_public_uri()` rejects credentials, localhost, non-public IPs, and internal/test/local/example-style hosts.
- `_extract_provider_source_index()` extracts web URIs from `grounding_chunks`, validates that they are public, deduplicates them, and assigns `source-*` IDs.
- `diagnose_grounded_research_text()` requires response text, grounding metadata, chunks, supports, mappable claims, source IDs, and bounded source counts.
- The current implementation does not compare source hostnames or URL paths against an official-domain allowlist.

Conclusion:

- Agent Col is enforcing "public and grounded," not "official for this request."
- This exactly matches the manual failure pattern: valid-looking grounded answers can include unofficial domains for an official-doc request.

### Current receipts are generated from normalized provider sources

Source: `research_expert.py:400-417`

Evidence:

- `build_research_receipts()` emits one `google_search` action receipt and citation receipts derived from `result.payload.sources`.
- If normalization accepts mixed public sources, the responder receives those accepted citations as authoritative receipts.

Conclusion:

- The responder is not inventing the citation list in this path.
- The better fix is to reject or classify unacceptable sources before receipts are built.

### Prior compatibility probe supports staying on the current provider surface

Source: `research_provider_compatibility_check.py:149-280`

Evidence:

- The probe checks ADK Research Service, direct `generate_content` with `google_search`, Interactions with and without `google_search`, and a forced Interactions request shape.
- The probe records metadata-only observations such as grounding metadata presence, grounding chunk/support counts, Interactions step types, Google Search call/result counts, and citation annotation counts.

Conclusion:

- The repo already has the right compatibility gate for deciding whether a provider topology change is warranted.
- The next implementation should not remove or bypass this probe.

## Hypothesis Assessment

Hypothesis:

> The official-doc failures are primarily a Google Search grounding result-selection/source-acceptance issue, not a missing tool call or responder fabrication issue.

Assessment: supported by current evidence.

Why:

- Official docs describe Google Search grounding as model/search-managed and citation-returning, not as domain-constrained retrieval.
- Local source shows Research is configured with Google Search.
- Local source shows citations are derived from validated provider metadata.
- Local source shows validation only checks public/grounded/bounded source structure.
- Manual prompt evidence showed completed grounded answers with mixed official and unofficial sources.

What this does not prove:

- It does not prove Google Search always ran for every failed manual attempt.
- It does not prove every unofficial citation was attached to a retained claim rather than appearing in a broader action/citation list.
- It does not prove prompt wording can never improve source selection.
- It does not prove Interactions would fail forever; it only preserves the current local compatibility result as a gate.

## Root Cause Statement

Supported root cause:

Agent Col currently treats any locally valid public grounded source as acceptable Research evidence, even when the user asked for official documentation. Google Search grounding can return mixed public sources, and the Research normalization layer has no request-scoped official-source policy to reject those mixed sources before building findings and citation receipts.

## Implementation Evidence Implications

The existing official-source policy plan is directionally correct, with these evidence-backed constraints:

1. Add `ResearchSourcePolicy` as typed request data, not as a responder prompt-only instruction.
2. Derive the policy at the executor/routing boundary from explicit official-source wording.
3. Enforce the policy during normalization, before receipts are built.
4. Use URL parsing and hostname/path matching; do not use substring matching.
5. Reject mixed official/unofficial cited sources for retained claims instead of silently dropping unofficial citations.
6. Preserve broad public research behavior when no official-source policy is present.
7. Do not migrate to AgentTool or Interactions in this pass.

## Recommended Additional Test Targets

In addition to the existing plan tests:

1. Unit-test that a policy allows subdomains of an allowed domain, such as `platform.openai.com` for `openai.com`.
2. Unit-test that a path-scoped allowed entry, such as `github.com/openai`, does not allow unrelated `github.com/other-owner/...` URLs.
3. Unit-test that broad research with no policy still accepts mixed public sources.
4. Service-test that `ResearchExpertService.research()` passes the policy into final-event normalization.
5. Executor-test that official-source wording creates a policy, while "use public evidence" does not.

## Stop Conditions Before Implementation

Stop and revise the implementation plan if source review shows any of these before editing:

- Research has been converted to AgentTool in production.
- The local Interactions compatibility probe starts passing and returns richer source-step metadata that materially changes the smallest fix.
- Official-source-only manual prompts start failing closed on mixed domains without a new policy implementation.
- The uncommitted grounded-claim normalization pass is reverted or materially changed.

## Verification For This Documentation Pass

Manual source checks:

- Official Gemini Google Search grounding documentation reviewed.
- Official ADK Google Search grounding documentation reviewed.
- Official ADK AgentTool grounding propagation documentation reviewed.
- Official Gemini Interactions API documentation reviewed.
- Local source files inspected for Research tool configuration, service path, input contract, normalization, citation receipts, provider probe, and responder boundary.

No production source code was changed in this pass.
