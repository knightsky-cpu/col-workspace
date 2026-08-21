from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from google.adk.sessions import State
from google.adk.tools import FunctionTool

from schemas import AgentActionReceipt, MemoryProposalReceipt
from trusted_memory_service import TrustedMemoryProposalResult


NOW = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)


class NoopMemoryService:
    async def propose_memory_signal(self, command):
        raise AssertionError("declaration inspection must not call service")


class RecordingMemoryService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.commands: list[object] = []

    async def propose_memory_signal(self, command):
        self.commands.append(command)
        if self.error is not None:
            raise self.error
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


def tool_context_state() -> dict[str, object]:
    return {
        "memory_user_id": "user-1",
        "memory_session_id": "session-1",
        "memory_source_message_id": "message-1",
        "memory_source_message_text": "I prefer concise responses.",
        "memory_decision_present": False,
        "memory_turn_id": "a" * 64,
        "memory_turn_owner_token": "owner-1",
    }


@pytest.mark.filterwarnings(
    "ignore:\\[EXPERIMENTAL\\].*JSON_SCHEMA_FOR_FUNC_DECL.*:UserWarning"
)
def test_proposal_tool_exposes_only_candidate_fields_to_model() -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    tool = create_propose_memory_signal_tool(NoopMemoryService())
    declaration = tool._get_declaration()

    assert isinstance(tool, FunctionTool)
    assert tool.name == "propose_memory_signal"
    assert declaration is not None
    schema = declaration.parameters_json_schema
    assert schema is not None
    assert set(schema["properties"]) == {"category", "proposed_value"}
    assert schema["required"] == ["category", "proposed_value"]
    rendered = declaration.model_dump_json(exclude_none=True)
    for server_owned_name in (
        "user_id",
        "session_id",
        "source_message_id",
        "source_message_text",
        "memory_decision_present",
        "turn_id",
        "owner_token",
        "tool_context",
    ):
        assert server_owned_name not in rendered


@pytest.mark.asyncio
async def test_proposal_tool_builds_pending_result_from_adk_state() -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    service = RecordingMemoryService()
    tool = create_propose_memory_signal_tool(service)

    result = await tool.run_async(
        args={
            "category": "response_length",
            "proposed_value": "concise",
        },
        tool_context=SimpleNamespace(
            state=State(value=tool_context_state(), delta={})
        ),
    )

    assert result == {
        "status": "pending",
        "action": {
            "action_name": "propose_memory_signal",
            "status": "completed",
        },
        "memory_proposal": {
            "proposal_id": (
                "response_length--e82366f7699ee2e39bff6a68154e09b7"
            ),
            "category": "response_length",
            "proposed_value": "concise",
            "expires_at": "2026-08-22T16:00:00Z",
        },
    }
    command = service.commands[0]
    assert command.user_id == "user-1"
    assert command.session_id == "session-1"
    assert command.source_message_id == "message-1"
    assert command.source_message_text == "I prefer concise responses."
    assert command.memory_decision_present is False
    assert command.category == "response_length"
    assert command.proposed_value == "concise"
    assert command.turn_lease.turn_id == "a" * 64
    assert command.turn_lease.owner_token == "owner-1"


@pytest.mark.asyncio
async def test_proposal_tool_rejects_invalid_candidate_without_receipt() -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    service = RecordingMemoryService(error=ValueError("private candidate"))
    tool = create_propose_memory_signal_tool(service)

    result = await tool.run_async(
        args={
            "category": "response_length",
            "proposed_value": "invalid-private-value",
        },
        tool_context=SimpleNamespace(state=tool_context_state()),
    )

    assert result == {
        "status": "rejected",
        "error_code": "invalid_memory_candidate",
    }
    assert "private" not in str(result)


@pytest.mark.parametrize(
    "invalid_state",
    (
        {"memory_source_message_id": None},
        {"memory_turn_owner_token": None},
    ),
)
@pytest.mark.asyncio
async def test_proposal_tool_rejects_incomplete_server_context_safely(
    invalid_state: dict[str, object],
) -> None:
    from memory_proposal_tool import (
        MemoryProposalToolConfigurationError,
        create_propose_memory_signal_tool,
    )

    state = tool_context_state()
    state.update(invalid_state)
    service = RecordingMemoryService()
    tool = create_propose_memory_signal_tool(service)

    with pytest.raises(MemoryProposalToolConfigurationError) as caught:
        await tool.run_async(
            args={
                "category": "response_length",
                "proposed_value": "concise",
            },
            tool_context=SimpleNamespace(state=state),
        )

    assert str(caught.value) == "Memory proposal tool context is invalid."
    assert service.commands == []
    assert "message" not in str(caught.value).lower()


def test_proposal_tool_response_parser_accepts_strict_envelopes() -> None:
    from memory_proposal_tool import (
        PendingMemoryProposalToolResponse,
        RejectedMemoryProposalToolResponse,
        parse_memory_proposal_tool_response,
    )

    pending = parse_memory_proposal_tool_response(
        {
            "status": "pending",
            "action": {
                "action_name": "propose_memory_signal",
                "status": "completed",
            },
            "memory_proposal": {
                "proposal_id": (
                    "response_length--e82366f7699ee2e39bff6a68154e09b7"
                ),
                "category": "response_length",
                "proposed_value": "concise",
                "expires_at": "2026-08-22T16:00:00Z",
            },
        }
    )
    rejected = parse_memory_proposal_tool_response(
        {
            "status": "rejected",
            "error_code": "invalid_memory_candidate",
        }
    )

    assert isinstance(pending, PendingMemoryProposalToolResponse)
    assert pending.action.action_name == "propose_memory_signal"
    assert isinstance(rejected, RejectedMemoryProposalToolResponse)


@pytest.mark.parametrize(
    "invalid_response",
    (
        {
            "status": "rejected",
            "error_code": "invalid_memory_candidate",
            "private_detail": "must-not-survive",
        },
        {
            "status": "pending",
            "action": {
                "action_name": "google_search",
                "status": "completed",
            },
            "memory_proposal": {
                "proposal_id": "response_length--invalid",
                "category": "response_length",
                "proposed_value": "concise",
                "expires_at": "2026-08-22T16:00:00Z",
            },
        },
        {"status": "unknown"},
        "private-response",
    ),
)
def test_proposal_tool_response_parser_rejects_malformed_content_safely(
    invalid_response: object,
) -> None:
    from memory_proposal_tool import (
        MemoryProposalToolResponseError,
        parse_memory_proposal_tool_response,
    )

    with pytest.raises(MemoryProposalToolResponseError) as caught:
        parse_memory_proposal_tool_response(invalid_response)

    assert str(caught.value) == "Memory proposal tool response is invalid."
    assert "private" not in str(caught.value)
