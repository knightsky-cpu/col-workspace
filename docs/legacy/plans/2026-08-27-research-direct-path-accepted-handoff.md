# Research Direct Path Accepted Handoff

Date: 2026-08-27

This handoff is for a fresh Agent Col session picking up the Gemini/Search Research reliability work after the direct grounded Research path was manually verified and checkpointed.

## Current Git State

Accepted implementation checkpoint:

```text
5ca8b6a use direct grounded research generation
```

Recent checkpoint chain:

```text
5ca8b6a use direct grounded research generation
a755146 document direct research grounding plan
91ba0ea revise research source disclaimer
27454e5 document research source policy evidence
6db8eb0 document research source policy handoff
7d58f58 preserve invalid output reasons
3553325 checkpoint research provider compatibility spike
735d879 document research provider compatibility recheck
```

Working tree after checkpoint:

```text
main...origin/main
?? .agents/
```

`.agents/` is untracked and was intentionally not staged.

## What We Were Trying To Fix

The Research path was unreliable for user prompts that clearly required current web evidence. The failures had several distinct causes and should not be collapsed into one vague "research failed" issue.

Primary symptoms observed:

- Official-source prompts sometimes failed with `official_source_policy_mismatch`.
- Omarchy and Python prompts later failed with `missing_grounding_chunks`.
- OpenAI official-doc prompts sometimes caused full `/api/chat` turn timeout and returned HTTP 504.
- Broad public research usually worked.

The work direction is to make Research reliable enough for Agent Col to answer current external factual questions with citations, while staying honest about Google Search results not being guaranteed official documentation.

## Accepted Work Completed

### 1. Invalid-output reason preservation

Checkpoint:

```text
7d58f58 preserve invalid output reasons
```

Outcome:

- Failed Research Expert outputs now preserve content-safe invalid-output reasons into executor/responder context.
- This made failures diagnosable as `missing_grounding_metadata`, `missing_grounding_chunks`, `too_many_sources_for_claim`, etc.

Read:

- `expert_contracts.py`
- `agent_col_expert_executor_v3.py`
- `agent_col_responder_context_v3.py`
- `tests/test_agent_col_expert_executor_v3.py`
- `tests/test_agent_col_responder_context_v3.py`
- `docs/superpowers/plans/2026-08-27-invalid-output-reason-handoff-pass-findings.md`

### 2. Grounded-claim compaction

Checkpoint:

```text
91ba0ea revise research source disclaimer
```

Outcome:

- Valid grounded text with more than 8 mappable claims is compacted to the first 8 findings.
- The original provider `grounding_support_count` is preserved.
- More than 40 grounding supports still fails closed.

Read:

- `research_expert.py`
- `tests/test_research_expert.py`
- `tests/test_research_expert_service.py`
- `docs/superpowers/plans/2026-08-27-research-grounded-claim-normalization-plan.md`

### 3. Removed hard official-source policy

Checkpoint:

```text
91ba0ea revise research source disclaimer
```

Outcome:

- The hard local official-source allowlist was removed.
- Source scan after the pass had no `ResearchSourcePolicy`, `source_policy`, `official_source_policy_mismatch`, or `derive_research_source_policy` references outside docs/venv/git.
- The policy was the wrong fix because Vertex grounding redirect URLs made local domain matching brittle, and because useful unofficial public context should remain available when the user asks for broad research.

User-visible replacement:

- The responder now plainly states that Google Search-grounded public web research is not guaranteed official documentation and that cited sources should be verified before treating them as official.

Read:

- `agent_col_responder.py`
- `tests/test_agent_col_responder.py`
- `docs/superpowers/plans/2026-08-27-research-official-source-evidence-findings.md`
- `docs/superpowers/plans/2026-08-27-research-official-source-policy-plan.md`

Important context:

- `2026-08-27-research-official-source-policy-plan.md` is now historical. Do not implement that hard policy as written.
- The accepted direction is disclaimer plus source/citation transparency, not local official-source rejection.

### 4. Direct grounded Research generation

Checkpoint:

```text
5ca8b6a use direct grounded research generation
```

Outcome:

