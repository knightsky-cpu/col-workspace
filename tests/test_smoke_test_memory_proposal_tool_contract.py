from datetime import UTC, datetime

import pytest

from schemas import AgentActionReceipt, MemoryProposalReceipt
from trusted_memory_service import TrustedMemoryProposalResult


NOW = datetime(2026, 8, 22, 17, 0, tzinfo=UTC)


class FakeMemoryService:
    def __init__(self) -> None:
        self.commands: list[object] = []

    async def propose_memory_signal(self, command):
        self.commands.append(command)
        return TrustedMemoryProposalResult(
            action=AgentActionReceipt(
                action_name="propose_memory_signal",
                status="completed",
            ),
            proposal=MemoryProposalReceipt(
                proposal_id=(
                    "response_length--e82366f7699ee2e39bff6a68154e09b7"
                ),
                category="response_length",
                proposed_value="concise",
                expires_at=NOW,
            ),
        )


@pytest.mark.asyncio
async def test_tool_contract_smoke_runs_real_declaration_and_adapter() -> None:
    from smoke_test_memory_proposal_tool_contract import (
        run_memory_proposal_tool_contract_smoke,
    )

    service = FakeMemoryService()
    result = await run_memory_proposal_tool_contract_smoke(
        memory_service=service
    )

    assert result.tool_name == "propose_memory_signal"
    assert result.model_args == ("category", "proposed_value")
    assert result.receipt_count == 1
    assert len(service.commands) == 1


@pytest.mark.asyncio
async def test_tool_contract_smoke_summary_excludes_private_context() -> None:
    from smoke_test_memory_proposal_tool_contract import (
        run_memory_proposal_tool_contract_smoke,
    )

    result = await run_memory_proposal_tool_contract_smoke(
        memory_service=FakeMemoryService()
    )

    summary = result.safe_summary()
    assert summary == (
        "m7-mem-2 pass tool=propose_memory_signal "
        "model_args=category,proposed_value receipt_count=1"
    )
    for private_value in (
        "concise",
        "I prefer",
        "user-1",
        "session-1",
        "message-1",
        "e82366f7699ee2e39bff6a68154e09b7",
    ):
        assert private_value not in summary
