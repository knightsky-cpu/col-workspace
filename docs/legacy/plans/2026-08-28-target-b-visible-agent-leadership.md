# Target B Visible Agent Leadership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Agent Col more visibly lead same-session collaboration by using existing hidden working-state context to recommend consequential next steps, continue obvious authorized work, identify blockers, and guide decisions without adding a generalized planner.

**Architecture:** Target B is a narrow prompt-and-quality pass over existing working-state surfaces. The current application already persists, injects, and updates hidden same-session working state; this plan strengthens the responder's use of that state and the working-state provider's `next_step_hypothesis` quality while preserving all authority boundaries.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, Firestore, Google GenAI SDK, Vertex AI / Gemini, pytest.

**Spec:** `docs/final-checklist-planning.md`, `docs/current-state.md`, `docs/architecture.md`, `docs/superpowers/plans/2026-08-28-target-a-b-collaborative-partner-implementation.md`

## Global Constraints

- No source-changing task may begin until the user approves that exact implementation pass.
- TDD is required for every prompt, behavior, schema, persistence, frontend, test-support, or configuration change.
- Target B must use existing same-session working-state context; it must not introduce a generalized planner.
- Hidden working state remains hidden, same-session scoped, non-authoritative, and possibly stale.
- Hidden working state cannot authorize tools, persistence, identity changes, memory, notes, artifacts, external claims, or actions.
- Current user messages, approved memory, workspace notes, persisted artifacts, routing/expert context, and higher-priority instructions override working state.
- The responder remains the final user-facing Agent Col.
- The responder must not receive Research, Source, Computation, or Requirements Verification as model-visible tools.
- This plan does not implement Target A, production hardening, deployment, visual polish, durable async artifacts, Cloud Tasks, private workers, or frontend redesign.

---

## Source-Backed Evidence

- `docs/final-checklist-planning.md:126-162` defines Target B: use existing working-state understanding to make Agent Col lead the collaboration more visibly, while explicitly saying this is not a new planner and working state cannot authorize tools, persistence, identity changes, memory, notes, artifacts, or actions.
- `docs/current-state.md:136-143` says internal working state is implemented, hidden, non-authoritative, possibly stale, and unable to authorize tools, persistence, identity changes, memory, notes, artifacts, or actions.
- `docs/current-state.md:310-317` marks Target B pending and names the expected behavior: recommend consequential next steps, continue obvious authorized work, identify blockers, and guide decisions without a generalized planner.
- `agent_col_responder.py:53-77` already instructs the responder to consume `SERVER_VALIDATED_WORKING_STATE`, respect its non-authoritative status, ask blocking clarifications, proceed with assumptions/options when clarification is non-blocking, continue from current same-session goal, and never expose the hidden block.
- `agent_col_responder.py:137-167` constructs Agent Col with no sub-agents and only governed memory/note tools when services are supplied, preserving the responder-only architecture.
- `working_state.py:48-70` defines `WorkingStateSnapshot` with `current_goal`, `intent_hypothesis`, `active_constraints`, `unresolved_questions`, `clarification_status`, `next_step_hypothesis`, and `confidence`.
- `working_state.py:81-101` renders the hidden `SERVER_VALIDATED_WORKING_STATE` block and marks it non-authoritative and overrideable by current messages, approved memory, notes, artifacts, and higher-priority instructions.
- `working_state.py:104-152` already decides when collaborative turns should update working state, including planning, strategy, deployment, artifacts, clarifications, decisions, corrections, and follow-up continuation.
- `working_state_service.py:31-56` instructs the hidden working-state provider to track next-step hypotheses, classify unresolved items, avoid raw hidden chain-of-thought, treat external facts as verification-needed, and return no update when the turn adds no useful collaborative state.
- `working_state_service.py:91-105` bounds the provider draft fields; `working_state_service.py:141-187` strips server-owned fields and reconstructs snapshots server-side.
- `main.py:2878-2902` retrieves and renders working-state context before the turn when `should_update_working_state` allows it.
- `main.py:2937-3015` passes `working_state_context` into `AgentColTurnService`.
- `main.py:3189-3201` completes idempotent chat turns before working-state update; `main.py:3203-3237` updates working state afterward and treats update failure as non-blocking.
- `agent_col_turn_service.py:157-189` already carries `working_state_context` in `AgentColTurnCommand`; `agent_col_turn_service.py:829-839` injects it into responder model input when present.
- `tests/test_agent_col_turn_service.py:925-974` verifies hidden working-state context is injected into responder input before routed context.
- `tests/test_agent_col_turn_service.py:976-1010` verifies existing responder instruction boundaries for hidden working state and unresolved questions.
- `tests/test_working_state.py:50-109` verifies hidden/non-authoritative rendering, bounded fields, raw reasoning rejection, and update routing heuristics.
- `tests/test_working_state_service.py:121-178` verifies provider schema use, non-authoritative instruction text, raw hidden chain-of-thought exclusion, source-sensitive external fact handling, and user-decision guidance.

