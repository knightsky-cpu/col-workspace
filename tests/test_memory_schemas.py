from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError


NOW = datetime(2026, 8, 20, tzinfo=UTC)


def active_signal_payload(
    *,
    signal_id: str,
    category: str,
    value: object,
) -> dict[str, object]:
    return {
        "signal_id": signal_id,
        "category": category,
        "value": value,
        "policy_version": "1.0",
        "source_event_id": f"{signal_id}--approved",
        "approved_at": NOW,
    }


def memory_event_payload() -> dict[str, object]:
    return {
        "event_id": "signal-1--approved",
        "event_type": "approved",
        "signal_id": "signal-1",
        "category": "response_length",
        "value": "concise",
        "policy_version": "1.0",
        "source_type": "explicit_user_feedback",
        "source_session_id": "source-session",
        "source_message_id": "source-message",
        "confirmation_channel": "chat_decision",
        "confirmation_session_id": "confirmation-session",
        "confirmation_message_id": "confirmation-message",
        "related_signal_id": None,
        "memory_revision": 1,
        "created_at": NOW,
    }


def test_memory_proposal_accepts_normalized_bounded_value() -> None:
    from schemas import MemoryProposal

    created_at = datetime(2026, 8, 20, tzinfo=UTC)
    proposal = MemoryProposal.model_validate(
        {
            "proposal_id": "preferred_name--proposal-1",
            "category": "preferred_name",
            "proposed_value": "  Avery  ",
            "expected_signal_id": None,
            "policy_version": "1.0",
            "status": "pending",
            "source_session_id": "session-1",
            "source_message_id": "message-1",
            "created_at": created_at,
            "expires_at": created_at + timedelta(hours=24),
        }
    )

    assert proposal.proposed_value == "Avery"


def test_collaboration_profile_defaults_to_empty_versioned_projection() -> None:
    from schemas import CollaborationProfile

    profile = CollaborationProfile()

    assert profile.model_dump(mode="json") == {
        "memory_schema_version": "1.0",
        "memory_revision": 0,
        "identity_context": {},
        "active_preferences": {},
    }


@pytest.mark.parametrize(
    ("profile_field", "map_key", "signal_category", "value"),
    (
        (
            "identity_context",
            "preferred_name",
            "broad_roles",
            ["student"],
        ),
        (
            "active_preferences",
            "response_length",
            "formatting_style",
            "prose",
        ),
    ),
)
def test_collaboration_profile_rejects_map_key_category_mismatch(
    profile_field: str,
    map_key: str,
    signal_category: str,
    value: object,
) -> None:
    from schemas import CollaborationProfile

    with pytest.raises(ValidationError):
        CollaborationProfile.model_validate(
            {
                profile_field: {
                    map_key: active_signal_payload(
                        signal_id="signal-1",
                        category=signal_category,
                        value=value,
                    )
                }
            }
        )


def test_memory_event_accepts_complete_chat_confirmation_provenance() -> None:
    from schemas import MemoryEvent

    event = MemoryEvent.model_validate(memory_event_payload())

    assert event.confirmation_channel == "chat_decision"
    assert event.confirmation_session_id == "confirmation-session"
    assert event.confirmation_message_id == "confirmation-message"


@pytest.mark.parametrize(
    ("channel", "session_id", "message_id"),
    (
        ("chat_decision", None, "confirmation-message"),
        ("chat_decision", "confirmation-session", None),
        ("memory_api", "confirmation-session", "confirmation-message"),
        ("memory_api", None, "confirmation-message"),
    ),
)
def test_memory_event_rejects_confirmation_channel_mismatch(
    channel: str,
    session_id: str | None,
    message_id: str | None,
) -> None:
    from schemas import MemoryEvent

    payload = memory_event_payload()
    payload["confirmation_channel"] = channel
    payload["confirmation_session_id"] = session_id
    payload["confirmation_message_id"] = message_id

    with pytest.raises(ValidationError):
        MemoryEvent.model_validate(payload)


