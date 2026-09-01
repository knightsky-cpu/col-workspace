from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import logging
from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.genai import types


@dataclass
class FakeSessionService:
    created: list[dict[str, object]] = field(default_factory=list)
    deleted: list[dict[str, str]] = field(default_factory=list)

    async def create_session(self, **kwargs: object) -> SimpleNamespace:
        self.created.append(dict(kwargs))
        return SimpleNamespace(id=kwargs["session_id"])

    async def delete_session(self, **kwargs: str) -> None:
        self.deleted.append(dict(kwargs))


class FakeEvent:
    def __init__(
        self,
        text: str | None,
        final: bool,
        function_responses: list[types.FunctionResponse] | None = None,
        function_calls: list[types.FunctionCall] | None = None,
        author: str = "Agent_Col",
        partial: bool = False,
        thought: bool = False,
    ) -> None:
        parts = [] if text is None else [types.Part.from_text(text=text)]
        if parts:
            parts[0].thought = thought
        self.content = types.Content(role="model", parts=parts)
        self._final = final
        self._function_responses = function_responses or []
        self._function_calls = function_calls or []
        self.author = author
        self.partial = partial

    def is_final_response(self) -> bool:
        return self._final

    def get_function_responses(self) -> list[types.FunctionResponse]:
        return list(self._function_responses)

    def get_function_calls(self) -> list[types.FunctionCall]:
        return list(self._function_calls)


def pending_function_response(
    *,
    origin_id: str = "e82366f7699ee2e39bff6a68154e09b7",
    proposed_value: str = "concise",
) -> types.FunctionResponse:
    return types.FunctionResponse(
        name="propose_memory_signal",
        response={
            "status": "pending",
            "action": {
                "action_name": "propose_memory_signal",
                "status": "completed",
            },
            "memory_proposal": {
                "proposal_id": f"response_length--{origin_id}",
                "category": "response_length",
                "proposed_value": proposed_value,
                "expires_at": "2026-08-22T16:00:00Z",
            },
        },
    )


def pending_v2_function_response() -> types.FunctionResponse:
    return types.FunctionResponse(
        name="propose_memory_signal",
        response={
            "status": "pending",
            "action": {
                "action_name": "propose_memory_signal",
                "status": "completed",
            },
            "memory_proposal": {
                "proposal_id": "development_environments--proposal-2",
                "category": "development_environments",
                "proposed_value": ["macos", "linux"],
                "policy_version": "2.0",
                "expires_at": "2026-08-26T16:00:00Z",
            },
        },
    )


def clarification_function_response() -> types.FunctionResponse:
    return types.FunctionResponse(
        name="propose_memory_signal",
        response={
            "status": "clarification_required",
            "memory_clarification": {
                "clarification_id": (
                    "memory-clarification--clarification-1"
                ),
                "choices": [
                    {
                        "candidate_index": 0,
                        "category_label": "Response length",
                        "value_label": "detailed",
                    },
                    {
                        "candidate_index": 1,
                        "category_label": "Explanation structure",
                        "value_label": "step by step",
                    },
                ],
                "expires_at": "2026-08-25T16:15:00Z",
            },
        },
    )


def pending_note_function_response() -> types.FunctionResponse:
    return types.FunctionResponse(
        name="propose_collaborative_note",
        response={
            "status": "pending",
            "action": {
                "action_name": "propose_collaborative_note",
                "status": "completed",
            },
            "collaborative_note_proposal": {
                "note_contract_version": "1.0",
                "proposal_id": "note-proposal-1",
                "note_kind": "constraint",
                "title": "API version",
                "body": "Use API version 2.",
                "source_session_id": "session-1",
                "source_message_ids": ["message-1"],
                "expected_note_id": None,
                "expected_revision": None,
                "policy_version": "1.0",
                "status": "pending",
                "created_at": "2026-08-26T16:00:00Z",
                "expires_at": "2026-08-27T16:00:00Z",
            },
        },
    )


@dataclass
class FakeRunner:
    events: list[object]
    calls: list[dict[str, object]] = field(default_factory=list)
    error: Exception | None = None

    async def run_async(self, **kwargs: object) -> AsyncIterator[object]:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        for event in self.events:
            yield event


@pytest.mark.asyncio
async def test_stream_turn_emits_true_adk_text_deltas_before_one_completion(
) -> None:
    from google.adk.agents.run_config import StreamingMode

    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    runner = FakeRunner(
        events=[
            FakeEvent(text="Agent ", final=False, partial=True),
            FakeEvent(text="Col", final=False, partial=True),
            FakeEvent(text="Agent Col", final=True),
        ]
    )
    runtime = SupervisorRuntime(
        runner=runner,
        session_service=FakeSessionService(),
    )

    streamed = [
        event
        async for event in runtime.stream_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Help with this design.",
            )
        )
    ]

    assert [event.text for event in streamed[:-1]] == ["Agent ", "Col"]
    assert streamed[-1].result.response == "Agent Col"
    assert runner.calls[0]["run_config"].streaming_mode is StreamingMode.SSE


