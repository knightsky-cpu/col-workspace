from datetime import UTC, datetime, timedelta

import pytest

from schemas import MemoryProposal


NOW = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)


class FakeProposalDatabase:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create_guarded_memory_proposal(self, **kwargs) -> MemoryProposal:
        self.calls.append(kwargs)
        ids = kwargs["origin_ids"]
        return MemoryProposal(
            proposal_id=ids.proposal_id,
            category=kwargs["category"],
            proposed_value=kwargs["proposed_value"],
            expected_signal_id=None,
            status="pending",
            source_session_id=kwargs["session_id"],
            source_message_id=kwargs["source_message_id"],
            created_at=kwargs["observed_at"],
            expires_at=kwargs["observed_at"] + timedelta(hours=24),
        )


def command(**updates):
    from trusted_memory_service import ProposeMemorySignalCommand

    values = {
        "user_id": "user-1",
        "session_id": "session-1",
        "source_message_id": "message-1",
        "source_message_text": "I prefer concise answers. Remember that.",
        "memory_decision_present": False,
        "category": "response_length",
        "proposed_value": "concise",
        "turn_lease": None,
    }
    values.update(updates)
    return ProposeMemorySignalCommand(**values)


@pytest.mark.asyncio
async def test_propose_memory_signal_normalizes_and_returns_stored_receipts(
) -> None:
    from trusted_memory_service import TrustedMemoryService

    database = FakeProposalDatabase()
    clock_calls = 0

    def clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        return NOW

    result = await TrustedMemoryService(
        database=database,
        clock=clock,
    ).propose_memory_signal(command())

    assert clock_calls == 1
    assert result.action.model_dump(mode="json") == {
        "action_name": "propose_memory_signal",
        "status": "completed",
    }
    assert result.proposal.model_dump(mode="json") == {
        "proposal_id": (
            "response_length--e82366f7699ee2e39bff6a68154e09b7"
        ),
        "category": "response_length",
        "proposed_value": "concise",
        "expires_at": "2026-08-22T14:00:00Z",
    }
    assert database.calls[0]["origin_ids"].origin_id == (
        "e82366f7699ee2e39bff6a68154e09b7"
    )


@pytest.mark.asyncio
async def test_propose_memory_signal_requires_preferred_name_in_source() -> None:
    from trusted_memory_service import TrustedMemoryService

    database = FakeProposalDatabase()
    service = TrustedMemoryService(database=database, clock=lambda: NOW)

    with pytest.raises(
        ValueError,
        match="Preferred name is absent from the current message",
    ):
        await service.propose_memory_signal(
            command(
                category="preferred_name",
                proposed_value="Avery",
                source_message_text="Please remember how I like responses.",
            )
        )

    assert database.calls == []


@pytest.mark.asyncio
async def test_propose_memory_signal_normalizes_grounded_identity_values() -> None:
    from trusted_memory_service import TrustedMemoryService

    database = FakeProposalDatabase()
    service = TrustedMemoryService(database=database, clock=lambda: NOW)

    preferred_name = await service.propose_memory_signal(
        command(
            category="preferred_name",
            proposed_value="  Avery  ",
            source_message_text="Please call me Avery.",
        )
    )
    broad_roles = await service.propose_memory_signal(
        command(
            source_message_id="message-2",
            category="broad_roles",
            proposed_value=["researcher", "student"],
            source_message_text=(
                "I am a student and researcher; remember that context."
            ),
        )
    )

    assert preferred_name.proposal.proposed_value == "Avery"
    assert broad_roles.proposal.proposed_value == ["student", "researcher"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "updates",
    (
        {"category": "unknown"},
        {"proposed_value": "bullets"},
        {"memory_decision_present": True},
        {"memory_decision_present": "false"},
        {"user_id": "user/1"},
        {"session_id": ""},
        {"source_message_id": "message/1"},
        {"source_message_text": "   "},
    ),
)
async def test_propose_memory_signal_rejects_before_database_access(
    updates: dict[str, object],
) -> None:
    from trusted_memory_service import TrustedMemoryService

    database = FakeProposalDatabase()
    service = TrustedMemoryService(database=database, clock=lambda: NOW)

    with pytest.raises(ValueError):
        await service.propose_memory_signal(command(**updates))

    assert database.calls == []
