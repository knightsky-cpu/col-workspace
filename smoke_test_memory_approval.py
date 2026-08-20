import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from database import MemoryEngine
from memory_policy import MemoryValue
from schemas import MemoryProposal


@dataclass(frozen=True, slots=True)
class MemoryApprovalSmokeResult:
    """Hold verified lifecycle evidence from the M3 live smoke run."""

    user_id: str
    initial_revision: int
    retry_revision: int
    correction_revision: int
    approved_event_id: str
    corrected_event_id: str
    superseded_event_id: str
    final_signal_id: str
    final_active_value: MemoryValue

    def safe_summary(self) -> str:
        """Render structural evidence without memory values or message text."""
        return (
            "trusted-memory-m3 pass "
            f"user_id={self.user_id} "
            "category=response_length "
            f"initial_revision={self.initial_revision} "
            f"retry_revision={self.retry_revision} "
            f"correction_revision={self.correction_revision} "
            f"approved_event={self.approved_event_id} "
            f"corrected_event={self.corrected_event_id} "
            f"superseded_event={self.superseded_event_id} "
            f"final_signal={self.final_signal_id}"
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def run_memory_approval_smoke(
    *,
    engine_factory: Callable[[], MemoryEngine] = MemoryEngine,
    id_factory: Callable[[], UUID] = uuid4,
    observed_at_factory: Callable[[], datetime] = _utc_now,
) -> MemoryApprovalSmokeResult:
    """Exercise initial approval, retry, correction, and typed profile load."""
    suffix = id_factory().hex
    observed_at = observed_at_factory()
    user_id = f"memory-m3-smoke-{suffix}"
    initial_signal_id = f"response_length--{suffix}-initial"
    corrected_signal_id = f"response_length--{suffix}-correction"
    initial_proposal = MemoryProposal(
        proposal_id=initial_signal_id,
        category="response_length",
        proposed_value="concise",
        expected_signal_id=None,
        status="pending",
        source_session_id=f"memory-m3-source-session-{suffix}",
        source_message_id=f"memory-m3-source-message-{suffix}",
        created_at=observed_at,
        expires_at=observed_at + timedelta(hours=24),
    )
    correction_proposal = MemoryProposal(
        proposal_id=corrected_signal_id,
        category="response_length",
        proposed_value="detailed",
        expected_signal_id=initial_signal_id,
        status="pending",
        source_session_id=f"memory-m3-correction-session-{suffix}",
        source_message_id=f"memory-m3-correction-message-{suffix}",
        created_at=observed_at,
        expires_at=observed_at + timedelta(hours=24),
    )
    engine = engine_factory()
    try:
        await engine.create_memory_proposal(
            user_id,
            initial_proposal,
            observed_at=observed_at,
        )
        initial = await engine.approve_memory_proposal(
            user_id,
            "response_length",
            initial_signal_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=observed_at,
        )
        retry = await engine.approve_memory_proposal(
            user_id,
            "response_length",
            initial_signal_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=observed_at,
        )
        await engine.create_memory_proposal(
            user_id,
            correction_proposal,
            observed_at=observed_at,
        )
        correction = await engine.approve_memory_proposal(
            user_id,
            "response_length",
            corrected_signal_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=observed_at,
        )
        final_profile = await engine.get_collaboration_profile(user_id)

        if initial.profile.memory_revision != 1:
            raise RuntimeError("Initial memory revision check failed.")
        if (
            retry.profile.memory_revision != 1
            or retry.event.event_id != initial.event.event_id
        ):
            raise RuntimeError("Memory approval retry check failed.")
        if (
            correction.profile.memory_revision != 2
            or correction.event.event_type != "corrected"
            or correction.superseded_event is None
        ):
            raise RuntimeError("Memory correction check failed.")
        active_signal = final_profile.active_preferences.get(
            "response_length"
        )
        if (
            final_profile.memory_revision != 2
            or active_signal is None
            or active_signal.signal_id != corrected_signal_id
            or active_signal.source_event_id != correction.event.event_id
        ):
            raise RuntimeError("Final collaboration profile check failed.")

        return MemoryApprovalSmokeResult(
            user_id=user_id,
            initial_revision=initial.profile.memory_revision,
            retry_revision=retry.profile.memory_revision,
            correction_revision=correction.profile.memory_revision,
            approved_event_id=initial.event.event_id,
            corrected_event_id=correction.event.event_id,
            superseded_event_id=correction.superseded_event.event_id,
            final_signal_id=active_signal.signal_id,
            final_active_value=active_signal.value,
        )
    finally:
        engine.close()


def main() -> None:
    """Run the live M3 smoke check and print copy-safe structural evidence."""
    result = asyncio.run(run_memory_approval_smoke())
    print(result.safe_summary())


if __name__ == "__main__":
    main()
