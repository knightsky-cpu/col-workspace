from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.adk.sessions import State
from google.adk.tools import FunctionTool

from schemas import AgentActionReceipt, MemoryProposalReceiptV2
from trusted_memory_service import (
    NaturalMemoryClarificationResult,
    NaturalMemoryProposalResult,
)


NOW = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)


class NoopMemoryService:
    async def propose_memory_signal(self, command):
        raise AssertionError("declaration inspection must not call service")


class RecordingMemoryService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.commands: list[object] = []

    async def handle_natural_memory_decision(self, command):
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return NaturalMemoryProposalResult(
            status="pending",
            action=AgentActionReceipt(
                action_name="propose_memory_signal",
                status="completed",
            ),
            proposal=MemoryProposalReceiptV2(
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
        "memory_workspace_id": "workspace-1",
        "memory_session_id": "session-1",
        "memory_source_message_id": "message-1",
        "memory_source_message_text": "I prefer concise responses.",
        "memory_decision_present": False,
        "artifact_feedback_decision_present": False,
        "memory_turn_id": "a" * 64,
        "memory_turn_owner_token": "owner-1",
    }


@pytest.mark.filterwarnings(
    "ignore:\\[EXPERIMENTAL\\].*JSON_SCHEMA_FOR_FUNC_DECL.*:UserWarning"
)
def test_proposal_tool_exposes_only_natural_decision_fields_to_model() -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    tool = create_propose_memory_signal_tool(NoopMemoryService())
    declaration = tool._get_declaration()

    assert isinstance(tool, FunctionTool)
    assert tool.name == "propose_memory_signal"
    assert declaration is not None
    schema = declaration.parameters_json_schema
    assert schema is not None
    assert set(schema["properties"]) == {
        "decision",
        "clarification_selection",
    }
    assert schema["required"] == ["decision"]
    rendered = declaration.model_dump_json(exclude_none=True)
    for server_owned_name in (
        "user_id",
        "session_id",
        "source_message_id",
        "source_message_text",
        "memory_decision_present",
        "turn_id",
        "owner_token",
        "workspace_id",
        "tool_context",
    ):
        assert server_owned_name not in rendered


@pytest.mark.filterwarnings(
    "ignore:\\[EXPERIMENTAL\\].*JSON_SCHEMA_FOR_FUNC_DECL.*:UserWarning"
)
def test_proposal_tool_declares_development_environments_as_an_array() -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    tool = create_propose_memory_signal_tool(NoopMemoryService())
    declaration = tool._get_declaration()

    assert declaration is not None
    schema = declaration.parameters_json_schema
    assert schema is not None
    candidate_schema = schema["$defs"][
        "DevelopmentEnvironmentsProviderCandidate"
    ]
    assert candidate_schema["properties"]["category"]["const"] == (
        "development_environments"
    )
    canonical_schema = candidate_schema["properties"]["canonical_value"]
    assert canonical_schema["type"] == "array"
    assert canonical_schema["minItems"] == 1
    assert canonical_schema["maxItems"] == 3
    assert canonical_schema["items"] == {
        "enum": ["macos", "linux", "windows"],
        "type": "string",
    }


@pytest.mark.filterwarnings(
    "ignore:\\[EXPERIMENTAL\\].*JSON_SCHEMA_FOR_FUNC_DECL.*:UserWarning"
)
def test_proposal_tool_declares_user_requested_memory_as_bounded_text() -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    tool = create_propose_memory_signal_tool(NoopMemoryService())
    declaration = tool._get_declaration()

    assert declaration is not None
    schema = declaration.parameters_json_schema
    assert schema is not None
    candidate_schema = schema["$defs"][
        "UserRequestedMemoryProviderCandidate"
    ]
    assert candidate_schema["properties"]["category"]["const"] == (
        "user_requested_memory"
    )
    canonical_schema = candidate_schema["properties"]["canonical_value"]
    assert canonical_schema["type"] == "string"
    assert canonical_schema["minLength"] == 1
    assert canonical_schema["maxLength"] == 240


@pytest.mark.asyncio
async def test_proposal_tool_preserves_user_requested_memory_candidate() -> None:
    from memory_candidate_decisions import ProfileCandidateDecision
    from memory_proposal_tool import create_propose_memory_signal_tool

    state = tool_context_state()
    state["memory_source_message_text"] = (
        "Col please remember that I like security focused software projects."
    )
    service = RecordingMemoryService()
    tool = create_propose_memory_signal_tool(service)

    result = await tool.run_async(
        args={
            "decision": {
                "kind": "profile_candidate",
                "category": "user_requested_memory",
                "canonical_value": (
                    "I like security focused software projects."
                ),
                "evidence_text": (
                    "I like security focused software projects."
                ),
            },
        },
        tool_context=SimpleNamespace(
            state=State(value=state, delta={})
        ),
    )

    assert result["status"] == "pending"
    assert len(service.commands) == 1
    decision = service.commands[0].decision
    assert isinstance(decision, ProfileCandidateDecision)
    assert decision.category == "user_requested_memory"
    assert decision.canonical_value == (
        "I like security focused software projects."
    )


@pytest.mark.asyncio
async def test_proposal_tool_builds_pending_result_from_adk_state() -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    service = RecordingMemoryService()
    tool = create_propose_memory_signal_tool(service)

    result = await tool.run_async(
        args={
            "decision": {
                "kind": "profile_candidate",
                "category": "response_length",
                "canonical_value": "concise",
                "evidence_text": "prefer concise responses",
            },
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
            "policy_version": "2.0",
            "expires_at": "2026-08-22T16:00:00Z",
        },
    }
    command = service.commands[0]
    assert command.user_id == "user-1"
    assert command.session_id == "session-1"
    assert command.source_message_id == "message-1"
    assert command.source_message_text == "I prefer concise responses."
    assert command.memory_decision_present is False
    assert command.workspace_id == "workspace-1"
    assert command.decision.kind == "profile_candidate"
    assert command.decision.category == "response_length"
    assert command.decision.canonical_value == "concise"
    assert command.clarification_selection is None
    assert command.turn_lease.turn_id == "a" * 64
    assert command.turn_lease.owner_token == "owner-1"


@pytest.mark.asyncio
async def test_proposal_tool_preserves_one_list_valued_environment_candidate(
) -> None:
    from memory_candidate_decisions import ProfileCandidateDecision
    from memory_proposal_tool import create_propose_memory_signal_tool

    state = tool_context_state()
    state["memory_source_message_text"] = (
        "Please remember that I prefer macOS and Linux development environments."
    )
    service = RecordingMemoryService()
    tool = create_propose_memory_signal_tool(service)

    result = await tool.run_async(
        args={
            "decision": {
                "kind": "profile_candidate",
                "category": "development_environments",
                "canonical_value": ["macos", "linux"],
                "evidence_text": (
                    "macOS and Linux development environments"
                ),
            },
        },
        tool_context=SimpleNamespace(
            state=State(value=state, delta={})
        ),
    )

    assert result["status"] == "pending"
    assert len(service.commands) == 1
    decision = service.commands[0].decision
    assert isinstance(decision, ProfileCandidateDecision)
    assert decision.category == "development_environments"
    assert decision.canonical_value == ["macos", "linux"]


@pytest.mark.asyncio
async def test_proposal_tool_rejects_live_malformed_clarification_before_service(
) -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    service = RecordingMemoryService()
    tool = create_propose_memory_signal_tool(service)

    result = await tool.run_async(
        args={
            "decision": {
                "kind": "clarify",
                "candidates": [
                    {
                        "kind": "profile_candidate",
                        "category": "development_environments",
                        "canonical_value": "macos",
                        "evidence_text": "macOS",
                    },
                    {
                        "kind": "profile_candidate",
                        "category": "development_environments",
                        "canonical_value": "linux",
                        "evidence_text": "Linux",
                    },
                ],
            },
        },
        tool_context=SimpleNamespace(state=tool_context_state()),
    )

    assert result == {
        "status": "rejected",
        "error_code": "invalid_memory_candidate",
    }
    assert service.commands == []


@pytest.mark.asyncio
async def test_proposal_tool_rejects_malformed_selection_before_service() -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    service = RecordingMemoryService()
    tool = create_propose_memory_signal_tool(service)

    result = await tool.run_async(
        args={
            "decision": {"kind": "no_memory"},
            "clarification_selection": {
                "selected_candidate_index": "first",
            },
        },
        tool_context=SimpleNamespace(state=tool_context_state()),
    )

    assert result == {
        "status": "rejected",
        "error_code": "invalid_memory_candidate",
    }
    assert service.commands == []


@pytest.mark.asyncio
async def test_proposal_tool_rejects_invalid_candidate_without_receipt() -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    service = RecordingMemoryService(error=ValueError("private candidate"))
    tool = create_propose_memory_signal_tool(service)

    result = await tool.run_async(
        args={
            "decision": {
                "kind": "profile_candidate",
                "category": "response_length",
                "canonical_value": "invalid-private-value",
                "evidence_text": "private candidate",
            },
        },
        tool_context=SimpleNamespace(state=tool_context_state()),
    )

    assert result == {
        "status": "rejected",
        "error_code": "invalid_memory_candidate",
    }
    assert "private" not in str(result)


@pytest.mark.asyncio
async def test_proposal_tool_refuses_artifact_feedback_turn() -> None:
    from memory_proposal_tool import create_propose_memory_signal_tool

    state = tool_context_state()
    state["artifact_feedback_decision_present"] = True
    service = RecordingMemoryService()
    tool = create_propose_memory_signal_tool(service)

    result = await tool.run_async(
        args={
            "decision": {"kind": "no_memory"},
        },
        tool_context=SimpleNamespace(state=state),
    )

    assert result == {
        "status": "rejected",
        "error_code": "invalid_memory_candidate",
    }
    assert service.commands == []


@pytest.mark.asyncio
async def test_proposal_tool_returns_application_owned_clarification() -> None:
    from memory_clarifications import MemoryClarificationReceipt
    from memory_proposal_tool import create_propose_memory_signal_tool

    service = RecordingMemoryService()
    service.handle_natural_memory_decision = AsyncMock(
        return_value=NaturalMemoryClarificationResult(
            status="clarification_required",
            clarification=MemoryClarificationReceipt(
                clarification_id="memory-clarification--abc",
                choices=[
                    {
                        "candidate_index": 0,
                        "category_label": "Preferred name",
                        "value_label": "wifiknight",
                    },
                    {
                        "candidate_index": 1,
                        "category_label": "Development environments",
                        "value_label": "macOS and Linux",
                    },
                ],
                expires_at=NOW,
            ),
        )
    )
    tool = create_propose_memory_signal_tool(service)

    result = await tool.run_async(
        args={
            "decision": {
                "kind": "clarify",
                "candidates": [
                    {
                        "kind": "profile_candidate",
                        "category": "preferred_name",
                        "canonical_value": "wifiknight",
                        "evidence_text": "called wifiknight",
                    },
                    {
                        "kind": "profile_candidate",
                        "category": "development_environments",
                        "canonical_value": ["macos", "linux"],
                        "evidence_text": "macOS and Linux",
                    },
                ],
            }
        },
        tool_context=SimpleNamespace(
            state=State(value=tool_context_state(), delta={})
        ),
    )

    assert result["status"] == "clarification_required"
    assert result["memory_clarification"]["choices"][1] == {
        "candidate_index": 1,
        "category_label": "Development environments",
        "value_label": "macOS and Linux",
    }


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
                "decision": {
                    "kind": "profile_candidate",
                    "category": "response_length",
                    "canonical_value": "concise",
                    "evidence_text": "prefer concise responses",
                },
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
                "policy_version": "2.0",
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
                "policy_version": "2.0",
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
