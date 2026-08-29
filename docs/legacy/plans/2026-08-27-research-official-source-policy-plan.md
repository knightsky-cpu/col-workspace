# Research Official Source Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make explicit official-documentation Research requests reject or exclude unofficial sources instead of treating mixed public citations as satisfying the request.

**Architecture:** Keep the current ADK Research Service and local Research normalization path. Add a request-scoped source policy derived by the routing/executor boundary only when the user explicitly asks for official documentation, then enforce that policy inside Research normalization without changing broad public-research behavior.

**Tech Stack:** Python, Pydantic, Google ADK, google-genai grounding metadata objects, pytest.

**Spec:** `docs/superpowers/plans/2026-08-27-research-current-work-and-handoff.md` and `docs/superpowers/plans/2026-08-27-adk-gemini-tool-surface-mismatch-handoff.md`

**Evidence:** `docs/superpowers/plans/2026-08-27-research-official-source-evidence-findings.md`

## Global Constraints

- Do not migrate Research to AgentTool.
- Do not migrate Research to Gemini Interactions.
- Do not add another validation layer around failed provider output.
- Do not add a source-policy `mode` field in this pass. If this pass works in automated and manual verification, a follow-up pass may add explicit modes such as official-only versus official-preferred.
- Do not require official-source filtering for broad research requests unless the user asks for official documentation, official install instructions, official release data, or equivalent authoritative-source wording.
- Preserve existing fail-closed behavior for missing response text, missing grounding metadata, missing grounding chunks, missing grounding supports, private/invalid sources, unmappable claims, claims without source IDs, too many sources per claim, and more than 40 grounding supports.
- Preserve the current bounded output limit of at most 8 Research findings.
- Preserve content-safe diagnostics only; do not log generated answer text, hidden context, full provider payloads, or raw user secrets.

---

## File Structure

- Modify: `research_expert.py`
  - Responsibility: define the request-level source policy contract and enforce it while extracting grounded sources.
- Modify: `agent_col_expert_executor_v3.py`
  - Responsibility: derive a conservative official-source policy from validated routing intent and current message.
- Modify: `tests/test_research_expert.py`
  - Responsibility: unit coverage for source-policy enforcement in normalization.
- Modify: `tests/test_agent_col_expert_executor_v3.py`
  - Responsibility: executor coverage for official-source policy derivation.
- Modify if needed: `research_provider_compatibility_check.py`
  - Responsibility: optional diagnostics only; do not make it runtime-dependent.

### Task 1: Add Research Source Policy Contract

**Files:**
- Modify: `research_expert.py`
- Test: `tests/test_research_expert.py`

**Interfaces:**
- Add `ResearchSourcePolicy` with:
  - `allowed_domains: tuple[str, ...]`
  - `policy_name: str`
- Add optional `source_policy: ResearchSourcePolicy | None = None` to `ResearchExpertInput`.
- Preserve existing `ResearchExpertInput` behavior when `source_policy is None`.
- Do not add `mode` yet. This pass is official-only enforcement when a policy is present. Official-preferred or unofficial-context preservation is a later pass only if this pass works.

- [ ] **Step 1: Write the failing contract test**

Add to `tests/test_research_expert.py`:

```python
def test_research_input_accepts_optional_official_source_policy() -> None:
    from research_expert import ResearchExpertInput, ResearchSourcePolicy

    request = ResearchExpertInput(
        question="Check the official OpenAI docs.",
        objective="Use official documentation only.",
        source_policy=ResearchSourcePolicy(
            policy_name="official_openai_docs",
            allowed_domains=("openai.com", "github.com/openai"),
        ),
    )

    assert request.source_policy is not None
    assert request.source_policy.allowed_domains == (
        "openai.com",
        "github.com/openai",
    )
```

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest tests/test_research_expert.py::test_research_input_accepts_optional_official_source_policy -q
```

Expected result: fail because `ResearchSourcePolicy` and `source_policy` do not exist.

- [ ] **Step 3: Implement the contract**

Add the minimal Pydantic model and field:

```python
class ResearchSourcePolicy(StrictResearchModel):
    policy_name: str = Field(min_length=1, max_length=80)
    allowed_domains: tuple[str, ...] = Field(min_length=1, max_length=8)