@pytest.mark.asyncio
async def test_stream_turn_buffers_ambiguous_repeated_prefix_deltas() -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(text="a", final=False, partial=True),
                FakeEvent(text="abc", final=False, partial=True),
                FakeEvent(text="!", final=False, partial=True),
                FakeEvent(text="aabc!", final=True),
            ]
        ),
        session_service=FakeSessionService(),
    )

    streamed = [
        event
        async for event in runtime.stream_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Help with this design.",
            )
        )
    ]

    deltas = [event.text for event in streamed[:-1]]
    assert deltas == ["a", "abc!"]
    assert "".join(deltas) == streamed[-1].result.response


@pytest.mark.asyncio
async def test_stream_turn_normalizes_cumulative_snapshots_without_duplicates(
) -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(text="Agent", final=False, partial=True),
                FakeEvent(text="Agent Col", final=False, partial=True),
                FakeEvent(text="Agent Col", final=True),
            ]
        ),
        session_service=FakeSessionService(),
    )

    streamed = [
        event
        async for event in runtime.stream_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Help with this design.",
            )
        )
    ]

    deltas = [event.text for event in streamed[:-1]]
    assert deltas == ["Agent", " Col"]
    assert "".join(deltas) == streamed[-1].result.response


@pytest.mark.asyncio
async def test_stream_turn_emits_only_the_missing_final_text_tail() -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(text="Agent", final=False, partial=True),
                FakeEvent(text="Agent Col", final=True),
            ]
        ),
        session_service=FakeSessionService(),
    )

    streamed = [
        event
        async for event in runtime.stream_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Help with this design.",
            )
        )
    ]

    assert [event.text for event in streamed[:-1]] == ["Agent", " Col"]
    assert streamed[-1].result.response == "Agent Col"


@pytest.mark.asyncio
async def test_stream_turn_ignores_thought_tool_and_non_agent_text() -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(
                    text="hidden reasoning",
                    final=False,
                    partial=True,
                    thought=True,
                ),
                FakeEvent(
                    text="tool internals",
                    final=False,
                    partial=True,
                    function_responses=[
                        types.FunctionResponse(
                            name="internal_tool",
                            response={"private": "value"},
                        )
                    ],
                ),
                FakeEvent(
                    text="tool request internals",
                    final=False,
                    partial=True,
                    function_calls=[
                        types.FunctionCall(
                            name="internal_tool",
                            args={"private": "value"},
                        )
                    ],
                ),
                FakeEvent(
                    text="specialist draft",
                    final=False,
                    partial=True,
                    author="ResearchExpert",
                ),
                FakeEvent(text="Safe answer.", final=True),
            ]
        ),
        session_service=FakeSessionService(),
    )

    streamed = [
        event
        async for event in runtime.stream_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Help with this design.",
            )
        )
    ]

    assert [event.text for event in streamed[:-1]] == ["Safe answer."]
    assert streamed[-1].result.response == "Safe answer."


@pytest.mark.asyncio
async def test_stream_turn_excludes_thought_parts_from_the_final_response(
) -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    final_event = FakeEvent(text="Safe answer.", final=True)
    final_event.content.parts.insert(
        0,
        types.Part(text="hidden reasoning", thought=True),
    )
    runtime = SupervisorRuntime(
        runner=FakeRunner(events=[final_event]),
        session_service=FakeSessionService(),
    )

    streamed = [
        event
        async for event in runtime.stream_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Help with this design.",
            )
        )
    ]

    assert [event.text for event in streamed[:-1]] == ["Safe answer."]
    assert streamed[-1].result.response == "Safe answer."


@pytest.mark.asyncio
async def test_run_turn_uses_bounded_fresh_session_and_returns_final_text(
) -> None:
    from supervisor_runtime import (
        SUPERVISOR_MAX_LLM_CALLS,
        SupervisorRuntime,
        SupervisorTurnContext,
    )

    sessions = FakeSessionService()
    runner = FakeRunner(
        events=[
            FakeEvent(text=None, final=False),
            FakeEvent(text="  Collaborative answer.  ", final=True),
        ]
    )
    history = types.Content(
        role="user",
        parts=[types.Part.from_text(text="Earlier context")],
    )
    runtime = SupervisorRuntime(runner=runner, session_service=sessions)
    context = SupervisorTurnContext(
        project_id="project-1",
        session_id="session-1",
        user_id="user-1",
        message="Help with this design.",
        model_input_context=(history,),
    )

    result = await runtime.run_turn(context)

    assert result.response == "Collaborative answer."
    assert result.actions == ()
    assert result.artifacts == ()
    assert result.citations == ()
    assert result.memory_proposals == ()
    created = sessions.created[0]
    assert created["app_name"] == "agent_col"
    assert created["user_id"] == "user-1"
    assert created["session_id"] != "session-1"
    state = dict(created["state"])
    delegation_token = state.pop("expert_delegation_token")
    assert isinstance(delegation_token, str)
    assert state == {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
    }
    assert sessions.deleted[0]["session_id"] == created["session_id"]
    call = runner.calls[0]
    assert call["session_id"] == created["session_id"]
    assert call["new_message"].parts[0].text == "Help with this design."
    assert call["run_config"].max_llm_calls == SUPERVISOR_MAX_LLM_CALLS
    assert SUPERVISOR_MAX_LLM_CALLS == 4
    assert call["run_config"].model_input_context == [history]


