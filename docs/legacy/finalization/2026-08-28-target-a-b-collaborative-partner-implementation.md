# Target A/B Collaborative Partner Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Pending source-backed validation and user approval. This document is a planning reference only. It does not authorize source, test, schema, prompt, persistence, API, frontend, dependency, deployment, or behavior changes.

**Goal:** Plan the final Collaborative Partner product work: Target A evidence-governed preference learning and Target B more visible Agent Col leadership.

**Architecture:** Target A adds a bounded, non-authoritative observation and hypothesis layer that can only feed the existing governed memory lifecycle after user confirmation. Target B strengthens Agent Col's use of existing hidden same-session working state, especially `next_step_hypothesis`, without adding a new planner or granting hidden state authority. Both targets preserve the responder-only architecture, deterministic application authority, explicit memory approval, workspace-note separation, and specialist-tool boundaries.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, Firestore, Vertex AI / Gemini, Google ADK, vanilla JavaScript modules, Node test runner, pytest.

**Spec:** `docs/final-checklist-planning.md`, `docs/current-state.md`, `docs/design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md`, `docs/superpowers/specs/2026-08-24-m9-mem-1-governed-profile-memory-scope-and-natural-request-design.md`

## Global Constraints

- This plan is pending source-backed validation and user approval before implementation.
- No source-changing task may begin until the user approves that exact implementation pass.
- TDD is required for every behavior, schema, prompt, persistence, frontend, test-support, or configuration change.
- Target A must preserve `observation evidence != preference hypothesis != candidate memory != active memory`.
- Observation extraction may use a narrow model step, but deterministic code must validate and bound every accepted observation.
- Do not call model extraction deterministic. Deterministic code validates model-extracted candidates.
- Observations and hypotheses are non-authoritative and must not adapt responses directly.
- Observations are workspace-scoped by default.
- No raw transcript mining, broad behavioral profiling, or autonomous background memory extraction.
- A hypothesis can become a memory candidate only after user confirmation.
- Active memory remains governed by existing approval, rejection, correction, revocation, deletion, provenance, receipts, and active-projection rules.
- Workspace notes and profile memory remain separate surfaces.
- Target B must use existing working-state context; it must not introduce a generalized planner.
- Hidden working state cannot authorize tools, actions, memory, notes, artifacts, identity changes, or external claims.
- The responder remains the final user-facing Agent Col and must not receive Research, Source, Computation, or Requirements Verification as model-visible tools.

---

## Source-Backed Validation Gate

This gate must run before any source-changing Target A or Target B pass. Its output is a short source-backed implementation memo that either confirms the file list below or proposes a revised pass boundary for approval.

### Files To Inspect

- `docs/design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md`: root memory and adaptation authority.
- `docs/final-checklist-planning.md`: current roadmap authority.
- `docs/current-state.md`: current implemented capability inventory.
- `docs/superpowers/specs/2026-08-24-m9-mem-1-governed-profile-memory-scope-and-natural-request-design.md`: old M9 contract and intentional non-goals.
- `memory_policy.py`: allowlisted memory categories, values, and validation.
- `memory_candidate_decisions.py`: structured provider decisions for memory candidates and clarifications.
- `memory_clarifications.py`: existing server-owned clarification choices.
- `memory_proposals.py`: proposal identity, origin, and evidence validation.
- `trusted_memory_service.py`: governed memory lifecycle service.
- `memory_context.py`: approved-memory rendering and adaptation receipts.
- `database.py`: Firestore persistence seams.
- `schemas.py`: chat request/response and receipt schemas.
- `main.py`: chat-turn orchestration, idempotency, memory decisions, clarification selection, working-state injection/update.
- `working_state.py`: hidden same-session working-state schema and renderer.
- `working_state_service.py`: working-state update provider prompt and validation.
- `agent_col_responder.py`: responder-only instruction and tool catalog.
- `frontend/*.mjs`, `frontend/index.html`, `frontend/styles.css`: existing memory clarification and memory panel surfaces.
- `tests/test_memory_policy.py`
- `tests/test_memory_policy_v2.py`
- `tests/test_memory_candidate_decisions.py`
- `tests/test_memory_clarifications.py`
- `tests/test_memory_proposal_service.py`
- `tests/test_trusted_memory_service.py`
- `tests/test_memory_database.py`
- `tests/test_main.py`
- `tests/test_agent_col_responder.py`
- `tests/test_working_state.py`
- `tests/test_working_state_service.py`
- `tests/frontend/chat-view.test.mjs`
- `tests/frontend/state.test.mjs`
- `tests/frontend/requests.test.mjs`

