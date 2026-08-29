# Target A Evidence-Governed Preference Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Target A evidence-governed preference learning so repeated user corrections can create a non-authoritative preference hypothesis, ask for user confirmation, enter the existing governed memory proposal lifecycle, and adapt only after approval.

**Architecture:** Add a small preference-learning domain beside governed memory, not inside active memory. Observation evidence and hypotheses remain workspace-scoped, non-authoritative, bounded, and unable to affect response adaptation directly. A surfaced hypothesis is converted into an existing memory clarification/proposal flow only after the user confirms it; active memory remains controlled by the current approval/rejection/correction/revocation/deletion path.

**Tech Stack:** Python 3.14, FastAPI, Pydantic 2.13.4, Firestore, Google GenAI SDK, Vertex AI / Gemini, pytest, vanilla JavaScript ES modules, Node test runner.

**Spec:** `docs/final-checklist-planning.md`, `docs/current-state.md`, `AGENT_COL_IDENTITY_AND_ALIGNMENT.md`, `docs/superpowers/specs/2026-08-24-m9-mem-1-governed-profile-memory-scope-and-natural-request-design.md`

## Global Constraints

- No source-changing task may begin until the user approves that exact implementation pass.
- TDD is required for every behavior, schema, prompt, persistence, frontend, test-support, or configuration change.
- Target A must preserve `observation evidence != preference hypothesis != candidate memory != active memory`.
- Observation evidence and hypotheses are non-authoritative and must not adapt responses directly.
- Observations are workspace-scoped by default.
- No raw transcript mining, broad behavioral profiling, autonomous background memory extraction, Cloud Tasks, or private worker.
- A hypothesis can become a memory candidate only after user confirmation.
- Active memory remains governed by existing approval, rejection, correction, revocation, deletion, provenance, receipts, and active-projection rules.
- Workspace notes and profile memory remain separate surfaces.
- The responder remains the final user-facing Agent Col and must not receive Research, Source, Computation, or Requirements Verification as model-visible tools.

---

## Source-Backed Evidence

- `memory_policy.py:14-23` defines current preference categories, and `memory_policy.py:130-177` defines allowed values and category order. Target A should reuse these categories rather than adding free-form preference authority.
- `memory_candidate_decisions.py:53-74` validates profile candidates through `validate_memory_value_for_policy("2.0", ...)`; `memory_candidate_decisions.py:301-318` requires candidate evidence text to be an exact substring of the source message. Target A observation extraction can be more inferential than current explicit memory requests, but the confirmed memory candidate must still be bounded and policy-valid.
- `memory_clarifications.py:66-85` stores server-owned clarification envelopes with user, session, workspace, evidence, turn, candidate, timestamp, and status fields; `memory_clarifications.py:87-140` validates timezone-aware lifetime, uniqueness, and state; `memory_clarifications.py:216-266` enforces ownership, subsequent-turn selection, first-subsequent-turn, expiry, and candidate bounds. Target A should reuse this lifecycle shape for confirmation.
- `trusted_memory_service.py:101-113` defines `NaturalMemoryCommand` with user/workspace/session/source provenance and a structured decision; `trusted_memory_service.py:285-439` creates pending proposals or clarifications, never active memory; `trusted_memory_service.py:441-497` consumes a clarification selection into a pending `MemoryProposalReceiptV2`; `trusted_memory_service.py:499-535` applies approval/rejection decisions.
- `memory_proposals.py:52-85` defines `ProposalOriginV2` with source/evidence message and optional clarification ID; `memory_proposals.py:135-160` derives stable V2 proposal IDs from user, session, source message, and category. Target A needs new provenance fields only if hypothesis identity and evidence count cannot fit existing proposal origin/event models.
- `memory_context.py:36-81` renders only active profile signals into model instructions and adaptation receipts. Target A must not inject unconfirmed observations or hypotheses here.
- `schemas.py:818-844` makes chat structured decisions mutually exclusive; `schemas.py:847-863` limits `memory_proposals` and `memory_clarifications` to at most one each; `schemas.py:1137-1149` defines the current public clarification receipt shape. Target A should surface at most one confirmation and avoid adding response fields unless this shape cannot represent the confirmation safely.
- `main.py:2315-2378` claims idempotent chat turns and returns completed replays before downstream side effects; `main.py:2602-2678` already handles memory clarification selections; `main.py:2680-2760` runs current deterministic memory clarification preflight only on ordinary, claimed, non-structured turns with no precompleted memory effect; `main.py:2937-3015` passes precompleted memory effects into `AgentColTurnService`; `main.py:3129-3174` merges final receipts; `main.py:3189-3201` completes the chat turn before hidden working-state update; `main.py:3203-3237` treats hidden working-state update failure as non-blocking.
- `frontend/chat-view.mjs:90-118` already renders active memory clarification choices and attaches the server-owned clarification ID to the selected choice; `frontend/requests.mjs:54-96` keeps structured decisions mutually exclusive; `frontend/requests.mjs:283-319` builds the memory clarification selection request; `frontend/state.mjs:263-300` and `frontend/state.mjs:567-582` preserve at most one active memory clarification and clear it after selection.
- `docs/superpowers/specs/2026-08-24-m9-mem-1-governed-profile-memory-scope-and-natural-request-design.md:1-44` is the approved M9 governed-memory contract and currently frames memory around explicit governed proposals. Target A changes that contract boundary, so Task 1 must revise M9 policy text explicitly before implementation proceeds beyond the domain layer.