@pytest.mark.parametrize("decision", ("approve", "reject"))
def test_memory_decision_request_accepts_structured_user_authority(
    decision: str,
) -> None:
    from schemas import MemoryDecisionRequest

    request = MemoryDecisionRequest(
        proposal_id="response_length--proposal-1",
        decision=decision,
    )

    assert request.decision == decision


def test_chat_contract_carries_decision_and_adaptation_receipts() -> None:
    from schemas import ChatRequest, ChatResponse

    request = ChatRequest(
        project_id="project-1",
        session_id="session-1",
        user_id="user-1",
        message="Yes, remember that preference.",
        memory_decision={
            "proposal_id": "response_length--proposal-1",
            "decision": "approve",
        },
    )
    response = ChatResponse(
        response="I will use concise responses going forward.",
        adaptations=[
            {
                "signal_id": "response_length--proposal-1",
                "category": "response_length",
                "value": "concise",
                "source_event_id": (
                    "response_length--proposal-1--approved"
                ),
                "status": "provided_to_model",
            }
        ],
    )

    assert request.memory_decision is not None
    assert request.memory_decision.decision == "approve"
    assert response.adaptations[0].category == "response_length"


def test_chat_response_limits_adaptation_receipts() -> None:
    from schemas import ChatResponse

    receipt = {
        "signal_id": "response_length--proposal-1",
        "category": "response_length",
        "value": "concise",
        "source_event_id": "response_length--proposal-1--approved",
        "status": "provided_to_model",
    }

    with pytest.raises(ValidationError):
        ChatResponse(
            response="Bounded response",
            adaptations=[receipt] * 11,
        )


def test_memory_proposal_receipt_normalizes_server_derived_value() -> None:
    from schemas import MemoryProposalReceipt

    receipt = MemoryProposalReceipt(
        proposal_id="preferred_name--proposal-1",
        category="preferred_name",
        proposed_value="  Avery  ",
        expires_at=NOW + timedelta(hours=24),
    )

    assert receipt.proposed_value == "Avery"


def test_adaptation_receipt_accepts_only_provided_to_model_status() -> None:
    from schemas import AdaptationReceipt

    receipt = AdaptationReceipt(
        signal_id="signal-1",
        category="broad_roles",
        value=["researcher", "student"],
        source_event_id="signal-1--approved",
        status="provided_to_model",
    )

    assert receipt.value == ["student", "researcher"]
    assert receipt.status == "provided_to_model"


def test_memory_inspection_response_enforces_public_bounds() -> None:
    from schemas import MemoryInspectionResponse, MemoryProposal

    proposal = MemoryProposal(
        proposal_id="response_length--proposal-1",
        category="response_length",
        proposed_value="concise",
        expected_signal_id=None,
        status="pending",
        source_session_id="source-session",
        source_message_id="source-message",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    event = memory_event_payload()

    response = MemoryInspectionResponse(
        profile={},
        unresolved_proposals=[proposal],
        events=[event],
        next_event_id="signal-1--approved",
    )

    assert response.profile.memory_revision == 0
    assert response.unresolved_proposals == [proposal]
    assert response.events[0].event_id == "signal-1--approved"
    assert response.next_event_id == "signal-1--approved"

    with pytest.raises(ValidationError):
        MemoryInspectionResponse(
            profile={},
            unresolved_proposals=[proposal] * 11,
            events=[],
            next_event_id=None,
        )
    with pytest.raises(ValidationError):
        MemoryInspectionResponse(
            profile={},
            unresolved_proposals=[],
            events=[event] * 51,
            next_event_id=None,
        )
    with pytest.raises(ValidationError):
        MemoryInspectionResponse(
            profile={},
            unresolved_proposals=[],
            events=[],
            next_event_id=None,
            unexpected=True,
        )


def test_memory_mutation_response_is_strict_and_typed() -> None:
    from schemas import MemoryMutationResponse

    response = MemoryMutationResponse(
        action={
            "action_name": "revoke_memory_signal",
            "status": "completed",
        },
        profile={"memory_revision": 2},
    )

    assert response.action.action_name == "revoke_memory_signal"
    assert response.profile.memory_revision == 2

    with pytest.raises(ValidationError):
        MemoryMutationResponse(
            action={
                "action_name": "revoke_memory_signal",
                "status": "completed",
            },
            profile={},
            unexpected=True,
        )


def test_memory_models_reject_extra_fields_and_category_value_mismatch() -> None:
    from schemas import ActiveMemorySignal, MemoryProposal

    proposal_payload = {
        "proposal_id": "proposal-1",
        "category": "response_length",
        "proposed_value": "prose",
        "expected_signal_id": None,
        "policy_version": "1.0",
        "status": "pending",
        "source_session_id": "session-1",
        "source_message_id": "message-1",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=24),
    }
    signal_payload = active_signal_payload(
        signal_id="signal-1",
        category="broad_roles",
        value=["student"],
    )
    signal_payload["unexpected"] = "forbidden"

    with pytest.raises(ValidationError):
        MemoryProposal.model_validate(proposal_payload)
    with pytest.raises(ValidationError):
        ActiveMemorySignal.model_validate(signal_payload)


