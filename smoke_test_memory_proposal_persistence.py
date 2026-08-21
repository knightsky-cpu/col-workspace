import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from database import MemoryEngine
from memory_proposals import derive_proposal_origin_ids
from trusted_memory_service import (
    ProposeMemorySignalCommand,
    TrustedMemoryService,
)


@dataclass(frozen=True, slots=True)
class ProposalPersistenceSmokeResult:
    """Hold structural evidence from the M7-MEM.1 persistence check."""

    user_id: str
    category: str
    origin_id: str
    proposal_id: str
    first_expires_at: datetime
    retry_expires_at: datetime

    def safe_summary(self) -> str:
        """Render Firestore locators without preference or source content."""
        expiry_preserved = self.first_expires_at == self.retry_expires_at
        return (
            "trusted-memory-m7-mem-1 pass "
            f"user_id={self.user_id} "
            f"category={self.category} "
            f"origin_id={self.origin_id} "
            f"proposal_id={self.proposal_id} "
            f"expiry_preserved={str(expiry_preserved).lower()} "
            f"expires_at={self.first_expires_at.isoformat()}"
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def run_proposal_persistence_smoke(
    *,
    engine_factory: Callable[[], MemoryEngine] = MemoryEngine,
    id_factory: Callable[[], UUID] = uuid4,
    observed_at_factory: Callable[[], datetime] = _utc_now,
) -> ProposalPersistenceSmokeResult:
    """Create and identically retry one governed-memory proposal."""
    suffix = id_factory().hex
    user_id = f"memory-m7-proposal-smoke-{suffix}"
    session_id = f"memory-m7-proposal-session-{suffix}"
    source_message_id = f"memory-m7-proposal-message-{suffix}"
    category = "response_length"
    command = ProposeMemorySignalCommand(
        user_id=user_id,
        session_id=session_id,
        source_message_id=source_message_id,
        source_message_text="I prefer concise responses.",
        memory_decision_present=False,
        category=category,
        proposed_value="concise",
    )
    ids = derive_proposal_origin_ids(
        user_id,
        session_id,
        source_message_id,
        category,
    )
    engine = engine_factory()
    service = TrustedMemoryService(
        database=engine,
        clock=observed_at_factory,
    )
    try:
        first = await service.propose_memory_signal(command)
        retry = await service.propose_memory_signal(command)
        if first.action != retry.action:
            raise RuntimeError("Proposal retry action check failed.")
        if first.proposal.proposal_id != ids.proposal_id:
            raise RuntimeError("Proposal identifier check failed.")
        if retry.proposal.proposal_id != first.proposal.proposal_id:
            raise RuntimeError("Proposal retry identifier check failed.")
        if retry.proposal.expires_at != first.proposal.expires_at:
            raise RuntimeError("Proposal retry expiry check failed.")
        return ProposalPersistenceSmokeResult(
            user_id=user_id,
            category=category,
            origin_id=ids.origin_id,
            proposal_id=ids.proposal_id,
            first_expires_at=first.proposal.expires_at,
            retry_expires_at=retry.proposal.expires_at,
        )
    finally:
        engine.close()


def main() -> None:
    """Run the live M7-MEM.1 check and print copy-safe evidence."""
    result = asyncio.run(run_proposal_persistence_smoke())
    print(result.safe_summary())


if __name__ == "__main__":
    main()