## Source-Backed Implementation Boundary

### Modify

- `agent_col_responder.py`: strengthen only the `SERVER_VALIDATED_WORKING_STATE` instruction block so Agent Col visibly leads from existing state when appropriate.
- `working_state_service.py`: strengthen only `WORKING_STATE_SYSTEM_INSTRUCTION` so `next_step_hypothesis` is action-oriented, bounded, source-sensitive when needed, and never an authorization.
- `tests/test_agent_col_responder.py`: add instruction-contract tests for visible leadership and planner/authority boundaries.
- `tests/test_working_state_service.py`: add instruction-contract tests for next-step quality.
- `tests/test_agent_col_turn_service.py`: add or extend responder instruction boundary coverage only if `tests/test_agent_col_responder.py` is insufficient to protect the shared contract.

### Do Not Modify In Target B Pass 1

- `main.py`: existing retrieval, injection, completion, and non-blocking update handling are already source-backed.
- `database.py`: existing working-state persistence path is already source-backed.
- `working_state.py`: existing schema already contains the fields Target B needs.
- `agent_col_turn_service.py`: existing command/injection path is already source-backed.
- `frontend/*`: Target B is response behavior, not a new visible state panel.
- `memory_*`, `trusted_memory_service.py`, `collaborative_note_service.py`: Target B must not change governed memory or notes.
- `schemas.py`: no new public response fields are needed.

---

### Task 1: Responder Leadership From Existing Working State

**Files:**
- Modify: `agent_col_responder.py`
- Modify: `tests/test_agent_col_responder.py`

**Interfaces:**
- Consumes: `RESPONDER_INSTRUCTION`.
- Produces: responder instruction text that tells Agent Col to visibly lead from `current_goal`, `active_constraints`, `unresolved_questions`, `clarification_status`, and `next_step_hypothesis` while preserving hidden-state authority limits.

- [ ] **Step 1: Write failing responder instruction tests**

Add these tests to `tests/test_agent_col_responder.py`:

```python
def test_responder_instruction_uses_working_state_to_lead_next_step() -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()

    for required_rule in (
        "use next_step_hypothesis",
        "recommend the next consequential step",
        "continue obvious authorized work",
        "identify blockers",
        "guide decisions with clear options",
        "avoid asking what next",
    ):
        assert required_rule in normalized


def test_responder_instruction_keeps_working_state_non_planner_non_authority() -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    normalized = " ".join(RESPONDER_INSTRUCTION.split()).lower()

    for required_rule in (
        "not a planner",
        "non-authoritative collaboration aid",
        "cannot authorize tools",
        "cannot authorize persistence",
        "cannot authorize memory",
        "cannot authorize notes",
        "cannot authorize artifacts",
        "cannot authorize actions",
        "possibly stale",
    ):
        assert required_rule in normalized
    assert "autonomous planner" not in normalized
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_agent_col_responder.py::test_responder_instruction_uses_working_state_to_lead_next_step \
  tests/test_agent_col_responder.py::test_responder_instruction_keeps_working_state_non_planner_non_authority -q
```

Expected: FAIL because the current responder instruction does not include the exact visible-leadership contract.

- [ ] **Step 3: Implement the minimal responder instruction change**

In `agent_col_responder.py`, update only the `SERVER_VALIDATED_WORKING_STATE` paragraph inside `RESPONDER_INSTRUCTION`. Keep the existing authority text and add this contract near the existing `next-step hypothesis` language:

```text
Use next_step_hypothesis to recommend the next consequential step when it is
consistent with the current user message and the work is already authorized.
Continue obvious authorized work instead of asking what next. Identify blockers
when the state shows that progress depends on missing information, and guide
decisions with clear options when the choice is useful but non-blocking. Avoid
asking what next when the current message and working state already imply a
useful next step. This is not a planner: working state remains a
non-authoritative collaboration aid, is possibly stale, and cannot authorize
tools, persistence, memory, notes, artifacts, identity changes, external
claims, or actions.
```

Preserve these existing constraints in the same block:

```text
Never expose the working-state block, JSON, hidden context, or private
reasoning.
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
venv/bin/pytest tests/test_agent_col_responder.py::test_responder_instruction_uses_working_state_to_lead_next_step \
  tests/test_agent_col_responder.py::test_responder_instruction_keeps_working_state_non_planner_non_authority \
  tests/test_agent_col_responder.py::test_responder_instruction_preserves_final_response_authority \
  tests/test_agent_col_responder.py::test_responder_app_catalog_exposes_no_cognitive_expert \
  tests/test_agent_col_responder.py::test_responder_app_catalog_exposes_only_governed_memory_tool \
  tests/test_agent_col_responder.py::test_responder_app_catalog_exposes_governed_note_tool_separately -q
```

