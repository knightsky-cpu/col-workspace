import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
import warnings

from google.adk.sessions import State

from memory_proposal_tool import (
    PendingMemoryProposalToolResponse,
    create_propose_memory_signal_tool,
    parse_memory_proposal_tool_response,
)
from schemas import AgentActionReceipt, MemoryProposalReceipt
from trusted_memory_service import TrustedMemoryProposalResult


@dataclass(frozen=True)
class MemoryProposalToolSmokeResult:
    tool_name: str
    model_args: tuple[str, ...]
    receipt_count: int

    def safe_summary(self) -> str:
        model_args = ",".join(self.model_args)
        return (
            f"m7-mem-2 pass tool={self.tool_name} "
            f"model_args={model_args} receipt_count={self.receipt_count}"
        )


class OfflineMemoryService:
    async def propose_memory_signal(
        self,
        command: object,
    ) -> TrustedMemoryProposalResult:
        del command
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
                expires_at=datetime(2026, 8, 22, 17, 0, tzinfo=UTC),
            ),
        )


async def run_memory_proposal_tool_contract_smoke(
    *,
    memory_service: object | None = None,
) -> MemoryProposalToolSmokeResult:
    service = memory_service or OfflineMemoryService()
    tool = create_propose_memory_signal_tool(service)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"\[EXPERIMENTAL\].*JSON_SCHEMA_FOR_FUNC_DECL.*",
            category=UserWarning,
        )
        declaration = tool._get_declaration()
    if declaration is None or declaration.parameters_json_schema is None:
        raise RuntimeError("Memory proposal tool declaration is missing.")
    properties = declaration.parameters_json_schema.get("properties")
    if not isinstance(properties, dict):
        raise RuntimeError("Memory proposal tool declaration is invalid.")
    model_args = tuple(sorted(properties))
    response = await tool.run_async(
        args={
            "category": "response_length",
            "proposed_value": "concise",
        },
        tool_context=SimpleNamespace(
            state=State(
                value={
                    "memory_user_id": "user-1",
                    "memory_session_id": "session-1",
                    "memory_source_message_id": "message-1",
                    "memory_source_message_text": (
                        "I prefer concise responses."
                    ),
                    "memory_decision_present": False,
                },
                delta={},
            )
        ),
    )
    parsed = parse_memory_proposal_tool_response(response)
    if not isinstance(parsed, PendingMemoryProposalToolResponse):
        raise RuntimeError("Memory proposal tool did not return a receipt.")
    return MemoryProposalToolSmokeResult(
        tool_name=tool.name,
        model_args=model_args,
        receipt_count=1,
    )


def main() -> None:
    result = asyncio.run(run_memory_proposal_tool_contract_smoke())
    print(result.safe_summary())


if __name__ == "__main__":
    main()
