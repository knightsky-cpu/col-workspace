from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError


NOW = datetime(2026, 8, 24, tzinfo=UTC)


def v1_signal() -> dict[str, object]:
    return {
        "signal_id": "response_length--signal-v1",
        "category": "response_length",
        "value": "concise",
        "policy_version": "1.0",
        "source_event_id": "response_length--signal-v1--approved",
        "approved_at": NOW,
    }


def v2_signal(
    *,
    category: str = "development_environments",
    value: object = ("linux", "macos"),
    suffix: str = "v2",
) -> dict[str, object]:
    return {
        "signal_id": f"{category}--signal-{suffix}",
        "category": category,
        "value": list(value) if isinstance(value, tuple) else value,
        "policy_version": "2.0",
        "source_event_id": f"{category}--signal-{suffix}--approved",
        "approved_at": NOW,
    }


def test_v2_proposal_requires_explicit_evidence_provenance() -> None:
    from schemas import MemoryProposalV2

    payload = {
        "proposal_id": "development_environments--proposal-v2",
        "category": "development_environments",
        "proposed_value": ["linux", "macos"],
        "expected_signal_id": None,
        "policy_version": "2.0",
        "status": "pending",
        "source_session_id": "session-1",
        "source_message_id": "message-1",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=24),
    }

    with pytest.raises(ValidationError):
        MemoryProposalV2.model_validate(payload)

    proposal = MemoryProposalV2.model_validate(
        {**payload, "evidence_message_id": "message-1"}
    )
    assert proposal.proposed_value == ["macos", "linux"]
    assert proposal.clarification_id is None


def test_v2_provenance_distinguishes_direct_and_clarified_selection() -> None:
    from schemas import MemoryProposalV2, MemorySourceProvenanceV2

    with pytest.raises(ValidationError):
        MemorySourceProvenanceV2(
            source_message_id="selection-message",
            evidence_message_id="evidence-message",
        )

    with pytest.raises(ValidationError):
        MemorySourceProvenanceV2(
            source_message_id="selection-message",
            evidence_message_id="selection-message",
            clarification_id="clarification-1",
        )

    clarified = MemoryProposalV2(
        proposal_id="development_environments--proposal-v2",
        category="development_environments",
        proposed_value=["linux", "macos"],
        expected_signal_id=None,
        status="pending",
        source_session_id="session-1",
        source_message_id="selection-message",
        evidence_message_id="evidence-message",
        clarification_id="clarification-1",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )

    assert clarified.evidence_message_id == "evidence-message"
    assert clarified.clarification_id == "clarification-1"


def test_v2_event_retains_selection_evidence_provenance() -> None:
    from schemas import MemoryEventV2

    event = MemoryEventV2(
        event_id="development_environments--signal-v2--approved",
        event_type="approved",
        signal_id="development_environments--signal-v2",
        category="development_environments",
        value=["linux", "macos"],
        source_type="explicit_user_feedback",
        source_session_id="session-1",
        source_message_id="selection-message",
        evidence_message_id="evidence-message",
        clarification_id="clarification-1",
        confirmation_channel="chat_decision",
        confirmation_session_id="session-1",
        confirmation_message_id="approval-message",
        related_signal_id=None,
        memory_revision=2,
        created_at=NOW,
    )

    assert event.value == ["macos", "linux"]
    assert event.policy_version == "2.0"


def test_v2_profile_accepts_mixed_policy_signals_and_caps_total_at_ten() -> None:
    from schemas import CollaborationProfileV2

    profile = CollaborationProfileV2(
        memory_revision=2,
        identity_context={},
        active_preferences={
            "response_length": v1_signal(),
            "development_environments": v2_signal(),
        },
    )
    assert profile.memory_schema_version == "2.0"
    assert profile.active_preferences["response_length"].policy_version == (
        "1.0"
    )
    assert profile.active_preferences[
        "development_environments"
    ].policy_version == "2.0"

    preferences = {
        "response_length": v1_signal(),
        "explanation_structure": v2_signal(
            category="explanation_structure",
            value="step_by_step",
        ),
        "explanation_pace": v2_signal(
            category="explanation_pace",
            value="balanced",
        ),
        "example_usage": v2_signal(
            category="example_usage",
            value="when_helpful",
        ),
        "learning_approach": v2_signal(
            category="learning_approach",
            value="concept_first",
        ),
        "question_style": v2_signal(
            category="question_style",
            value="minimal_follow_up",
        ),
        "planning_granularity": v2_signal(
            category="planning_granularity",
            value="tasks",
        ),
        "progress_check_ins": v2_signal(
            category="progress_check_ins",
            value="at_milestones",
        ),
        "tool_use_style": v2_signal(
            category="tool_use_style",
            value="use_when_needed",
        ),
        "formatting_style": v2_signal(
            category="formatting_style",
            value="mixed",
        ),
        "development_environments": v2_signal(),
    }
    with pytest.raises(ValidationError):
        CollaborationProfileV2.model_validate(
            {
                "memory_revision": 2,
                "identity_context": {},
                "active_preferences": preferences,
            }
        )


def test_versioned_profile_reader_projects_v1_without_rewriting_signals() -> None:
    from schemas import (
        CollaborationProfile,
        CollaborationProfileV2,
        parse_collaboration_profile,
        project_collaboration_profile_v2,
    )

    source_document = {
        "memory_schema_version": "1.0",
        "memory_revision": 1,
        "identity_context": {},
        "active_preferences": {"response_length": v1_signal()},
    }
    parsed = parse_collaboration_profile(source_document)
    projected = project_collaboration_profile_v2(parsed)

    assert isinstance(parsed, CollaborationProfile)
    assert isinstance(projected, CollaborationProfileV2)
    assert projected.memory_schema_version == "2.0"
    assert projected.active_preferences[
        "response_length"
    ].policy_version == "1.0"
    assert source_document["memory_schema_version"] == "1.0"


def test_versioned_profile_reader_accepts_v2_and_rejects_unknown_versions() -> None:
    from schemas import CollaborationProfileV2, parse_collaboration_profile

    parsed = parse_collaboration_profile(
        {
            "memory_schema_version": "2.0",
            "memory_revision": 2,
            "identity_context": {},
            "active_preferences": {
                "development_environments": v2_signal()
            },
        }
    )
    assert isinstance(parsed, CollaborationProfileV2)

    with pytest.raises(ValueError, match="Unsupported memory schema version"):
        parse_collaboration_profile(
            {
                "memory_schema_version": "3.0",
                "memory_revision": 0,
                "identity_context": {},
                "active_preferences": {},
            }
        )


def test_v2_profile_rejects_unknown_nested_policy_and_v2_signal_in_v1_root() -> None:
    from schemas import parse_collaboration_profile

    unknown_policy_signal = v2_signal()
    unknown_policy_signal["policy_version"] = "3.0"
    with pytest.raises(ValidationError):
        parse_collaboration_profile(
            {
                "memory_schema_version": "2.0",
                "memory_revision": 2,
                "identity_context": {},
                "active_preferences": {
                    "development_environments": unknown_policy_signal
                },
            }
        )

    with pytest.raises(ValidationError):
        parse_collaboration_profile(
            {
                "memory_schema_version": "1.0",
                "memory_revision": 1,
                "identity_context": {},
                "active_preferences": {
                    "development_environments": v2_signal()
                },
            }
        )