class ResearchExpertInput(StrictResearchModel):
    ...
    source_policy: ResearchSourcePolicy | None = None
```

- [ ] **Step 4: Verify GREEN**

Run the same single test and confirm it passes.

### Task 2: Enforce Official Domains During Source Extraction

**Files:**
- Modify: `research_expert.py`
- Test: `tests/test_research_expert.py`

**Interfaces:**
- Update `diagnose_grounded_research_text` to accept `source_policy: ResearchSourcePolicy | None = None`.
- When a policy is present, only grounded sources matching the allowed domains can satisfy the result.
- Add a content-safe reason such as `OFFICIAL_SOURCE_POLICY_MISMATCH = "official_source_policy_mismatch"`.

- [ ] **Step 1: Write the mixed-source failing test**

Add to `tests/test_research_expert.py`:

```python
def test_official_source_policy_rejects_mixed_unofficial_sources() -> None:
    from research_expert import (
        ResearchInvalidOutputReason,
        ResearchSourcePolicy,
        diagnose_grounded_research_text,
    )

    response_text = "The official SDK install command is documented."
    metadata = types.GroundingMetadata(
        grounding_chunks=[
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://platform.openai.com/docs/libraries",
                    title="OpenAI libraries",
                )
            ),
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://medium.com/example/openai-sdk-guide",
                    title="Unofficial guide",
                )
            ),
        ],
        grounding_supports=[
            types.GroundingSupport(
                segment=types.Segment(text=response_text),
                grounding_chunk_indices=[0, 1],
            )
        ],
    )

    outcome = diagnose_grounded_research_text(
        response_text=response_text,
        metadata=metadata,
        source_policy=ResearchSourcePolicy(
            policy_name="official_openai_docs",
            allowed_domains=("openai.com",),
        ),
    )

    assert outcome.invalid_output_reason is (
        ResearchInvalidOutputReason.OFFICIAL_SOURCE_POLICY_MISMATCH
    )
```

- [ ] **Step 2: Write the official-source positive test**

Add to `tests/test_research_expert.py`:

```python
def test_official_source_policy_accepts_allowed_sources() -> None:
    from expert_contracts import ExpertStatus
    from research_expert import ResearchSourcePolicy, diagnose_grounded_research_text

    response_text = "The official SDK install command is documented."
    metadata = types.GroundingMetadata(
        grounding_chunks=[
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://platform.openai.com/docs/libraries",
                    title="OpenAI libraries",
                )
            )
        ],
        grounding_supports=[
            types.GroundingSupport(
                segment=types.Segment(text=response_text),
                grounding_chunk_indices=[0],
            )
        ],
    )

    outcome = diagnose_grounded_research_text(
        response_text=response_text,
        metadata=metadata,
        source_policy=ResearchSourcePolicy(
            policy_name="official_openai_docs",
            allowed_domains=("openai.com",),
        ),
    )

    assert outcome.invalid_output_reason is None
    assert outcome.result.status is ExpertStatus.COMPLETED
