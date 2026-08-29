# Direct Google Search Research Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the intermittent ADK workflow Research execution surface with a direct Google Gen AI `generate_content` + Google Search path while preserving Agent Col's validated Research result, citation receipts, fail-closed behavior, and plain Google Search disclaimer.

**Architecture:** Keep the existing Research normalization and receipt contracts. Change `ResearchExpertService` from collecting ADK workflow final events to issuing one direct grounded `generate_content` request, then normalize the returned response text and `grounding_metadata` through the existing `diagnose_grounded_research_text` path. Leave routing, executor, responder context, and citation rendering unchanged.

**Tech Stack:** Python, Pydantic, pytest, `google-genai`, Gemini Enterprise Agent Platform / Vertex AI, Google Search grounding.

**Spec:** Current live failure report from 2026-08-27, checkpoint `91ba0ea revise research source disclaimer`, and prior evidence docs:
- `docs/superpowers/plans/2026-08-27-adk-gemini-tool-surface-mismatch-handoff.md`
- `docs/superpowers/plans/2026-08-27-research-provider-compatibility-recheck-findings.md`
- `docs/superpowers/plans/2026-08-27-research-current-work-and-handoff.md`

## Global Constraints

- Do not restore the removed official-source policy. The source scan after checkpoint `91ba0ea` had no `ResearchSourcePolicy`, `source_policy`, or `official_source_policy_mismatch` references outside docs/venv/git.
- Keep the responder disclaimer from `agent_col_responder.py`: Google Search-grounded public web research is not guaranteed official documentation, and users should verify cited sources before treating them as official.
- Preserve fail-closed behavior when response text, grounding metadata, grounding chunks, grounding supports, public source validation, mappable claims, source IDs, or bounded source counts are missing or invalid.
- Preserve grounded-claim compaction: expose at most 8 findings while retaining the provider's original grounding support count.
- Do not change routing, memory, notes, artifacts, workspace UI, or broad public research behavior in this pass.
- Do not checkpoint implementation work until the user completes manual verification and explicitly approves the implementation checkpoint.

---

## Current Evidence

### Checkpoint Evidence

- Documentation/disclaimer checkpoint pushed to `origin/main`: `91ba0ea revise research source disclaimer`.
- Focused verification before checkpoint: `107 passed`, `1` existing ADK deprecation warning.
- `git diff --check`: clean.
- Worktree after checkpoint: only untracked `.agents/`.

### Old Source Policy Issue

- The hard official-source policy is removed from source.
- The user asked whether the source policy was removed after seeing continued failures. Source-backed answer: yes, the old policy is gone. Current failures are not `official_source_policy_mismatch`.

### Current Omarchy Failure

Observed live UI behavior:

- Omarchy official install prompt can fail with a contained response explaining Research execution limitation.
- Terminal / probe evidence identifies the reason as `missing_grounding_chunks`, not source-policy mismatch.

Provider probe evidence:

```text
research-provider probe=adk-research-service surface=adk_research_service status=invalid_output ... invalid_output_reason=missing_grounding_chunks
research-provider probe=generate-content-google-search surface=generate_content status=completed ... grounding_metadata=true grounding_chunks=14 grounding_supports=26 invalid_output_reason=none
```

Repeated Omarchy probes showed ADK workflow behavior is intermittent:

```text
run 1: adk_research_service completed, grounding_chunks=7, grounding_supports=19
run 2: adk_research_service invalid_output, invalid_output_reason=missing_grounding_chunks
run 3: adk_research_service completed, grounding_chunks=5, grounding_supports=2
```

Raw ADK event inspection also showed a successful Omarchy run:

```text
event 1: author=research_expert final=True text_len=2094 metadata=True chunks=9 supports=16 output=False
```

Inference: Google Search can find and ground Omarchy results. The unreliable component is the current ADK `Agent` / `Workflow` Research surface, which can return a final response with missing or empty grounding chunks for the same kind of prompt.

