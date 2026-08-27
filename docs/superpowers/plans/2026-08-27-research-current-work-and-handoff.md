# Research Current Work And Fresh-Session Handoff

Date: 2026-08-27

Current branch: `main`

Latest pushed checkpoint before this handoff document: `7d58f58 preserve invalid output reasons`

## Read This First In A Fresh Session

Read these documents in order:

1. `docs/superpowers/plans/2026-08-27-research-current-work-and-handoff.md`
2. `docs/superpowers/plans/2026-08-27-adk-gemini-tool-surface-mismatch-handoff.md`
3. `docs/superpowers/plans/2026-08-27-research-provider-compatibility-spike-findings.md`
4. `docs/superpowers/plans/2026-08-27-invalid-output-reason-handoff-pass-findings.md`
5. `docs/superpowers/plans/2026-08-27-research-grounded-claim-normalization-plan.md`
6. `docs/superpowers/plans/2026-08-27-research-official-source-policy-plan.md`
7. `docs/superpowers/plans/2026-08-27-research-tool-invalid-output-findings-and-plan.md`
8. `docs/superpowers/plans/2026-08-27-adk-gemini-research-tool-root-issues-and-research-plan.md`

Then inspect these source files:

1. `research_expert.py`
2. `research_expert_service.py`
3. `agent_col_expert_executor_v3.py`
4. `agent_col_responder_context_v3.py`
5. `research_provider_compatibility_check.py`
6. `tests/test_research_expert.py`
7. `tests/test_research_expert_service.py`
8. `tests/test_agent_col_expert_executor_v3.py`
9. `tests/test_agent_col_responder_context_v3.py`

Manual evidence lives under `scrnshot-evidence/`. The most relevant recent evidence is the user's copied manual prompt output in the conversation immediately preceding this handoff:

- OpenAI official documentation prompt: completed with citations, but included non-official domains in the citation/action list.
- Python official release prompt: first attempt failed closed with `invalid_output`, second attempt completed with `python.org` citations.
- Omarchy official install prompt: completed with `omarchy.org` plus unrelated social/video/blog/vendor sources.

## Committed Work

### `735d879 document research provider compatibility recheck`

Documented the conclusion that the next real issue was provider/tool-surface compatibility and Research failure semantics, not collaboration continuity.

### `3553325 checkpoint research provider compatibility spike`

Added:

- `research_provider_compatibility_check.py`
- `tests/test_research_provider_compatibility_check.py`
- `docs/superpowers/plans/2026-08-27-research-provider-compatibility-spike-findings.md`

Key finding:

- ADK Research Service completed with grounding metadata.
- Direct `generate_content` with `google_search` completed with grounding metadata.
- Interactions returned HTTP 400 on basic no-tool calls and on Search calls for this configured Vertex/Enterprise backend.

### `7d58f58 preserve invalid output reasons`

Added:

- content-safe `invalid_output_reason` field to the shared expert result contract;
- Research and Requirements Verification executor preservation for invalid-output reasons;
- responder-context instruction that failed expert results are non-authoritative and must not be replaced with fallback facts;
- findings doc and the grounded-claim normalization plan.

Key source files:

- `expert_contracts.py`
- `agent_col_expert_executor_v3.py`
- `agent_col_responder_context_v3.py`
- `tests/test_expert_contracts.py`
- `tests/test_agent_col_expert_executor_v3.py`
- `tests/test_agent_col_responder_context_v3.py`

## Uncommitted Work Pending Manual Verification

The grounded-claim normalization implementation is currently in the worktree and is not checkpointed as accepted implementation.

Changed files:

- `research_expert.py`
- `tests/test_research_expert.py`
- `tests/test_research_expert_service.py`

Behavior:

- `diagnose_grounded_research_text()` no longer rejects solely because valid provider grounding maps to more than 8 grounded claims.
- It now exposes the first 8 mappable claims as bounded findings.
- It preserves `grounding_support_count` as the original support count.
- It keeps fail-closed behavior for missing metadata, missing chunks, missing supports, invalid/private sources, unmappable supports, claims without source IDs, more than 5 sources for a claim, and more than 40 supports.

