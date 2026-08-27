# Research Grounded Claim Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce false `too_many_grounded_claims` Research failures when Gemini/ADK returns valid public grounding metadata with more support segments than Agent Col should expose as final findings.

**Architecture:** Keep the existing ADK Research Service and `generate_content`-era Google Search grounding path. Change only local normalization so valid provider-grounded text can be compacted into Agent Col's bounded finding limit instead of being rejected solely because the provider emitted more than 8 mappable support segments.

**Tech Stack:** Python, Pydantic, Google ADK, google-genai grounding metadata objects, pytest.

**Spec:** `docs/superpowers/plans/2026-08-27-research-provider-compatibility-spike-findings.md` and `docs/superpowers/plans/2026-08-27-invalid-output-reason-handoff-pass-findings.md`

## Global Constraints

- Do not migrate Research to AgentTool.
- Do not migrate Research to Gemini Interactions.
- Do not add another validation layer.
- Do not remove fail-closed handling for missing response text, missing grounding metadata, missing grounding chunks, missing grounding supports, private/invalid sources, unmappable claims, claims without source IDs, or excessive sources per claim.
- Keep `ResearchExpertEvidence.grounded_finding_count` bounded at 1 through 8.
- Preserve content-safe diagnostics only; do not log generated answer text, full provider payloads, raw URLs beyond existing normalized public source fields, hidden context, or user secrets.
- Stop and revise the plan if the RED test cannot reproduce a valid provider-grounded false rejection.

---

## File Structure

- Modify: `research_expert.py`
  - Responsibility: normalize Gemini grounding metadata into bounded `ResearchExpertResult` objects.
- Modify: `tests/test_research_expert.py`
  - Responsibility: unit/regression coverage for provider-grounded text normalization.
- Modify if needed: `tests/test_research_expert_service.py`
  - Responsibility: service-level invalid-output classification expectations.
- Read only: `research_provider_compatibility_check.py`
  - Responsibility: optional manual backend probe for post-change diagnostics; no runtime dependency.

### Task 1: Prove Valid Extra Grounding Supports Should Compact Instead Of Fail

**Files:**
- Modify: `tests/test_research_expert.py`
- Read: `research_expert.py`

**Interfaces:**
- Consumes: `research_expert.diagnose_grounded_research_text(response_text: str, metadata: types.GroundingMetadata | None) -> ResearchNormalizationOutcome`
- Produces: a failing regression test that describes the exact accepted behavior for more than 8 valid grounded support segments.

- [ ] **Step 1: Write the failing test**

Add this test near existing grounded-text normalization tests in `tests/test_research_expert.py`:

```python
def test_grounded_text_compacts_more_than_eight_supported_claims() -> None:
    from expert_contracts import ExpertStatus
    from research_expert import diagnose_grounded_research_text

    claims = tuple(
        f"Documented public fact {index}." for index in range(1, 10)
    )
    response_text = " ".join(claims)
    metadata = types.GroundingMetadata(
        grounding_chunks=[
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://www.python.org/downloads/",
                    title="Python downloads",
                )
            )
        ],
        grounding_supports=[
            types.GroundingSupport(
                segment=types.Segment(text=claim),
                grounding_chunk_indices=[0],
            )
            for claim in claims
        ],
    )

    outcome = diagnose_grounded_research_text(
        response_text=response_text,
        metadata=metadata,
    )

    assert outcome.invalid_output_reason is None
    assert outcome.result.status is ExpertStatus.COMPLETED
    assert outcome.result.payload is not None
    assert len(outcome.result.payload.findings) == 8
    assert outcome.result.evidence is not None
    assert outcome.result.evidence.grounded_finding_count == 8
    assert outcome.result.evidence.grounding_support_count == 9
```

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest tests/test_research_expert.py::test_grounded_text_compacts_more_than_eight_supported_claims -q
```

Expected result:

```text
FAIL
```

Expected failure reason:

```text
outcome.invalid_output_reason == ResearchInvalidOutputReason.TOO_MANY_GROUNDED_CLAIMS
```

If the test fails for missing imports, malformed metadata construction, or any reason other than `too_many_grounded_claims`, fix the test setup before production changes.

### Task 2: Compact Supported Claims To The Existing Finding Limit

**Files:**
- Modify: `research_expert.py`
- Test: `tests/test_research_expert.py`

**Interfaces:**
- Consumes: `source_ids_by_claim: dict[str, list[str]]` inside `diagnose_grounded_research_text`
- Produces: completed `ResearchExpertResult` with at most 8 findings and the original grounding support count.

- [ ] **Step 1: Implement the minimal normalization change**

In `research_expert.py`, replace the rejection:

```python
if len(source_ids_by_claim) > 8:
    return _invalid_research_outcome(
        ResearchInvalidOutputReason.TOO_MANY_GROUNDED_CLAIMS
    )
