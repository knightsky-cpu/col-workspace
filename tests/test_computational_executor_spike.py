import importlib
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.events import Event
from google.adk.models import Gemini
from google.adk.workflow import Workflow
from google.genai import types

from vertex_config import VertexAISettings


SPIKE_AGENT_NAME = "computational_executor_spike"


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


def load_spike_module():
    try:
        return importlib.import_module("computational_executor_spike")
    except ModuleNotFoundError:
        pytest.fail("computational_executor_spike has not been implemented")


def model_event(*parts: types.Part) -> Event:
    return Event(
        author=SPIKE_AGENT_NAME,
        content=types.Content(role="model", parts=list(parts)),
    )


def test_prose_only_response_has_no_trustworthy_execution_evidence() -> None:
    spike = load_spike_module()

    result = spike.normalize_execution_events(
        (model_event(types.Part.from_text(text="The answer is 42.")),)
    )

    assert result.status is spike.SpikeStatus.NO_EXECUTION_EVIDENCE
    assert result.execution_count == 0
    assert result.successful_execution_count == 0
    assert result.exit_code == 1


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    (
        (types.Outcome.OUTCOME_FAILED, "execution_failed"),
        (
            types.Outcome.OUTCOME_DEADLINE_EXCEEDED,
            "execution_deadline_exceeded",
        ),
    ),
)
def test_failed_or_deadline_execution_does_not_complete(
    outcome: types.Outcome,
    expected_status: str,
) -> None:
    spike = load_spike_module()

    result = spike.normalize_execution_events(
        (
            model_event(
                types.Part(
                    executable_code=types.ExecutableCode(
                        language=types.Language.PYTHON,
                        code="print(42)",
                    )
                ),
                types.Part(
                    code_execution_result=types.CodeExecutionResult(
                        outcome=outcome,
                        output="provider execution did not complete",
                    )
                ),
            ),
        )
    )

    assert result.status.value == expected_status
    assert result.execution_count == 1
    assert result.successful_execution_count == 0
    assert result.exit_code == 1


def test_any_failed_execution_prevents_mixed_run_from_completing() -> None:
    spike = load_spike_module()

    result = spike.normalize_execution_events(
        (
            model_event(
                types.Part(
                    executable_code=types.ExecutableCode(
                        language=types.Language.PYTHON,
                        code="raise RuntimeError()",
                    )
                ),
                types.Part(
                    code_execution_result=types.CodeExecutionResult(
                        outcome=types.Outcome.OUTCOME_FAILED,
                        output="RuntimeError",
                    )
                ),
                types.Part(
                    executable_code=types.ExecutableCode(
                        language=types.Language.PYTHON,
                        code="print(42)",
                    )
                ),
                types.Part(
                    code_execution_result=types.CodeExecutionResult(
                        outcome=types.Outcome.OUTCOME_OK,
                        output="42\n",
                    )
                ),
            ),
        )
    )

    assert result.status is spike.SpikeStatus.EXECUTION_FAILED
    assert result.execution_count == 2
    assert result.successful_execution_count == 0
    assert result.exit_code == 1


@pytest.mark.parametrize(
    ("code", "output"),
    (
        ("x" * 8_001, "42"),
        ("print(42)", "x" * 8_001),
    ),
)
def test_oversized_code_or_output_is_rejected(
    code: str,
    output: str,
) -> None:
    spike = load_spike_module()

    result = spike.normalize_execution_events(
        (
            model_event(
                types.Part(
                    executable_code=types.ExecutableCode(
                        language=types.Language.PYTHON,
                        code=code,
                    )
                ),
                types.Part(
                    code_execution_result=types.CodeExecutionResult(
                        outcome=types.Outcome.OUTCOME_OK,
                        output=output,
                    )
                ),
            ),
        )
    )

    assert result.status is spike.SpikeStatus.INVALID_EXECUTION_EVIDENCE
    assert result.execution_count == 1
    assert result.successful_execution_count == 0
    assert result.exit_code == 1