```

- [ ] **Step 3: Verify RED**

Run:

```bash
venv/bin/pytest tests/test_research_expert.py::test_official_source_policy_rejects_mixed_unofficial_sources tests/test_research_expert.py::test_official_source_policy_accepts_allowed_sources -q
```

Expected result: fail because the source policy is not enforced.

- [ ] **Step 4: Implement matching**

Use URL parsing instead of string contains. A source matches when:

- the hostname equals an allowed domain, such as `openai.com`; or
- the hostname is a subdomain of an allowed domain, such as `platform.openai.com`; or
- the allowed entry includes an owner/repo path such as `github.com/openai` and the source URL hostname/path starts with that host/path.

If any cited source for a retained claim is outside the policy, return `official_source_policy_mismatch`. Do not silently drop unofficial sources from the claim, because that would make mixed-source evidence appear cleaner than it is.

- [ ] **Step 5: Verify GREEN**

Run the same two tests and confirm they pass.

### Task 3: Derive Official Source Policy At The Executor Boundary

**Files:**
- Modify: `agent_col_expert_executor_v3.py`
- Test: `tests/test_agent_col_expert_executor_v3.py`

**Interfaces:**
- Add a helper such as:

```python
def derive_research_source_policy(
    directive: AgentColRoutingDirective,
) -> ResearchSourcePolicy | None:
    ...
```

- Derive policies only from explicit authoritative-source language inside `directive.research_intent.question`, `objective`, and `constraints`.
- Initial policy map:
  - OpenAI official docs: `("openai.com", "github.com/openai")`
  - Python official release/docs: `("python.org", "peps.python.org")`
  - Omarchy official docs/install: start with `("omarchy.org", "github.com/basecamp/omarchy")` only if source review confirms that repo/domain is official before implementation.

- [ ] **Step 1: Write failing executor test for OpenAI docs**

Add to `tests/test_agent_col_expert_executor_v3.py`:

```python
@pytest.mark.asyncio
async def test_executor_v3_derives_official_openai_source_policy() -> None:
    executor_v3 = load_executor_v3()
    service = RecordingService()
    executor = executor_v3.AgentColExpertExecutorV3(research_service=service)
    directive = AgentColRoutingDirective(
        route="research",
        research_intent={
            "question": "Check the official OpenAI Python SDK docs.",
            "objective": "Use official OpenAI documentation only.",
        },
    )
    routing_input = AgentColRoutingInput(
        current_message="Check the official OpenAI Python SDK docs.",
        available_capabilities=("research",),
    )

    await executor.execute(directive, routing_input)

    request = service.requests[0]
    assert request.source_policy is not None
    assert request.source_policy.policy_name == "official_openai_docs"
    assert request.source_policy.allowed_domains == (
        "openai.com",
        "github.com/openai",
    )
```

- [ ] **Step 2: Write broad-research negative test**

Add to `tests/test_agent_col_expert_executor_v3.py`:

```python
@pytest.mark.asyncio
async def test_executor_v3_leaves_broad_research_without_source_policy() -> None:
    executor_v3 = load_executor_v3()
    service = RecordingService()
    executor = executor_v3.AgentColExpertExecutorV3(research_service=service)
    directive = AgentColRoutingDirective(
        route="research",
        research_intent={
            "question": "Compare recent Python packaging discussions.",
            "objective": "Use public evidence.",
        },
    )
    routing_input = AgentColRoutingInput(
        current_message="Compare recent Python packaging discussions.",
        available_capabilities=("research",),
    )

    await executor.execute(directive, routing_input)

    assert service.requests[0].source_policy is None
