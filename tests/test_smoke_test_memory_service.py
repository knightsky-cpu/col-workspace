from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from database import MemoryRejectionResult
from schemas import CollaborationProfile
from smoke_test_memory_service import run_memory_service_smoke


NOW = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)


class FakeMemoryEngine:
    def __init__(self) -> None:
        self.operations: list[tuple[str, object]] = []

    async def create_memory_proposal(self, user_id, proposal, *, observed_at):
        self.operations.append(("create", proposal))
        return proposal

    async def reject_memory_proposal(
        self,
        user_id,
        category,
        proposal_id,
        *,
        observed_at,
    ):
        self.operations.append(("reject", proposal_id))
        proposal = self.operations[0][1].model_copy(
            update={"status": "rejected"}
        )
        return MemoryRejectionResult(
            profile=CollaborationProfile(),
            proposal=proposal,
        )

    async def get_collaboration_profile(self, user_id):
        self.operations.append(("load", user_id))
        return CollaborationProfile()

    def close(self) -> None:
        self.operations.append(("close", None))


@pytest.mark.asyncio
async def test_run_memory_service_smoke_rejects_and_retries_without_activation(
) -> None:
    engine = FakeMemoryEngine()

    result = await run_memory_service_smoke(
        engine_factory=lambda: engine,
        id_factory=lambda: SimpleNamespace(hex="fixed-id"),
        observed_at_factory=lambda: NOW,
    )

    assert result.user_id == "memory-m5-service-smoke-fixed-id"
    assert result.proposal_id == "response_length--fixed-id"
    assert result.rejection_revision == 0
    assert result.retry_revision == 0
    assert result.final_revision == 0
    assert [operation for operation, _ in engine.operations] == [
        "create",
        "reject",
        "reject",
        "load",
        "close",
    ]


@pytest.mark.asyncio
async def test_memory_service_smoke_summary_excludes_memory_content() -> None:
    result = await run_memory_service_smoke(
        engine_factory=FakeMemoryEngine,
        id_factory=lambda: SimpleNamespace(hex="fixed-id"),
        observed_at_factory=lambda: NOW,
    )

    summary = result.safe_summary()
    assert "trusted-memory-m5-1 pass" in summary
    assert "concise" not in summary
    assert "source-session" not in summary
    assert "source-message" not in summary
