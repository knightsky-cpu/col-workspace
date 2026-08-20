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
    def __init__(self, text: str | None, final: bool) -> None:
        parts = [] if text is None else [types.Part.from_text(text=text)]
        self.content = types.Content(role="model", parts=parts)
        self._final = final

    def is_final_response(self) -> bool:
        return self._final


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
