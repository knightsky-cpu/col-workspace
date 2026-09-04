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


class RecordingAgentJobRepository:
    def __init__(self) -> None:
        self.enqueued: list[object] = []
        self.leases: list[dict[str, object]] = []
        self.completed: list[dict[str, object]] = []
        self.failed: list[dict[str, object]] = []
        self.events: list[object] = []

    async def enqueue_job(self, job):
        self.enqueued.append(job)
        return job

    async def enqueue_job_with_payload(self, job, payload):
        self.enqueued.append(job)
        self.payload = payload
        return job

    async def lease_queued_job(self, **kwargs):
        self.leases.append(kwargs)
        job = self.enqueued[-1]
        return job.model_copy(
            update={
                "status": "running",
                "lease_owner": kwargs["lease_owner"],
                "lease_expires_at": kwargs["lease_expires_at"],
                "updated_at": kwargs["observed_at"],
            }
        )

    async def complete_job(self, **kwargs):
        self.completed.append(kwargs)
        job = self.enqueued[-1]
        return job.model_copy(
            update={
                "status": "completed",
                "updated_at": kwargs["observed_at"],
                "result_refs": kwargs["result_refs"],
            }
        )

    async def fail_job(self, **kwargs):
        self.failed.append(kwargs)
        job = self.enqueued[-1]
        return job.model_copy(
            update={
                "status": "failed",
                "updated_at": kwargs["observed_at"],
                "failure_summary": kwargs["failure"],
            }
        )

    async def append_event(self, **kwargs):
        self.events.append(kwargs["event"])
        return kwargs["event"]


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

    state = note_tool_state() | {
        "note_turn_id": "a" * 64,
        "note_turn_owner_token": "owner-1",
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
    assert command.turn_lease is None


@pytest.mark.asyncio
async def test_note_tool_queues_background_job_when_dispatcher_is_available(
) -> None:
    from collaborative_note_tool import create_propose_collaborative_note_tool

    dispatched = []
    jobs = RecordingAgentJobRepository()
    service = RecordingCollaborativeNoteService()
    tool = create_propose_collaborative_note_tool(
        service,
        agent_job_repository=jobs,
        note_job_dispatcher=dispatched.append,
    )

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

    assert result["status"] == "queued"
    assert len(service.commands) == 0
    assert len(jobs.enqueued) == 1
    job = jobs.enqueued[0]
    assert result["queued_action"] == job.to_queued_action_receipt().model_dump(
        mode="json"
    )
    assert jobs.payload.job_id == job.job_id
    assert jobs.payload.action_kind == "propose_collaborative_note"
    assert "turn_lease" not in jobs.payload.payload
    assert "owner-1" not in str(jobs.payload.payload)
    assert dispatched == [job]
    assert [event.event_type for event in jobs.events] == ["queued"]


@pytest.mark.asyncio
async def test_note_tool_records_agent_job_lifecycle_for_pending_proposal(
) -> None:
    from collaborative_note_tool import create_propose_collaborative_note_tool

    jobs = RecordingAgentJobRepository()
    service = RecordingCollaborativeNoteService()
    tool = create_propose_collaborative_note_tool(
        service,
        agent_job_repository=jobs,
    )

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
    assert len(jobs.enqueued) == 1
    job = jobs.enqueued[0]
    assert job.action_kind == "propose_collaborative_note"
    assert job.status == "queued"
    assert job.user_id == "user-1"
    assert job.project_id == "workspace-1"
    assert job.workspace_id == "workspace-1"
    assert job.session_id == "session-1"
    assert job.source_message_id == "message-1"
    assert job.source_turn_id == "message-1"
    assert job.agent_label == "Note Curator"
    assert "API version" in job.display_label
    assert jobs.leases[0]["job_id"] == job.job_id
    assert jobs.completed[0]["job_id"] == job.job_id
    assert jobs.completed[0]["result_refs"] == {
        "proposal_id": "note-proposal-1",
    }
    assert [event.event_type for event in jobs.events] == [
        "queued",
        "started",
        "completed",
    ]


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
async def test_note_tool_does_not_enqueue_when_note_prequeued_for_turn(
) -> None:
    from collaborative_note_tool import create_propose_collaborative_note_tool

    dispatched = []
    jobs = RecordingAgentJobRepository()
    service = RecordingCollaborativeNoteService()
    tool = create_propose_collaborative_note_tool(
        service,
        agent_job_repository=jobs,
        note_job_dispatcher=dispatched.append,
    )
    state = note_tool_state() | {"note_prequeued_for_turn": True}

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
    assert jobs.enqueued == []
    assert dispatched == []


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_error", "expected_error_code"),
    (
        (
            "MemoryProposalConflictError",
            "collaborative_note_proposal_conflict",
        ),
        (
            "MemoryProposalOriginConflictError",
            "collaborative_note_proposal_conflict",
        ),
        (
            "ChatTurnStateError",
            "collaborative_note_turn_conflict",
        ),
        (
            "ChatTurnOwnershipError",
            "collaborative_note_turn_conflict",
        ),
    ),
)
async def test_note_tool_returns_rejected_response_for_state_conflicts(
    service_error: str,
    expected_error_code: str,
) -> None:
    from chat_turns import ChatTurnOwnershipError, ChatTurnStateError
    from collaborative_note_tool import create_propose_collaborative_note_tool
    from database import (
        MemoryProposalConflictError,
        MemoryProposalOriginConflictError,
    )

    error_types = {
        "MemoryProposalConflictError": MemoryProposalConflictError,
        "MemoryProposalOriginConflictError": MemoryProposalOriginConflictError,
        "ChatTurnStateError": ChatTurnStateError,
        "ChatTurnOwnershipError": ChatTurnOwnershipError,
    }
    service = RecordingCollaborativeNoteService(
        error=error_types[service_error]("private conflict detail")
    )
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

    assert result == {
        "status": "rejected",
        "error_code": expected_error_code,
    }
    assert len(service.commands) == 1
    assert "private" not in str(result)