@pytest.mark.asyncio
async def test_run_turn_places_server_owned_memory_context_in_session_state(
) -> None:
    from memory_proposals import ProposalTurnLease
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    sessions = FakeSessionService()
    runtime = SupervisorRuntime(
        runner=FakeRunner(events=[FakeEvent("Pending proposal.", True)]),
        session_service=sessions,
    )

    await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Remember that I prefer concise responses.",
            source_message_id="turn--source-message--user",
            memory_decision_present=False,
            turn_lease=ProposalTurnLease(
                turn_id="a" * 64,
                owner_token="owner-token-1",
            ),
        )
    )

    state = dict(sessions.created[0]["state"])
    delegation_token = state.pop("expert_delegation_token")
    assert isinstance(delegation_token, str)
    assert state == {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "memory_user_id": "user-1",
        "memory_workspace_id": "project-1",
        "memory_session_id": "session-1",
        "memory_source_message_id": "turn--source-message--user",
        "memory_source_message_text": (
            "Remember that I prefer concise responses."
        ),
        "memory_decision_present": False,
        "artifact_feedback_decision_present": False,
        "memory_turn_id": "a" * 64,
        "memory_turn_owner_token": "owner-token-1",
        "note_user_id": "user-1",
        "note_workspace_id": "project-1",
        "note_session_id": "session-1",
        "note_source_message_id": "turn--source-message--user",
        "note_source_message_text": (
            "Remember that I prefer concise responses."
        ),
        "collaborative_note_decision_present": False,
        "note_turn_id": "a" * 64,
        "note_turn_owner_token": "owner-token-1",
    }


@pytest.mark.asyncio
async def test_run_turn_places_server_owned_note_context_in_session_state(
) -> None:
    from memory_proposals import ProposalTurnLease
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    sessions = FakeSessionService()
    runtime = SupervisorRuntime(
        runner=FakeRunner(events=[FakeEvent("Pending note.", True)]),
        session_service=sessions,
    )

    await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Agent Col, note that this workspace must use API v2.",
            source_message_id="turn--source-message--user",
            memory_decision_present=False,
            collaborative_note_decision_present=False,
            artifact_feedback_decision_present=False,
            turn_lease=ProposalTurnLease(
                turn_id="a" * 64,
                owner_token="owner-token-1",
            ),
        )
    )

    state = dict(sessions.created[0]["state"])
    delegation_token = state.pop("expert_delegation_token")
    assert isinstance(delegation_token, str)
    assert state == {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "memory_user_id": "user-1",
        "memory_workspace_id": "project-1",
        "memory_session_id": "session-1",
        "memory_source_message_id": "turn--source-message--user",
        "memory_source_message_text": (
            "Agent Col, note that this workspace must use API v2."
        ),
        "memory_decision_present": False,
        "artifact_feedback_decision_present": False,
        "memory_turn_id": "a" * 64,
        "memory_turn_owner_token": "owner-token-1",
        "note_user_id": "user-1",
        "note_workspace_id": "project-1",
        "note_session_id": "session-1",
        "note_source_message_id": "turn--source-message--user",
        "note_source_message_text": (
            "Agent Col, note that this workspace must use API v2."
        ),
        "collaborative_note_decision_present": False,
        "note_turn_id": "a" * 64,
        "note_turn_owner_token": "owner-token-1",
    }


