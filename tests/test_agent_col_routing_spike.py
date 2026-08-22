import asyncio
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types
from pydantic import ValidationError


def test_module_entrypoint_follows_all_definitions() -> None:
    module_path = Path("agent_col_routing_spike.py")
    module = ast.parse(module_path.read_text(encoding="utf-8"))
    entrypoint_index = next(
        index
        for index, node in enumerate(module.body)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )

    assert not any(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        for node in module.body[entrypoint_index + 1 :]
    )


def test_route_decision_requires_question_only_for_clarification() -> None:
    from agent_col_routing_spike import AgentColRoutingDecision

    clarification = AgentColRoutingDecision(
        route="clarify",
        clarifying_question="Which part of the supplied page should I analyze?",
    )
    direct = AgentColRoutingDecision(route="direct")

    assert clarification.route == "clarify"
    assert direct.clarifying_question is None
    with pytest.raises(ValidationError):
        AgentColRoutingDecision(route="clarify")
    with pytest.raises(ValidationError):
        AgentColRoutingDecision(
            route="source",
            clarifying_question="This must not survive.",
        )
    with pytest.raises(ValidationError):
        AgentColRoutingDecision(
            route="direct",
            private_reasoning="must-not-load",
        )


class FakeRoutingModels:
    def __init__(
        self,
        *,
        response_text: str = '{"route":"source"}',
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.response_text = response_text
        self.error = error
        self.delay = delay
        self.calls: list[dict[str, object]] = []

    async def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.response_text)


def fake_routing_client(models: FakeRoutingModels) -> SimpleNamespace:
    return SimpleNamespace(aio=SimpleNamespace(models=models))