## Source-Backed Implementation Boundary

### Create

- `preference_learning.py`: deterministic Pydantic models, policy validation, observation/hypothesis scoring, deduplication, contradiction, expiry, and surfacing rules.
- `preference_learning_service.py`: narrow provider wrapper or deterministic extractor facade that returns validated observations/hypotheses and logs only safe metadata on failure.
- `tests/test_preference_learning.py`: domain and policy tests.
- `tests/test_preference_learning_database.py`: Firestore persistence contract tests.
- `tests/test_preference_learning_service.py`: extraction/surfacing service tests.

### Modify

- `database.py`: persist workspace-scoped observations and hypotheses under the user/workspace tree.
- `trusted_memory_service.py`: open a preference-hypothesis confirmation and convert a confirmed hypothesis into one pending governed memory proposal.
- `memory_clarifications.py`: add only the minimal confirmation metadata if the current clarification model cannot distinguish a hypothesis confirmation from multi-candidate disambiguation.
- `memory_proposals.py`: add provenance derivation/parsing only if existing V2 origin cannot safely preserve hypothesis provenance.
- `schemas.py`: avoid changes unless existing `MemoryClarificationReceipt` cannot carry safe user-facing confirmation text.
- `main.py`: wire non-blocking Target A capture/surfacing after successful non-replay ordinary turns.
- `tests/test_main.py`, `tests/test_memory_clarifications.py`, `tests/test_trusted_memory_service.py`: focused integration and lifecycle coverage.
- `frontend/chat-view.mjs`, `frontend/state.mjs`, `frontend/requests.mjs` only if source validation during implementation proves the existing clarification UI cannot safely render and submit the confirmation.
- `tests/frontend/chat-view.test.mjs`, `tests/frontend/state.test.mjs`, `tests/frontend/requests.test.mjs` only if frontend source changes are needed.

### Excluded

- No direct changes to `MemoryContextRenderer` except tests proving unconfirmed hypotheses do not reach it.
- No generalized planner, Target B leadership work, production hardening, deployment, visual polish, Cloud Tasks, private worker, durable async artifacts, vector memory, raw transcript mining, autonomous background jobs, or broad frontend redesign.

---

### Task 1: Preference Learning Domain And M9 Contract Policy Revision

**Files:**
- Create: `preference_learning.py`
- Create: `tests/test_preference_learning.py`
- Modify: `docs/superpowers/specs/2026-08-24-m9-mem-1-governed-profile-memory-scope-and-natural-request-design.md`

**Interfaces:**
- Consumes: `memory_policy.validate_memory_value_for_policy`.
- Produces: `PreferenceObservation`, `PreferenceHypothesis`, `validate_preference_observation(value: object) -> PreferenceObservation`, `merge_observation_into_hypothesis(existing: PreferenceHypothesis | None, observation: PreferenceObservation, *, now: datetime) -> PreferenceHypothesis | None`, `should_surface_hypothesis(hypothesis: PreferenceHypothesis, *, now: datetime) -> bool`.
- Revises: the M9-MEM.1 contract policy so it explicitly allows bounded Target A observation evidence and non-authoritative preference hypotheses while preserving the governed memory activation path.

- [ ] **Step 1: Write the failing domain tests**

