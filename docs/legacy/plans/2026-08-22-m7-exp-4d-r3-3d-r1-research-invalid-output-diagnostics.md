# M7-EXP.4D-R3.3D-R1 Research Invalid-Output Diagnostics

## Goal

Identify why a live Research attempt fails local evidence validation without
logging or returning user content, provider content, URLs, identifiers, or
model output.

## Approved boundary

- Preserve `invalid_output` as the public expert status.
- Preserve the HTTP `200` contained-degradation response when Agent_Col can
  safely explain that no validated evidence was returned.
- Preserve fail-closed receipt behavior: rejected Research output creates no
  `google_search` action and no citations.
- Add stable internal reason codes only at the Research normalization and
  service boundaries.
- Log only the stable reason code.
- Do not change routing, provider configuration, retries, timeouts, Firestore,
  schemas, dependencies, or the responder contract.

## Diagnostic reasons

- `missing_final_event`
- `multiple_final_events`
- `missing_response_text`
- `missing_grounding_metadata`
- `missing_grounding_chunks`
- `no_valid_public_sources`
- `missing_grounding_supports`
- `too_many_grounding_supports`
- `no_mappable_grounding_claims`
- `too_many_grounded_claims`
- `grounded_claim_without_source`
- `too_many_sources_for_claim`
- `normalized_result_validation_failed`

## TDD targets

1. Invalid event streams expose the exact internal reason and log only that
   reason.
2. Every rejection branch reachable through the live Research service has a
   distinct reason.
3. Logs exclude request fields, provider titles, claims, URLs, and identifiers.
4. Existing normalized results, executor containment, receipts, and turn
   orchestration remain unchanged.

## Manual verification

Run the same current-information chat request through `/api/chat`. If Research
still fails, the application response remains safely degraded while the
Uvicorn terminal prints one line in this form:

```text
Research Expert output rejected (<reason_code>).
```

The line must contain no user prompt, URL, source title, identifier, or model
output. The reason code determines the smallest subsequent compatibility fix.

## Explicit exclusions

- No attempt to force Google Search.
- No provider retry changes.
- No relaxation of grounding or citation validation.
- No response-schema or HTTP-status changes.
- No fix for FastAPI's oversized-validation input echo in this pass.