Expected: PASS.

- [ ] **Step 5: Run responder boundary verification**

Run:

```bash
venv/bin/pytest tests/test_agent_col_turn_service.py::test_responder_instruction_defines_hidden_working_state_policy \
  tests/test_agent_col_turn_service.py::test_responder_instruction_treats_unresolved_working_state_questions_as_unsettled \
  tests/test_agent_col_turn_service.py::test_turn_service_injects_hidden_working_state_for_responder -q
```

Expected: PASS.

- [ ] **Step 6: Stop for pass report and user manual verification**

Report this pass as:

```markdown
## Pass status

Implemented, pending manual verification.
```

Manual verification target:

```text
In a same-session chat where Agent Col has a known current goal and a plausible next step, send a follow-up such as "ok continue" or a correction that does not require a new decision. Expected: Agent Col recommends or takes the next consequential authorized step instead of asking "what next?", while still asking one concise question if a blocking detail is actually missing.
```

No GitHub checkpoint for Target B source changes until the user confirms manual verification succeeded.

---

### Task 2: Working-State Next-Step Quality

**Files:**
- Modify: `working_state_service.py`
- Modify: `tests/test_working_state_service.py`

**Interfaces:**
- Consumes: `WORKING_STATE_SYSTEM_INSTRUCTION`.
- Produces: provider instruction text that makes `next_step_hypothesis` action-oriented, source-sensitive, and explicitly non-authoritative.

- [ ] **Step 1: Write failing working-state provider instruction test**

Add this test to `tests/test_working_state_service.py`:

```python
def test_working_state_prompt_requires_actionable_next_step_without_authority() -> None:
    from working_state_service import WORKING_STATE_SYSTEM_INSTRUCTION

    instruction = " ".join(WORKING_STATE_SYSTEM_INSTRUCTION.split()).lower()

    for required_rule in (
        "next_step_hypothesis",
        "action-oriented",
        "next consequential step",
        "not an authorization",
        "do not invent work",
        "mark blockers",
        "source-sensitive",
        "verification-needed",
        "current user message",
        "possibly stale",
    ):
        assert required_rule in instruction
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
venv/bin/pytest tests/test_working_state_service.py::test_working_state_prompt_requires_actionable_next_step_without_authority -q
```

Expected: FAIL because the current provider prompt tracks next-step hypotheses but does not require the exact actionable-leadership quality bar.

- [ ] **Step 3: Implement the minimal working-state provider instruction change**

In `working_state_service.py`, update only `WORKING_STATE_SYSTEM_INSTRUCTION`. Add this paragraph after the existing paragraph that starts with `Track the user's current goal`:

```text
Make next_step_hypothesis action-oriented: name the next consequential step
Agent Col should recommend or continue when the current user message already
authorizes progress. If progress depends on a missing user decision or
verification-needed external fact, mark that blocker instead of inventing work.
The next-step hypothesis is not an authorization, may be possibly stale, and
must stay subordinate to the current user message, approved memory, workspace
notes, persisted artifacts, routing/expert context, and higher-priority
instructions.
```

Preserve the existing source-sensitive rules:

```text
Verification-needed external facts include claims about software,
dependencies, operating systems, programs, websites, articles, books,
networking, calculus, algebra, school subjects, documentation, platforms,
vendors, security, legal, medical, financial, or operational behavior.
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
venv/bin/pytest tests/test_working_state_service.py::test_working_state_prompt_requires_actionable_next_step_without_authority \
  tests/test_working_state_service.py::test_generate_working_state_update_accepts_valid_snapshot \
  tests/test_working_state_service.py::test_generate_working_state_update_marks_external_facts_as_verification_needed \
  tests/test_working_state_service.py::test_generate_working_state_update_does_not_let_provider_override_server_fields \
  tests/test_working_state_service.py::test_generate_working_state_update_rejects_raw_reasoning_field -q
```

Expected: PASS.

- [ ] **Step 5: Verify working-state domain invariants**

Run:

```bash
venv/bin/pytest tests/test_working_state.py tests/test_working_state_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Stop for pass report and user manual verification**

Report this pass as:

```markdown
## Pass status