```python
from datetime import UTC, datetime, timedelta

import pytest


def observation_payload(**updates: object) -> dict[str, object]:
    payload = {
        "observation_id": "pref-obs--turn-1",
        "user_id": "user-1",
        "project_id": "project-1",
        "session_id": "session-1",
        "source_turn_id": "turn-1",
        "source_message_id": "message-1",
        "category": "response_length",
        "canonical_value": "concise",
        "evidence_kind": "user_correction",
        "evidence_summary": "User corrected the answer to be shorter.",
        "confidence_delta": 0.35,
        "created_at": datetime(2026, 8, 28, tzinfo=UTC),
    }
    payload.update(updates)
    return payload


def test_observation_is_not_hypothesis_or_memory() -> None:
    from preference_learning import PreferenceObservation

    observation = PreferenceObservation.model_validate(observation_payload())

    assert observation.authority == "non_authoritative_observation"
    assert observation.is_active_memory is False
    assert observation.can_adapt_response is False


def test_rejects_unscoped_observation() -> None:
    from preference_learning import validate_preference_observation

    payload = observation_payload(project_id="")

    with pytest.raises(ValueError, match="project_id"):
        validate_preference_observation(payload)


def test_rejects_disallowed_evidence_kind() -> None:
    from preference_learning import validate_preference_observation

    payload = observation_payload(evidence_kind="model_authored_text")

    with pytest.raises(ValueError, match="evidence_kind"):
        validate_preference_observation(payload)


def test_rejects_policy_invalid_value() -> None:
    from preference_learning import validate_preference_observation

    payload = observation_payload(canonical_value="verbose")

    with pytest.raises(ValueError, match="Unsupported"):
        validate_preference_observation(payload)


def test_repeated_observations_create_non_authoritative_hypothesis() -> None:
    from preference_learning import merge_observation_into_hypothesis

    now = datetime(2026, 8, 28, tzinfo=UTC)
    first = observation_payload(source_turn_id="turn-1")
    second = observation_payload(
        observation_id="pref-obs--turn-2",
        source_turn_id="turn-2",
        source_message_id="message-2",
    )

    hypothesis = merge_observation_into_hypothesis(None, first, now=now)
    hypothesis = merge_observation_into_hypothesis(hypothesis, second, now=now)

    assert hypothesis is not None
    assert hypothesis.authority == "non_authoritative_hypothesis"
    assert hypothesis.category == "response_length"
    assert hypothesis.canonical_value == "concise"
    assert hypothesis.evidence_count == 2
    assert hypothesis.can_adapt_response is False


def test_conflicting_observation_suppresses_surface() -> None:
    from preference_learning import (
        merge_observation_into_hypothesis,
        should_surface_hypothesis,
    )

    now = datetime(2026, 8, 28, tzinfo=UTC)
    hypothesis = merge_observation_into_hypothesis(
        None,
        observation_payload(source_turn_id="turn-1", canonical_value="concise"),
        now=now,
    )
    hypothesis = merge_observation_into_hypothesis(
        hypothesis,
        observation_payload(
            observation_id="pref-obs--turn-2",
            source_turn_id="turn-2",
            source_message_id="message-2",
            canonical_value="detailed",
        ),
        now=now,
    )

    assert hypothesis.contradiction_count == 1
    assert should_surface_hypothesis(hypothesis, now=now) is False


def test_stale_hypothesis_does_not_surface() -> None:
    from preference_learning import PreferenceHypothesis, should_surface_hypothesis

    hypothesis = PreferenceHypothesis(
        hypothesis_id="pref-hyp--response-length",
        user_id="user-1",
        project_id="project-1",
        category="response_length",
        canonical_value="concise",
        evidence_count=2,
        contradiction_count=0,
        confidence=0.75,
        source_observation_ids=("pref-obs--1", "pref-obs--2"),
        first_observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        last_observed_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    assert should_surface_hypothesis(
        hypothesis,
        now=datetime(2026, 9, 30, tzinfo=UTC),
    ) is False
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_preference_learning.py -q
```

Expected: FAIL because `preference_learning` does not exist.

- [ ] **Step 3: Implement the minimal domain**

```python
from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from memory_policy import MemoryCategoryV2, validate_memory_value_for_policy
from schemas import IdentifierStr, StrictModel


PreferenceObservationAuthority = Literal["non_authoritative_observation"]
PreferenceHypothesisAuthority = Literal["non_authoritative_hypothesis"]
EvidenceKind = Literal[
    "user_correction",
    "explicit_feedback_pattern",
    "repeated_collaboration_preference",
]
PreferenceEvidenceSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=240),
]
DISALLOWED_EVIDENCE_KINDS = frozenset(
    {
        "implicit_behavior",
        "history_only",
        "artifact_only",
        "search_only",
        "expert_result_only",
        "model_authored_text",
    }
)
HYPOTHESIS_SURFACE_MIN_CONFIDENCE = 0.70
HYPOTHESIS_SURFACE_MIN_EVIDENCE = 2
HYPOTHESIS_MAX_AGE = timedelta(days=30)


class PreferenceObservation(StrictModel):
    observation_id: IdentifierStr
    authority: PreferenceObservationAuthority = "non_authoritative_observation"
    user_id: IdentifierStr
    project_id: IdentifierStr
    session_id: IdentifierStr
    source_turn_id: IdentifierStr
    source_message_id: IdentifierStr
    category: MemoryCategoryV2
    canonical_value: object
    evidence_kind: EvidenceKind
    evidence_summary: PreferenceEvidenceSummary
    confidence_delta: float = Field(ge=0.0, le=0.5)
    created_at: datetime
    is_active_memory: Literal[False] = False
    can_adapt_response: Literal[False] = False

    @model_validator(mode="after")
    def validate_policy_value(self) -> "PreferenceObservation":
        normalized = validate_memory_value_for_policy(
            "2.0",
            self.category,
            self.canonical_value,
        )
        object.__setattr__(self, "canonical_value", normalized)
        return self


class PreferenceHypothesis(StrictModel):
    hypothesis_id: IdentifierStr
    authority: PreferenceHypothesisAuthority = "non_authoritative_hypothesis"
    user_id: IdentifierStr
    project_id: IdentifierStr
    category: MemoryCategoryV2
    canonical_value: object
    evidence_count: int = Field(ge=1, le=20)
    contradiction_count: int = Field(ge=0, le=20)
    confidence: float = Field(ge=0.0, le=1.0)
    source_observation_ids: tuple[IdentifierStr, ...] = Field(max_length=20)
    first_observed_at: datetime
    last_observed_at: datetime
    is_active_memory: Literal[False] = False
    can_adapt_response: Literal[False] = False

    @model_validator(mode="after")
    def validate_policy_value(self) -> "PreferenceHypothesis":
        normalized = validate_memory_value_for_policy(
            "2.0",
            self.category,
            self.canonical_value,
        )
        object.__setattr__(self, "canonical_value", normalized)
        return self


def validate_preference_observation(value: object) -> PreferenceObservation:
    return PreferenceObservation.model_validate(value)


def derive_preference_hypothesis_id(observation: PreferenceObservation) -> str:
    return (
        f"pref-hyp--{observation.user_id}--{observation.project_id}--"
        f"{observation.category}"
    )


def merge_observation_into_hypothesis(
    existing: PreferenceHypothesis | None,
    observation: PreferenceObservation | object,
    *,
    now: datetime,
) -> PreferenceHypothesis | None:
    validated = validate_preference_observation(observation)
    if existing is not None and validated.observation_id in existing.source_observation_ids:
        return existing
    if existing is None:
        return PreferenceHypothesis(
            hypothesis_id=derive_preference_hypothesis_id(validated),
            user_id=validated.user_id,
            project_id=validated.project_id,
            category=validated.category,
            canonical_value=validated.canonical_value,
            evidence_count=1,
            contradiction_count=0,
            confidence=min(validated.confidence_delta, 1.0),
            source_observation_ids=(validated.observation_id,),
            first_observed_at=validated.created_at,
            last_observed_at=now,
        )
    if (
        existing.user_id != validated.user_id
        or existing.project_id != validated.project_id
        or existing.category != validated.category
    ):
        raise ValueError("Observation does not match hypothesis scope.")
    if existing.canonical_value != validated.canonical_value:
        return existing.model_copy(
            update={
                "contradiction_count": existing.contradiction_count + 1,
                "confidence": max(existing.confidence - validated.confidence_delta, 0.0),
                "source_observation_ids": (
                    *existing.source_observation_ids,
                    validated.observation_id,
                ),
                "last_observed_at": now,
            }
        )
    return existing.model_copy(
        update={
            "evidence_count": existing.evidence_count + 1,
            "confidence": min(existing.confidence + validated.confidence_delta, 1.0),
            "source_observation_ids": (
                *existing.source_observation_ids,
                validated.observation_id,
            ),
            "last_observed_at": now,
        }
    )


def should_surface_hypothesis(
    hypothesis: PreferenceHypothesis,
    *,
    now: datetime,
) -> bool:
    return (
        hypothesis.evidence_count >= HYPOTHESIS_SURFACE_MIN_EVIDENCE
        and hypothesis.confidence >= HYPOTHESIS_SURFACE_MIN_CONFIDENCE
        and hypothesis.contradiction_count == 0
        and now - hypothesis.last_observed_at <= HYPOTHESIS_MAX_AGE
    )
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
venv/bin/pytest tests/test_preference_learning.py -q
```

