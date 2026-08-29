# Research Tool Invalid Output Findings and Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Agent Col's Source/Research failure boundary so explicit verification requests do not produce generic unsourced fallback answers after an expert `invalid_output`.

**Architecture:** Routing can continue to select Source or Research, but failed expert execution must preserve a content-safe failure reason through executor, responder context, and final response policy. The responder should make the verification failure explicit and avoid unsupported current claims when citations are unavailable.

**Tech Stack:** FastAPI, Python, Pydantic, Google ADK, Gemini, Firestore, pytest.

**Spec:** This plan is based on read-only live Firestore inspection of `session--109ad178-eb1e-4572-b43e-6d81d906f7bf`, source review of the Research Expert path, and the user's manual end-to-end chatflow.

## Source-Backed Findings

### Finding 1: The previous fail-safe pass addressed the stuck-turn boundary

- `main.py` now catches unexpected exceptions after `turn_service.run_turn`, logs only the exception type, releases the active chat turn claim, and returns a bounded `500` response.
- `tests/test_main.py::test_chat_releases_claim_after_unexpected_turn_exception` verifies the claim is released, no completion is saved, and private exception content is not returned.
- Live Firestore inspection of the new end-to-end workspace showed the two reported research prompts completed with model messages rather than remaining stuck.

**Conclusion:** The previous pass succeeds for the intended stuck-turn error boundary. The new failure is a different boundary.

### Finding 2: The new end-to-end failure is a routed Research Expert invalid-output failure

Live Firestore inspection found the new chatflow under:

- `project_id`: `project--eb3e1d02bb1c9e01c59957622341f107--end-to-end`
- `session_id`: `session--109ad178-eb1e-4572-b43e-6d81d906f7bf`

Observed turns:

- OpenAI official documentation request: `status=completed`, empty `citations`, empty `actions`, model response says research lookup failed with `invalid_output`.
- Omarchy official documentation request: `status=completed`, empty `citations`, empty `actions`, model response says research lookup failed with `invalid_output`.

**Conclusion:** Routing likely selected a research-capable path. The failure is not a 500, not a stuck claim, and not a missing model response. It is a completed response after a failed research expert result.

### Finding 3: Research Expert is designed to fail closed when grounding is missing or unmappable

- `research_expert.py` instructs the bounded Research Expert to use Google Search and directly support every factual sentence with grounding.
- `research_expert.py` rejects research output when response text, grounding metadata, grounding chunks, grounding supports, valid public sources, or mappable grounded claims are missing.
- `research_expert_service.py` converts rejected normalized output into `ResearchExpertServiceError(ExpertStatus.INVALID_OUTPUT)` and retains only a content-safe invalid-output reason.

**Conclusion:** The `invalid_output` status is expected defensive behavior when provider output is not locally validatable.

### Finding 4: The executor drops the detailed invalid-output reason before responder handoff

- `agent_col_expert_executor_v3.py` catches `ResearchExpertServiceError`.
- It currently constructs `ResearchExpertResult(status=exc.status)` without preserving `exc.invalid_output_reason`.
- Failed research receipts produce empty actions and citations.

**Conclusion:** The responder sees a failed expert status but not the detailed reason. The UI and persisted turn records also lose useful diagnostic evidence.

### Finding 5: Responder policy is directionally correct but not strict enough in practice

- `agent_col_responder.py` instructs Agent Col that if context reports a failed expert, it should explain the limitation or ask how to proceed and should not make unsupported current claims.
- The live responses did explain the limitation, but then continued with generic unsourced guidance after explicit official-documentation verification failed.

**Conclusion:** The current responder instruction reduces overreach but does not reliably prevent unsourced fallback content after explicit verification failures.

## Proposed Implementation Pass

### Task 1: Preserve content-safe research failure reasons

**Files:**
- Modify: `research_expert.py`
- Modify: `agent_col_expert_executor_v3.py`
- Test: `tests/test_agent_col_expert_executor_v3.py`

**Interface:**
- Add an optional content-safe failure field to `ResearchExpertResult`, for example `failure_reason: ResearchInvalidOutputReason | None = None`.
- When `ResearchExpertServiceError.invalid_output_reason` is present, preserve it in the failed `ResearchExpertResult`.