def test_successful_python_execution_produces_content_safe_evidence() -> None:
    spike = load_spike_module()
    code = "values = [2, 4, 6]\nprint(sum(values) / len(values))"
    output = "4.0\n"

    result = spike.normalize_execution_events(
        (
            model_event(
                types.Part(
                    executable_code=types.ExecutableCode(
                        language=types.Language.PYTHON,
                        code=code,
                    )
                ),
                types.Part(
                    code_execution_result=types.CodeExecutionResult(
                        outcome=types.Outcome.OUTCOME_OK,
                        output=output,
                    )
                ),
                types.Part.from_text(text="The computed mean is 4.0."),
            ),
        )
    )

    assert result.status is spike.SpikeStatus.COMPLETED
    assert result.execution_count == 1
    assert result.successful_execution_count == 1
    assert result.code_character_count == len(code)
    assert result.output_character_count == len(output)
    assert result.observed_outcomes == ("OUTCOME_OK",)
    assert result.exit_code == 0
    assert code not in repr(result)
    assert output not in repr(result)


def test_spike_agent_uses_exact_isolated_vertex_code_executor_topology(
) -> None:
    spike = load_spike_module()

    agent = spike.create_spike_agent(
        VertexAISettings(project="project-1", location="global")
    )

    assert agent.name == SPIKE_AGENT_NAME
    assert agent.mode == "single_turn"
    assert isinstance(agent.model, Gemini)
    assert agent.model.model == "gemini-3.6-flash"
    assert agent.model.client_kwargs == {
        "enterprise": True,
        "project": "project-1",
        "location": "global",
    }
    assert isinstance(agent.code_executor, BuiltInCodeExecutor)
    assert agent.code_executor.timeout_seconds == 30
    assert agent.tools == []
    assert agent.sub_agents == []
    assert agent.disallow_transfer_to_parent is True
    assert agent.disallow_transfer_to_peers is True
    assert agent.include_contents == "none"
    assert agent.output_schema is None
    assert "Do not access files" in agent.instruction
    assert "Do not access the network" in agent.instruction


@pytest.mark.asyncio
async def test_live_spike_collects_native_events_and_deletes_session() -> None:
    spike = load_spike_module()
    event = model_event(
        types.Part(
            executable_code=types.ExecutableCode(
                language=types.Language.PYTHON,
                code="print(4.0)",
            )
        ),
        types.Part(
            code_execution_result=types.CodeExecutionResult(
                outcome=types.Outcome.OUTCOME_OK,
                output="4.0\n",
            )
        ),
    )
    runner = RecordingRunner((event,))
    sessions = RecordingSessions()

    result = await spike.run_live_spike(
        VertexAISettings(project="project-1", location="global"),
        runner=runner,
        session_service=sessions,
        invocation_id_factory=lambda: "invocation-1",
    )

    assert result.status is spike.SpikeStatus.COMPLETED
    expected_session = {
        "app_name": "agent_col_computational_executor_spike",
        "user_id": "computational_executor_spike_service",
        "session_id": "invocation-1",
    }
    assert sessions.created == [expected_session]
    assert sessions.deleted == [expected_session]
    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["user_id"] == expected_session["user_id"]
    assert call["session_id"] == expected_session["session_id"]
    assert call["run_config"].max_llm_calls == 2
    message = call["new_message"]
    assert isinstance(message, types.Content)
    assert len(message.parts or ()) == 1
    prompt = message.parts[0].text or ""
    assert "[12, 15, 18, 21, 24, 27]" in prompt
    assert "Python" in prompt


