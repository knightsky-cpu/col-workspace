from datetime import UTC, datetime

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

    with pytest.raises(ValueError, match="not allowed"):
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

    assert hypothesis is not None
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