```

with bounded iteration:

```python
bounded_claims = tuple(source_ids_by_claim.items())[:8]
```

Then iterate over `bounded_claims` instead of `source_ids_by_claim.items()` when building `findings`.

Keep this rejection unchanged:

```python
if len(supports) > 40:
    return _invalid_research_outcome(
        ResearchInvalidOutputReason.TOO_MANY_GROUNDING_SUPPORTS
    )
```

- [ ] **Step 2: Verify GREEN**

Run:

```bash
venv/bin/pytest tests/test_research_expert.py::test_grounded_text_compacts_more_than_eight_supported_claims -q
```

Expected result:

```text
PASS
```

### Task 3: Preserve Existing Failure Semantics For Unsafe Grounding

**Files:**
- Modify if needed: `tests/test_research_expert_service.py`
- Modify if needed: `research_expert.py`

**Interfaces:**
- Consumes: existing parameterized service test that expects:
  - `too_many_grounding_supports`
  - `grounded_claim_without_source`
  - `too_many_sources_for_claim`
  - missing metadata/chunks/supports/source cases
- Produces: updated expectation only for the exact valid nine-supported-claim scenario, not for unsafe metadata.

- [ ] **Step 1: Run existing invalid-output classification tests**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_reports_content_safe_invalid_output_reason -q
```

Expected result before any needed test update:

```text
FAIL only if the existing synthetic nine-claim case now completes instead of returning too_many_grounded_claims.
```

- [ ] **Step 2: Update only the obsolete expectation if required**

If the service test contains a synthetic case with 9 individually supported claims and valid public source metadata, move that case out of the invalid-output parameterization and add a positive assertion that it completes with 8 exposed findings and `grounding_support_count == 9`.

Do not change expectations for missing metadata, invalid private sources, unmappable supports, claims without source IDs, more than 40 supports, or more than 5 sources per claim.

- [ ] **Step 3: Verify service-level behavior**

Run:

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_reports_content_safe_invalid_output_reason -q
```

Expected result:

```text
PASS
```

### Task 4: Focused Verification And Manual Probe

**Files:**
- Read: `research_provider_compatibility_check.py`
- Verify: Research tests and provider probe

**Interfaces:**
- Consumes: local test suite and optional live provider diagnostic.
- Produces: evidence that the normalizer is less brittle without expanding provider/runtime scope.

- [ ] **Step 1: Run focused Research tests**

Run:

```bash
venv/bin/pytest tests/test_research_expert.py tests/test_research_expert_service.py tests/test_research_provider_compatibility_check.py -q
```

Expected result:

```text
PASS
```

- [ ] **Step 2: Run static diff check**

Run:

```bash
git diff --check
```

Expected result:

```text
no output, exit 0
```

- [ ] **Step 3: Run live backend probe only after local tests pass**

Run:

```bash
venv/bin/python research_provider_compatibility_check.py
```

Expected acceptable outcomes:

- `adk-research-service` completed with `grounding_metadata=true`; or
- `adk-research-service` returns `invalid_output` with a content-safe reason that is not `too_many_grounded_claims` for valid public grounding.

If live Interactions still returns HTTP 400, that is expected and not part of this pass.

## Acceptance Criteria

- Valid provider-grounded output with more than 8 support segments no longer fails only because it maps to more than 8 claims.
- Output remains bounded to at most 8 Research findings.
- More than 40 grounding supports still fails as `too_many_grounding_supports`.
- Missing/unmappable/private/unsupported grounding still fails closed.
- No production use of Interactions or AgentTool is introduced.
- No provider answer text or raw provider payload is logged by tests or probes.

## Manual Runtime Verification Targets

1. Ask the previous official-documentation Research prompt that produced an `invalid_output` answer.
2. If provider grounding is valid but verbose, expect a completed grounded answer with citations rather than a `too_many_grounded_claims` failure.
3. If provider grounding is missing or unmappable, expect the bounded failed-verification response from the prior pass, not unsourced fallback facts.
4. Confirm no new application-level retry loop is visible to the user.

## Rollback

This document is a nonbehavioral plan. If this unapproved plan checkpoint needs to be removed before implementation, use:

```bash
git revert HEAD
```

Only run that command when `git log -1 --oneline` shows the checkpoint commit for this plan.

Before implementing this plan, record the then-current checkpoint with:

```bash
git rev-parse HEAD
```

The implementation pass report must include the exact rollback command for the implementation commit created by that future pass.