### Current Timeout Failure

Observed live UI/terminal behavior:

```text
Root node Agent_Col was cancelled.
Agent_Col turn failed (TimeoutError).
Agent_Col chat turn timed out (stage=turn completed_actions=0 ...).
POST /api/chat HTTP/1.1 504 Gateway Timeout
```

Source-backed timeout boundaries:

- `agent_col_turn_service.py`: `TURN_TIMEOUT_SECONDS = 90.0`
- `agent_col_turn_service.py`: `TURN_EXPERT_BUDGET_SECONDS = 45.0`
- `agent_col_turn_service.py`: `TURN_RESPONDER_RESERVE_SECONDS = 20.0`
- `main.py` maps `AgentColTurnTimeoutError` to HTTP 504.

Inference: Some full turns spend too long across routing, Research execution, and final responder generation. Reducing Research surface latency and avoiding an extra ADK workflow/provider attempt should reduce 504 frequency, but a separate responder-timeout pass may still be needed if 504s continue after Research stabilizes.

### Official Documentation Evidence

Google Cloud documentation describes Grounding with Google Search as connecting Gemini responses to publicly available web data and lists Gemini 3.6 Flash among supported models. The same page documents Python `generate_content` with a `Tool(google_search=GoogleSearch(...))` configuration. Google's SDK overview documents the `google-genai` SDK and Vertex/Enterprise environment variables.

References:

- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-google-search
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/sdks/overview

## File Structure

- Modify: `research_expert_service.py`
  - Responsibility: execute Research with direct Google Gen AI `generate_content` and Google Search grounding, normalize direct response metadata, and preserve service error semantics.
- Modify: `tests/test_research_expert_service.py`
  - Responsibility: service-level TDD coverage for direct provider request construction, successful grounded response normalization, missing-grounding rejection, timeout mapping, and provider-error mapping.
- Modify if needed: `research_provider_compatibility_check.py`
  - Responsibility: keep diagnostics aligned if the production Research service no longer uses the ADK workflow as its primary path.
- Read only unless required by tests: `research_expert.py`
  - Responsibility: existing provider-grounding normalization and citation payload construction.
- Read only unless required by tests: `agent_col_expert_executor_v3.py`, `agent_col_responder_context_v3.py`, `agent_col_responder.py`
  - Responsibility: prove the direct service still feeds the existing executor/responder/citation boundary.

## Task 1: Introduce Direct Grounded Provider Service Contract

**Files:**
- Modify: `tests/test_research_expert_service.py`
- Modify: `research_expert_service.py`

**Interfaces:**
- Consumes: `ResearchExpertInput`, `ResearchExpertResult`, `ResearchExpertServiceError`, `ResearchInvalidOutputReason`.
- Produces: `ResearchExpertService(app, runner, session_service, genai_client=None, timeout_seconds=...)` or equivalent minimal constructor extension that allows tests to pass a fake direct client without live network.

- [ ] **Step 1: Write the failing constructor/topology test**

Add a test proving `ResearchExpertService.from_vertex_settings(settings)` creates a service with a direct Gen AI client available for Research execution, while preserving the existing `app` property for compatibility.

Expected test shape:

```python
def test_research_service_from_vertex_settings_configures_direct_client() -> None:
    from research_expert_service import ResearchExpertService
    from vertex_config import VertexAISettings

    service = ResearchExpertService.from_vertex_settings(
        VertexAISettings(project="project-1", location="global")
    )

    assert service.app.name == "agent_col_research"
    assert service.direct_client is not None
```

- [ ] **Step 2: Run RED**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_from_vertex_settings_configures_direct_client -q
```

Expected: fail because `direct_client` does not exist or the constructor does not expose/configure it.

- [ ] **Step 3: Implement minimal direct-client storage**

Add a private direct client dependency and a read-only test-facing property:

```python
class ResearchExpertService:
    def __init__(..., direct_client: object | None = None, ...):
        ...
        self._direct_client = direct_client

    @property
    def direct_client(self) -> object | None:
        return self._direct_client