@pytest.mark.asyncio
async def test_run_turn_includes_precompleted_note_decision_context() -> None:
    from datetime import UTC, datetime
    from schemas import AgentActionReceipt, CollaborativeNoteEvent
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    event = CollaborativeNoteEvent(
        event_id="event--private-note-approved",
        note_id="note--private",
        proposal_id="note-proposal--private",
        owner_user_id="user-1",
        workspace_id="workspace--private",
        event_type="approved",
        note_kind="constraint",
        title="API version",
        body="Use API version 2.",
        source_session_id="session--private",
        source_message_ids=["message--private"],
        revision=1,
        previous_revision=None,
        created_at=datetime(2026, 8, 26, 16, 0, tzinfo=UTC),
    )
    action = AgentActionReceipt(
        action_name="approve_collaborative_note",
        status="completed",
    )
    runner = FakeRunner(events=[FakeEvent("Recorded.", True)])
    runtime = SupervisorRuntime(
        runner=runner,
        session_service=FakeSessionService(),
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Approve that note.",
            precompleted_actions=(action,),
            precompleted_collaborative_note_events=(event,),
        )
    )

    assert result.actions == (action,)
    assert result.collaborative_note_events == (event,)
    context_text = runner.calls[0]["run_config"].model_input_context[0].parts[
        0
    ].text
    assert "SERVER_VALIDATED_PRECOMPLETED_ACTIONS" in context_text
    assert "collaborative_note_events" in context_text
    assert "API version" in context_text
    assert "Use API version 2." in context_text
    assert "approved" in context_text
    assert "event--private-note-approved" not in context_text
    assert "note--private" not in context_text
    assert "note-proposal--private" not in context_text
    assert "workspace--private" not in context_text
    assert "session--private" not in context_text
    assert "message--private" not in context_text


@pytest.mark.asyncio
async def test_run_turn_marks_precompleted_artifact_as_durable_tool_state(
) -> None:
    from schemas import AgentActionReceipt
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    action = AgentActionReceipt(
        action_name="create_artifact",
        status="completed",
    )
    sessions = FakeSessionService()
    runtime = SupervisorRuntime(
        runner=FakeRunner(events=[FakeEvent("Created the script.", True)]),
        session_service=sessions,
    )

    await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Write a bash script.",
            source_message_id="turn--source-message--user",
            precompleted_actions=(action,),
        )
    )

    state = dict(sessions.created[0]["state"])
    assert state["governed_turn_has_precompleted_durable_effect"] is True


@pytest.mark.asyncio
async def test_run_turn_collects_note_proposal_receipt_truthfully() -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(None, False, [pending_note_function_response()]),
                FakeEvent("That note is pending your approval.", True),
            ]
        ),
        session_service=FakeSessionService(),
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Agent Col, note that this workspace must use API v2.",
        )
    )

    assert result.response == "That note is pending your approval."
    assert [action.model_dump(mode="json") for action in result.actions] == [
        {
            "action_name": "propose_collaborative_note",
            "status": "completed",
        }
    ]
    assert result.memory_proposals == ()
    assert len(result.collaborative_note_proposals) == 1
    assert result.collaborative_note_proposals[0].proposal_id == (
        "note-proposal-1"
    )


@pytest.mark.asyncio
async def test_run_turn_rejects_combined_memory_and_note_proposals() -> None:
    from supervisor_runtime import (
        SupervisorRuntime,
        SupervisorRuntimeError,
        SupervisorTurnContext,
    )

    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(
                    None,
                    False,
                    [
                        pending_function_response(),
                        pending_note_function_response(),
                    ],
                )
            ]
        ),
        session_service=FakeSessionService(),
    )

    with pytest.raises(SupervisorRuntimeError, match="conflicting"):
        await runtime.run_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Remember and note this.",
            )
        )


@pytest.mark.asyncio
async def test_run_turn_collects_version_two_proposal_receipt_truthfully(
) -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(None, False, [pending_v2_function_response()]),
                FakeEvent(
                    "That preference is pending your approval.",
                    True,
                ),
            ]
        ),
        session_service=FakeSessionService(),
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Remember that I prefer macOS and Linux environments.",
        )
    )

    assert result.response == "That preference is pending your approval."
    assert result.memory_proposals[0].model_dump(mode="json") == {
        "proposal_id": "development_environments--proposal-2",
        "category": "development_environments",
        "proposed_value": ["macos", "linux"],
        "policy_version": "2.0",
        "expires_at": "2026-08-26T16:00:00Z",
    }


@pytest.mark.asyncio
async def test_run_turn_collects_memory_clarification_receipt_truthfully(
) -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(None, False, [clarification_function_response()]),
                FakeEvent(
                    "Which preference would you like me to remember?",
                    True,
                ),
            ]
        ),
        session_service=FakeSessionService(),
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Remember that I prefer detailed explanations.",
        )
    )

    assert result.memory_proposals == ()
    assert len(result.memory_clarifications) == 1
    assert result.memory_clarifications[0].model_dump(mode="json") == {
        "clarification_id": "memory-clarification--clarification-1",
        "choices": [
            {
                "candidate_index": 0,
                "category_label": "Response length",
                "value_label": "detailed",
            },
            {
                "candidate_index": 1,
                "category_label": "Explanation structure",
                "value_label": "step by step",
            },
        ],
        "expires_at": "2026-08-25T16:15:00Z",
    }


