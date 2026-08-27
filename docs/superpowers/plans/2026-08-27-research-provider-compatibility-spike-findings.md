# Research Provider Compatibility Spike Findings

Date: 2026-08-27

Checkpoint base before this spike: `735d879 document research provider compatibility recheck`

## Scope

This was a backend-only compatibility spike for the Research provider failure path. It intentionally avoided frontend application testing and avoided logging generated research text, raw provider answers, source URLs, raw prompts beyond the static probe prompt, or full provider error bodies.

The spike tested these surfaces:

- Current production ADK `ResearchExpertService`.
- Direct GenAI `models.generate_content` with `google_search`.
- GenAI Interactions with no tools.
- GenAI Interactions with `google_search`.
- GenAI Interactions with forced `tool_choice` sent through `extra_body`.

## Source Evidence

The executable spike is in `research_provider_compatibility_check.py`.

- `ResearchProviderObservation.to_report_line()` emits only metadata counters and sanitized error class/status.
- `summarize_generate_content_response()` counts candidates, grounding metadata, chunks, supports, and the existing local invalid-output diagnosis.
- `summarize_interaction()` counts Interactions steps and URL citation annotations without logging model output.
- `summarize_probe_error()` logs exception class and API status only.
- `run_research_provider_compatibility_check()` runs the ADK service, direct `generate_content`, and Interactions matrix from the same local Vertex settings.

The regression tests are in `tests/test_research_provider_compatibility_check.py`.

- `test_generate_content_summary_reports_metadata_without_text` proves generated answer text and source URL text are not emitted in report lines.
- `test_interaction_summary_counts_search_steps_and_annotations` proves Interactions step counters and citation annotation counters are summarized without model text.
- `test_probe_error_summary_reports_only_exception_class` proves raw exception text is not emitted.

## Live Provider Evidence

Command:

```bash
venv/bin/python research_provider_compatibility_check.py
```

Live output:

```text
research-provider probe=adk-research-service surface=adk_research_service status=completed error_class=none api_status=none candidates=0 grounding_metadata=true grounding_chunks=5 grounding_supports=3 steps=none google_search_calls=0 google_search_results=0 model_outputs=0 annotations=0 invalid_output_reason=none
research-provider probe=generate-content-google-search surface=generate_content status=completed error_class=none api_status=none candidates=1 grounding_metadata=true grounding_chunks=3 grounding_supports=8 steps=none google_search_calls=0 google_search_results=0 model_outputs=0 annotations=0 invalid_output_reason=none
research-provider probe=interactions-basic-3.6 surface=interactions status=error error_class=BadRequestError api_status=400 candidates=0 grounding_metadata=false grounding_chunks=0 grounding_supports=0 steps=none google_search_calls=0 google_search_results=0 model_outputs=0 annotations=0 invalid_output_reason=none
research-provider probe=interactions-google-search-3.6 surface=interactions status=error error_class=BadRequestError api_status=400 candidates=0 grounding_metadata=false grounding_chunks=0 grounding_supports=0 steps=none google_search_calls=0 google_search_results=0 model_outputs=0 annotations=0 invalid_output_reason=none
research-provider probe=interactions-basic-3.7 surface=interactions status=error error_class=BadRequestError api_status=400 candidates=0 grounding_metadata=false grounding_chunks=0 grounding_supports=0 steps=none google_search_calls=0 google_search_results=0 model_outputs=0 annotations=0 invalid_output_reason=none
research-provider probe=interactions-google-search-3.7 surface=interactions status=error error_class=BadRequestError api_status=400 candidates=0 grounding_metadata=false grounding_chunks=0 grounding_supports=0 steps=none google_search_calls=0 google_search_results=0 model_outputs=0 annotations=0 invalid_output_reason=none
research-provider probe=interactions-forced-extra-body-google-search-3.7 surface=interactions status=error error_class=BadRequestError api_status=400 candidates=0 grounding_metadata=false grounding_chunks=0 grounding_supports=0 steps=none google_search_calls=0 google_search_results=0 model_outputs=0 annotations=0 invalid_output_reason=none
```

Additional diagnostic matrix, using a non-private prompt and sanitized truncated provider detail:

```text
basic-36: error class=BadRequestError status=400 detail=Unsupported model interaction: gemini-3.6-flash
basic-37: error class=BadRequestError status=400 detail=Unsupported model interaction: gemini-3.7-flash
search-36: error class=BadRequestError status=400 detail=Unsupported model interaction: gemini-3.6-flash
search-37: error class=BadRequestError status=400 detail=Unsupported model interaction: gemini-3.7-flash
forced-top-37: error class=TypeError status=None detail=create() got unexpected keyword argument(s): tool_choice. Use extra_body=... to send additional request body fields.
forced-genconfig-37: error class=BadRequestError status=400 detail=Unsupported model interaction: gemini-3.7-flash
basic-models-37: error class=BadRequestError status=400 detail=Unsupported model interaction: models/gemini-3.7-flash
search-models-37: error class=BadRequestError status=400 detail=Unsupported model interaction: models/gemini-3.7-flash
forced-extra-body-37: error class=BadRequestError status=400 detail=Unknown parameter 'tool_choice'.
```

## Interpretation

The important result is that Interactions failed before `google_search` mattered. Basic no-tool Interactions calls returned HTTP 400 on both `gemini-3.6-flash` and `gemini-3.7-flash` for the currently configured Vertex/Enterprise backend. Grounding chunk and support counts can vary between live runs; the stable signal is that ADK Research and direct `generate_content` completed with grounding metadata, while Interactions returned 400 for every tested shape. That rules out an immediate Interactions migration as the smallest credible production fix.

Current ADK Research Service completed with grounding evidence in the same run. Direct `generate_content` with `google_search` also completed with grounding metadata. Therefore, the provider can produce Search grounding through the existing generateContent-era surface.

The failed Research behavior should not be treated as proof that more layered validation is needed. The live spike supports the opposite: the next fix should reduce brittle failure behavior and improve lossless failure handoff. The current validation may still be useful as a safety boundary, but adding more validation around a provider/runtime compatibility issue is likely to increase false negatives.

## Official Documentation Contrast

Official docs support the user's original concern that tool surfaces matter:

- ADK documents `AgentTool(..., propagate_grounding_metadata=True)` for preserving grounding metadata when a search-capable specialist is exposed as a tool.
- ADK and Gemini docs describe `google_search` as model-managed; adding the built-in Search tool does not guarantee every call will execute Search.
- Gemini Interactions docs describe explicit step visibility and `tool_choice` concepts, which would be attractive for deterministic Search-path diagnostics.
- The installed SDK/backend combination in this repo does not currently make Interactions usable through the configured Vertex/Enterprise backend, so the official Interactions path is not a near-term production fix without changing provider/backend configuration.

## Current Verdict

Confirmed:

- Backend-only automated provider testing is feasible and saves application-test cycles.
- The current provider settings can return Google Search grounding through ADK Research Service.
- The current provider settings can return grounding metadata through direct `generate_content`.
- Interactions is not available on the current configured Vertex/Enterprise backend, even without tools.
- Forced Interactions tool choice is not currently accepted through the tested SDK/backend request paths.

Not confirmed:

- That AgentTool migration would fix the current production failure.
- That Interactions can be used from this repo without changing provider/backend configuration.
- That additional validation would improve the failure rate.

## Recommended Smallest Production Fix

Do not switch the production Research path to AgentTool or Interactions yet.

The smallest next implementation should:

1. Preserve `ResearchExpertServiceError.invalid_output_reason` when the executor converts service errors to `ResearchExpertResult`.
2. Preserve the same failure reason for requirements verification, which already has the same error object shape and the same executor loss.
3. Add responder-context failure language that says failed expert output is non-authoritative and must not be replaced by unsourced factual fallback.
4. Relax only the brittle local normalization rule that over-penalizes supported grounded claims, if a targeted regression test proves the current rule rejects provider-grounded output with valid metadata.
5. Keep the backend provider compatibility probe as an on-demand diagnostic, not a runtime dependency.

This plan addresses the real lossy boundary and validation brittleness without adding another validation layer and without betting production behavior on an unavailable Interactions backend.

## Verification

Commands run:

```bash
venv/bin/pytest tests/test_research_provider_compatibility_check.py -q
venv/bin/pytest tests/test_research_provider_compatibility_check.py tests/test_research_expert.py tests/test_research_expert_service.py -q
git diff --check
```

Results:

- `tests/test_research_provider_compatibility_check.py`: 3 passed, 1 deprecation warning.
- Focused Research test set: 85 passed, 1 deprecation warning.
- `git diff --check`: clean.

## Rollback

To return the local checkout to the previous checkpoint before this spike:

```bash
git reset --hard 735d879
```

For the pushed repository, prefer a normal `git revert` of the resulting spike checkpoint commit instead of rewriting `origin/main`.
