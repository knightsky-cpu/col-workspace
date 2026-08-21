from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import logging
from types import SimpleNamespace

import pytest
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
    ) -> None:
        parts = [] if text is None else [types.Part.from_text(text=text)]
        self.content = types.Content(role="model", parts=parts)
        self._final = final
        self._function_responses = function_responses or []

    def is_final_response(self) -> bool:
        return self._final

    def get_function_responses(self) -> list[types.FunctionResponse]:
        return list(self._function_responses)


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


@dataclass
class FakeRunner:
    events: list[FakeEvent]
    calls: list[dict[str, object]] = field(default_factory=list)
    error: Exception | None = None

    async def run_async(self, **kwargs: object) -> AsyncIterator[FakeEvent]:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        for event in self.events:
            yield event


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
    assert created["state"] == {
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

    assert sessions.created[0]["state"] == {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "memory_user_id": "user-1",
        "memory_session_id": "session-1",
        "memory_source_message_id": "turn--source-message--user",
        "memory_source_message_text": (
            "Remember that I prefer concise responses."
        ),
        "memory_decision_present": False,
        "memory_turn_id": "a" * 64,
        "memory_turn_owner_token": "owner-token-1",
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
        proposal_id="response_length--proposal-1",
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
    assert "response_length--proposal-1" in operational_context


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

    assert SupervisorRuntime.from_app(create_supervisor_app()) is not None


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
