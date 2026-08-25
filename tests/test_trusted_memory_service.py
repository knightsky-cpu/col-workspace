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
    MemoryDecisionCommand,
    RevokeMemorySignalCommand,
    TrustedMemoryService,
)


NOW = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)
PROPOSAL_ID = "response_length--proposal-1"


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