@pytest.mark.asyncio
async def test_run_turn_recovers_precompleted_proposal_without_new_tool_call(
) -> None:
    from datetime import UTC, datetime

    from schemas import AgentActionReceipt, MemoryProposalReceipt
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    action = AgentActionReceipt(
        action_name="propose_memory_signal",
        status="completed",
    )
    proposal = MemoryProposalReceipt(
        proposal_id="response_length--private-proposal",
        category="response_length",
        proposed_value="concise",
        expires_at=datetime(2026, 8, 22, 16, 0, tzinfo=UTC),
    )
    runner = FakeRunner(events=[FakeEvent("Proposal remains pending.", True)])
    runtime = SupervisorRuntime(
        runner=runner,
        session_service=FakeSessionService(),
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Remember my preference.",
            source_message_id="message-1",
            precompleted_actions=(action,),
            precompleted_memory_proposals=(proposal,),
        )
    )

    assert result.actions == (action,)
    assert result.memory_proposals == (proposal,)
    operational_context = runner.calls[0][
        "run_config"
    ].model_input_context[-1].parts[0].text
    assert "already completed" in operational_context
    assert "do not call propose_memory_signal" in operational_context
    assert "do not call propose_collaborative_note" in operational_context
    assert "response_length" in operational_context
    assert "concise" in operational_context
    assert "response_length--private-proposal" not in operational_context


@pytest.mark.asyncio
async def test_run_turn_collects_proposal_receipt_only_from_function_response(
) -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    pending_response = types.FunctionResponse(
        name="propose_memory_signal",
        response={
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
        },
    )
    sessions = FakeSessionService()
    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(
                    text="I will remember this.",
                    final=False,
                    function_responses=[pending_response],
                ),
                FakeEvent(text="Proposal is pending.", final=True),
            ]
        ),
        session_service=sessions,
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Remember that I prefer concise responses.",
        )
    )

    assert result.response == "Proposal is pending."
    assert [action.model_dump(mode="json") for action in result.actions] == [
        {
            "action_name": "propose_memory_signal",
            "status": "completed",
        }
    ]
    assert len(result.memory_proposals) == 1
    assert result.memory_proposals[0].proposal_id == (
        "response_length--e82366f7699ee2e39bff6a68154e09b7"
    )
    assert len(sessions.deleted) == 1


@pytest.mark.asyncio
async def test_run_turn_deduplicates_identical_proposal_responses() -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    response = pending_function_response()
    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(None, False, [response]),
                FakeEvent(None, False, [response]),
                FakeEvent("Proposal is pending.", True),
            ]
        ),
        session_service=FakeSessionService(),
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Remember my preference.",
        )
    )

    assert len(result.actions) == 1
    assert len(result.memory_proposals) == 1


@pytest.mark.asyncio
async def test_run_turn_rejects_distinct_proposal_responses() -> None:
    from supervisor_runtime import (
        SupervisorRuntime,
        SupervisorRuntimeError,
        SupervisorTurnContext,
    )

    sessions = FakeSessionService()
    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(None, False, [pending_function_response()]),
                FakeEvent(
                    None,
                    False,
                    [
                        pending_function_response(
                            origin_id="b" * 32,
                            proposed_value="detailed",
                        )
                    ],
                ),
                FakeEvent("Two proposals were created.", True),
            ]
        ),
        session_service=sessions,
    )

    with pytest.raises(SupervisorRuntimeError):
        await runtime.run_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Remember two preferences.",
            )
        )

    assert len(sessions.deleted) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "function_response",
    (
        types.FunctionResponse(
            name="propose_memory_signal",
            response={
                "status": "rejected",
                "error_code": "invalid_memory_candidate",
            },
        ),
        types.FunctionResponse(
            name="unrelated_tool",
            response={"private_payload": "must-be-ignored"},
        ),
    ),
)
async def test_run_turn_emits_no_receipt_for_rejected_or_unrelated_response(
    function_response: types.FunctionResponse,
) -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(None, False, [function_response]),
                FakeEvent("No memory proposal was created.", True),
            ]
        ),
        session_service=FakeSessionService(),
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Help with this task.",
        )
    )

    assert result.actions == ()
    assert result.memory_proposals == ()