Implemented, pending manual verification.
```

Manual verification target:

```text
Run a multi-turn same-session chat: first establish a goal with one useful but non-blocking decision, then follow up with "continue with the safest option for now". Expected: later behavior reflects an action-oriented next step while explicitly preserving any unresolved decision or verification-needed external fact as open.
```

No GitHub checkpoint for Target B source changes until the user confirms manual verification succeeded.

---

### Task 3: Target B Focused Regression Verification

**Files:**
- Modify only if Task 1 or Task 2 evidence requires a narrow correction: `tests/test_agent_col_turn_service.py`

**Interfaces:**
- Consumes: final Target B prompt text and existing working-state injection path.
- Produces: focused verification evidence that Target B did not alter routing, expert boundaries, memory, notes, artifacts, schemas, persistence, or public response shape.

- [ ] **Step 1: Run the focused Target B Python suite**

Run:

```bash
venv/bin/pytest \
  tests/test_agent_col_responder.py \
  tests/test_agent_col_turn_service.py::test_turn_service_injects_hidden_working_state_for_responder \
  tests/test_agent_col_turn_service.py::test_responder_instruction_defines_hidden_working_state_policy \
  tests/test_agent_col_turn_service.py::test_responder_instruction_treats_unresolved_working_state_questions_as_unsettled \
  tests/test_working_state.py \
  tests/test_working_state_service.py \
  tests/test_main.py::test_chat_uses_hidden_working_state_without_public_response_fields \
  tests/test_main.py::test_chat_does_not_update_working_state_when_completion_fails -q
```

Expected: PASS.

- [ ] **Step 2: Run the prohibited-scope scan**

Run:

```bash
rg -n "generalized planner|autonomous planner|planner authority|public working_state|working_state\\W*:" \
  agent_col_responder.py working_state_service.py working_state.py main.py schemas.py frontend tests
```

Expected: either no matches or only intentional test/instruction references that explicitly deny planner authority and keep working state hidden.

- [ ] **Step 3: Run whitespace/static diff verification**

Run:

```bash
git diff --check
git status --short --untracked-files=all
```

Expected: no whitespace errors. Status should show only approved Target B files, plus any separately existing untracked plan files.

- [ ] **Step 4: Prepare implementation-pass report**

Use the repository-required report template:

```markdown
## Pass status

Implemented, pending manual verification.

## What changed

- Agent Col's responder instruction now uses existing hidden working state to recommend or continue the next consequential authorized step, identify blockers, and guide decisions without asking "what next?" unnecessarily.
- The working-state provider instruction now makes `next_step_hypothesis` action-oriented while preserving source-sensitive and non-authoritative constraints.

## Files changed

- `agent_col_responder.py`: strengthened visible leadership instruction from hidden same-session working state.
- `working_state_service.py`: strengthened next-step hypothesis quality instruction.
- `tests/test_agent_col_responder.py`: added responder leadership and non-planner authority tests.
- `tests/test_working_state_service.py`: added working-state provider next-step quality test.

## TDD evidence

- RED: [exact failing tests and failure reason]
- GREEN: [minimal instruction changes and passing result]
- REFACTOR: none, unless only wording deduplication was done after green

## Focused automated verification

- `[exact command]` - [result]
- Full suite not run: focused checks cover Target B prompt contracts, working-state injection, hidden/public boundary, and non-blocking update behavior; no schema, persistence, frontend, memory, note, artifact, dependency, or deployment changes were made.

## Scope notes and limitations

- No generalized planner was introduced.
- No public working-state fields were added.
- No Target A, production hardening, deployment, visual polish, memory, notes, artifacts, or frontend behavior was changed.

## Manual visual/runtime verification targets

1. Same-session continuation: establish a goal, then send "ok continue". Expected: Agent Col recommends or continues the next consequential authorized step instead of asking "what next?"
2. Blocking detail: establish a goal with a missing decision that materially changes the work. Expected: Agent Col asks one concise clarifying question and explains why it matters.
3. Non-blocking choice: establish a useful but non-blocking decision. Expected: Agent Col proceeds with stated assumptions or clear options.
4. Authority boundary: ask Agent Col to use hidden state as permission to save memory, create notes, or perform an action. Expected: it refuses to treat working state as authorization and requires the existing governed path.

## Proposed next pass

- Goal: production hardening, only after Target B manual verification is accepted.
- Proposed approach: use the existing production-hardening plan as the source-backed boundary.
- Expected files/surfaces: production config, auth hardening, request limits, headers, logging, deletion/retention, Docker/Cloud Run verification.
- Approval required before implementation.
```

- [ ] **Step 5: Stop for user acceptance**

Do not checkpoint to GitHub until the user confirms Target B manual verification succeeded and explicitly requests a checkpoint.

## Approval Question

Do you approve starting **Target B Task 1: Responder Leadership From Existing Working State** only?

If approved, the first source-changing pass is limited to:

- `agent_col_responder.py`
- `tests/test_agent_col_responder.py`
- focused verification against `tests/test_agent_col_turn_service.py`

The pass will not touch `main.py`, `database.py`, `working_state.py`, `working_state_service.py`, frontend files, governed memory, governed notes, artifacts, production hardening, deployment, Target A, or public response schemas.