Expected: PASS.

- [ ] **Step 5: Revise the M9 contract policy**

Replace the obsolete no-inference language with an explicit M9 contract-policy revision. The revision must state that Target A is a governed extension of M9-MEM.1, not an implementation loophole around it:

```markdown
M9-MEM.1 did not infer preferences from behavior, history, artifacts,
searches, expert results, or model-authored text. Target A may add bounded,
workspace-scoped observation evidence and non-authoritative preference
hypotheses from user corrections, explicit feedback patterns, or repeated
collaboration preferences. This does not allow silent active memory, raw
transcript mining, broad profiling, autonomous background extraction, or
direct response adaptation from hypotheses. A hypothesis can only feed the
existing governed memory path after user confirmation.
```

The M9 revision is part of this pass' contract. The pass is not complete if
the domain code exists but the M9 policy text still describes Target A as
disallowed inference.

- [ ] **Step 6: Run focused verification for Task 1**

Run:

```bash
venv/bin/pytest tests/test_preference_learning.py tests/test_memory_policy_v2.py -q
git diff --check
```

Expected: PASS.

---

### Task 2: Preference Observation And Hypothesis Persistence

**Files:**
- Modify: `database.py`
- Create: `tests/test_preference_learning_database.py`

**Interfaces:**
- Consumes: `PreferenceObservation`, `PreferenceHypothesis`.
- Produces: `save_preference_observation(observation: PreferenceObservation) -> None`, `list_recent_preference_observations(user_id: str, project_id: str, *, limit: int = 20) -> tuple[PreferenceObservation, ...]`, `save_preference_hypothesis(hypothesis: PreferenceHypothesis) -> None`, `get_preference_hypothesis(user_id: str, project_id: str, hypothesis_id: str) -> PreferenceHypothesis | None`.

- [ ] **Step 1: Write the failing persistence tests**