- `ResearchExpertService.from_vertex_settings()` now configures a direct `google.genai.Client`.
- Production Research uses `client.aio.models.generate_content(...)` with `types.Tool(google_search=types.GoogleSearch())`.
- The old ADK runner path remains as a compatibility fallback when no direct client is supplied.
- Direct Research uses a concise prompt, not the long ADK agent instruction.
- Direct Research uses `temperature=0.0`.
- Direct Research retries once if the first provider response is ungrounded due:
  - `missing_grounding_metadata`
  - `missing_grounding_chunks`
  - `missing_grounding_supports`
- The second failure still fails closed; the service does not substitute fallback facts.

Read:

- `research_expert_service.py`
- `tests/test_research_expert_service.py`
- `research_expert.py`
- `docs/superpowers/plans/2026-08-27-direct-google-search-research-path-plan.md`

Focused verification before checkpoint:

```text
venv/bin/pytest tests/test_research_expert.py tests/test_research_expert_service.py tests/test_agent_col_expert_executor_v3.py tests/test_agent_col_responder_context_v3.py tests/test_agent_col_responder.py -q
120 passed, 1 existing ADK deprecation warning

git diff --check
clean
```

Manual verification accepted by user:

- Omarchy install prompt succeeded with citations and disclaimer.
- Python stable release prompt succeeded with `python.org` citations.
- OpenAI SDK/FastAPI prompt succeeded with citations and disclaimer.
- General Henry the Great lookup succeeded with public citations.
- Calculus limit definition direct-answer path remained capable, but it did not call Research or provide live citations; that is expected unless routing selects Research.

## Important Live Evidence

### Before direct path

The same Omarchy prompt could produce:

```text
adk_research_service status=invalid_output invalid_output_reason=missing_grounding_chunks
generate_content status=completed grounding_metadata=true grounding_chunks=14 grounding_supports=26
```

Inference:

- Google Search could find and ground Omarchy.
- The unreliable component was the ADK `Agent` / `Workflow` Research surface or the prompt/config around it, not Google Search itself.

### During direct-path implementation

A first direct service implementation still produced intermittent `missing_grounding_chunks` with the long ADK agent instruction and `temperature=1.0`, while a bare direct prompt grounded.

Variant probe:

```text
bare temp=0.0 metadata=True chunks=9 supports=26
bare temp=1.0 metadata=True chunks=9 supports=27
production temp=0.0 metadata=True chunks=6 supports=11
production temp=1.0 metadata=True chunks=8 supports=25
```

Concise prompt probe:

```text
concise-1 metadata=True chunks=6 supports=23
concise-2 metadata=True chunks=10 supports=24
concise-3 metadata=True chunks=8 supports=25
```

Accepted implementation therefore uses:

- concise direct prompt;
- `temperature=0.0`;
- one retry on ungrounded provider response.

### After direct path

Live metadata probes completed with grounded Research service output:

```text
Omarchy: grounding_metadata=true grounding_chunks=3 grounding_supports=5
Python:  grounding_metadata=true grounding_chunks=5 grounding_supports=8
OpenAI:  grounding_metadata=true grounding_chunks=7 grounding_supports=9
```

Diagnostic caveat:

- `research_provider_compatibility_check.py` still labels the production service probe as `adk-research-service` / `adk_research_service`.
- That label is now stale because `ResearchExpertService.from_vertex_settings()` uses direct generation.

## Source Files Fresh Session Should Review First

Read these in order:

1. `AGENTS.md`
   - Approval-gated workflow, TDD requirement, manual verification gate, explicit-path Git staging.
2. `research_expert_service.py`
   - Current production Research execution surface.
3. `research_expert.py`
   - Grounding metadata normalization, public source validation, finding/source payloads, compaction behavior.
4. `agent_col_expert_executor_v3.py`
   - How Research service results become responder context and citation receipts.
5. `agent_col_responder_context_v3.py`
   - Failed expert context and citation/action serialization.
6. `agent_col_responder.py`
   - Final responder instructions, including Google Search official-doc disclaimer.
7. `agent_col_turn_service.py`
   - Turn-level budget and timeout handling.
8. `main.py`
   - `/api/chat` HTTP mapping for timeouts and partial failures.
9. `research_provider_compatibility_check.py`
   - Live metadata probe; useful but currently has stale service-surface labels.

Relevant tests:

1. `tests/test_research_expert_service.py`
2. `tests/test_research_expert.py`
3. `tests/test_agent_col_expert_executor_v3.py`
4. `tests/test_agent_col_responder_context_v3.py`
5. `tests/test_agent_col_responder.py`
6. `tests/test_main.py`
7. `tests/test_agent_col_turn_service.py`
8. `tests/test_research_provider_compatibility_check.py`