```

In `from_vertex_settings`, create:

```python
client = genai.Client(**vertex_settings.client_kwargs())
```

and pass it as `direct_client=client`.

- [ ] **Step 4: Run GREEN**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_from_vertex_settings_configures_direct_client -q
```

Expected: pass.

## Task 2: Normalize Successful Direct Google Search Grounding

**Files:**
- Modify: `tests/test_research_expert_service.py`
- Modify: `research_expert_service.py`

**Interfaces:**
- Consumes: fake `direct_client.aio.models.generate_content(...)` returning an object with `text` and `candidates[0].grounding_metadata`.
- Produces: `ResearchExpertService.research(...) -> ResearchExpertResult(status=COMPLETED)` using existing citation payloads.

- [ ] **Step 1: Write failing service test for direct grounded success**

Add a fake direct client and test:

```python
class RecordingGenerateContentModels:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls = []

    async def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class RecordingGenerateContentClient:
    def __init__(self, response: object) -> None:
        self.aio = type("Aio", (), {})()
        self.aio.models = RecordingGenerateContentModels(response)


def direct_response(text: str, metadata: types.GroundingMetadata) -> object:
    candidate = type("Candidate", (), {"grounding_metadata": metadata})()
    return type(
        "DirectResponse",
        (),
        {"text": text, "candidates": [candidate]},
    )()
```

Then:

```python
@pytest.mark.asyncio
async def test_research_service_normalizes_direct_grounded_response() -> None:
    from expert_contracts import ExpertStatus
    from research_expert_service import ResearchExpertService

    claim = "Omarchy installation is documented by the project."
    metadata = types.GroundingMetadata(
        grounding_chunks=[public_grounding_chunk()],
        grounding_supports=[
            types.GroundingSupport(
                segment=types.Segment(text=claim),
                grounding_chunk_indices=[0],
            )
        ],
    )
    client = RecordingGenerateContentClient(direct_response(claim, metadata))
    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=RecordingRunner(()),
        session_service=RecordingSessionService(),
        direct_client=client,
    )

    result = await service.research(
        ResearchExpertInput(
            question="What are the current Omarchy install instructions?",
            objective="Return grounded public evidence.",
        )
    )

    assert result.status is ExpertStatus.COMPLETED
    assert result.payload is not None
    assert result.evidence is not None
    assert result.evidence.grounding_support_count == 1
    call = client.aio.models.calls[0]
    assert call["model"] == "gemini-3.6-flash"
    assert call["contents"]
    assert call["config"].tools
```

- [ ] **Step 2: Run RED**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_normalizes_direct_grounded_response -q
```

Expected: fail because `research()` still uses the ADK runner path and ignores the fake direct client.

- [ ] **Step 3: Implement direct generation path**

Inside `ResearchExpertService.research`, under the existing timeout/session error mapping, call a new helper:

```python
async def _run_direct_invocation(self, request: ResearchExpertInput) -> ResearchExpertResult:
    response = await self._direct_client.aio.models.generate_content(
        model=RESEARCH_EXPERT_MODEL_NAME,
        contents=_direct_research_prompt(request),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=1.0,
            max_output_tokens=2_048,
        ),
    )
    metadata = _direct_response_grounding_metadata(response)
    outcome = diagnose_grounded_research_text(
        response_text=response.text if isinstance(response.text, str) else "",
        metadata=metadata,
    )
    if outcome.result.status is not ExpertStatus.COMPLETED:
        self._raise_invalid_output(
            outcome.invalid_output_reason
            or ResearchInvalidOutputReason.NORMALIZED_RESULT_VALIDATION_FAILED
        )
    return outcome.result
