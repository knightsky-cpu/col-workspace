# Invalid Output Reason Handoff Pass Findings

Date: 2026-08-27

Checkpoint base before this pass: `3553325 checkpoint research provider compatibility spike`

## Scope

This pass implemented the smallest approved production fix after the provider compatibility spike:

- preserve content-safe invalid-output reasons across the expert service to executor boundary;
- include that reason in responder context serialization;
- harden responder context policy against unsourced fallback after failed expert verification;
- avoid AgentTool migration, Interactions migration, provider changes, and additional validation layers.

This pass did not change the Research provider topology and did not relax Research grounding validation.

## Source-Backed Problem

The prior source state dropped useful failure evidence:

- `ResearchExpertServiceError` carried `invalid_output_reason`, but `agent_col_expert_executor_v3.py` converted it to `ResearchExpertResult(status=exc.status)` and lost the reason.
- `RequirementsVerificationServiceError` had the same content-safe reason shape, but the executor converted it to `RequirementsVerificationResult(status=exc.status)` and lost the reason.
- `ExpertResult` had `extra="forbid"` and no diagnostic field, so preserving the reason required an explicit contract addition.
- `agent_col_responder_context_v3.py` told the responder not to fabricate receipts, but did not explicitly say failed expert output is non-authoritative and must not be replaced with fallback facts.

Manual failure evidence is also present under `scrnshot-evidence/`. The screenshots show the user-facing symptom class: failed tool/provider paths still yielded inadequate or incorrect application behavior. This pass focused on the backend source boundary that was directly proven by tests and source review.

## Implementation

Modified files:

- `expert_contracts.py`
  - Added `ExpertInvalidOutputReason`.
  - Added `invalid_output_reason: ExpertInvalidOutputReason | None = None` to `ExpertResult`.
  - Added validation that only `ExpertStatus.INVALID_OUTPUT` results may carry `invalid_output_reason`.
  - Preserved the existing invariant that noncompleted results cannot carry summary, limitations, payload, or evidence.

- `agent_col_expert_executor_v3.py`
  - Preserves Research invalid-output reasons when catching `ResearchExpertServiceError`.
  - Preserves Requirements Verification invalid-output reasons when catching `RequirementsVerificationServiceError`.
  - Converts enum-backed reasons to their string `.value` for content-safe serialized context.
  - Does not attach reasons to `unavailable`, `timed_out`, or `rejected_input`.

- `agent_col_responder_context_v3.py`
  - Adds the explicit responder boundary: failed expert results are non-authoritative and must not be replaced with fallback facts.

- `tests/test_expert_contracts.py`
  - Adds regression coverage that `INVALID_OUTPUT` can carry a safe reason.
  - Adds regression coverage that other statuses reject the reason.
  - Existing generic expert-result safety tests were preserved.

- `tests/test_agent_col_expert_executor_v3.py`
  - Adds regression coverage for Research reason preservation.
  - Adds regression coverage for Requirements Verification reason preservation.

- `tests/test_agent_col_responder_context_v3.py`
  - Adds regression coverage that serialized responder context contains the reason and the no-fallback failed-expert boundary.

## TDD Evidence

RED command:

```bash
venv/bin/pytest tests/test_expert_contracts.py tests/test_agent_col_expert_executor_v3.py::test_executor_v3_preserves_research_invalid_output_reason tests/test_agent_col_expert_executor_v3.py::test_executor_v3_preserves_verification_invalid_output_reason tests/test_agent_col_responder_context_v3.py::test_v3_responder_context_marks_failed_expert_as_non_authoritative -q
```

RED result:

```text
4 failed, 4 passed, 1 warning
```

Failure reasons were expected:

- `invalid_output_reason` was rejected as an extra field.
- `ResearchExpertResult` lacked `invalid_output_reason`.
- `RequirementsVerificationResult` lacked `invalid_output_reason`.
- Failed Research responder context could not serialize the missing reason.

GREEN result for the same command:

```text
8 passed, 1 warning
```

## Verification

Focused verification:

```bash
venv/bin/pytest tests/test_expert_contracts.py tests/test_agent_col_expert_executor_v3.py tests/test_agent_col_responder_context_v3.py tests/test_research_expert.py tests/test_requirements_verification.py -q
```

Result:

```text
178 passed, 1 warning
```

Adjacent context/probe verification:

```bash
venv/bin/pytest tests/test_agent_col_turn_service.py::test_failed_expert_context_adds_no_cognitive_receipt tests/test_research_provider_compatibility_check.py -q
```

Result:

```text
4 passed, 1 warning
```

Whitespace/static diff check:

```bash
git diff --check
```

Result: clean.

Full suite was not run because this pass changed a narrow expert-result diagnostic field, v3 executor failure conversion, and v3 responder context serialization. The focused tests cover those surfaces plus adjacent Research, Requirements Verification, turn-service failed-expert behavior, and the provider compatibility probe.

## Current Assessment

This pass fixes the proven lossy boundary. It does not claim to fix every observed Research failure.

What is now fixed:

- A Research `invalid_output` reason can survive into the normalized responder context.
- A Requirements Verification `invalid_output` reason can survive into the normalized responder context.
- Non-invalid statuses cannot carry this diagnostic field.
- The responder receives an explicit instruction not to replace failed expert evidence with fallback facts.

What remains open:

- The Research validator can still reject provider-grounded output when the provider returns more than 8 mappable grounded claims.
- The live provider spike showed direct `generate_content` and ADK Research can both return grounding metadata.
- Interactions remains unavailable on the configured Vertex/Enterprise backend and is not a near-term fix.

## Manual Verification Targets

Use the same user-facing flows that produced the screenshot evidence:

1. Ask for current official documentation verification where the Research provider previously returned `invalid_output`.
2. If the expert fails, verify the response reports the failed verification boundary instead of answering with unsourced fallback facts.
3. Confirm no citations or action receipts are fabricated for failed expert output.
4. Confirm a successful Research path still returns grounded answer behavior when provider metadata validates.

## Rollback

To return the local checkout to the checkpoint before this implementation pass:

```bash
git reset --hard 3553325
```

For the pushed repository, prefer reverting the resulting checkpoint commit instead of rewriting `origin/main`.