@pytest.mark.asyncio
async def test_note_tool_marks_agent_job_failed_when_note_service_errors(
) -> None:
    from collaborative_note_tool import create_propose_collaborative_note_tool
    from database import MemoryProposalConflictError

    jobs = RecordingAgentJobRepository()
    service = RecordingCollaborativeNoteService(
        error=MemoryProposalConflictError("private conflict detail")
    )
    tool = create_propose_collaborative_note_tool(
        service,
        agent_job_repository=jobs,
    )

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

    assert result == {
        "status": "rejected",
        "error_code": "collaborative_note_proposal_conflict",
    }
    assert jobs.failed[0]["job_id"] == jobs.enqueued[0].job_id
    failure = jobs.failed[0]["failure"]
    assert failure.code == "collaborative_note_proposal_conflict"
    assert failure.summary == "Workspace note proposal could not be created."
    assert failure.retryable is False
    assert [event.event_type for event in jobs.events] == [
        "queued",
        "started",
        "failed",
    ]
    assert "private" not in failure.summary


def test_note_tool_response_parser_accepts_state_conflict_rejections() -> None:
    from collaborative_note_tool import (
        RejectedCollaborativeNoteToolResponse,
        parse_collaborative_note_tool_response,
    )

    proposal_conflict = parse_collaborative_note_tool_response(
        {
            "status": "rejected",
            "error_code": "collaborative_note_proposal_conflict",
        }
    )
    turn_conflict = parse_collaborative_note_tool_response(
        {
            "status": "rejected",
            "error_code": "collaborative_note_turn_conflict",
        }
    )

    assert isinstance(
        proposal_conflict,
        RejectedCollaborativeNoteToolResponse,
    )
    assert isinstance(turn_conflict, RejectedCollaborativeNoteToolResponse)