### Validation Commands

- [ ] Run source search:

```bash
rg -n "infer preferences|autonomous background|Do not infer memory|MemoryContextRenderer|propose_memory_signal|MemoryClarification|memory_decision|next_step_hypothesis|SERVER_VALIDATED_WORKING_STATE" \
  docs/design/AGENT_COL_IDENTITY_AND_ALIGNMENT.md \
  docs/final-checklist-planning.md \
  docs/current-state.md \
  docs/superpowers/specs/2026-08-24-m9-mem-1-governed-profile-memory-scope-and-natural-request-design.md \
  memory_*.py trusted_memory_service.py memory_context.py database.py schemas.py main.py \
  working_state.py working_state_service.py agent_col_responder.py tests frontend
```

- [ ] Inspect exact source seams:

```bash
sed -n '1,180p' agent_col_responder.py
sed -n '1,150p' working_state.py
sed -n '1,320p' memory_clarifications.py
sed -n '1,360p' trusted_memory_service.py
sed -n '2200,3240p' main.py
```

- [ ] Produce a short implementation memo with these headings:

```markdown
## Source-Backed Validation Memo

### Confirmed Current Behavior
- [evidence with file references]

### Target A Contract Revision
- [exact M9 text being revised]
- [exact preserving rules]

### Target A Source Boundary
- [files confirmed for implementation]
- [files excluded]

### Target B Source Boundary
- [files confirmed for implementation]
- [files excluded]

### Approval Question
Do you approve Target A pass 1 and Target B pass 1 as bounded above?
```

- [ ] Stop for user approval before source changes.

---

## Planned File Structure

These files are expected implementation surfaces. The validation gate may narrow or revise them before approval.

- Create `preference_learning.py`: deterministic Pydantic models, policy validation, scoring, deduplication, contradiction, decay, and surfacing rules for observations and hypotheses.
- Create `preference_learning_service.py`: narrow provider extraction wrapper and deterministic conversion into validated observations and hypotheses.
- Modify `database.py`: Firestore persistence for workspace-scoped observation evidence and non-authoritative hypotheses.
- Modify `trusted_memory_service.py`: bridge a confirmed hypothesis into the existing governed memory clarification/proposal lifecycle without creating active memory directly.
- Modify `memory_clarifications.py`: represent server-owned preference-hypothesis confirmation choices if existing clarification fields are insufficient.
- Modify `memory_proposals.py`: preserve evidence/provenance when a user-confirmed hypothesis becomes a pending memory proposal.
- Modify `schemas.py`: expose at most one server-owned confirmation/clarification receipt in chat responses if existing response fields are insufficient.
- Modify `main.py`: orchestrate observation capture after successful turns, avoid capture on failed/idempotent replay paths, surface at most one confirmation, and preserve existing memory/note/artifact precedence.
- Modify `agent_col_responder.py`: strengthen leadership instructions using working state and clarify the new Target A confirmation boundary.
- Modify `working_state_service.py`: tune next-step generation criteria if source validation shows the provider prompt is the correct seam.
- Modify frontend modules only if current memory clarification UI cannot safely render preference-hypothesis confirmations.
- Add focused tests under `tests/` and `tests/frontend/` for every source-changing behavior.

---

## Task 1: Target A Contract Revision And Policy Scaffold

**Files:**
- Create: `preference_learning.py`
- Modify: `docs/superpowers/specs/2026-08-24-m9-mem-1-governed-profile-memory-scope-and-natural-request-design.md`
- Test: `tests/test_preference_learning.py`

**Interfaces:**
- Produces: `PreferenceObservation`, `PreferenceHypothesis`, `validate_preference_observation(value: object) -> PreferenceObservation`, `merge_observations_into_hypothesis(existing: PreferenceHypothesis | None, observation: PreferenceObservation, *, now: datetime) -> PreferenceHypothesis | None`
- Consumes: `memory_policy.validate_memory_value_for_policy`