```

Use temperature `1.0` because Google Cloud's Grounding with Google Search page says ideal results use temperature `1.0`.

- [ ] **Step 4: Run GREEN**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_normalizes_direct_grounded_response -q
```

Expected: pass.

## Task 3: Preserve Fail-Closed Direct Missing-Grounding Behavior

**Files:**
- Modify: `tests/test_research_expert_service.py`
- Modify: `research_expert_service.py`

**Interfaces:**
- Consumes: direct response with text and empty/missing `grounding_chunks`.
- Produces: `ResearchExpertServiceError(status=INVALID_OUTPUT, invalid_output_reason=MISSING_GROUNDING_CHUNKS)` or existing equivalent safe reason.

- [ ] **Step 1: Write failing missing-grounding test**

```python
@pytest.mark.asyncio
async def test_research_service_rejects_direct_response_without_grounding_chunks() -> None:
    from expert_contracts import ExpertStatus
    from research_expert import ResearchInvalidOutputReason
    from research_expert_service import ResearchExpertService, ResearchExpertServiceError

    response = direct_response(
        "Omarchy installation is documented.",
        types.GroundingMetadata(grounding_chunks=[], grounding_supports=[]),
    )
    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=RecordingRunner(()),
        session_service=RecordingSessionService(),
        direct_client=RecordingGenerateContentClient(response),
    )

    with pytest.raises(ResearchExpertServiceError) as exc_info:
        await service.research(
            ResearchExpertInput(
                question="What are the current Omarchy install instructions?",
                objective="Return grounded public evidence.",
            )
        )

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT
    assert exc_info.value.invalid_output_reason is (
        ResearchInvalidOutputReason.MISSING_GROUNDING_CHUNKS
    )
```

- [ ] **Step 2: Run RED**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_rejects_direct_response_without_grounding_chunks -q
```

Expected: fail until direct missing-grounding rejection is wired.

- [ ] **Step 3: Implement missing-grounding mapping**

Use `diagnose_grounded_research_text(...)` directly. Do not add a local source policy or fallback facts.

- [ ] **Step 4: Run GREEN**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_rejects_direct_response_without_grounding_chunks -q
```

Expected: pass.

## Task 4: Preserve Timeout and Provider Error Semantics

**Files:**
- Modify: `tests/test_research_expert_service.py`
- Modify: `research_expert_service.py`

**Interfaces:**
- Consumes: direct client that raises `TimeoutError`, generic provider exception, or validation error.
- Produces: existing safe statuses: `TIMED_OUT`, `UNAVAILABLE`, `REJECTED_INPUT` as applicable.

- [ ] **Step 1: Write direct timeout test**

```python
class RaisingGenerateContentModels:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def generate_content(self, **kwargs: object) -> object:
        raise self.exc


class RaisingGenerateContentClient:
    def __init__(self, exc: Exception) -> None:
        self.aio = type("Aio", (), {})()
        self.aio.models = RaisingGenerateContentModels(exc)


@pytest.mark.asyncio
async def test_research_service_maps_direct_timeout_to_timed_out() -> None:
    from expert_contracts import ExpertStatus
    from research_expert_service import ResearchExpertService, ResearchExpertServiceError

    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=RecordingRunner(()),
        session_service=RecordingSessionService(),
        direct_client=RaisingGenerateContentClient(TimeoutError()),
    )

    with pytest.raises(ResearchExpertServiceError) as exc_info:
        await service.research(
            ResearchExpertInput(question="Current release?", objective="Ground it.")
        )

    assert exc_info.value.status is ExpertStatus.TIMED_OUT
```

- [ ] **Step 2: Run RED**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_maps_direct_timeout_to_timed_out -q
```

Expected: fail until direct exceptions flow through existing timeout mapping.

- [ ] **Step 3: Implement by reusing existing outer exception mapping**

Make direct invocation run inside the existing `asyncio.timeout(self._timeout_seconds)` block so `TimeoutError` maps to `TIMED_OUT` and generic provider errors map to `UNAVAILABLE`.

- [ ] **Step 4: Run GREEN**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_maps_direct_timeout_to_timed_out -q
```