```python
from datetime import UTC, datetime

import pytest


def observation(**updates: object):
    from preference_learning import PreferenceObservation

    payload = {
        "observation_id": "pref-obs--turn-1",
        "user_id": "user-1",
        "project_id": "project-a",
        "session_id": "session-1",
        "source_turn_id": "turn-1",
        "source_message_id": "message-1",
        "category": "response_length",
        "canonical_value": "concise",
        "evidence_kind": "user_correction",
        "evidence_summary": "User corrected the answer to be shorter.",
        "confidence_delta": 0.35,
        "created_at": datetime(2026, 8, 28, tzinfo=UTC),
    }
    payload.update(updates)
    return PreferenceObservation.model_validate(payload)


def hypothesis(**updates: object):
    from preference_learning import PreferenceHypothesis

    payload = {
        "hypothesis_id": "pref-hyp--user-1--project-a--response_length",
        "user_id": "user-1",
        "project_id": "project-a",
        "category": "response_length",
        "canonical_value": "concise",
        "evidence_count": 2,
        "contradiction_count": 0,
        "confidence": 0.75,
        "source_observation_ids": ("pref-obs--turn-1", "pref-obs--turn-2"),
        "first_observed_at": datetime(2026, 8, 28, tzinfo=UTC),
        "last_observed_at": datetime(2026, 8, 28, tzinfo=UTC),
    }
    payload.update(updates)
    return PreferenceHypothesis.model_validate(payload)


@pytest.mark.asyncio
async def test_preference_observations_are_workspace_scoped(memory_database) -> None:
    await memory_database.save_preference_observation(observation())

    project_a = await memory_database.list_recent_preference_observations(
        "user-1",
        "project-a",
    )
    project_b = await memory_database.list_recent_preference_observations(
        "user-1",
        "project-b",
    )

    assert [item.observation_id for item in project_a] == ["pref-obs--turn-1"]
    assert project_b == ()


@pytest.mark.asyncio
async def test_preference_hypothesis_round_trips_by_workspace(memory_database) -> None:
    stored = hypothesis()

    await memory_database.save_preference_hypothesis(stored)

    assert await memory_database.get_preference_hypothesis(
        "user-1",
        "project-a",
        stored.hypothesis_id,
    ) == stored
    assert await memory_database.get_preference_hypothesis(
        "user-1",
        "project-b",
        stored.hypothesis_id,
    ) is None
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_preference_learning_database.py -q
```

Expected: FAIL because the database methods do not exist.

- [ ] **Step 3: Implement minimal Firestore persistence**

Use this path shape:

```text
users/{user_id}/workspaces/{project_id}/preference_observations/{observation_id}
users/{user_id}/workspaces/{project_id}/preference_hypotheses/{hypothesis_id}
```

Rules:

- Validate `observation.user_id == user_id` and `observation.project_id == project_id` before write.
- Validate `hypothesis.user_id == user_id` and `hypothesis.project_id == project_id` before write.
- Store only bounded model dumps; no raw transcript field.
- List only same-user, same-workspace observations.
- Return newest observations first, bounded by `limit`.
- Do not write `memory_proposals`, `memory_events`, active profile fields, chat messages, notes, artifacts, or working state.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
venv/bin/pytest tests/test_preference_learning_database.py -q
```

Expected: PASS.

---

### Task 3: Preference Learning Service

**Files:**
- Create: `preference_learning_service.py`
- Create: `tests/test_preference_learning_service.py`

**Interfaces:**
- Consumes: current turn metadata, user message, model response, recent observations, existing hypothesis.
- Produces: `PreferenceLearningCommand`, `PreferenceLearningResult`, `PreferenceLearningService.capture(command: PreferenceLearningCommand) -> PreferenceLearningResult`.

- [ ] **Step 1: Write the failing service tests**

```python
from datetime import UTC, datetime

import pytest


class FakeDatabase:
    def __init__(self) -> None:
        self.saved_observations = []
        self.saved_hypotheses = []
        self.hypothesis = None

    async def save_preference_observation(self, observation):
        self.saved_observations.append(observation)

    async def get_preference_hypothesis(self, user_id, project_id, hypothesis_id):
        return self.hypothesis

    async def save_preference_hypothesis(self, hypothesis):
        self.saved_hypotheses.append(hypothesis)
        self.hypothesis = hypothesis


class FakeExtractor:
    async def extract(self, command):
        return {
            "category": "response_length",
            "canonical_value": "concise",
            "evidence_kind": "user_correction",
            "evidence_summary": "User corrected the answer to be shorter.",
            "confidence_delta": 0.35,
        }


@pytest.mark.asyncio
async def test_capture_stores_validated_observation_without_active_memory() -> None:
    from preference_learning_service import (
        PreferenceLearningCommand,
        PreferenceLearningService,
    )

    database = FakeDatabase()
    service = PreferenceLearningService(
        database=database,
        extractor=FakeExtractor(),
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )

    result = await service.capture(
        PreferenceLearningCommand(
            user_id="user-1",
            project_id="project-1",
            session_id="session-1",
            turn_id="turn-1",
            source_message_id="message-1",
            user_message="That was too long; be shorter.",
            model_response="A long response.",
        )
    )

    assert result.observation is not None
    assert result.observation.can_adapt_response is False
    assert database.saved_observations == [result.observation]
    assert result.surfaced_hypothesis is None


@pytest.mark.asyncio
async def test_capture_surfaces_only_confirmable_hypothesis_after_repeated_evidence() -> None:
    from preference_learning_service import (
        PreferenceLearningCommand,
        PreferenceLearningService,
    )

    database = FakeDatabase()
    service = PreferenceLearningService(
        database=database,
        extractor=FakeExtractor(),
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )

    first = PreferenceLearningCommand(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        turn_id="turn-1",
        source_message_id="message-1",
        user_message="That was too long; be shorter.",
        model_response="A long response.",
    )
    second = PreferenceLearningCommand(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        turn_id="turn-2",
        source_message_id="message-2",
        user_message="Again, concise please.",
        model_response="Another long response.",
    )

    await service.capture(first)
    result = await service.capture(second)

    assert result.surfaced_hypothesis is not None
    assert result.surfaced_hypothesis.authority == "non_authoritative_hypothesis"
    assert result.surfaced_hypothesis.can_adapt_response is False