## Documentation Fresh Session Should Review

Start with:

1. `docs/superpowers/plans/2026-08-27-direct-google-search-research-path-plan.md`
   - The plan that led to checkpoint `5ca8b6a`.
2. `docs/superpowers/plans/2026-08-27-research-current-work-and-handoff.md`
   - Earlier handoff context.
3. `docs/superpowers/plans/2026-08-27-adk-gemini-tool-surface-mismatch-handoff.md`
   - Tool surface mismatch and ADK/Gemini research background.
4. `docs/superpowers/plans/2026-08-27-research-provider-compatibility-recheck-findings.md`
   - Provider compatibility observations.
5. `docs/superpowers/plans/2026-08-27-research-provider-compatibility-spike-findings.md`
   - Original spike findings.
6. `docs/superpowers/plans/2026-08-27-invalid-output-reason-handoff-pass-findings.md`
   - Why invalid-output reasons were preserved.
7. `docs/superpowers/plans/2026-08-27-research-grounded-claim-normalization-plan.md`
   - Claim compaction rationale.
8. `docs/superpowers/plans/2026-08-27-research-official-source-evidence-findings.md`
   - Official-source research evidence.
9. `docs/superpowers/plans/2026-08-27-research-official-source-policy-plan.md`
   - Historical plan only; do not treat as current implementation direction.
10. `docs/superpowers/plans/2026-08-27-adk-gemini-research-tool-root-issues-and-research-plan.md`
    - Broader root issue research plan.

## Official Documentation To Review

The earlier source-backed direction relied on these official docs:

- Google Cloud Gemini Enterprise Agent Platform: Grounding with Google Search
  - `https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-google-search`
- Google Cloud Gemini Enterprise Agent Platform SDK overview
  - `https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/sdks/overview`
- ADK Google Search grounding docs
  - `https://adk.dev/grounding/google_search_grounding/`
- ADK AgentTool docs if returning to sub-agent/tool propagation
  - Specifically review `AgentTool(..., propagate_grounding_metadata=True)`.

For any new claim about current Gemini, ADK, Interactions, or OpenAI API behavior, verify official docs again. These surfaces are moving targets.

## Remaining Work On This Research Tool Surface

### Priority 1: Rename / correct compatibility probe labels

Problem:

- `research_provider_compatibility_check.py` still calls the production Research service probe `adk-research-service` and surface `adk_research_service`.
- After `5ca8b6a`, that is misleading.

Recommended pass:

- Rename the probe to something like `research-service-production`.
- Rename or broaden `ProbeSurface` from `adk_research_service` to `research_service`.
- Update `tests/test_research_provider_compatibility_check.py`.
- Keep historical docs as-is; only fix the live diagnostic script.

Risk:

- Low. Diagnostic/reporting only.

### Priority 2: Add a small live smoke command for accepted prompts

Problem:

- Manual prompt acceptance is currently UI-observed.
- The metadata probe is useful but does not exercise the full `/api/chat` responder path.

Recommended pass:

- Add or update a smoke script that can run the four accepted prompt classes against `/api/chat` and report only safe metadata:
  - HTTP status
  - timeout or not
  - action/citation count
  - whether citation domains are present
  - no private full answer text in logs

Risk:

- Medium if it touches auth/session handling.
- Keep it diagnostic-only unless user approves production behavior changes.

### Priority 3: Monitor turn timeout after direct Research

Problem:

- The direct Research path reduces one expensive/unstable layer, but `Agent_Col` can still hit the outer 90-second timeout if routing + Research + responder generation exceed the budget.

Source to inspect:

- `agent_col_turn_service.py`
  - `TURN_TIMEOUT_SECONDS = 90.0`
  - `TURN_EXPERT_BUDGET_SECONDS = 45.0`
  - `TURN_RESPONDER_RESERVE_SECONDS = 20.0`
- `main.py`
  - `_log_chat_turn_timeout`
  - `/api/chat` timeout HTTP 504 mapping

Recommended pass:

- Instrument safe elapsed-time metadata per stage:
  - routing duration
  - expert duration
  - responder duration
  - final status
- Do not log prompt text or model output.

Risk:

- Medium. Logging/telemetry can leak data if careless.