Verification already run for this uncommitted implementation:

```bash
venv/bin/pytest tests/test_research_expert.py::test_grounded_text_compacts_more_than_eight_supported_claims -q
```

Result:

```text
1 passed, 1 warning
```

```bash
venv/bin/pytest tests/test_research_expert_service.py::test_research_service_distinguishes_normalization_rejection_reason tests/test_research_expert_service.py::test_research_service_compacts_extra_valid_grounded_claims -q
```

Result:

```text
8 passed, 1 warning
```

```bash
venv/bin/pytest tests/test_research_expert.py tests/test_research_expert_service.py tests/test_research_provider_compatibility_check.py -q
```

Result:

```text
86 passed, 1 warning
```

```bash
git diff --check
```

Result: clean.

Live provider probe after the uncommitted normalization pass:

```text
adk-research-service: completed with grounding_metadata=true
generate-content-google-search: completed with grounding_metadata=true
interactions-basic/search/forced 3.6 and 3.7: BadRequestError api_status=400
```

## Manual Test Assessment

The user's three manual prompt results do not prove full acceptance of the Research work. They show partial success and one remaining defect class.

### OpenAI official-docs prompt

Prompt asked for official OpenAI Python SDK installation instructions and Responses API usage from a FastAPI backend.

Observed:

- Response completed.
- It cited `openai.com` and `github.com`.
- The action/citation list also included `microsoft.com`, `datacamp.com`, `sparrow.so`, and `medium.com`.

Verdict:

- Not a clean success for "official OpenAI documentation."
- This shows the Research path can produce citations, but it does not enforce official-source constraints.

### Python official-release prompt

Prompt asked for current stable Python release using official Python docs.

Observed first attempt:

- Research lookup returned `invalid_output`.
- Response failed closed and did not provide fallback version numbers or fake citations.

Observed second attempt:

- Response completed with `python.org` citations.
- It reported Python 3.14.7 as the latest stable patch release.

Verdict:

- Partial success.
- The failed attempt shows the previous no-fallback boundary is working.
- The successful retry suggests the grounded-claim normalization pass is directionally useful, but a single manual retry does not prove complete reliability.

### Omarchy official-install prompt

Prompt asked for official Omarchy installation instructions.

Observed:

- Response completed.
- It included `omarchy.org`.
- It also included `facebook.com`, `slimbook.com`, `travis.media`, and `youtube.com`.

Verdict:

- Not a clean success for "official project documentation."
- This is the clearest evidence for the next pass: official-source policy enforcement.

## Current Conclusion

The work has improved the failure mode:

- Failed Research can now fail closed without fallback facts.
- Invalid-output reasons can survive into responder context.
- Valid but verbose grounded support can be compacted locally instead of rejected solely as `too_many_grounded_claims`.

The remaining defect is not "Google Search did not run" in every case. The remaining defect is that Search can return mixed public sources, and Agent Col currently has no source policy that distinguishes official documentation requests from broad public research.

## Recommended Next Pass

Implement `docs/superpowers/plans/2026-08-27-research-official-source-policy-plan.md`.

Smallest scope:

1. Add a request-scoped `ResearchSourcePolicy`.
2. Derive it only for explicit official-doc/source requests.
3. Enforce allowed domains inside Research normalization.
4. Add a content-safe `official_source_policy_mismatch` invalid-output reason.
5. Keep broad public research unchanged.

Do not migrate to AgentTool or Interactions in that pass.

## Rollback Notes

To discard the currently uncommitted grounded-claim normalization implementation:

```bash
git restore research_expert.py tests/test_research_expert.py tests/test_research_expert_service.py
```

To revert the latest pushed checkpoint before this documentation handoff:

```bash
git revert 7d58f58
```

After this documentation handoff is checkpointed, use `git log -1 --oneline` to capture the new checkpoint SHA before starting the next implementation pass.
