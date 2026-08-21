from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from database import MemoryEngineError
from memory_routing_evaluation import (
    MemoryRoutingScenario,
    StatefulRoutingSetup,
)
from schemas import (
    ActiveMemorySignal,
    AgentActionReceipt,
    CollaborationProfile,
    MemoryProposalReceipt,
)
from trusted_memory_service import (
    TrustedMemoryMutationResult,
    TrustedMemoryProposalResult,
)


PROPOSAL_ID = "response_length--1234567890abcdef1234567890abcdef"


def make_stateful_scenario(
    *,
    precondition: str,
    target_decision: str,
) -> MemoryRoutingScenario:
    return MemoryRoutingScenario(
        scenario_id="stateful-case",
        fixture_version="1.0",
        message="Please remember that I prefer concise responses.",
        expected_routing="no_proposal",
        expected_proposal=None,
        manual_semantic_review="none",
        execution_mode="stateful",
        state_precondition=precondition,
        state_setup=StatefulRoutingSetup(
            category="response_length",
            proposed_value="concise",
            proposal_source_message=(
                "Please remember that I prefer concise responses."
            ),
            target_decision=target_decision,
        ),
    )


@dataclass
class RecordingDatabase:
    saved_messages: list[tuple[str, str, str]] = field(default_factory=list)
    closed: bool = False

    async def save_message(
        self,
        session_id: str,
        role: str,
        text: str,
    ) -> str:
        self.saved_messages.append((session_id, role, text))
        return "setup-source-message"

    def close(self) -> None:
        self.closed = True


@dataclass
class RecordingMemoryService:
    proposal_commands: list[object] = field(default_factory=list)
    decision_commands: list[object] = field(default_factory=list)

    async def propose_memory_signal(
        self,
        command: object,
    ) -> TrustedMemoryProposalResult:
        self.proposal_commands.append(command)
        return TrustedMemoryProposalResult(
            action=AgentActionReceipt(
                action_name="propose_memory_signal",
                status="completed",
            ),
            proposal=MemoryProposalReceipt(
                proposal_id=PROPOSAL_ID,
                category="response_length",
                proposed_value="concise",
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            ),
        )

    async def decide_memory_proposal(
        self,
        command: object,
    ) -> TrustedMemoryMutationResult:
        self.decision_commands.append(command)
        signal = ActiveMemorySignal(
            signal_id=PROPOSAL_ID,
            category="response_length",
            value="concise",
            source_event_id=f"{PROPOSAL_ID}--approved",
            approved_at=datetime.now(UTC),
        )
        return TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="approve_memory_signal",
                status="completed",
            ),
            profile=CollaborationProfile(
                memory_revision=1,
                active_preferences={"response_length": signal},
            ),
        )


@pytest.mark.asyncio
async def test_state_manager_establishes_active_identical_preference() -> None:
    from memory_routing_state import MemoryRoutingStateManager

    database = RecordingDatabase()
    service = RecordingMemoryService()
    manager = MemoryRoutingStateManager(
        database=database,
        memory_service=service,
    )

    decision = await manager.prepare(
        make_stateful_scenario(
            precondition="active_identical_preference",
            target_decision="none",
        ),
        user_id="stateful-user",
        session_id="stateful-session",
    )

    assert decision is None
    assert database.saved_messages == [
        (
            "stateful-session-setup",
            "user",
            "Please remember that I prefer concise responses.",
        )
    ]
    assert len(service.proposal_commands) == 1
    proposal_command = service.proposal_commands[0]
    assert proposal_command.user_id == "stateful-user"
    assert proposal_command.session_id == "stateful-session-setup"
    assert proposal_command.source_message_id == "setup-source-message"
    assert proposal_command.memory_decision_present is False
    assert proposal_command.category == "response_length"
    assert proposal_command.proposed_value == "concise"
    assert len(service.decision_commands) == 1
    approval = service.decision_commands[0]
    assert approval.proposal_id == PROPOSAL_ID
    assert approval.decision == "approve"
    assert approval.confirmation_channel == "memory_api"
    assert approval.confirmation_session_id is None
    assert approval.confirmation_message_id is None


@pytest.mark.asyncio
async def test_state_manager_returns_pending_structured_decision() -> None:
    from memory_routing_state import MemoryRoutingStateManager

    database = RecordingDatabase()
    service = RecordingMemoryService()
    manager = MemoryRoutingStateManager(
        database=database,
        memory_service=service,
    )

    decision = await manager.prepare(
        make_stateful_scenario(
            precondition="structured_memory_decision",
            target_decision="approve",
        ),
        user_id="stateful-user",
        session_id="stateful-session",
    )

    assert decision is not None
    assert decision.proposal_id == PROPOSAL_ID
    assert decision.decision == "approve"
    assert service.decision_commands == []


@pytest.mark.asyncio
async def test_state_manager_translates_database_failure_without_content(
) -> None:
    from memory_routing_state import (
        MemoryRoutingStateError,
        MemoryRoutingStateManager,
    )

    private_detail = "private-firestore-detail"

    class FailingDatabase(RecordingDatabase):
        async def save_message(
            self,
            session_id: str,
            role: str,
            text: str,
        ) -> str:
            raise MemoryEngineError(private_detail)

    manager = MemoryRoutingStateManager(
        database=FailingDatabase(),
        memory_service=RecordingMemoryService(),
    )

    with pytest.raises(MemoryRoutingStateError) as exc_info:
        await manager.prepare(
            make_stateful_scenario(
                precondition="structured_memory_decision",
                target_decision="approve",
            ),
            user_id="stateful-user",
            session_id="stateful-session",
        )

    assert private_detail not in str(exc_info.value)


def test_state_manager_closes_owned_database() -> None:
    from memory_routing_state import MemoryRoutingStateManager

    database = RecordingDatabase()
    manager = MemoryRoutingStateManager(
        database=database,
        memory_service=RecordingMemoryService(),
    )

    manager.close()

    assert database.closed is True