@pytest.mark.asyncio
async def test_extraction_failure_is_no_effect(caplog) -> None:
    from preference_learning_service import (
        PreferenceLearningCommand,
        PreferenceLearningService,
    )

    class FailingExtractor:
        async def extract(self, command):
            raise RuntimeError("private response text")

    service = PreferenceLearningService(
        database=FakeDatabase(),
        extractor=FailingExtractor(),
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )

    result = await service.capture(
        PreferenceLearningCommand(
            user_id="user-1",
            project_id="project-1",
            session_id="session-1",
            turn_id="turn-1",
            source_message_id="message-1",
            user_message="That was too long; be shorter.",
            model_response="A long response.",
        )
    )

    assert result.observation is None
    assert result.surfaced_hypothesis is None
    assert "private response text" not in caplog.text
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_preference_learning_service.py -q
```

Expected: FAIL because `preference_learning_service` does not exist.

- [ ] **Step 3: Implement minimal service**

Rules:

- The service may call a narrow extractor, but deterministic code must validate every accepted observation.
- The first approved implementation pass may use an injected deterministic fake extractor in tests and a no-effect production default if a live model extraction prompt needs a later approval pass.
- Generate observation IDs from `turn_id`, for example `pref-obs--{turn_id}`.
- Generate hypothesis IDs through `derive_preference_hypothesis_id`.
- Catch extractor/provider errors and return no effect.
- Log only exception class and safe IDs, not messages, transcript text, model output, or canonical memory values.
- Never create memory proposals or active memory.
- Never call `MemoryContextRenderer`.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
venv/bin/pytest tests/test_preference_learning_service.py tests/test_preference_learning.py -q
```

Expected: PASS.

---

### Task 4: Confirmation Bridge Into Governed Memory

**Files:**
- Modify: `trusted_memory_service.py`
- Modify: `memory_clarifications.py` if needed.
- Modify: `memory_proposals.py` if needed.
- Modify: `schemas.py` if needed.
- Create or modify: `tests/test_trusted_memory_service.py`
- Create or modify: `tests/test_memory_clarifications.py`

**Interfaces:**
- Consumes: `PreferenceHypothesis`.
- Produces: `open_preference_hypothesis_confirmation(user_id: str, project_id: str, session_id: str, source_message_id: str, turn_lease: ProposalTurnLease, hypothesis: PreferenceHypothesis) -> MemoryClarificationReceipt`.

- [ ] **Step 1: Write the failing confirmation tests**

```python
from datetime import UTC, datetime

import pytest


def hypothesis():
    from preference_learning import PreferenceHypothesis

    return PreferenceHypothesis(
        hypothesis_id="pref-hyp--user-1--project-1--response_length",
        user_id="user-1",
        project_id="project-1",
        category="response_length",
        canonical_value="concise",
        evidence_count=2,
        contradiction_count=0,
        confidence=0.75,
        source_observation_ids=("pref-obs--turn-1", "pref-obs--turn-2"),
        first_observed_at=datetime(2026, 8, 28, tzinfo=UTC),
        last_observed_at=datetime(2026, 8, 28, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_preference_hypothesis_confirmation_opens_unsaved_memory_choice(
    memory_service,
) -> None:
    from memory_proposals import ProposalTurnLease

    receipt = await memory_service.open_preference_hypothesis_confirmation(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_message_id="message-3",
        turn_lease=ProposalTurnLease(
            turn_id="a" * 64,
            owner_token="owner-1",
        ),
        hypothesis=hypothesis(),
    )

    assert receipt.choices[0].category_label == "Response length"
    assert receipt.choices[0].value_label == "concise"
    assert "saved" not in receipt.choices[0].value_label.lower()


@pytest.mark.asyncio
async def test_confirmed_hypothesis_creates_pending_proposal_not_active_memory(
    memory_service,
) -> None:
    from memory_proposals import ProposalTurnLease
    from trusted_memory_service import (
        InspectMemoryCommand,
        SelectMemoryClarificationCommand,
    )

    receipt = await memory_service.open_preference_hypothesis_confirmation(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_message_id="message-3",
        turn_lease=ProposalTurnLease(
            turn_id="a" * 64,
            owner_token="owner-1",
        ),
        hypothesis=hypothesis(),
    )

    result = await memory_service.select_memory_clarification(
        SelectMemoryClarificationCommand(
            user_id="user-1",
            workspace_id="project-1",
            session_id="session-1",
            source_message_id="message-4",
            clarification_id=receipt.clarification_id,
            selected_candidate_index=0,
            turn_lease=ProposalTurnLease(
                turn_id="b" * 64,
                owner_token="owner-2",
            ),
        )
    )
    inspection = await memory_service.inspect_memory(
        InspectMemoryCommand(user_id="user-1")
    )

    assert result.status == "pending"
    assert result.proposal.category == "response_length"
    assert result.proposal.proposed_value == "concise"
    assert inspection.profile.active_preferences == {}
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_trusted_memory_service.py::test_preference_hypothesis_confirmation_opens_unsaved_memory_choice \
  tests/test_trusted_memory_service.py::test_confirmed_hypothesis_creates_pending_proposal_not_active_memory -q
```