- [ ] **Step 1: Write the failing policy tests**

```python
from datetime import UTC, datetime

import pytest


def test_observation_is_not_hypothesis_or_memory() -> None:
    from preference_learning import PreferenceObservation

    observation = PreferenceObservation(
        observation_id="pref-obs--1",
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_turn_id="turn-1",
        category="response_length",
        canonical_value="concise",
        evidence_kind="user_correction",
        evidence_summary="User corrected the answer to be shorter.",
        confidence_delta=0.35,
        created_at=datetime(2026, 8, 28, tzinfo=UTC),
    )

    assert observation.authority == "non_authoritative_observation"
    assert observation.is_active_memory is False
    assert observation.can_adapt_response is False


def test_rejects_workspace_specific_profile_overreach() -> None:
    from preference_learning import validate_preference_observation

    with pytest.raises(ValueError, match="workspace-scoped"):
        validate_preference_observation({
            "observation_id": "pref-obs--2",
            "user_id": "user-1",
            "project_id": "project-1",
            "session_id": "session-1",
            "source_turn_id": "turn-2",
            "category": "development_environments",
            "canonical_value": ["macos"],
            "evidence_kind": "implicit_behavior",
            "evidence_summary": "User used a macOS path once.",
            "confidence_delta": 0.15,
        })
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_preference_learning.py::test_observation_is_not_hypothesis_or_memory \
  tests/test_preference_learning.py::test_rejects_workspace_specific_profile_overreach -q
```

Expected: FAIL because `preference_learning` does not exist.

- [ ] **Step 3: Implement the minimal policy scaffold**

Create Pydantic models with exact authority fields:

```python
PreferenceObservationAuthority = Literal["non_authoritative_observation"]
PreferenceHypothesisAuthority = Literal["non_authoritative_hypothesis"]
EvidenceKind = Literal["user_correction", "explicit_feedback_pattern", "repeated_collaboration_preference"]
```

Validation rules:

- `authority` defaults to the non-authoritative literal.
- `is_active_memory` is always `False`.
- `can_adapt_response` is always `False`.
- `project_id` is required.
- `implicit_behavior`, `history_only`, `artifact_only`, `search_only`, `expert_result_only`, and `model_authored_text` are rejected evidence kinds.
- Canonical values must pass existing memory policy validation for the target category.
- The implementation must not create, approve, render, or activate memory.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
venv/bin/pytest tests/test_preference_learning.py::test_observation_is_not_hypothesis_or_memory \
  tests/test_preference_learning.py::test_rejects_workspace_specific_profile_overreach -q
```

Expected: PASS.

- [ ] **Step 5: Update M9 spec language**

Revise the old M9 non-goal narrowly:

```markdown
M9-MEM.1 did not infer preferences from behavior, history, artifacts,
searches, expert results, or model-authored text. The Target A finalization
work may add bounded, workspace-scoped observation evidence and
non-authoritative preference hypotheses from user corrections, explicit
feedback patterns, or repeated collaboration preferences. This does not allow
silent active memory, raw transcript mining, broad profiling, or autonomous
background extraction. A hypothesis can only feed the existing governed memory
path after user confirmation.
```

- [ ] **Step 6: Commit only after user-approved implementation pass**

```bash
git add preference_learning.py tests/test_preference_learning.py docs/superpowers/specs/2026-08-24-m9-mem-1-governed-profile-memory-scope-and-natural-request-design.md
git commit -m "Add preference learning policy scaffold"
```

---

## Task 2: Target A Observation Persistence

**Files:**
- Modify: `database.py`
- Test: `tests/test_preference_learning_database.py`

**Interfaces:**
- Consumes: `PreferenceObservation`
- Produces: `save_preference_observation(observation: PreferenceObservation) -> None`, `list_recent_preference_observations(user_id: str, project_id: str, *, limit: int = 20) -> tuple[PreferenceObservation, ...]`

- [ ] **Step 1: Write the failing persistence test**

```python
import pytest