def test_collaboration_profile_rejects_category_family_and_bounds() -> None:
    from schemas import CollaborationProfile

    wrong_family = active_signal_payload(
        signal_id="signal-1",
        category="response_length",
        value="concise",
    )
    nine_preferences = {
        category: active_signal_payload(
            signal_id=f"signal-{index}",
            category=category,
            value=value,
        )
        for index, (category, value) in enumerate(
            (
                ("response_length", "concise"),
                ("explanation_structure", "step_by_step"),
                ("example_usage", "when_helpful"),
                ("question_style", "minimal_follow_up"),
                ("planning_granularity", "tasks"),
                ("progress_check_ins", "at_milestones"),
                ("tool_use_style", "minimize_tools"),
                ("formatting_style", "mixed"),
                ("ninth_category", "concise"),
            )
        )
    }

    with pytest.raises(ValidationError):
        CollaborationProfile(
            identity_context={"response_length": wrong_family}
        )
    with pytest.raises(ValidationError):
        CollaborationProfile(active_preferences=nine_preferences)
    with pytest.raises(ValidationError):
        CollaborationProfile(memory_revision=-1)
    with pytest.raises(ValidationError):
        CollaborationProfile(unexpected="forbidden")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("event_type", "created"),
        ("source_type", "model_inference"),
        ("memory_revision", 0),
        ("policy_version", "2.0"),
        ("value", "prose"),
    ),
)
def test_memory_event_rejects_invalid_contract_fields(
    field: str,
    value: object,
) -> None:
    from schemas import MemoryEvent

    payload = memory_event_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        MemoryEvent.model_validate(payload)


def test_memory_api_event_forbids_chat_confirmation_identifiers() -> None:
    from schemas import MemoryEvent

    payload = memory_event_payload()
    payload["confirmation_channel"] = "memory_api"
    payload["confirmation_session_id"] = None
    payload["confirmation_message_id"] = None

    event = MemoryEvent.model_validate(payload)

    assert event.confirmation_channel == "memory_api"


def test_decision_and_receipts_reject_invalid_public_values() -> None:
    from schemas import (
        AdaptationReceipt,
        MemoryDecisionRequest,
        MemoryProposalReceipt,
    )

    with pytest.raises(ValidationError):
        MemoryDecisionRequest(proposal_id="proposal-1", decision="yes")
    with pytest.raises(ValidationError):
        MemoryProposalReceipt(
            proposal_id="proposal-1",
            category="response_length",
            proposed_value="prose",
            expires_at=NOW,
        )
    with pytest.raises(ValidationError):
        AdaptationReceipt(
            signal_id="signal-1",
            category="response_length",
            value="concise",
            source_event_id="signal-1--approved",
            status="applied_by_model",
        )