### Priority 4: Revisit retry policy only with evidence

Current direct Research retries once for missing grounding metadata/chunks/supports.

Do not add broad retries blindly.

Only revisit if live evidence shows:

- provider 429/5xx;
- repeated missing grounding on first attempt but success on second;
- repeated missing grounding on both attempts;
- turn timeout caused by retries.

Possible future options:

- retry once only on missing grounding, current accepted state;
- make retry count configurable;
- use shorter `max_output_tokens`;
- reduce answer verbosity at Research layer and let responder format final output.

## Other Tool Surfaces Still Needing Inspection

### Interactions API surface

Current probe evidence:

```text
interactions-basic-3.6 status=error error_class=BadRequestError api_status=400
interactions-google-search-3.6 status=error error_class=BadRequestError api_status=400
interactions-basic-3.7 status=error error_class=BadRequestError api_status=400
interactions-google-search-3.7 status=error error_class=BadRequestError api_status=400
interactions-forced-extra-body-google-search-3.7 status=error error_class=BadRequestError api_status=400
```

Status:

- Not resolved.
- Not needed for the accepted Research fix.

Next investigation:

- Verify current official Interactions API request shape for Vertex/Gemini Enterprise.
- Inspect whether model names `gemini-3.6-flash` and `gemini-3.7-flash` are valid for that surface.
- Check if `tools=[{"type": "google_search"}]` is valid there or if Search grounding is only exposed differently.
- Keep this read-only until a source-backed implementation plan exists.

### AsyncChat / AFC warning surface

Observed warning:

```text
Direct use of automatic function calling (AFC) in AsyncModels.generate_content is not recommended. Instead, we recommend to use AFC in AsyncChat.send_message.
```

Status:

- Not resolved.
- Direct `generate_content` works for Google Search grounding but emits the warning.

Important distinction:

- The warning is about automatic function calling style.
- It is not the same as missing grounding.
- Do not switch to `AsyncChat.send_message` without official-doc verification and live metadata evidence that grounding metadata is preserved and normalizable.

Next investigation:

- Official docs for `AsyncChat.send_message` with Google Search grounding.
- Whether response objects expose the same `candidates[0].grounding_metadata`.
- Whether using chat avoids warning without regressing citations.

### ADK Agent / Workflow surface

Status:

- Production Research no longer depends on this surface when built with `from_vertex_settings`.
- The old runner path remains as a fallback/test compatibility path when no direct client is supplied.

Risk:

- The fallback path can still show intermittent missing grounding if used accidentally.

Next investigation:

- Decide whether to delete the fallback path in a later cleanup or keep it for test compatibility.
- If kept, rename comments/docstrings so it is clear production uses direct generation.

### AgentTool propagation surface

Status:

- Not currently used for Research.
- Earlier docs note `AgentTool(..., propagate_grounding_metadata=True)` if Research ever becomes a sub-agent tool again.

Next investigation:

- Only relevant if architecture moves back to sub-agent/tool composition.
- Do not mix into direct Research stabilization unless explicitly approved.

## What Not To Do Next

- Do not reintroduce hard official-source policy enforcement.
- Do not claim Google Search citations are guaranteed official docs.
- Do not use unsourced fallback facts when Research fails.
- Do not broaden retries or timeouts without evidence.
- Do not checkpoint source work before manual verification.
- Do not stage `.agents/` unless the user explicitly asks.

## Suggested Next Pass

Recommended next source-changing pass:

```text
Diagnostic cleanup: rename research_provider_compatibility_check.py's production service probe away from stale ADK labels and add a regression test for the new report label.
```

Why this next:

- It is small.
- It removes misleading evidence labels before further research.
- It reduces the chance a fresh session misreads "adk-research-service" as still using the old ADK workflow path.

Expected files:

- `research_provider_compatibility_check.py`
- `tests/test_research_provider_compatibility_check.py`

Focused verification:

```bash
venv/bin/pytest tests/test_research_provider_compatibility_check.py -q
git diff --check
```

Manual check:

```bash
venv/bin/python research_provider_compatibility_check.py --prompt "What are the current official installation instructions for Omarchy on a Linux machine as of today, August 27, 2026? Please verify against the official project documentation before answering and cite the sources you used."
```

Expected:

- First probe label should no longer say ADK.
- Grounding metadata counts should still be reported.

Approval is required before implementing that pass.
