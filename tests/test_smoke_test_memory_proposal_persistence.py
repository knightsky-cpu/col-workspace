from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from schemas import MemoryProposal


NOW = datetime(2026, 8, 21, 16, 0, tzinfo=UTC)


class FakeMemoryEngine:
    def __init__(self) -> None:
        self.operations: list[dict[str, object]] = []
        self.stored: MemoryProposal | None = None
        self.closed = False

    async def create_guarded_memory_proposal(self, **kwargs):
        self.operations.append(kwargs)
        if self.stored is None:
            self.stored = MemoryProposal(
                proposal_id=kwargs["origin_ids"].proposal_id,
                category=kwargs["category"],
                proposed_value=kwargs["proposed_value"],
                expected_signal_id=None,
                status="pending",
                source_session_id=kwargs["session_id"],
                source_message_id=kwargs["source_message_id"],
                created_at=kwargs["observed_at"],
                expires_at=kwargs["observed_at"] + timedelta(hours=24),
            )
        return self.stored

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_proposal_persistence_smoke_creates_and_retries_same_command(
) -> None:
    from smoke_test_memory_proposal_persistence import (
        run_proposal_persistence_smoke,
    )

    engine = FakeMemoryEngine()
    times = iter((NOW, NOW + timedelta(hours=1)))

    result = await run_proposal_persistence_smoke(
        engine_factory=lambda: engine,
        id_factory=lambda: SimpleNamespace(hex="fixed-id"),
        observed_at_factory=lambda: next(times),
    )

    assert len(engine.operations) == 2
    first, retry = engine.operations
    assert first["origin_ids"] == retry["origin_ids"]
    assert first["source_message_id"] == retry["source_message_id"]
    assert first["proposed_value"] == retry["proposed_value"] == "concise"
    assert result.first_expires_at == NOW + timedelta(hours=24)
    assert result.retry_expires_at == result.first_expires_at
    assert engine.closed is True


@pytest.mark.asyncio
async def test_proposal_persistence_smoke_summary_excludes_memory_content(
) -> None:
    from smoke_test_memory_proposal_persistence import (
        run_proposal_persistence_smoke,
    )

    engine = FakeMemoryEngine()
    result = await run_proposal_persistence_smoke(
        engine_factory=lambda: engine,
        id_factory=lambda: SimpleNamespace(hex="fixed-id"),
        observed_at_factory=lambda: NOW,
    )

    summary = result.safe_summary()
    assert "trusted-memory-m7-mem-1 pass" in summary
    assert "concise" not in summary
    assert "I prefer concise responses" not in summary
    assert result.origin_id in summary
    assert result.proposal_id in summary