@pytest.mark.asyncio
async def test_decide_route_uses_tool_free_structured_vertex_request() -> None:
    from agent_col_routing_spike import (
        ROUTING_MODEL_NAME,
        decide_agent_col_route,
    )

    models = FakeRoutingModels()
    message = (
        "Analyze https://example.com/ and "
        "https://www.iana.org/help/example-domains."
    )

    decision = await decide_agent_col_route(
        fake_routing_client(models),
        message,
    )

    assert decision.route == "source"
    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == ROUTING_MODEL_NAME == "gemini-3.6-flash"
    assert len(call["contents"]) == 1
    content = call["contents"][0]
    assert isinstance(content, types.Content)
    prompt = content.parts[0].text
    assert prompt is not None
    assert "[UNTRUSTED_USER_REQUEST]" in prompt
    assert message in prompt
    assert "[/UNTRUSTED_USER_REQUEST]" in prompt
    config = call["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.temperature == 0
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema is not None
    assert config.response_schema is None
    assert not config.tools
    assert config.max_output_tokens == 256
    assert config.thinking_config == types.ThinkingConfig(
        thinking_level=types.ThinkingLevel.MINIMAL,
    )


@pytest.mark.asyncio
async def test_decide_route_contains_provider_failure() -> None:
    from agent_col_routing_spike import (
        AgentColRoutingSpikeError,
        decide_agent_col_route,
    )

    with pytest.raises(AgentColRoutingSpikeError) as exc_info:
        await decide_agent_col_route(
            fake_routing_client(
                FakeRoutingModels(
                    error=RuntimeError("private-provider-detail")
                )
            ),
            "private-request",
        )

    assert str(exc_info.value) == "Routing decision failed."
    assert "private" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_decide_route_has_distinct_timeout_failure() -> None:
    from agent_col_routing_spike import (
        AgentColRoutingSpikeTimeoutError,
        decide_agent_col_route,
    )

    with pytest.raises(AgentColRoutingSpikeTimeoutError):
        await decide_agent_col_route(
            fake_routing_client(FakeRoutingModels(delay=0.02)),
            "bounded request",
            timeout_seconds=0.001,
        )


def test_route_schema_is_provider_safe_and_locally_strict() -> None:
    from agent_col_routing_spike import build_routing_response_schema

    schema = build_routing_response_schema()

    assert schema["additionalProperties"] is False
    assert schema["properties"]["route"]["enum"] == [
        "direct",
        "clarify",
        "source",
        "research",
    ]
    assert "maxLength" not in json.dumps(schema)


def write_routing_fixture(
    path: Path,
    scenarios: list[dict[str, str]],
) -> Path:
    path.write_text(
        json.dumps(
            {
                "fixture_version": "1.0",
                "scenarios": scenarios,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_fixture_loader_returns_strict_versioned_scenarios(
    tmp_path: Path,
) -> None:
    from agent_col_routing_spike import load_routing_spike_scenarios

    fixture = write_routing_fixture(
        tmp_path / "routing.json",
        [
            {
                "scenario_id": "explicit-source",
                "message": "Analyze https://example.com/.",
                "expected_route": "source",
            }
        ],
    )

    scenarios = load_routing_spike_scenarios(fixture)

    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "explicit-source"
    assert scenarios[0].fixture_version == "1.0"
    assert scenarios[0].expected_route == "source"


@pytest.mark.parametrize("mutation", ("extra_field", "duplicate_id"))
def test_fixture_loader_rejects_untrusted_structure(
    tmp_path: Path,
    mutation: str,
) -> None:
    from agent_col_routing_spike import load_routing_spike_scenarios

    scenario = {
        "scenario_id": "ordinary",
        "message": "Explain idempotency.",
        "expected_route": "direct",
    }
    scenarios = [scenario]
    if mutation == "extra_field":
        scenario["private_profile"] = "must-not-load"
    else:
        scenarios.append(dict(scenario))
    fixture = write_routing_fixture(
        tmp_path / "routing.json",
        scenarios,
    )

    with pytest.raises(ValidationError):
        load_routing_spike_scenarios(fixture)


def test_evaluator_reports_only_route_mismatch() -> None:
    from agent_col_routing_spike import (
        AgentColRoutingDecision,
        RoutingSpikeScenario,
        evaluate_routing_decision,
    )

    scenario = RoutingSpikeScenario(
        scenario_id="explicit-source",
        fixture_version="1.0",
        message="private-message",
        expected_route="source",
    )

    assert evaluate_routing_decision(
        scenario,
        AgentColRoutingDecision(route="source"),
    ) == ()
    findings = evaluate_routing_decision(
        scenario,
        AgentColRoutingDecision(route="direct"),
    )
    assert tuple(finding.code for finding in findings) == (
        "route_mismatch",
    )


def test_default_fixture_covers_routing_spike_boundaries() -> None:
    from agent_col_routing_spike import (
        DEFAULT_ROUTING_SPIKE_FIXTURE_PATH,
        load_routing_spike_scenarios,
    )

    scenarios = load_routing_spike_scenarios(
        DEFAULT_ROUTING_SPIKE_FIXTURE_PATH
    )

    assert tuple(scenario.scenario_id for scenario in scenarios) == (
        "explicit-single-url",
        "explicit-multiple-urls",
        "stable-no-url",
        "incidental-url",
        "explicit-no-tools-with-url",
        "ambiguous-url",
        "current-public-fact",
    )
    assert tuple(scenario.expected_route for scenario in scenarios) == (
        "source",
        "source",
        "direct",
        "direct",
        "direct",
        "clarify",
        "research",
    )


@pytest.mark.asyncio
async def test_runner_distinguishes_route_and_provider_failures() -> None:
    import agent_col_routing_spike as module

    scenarios = (
        module.RoutingSpikeScenario(
            "source-case",
            "1.0",
            "private source request",
            "source",
        ),
        module.RoutingSpikeScenario(
            "direct-case",
            "1.0",
            "private direct request",
            "direct",
        ),
        module.RoutingSpikeScenario(
            "provider-case",
            "1.0",
            "private provider request",
            "direct",
        ),
    )
    results = iter(
        (
            module.AgentColRoutingDecision(route="source"),
            module.AgentColRoutingDecision(route="source"),
            module.AgentColRoutingSpikeError("private provider detail"),
        )
    )

    async def request_decision(
        _scenario: module.RoutingSpikeScenario,
        _repetition: int,
    ) -> module.AgentColRoutingDecision:
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    output: list[str] = []
    exit_code = await module.run_routing_spike(
        scenarios=scenarios,
        selected_scenario_id=None,
        repetitions=1,
        request_decision=request_decision,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [
        "source-case run=1 expected=source actual=source pass",
        "direct-case run=1 expected=direct actual=source route_mismatch",
        "provider-case run=1 provider_error",
    ]
    assert "private" not in " ".join(output)


@pytest.mark.asyncio
async def test_runner_distinguishes_invalid_model_output() -> None:
    import agent_col_routing_spike as module

    scenario = module.RoutingSpikeScenario(
        "source-case",
        "1.0",
        "private source request",
        "source",
    )
    models = FakeRoutingModels(response_text="not-json")

    async def request_decision(
        _scenario: module.RoutingSpikeScenario,
        _repetition: int,
    ) -> module.AgentColRoutingDecision:
        return await module.decide_agent_col_route(
            fake_routing_client(models),
            "private source request",
        )

    output: list[str] = []
    exit_code = await module.run_routing_spike(
        scenarios=(scenario,),
        selected_scenario_id=None,
        repetitions=1,
        request_decision=request_decision,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["source-case run=1 model_output_error"]
    assert "private" not in " ".join(output)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repetitions", "selected_scenario_id"),
    ((0, None), (11, None), (1, "missing-scenario")),
)
async def test_runner_rejects_invalid_configuration_before_provider_calls(
    repetitions: int,
    selected_scenario_id: str | None,
) -> None:
    from agent_col_routing_spike import (
        AgentColRoutingDecision,
        RoutingSpikeScenario,
        run_routing_spike,
    )

    async def request_decision(
        _scenario: RoutingSpikeScenario,
        _repetition: int,
    ) -> AgentColRoutingDecision:
        raise AssertionError("invalid configuration must make no request")

    output: list[str] = []
    exit_code = await run_routing_spike(
        scenarios=(
            RoutingSpikeScenario(
                "ordinary",
                "1.0",
                "Explain idempotency.",
                "direct",
            ),
        ),
        selected_scenario_id=selected_scenario_id,
        repetitions=repetitions,
        request_decision=request_decision,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["agent-col-routing-spike configuration_error"]


@pytest.mark.asyncio
async def test_fixture_runner_contains_invalid_fixture() -> None:
    from agent_col_routing_spike import run_routing_spike_fixture

    output: list[str] = []
    exit_code = await run_routing_spike_fixture(
        fixture_path=Path("missing-private-fixture.json"),
        selected_scenario_id=None,
        repetitions=1,
        request_decision=lambda _scenario, _repetition: None,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["agent-col-routing-spike configuration_error"]


def test_main_forwards_cli_options() -> None:
    from agent_col_routing_spike import main

    received: list[dict[str, object]] = []

    async def fixture_runner(**kwargs: object) -> int:
        received.append(kwargs)
        return 1

    exit_code = main(
        [
            "--scenario",
            "explicit-multiple-urls",
            "--repetitions",
            "7",
        ],
        live_runner=fixture_runner,
    )

    assert exit_code == 1
    assert len(received) == 1
    assert received[0]["selected_scenario_id"] == (
        "explicit-multiple-urls"
    )
    assert received[0]["repetitions"] == 7


@pytest.mark.asyncio
async def test_live_runner_uses_vertex_client_and_closes_resources(
    tmp_path: Path,
) -> None:
    from agent_col_routing_spike import run_live_routing_spike

    fixture = write_routing_fixture(
        tmp_path / "routing.json",
        [
            {
                "scenario_id": "ordinary",
                "message": "Explain idempotency.",
                "expected_route": "direct",
            }
        ],
    )
    models = FakeRoutingModels(response_text='{\"route\":\"direct\"}')

    class ClosableClient:
        def __init__(self) -> None:
            self.aio = SimpleNamespace(
                models=models,
                aclose=self.aclose,
            )
            self.async_closed = False
            self.closed = False

        async def aclose(self) -> None:
            self.async_closed = True

        def close(self) -> None:
            self.closed = True

    client = ClosableClient()
    client_arguments: list[dict[str, object]] = []

    def client_factory(**kwargs: object) -> ClosableClient:
        client_arguments.append(kwargs)
        return client

    output: list[str] = []
    exit_code = await run_live_routing_spike(
        fixture_path=fixture,
        selected_scenario_id=None,
        repetitions=1,
        output=output.append,
        environment={
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        },
        client_factory=client_factory,
    )

    assert exit_code == 0
    assert client_arguments == [
        {
            "enterprise": True,
            "project": "project-1",
            "location": "global",
        }
    ]
    assert client.async_closed is True
    assert client.closed is True
    assert output == [
        "ordinary run=1 expected=direct actual=direct pass"
    ]
