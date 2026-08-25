from datetime import UTC, datetime, timedelta

import pytest

from schemas import MemoryProposal, MemoryProposalV2


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

    async def create_guarded_memory_proposal_v2(
        self,
        **kwargs,
    ) -> MemoryProposalV2:
        self.calls.append(kwargs)
        ids = kwargs["origin_ids"]
        return MemoryProposalV2(
            proposal_id=ids.proposal_id,
            category=kwargs["category"],
            proposed_value=kwargs["proposed_value"],
            expected_signal_id=None,
            status="pending",
            source_session_id=kwargs["session_id"],
            source_message_id=kwargs["source_message_id"],
            evidence_message_id=kwargs["evidence_message_id"],
            clarification_id=kwargs["clarification_id"],
            created_at=kwargs["observed_at"],
            expires_at=kwargs["observed_at"] + timedelta(hours=24),
        )

    async def consume_memory_clarification_to_proposal_v2(
        self,
        **kwargs,
    ) -> MemoryProposalV2:
        self.calls.append(kwargs)
        return MemoryProposalV2(
            proposal_id="development_environments--clarified-proposal",
            category="development_environments",
            proposed_value=["macos", "linux"],
            expected_signal_id=None,
            status="pending",
            source_session_id=kwargs["session_id"],
            source_message_id=kwargs["source_message_id"],
            evidence_message_id="message-1",
            clarification_id="memory-clarification--clarify-1",
            created_at=kwargs["observed_at"],
            expires_at=kwargs["observed_at"] + timedelta(hours=24),
        )

    async def create_memory_clarification(
        self,
        *,
        envelope,
        observed_at,
        turn_lease,
    ):
        self.calls.append(
            {
                "envelope": envelope,
                "observed_at": observed_at,
                "turn_lease": turn_lease,
            }
        )
        return envelope


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


def natural_command(**updates):
    from memory_candidate_decisions import ProfileCandidateDecision
    from trusted_memory_service import NaturalMemoryCommand

    values = {
        "user_id": "user-1",
        "workspace_id": "workspace-1",
        "session_id": "session-1",
        "source_message_id": "message-1",
        "source_message_text": (
            "Please remember that I prefer macOS and Linux environments."
        ),
        "memory_decision_present": False,
        "decision": ProfileCandidateDecision(
            category="development_environments",
            canonical_value=["macos", "linux"],
            evidence_text="macOS and Linux environments",
        ),
        "clarification_selection": None,
        "turn_lease": None,
    }
    values.update(updates)
    return NaturalMemoryCommand(**values)


@pytest.mark.asyncio
async def test_natural_profile_candidate_persists_version_2_proposal() -> None:
    from trusted_memory_service import (
        NaturalMemoryProposalResult,
        TrustedMemoryService,
    )

    database = FakeProposalDatabase()
    result = await TrustedMemoryService(
        database=database,
        clock=lambda: NOW,
    ).handle_natural_memory_decision(natural_command())

    assert isinstance(result, NaturalMemoryProposalResult)
    assert result.status == "pending"
    assert result.action.action_name == "propose_memory_signal"
    assert result.proposal.model_dump(mode="json") == {
        "proposal_id": (
            "development_environments--"
            "ada68682134ed3b8701d2e545891ad8a"
        ),
        "category": "development_environments",
        "proposed_value": ["macos", "linux"],
        "policy_version": "2.0",
        "expires_at": "2026-08-22T14:00:00Z",
    }
    assert database.calls == [
        {
            "user_id": "user-1",
            "session_id": "session-1",
            "source_message_id": "message-1",
            "evidence_message_id": "message-1",
            "clarification_id": None,
            "origin_ids": database.calls[0]["origin_ids"],
            "category": "development_environments",
            "proposed_value": ["macos", "linux"],
            "observed_at": NOW,
            "turn_lease": None,
        }
    ]


@pytest.mark.asyncio
async def test_natural_profile_candidate_rejects_non_source_evidence() -> None:
    from memory_candidate_decisions import ProfileCandidateDecision
    from trusted_memory_service import TrustedMemoryService

    database = FakeProposalDatabase()
    decision = ProfileCandidateDecision(
        category="response_length",
        canonical_value="detailed",
        evidence_text="detailed answers",
    )

    with pytest.raises(ValueError, match="exact substring"):
        await TrustedMemoryService(
            database=database,
            clock=lambda: NOW,
        ).handle_natural_memory_decision(
            natural_command(
                source_message_text="Please remember my preference.",
                decision=decision,
            )
        )

    assert database.calls == []


@pytest.mark.asyncio
async def test_natural_memory_service_rejects_raw_decision_before_effects() -> None:
    from trusted_memory_service import TrustedMemoryService

    database = FakeProposalDatabase()

    with pytest.raises(ValueError, match="canonical decision"):
        await TrustedMemoryService(
            database=database,
            clock=lambda: NOW,
        ).handle_natural_memory_decision(
            natural_command(decision={"kind": "no_memory"})
        )

    assert database.calls == []


@pytest.mark.asyncio
async def test_natural_memory_service_rejects_raw_selection_before_effects() -> None:
    from memory_candidate_decisions import NoMemoryDecision
    from trusted_memory_service import TrustedMemoryService

    database = FakeProposalDatabase()

    with pytest.raises(ValueError, match="canonical clarification selection"):
        await TrustedMemoryService(
            database=database,
            clock=lambda: NOW,
        ).handle_natural_memory_decision(
            natural_command(
                decision=NoMemoryDecision(),
                clarification_selection={"selected_candidate_index": 0},
            )
        )

    assert database.calls == []


