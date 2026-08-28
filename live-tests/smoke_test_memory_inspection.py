import _repo_path
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from database import MemoryEngine
from memory_policy import MemoryCategory, MemoryValue
from schemas import MemoryProposal
from trusted_memory_service import (
    InspectMemoryCommand,
    MemoryDecisionCommand,
    TrustedMemoryService,
)


@dataclass(frozen=True, slots=True)
class MemoryInspectionSmokeResult:
    """Hold content-free evidence from the M5.2 live inspection check."""

    user_id: str
    profile_revision: int
    unresolved_count: int
    event_count: int
    next_event_id: str | None

    def safe_summary(self) -> str:
        """Render structural evidence without stored memory values."""
        cursor = self.next_event_id or "none"
        return (
            "trusted-memory-m5-2 pass "
            f"user_id={self.user_id} "
            f"profile_revision={self.profile_revision} "
            f"unresolved={self.unresolved_count} "
            f"events={self.event_count} "
            f"next_event_id={cursor}"
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _proposal(
    *,
    suffix: str,
    category: MemoryCategory,
    value: MemoryValue,
    observed_at: datetime,
) -> MemoryProposal:
    return MemoryProposal(
        proposal_id=f"{category}--{suffix}",
        category=category,
        proposed_value=value,
        expected_signal_id=None,
        status="pending",
        source_session_id=f"memory-m5-inspection-session-{suffix}",
        source_message_id=f"memory-m5-inspection-message-{suffix}",
        created_at=observed_at,
        expires_at=observed_at + timedelta(hours=24),
    )


async def run_memory_inspection_smoke(
    *,
    engine_factory: Callable[[], MemoryEngine] = MemoryEngine,
    id_factory: Callable[[], UUID] = uuid4,
    observed_at_factory: Callable[[], datetime] = _utc_now,
) -> MemoryInspectionSmokeResult:
    """Create governed states and verify one bounded inspection page."""
    suffix = id_factory().hex
    observed_at = observed_at_factory()
    user_id = f"memory-m5-inspection-smoke-{suffix}"
    approved = _proposal(
        suffix=suffix,
        category="response_length",
        value="concise",
        observed_at=observed_at,
    )
    unresolved = _proposal(
        suffix=suffix,
        category="example_usage",
        value="always_practical",
        observed_at=observed_at,
    )
    rejected = _proposal(
        suffix=suffix,
        category="formatting_style",
        value="mixed",
        observed_at=observed_at,
    )
    engine = engine_factory()
    service = TrustedMemoryService(
        database=engine,
        clock=lambda: observed_at,
    )
    try:
        await engine.create_memory_proposal(
            user_id,
            approved,
            observed_at=observed_at,
        )
        await service.decide_memory_proposal(
            MemoryDecisionCommand(
                user_id=user_id,
                proposal_id=approved.proposal_id,
                decision="approve",
                confirmation_channel="memory_api",
                confirmation_session_id=None,
                confirmation_message_id=None,
            )
        )
        await engine.create_memory_proposal(
            user_id,
            unresolved,
            observed_at=observed_at,
        )
        await engine.create_memory_proposal(
            user_id,
            rejected,
            observed_at=observed_at,
        )
        await service.decide_memory_proposal(
            MemoryDecisionCommand(
                user_id=user_id,
                proposal_id=rejected.proposal_id,
                decision="reject",
                confirmation_channel="memory_api",
                confirmation_session_id=None,
                confirmation_message_id=None,
            )
        )
        inspection = await service.inspect_memory(
            InspectMemoryCommand(user_id=user_id)
        )

        active = inspection.profile.active_preferences.get(
            "response_length"
        )
        if (
            inspection.profile.memory_revision != 1
            or active is None
            or active.signal_id != approved.proposal_id
        ):
            raise RuntimeError("Memory inspection profile check failed.")
        if tuple(
            proposal.proposal_id
            for proposal in inspection.unresolved_proposals
        ) != (unresolved.proposal_id,):
            raise RuntimeError("Unresolved proposal filter check failed.")
        if (
            len(inspection.events) != 1
            or inspection.events[0].event_type != "approved"
            or inspection.events[0].signal_id != approved.proposal_id
        ):
            raise RuntimeError("Memory inspection event check failed.")
        if inspection.next_event_id is not None:
            raise RuntimeError("Memory inspection cursor check failed.")

        return MemoryInspectionSmokeResult(
            user_id=user_id,
            profile_revision=inspection.profile.memory_revision,
            unresolved_count=len(inspection.unresolved_proposals),
            event_count=len(inspection.events),
            next_event_id=inspection.next_event_id,
        )
    finally:
        engine.close()


def main() -> None:
    """Run the M5.2 live Firestore smoke check."""
    result = asyncio.run(run_memory_inspection_smoke())
    print(result.safe_summary())


if __name__ == "__main__":
    main()