@pytest.mark.asyncio
async def test_preference_observations_are_workspace_scoped(memory_database) -> None:
    from preference_learning import PreferenceObservation

    observation = PreferenceObservation(
        observation_id="pref-obs--turn-1",
        user_id="user-1",
        project_id="project-a",
        session_id="session-1",
        source_turn_id="turn-1",
        category="response_length",
        canonical_value="concise",
        evidence_kind="user_correction",
        evidence_summary="User asked for a shorter answer after a verbose reply.",
        confidence_delta=0.35,
    )

    await memory_database.save_preference_observation(observation)

    project_a = await memory_database.list_recent_preference_observations(
        "user-1", "project-a"
    )
    project_b = await memory_database.list_recent_preference_observations(
        "user-1", "project-b"
    )

    assert [item.observation_id for item in project_a] == ["pref-obs--turn-1"]
    assert project_b == ()
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
venv/bin/pytest tests/test_preference_learning_database.py::test_preference_observations_are_workspace_scoped -q
```

Expected: FAIL because persistence methods do not exist.

- [ ] **Step 3: Implement minimal Firestore methods**

Expected path shape:

```text
users/{user_id}/projects/{project_id}/preference_observations/{observation_id}
```

Required behavior:

- reject `user_id` or `project_id` mismatches;
- write bounded observation payloads only;
- no raw transcript field;
- list newest bounded observations for the same user and workspace only;
- do not write active profile memory, proposal documents, or lifecycle events.

- [ ] **Step 4: Run database test**

Run:

```bash
venv/bin/pytest tests/test_preference_learning_database.py::test_preference_observations_are_workspace_scoped -q
```

Expected: PASS.

- [ ] **Step 5: Commit only after user-approved implementation pass**

```bash
git add database.py tests/test_preference_learning_database.py
git commit -m "Persist preference observations by workspace"
```

---

## Task 3: Target A Hypothesis Aggregation And Surfacing Policy

**Files:**
- Modify: `preference_learning.py`
- Test: `tests/test_preference_learning.py`

**Interfaces:**
- Consumes: `PreferenceObservation`
- Produces: `PreferenceHypothesis`, `should_surface_hypothesis(hypothesis: PreferenceHypothesis, *, now: datetime) -> bool`

- [ ] **Step 1: Write failing aggregation tests**

```python
from datetime import UTC, datetime, timedelta


def observation(turn_id: str, value: str = "concise"):
    from preference_learning import PreferenceObservation

    return PreferenceObservation(
        observation_id=f"pref-obs--{turn_id}",
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_turn_id=turn_id,
        category="response_length",
        canonical_value=value,
        evidence_kind="user_correction",
        evidence_summary="User corrected response length.",
        confidence_delta=0.35,
    )


def test_repeated_observations_create_non_authoritative_hypothesis() -> None:
    from preference_learning import merge_observations_into_hypothesis

    now = datetime(2026, 8, 28, tzinfo=UTC)
    hypothesis = merge_observations_into_hypothesis(None, observation("turn-1"), now=now)
    hypothesis = merge_observations_into_hypothesis(hypothesis, observation("turn-2"), now=now)

    assert hypothesis is not None
    assert hypothesis.authority == "non_authoritative_hypothesis"
    assert hypothesis.category == "response_length"
    assert hypothesis.canonical_value == "concise"
    assert hypothesis.evidence_count == 2
    assert hypothesis.can_adapt_response is False


def test_contradiction_reduces_confidence_and_blocks_surface() -> None:
    from preference_learning import merge_observations_into_hypothesis, should_surface_hypothesis

    now = datetime(2026, 8, 28, tzinfo=UTC)
    hypothesis = merge_observations_into_hypothesis(None, observation("turn-1", "concise"), now=now)
    hypothesis = merge_observations_into_hypothesis(hypothesis, observation("turn-2", "detailed"), now=now)

    assert hypothesis.contradiction_count == 1
    assert should_surface_hypothesis(hypothesis, now=now) is False


