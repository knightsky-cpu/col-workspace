import _repo_path
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from database import MemoryEngine
from schemas import MemoryProposal
from trusted_memory_service import (
    MemoryDecisionCommand,
    TrustedMemoryService,
)


@dataclass(frozen=True, slots=True)
class MemoryServiceSmokeResult:
    """Hold structural evidence from the M5.1 live rejection check."""

    user_id: str
    proposal_id: str
    rejection_revision: int
    retry_revision: int
    final_revision: int

    def safe_summary(self) -> str:
        """Render Firestore locators and revisions without memory content."""
        return (
            "trusted-memory-m5-1 pass "
            f"user_id={self.user_id} "
            "category=response_length "
            f"proposal_id={self.proposal_id} "
            f"rejection_revision={self.rejection_revision} "
            f"retry_revision={self.retry_revision} "
            f"final_revision={self.final_revision}"
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def run_memory_service_smoke(
    *,
    engine_factory: Callable[[], MemoryEngine] = MemoryEngine,
    id_factory: Callable[[], UUID] = uuid4,
    observed_at_factory: Callable[[], datetime] = _utc_now,
) -> MemoryServiceSmokeResult:
    """Create and reject one proposal through the service, then retry."""
    suffix = id_factory().hex
    observed_at = observed_at_factory()
    user_id = f"memory-m5-service-smoke-{suffix}"
    proposal_id = f"response_length--{suffix}"
    proposal = MemoryProposal(
        proposal_id=proposal_id,
        category="response_length",
        proposed_value="concise",
        expected_signal_id=None,
        status="pending",
        source_session_id=f"memory-m5-source-session-{suffix}",
        source_message_id=f"memory-m5-source-message-{suffix}",
        created_at=observed_at,
        expires_at=observed_at + timedelta(hours=24),
    )
    engine = engine_factory()
    service = TrustedMemoryService(
        database=engine,
        clock=lambda: observed_at,
    )
    command = MemoryDecisionCommand(
        user_id=user_id,
        proposal_id=proposal_id,
        decision="reject",
        confirmation_channel="memory_api",
        confirmation_session_id=None,
        confirmation_message_id=None,
    )
    try:
        await engine.create_memory_proposal(
            user_id,
            proposal,
            observed_at=observed_at,
        )
        rejection = await service.decide_memory_proposal(command)
        retry = await service.decide_memory_proposal(command)
        final_profile = await engine.get_collaboration_profile(user_id)

        if rejection.action.action_name != "reject_memory_signal":
            raise RuntimeError("Memory rejection action check failed.")
        if retry.action != rejection.action:
            raise RuntimeError("Memory rejection retry action check failed.")
        if (
            rejection.profile.memory_revision != 0
            or retry.profile.memory_revision != 0
            or final_profile.memory_revision != 0
        ):
            raise RuntimeError("Memory rejection revision check failed.")
        if (
            final_profile.identity_context
            or final_profile.active_preferences
        ):
            raise RuntimeError("Rejected memory became active.")

        return MemoryServiceSmokeResult(
            user_id=user_id,
            proposal_id=proposal_id,
            rejection_revision=rejection.profile.memory_revision,
            retry_revision=retry.profile.memory_revision,
            final_revision=final_profile.memory_revision,
        )
    finally:
        engine.close()


def main() -> None:
    """Run the live M5.1 smoke check and print copy-safe evidence."""
    result = asyncio.run(run_memory_service_smoke())
    print(result.safe_summary())


if __name__ == "__main__":
    main()
