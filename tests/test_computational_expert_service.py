import importlib
import json
import asyncio
from collections.abc import AsyncIterator

import pytest
from google.adk.events import Event
from google.adk.workflow import NodeTimeoutError, Workflow
from google.genai import types

from computational_expert import (
    ComputationExpertInput,
    create_computational_expert_app,
)
from expert_contracts import ExpertStatus
from vertex_config import VertexAISettings


class RecordingSessions:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []
        self.deleted: list[dict[str, str]] = []

    async def create_session(self, **kwargs: str) -> None:
        self.created.append(kwargs)

    async def delete_session(self, **kwargs: str) -> None:
        self.deleted.append(kwargs)


class RecordingRunner:
    def __init__(self, events: tuple[Event, ...]) -> None:
        self.events = events
        self.calls: list[dict[str, object]] = []

    async def run_async(self, **kwargs: object) -> AsyncIterator[Event]:
        self.calls.append(kwargs)
        for event in self.events:
            yield event


class FailingRunner:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def run_async(self, **_: object) -> AsyncIterator[Event]:
        raise self.error
        yield


class BlockingRunner:
    async def run_async(self, **_: object) -> AsyncIterator[Event]:
        await asyncio.sleep(0.05)
        yield successful_event()


def load_service_module():
    try:
        return importlib.import_module("computational_expert_service")
    except ModuleNotFoundError:
        pytest.fail("computational_expert_service has not been implemented")


def valid_request() -> ComputationExpertInput:
    return ComputationExpertInput(
        objective="Calculate the arithmetic mean.",
        inputs={
            "series": [{"name": "values", "values": [1, 2, 3]}],
            "expression": "mean(values)",
        },
        required_precision={"mode": "decimal_places", "digits": 2},
    )


def successful_event() -> Event:
    return Event(
        author="computational_expert",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    executable_code=types.ExecutableCode(
                        language=types.Language.PYTHON,
                        code="values = [1, 2, 3]\nprint(sum(values) / 3)",
                    )
                ),
                types.Part(
                    code_execution_result=types.CodeExecutionResult(
                        outcome=types.Outcome.OUTCOME_OK,
                        output="2.0\n",
                    )
                ),
                types.Part.from_text(text="The arithmetic mean is 2.00."),
            ],
        ),
    )


@pytest.mark.asyncio
async def test_service_projects_exact_request_and_cleans_session() -> None:
    service_module = load_service_module()
    settings = VertexAISettings(project="project-1", location="global")
    app = create_computational_expert_app(settings)
    runner = RecordingRunner((successful_event(),))
    sessions = RecordingSessions()
    service = service_module.ComputationalExpertService(
        app=app,
        runner=runner,
        session_service=sessions,
    )
    request = valid_request()

    result = await service.compute(request)

    assert result.status is ExpertStatus.COMPLETED
    assert service.app is app
    assert len(sessions.created) == 1
    assert sessions.deleted == sessions.created
    session = sessions.created[0]
    assert session["app_name"] == "agent_col_computation"
    assert session["user_id"] == "computational_expert_service"
    assert session["session_id"]
    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["user_id"] == session["user_id"]
    assert call["session_id"] == session["session_id"]
    assert call["run_config"].max_llm_calls == 2
    message = call["new_message"]
    assert isinstance(message, types.Content)
    assert len(message.parts or ()) == 1
    assert json.loads(message.parts[0].text or "") == request.model_dump(
        mode="json"
    )


def test_service_constructs_the_accepted_isolated_workflow() -> None:
    service_module = load_service_module()

    service = service_module.ComputationalExpertService.from_vertex_settings(
        VertexAISettings(project="project-1", location="global")
    )

    assert service.app.name == "agent_col_computation"
    assert isinstance(service.app.root_agent, Workflow)
    assert service.app.root_agent.name == "computational_expert_workflow"


def test_service_rejects_nonpositive_timeout() -> None:
    service_module = load_service_module()

    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        service_module.ComputationalExpertService(
            app=create_computational_expert_app(
                VertexAISettings(project="project-1", location="global")
            ),
            runner=RecordingRunner(()),
            session_service=RecordingSessions(),
            timeout_seconds=0,
        )


@pytest.mark.asyncio
async def test_service_rejects_invalid_output_and_cleans_session() -> None:
    service_module = load_service_module()
    sessions = RecordingSessions()
    service = service_module.ComputationalExpertService(
        app=create_computational_expert_app(
            VertexAISettings(project="project-1", location="global")
        ),
        runner=RecordingRunner(
            (
                Event(
                    author="computational_expert",
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text="Plausible prose.")],
                    ),
                ),
            )
        ),
        session_service=sessions,
    )

    with pytest.raises(
        service_module.ComputationalExpertServiceError
    ) as exc_info:
        await service.compute(valid_request())

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT
    assert len(sessions.created) == 1
    assert sessions.deleted == sessions.created


@pytest.mark.asyncio
async def test_provider_failure_is_safe_unavailable_and_cleans_session(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service_module = load_service_module()
    sensitive_detail = "do-not-log-request-code-output-or-provider-payload"
    sessions = RecordingSessions()
    service = service_module.ComputationalExpertService(
        app=create_computational_expert_app(
            VertexAISettings(project="project-1", location="global")
        ),
        runner=FailingRunner(RuntimeError(sensitive_detail)),
        session_service=sessions,
    )

    with pytest.raises(
        service_module.ComputationalExpertServiceError
    ) as exc_info:
        await service.compute(valid_request())

    assert exc_info.value.status is ExpertStatus.UNAVAILABLE
    assert len(sessions.created) == 1
    assert sessions.deleted == sessions.created
    assert sensitive_detail not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_timeout_is_safe_timed_out_and_cleans_session(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service_module = load_service_module()
    sessions = RecordingSessions()
    service = service_module.ComputationalExpertService(
        app=create_computational_expert_app(
            VertexAISettings(project="project-1", location="global")
        ),
        runner=BlockingRunner(),
        session_service=sessions,
        timeout_seconds=0.001,
    )

    with pytest.raises(
        service_module.ComputationalExpertServiceError
    ) as exc_info:
        await service.compute(valid_request())

    assert exc_info.value.status is ExpertStatus.TIMED_OUT
    assert len(sessions.created) == 1
    assert sessions.deleted == sessions.created
    assert "TimeoutError" in caplog.text


@pytest.mark.asyncio
async def test_adk_node_timeout_is_translated_to_timed_out(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service_module = load_service_module()
    sessions = RecordingSessions()
    service = service_module.ComputationalExpertService(
        app=create_computational_expert_app(
            VertexAISettings(project="project-1", location="global")
        ),
        runner=FailingRunner(
            NodeTimeoutError(node_name="computational_expert", timeout=45)
        ),
        session_service=sessions,
    )

    with pytest.raises(
        service_module.ComputationalExpertServiceError
    ) as exc_info:
        await service.compute(valid_request())

    assert exc_info.value.status is ExpertStatus.TIMED_OUT
    assert sessions.deleted == sessions.created
    assert "NodeTimeoutError" in caplog.text