- [ ] Write a failing executor test where `ResearchExpertServiceError(ExpertStatus.INVALID_OUTPUT, invalid_output_reason=ResearchInvalidOutputReason.MISSING_GROUNDING_METADATA)` becomes a responder context whose `expert_result.failure_reason` is `missing_grounding_metadata`.
- [ ] Run the single test and verify it fails because the reason is currently absent.
- [ ] Add the minimal model field and executor mapping.
- [ ] Rerun the single test and verify it passes.

### Task 2: Preserve content-safe source failure reasons if available

**Files:**
- Inspect/modify: `source_expert.py`
- Inspect/modify: `source_expert_service.py`
- Modify: `agent_col_expert_executor_v3.py`
- Test: `tests/test_agent_col_expert_executor_v3.py`

**Interface:**
- If `SourceExpertServiceError` exposes a content-safe invalid-output reason, preserve it similarly.
- If it does not expose one yet, defer Source reason preservation and document the gap rather than inventing a parallel enum in this pass.

- [ ] Write a failing test only if the source service already carries a safe reason.
- [ ] Implement the minimal mapping.
- [ ] Rerun the focused test.

### Task 3: Harden responder context wording for failed source/research routes

**Files:**
- Modify: `agent_col_responder_context_v3.py`
- Modify: `agent_col_responder.py`
- Test: `tests/test_agent_col_responder_context_v3.py`

**Behavior:**
- The server context should explicitly tell the responder that failed Source/Research results contain no validated citations.
- For explicit verification/current/official-doc requests, the responder must not provide general factual fallback content as though it were verified.
- The responder may offer safe next choices: retry, use a provided URL, or proceed explicitly without source verification.

- [ ] Write a failing context test that renders a failed research result and asserts the model context contains an explicit "no validated citations" / "do not provide source-backed claims" instruction.
- [ ] Run the test and verify it fails against the current context text.
- [ ] Add the minimal context wording and responder instruction.
- [ ] Rerun the focused context test.

### Task 4: Add a turn-service regression around failed research handoff

**Files:**
- Modify: `tests/test_agent_col_turn_service.py`

**Behavior:**
- A failed Research Expert result should complete the turn without stuck state, carry no citations, and pass a failed-expert context to the responder.
- The responder should receive failure context sufficient to produce a bounded verification-failed answer.

- [ ] Write a failing test using a recording responder that captures the rendered responder context for `research` plus `invalid_output`.
- [ ] Verify the captured context lacks the new failure reason before implementation.
- [ ] After Tasks 1-3, rerun and verify it passes.

## Focused Verification Commands

- `venv/bin/pytest tests/test_agent_col_expert_executor_v3.py -q`
- `venv/bin/pytest tests/test_agent_col_responder_context_v3.py -q`
- `venv/bin/pytest tests/test_agent_col_turn_service.py::test_failed_expert_context_adds_no_cognitive_receipt -q`
- `git diff --check`

Full suite is not required for this pass unless the model/result schema change causes broad import or validation failures in focused tests.

## Expected Results

- Explicit official-documentation/current-verification requests still route to Research or Source when appropriate.
- If the expert returns `invalid_output`, the turn completes without becoming stuck.
- The final answer clearly states that source verification failed and does not continue with unsourced current facts.
- The persisted turn remains content-safe while carrying enough structured status for debugging.

## Risks and Exclusions

- This pass does not fix the underlying provider/ADK/Gemini cause of `invalid_output`.
- This pass does not add a retry strategy.
- This pass does not replace Google Search grounding with a different research backend.
- A follow-up documentation review is required to determine whether the current ADK agent-as-tool architecture is correctly implemented.

## Manual Verification Targets

1. In the end-to-end workspace, ask: `What are the current official OpenAI API model names and recommended Python SDK usage for FastAPI as of today, August 27, 2026? Please verify against the official OpenAI documentation before answering.`
2. If research succeeds, expect citations and source-backed current facts.
3. If research fails, expect a bounded failure response with no generic unsourced model-list fallback.
4. Ask: `can you check the official documentation for installing omarchy on my linux machine`
5. If no official source is verified, expect Agent Col to say verification failed and ask whether to retry, use a URL, or proceed without verification.

## Proposed Follow-Up

After this pass, inspect official Google ADK, Google Gen AI SDK, Vertex AI, Gemini, grounding, and function/tool-calling documentation to determine whether the current Research Expert implementation matches supported framework patterns or is relying on a brittle/incorrect "agent as tool" path.
