from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from database import (
    MemoryApprovalResult,
    MemoryDeletionResult,
    MemoryRejectionResult,
    MemoryRevocationResult,
)
from schemas import (
    AgentActionReceipt,
    CollaborationProfile,
    CollaborationProfileV2,
    MemoryEvent,
    MemoryProposal,
    MemoryProposalV2,
)
from trusted_memory_service import (
    DeleteMemorySignalCommand,
    InspectMemoryCommand,
    MemoryDecisionCommand,
    RevokeMemorySignalCommand,
    SelectMemoryClarificationCommand,
    TrustedMemoryService,
)


NOW = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)
PROPOSAL_ID = "response_length--proposal-1"


def preference_hypothesis():
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
        first_observed_at=NOW,
        last_observed_at=NOW,
    )


def rejected_proposal() -> MemoryProposal:
    return MemoryProposal(
        proposal_id=PROPOSAL_ID,
        category="response_length",
        proposed_value="concise",
        expected_signal_id=None,
        status="rejected",
        source_session_id="source-session",
        source_message_id="source-message",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )


def approved_event() -> MemoryEvent:
    return MemoryEvent.model_validate(
        {
            "event_id": f"{PROPOSAL_ID}--approved",
            "event_type": "approved",
            "signal_id": PROPOSAL_ID,
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
    )


@pytest.mark.asyncio
async def test_preference_hypothesis_confirmation_opens_unsaved_memory_choice():
    database = MagicMock()
    database.create_memory_clarification = AsyncMock(
        side_effect=lambda *, envelope, **kwargs: envelope
    )
    service = TrustedMemoryService(database=database, clock=lambda: NOW)

    first = await service.open_preference_hypothesis_confirmation(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_message_id="message-3",
        turn_lease=None,
        hypothesis=preference_hypothesis(),
        confirmation_created_at=NOW,
    )
    second = await service.open_preference_hypothesis_confirmation(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_message_id="message-3",
        turn_lease=None,
        hypothesis=preference_hypothesis(),
        confirmation_created_at=NOW,
    )

    assert first == second
    assert first.choices[0].category_label == "Response length"
    assert first.choices[0].value_label == "concise"
    assert first.choices[1].category_label == "Do not save"
    assert "feedback only" in first.choices[1].value_label
    assert "saved" not in first.choices[0].value_label.lower()
    assert database.create_memory_clarification.await_count == 2
    first_call, second_call = database.create_memory_clarification.await_args_list
    first_envelope = first_call.kwargs["envelope"]
    second_envelope = second_call.kwargs["envelope"]
    assert first_envelope == second_envelope
    assert first_envelope.evidence_message_id == "message-3"
    assert first_envelope.clarification_turn_id != "message-3"
    assert first_call.kwargs["turn_lease"] is None
    assert second_call.kwargs["turn_lease"] is None


@pytest.mark.asyncio
async def test_preference_confirmation_identity_separates_distinct_hypotheses():
    database = MagicMock()
    database.create_memory_clarification = AsyncMock(
        side_effect=lambda *, envelope, **kwargs: envelope
    )
    service = TrustedMemoryService(database=database, clock=lambda: NOW)
    first_hypothesis = preference_hypothesis()
    second_hypothesis = first_hypothesis.model_copy(
        update={
            "hypothesis_id": "pref-hyp--user-1--project-1--example_usage",
            "category": "example_usage",
            "canonical_value": "when_helpful",
        }
    )

    await service.open_preference_hypothesis_confirmation(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_message_id="message-3",
        turn_lease=None,
        hypothesis=first_hypothesis,
        confirmation_created_at=NOW,
    )
    await service.open_preference_hypothesis_confirmation(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_message_id="message-3",
        turn_lease=None,
        hypothesis=second_hypothesis,
        confirmation_created_at=NOW,
    )

    first_call, second_call = database.create_memory_clarification.await_args_list
    assert (
        first_call.kwargs["envelope"].clarification_id
        != second_call.kwargs["envelope"].clarification_id
    )


@pytest.mark.asyncio
async def test_confirmed_hypothesis_creates_pending_proposal_not_active_memory():
    from memory_proposals import ProposalTurnLease

    proposal = MemoryProposalV2(
        proposal_id="response_length--from-preference-confirmation",
        category="response_length",
        proposed_value="concise",
        expected_signal_id=None,
        status="pending",
        source_session_id="session-1",
        source_message_id="message-4",
        evidence_message_id="message-3",
        clarification_id="memory-clarification--pref-hyp",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    database = MagicMock()
    database.create_memory_clarification = AsyncMock(
        side_effect=lambda *, envelope, **kwargs: envelope
    )
    database.consume_memory_clarification_to_proposal_v2 = AsyncMock(
        return_value=proposal
    )
    database.get_memory_inspection = AsyncMock(
        return_value=SimpleNamespace(
            profile=CollaborationProfileV2(),
            unresolved_proposals=(proposal,),
            events=(),
            next_event_id=None,
        )
    )
    service = TrustedMemoryService(database=database, clock=lambda: NOW)
    receipt = await service.open_preference_hypothesis_confirmation(
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_message_id="message-3",
        turn_lease=ProposalTurnLease(
            turn_id="a" * 64,
            owner_token="owner-1",
        ),
        hypothesis=preference_hypothesis(),
    )

    result = await service.select_memory_clarification(
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
    inspection = await service.inspect_memory(
        InspectMemoryCommand(user_id="user-1")
    )

    assert result.status == "pending"
    assert result.proposal.category == "response_length"
    assert result.proposal.proposed_value == "concise"
    assert inspection.profile.active_preferences == {}


@pytest.mark.asyncio
async def test_decide_memory_proposal_dispatches_rejection_once() -> None:
    database = MagicMock()
    database.reject_memory_proposal = AsyncMock(
        return_value=MemoryRejectionResult(
            profile=CollaborationProfile(),
            proposal=rejected_proposal(),
        )
    )
    service = TrustedMemoryService(database=database, clock=lambda: NOW)
    command = MemoryDecisionCommand(
        user_id="user-1",
        proposal_id=PROPOSAL_ID,
        decision="reject",
        confirmation_channel="chat_decision",
        confirmation_session_id="confirmation-session",
        confirmation_message_id="confirmation-message",
    )

    result = await service.decide_memory_proposal(command)

    assert result.profile == CollaborationProfile()
    assert result.action == AgentActionReceipt(
        action_name="reject_memory_signal",
        status="completed",
    )
    database.reject_memory_proposal.assert_awaited_once_with(
        "user-1",
        "response_length",
        PROPOSAL_ID,
        observed_at=NOW,
    )
    database.approve_memory_proposal.assert_not_called()


@pytest.mark.asyncio
async def test_decide_memory_proposal_dispatches_v2_category() -> None:
    proposal_id = "development_environments--proposal-v2"
    proposal = MemoryProposalV2(
        proposal_id=proposal_id,
        category="development_environments",
        proposed_value=["linux", "macos"],
        expected_signal_id=None,
        status="rejected",
        source_session_id="source-session",
        source_message_id="source-message",
        evidence_message_id="source-message",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    database = MagicMock()
    database.reject_memory_proposal = AsyncMock(
        return_value=MemoryRejectionResult(
            profile=CollaborationProfileV2(),
            proposal=proposal,
        )
    )
    service = TrustedMemoryService(database=database, clock=lambda: NOW)

    result = await service.decide_memory_proposal(
        MemoryDecisionCommand(
            user_id="user-1",
            proposal_id=proposal_id,
            decision="reject",
            confirmation_channel="chat_decision",
            confirmation_session_id="confirmation-session",
            confirmation_message_id="confirmation-message",
        )
    )

    assert result.profile == CollaborationProfileV2()
    database.reject_memory_proposal.assert_awaited_once_with(
        "user-1",
        "development_environments",
        proposal_id,
        observed_at=NOW,
    )


@pytest.mark.asyncio
async def test_decide_memory_proposal_dispatches_approval_with_provenance(
) -> None:
    database = MagicMock()
    database.approve_memory_proposal = AsyncMock(
        return_value=MemoryApprovalResult(
            profile=CollaborationProfile(memory_revision=1),
            event=approved_event(),
        )
    )
    clock = MagicMock(return_value=NOW)
    service = TrustedMemoryService(database=database, clock=clock)
    command = MemoryDecisionCommand(
        user_id="user-1",
        proposal_id=PROPOSAL_ID,
        decision="approve",
        confirmation_channel="chat_decision",
        confirmation_session_id="confirmation-session",
        confirmation_message_id="confirmation-message",
    )

    result = await service.decide_memory_proposal(command)

    assert result.profile.memory_revision == 1
    assert result.action == AgentActionReceipt(
        action_name="approve_memory_signal",
        status="completed",
    )
    database.approve_memory_proposal.assert_awaited_once_with(
        "user-1",
        "response_length",
        PROPOSAL_ID,
        confirmation_channel="chat_decision",
        confirmation_session_id="confirmation-session",
        confirmation_message_id="confirmation-message",
        observed_at=NOW,
    )
    database.reject_memory_proposal.assert_not_called()
    clock.assert_called_once_with()


@pytest.mark.asyncio
async def test_revoke_memory_signal_uses_memory_api_confirmation() -> None:
    database = MagicMock()
    revoked = approved_event().model_copy(
        update={
            "event_id": f"{PROPOSAL_ID}--revoked",
            "event_type": "revoked",
            "confirmation_channel": "memory_api",
            "confirmation_session_id": None,
            "confirmation_message_id": None,
            "memory_revision": 2,
        }
    )
    database.revoke_memory_signal = AsyncMock(
        return_value=MemoryRevocationResult(
            profile=CollaborationProfile(memory_revision=2),
            event=revoked,
        )
    )
    service = TrustedMemoryService(database=database, clock=lambda: NOW)

    result = await service.revoke_memory_signal(
        RevokeMemorySignalCommand(
            user_id="user-1",
            signal_id=PROPOSAL_ID,
        )
    )

    assert result.profile.memory_revision == 2
    assert result.action == AgentActionReceipt(
        action_name="revoke_memory_signal",
        status="completed",
    )
    database.revoke_memory_signal.assert_awaited_once_with(
        "user-1",
        "response_length",
        PROPOSAL_ID,
        confirmation_channel="memory_api",
        confirmation_session_id=None,
        confirmation_message_id=None,
        observed_at=NOW,
    )


@pytest.mark.asyncio
async def test_delete_memory_signal_returns_completed_idempotent_action(
) -> None:
    database = MagicMock()
    database.delete_memory_signal = AsyncMock(
        return_value=MemoryDeletionResult(
            profile=CollaborationProfile(memory_revision=3),
            artifacts_deleted=False,
        )
    )
    clock = MagicMock(return_value=NOW)
    service = TrustedMemoryService(database=database, clock=clock)

    result = await service.delete_memory_signal(
        DeleteMemorySignalCommand(
            user_id="user-1",
            signal_id=PROPOSAL_ID,
        )
    )

    assert result.profile.memory_revision == 3
    assert result.action == AgentActionReceipt(
        action_name="delete_memory_signal",
        status="completed",
    )
    database.delete_memory_signal.assert_awaited_once_with(
        "user-1",
        "response_length",
        PROPOSAL_ID,
    )
    clock.assert_not_called()


@pytest.mark.asyncio
async def test_decide_memory_proposal_rejects_invalid_confirmation_boundary(
) -> None:
    database = MagicMock()
    database.reject_memory_proposal = AsyncMock()
    clock = MagicMock(return_value=NOW)
    service = TrustedMemoryService(database=database, clock=clock)

    with pytest.raises(ValueError):
        await service.decide_memory_proposal(
            MemoryDecisionCommand(
                user_id="user-1",
                proposal_id=PROPOSAL_ID,
                decision="reject",
                confirmation_channel="chat_decision",
                confirmation_session_id=None,
                confirmation_message_id=None,
            )
        )

    database.reject_memory_proposal.assert_not_called()
    database.approve_memory_proposal.assert_not_called()
    clock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("decide", "revoke", "delete"))
async def test_memory_service_rejects_invalid_identifier_before_dispatch(
    operation: str,
) -> None:
    database = MagicMock()
    database.approve_memory_proposal = AsyncMock()
    database.reject_memory_proposal = AsyncMock()
    database.revoke_memory_signal = AsyncMock()
    database.delete_memory_signal = AsyncMock()
    clock = MagicMock(return_value=NOW)
    service = TrustedMemoryService(database=database, clock=clock)
    invalid_id = "response_length--bad/slash"

    with pytest.raises(ValueError):
        if operation == "decide":
            await service.decide_memory_proposal(
                MemoryDecisionCommand(
                    user_id="user-1",
                    proposal_id=invalid_id,
                    decision="reject",
                    confirmation_channel="memory_api",
                    confirmation_session_id=None,
                    confirmation_message_id=None,
                )
            )
        elif operation == "revoke":
            await service.revoke_memory_signal(
                RevokeMemorySignalCommand(
                    user_id="user-1",
                    signal_id=invalid_id,
                )
            )
        else:
            await service.delete_memory_signal(
                DeleteMemorySignalCommand(
                    user_id="user-1",
                    signal_id=invalid_id,
                )
            )

    database.approve_memory_proposal.assert_not_called()
    database.reject_memory_proposal.assert_not_called()
    database.revoke_memory_signal.assert_not_called()
    database.delete_memory_signal.assert_not_called()
    clock.assert_not_called()


@pytest.mark.asyncio
async def test_inspect_memory_uses_one_observation_time_and_cursor() -> None:
    from trusted_memory_service import InspectMemoryCommand

    pending_proposal = rejected_proposal().model_copy(
        update={"status": "pending"}
    )
    database = MagicMock()
    database.get_memory_inspection = AsyncMock(
        return_value=SimpleNamespace(
            profile=CollaborationProfile(memory_revision=4),
            unresolved_proposals=(pending_proposal,),
            events=(approved_event(),),
            next_event_id="response_length--earlier--approved",
        )
    )
    clock = MagicMock(return_value=NOW)
    service = TrustedMemoryService(database=database, clock=clock)

    result = await service.inspect_memory(
        InspectMemoryCommand(
            user_id="user-1",
            after_event_id="response_length--cursor--approved",
        )
    )

    assert result.profile.memory_revision == 4
    assert result.unresolved_proposals == (pending_proposal,)
    assert result.events == (approved_event(),)
    assert result.next_event_id == "response_length--earlier--approved"
    database.get_memory_inspection.assert_awaited_once_with(
        "user-1",
        observed_at=NOW,
        after_event_id="response_length--cursor--approved",
    )
    clock.assert_called_once_with()
