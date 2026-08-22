import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def write_fixture(path: Path, scenarios: list[dict[str, object]]) -> Path:
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


def test_default_fixture_covers_all_routing_directive_shapes() -> None:
    from smoke_test_agent_col_routing import (
        DEFAULT_ROUTING_COMPATIBILITY_FIXTURE,
        load_routing_compatibility_scenarios,
    )

    scenarios = load_routing_compatibility_scenarios(
        DEFAULT_ROUTING_COMPATIBILITY_FIXTURE
    )

    assert tuple(scenario.scenario_id for scenario in scenarios) == (
        "direct",
        "clarify",
        "source",
        "research",
    )
    assert tuple(scenario.expected_route for scenario in scenarios) == (
        "direct",
        "clarify",
        "source",
        "research",
    )
    assert len(scenarios[2].routing_input.candidate_urls) == 2


def test_fixture_rejects_duplicate_ids_and_extra_fields(tmp_path: Path) -> None:
    from pydantic import ValidationError

    from smoke_test_agent_col_routing import (
        load_routing_compatibility_scenarios,
    )

    fixture = write_fixture(
        tmp_path / "invalid.json",
        [
            {
                "scenario_id": "duplicate",
                "routing_input": {
                    "current_message": "Explain this.",
                },
                "expected_route": "direct",
            },
            {
                "scenario_id": "duplicate",
                "routing_input": {
                    "current_message": "Explain that.",
                },
                "expected_route": "direct",
                "unexpected": True,
            },
        ],
    )

    with pytest.raises(ValidationError):
        load_routing_compatibility_scenarios(fixture)


@pytest.mark.asyncio
async def test_runner_reports_valid_directives_without_executing_experts(
) -> None:
    from agent_col_routing import AgentColRoutingDirective
    from smoke_test_agent_col_routing import (
        load_routing_compatibility_scenarios,
        run_routing_compatibility,
    )

    scenarios = load_routing_compatibility_scenarios(
        Path("tests/fixtures/agent_col_routing_contract_cases.json")
    )
    decisions = {
        "direct": AgentColRoutingDirective(route="direct"),
        "clarify": AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Which public URL should I analyze?",
        ),
        "source": AgentColRoutingDirective(
            route="source",
            source_intent={
                "objective": "Compare both supplied pages.",
                "selected_url_ids": ("url-1", "url-2"),
            },
        ),
        "research": AgentColRoutingDirective(
            route="research",
            research_intent={
                "question": "What is the current stable Python release?",
                "objective": "Verify the current release.",
            },
        ),
    }
    calls: list[str] = []

    async def request(scenario: object, _repetition: int) -> object:
        scenario_id = scenario.scenario_id
        calls.append(scenario_id)
        return decisions[scenario_id]

    output: list[str] = []
    exit_code = await run_routing_compatibility(
        scenarios=scenarios,
        selected_scenario_id=None,
        repetitions=1,
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 0
    assert calls == ["direct", "clarify", "source", "research"]
    assert output == [
        "direct run=1 expected=direct actual=direct pass",
        "clarify run=1 expected=clarify actual=clarify pass",
        "source run=1 expected=source actual=source pass",
        "research run=1 expected=research actual=research pass",
    ]


@pytest.mark.asyncio
async def test_runner_distinguishes_mismatch_and_safe_execution_failures(
) -> None:
    from agent_col_routing import (
        AgentColRoutingDirective,
        RoutingDirectiveInputError,
    )
    from agent_col_routing_provider import (
        AgentColRoutingProviderError,
        AgentColRoutingProviderOutputError,
        AgentColRoutingProviderTimeoutError,
    )
    from smoke_test_agent_col_routing import (
        RoutingCompatibilityScenario,
        run_routing_compatibility,
    )

    scenario = RoutingCompatibilityScenario(
        scenario_id="safe-case",
        fixture_version="1.0",
        routing_input={"current_message": "Explain it."},
        expected_route="direct",
    )
    outcomes = (
        AgentColRoutingDirective(
            route="clarify",
            clarifying_question="What should I explain?",
        ),
        AgentColRoutingProviderError("private-provider-data"),
        AgentColRoutingProviderTimeoutError("private-timeout-data"),
        AgentColRoutingProviderOutputError("private-model-output"),
        RoutingDirectiveInputError("private-routing-input"),
    )

    async def request(_scenario: object, repetition: int) -> object:
        outcome = outcomes[repetition - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    output: list[str] = []
    exit_code = await run_routing_compatibility(
        scenarios=(scenario,),
        selected_scenario_id=None,
        repetitions=5,
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [
        "safe-case run=1 expected=direct actual=clarify route_mismatch",
        "safe-case run=2 provider_error",
        "safe-case run=3 timeout_error",
        "safe-case run=4 model_output_error",
        "safe-case run=5 directive_input_error",
    ]
    assert "private" not in " ".join(output)


@pytest.mark.asyncio
async def test_runner_rejects_invalid_selection_or_repetition_bounds() -> None:
    from smoke_test_agent_col_routing import (
        RoutingCompatibilityScenario,
        run_routing_compatibility,
    )

    scenario = RoutingCompatibilityScenario(
        scenario_id="only",
        fixture_version="1.0",
        routing_input={"current_message": "Explain it."},
        expected_route="direct",
    )

    async def request(_scenario: object, _repetition: int) -> object:
        raise AssertionError("Provider must not be called.")

    for selected, repetitions in (("missing", 1), (None, 0), (None, 6)):
        output: list[str] = []
        exit_code = await run_routing_compatibility(
            scenarios=(scenario,),
            selected_scenario_id=selected,
            repetitions=repetitions,
            request_directive=request,
            output=output.append,
        )
        assert exit_code == 2
        assert output == ["agent-col-routing-compatibility configuration_error"]


@pytest.mark.asyncio
async def test_live_runner_uses_vertex_adc_and_closes_client(
    tmp_path: Path,
) -> None:
    from smoke_test_agent_col_routing import run_live_routing_compatibility

    fixture = write_fixture(
        tmp_path / "routing.json",
        [
            {
                "scenario_id": "direct",
                "routing_input": {
                    "current_message": "Explain idempotency.",
                },
                "expected_route": "direct",
            }
        ],
    )

    class ClosableClient:
        def __init__(self) -> None:
            self.aio = SimpleNamespace(aclose=self.aclose)
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

    async def request_directive(
        _client: object,
        _routing_input: object,
    ) -> object:
        from agent_col_routing import AgentColRoutingDirective

        return AgentColRoutingDirective(route="direct")

    output: list[str] = []
    exit_code = await run_live_routing_compatibility(
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
        provider_request=request_directive,
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
        "direct run=1 expected=direct actual=direct pass",
    ]


def test_main_forwards_bounded_cli_options() -> None:
    from smoke_test_agent_col_routing import (
        DEFAULT_ROUTING_COMPATIBILITY_FIXTURE,
        main,
    )

    received: list[dict[str, object]] = []

    async def live_runner(**kwargs: object) -> int:
        received.append(kwargs)
        return 1

    exit_code = main(
        ["--scenario", "source", "--repetitions", "3"],
        live_runner=live_runner,
    )

    assert exit_code == 1
    assert received == [
        {
            "fixture_path": DEFAULT_ROUTING_COMPATIBILITY_FIXTURE,
            "selected_scenario_id": "source",
            "repetitions": 3,
            "output": print,
        }
    ]
