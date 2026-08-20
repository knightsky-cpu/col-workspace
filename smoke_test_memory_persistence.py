import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from database import MemoryEngine
from schemas import MemoryProposal


async def exercise_memory_proposal(
    engine: MemoryEngine,
    *,
    user_id: str,
    proposal_id: str,
    observed_at: datetime,
) -> MemoryProposal:
    """Create one pending proposal and prove an identical retry is stable."""
    candidate = MemoryProposal(
        proposal_id=proposal_id,
        category="response_length",
        proposed_value="concise",
        expected_signal_id=None,
        status="pending",
        source_session_id="memory-m2-smoke-session",
        source_message_id="memory-m2-smoke-message",
        created_at=observed_at,
        expires_at=observed_at + timedelta(hours=24),
    )

    first = await engine.create_memory_proposal(
        user_id,
        candidate,
        observed_at=observed_at,
    )
    second = await engine.create_memory_proposal(
        user_id,
        candidate,
        observed_at=observed_at,
    )
    if (
        first.proposal_id != candidate.proposal_id
        or second.proposal_id != candidate.proposal_id
    ):
        raise RuntimeError("Memory proposal idempotency check failed.")
    return second


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def run_memory_persistence_smoke(
    *,
    engine_factory: Callable[[], MemoryEngine] = MemoryEngine,
    id_factory: Callable[[], UUID] = uuid4,
    observed_at_factory: Callable[[], datetime] = _utc_now,
) -> str:
    """Run one live proposal write and return its inspection locator."""
    suffix = id_factory().hex
    user_id = f"memory-m2-smoke-{suffix}"
    proposal_id = f"response_length--{suffix}"
    observed_at = observed_at_factory()
    engine = engine_factory()
    try:
        await exercise_memory_proposal(
            engine,
            user_id=user_id,
            proposal_id=proposal_id,
            observed_at=observed_at,
        )
    finally:
        engine.close()
    return (
        f"trusted-memory-m2 pass user_id={user_id} "
        "category=response_length"
    )


def main() -> None:
    """Run the live smoke check and print its Firestore locator."""
    print(asyncio.run(run_memory_persistence_smoke()))


if __name__ == "__main__":
    main()