@pytest.mark.asyncio
async def test_run_turn_translates_malformed_proposal_response_safely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from memory_proposal_tool import MemoryProposalToolResponseError
    from supervisor_runtime import (
        SupervisorRuntime,
        SupervisorRuntimeError,
        SupervisorTurnContext,
    )

    sessions = FakeSessionService()
    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(
                    None,
                    False,
                    [
                        types.FunctionResponse(
                            name="propose_memory_signal",
                            response={
                                "status": "rejected",
                                "error_code": "invalid_memory_candidate",
                                "private_payload": "must-not-leak",
                            },
                        )
                    ],
                )
            ]
        ),
        session_service=sessions,
    )
    caplog.set_level(logging.ERROR, logger="supervisor_runtime")

    with pytest.raises(SupervisorRuntimeError) as caught:
        await runtime.run_turn(
            SupervisorTurnContext(
                project_id="private-project",
                session_id="private-session",
                user_id="private-user",
                message="private-message",
            )
        )

    assert isinstance(caught.value.__cause__, MemoryProposalToolResponseError)
    assert len(sessions.deleted) == 1
    assert "MemoryProposalToolResponseError" in caplog.text
    for private_value in (
        "private-project",
        "private-session",
        "private-user",
        "private-message",
        "must-not-leak",
    ):
        assert private_value not in caplog.text


def test_runtime_constructs_from_real_adk_app_without_network() -> None:
    from supervisor import create_supervisor_app
    from supervisor_runtime import SupervisorRuntime
    from vertex_config import VertexAISettings

    app = create_supervisor_app(
        vertex_settings=VertexAISettings(
            project="project-1",
            location="global",
        )
    )

    assert SupervisorRuntime.from_app(app) is not None


@pytest.mark.asyncio
async def test_run_turn_never_reuses_an_adk_session() -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    sessions = FakeSessionService()
    runtime = SupervisorRuntime(
        runner=FakeRunner(events=[FakeEvent(text="Answer", final=True)]),
        session_service=sessions,
    )
    context = SupervisorTurnContext(
        project_id="project-1",
        session_id="session-1",
        user_id="user-1",
        message="Hello",
    )

    await runtime.run_turn(context)
    await runtime.run_turn(context)

    created = [item["session_id"] for item in sessions.created]
    deleted = [item["session_id"] for item in sessions.deleted]
    assert len(set(created)) == 2
    assert deleted == created


@pytest.mark.asyncio
async def test_run_turn_wraps_provider_error_and_cleans_session_safely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from supervisor_runtime import (
        SupervisorRuntime,
        SupervisorRuntimeError,
        SupervisorTurnContext,
    )

    provider_error = RuntimeError("provider echoed private-message")
    sessions = FakeSessionService()
    runtime = SupervisorRuntime(
        runner=FakeRunner(events=[], error=provider_error),
        session_service=sessions,
    )
    context = SupervisorTurnContext(
        project_id="private-project",
        session_id="private-session",
        user_id="private-user",
        message="private-message",
    )
    caplog.set_level(logging.ERROR, logger="supervisor_runtime")

    with pytest.raises(SupervisorRuntimeError) as caught:
        await runtime.run_turn(context)

    assert caught.value.__cause__ is provider_error
    assert len(sessions.deleted) == 1
    assert "RuntimeError" in caplog.text
    for private_value in (
        "private-project",
        "private-session",
        "private-user",
        "private-message",
        "provider echoed",
    ):
        assert private_value not in caplog.text


@pytest.mark.asyncio
async def test_provider_failure_after_proposal_carries_completed_receipts(
) -> None:
    from supervisor_runtime import (
        SupervisorRuntime,
        SupervisorRuntimeError,
        SupervisorTurnContext,
    )

    class ProposalThenFailureRunner(FakeRunner):
        async def run_async(
            self,
            **kwargs: object,
        ) -> AsyncIterator[FakeEvent]:
            self.calls.append(dict(kwargs))
            yield FakeEvent(None, False, [pending_function_response()])
            raise RuntimeError("private provider failure")

    runtime = SupervisorRuntime(
        runner=ProposalThenFailureRunner(events=[]),
        session_service=FakeSessionService(),
    )

    with pytest.raises(SupervisorRuntimeError) as caught:
        await runtime.run_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Remember my preference.",
            )
        )

    assert [item.action_name for item in caught.value.actions] == [
        "propose_memory_signal"
    ]
    assert [
        item.proposal_id for item in caught.value.memory_proposals
    ] == ["response_length--e82366f7699ee2e39bff6a68154e09b7"]


@pytest.mark.asyncio
async def test_timeout_after_proposal_carries_completed_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    import supervisor_runtime
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    class ProposalThenWaitRunner(FakeRunner):
        async def run_async(
            self,
            **kwargs: object,
        ) -> AsyncIterator[FakeEvent]:
            self.calls.append(dict(kwargs))
            yield FakeEvent(None, False, [pending_function_response()])
            await asyncio.Event().wait()

    runtime = SupervisorRuntime(
        runner=ProposalThenWaitRunner(events=[]),
        session_service=FakeSessionService(),
    )
    monkeypatch.setattr(
        supervisor_runtime,
        "SUPERVISOR_TIMEOUT_SECONDS",
        0.01,
    )

    with pytest.raises(supervisor_runtime.SupervisorTimeoutError) as caught:
        await asyncio.wait_for(
            runtime.run_turn(
                SupervisorTurnContext(
                    project_id="project-1",
                    session_id="session-1",
                    user_id="user-1",
                    message="Remember my preference.",
                )
            ),
            timeout=0.2,
        )

    assert [item.action_name for item in caught.value.actions] == [
        "propose_memory_signal"
    ]
    assert len(caught.value.memory_proposals) == 1