Expected: pass.

## Task 5: Remove or Demote ADK Workflow Execution From Production Research

**Files:**
- Modify: `research_expert_service.py`
- Modify if needed: `tests/test_research_expert_service.py`

**Interfaces:**
- Consumes: current service API used by `agent_col_expert_executor_v3.py`.
- Produces: same `ResearchExpertService.research(request)` behavior through direct grounded generation.

- [ ] **Step 1: Decide compatibility boundary**

Keep constants and `app` topology if tests or app assembly expect them, but `research()` should prefer direct grounded generation when `_direct_client` is configured.

- [ ] **Step 2: Keep ADK runner only as test/legacy fallback if necessary**

If any existing topology tests assert app construction, leave those intact. Do not run the ADK workflow path in normal `from_vertex_settings` production Research if the direct client is configured.

- [ ] **Step 3: Run focused service tests**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py -q
```

Expected: pass.

## Task 6: Focused Integration Verification

**Files:**
- No production edits unless tests reveal a real contract break.

**Interfaces:**
- Consumes: existing executor/responder tests.
- Produces: evidence that the direct Research service still feeds existing receipts and failed-expert context.

- [ ] **Step 1: Run affected tests**

Run:

```bash
venv/bin/pytest tests/test_research_expert.py tests/test_research_expert_service.py tests/test_agent_col_expert_executor_v3.py tests/test_agent_col_responder_context_v3.py tests/test_agent_col_responder.py -q
```

Expected: pass.

- [ ] **Step 2: Run static diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Optional live metadata probe**

Run:

```bash
venv/bin/python research_provider_compatibility_check.py --prompt "What are the current official installation instructions for Omarchy on a Linux machine as of today, August 27, 2026? Please verify against the official project documentation before answering and cite the sources you used."
```

Expected after implementation: production Research service path should report completed direct grounding or a content-safe provider failure. The direct `generate_content` probe should remain grounded.

## Manual Verification Targets

Run in workspace `test` through the normal browser chat UI:

1. Prompt: `What are the current official installation instructions for Omarchy on a Linux machine as of today, August 27, 2026? Please verify against the official project documentation before answering and cite the sources you used.`
   - Expected: no `official_source_policy_mismatch`; no intermittent `missing_grounding_chunks` if direct grounding succeeds; answer includes citation receipts and the plain Google Search verification disclaimer.
2. Prompt: `What is the current stable Python release as of today, August 27, 2026? Please verify using official Python documentation or python.org release pages before answering and cite the sources you used.`
   - Expected: grounded answer or content-safe provider failure, not unsourced fallback facts.
3. Prompt: `Using only official OpenAI documentation, tell me the current Python SDK install command and the recommended Responses API call pattern for a FastAPI backend.`
   - Expected: completes within the turn budget when provider latency is normal; if it fails, failure reason should be content-safe and not source-policy-related.
4. Prompt: `Research current Python packaging discussion across public sources and summarize the main points with citations.`
   - Expected: broad public research still works with mixed public citations.

## Risks and Stop Conditions

- Stop if direct `generate_content` cannot expose grounding metadata through fake or live responses without weakening validation.
- Stop if converting the service requires changing routing/executor/responder contracts.
- Stop if focused tests show citation receipts no longer map to normalized source IDs.
- Stop if live provider failures are all provider-side 5xx/429/timeout errors rather than missing grounding; that requires retry/backoff planning, not a normalization change.

## Rollback

Current checkpoint before this implementation pass:

```bash
git reset --hard 91ba0ea
```

For a non-destructive source-only rollback before checkpointing implementation:

```bash
git restore research_expert_service.py tests/test_research_expert_service.py research_provider_compatibility_check.py
```

Do not run the destructive rollback unless explicitly approved by the user.
