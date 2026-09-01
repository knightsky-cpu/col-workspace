from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from google.adk.sessions import State
from google.adk.tools import FunctionTool

from schemas import AgentActionReceipt, CollaborativeNoteProposal


NOW = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)


class NoopCollaborativeNoteService:
    async def create_natural_proposal(self, command):
        raise AssertionError("declaration inspection must not call service")


class RecordingCollaborativeNoteService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.commands: list[object] = []

    async def create_natural_proposal(self, command):
        from collaborative_note_service import CollaborativeNoteProposalResult

        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return CollaborativeNoteProposalResult(
            action=AgentActionReceipt(
                action_name="propose_collaborative_note",
                status="completed",
            ),
            proposal=CollaborativeNoteProposal(
                proposal_id="note-proposal-1",
                note_kind="constraint",
                title="API version",
                body="Use API version 2.",
                source_session_id="session-1",
                source_message_ids=["message-1"],
                expected_note_id=None,
                expected_revision=None,
                policy_version="1.0",
                status="pending",
                created_at=NOW,
                expires_at=NOW + timedelta(hours=24),
            ),
        )


def note_tool_state() -> dict[str, object]:
    return {
        "note_user_id": "user-1",
        "note_workspace_id": "workspace-1",
        "note_session_id": "session-1",
        "note_source_message_id": "message-1",
        "note_source_message_text": (
            "Agent Col, note that this workspace must use API version 2."
        ),
        "memory_decision_present": False,
        "collaborative_note_decision_present": False,
        "artifact_feedback_decision_present": False,
        "note_turn_id": "a" * 64,
        "note_turn_owner_token": "owner-1",
    }


@pytest.mark.filterwarnings(
    "ignore:\\[EXPERIMENTAL\\].*JSON_SCHEMA_FOR_FUNC_DECL.*:UserWarning"
)
def test_note_tool_exposes_only_note_decision_fields_to_model() -> None:
    from collaborative_note_tool import create_propose_collaborative_note_tool

    tool = create_propose_collaborative_note_tool(
        NoopCollaborativeNoteService()
    )
    declaration = tool._get_declaration()

    assert isinstance(tool, FunctionTool)
    assert tool.name == "propose_collaborative_note"
    assert declaration is not None
    schema = declaration.parameters_json_schema
    assert schema is not None
    assert set(schema["properties"]) == {"decision"}
    assert schema["required"] == ["decision"]
    rendered = declaration.model_dump_json(exclude_none=True)
    for server_owned_name in (
        "user_id",
        "workspace_id",
        "session_id",
        "source_message_id",
        "source_message_text",
        "turn_id",
        "owner_token",
        "tool_context",
    ):
        assert server_owned_name not in rendered


@pytest.mark.asyncio
async def test_note_tool_builds_pending_result_from_adk_state() -> None:
    from collaborative_note_candidates import NoteCandidateDecision
    from collaborative_note_tool import create_propose_collaborative_note_tool

    service = RecordingCollaborativeNoteService()
    tool = create_propose_collaborative_note_tool(service)

    result = await tool.run_async(
        args={
            "decision": {
                "kind": "note_candidate",
                "note_kind": "constraint",
                "title": "API version",
                "body": "Use API version 2.",
                "evidence_text": "this workspace must use API version 2",
            }
        },
        tool_context=SimpleNamespace(
            state=State(value=note_tool_state(), delta={})
        ),
    )

    assert result["status"] == "pending"
    assert result["action"] == {
        "action_name": "propose_collaborative_note",
        "status": "completed",
    }
    assert result["collaborative_note_proposal"]["proposal_id"] == (
        "note-proposal-1"
    )
    command = service.commands[0]
    assert command.user_id == "user-1"
    assert command.workspace_id == "workspace-1"
    assert command.session_id == "session-1"
    assert command.source_message_id == "message-1"
    assert command.source_message_text == (
        "Agent Col, note that this workspace must use API version 2."
    )
    assert command.memory_decision_present is False
    assert command.collaborative_note_decision_present is False
    assert isinstance(command.decision, NoteCandidateDecision)
    assert command.turn_lease.turn_id == "a" * 64


@pytest.mark.asyncio
async def test_note_tool_skips_candidate_when_turn_already_has_durable_effect(
) -> None:
    from collaborative_note_tool import create_propose_collaborative_note_tool

    service = RecordingCollaborativeNoteService()
    tool = create_propose_collaborative_note_tool(service)
    state = note_tool_state() | {
        "governed_turn_has_precompleted_durable_effect": True,
    }

    result = await tool.run_async(
        args={
            "decision": {
                "kind": "note_candidate",
                "note_kind": "constraint",
                "title": "API version",
                "body": "Use API version 2.",
                "evidence_text": "this workspace must use API version 2",
            }
        },
        tool_context=SimpleNamespace(state=State(value=state, delta={})),
    )

    assert result == {"status": "no_note"}
    assert service.commands == []


@pytest.mark.asyncio
async def test_note_tool_rejects_unsafe_or_ungrounded_candidates() -> None:
    from collaborative_note_tool import create_propose_collaborative_note_tool

    service = RecordingCollaborativeNoteService()
    tool = create_propose_collaborative_note_tool(service)

    result = await tool.run_async(
        args={
            "decision": {
                "kind": "note_candidate",
                "note_kind": "working_context",
                "title": "Key",
                "body": "The API key is sk-123456789abcdef",
                "evidence_text": "The API key is sk-123456789abcdef",
            }
        },
        tool_context=SimpleNamespace(
            state=State(value=note_tool_state(), delta={})
        ),
    )

    assert result == {
        "status": "rejected",
        "error_code": "invalid_collaborative_note_candidate",
    }
    assert service.commands == []

    result = await tool.run_async(
        args={
            "decision": {
                "kind": "note_candidate",
                "note_kind": "constraint",
                "title": "API version",
                "body": "Use API version 2.",
                "evidence_text": "Use API version 2",
            }
        },
        tool_context=SimpleNamespace(
            state=State(value=note_tool_state(), delta={})
        ),
    )

    assert result["status"] == "rejected"
    assert service.commands == []