def test_stale_hypothesis_does_not_surface() -> None:
    from preference_learning import PreferenceHypothesis, should_surface_hypothesis

    hypothesis = PreferenceHypothesis(
        hypothesis_id="pref-hyp--1",
        user_id="user-1",
        project_id="project-1",
        category="response_length",
        canonical_value="concise",
        evidence_count=2,
        contradiction_count=0,
        confidence=0.75,
        first_observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        last_observed_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    assert should_surface_hypothesis(
        hypothesis,
        now=datetime(2026, 8, 28, tzinfo=UTC) + timedelta(days=31),
    ) is False
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_preference_learning.py::test_repeated_observations_create_non_authoritative_hypothesis \
  tests/test_preference_learning.py::test_contradiction_reduces_confidence_and_blocks_surface \
  tests/test_preference_learning.py::test_stale_hypothesis_does_not_surface -q
```

Expected: FAIL because aggregation is not implemented.

- [ ] **Step 3: Implement aggregation**

Minimum rules:

- require at least two aligned observations before a hypothesis can surface;
- start surfacing threshold at `confidence >= 0.70` and `evidence_count >= 2`;
- increment `contradiction_count` and reduce confidence when category matches but value conflicts;
- expire or suppress hypotheses older than the chosen source-backed interval;
- deduplicate observations by `source_turn_id`;
- never return active memory or adaptation instructions.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
venv/bin/pytest tests/test_preference_learning.py::test_repeated_observations_create_non_authoritative_hypothesis \
  tests/test_preference_learning.py::test_contradiction_reduces_confidence_and_blocks_surface \
  tests/test_preference_learning.py::test_stale_hypothesis_does_not_surface -q
```

Expected: PASS.

- [ ] **Step 5: Commit only after user-approved implementation pass**

```bash
git add preference_learning.py tests/test_preference_learning.py
git commit -m "Aggregate preference observations into hypotheses"
```

---

## Task 4: Target A User Confirmation Into Existing Governed Memory

**Files:**
- Modify: `memory_clarifications.py`
- Modify: `trusted_memory_service.py`
- Modify: `memory_proposals.py` if existing origin metadata cannot preserve hypothesis provenance.
- Test: `tests/test_memory_clarifications.py`
- Test: `tests/test_trusted_memory_service.py`

**Interfaces:**
- Consumes: `PreferenceHypothesis`
- Produces: server-owned confirmation receipt that can create one pending governed memory proposal after user confirmation.

- [ ] **Step 1: Write failing confirmation tests**

```python
import pytest


@pytest.mark.asyncio
async def test_confirmed_preference_hypothesis_creates_pending_memory_proposal(memory_service) -> None:
    from preference_learning import PreferenceHypothesis

    hypothesis = PreferenceHypothesis(
        hypothesis_id="pref-hyp--response-length",
        user_id="user-1",
        project_id="project-1",
        category="response_length",
        canonical_value="concise",
        evidence_count=2,
        contradiction_count=0,
        confidence=0.75,
    )

    clarification = await memory_service.open_preference_hypothesis_confirmation(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        turn_id="turn-3",
        hypothesis=hypothesis,
    )

    result = await memory_service.select_memory_clarification(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        selecting_turn_id="turn-4",
        clarification_id=clarification.clarification_id,
        selected_candidate_index=0,
    )

    assert result.proposal.category == "response_length"
    assert result.proposal.value == "concise"
    assert result.proposal.status == "pending"


@pytest.mark.asyncio
async def test_unconfirmed_hypothesis_does_not_create_memory(memory_service) -> None:
    profile = await memory_service.inspect_memory(user_id="user-1")

    assert profile.unresolved_proposals == []
    assert profile.active_preferences == {}
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_trusted_memory_service.py::test_confirmed_preference_hypothesis_creates_pending_memory_proposal \
  tests/test_trusted_memory_service.py::test_unconfirmed_hypothesis_does_not_create_memory -q
```

Expected: FAIL because hypothesis confirmation is not wired.

- [ ] **Step 3: Implement the confirmation bridge**

Rules:

- At most one hypothesis confirmation may be open per turn.
- Confirmation text must not claim the preference is saved.
- Selection creates a pending proposal, not active memory.
- Existing approval/rejection controls remain required.
- Rejection or expiry leaves no pending proposal.
- The source evidence recorded with the pending proposal must identify the bounded hypothesis and evidence count, not raw transcript text.
- Existing clarification selection ownership, expiry, one-subsequent-turn rule, and idempotency rules remain intact.

- [ ] **Step 4: Run confirmation tests**

Run:

```bash
venv/bin/pytest tests/test_memory_clarifications.py tests/test_trusted_memory_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit only after user-approved implementation pass**

```bash
git add memory_clarifications.py trusted_memory_service.py memory_proposals.py tests/test_memory_clarifications.py tests/test_trusted_memory_service.py
git commit -m "Confirm preference hypotheses through governed memory"
```

---

## Task 5: Target A Turn Integration

**Files:**
- Create: `preference_learning_service.py`
- Modify: `main.py`
- Modify: `schemas.py` only if existing response fields cannot carry the confirmation receipt.
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: completed chat turn with current user message, final model response, user/project/session/turn identifiers, existing memory and note receipts.
- Produces: zero or one stored observation and zero or one user-facing confirmation receipt.

- [ ] **Step 1: Write failing integration tests**

```python
import pytest


@pytest.mark.asyncio
async def test_chat_records_preference_observation_without_active_memory(client, service_state):
    service_state.preference_learning_service.observation = {
        "category": "response_length",
        "canonical_value": "concise",
        "evidence_kind": "user_correction",
        "evidence_summary": "User corrected the response to be shorter.",
    }

    response = await client.post(
        "/api/projects/default/chat",
        json={
            "message": "That was too long; be shorter here.",
            "session_id": "session-1",
            "idempotency_key": "turn-pref-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body.get("memory_proposals", []) == []
    assert service_state.database.saved_preference_observations


@pytest.mark.asyncio
async def test_chat_surfaces_hypothesis_confirmation_without_saving_memory(client, service_state):
    service_state.preference_learning_service.surface_confirmation = True

    response = await client.post(
        "/api/projects/default/chat",
        json={
            "message": "Again, please give me concise practical answers.",
            "session_id": "session-1",
            "idempotency_key": "turn-pref-2",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["memory_clarifications"][0]["choices"][0]["category"] == "response_length"
    assert body.get("memory_proposals", []) == []
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_main.py::test_chat_records_preference_observation_without_active_memory \
  tests/test_main.py::test_chat_surfaces_hypothesis_confirmation_without_saving_memory -q
```

Expected: FAIL because Target A service integration does not exist.

- [ ] **Step 3: Implement minimal orchestration**

Rules:

- Run only after a successful non-replay chat completion.
- Do not run on structured memory decision turns or clarification selection turns unless source validation approves that boundary.
- Do not run when the current turn already created a memory proposal, memory clarification, note proposal, or failure receipt.
- Do not block the main chat response if extraction fails; log only safe metadata.
- Store only validated observation summaries.
- Surface at most one confirmation.
- Never inject unconfirmed hypotheses into `MemoryContextRenderer`.

- [ ] **Step 4: Run focused integration tests**

Run:

```bash
venv/bin/pytest tests/test_main.py::test_chat_records_preference_observation_without_active_memory \
  tests/test_main.py::test_chat_surfaces_hypothesis_confirmation_without_saving_memory \
  tests/test_main.py::test_chat_uses_hidden_working_state_without_public_response_fields -q
```

Expected: PASS.

- [ ] **Step 5: Commit only after user-approved implementation pass**

```bash
git add preference_learning_service.py main.py schemas.py tests/test_main.py
git commit -m "Integrate preference learning into chat turns"
```

---

## Task 6: Target A Frontend Confirmation Surface

**Files:**
- Modify: `frontend/chat-view.mjs` only if current clarification rendering cannot safely handle the confirmation receipt.
- Modify: `frontend/state.mjs` only if current state cannot preserve the active confirmation receipt.
- Modify: `frontend/requests.mjs` only if current clarification selection request is insufficient.
- Test: `tests/frontend/chat-view.test.mjs`
- Test: `tests/frontend/state.test.mjs`
- Test: `tests/frontend/requests.test.mjs`

**Interfaces:**
- Consumes: existing or extended `memory_clarifications` response field.
- Produces: existing structured clarification selection request.

- [ ] **Step 1: Write failing frontend tests only if source validation shows a frontend gap**

```javascript
test("preference hypothesis confirmation renders as an unsaved memory choice", () => {
  const receipt = {
    clarification_id: "memory-clarification--pref-hyp-1",
    expires_at: "2026-08-28T12:00:00Z",
    choices: [{
      candidate_index: 0,
      category: "response_length",
      value_label: "concise",
      action_label: "Ask to save this preference",
    }],
  };

  renderActiveMemoryClarification(receipt);

  assert.match(textTree(clarificationChoices), /Ask to save this preference/);
  assert.doesNotMatch(textTree(clarificationChoices), /saved|remembered/i);
  assert.doesNotMatch(textTree(clarificationChoices), /memory-clarification--/);
});
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs tests/frontend/state.test.mjs tests/frontend/requests.test.mjs
```

Expected: FAIL only for the new unsupported confirmation rendering.

- [ ] **Step 3: Implement minimal rendering/state changes**

Rules:

- Reuse existing clarification button pattern.
- Do not expose internal clarification IDs in visible text.
- Do not claim memory is saved before approval.
- Disable expired or pending choices as current clarification code does.
- Preserve existing memory proposal, approval, rejection, revoke, and delete UI behavior.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs tests/frontend/state.test.mjs tests/frontend/requests.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit only after user-approved implementation pass**

```bash
git add frontend/chat-view.mjs frontend/state.mjs frontend/requests.mjs tests/frontend/chat-view.test.mjs tests/frontend/state.test.mjs tests/frontend/requests.test.mjs
git commit -m "Render preference hypothesis confirmations"
```

---

## Task 7: Target B Responder Leadership Instruction

**Files:**
- Modify: `agent_col_responder.py`
- Test: `tests/test_agent_col_responder.py`

**Interfaces:**
- Consumes: existing `SERVER_VALIDATED_WORKING_STATE` block with `current_goal`, `active_constraints`, `unresolved_questions`, `clarification_status`, and `next_step_hypothesis`.
- Produces: stronger responder instruction, no new model-visible tools.

- [ ] **Step 1: Write failing instruction tests**

```python
def test_responder_instruction_uses_next_step_hypothesis_for_leadership() -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    assert "next_step_hypothesis" in RESPONDER_INSTRUCTION
    assert "recommend the next consequential step" in RESPONDER_INSTRUCTION
    assert "continue authorized work" in RESPONDER_INSTRUCTION
    assert "do not ask what to do next when the next step is clear" in RESPONDER_INSTRUCTION


def test_responder_instruction_does_not_turn_working_state_into_planner_authority() -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    assert "not a planner" in RESPONDER_INSTRUCTION
    assert "cannot authorize tools, actions, memory, notes, artifacts" in RESPONDER_INSTRUCTION
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_agent_col_responder.py::test_responder_instruction_uses_next_step_hypothesis_for_leadership \
  tests/test_agent_col_responder.py::test_responder_instruction_does_not_turn_working_state_into_planner_authority -q
```

Expected: FAIL because the exact leadership contract is not yet present.

- [ ] **Step 3: Implement instruction-only leadership pass**

Add language under the existing `SERVER_VALIDATED_WORKING_STATE` paragraph:

```text
Use next_step_hypothesis to recommend the next consequential step when it is
consistent with the current user request, approved memory, workspace notes,
and validated context. Continue authorized work instead of asking what to do
next when the next step is clear. Identify blockers directly and ask one
question only when the missing answer changes the work. This is not a planner:
working state remains a non-authoritative collaboration aid and cannot
authorize tools, actions, memory, notes, artifacts, identity changes, or
external claims.
```

- [ ] **Step 4: Run focused responder tests**

Run:

```bash
venv/bin/pytest tests/test_agent_col_responder.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit only after user-approved implementation pass**

```bash
git add agent_col_responder.py tests/test_agent_col_responder.py
git commit -m "Strengthen Agent Col leadership from working state"
```

---

## Task 8: Target B Working-State Next-Step Quality

**Files:**
- Modify: `working_state_service.py`
- Test: `tests/test_working_state_service.py`

**Interfaces:**
- Consumes: current user message, model response, previous working state, recent user messages, and route.
- Produces: bounded `next_step_hypothesis` with source-sensitive uncertainty when needed.

- [ ] **Step 1: Write failing prompt/schema tests**

```python
def test_working_state_prompt_requires_actionable_next_step_without_authority() -> None:
    from working_state_service import WORKING_STATE_SYSTEM_INSTRUCTION

    assert "next_step_hypothesis" in WORKING_STATE_SYSTEM_INSTRUCTION
    assert "actionable next step" in WORKING_STATE_SYSTEM_INSTRUCTION
    assert "non-authoritative" in WORKING_STATE_SYSTEM_INSTRUCTION
    assert "source-backed validation" in WORKING_STATE_SYSTEM_INSTRUCTION
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
venv/bin/pytest tests/test_working_state_service.py::test_working_state_prompt_requires_actionable_next_step_without_authority -q
```

Expected: FAIL if the current provider instruction lacks the exact leadership-quality requirement.

- [ ] **Step 3: Implement the prompt refinement**

Rules:

- Ask for a concrete next step, not generic encouragement.
- Mark source-sensitive next steps as needing validation.
- Preserve bounded field lengths.
- Do not add hidden chain-of-thought fields.
- Do not create a public response field.

- [ ] **Step 4: Run focused working-state tests**

Run:

```bash
venv/bin/pytest tests/test_working_state.py tests/test_working_state_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit only after user-approved implementation pass**

```bash
git add working_state_service.py tests/test_working_state_service.py
git commit -m "Improve working-state next-step quality"
```

---

## Task 9: Cross-Target Regression Verification

**Files:**
- No production files unless previous tasks reveal a source-backed gap.
- Test: existing focused suites.

**Interfaces:**
- Confirms Target A and Target B did not regress governed memory, note separation, hidden working state, or responder-only expert boundaries.

- [ ] **Step 1: Run focused Python regression checks**

Run:

```bash
venv/bin/pytest \
  tests/test_preference_learning.py \
  tests/test_preference_learning_database.py \
  tests/test_memory_policy.py \
  tests/test_memory_policy_v2.py \
  tests/test_memory_clarifications.py \
  tests/test_memory_proposal_service.py \
  tests/test_trusted_memory_service.py \
  tests/test_memory_context.py \
  tests/test_working_state.py \
  tests/test_working_state_service.py \
  tests/test_agent_col_responder.py \
  tests/test_main.py -q
```

Expected: PASS. If this is too broad for a single approved pass, split by Target A and Target B and explain why.

- [ ] **Step 2: Run focused frontend regression checks**

Run:

```bash
node --test \
  tests/frontend/chat-view.test.mjs \
  tests/frontend/state.test.mjs \
  tests/frontend/requests.test.mjs \
  tests/frontend/memory-view.test.mjs
```

Expected: PASS.

- [ ] **Step 3: Verify no broad async/Cloud Tasks dependency was introduced**

Run:

```bash
rg -n "Cloud Tasks|private worker|durable async|background memory extraction|autonomous background" \
  preference_learning.py preference_learning_service.py main.py database.py trusted_memory_service.py agent_col_responder.py working_state_service.py tests
```

Expected: no new Target A/B implementation dependency on Cloud Tasks, private worker, durable async artifacts, or autonomous background memory extraction.

- [ ] **Step 4: Prepare implementation-pass report**

Use the repository pass-report template from `AGENTS.md`. Report status as:

```markdown
Implemented, pending manual verification.
```

- [ ] **Step 5: Stop for user manual verification and acceptance**

No GitHub checkpoint for source changes until the user confirms the implemented pass is accepted.

---

## Manual Verification Targets For Future Implementation

After source implementation and focused automated checks, the user should verify:

1. In one chat, correct Agent Col's collaboration style at least twice. Expected: Agent Col may ask whether it should remember the possible preference, but it must not claim the preference is saved.
2. Select the confirmation. Expected: a pending governed memory proposal appears; active memory still does not change until approval.
3. Approve the proposal through the existing memory lifecycle. Expected: later chat responses adapt and show existing adaptation receipts.
4. Reject or ignore a confirmation. Expected: no active memory and no adaptation from the unconfirmed hypothesis.
5. Give contradictory style corrections. Expected: no confident memory prompt is surfaced from conflicting evidence.
6. Continue a multi-turn planning task. Expected: Agent Col recommends the next consequential step or identifies the blocker instead of restarting or asking an unnecessary open-ended question.
7. Ask a source-sensitive next-step question. Expected: Agent Col frames it as needing source-backed validation unless validated context is already present.

## Known Exclusions

- No generalized planner.
- No autonomous background jobs.
- No Cloud Tasks or private worker.
- No unbounded transcript mining.
- No vector or semantic memory store.
- No silent active memory.
- No direct response adaptation from observations or hypotheses.
- No broad frontend redesign.
- No production hardening changes in this Target A/B plan.