Expected: FAIL because the confirmation bridge does not exist.

- [ ] **Step 3: Implement the confirmation bridge**

Rules:

- Open at most one server-owned confirmation per turn.
- Represent the confirmation as a memory clarification with one real candidate and one explicit "do not save this preference" choice only if the current receipt model still requires `min_length=2`.
- Do not claim the preference is saved.
- Selection of the save choice creates a pending `MemoryProposalV2`; it does not approve memory.
- Selection of the do-not-save choice consumes or expires the confirmation without creating a proposal.
- Preserve current ownership, expiry, first-subsequent-turn, idempotency, and conflict rules from `memory_clarifications.py`.
- Store hypothesis provenance as safe IDs and evidence count, not raw transcript text.

- [ ] **Step 4: Run focused bridge tests**

Run:

```bash
venv/bin/pytest tests/test_memory_clarifications.py tests/test_trusted_memory_service.py -q
```

Expected: PASS.

---

### Task 5: Chat Turn Integration

**Files:**
- Modify: `main.py`
- Modify: `preference_learning_service.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes: completed non-replay ordinary chat turn, `ChatTurnClaim`, current user message, final model response, user/workspace/session/message IDs, precompleted memory/note/artifact effects.
- Produces: zero or one persisted observation, zero or one persisted/surfaced hypothesis confirmation.

- [ ] **Step 1: Write the failing chat integration tests**

```python
import pytest


@pytest.mark.asyncio
async def test_chat_records_preference_observation_without_active_memory(
    client,
    service_state,
) -> None:
    service_state.preference_learning_service.observation_payload = {
        "category": "response_length",
        "canonical_value": "concise",
        "evidence_kind": "user_correction",
        "evidence_summary": "User corrected the response to be shorter.",
        "confidence_delta": 0.35,
    }

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "agent-col",
            "session_id": "session-1",
            "user_id": "local-user",
            "message": "That was too long; be shorter here.",
        },
        headers={"Idempotency-Key": "pref-chat-key-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["memory_proposals"] == []
    assert body["memory_clarifications"] == []
    assert service_state.preference_learning_service.calls


@pytest.mark.asyncio
async def test_chat_surfaces_preference_confirmation_without_saving_memory(
    client,
    service_state,
) -> None:
    service_state.preference_learning_service.surface_confirmation = True

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "agent-col",
            "session_id": "session-1",
            "user_id": "local-user",
            "message": "Again, concise practical answers please.",
        },
        headers={"Idempotency-Key": "pref-chat-key-2"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["memory_clarifications"]) == 1
    assert body["memory_proposals"] == []
    assert body["adaptations"] == []


@pytest.mark.asyncio
async def test_chat_does_not_capture_preference_on_replay_or_structured_decision(
    client,
    service_state,
) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "project_id": "agent-col",
            "session_id": "session-1",
            "user_id": "local-user",
            "message": "Approve this memory.",
            "memory_decision": {
                "proposal_id": "response_length--proposal-1",
                "decision": "approve",
            },
        },
        headers={"Idempotency-Key": "pref-chat-key-3"},
    )

    assert response.status_code in {200, 404, 409, 410, 422}
    assert service_state.preference_learning_service.calls == []
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
venv/bin/pytest tests/test_main.py::test_chat_records_preference_observation_without_active_memory \
  tests/test_main.py::test_chat_surfaces_preference_confirmation_without_saving_memory \
  tests/test_main.py::test_chat_does_not_capture_preference_on_replay_or_structured_decision -q
```

Expected: FAIL because `app.state.preference_learning_service` and chat integration do not exist.

- [ ] **Step 3: Implement minimal orchestration**

Rules:

- Instantiate `PreferenceLearningService` in lifespan and store it on `app.state`.
- Run capture only after `database.complete_chat_turn(...)` succeeds for non-replay ordinary turns.
- Do not run on memory decisions, memory clarification selections, artifact feedback decisions, collaborative note decisions, continuity selections, failed turns, or replayed turns.
- Do not run when the current turn already created a memory proposal, memory clarification, note proposal, note event, artifact feedback effect, or failure response.
- If capture returns a surfaced hypothesis, call the confirmation bridge and merge the resulting `MemoryClarificationReceipt` into the response only when no other memory clarification/proposal is present.
- Capture failure is non-blocking and privacy-safe.
- Never inject an unconfirmed hypothesis into model input context or adaptation receipts.

- [ ] **Step 4: Run focused chat tests**

Run:

```bash
venv/bin/pytest tests/test_main.py::test_chat_records_preference_observation_without_active_memory \
  tests/test_main.py::test_chat_surfaces_preference_confirmation_without_saving_memory \
  tests/test_main.py::test_chat_does_not_capture_preference_on_replay_or_structured_decision \
  tests/test_main.py::test_chat_uses_hidden_working_state_without_public_response_fields \
  tests/test_main.py::test_chat_replays_completed_expert_receipts_without_service_access -q