@pytest.mark.asyncio
async def test_natural_clarification_selection_uses_server_owned_envelope(
) -> None:
    from memory_candidate_decisions import NoMemoryDecision
    from memory_clarifications import MemoryClarificationSelection
    from memory_proposals import ProposalTurnLease
    from trusted_memory_service import (
        NaturalMemoryProposalResult,
        TrustedMemoryService,
    )

    database = FakeProposalDatabase()
    result = await TrustedMemoryService(
        database=database,
        clock=lambda: NOW,
    ).handle_natural_memory_decision(
        natural_command(
            source_message_id="message-2",
            source_message_text="The development environments preference.",
            decision=NoMemoryDecision(),
            clarification_selection=MemoryClarificationSelection(
                selected_candidate_index=1,
            ),
            turn_lease=ProposalTurnLease(
                turn_id="b" * 64,
                owner_token="owner-2",
            ),
        )
    )

    assert isinstance(result, NaturalMemoryProposalResult)
    assert result.status == "pending"
    assert result.proposal.category == "development_environments"
    assert result.proposal.proposed_value == ["macos", "linux"]
    assert database.calls == [
        {
            "user_id": "user-1",
            "workspace_id": "workspace-1",
            "session_id": "session-1",
            "source_message_id": "message-2",
            "selection": MemoryClarificationSelection(
                selected_candidate_index=1,
            ),
            "observed_at": NOW,
            "turn_lease": ProposalTurnLease(
                turn_id="b" * 64,
                owner_token="owner-2",
            ),
        }
    ]


@pytest.mark.asyncio
async def test_explicit_clarification_selection_binds_public_id() -> None:
    from memory_clarifications import MemoryClarificationSelection
    from memory_proposals import ProposalTurnLease
    from trusted_memory_service import (
        NaturalMemoryProposalResult,
        SelectMemoryClarificationCommand,
        TrustedMemoryService,
    )

    database = FakeProposalDatabase()
    turn_lease = ProposalTurnLease(
        turn_id="b" * 64,
        owner_token="owner-2",
    )
    result = await TrustedMemoryService(
        database=database,
        clock=lambda: NOW,
    ).select_memory_clarification(
        SelectMemoryClarificationCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-1",
            source_message_id="message-2",
            clarification_id="memory-clarification--clarify-1",
            selected_candidate_index=1,
            turn_lease=turn_lease,
        )
    )

    assert isinstance(result, NaturalMemoryProposalResult)
    assert result.status == "pending"
    assert result.proposal.category == "development_environments"
    assert database.calls == [
        {
            "user_id": "user-1",
            "workspace_id": "workspace-1",
            "session_id": "session-1",
            "source_message_id": "message-2",
            "selection": MemoryClarificationSelection(
                selected_candidate_index=1,
            ),
            "expected_clarification_id": (
                "memory-clarification--clarify-1"
            ),
            "observed_at": NOW,
            "turn_lease": turn_lease,
        }
    ]


@pytest.mark.asyncio
async def test_explicit_clarification_selection_rejects_boolean_index(
) -> None:
    from memory_proposals import ProposalTurnLease
    from trusted_memory_service import (
        SelectMemoryClarificationCommand,
        TrustedMemoryService,
    )

    database = FakeProposalDatabase()

    with pytest.raises(ValueError, match="candidate index"):
        await TrustedMemoryService(
            database=database,
            clock=lambda: NOW,
        ).select_memory_clarification(
            SelectMemoryClarificationCommand(
                user_id="user-1",
                workspace_id="workspace-1",
                session_id="session-1",
                source_message_id="message-2",
                clarification_id="memory-clarification--clarify-1",
                selected_candidate_index=True,
                turn_lease=ProposalTurnLease(
                    turn_id="b" * 64,
                    owner_token="owner-2",
                ),
            )
        )

    assert database.calls == []


@pytest.mark.asyncio
async def test_natural_clarification_persists_with_observed_timestamp() -> None:
    from memory_candidate_decisions import (
        ClarifyDecision,
        ProfileCandidateDecision,
    )
    from memory_proposals import ProposalTurnLease
    from trusted_memory_service import (
        NaturalMemoryClarificationResult,
        TrustedMemoryService,
    )

    database = FakeProposalDatabase()
    turn_lease = ProposalTurnLease(
        turn_id="a" * 64,
        owner_token="owner-1",
    )
    result = await TrustedMemoryService(
        database=database,
        clock=lambda: NOW,
    ).handle_natural_memory_decision(
        natural_command(
            decision=ClarifyDecision(
                candidates=[
                    ProfileCandidateDecision(
                        category="preferred_name",
                        canonical_value="wifiknight",
                        evidence_text="wifiknight",
                    ),
                    ProfileCandidateDecision(
                        category="development_environments",
                        canonical_value=["macos", "linux"],
                        evidence_text="macOS and Linux",
                    ),
                ],
            ),
            source_message_text=(
                "Please remember wifiknight and macOS and Linux."
            ),
            turn_lease=turn_lease,
        )
    )

    assert isinstance(result, NaturalMemoryClarificationResult)
    assert database.calls[0]["observed_at"] == NOW
    assert database.calls[0]["turn_lease"] == turn_lease


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