@pytest.mark.asyncio
async def test_run_turn_translates_timeout_and_cleans_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    import supervisor_runtime
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    class NeverReturningRunner(FakeRunner):
        async def run_async(
            self,
            **kwargs: object,
        ) -> AsyncIterator[FakeEvent]:
            self.calls.append(dict(kwargs))
            await asyncio.Event().wait()
            if False:
                yield FakeEvent(text=None, final=False)

    sessions = FakeSessionService()
    runtime = SupervisorRuntime(
        runner=NeverReturningRunner(events=[]),
        session_service=sessions,
    )
    context = SupervisorTurnContext(
        project_id="project-1",
        session_id="session-1",
        user_id="user-1",
        message="Hello",
    )
    monkeypatch.setattr(
        supervisor_runtime,
        "SUPERVISOR_TIMEOUT_SECONDS",
        0.01,
    )

    with pytest.raises(supervisor_runtime.SupervisorTimeoutError):
        await asyncio.wait_for(runtime.run_turn(context), timeout=0.2)

    assert len(sessions.deleted) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "events",
    (
        [],
        [FakeEvent(text=None, final=True)],
        [FakeEvent(text="   ", final=True)],
        [
            FakeEvent(text="First", final=True),
            FakeEvent(text="Second", final=True),
        ],
    ),
)
async def test_run_turn_requires_exactly_one_nonempty_final_response(
    events: list[FakeEvent],
) -> None:
    from supervisor_runtime import (
        SupervisorRuntime,
        SupervisorRuntimeError,
        SupervisorTurnContext,
    )

    sessions = FakeSessionService()
    runtime = SupervisorRuntime(
        runner=FakeRunner(events=events),
        session_service=sessions,
    )

    with pytest.raises(SupervisorRuntimeError):
        await runtime.run_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Hello",
            )
        )

    assert len(sessions.deleted) == 1


@pytest.mark.asyncio
async def test_run_turn_maps_grounded_research_without_child_final_ownership(
) -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    claim = "Python 3.14.7 is the current stable release."
    research_call = Event(
        author="Agent_Col",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id="research-call-1",
                        name="research_expert",
                        args={
                            "question": "What is the current Python release?",
                            "objective": "Establish the current release.",
                        },
                    )
                )
            ],
        ),
    )
    research_output = Event(
        author="research_expert",
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=claim)],
        ),
        output={
            "findings": [
                {
                    "claim": claim,
                    "evidence_summary": "Python.org supports the claim.",
                    "confidence": "high",
                }
            ]
        },
        grounding_metadata=types.GroundingMetadata(
            grounding_chunks=[
                types.GroundingChunk(
                    web=types.GroundingChunkWeb(
                        uri="https://www.python.org/downloads/",
                        title="Python downloads",
                    )
                )
            ],
            grounding_supports=[
                types.GroundingSupport(
                    segment=types.Segment(text=claim),
                    grounding_chunk_indices=[0],
                )
            ],
        ),
    )
    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                research_call,
                research_output,
                FakeEvent("Agent_Col grounded answer.", True),
            ]
        ),
        session_service=FakeSessionService(),
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="What is the current Python release?",
        )
    )

    assert result.response == "Agent_Col grounded answer."
    assert [action.model_dump(mode="json") for action in result.actions] == [
        {"action_name": "google_search", "status": "completed"}
    ]
    assert [
        citation.model_dump(mode="json") for citation in result.citations
    ] == [
        {
            "uri": "https://www.python.org/downloads/",
            "label": "Python downloads",
        }
    ]


@pytest.mark.asyncio
async def test_run_turn_maps_source_receipts_and_releases_turn_token() -> None:
    from expert_contracts import ExpertCapability
    from expert_delegation import (
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
        ExpertDelegationRegistry,
    )
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext
    from tests.test_source_expert_tool import completed_source_result

    source_response = types.FunctionResponse(
        name="analyze_source",
        response={
            "status": "completed",
            "result": completed_source_result().model_dump(mode="json"),
        },
    )
    sessions = FakeSessionService()
    registry = ExpertDelegationRegistry()
    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(None, False, [source_response]),
                FakeEvent(
                    "Agent_Col integrated source answer.",
                    True,
                ),
            ]
        ),
        session_service=sessions,
        delegation_registry=registry,
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Analyze https://example.com/.",
        )
    )

    assert result.response == "Agent_Col integrated source answer."
    assert [action.model_dump(mode="json") for action in result.actions] == [
        {"action_name": "url_context", "status": "completed"}
    ]
    assert [
        citation.model_dump(mode="json") for citation in result.citations
    ] == [
        {
            "uri": "https://example.com/",
            "label": "Example Domain",
        }
    ]
    token = sessions.created[0]["state"]["expert_delegation_token"]
    assert isinstance(token, str)
    with pytest.raises(ExpertDelegationDeniedError) as exc_info:
        await registry.claim(
            token,
            ExpertCapability.SOURCE,
            depth=1,
            minimum_remaining_seconds=1,
        )
    assert exc_info.value.reason is (
        ExpertDelegationDenialReason.TURN_NOT_REGISTERED
    )