```

- [ ] **Step 3: Verify RED**

Run:

```bash
venv/bin/pytest tests/test_agent_col_expert_executor_v3.py::test_executor_v3_derives_official_openai_source_policy tests/test_agent_col_expert_executor_v3.py::test_executor_v3_leaves_broad_research_without_source_policy -q
```

Expected result: fail because no source policy is derived.

- [ ] **Step 4: Implement minimal derivation**

Add a small rule-based helper. Do not call the model and do not add a new route.

- [ ] **Step 5: Verify GREEN**

Run the same two tests and confirm they pass.

### Task 4: Pass Source Policy Through Service Normalization

**Files:**
- Modify: `research_expert_service.py`
- Test: `tests/test_research_expert_service.py`

**Interfaces:**
- `ResearchExpertService.research(request: ResearchExpertInput)` must pass `request.source_policy` into `normalize_research_event` or `diagnose_grounded_research_text`.

- [ ] **Step 1: Write failing service test**

Add a service test that sends `ResearchExpertInput(..., source_policy=ResearchSourcePolicy(...))` and a mixed official/unofficial grounded event. Assert `ResearchExpertServiceError.invalid_output_reason == ResearchInvalidOutputReason.OFFICIAL_SOURCE_POLICY_MISMATCH`.

- [ ] **Step 2: Verify RED**

Run the new service test and confirm it fails because policy is not passed through.

- [ ] **Step 3: Implement minimal pass-through**

Thread `source_policy` through the existing normalization call. Do not alter provider invocation.

- [ ] **Step 4: Verify GREEN**

Run the new service test and confirm it passes.

### Task 5: Focused Verification And Manual Targets

**Files:**
- Verify changed Research and executor surfaces.

- [ ] **Step 1: Run focused tests**

Run:

```bash
venv/bin/pytest tests/test_research_expert.py tests/test_research_expert_service.py tests/test_agent_col_expert_executor_v3.py tests/test_agent_col_responder_context_v3.py -q
```

Expected result: pass.

- [ ] **Step 2: Run provider compatibility probe**

Run:

```bash
venv/bin/python research_provider_compatibility_check.py
```

Expected result:

- ADK Research or direct `generate_content` can still complete with grounding metadata.
- Interactions HTTP 400 remains known and out of scope.

- [ ] **Step 3: Run diff check**

Run:

```bash
git diff --check
```

Expected result: no output, exit 0.

## Acceptance Criteria

- Official OpenAI docs requests no longer accept unrelated domains such as `microsoft.com`, `datacamp.com`, `medium.com`, or unknown wrappers as satisfying official OpenAI documentation.
- Official Python release/docs requests accept `python.org` and `peps.python.org` and reject unrelated public sources when official-only wording is present.
- Official Omarchy install/docs requests enforce only verified official project domains/repos after source review confirms the canonical domain and repo.
- Broad public research requests still allow mixed public sources.
- Failed official-source validation returns a content-safe `official_source_policy_mismatch` reason.
- Unofficial sources returned by Google Search are not exposed as citations for official-only answers in this pass. They may inform a future diagnostics mode, but they do not satisfy the official-source request.
- The pass report includes the four targeted Research/Google Search manual prompts listed below and their expected pass/fail interpretation.
- No provider topology migration is introduced.

## Manual Runtime Verification Targets

Run these prompts through the normal Agent Col chat path. Each prompt is intentionally current/external so routing should select Research and the Research Expert should have reason to use Google Search grounding.

1. Prompt: `Using only official OpenAI documentation, tell me the current Python SDK install command and the recommended Responses API call pattern for a FastAPI backend.`
   - Expected: success only when retained citations are approved OpenAI sources such as `openai.com` or `github.com/openai`; fail closed with `official_source_policy_mismatch` if retained claims depend on unrelated public sources such as tutorials, blogs, vendor pages, or social sites.
2. Prompt: `Using only official Python sources, what is the current stable Python release and where is it documented?`
   - Expected: success only with `python.org` or `peps.python.org` sources; fail closed if retained claims depend on unrelated public sources.
3. Prompt: `Using only official Omarchy project documentation, what are the current install instructions and prerequisites?`
   - Expected: success only with verified official Omarchy project sources after source review confirms the canonical domain/repo; fail closed if retained claims depend on video, blog, vendor, or social sources.
4. Prompt: `Research current Python packaging discussion across public sources and summarize the main points with citations.`
   - Expected: broad public research remains unchanged; mixed public sources are allowed because no official-only source policy should be derived.

In the implementation pass report, include these four prompts under manual verification targets and explicitly state that the user must confirm the live results before checkpointing the source implementation.

## Rollback

Before implementing this plan, record the current checkpoint:

```bash
git rev-parse HEAD
```

If this plan itself needs to be reverted while it is the latest commit:

```bash
git revert HEAD
```

For a future implementation pass, use the exact implementation commit SHA in that pass report.