@pytest.mark.asyncio
async def test_default_live_spike_wraps_single_turn_agent_in_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spike = load_spike_module()
    sessions = RecordingSessions()
    runner = RecordingRunner(())
    observed: dict[str, object] = {}

    def build_sessions() -> RecordingSessions:
        return sessions

    def build_runner(*, app: object, session_service: object):
        observed["app"] = app
        observed["session_service"] = session_service
        return runner

    monkeypatch.setattr(spike, "InMemorySessionService", build_sessions)
    monkeypatch.setattr(spike, "Runner", build_runner)

    await spike.run_live_spike(
        VertexAISettings(project="project-1", location="global"),
        invocation_id_factory=lambda: "invocation-1",
    )

    app = observed["app"]
    assert app.name == "agent_col_computational_executor_spike"
    assert isinstance(app.root_agent, Workflow)
    assert app.root_agent.name == "computational_executor_spike_workflow"
    assert app.root_agent.graph is not None
    assert len(app.root_agent.graph.edges) == 1
    edge = app.root_agent.graph.edges[0]
    assert edge.from_node.name == "__START__"
    assert edge.to_node.name == SPIKE_AGENT_NAME
    assert edge.to_node.mode == "single_turn"
    assert observed["session_service"] is sessions


def test_cli_returns_two_for_configuration_error_without_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    spike = load_spike_module()
    sensitive_project = "do-not-print-project"

    exit_code = spike.main(
        environment={
            "GOOGLE_CLOUD_PROJECT": sensitive_project,
            "GOOGLE_CLOUD_LOCATION": "wrong-region",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        }
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == "computational-executor-spike configuration_error\n"
    assert captured.err == ""
    assert sensitive_project not in captured.out


def test_cli_returns_normalized_exit_and_content_safe_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    spike = load_spike_module()
    code = "print('sensitive code')"
    output = "sensitive output"

    async def completed_runner(
        settings: VertexAISettings,
    ):
        assert settings.project == "project-1"
        return spike.normalize_execution_events(
            (
                model_event(
                    types.Part(
                        executable_code=types.ExecutableCode(
                            language=types.Language.PYTHON,
                            code=code,
                        )
                    ),
                    types.Part(
                        code_execution_result=types.CodeExecutionResult(
                            outcome=types.Outcome.OUTCOME_OK,
                            output=output,
                        )
                    ),
                ),
            )
        )

    exit_code = spike.main(
        environment={
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        },
        live_runner=completed_runner,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == (
        "computational-executor-spike completed executions=1 "
        "successful=1 code_chars=23 output_chars=16 "
        "outcomes=OUTCOME_OK\n"
    )
    assert captured.err == ""
    assert code not in captured.out
    assert output not in captured.out


def test_cli_returns_two_for_provider_error_without_exception_content(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    spike = load_spike_module()
    sensitive_detail = "do-not-log-provider-payload"

    async def failing_runner(_: VertexAISettings):
        raise RuntimeError(sensitive_detail)

    exit_code = spike.main(
        environment={
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        },
        live_runner=failing_runner,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == "computational-executor-spike provider_error\n"
    assert captured.err == ""
    assert sensitive_detail not in captured.out
    assert sensitive_detail not in caplog.text
    assert "RuntimeError" in caplog.text


def test_script_entrypoint_returns_cli_exit_code() -> None:
    environment = {
        "PATH": "/usr/bin:/bin",
        "GOOGLE_CLOUD_PROJECT": "project-1",
        "GOOGLE_CLOUD_LOCATION": "wrong-region",
        "GOOGLE_GENAI_USE_ENTERPRISE": "True",
    }
    completed = subprocess.run(
        [sys.executable, "computational_executor_spike.py"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 2
    assert completed.stdout == (
        "computational-executor-spike configuration_error\n"
    )
    assert completed.stderr == ""


def test_cli_loads_repository_dotenv_before_live_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spike = load_spike_module()
    for name in (
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_GENAI_USE_ENTERPRISE",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "GOOGLE_CLOUD_PROJECT=project-from-dotenv\n"
        "GOOGLE_CLOUD_LOCATION=global\n"
        "GOOGLE_GENAI_USE_ENTERPRISE=True\n",
        encoding="utf-8",
    )

    async def no_evidence_runner(settings: VertexAISettings):
        assert settings.project == "project-from-dotenv"
        return spike.normalize_execution_events(())

    exit_code = spike.main(
        dotenv_path=tmp_path / ".env",
        live_runner=no_evidence_runner,
    )

    assert exit_code == 1
    assert capsys.readouterr().out.startswith(
        "computational-executor-spike no_execution_evidence"
    )