@pytest.mark.asyncio
async def test_run_turn_contains_source_failure_without_receipts() -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    failure_response = types.FunctionResponse(
        name="analyze_source",
        response={
            "status": "unavailable",
            "message": "Source analysis could not be completed.",
        },
    )
    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(None, False, [failure_response]),
                FakeEvent("I could not verify that source.", True),
            ]
        ),
        session_service=FakeSessionService(),
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Analyze https://example.com/.",
        )
    )

    assert result.response == "I could not verify that source."
    assert result.actions == ()
    assert result.citations == ()


@pytest.mark.asyncio
async def test_run_turn_never_uses_source_tool_output_as_final_response(
) -> None:
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext
    from tests.test_source_expert_tool import completed_source_result

    source_response = types.FunctionResponse(
        name="analyze_source",
        response={
            "status": "completed",
            "result": completed_source_result().model_dump(mode="json"),
        },
    )
    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(
                    "Source tool internal output.",
                    True,
                    [source_response],
                    author="analyze_source",
                ),
                FakeEvent("Agent_Col final answer.", True),
            ]
        ),
        session_service=FakeSessionService(),
    )

    result = await runtime.run_turn(
        SupervisorTurnContext(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Analyze https://example.com/.",
        )
    )

    assert result.response == "Agent_Col final answer."


@pytest.mark.asyncio
async def test_run_turn_fails_closed_for_malformed_source_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from source_expert_runtime import SourceExpertRuntimeError
    from supervisor_runtime import (
        SupervisorRuntime,
        SupervisorRuntimeError,
        SupervisorTurnContext,
    )

    runtime = SupervisorRuntime(
        runner=FakeRunner(
            events=[
                FakeEvent(
                    None,
                    False,
                    [
                        types.FunctionResponse(
                            name="analyze_source",
                            response={
                                "status": "unavailable",
                                "message": (
                                    "Source analysis could not be completed."
                                ),
                                "private_detail": "must-not-leak",
                            },
                        )
                    ],
                )
            ]
        ),
        session_service=FakeSessionService(),
    )
    caplog.set_level(logging.ERROR, logger="supervisor_runtime")

    with pytest.raises(SupervisorRuntimeError) as exc_info:
        await runtime.run_turn(
            SupervisorTurnContext(
                project_id="private-project",
                session_id="private-session",
                user_id="private-user",
                message="private-message",
            )
        )

    assert isinstance(exc_info.value.__cause__, SourceExpertRuntimeError)
    assert "SourceExpertRuntimeError" in caplog.text
    for private_value in (
        "private-project",
        "private-session",
        "private-user",
        "private-message",
        "must-not-leak",
    ):
        assert private_value not in caplog.text


@pytest.mark.asyncio
async def test_run_turn_releases_delegation_token_after_cancellation() -> None:
    import asyncio

    from expert_contracts import ExpertCapability
    from expert_delegation import (
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
        ExpertDelegationRegistry,
    )
    from supervisor_runtime import SupervisorRuntime, SupervisorTurnContext

    started = asyncio.Event()

    class BlockingRunner(FakeRunner):
        async def run_async(
            self,
            **kwargs: object,
        ) -> AsyncIterator[FakeEvent]:
            self.calls.append(dict(kwargs))
            started.set()
            await asyncio.Event().wait()
            if False:
                yield FakeEvent(None, False)

    sessions = FakeSessionService()
    registry = ExpertDelegationRegistry()
    runtime = SupervisorRuntime(
        runner=BlockingRunner(events=[]),
        session_service=sessions,
        delegation_registry=registry,
    )
    task = asyncio.create_task(
        runtime.run_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Analyze https://example.com/.",
            )
        )
    )
    await asyncio.wait_for(started.wait(), timeout=0.2)
    token = sessions.created[0]["state"]["expert_delegation_token"]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    with pytest.raises(ExpertDelegationDeniedError) as exc_info:
        await registry.claim(
            token,
            ExpertCapability.SOURCE,
            depth=1,
            minimum_remaining_seconds=1,
        )
    assert exc_info.value.reason is (
        ExpertDelegationDenialReason.TURN_NOT_REGISTERED
    )
