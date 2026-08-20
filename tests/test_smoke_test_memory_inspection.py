from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from database import (
    MemoryApprovalResult,
    MemoryInspectionPage,
    MemoryRejectionResult,
)
from schemas import (
    ActiveMemorySignal,
    CollaborationProfile,
    MemoryEvent,
)


NOW = datetime(2026, 8, 20, 22, 0, tzinfo=UTC)


class FakeMemoryEngine:
    def __init__(self) -> None:
        self.proposals = {}
        self.profile = CollaborationProfile()
        self.events: list[MemoryEvent] = []
        self.operations: list[str] = []

    async def create_memory_proposal(
        self,
        user_id,
        proposal,
        *,
        observed_at,
    ):
        self.operations.append(f"create:{proposal.category}")
        self.proposals[proposal.category] = proposal
        return proposal

    async def approve_memory_proposal(
        self,
        user_id,
        category,
        proposal_id,
        **kwargs,
    ):
        self.operations.append(f"approve:{category}")
        proposal = self.proposals[category].model_copy(
            update={"status": "approved"}
        )
        self.proposals[category] = proposal
        event = MemoryEvent(
            event_id=f"{proposal_id}--approved",
            event_type="approved",
            signal_id=proposal_id,
            category=category,
            value=proposal.proposed_value,
            source_type="explicit_user_feedback",
            source_session_id=proposal.source_session_id,
            source_message_id=proposal.source_message_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            related_signal_id=None,
            memory_revision=1,
            created_at=NOW,
        )
        self.events.append(event)
        self.profile = CollaborationProfile(
            memory_revision=1,
            active_preferences={
                category: ActiveMemorySignal(
                    signal_id=proposal_id,
                    category=category,
                    value=proposal.proposed_value,
                    source_event_id=event.event_id,
                    approved_at=NOW,
                )
            },
        )
        return MemoryApprovalResult(profile=self.profile, event=event)

    async def reject_memory_proposal(
        self,
        user_id,
        category,
        proposal_id,
        *,
        observed_at,
    ):
        self.operations.append(f"reject:{category}")
        proposal = self.proposals[category].model_copy(
            update={"status": "rejected"}
        )
        self.proposals[category] = proposal
        return MemoryRejectionResult(
            profile=self.profile,
            proposal=proposal,
        )

    async def get_memory_inspection(
        self,
        user_id,
        *,
        observed_at,
        after_event_id,
    ):
        self.operations.append("inspect")
        unresolved = tuple(
            proposal
            for proposal in self.proposals.values()
            if proposal.status == "pending"
            and observed_at < proposal.expires_at
        )
        return MemoryInspectionPage(
            profile=self.profile,
            unresolved_proposals=unresolved,
            events=tuple(self.events),
            next_event_id=None,
        )

    def close(self) -> None:
        self.operations.append("close")


@pytest.mark.asyncio
async def test_memory_inspection_smoke_exposes_only_governed_state() -> None:
    from smoke_test_memory_inspection import run_memory_inspection_smoke

    engine = FakeMemoryEngine()

    result = await run_memory_inspection_smoke(
        engine_factory=lambda: engine,
        id_factory=lambda: SimpleNamespace(hex="fixed-id"),
        observed_at_factory=lambda: NOW,
    )

    assert result.user_id == "memory-m5-inspection-smoke-fixed-id"
    assert result.profile_revision == 1
    assert result.unresolved_count == 1
    assert result.event_count == 1
    assert result.next_event_id is None
    assert engine.operations == [
        "create:response_length",
        "approve:response_length",
        "create:example_usage",
        "create:formatting_style",
        "reject:formatting_style",
        "inspect",
        "close",
    ]
    summary = result.safe_summary()
    assert "trusted-memory-m5-2 pass" in summary
    assert "concise" not in summary
    assert "always_practical" not in summary
    assert "mixed" not in summary
    assert "source-message" not in summary