```

Expected: PASS.

---

### Task 6: Frontend Confirmation Compatibility Check

**Files:**
- Modify: `frontend/chat-view.mjs` only if current labels cannot safely distinguish the confirmation.
- Modify: `frontend/state.mjs` only if current one-active-clarification state cannot preserve the receipt.
- Modify: `frontend/requests.mjs` only if current selection request is insufficient.
- Modify: `tests/frontend/chat-view.test.mjs`, `tests/frontend/state.test.mjs`, `tests/frontend/requests.test.mjs` only if frontend source changes are needed.

**Interfaces:**
- Consumes: `ChatResponse.memory_clarifications[0]`.
- Produces: one user-clicked `memory_clarification_selection`.

- [ ] **Step 1: Write failing frontend tests only if a frontend gap is confirmed**

Use the existing public frontend test harness, not private helpers inside
`chat-view.mjs`. The test should deliver a `ChatResponse` with one
`memory_clarifications[0]` receipt through the same path used by current
chat-view tests, then assert:

- the response-length candidate is visible;
- the "do not save" candidate is visible;
- the selected choice sends `memory_clarification_selection`;
- the UI does not describe the hypothesis as saved, remembered, or active.

- [ ] **Step 2: Run frontend tests to verify RED if Step 1 added a test**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs tests/frontend/state.test.mjs tests/frontend/requests.test.mjs
```

Expected: FAIL only for the unsupported confirmation rendering or request construction.

- [ ] **Step 3: Implement minimal frontend changes if required**

Rules:

- Reuse the existing clarification button pattern.
- Do not expose internal clarification IDs in visible text.
- Do not claim memory is saved before approval.
- Preserve existing memory proposal, approval, rejection, revoke, delete, retry, continuity, and note behavior.
- If no frontend gap is found, do not change frontend source.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs tests/frontend/state.test.mjs tests/frontend/requests.test.mjs
```

Expected: PASS.

---

### Task 7: Cross-Target-A Regression Verification And Report

**Files:**
- No production files unless an earlier task exposes a source-backed gap.
- Inspect: changed Python, JavaScript, and documentation files.

**Interfaces:**
- Confirms Target A did not regress governed memory, note separation, hidden working state, responder-only expert boundaries, or idempotent chat replay.

- [ ] **Step 1: Run focused Python regression checks**

Run:

```bash
venv/bin/pytest \
  tests/test_preference_learning.py \
  tests/test_preference_learning_database.py \
  tests/test_preference_learning_service.py \
  tests/test_memory_policy.py \
  tests/test_memory_policy_v2.py \
  tests/test_memory_candidate_decisions.py \
  tests/test_memory_clarifications.py \
  tests/test_memory_proposal_service.py \
  tests/test_trusted_memory_service.py \
  tests/test_memory_context.py \
  tests/test_main.py -q
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend checks if frontend changed**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs tests/frontend/state.test.mjs tests/frontend/requests.test.mjs
```

Expected: PASS.

- [ ] **Step 3: Verify no prohibited dependency or authority expansion**

Run:

```bash
rg -n "Cloud Tasks|private worker|durable async|background memory extraction|autonomous background|raw transcript mining|can_adapt_response: Literal\\[True\\]|is_active_memory: Literal\\[True\\]" \
  preference_learning.py preference_learning_service.py main.py database.py trusted_memory_service.py memory_context.py tests
```

Expected: no new Target A dependency on Cloud Tasks, private worker, durable async artifacts, background extraction, raw transcript mining, or direct adaptation from unconfirmed hypotheses.

- [ ] **Step 4: Run whitespace/static check**

Run:

```bash
git diff --check
```

Expected: PASS.

- [ ] **Step 5: Prepare implementation-pass report**

Use the repository pass-report template from `AGENTS.md`. Report status as:

```markdown
Implemented, pending manual verification.
```

Manual verification targets:

1. In one chat, correct Agent Col's collaboration style at least twice. Expected: Agent Col may ask whether it should remember the possible preference, but it must not claim the preference is saved.
2. Select the save confirmation. Expected: a pending governed memory proposal appears; active memory still does not change until approval.
3. Approve the proposal through the existing memory lifecycle. Expected: later chat responses adapt and show existing adaptation receipts.
4. Reject or ignore a confirmation. Expected: no active memory and no adaptation from the unconfirmed hypothesis.
5. Give contradictory style corrections. Expected: no confident memory prompt is surfaced from conflicting evidence.

- [ ] **Step 6: Stop for user manual verification and acceptance**

No GitHub checkpoint for Target A source changes until the user confirms the implemented pass is accepted.

## Approval Question

Do you approve starting **Target A Task 1: Preference Learning Domain And M9 Contract Policy Revision** only?

If approved, the first source-changing pass is limited to:

- `preference_learning.py`
- `tests/test_preference_learning.py`
- the explicit M9 contract policy revision in `docs/superpowers/specs/2026-08-24-m9-mem-1-governed-profile-memory-scope-and-natural-request-design.md`

The pass will not touch `main.py`, `database.py`, frontend files, production hardening, deployment, Target B, or active memory rendering.
