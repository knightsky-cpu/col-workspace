import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def write_fixture(path: Path, scenarios: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"fixture_version": "2.0", "scenarios": scenarios}),
        encoding="utf-8",
    )
    return path


def test_default_v2_fixture_covers_all_routes_and_exact_numeric_provenance(
) -> None:
    from smoke_test_agent_col_routing_v2 import (
        DEFAULT_ROUTING_V2_COMPATIBILITY_FIXTURE,
        load_routing_v2_compatibility_scenarios,
    )

    scenarios = load_routing_v2_compatibility_scenarios(
        DEFAULT_ROUTING_V2_COMPATIBILITY_FIXTURE
    )

    assert tuple(scenario.scenario_id for scenario in scenarios) == (
        "direct-restraint",
        "clarify-unsupported-fraction",
        "source-regression",
        "research-regression",
        "computation-series",
    )
    assert tuple(scenario.expected_route for scenario in scenarios) == (
        "direct",
        "clarify",
        "source",
        "research",
        "computation",
    )
    computation_input = scenarios[-1].routing_input
    assert tuple(
        candidate.candidate_id
        for candidate in computation_input.numeric_candidates
    ) == tuple(f"number-{index}" for index in range(1, 7))
    assert tuple(
        candidate.raw_text
        for candidate in computation_input.numeric_candidates
    ) == ("12", "15", "18", "21", "24", "27")


def test_v2_fixture_rejects_duplicate_ids_and_extra_fields(
    tmp_path: Path,
) -> None:
    from pydantic import ValidationError

    from smoke_test_agent_col_routing_v2 import (
        load_routing_v2_compatibility_scenarios,
    )

    fixture = write_fixture(
        tmp_path / "invalid.json",
        [
            {
                "scenario_id": "duplicate",
                "routing_input": {"current_message": "Explain this."},
                "expected_route": "direct",
            },
            {
                "scenario_id": "duplicate",
                "routing_input": {"current_message": "Explain that."},
                "expected_route": "direct",
                "unexpected": True,
            },
        ],
    )

    with pytest.raises(ValidationError):
        load_routing_v2_compatibility_scenarios(fixture)


@pytest.mark.asyncio
async def test_v2_runner_reports_routes_without_executing_experts() -> None:
    from agent_col_routing_v2 import AgentColRoutingDirective
    from smoke_test_agent_col_routing_v2 import (
        DEFAULT_ROUTING_V2_COMPATIBILITY_FIXTURE,
        load_routing_v2_compatibility_scenarios,
        run_routing_v2_compatibility,
    )

    scenarios = load_routing_v2_compatibility_scenarios(
        DEFAULT_ROUTING_V2_COMPATIBILITY_FIXTURE
    )
    decisions = {
        "direct-restraint": AgentColRoutingDirective(route="direct"),
        "clarify-unsupported-fraction": AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Please restate the fraction as a decimal.",
        ),
        "source-regression": AgentColRoutingDirective(
            route="source",
            source_intent={
                "objective": "Analyze the supplied page.",
                "selected_url_ids": ["url-1"],
            },
        ),
        "research-regression": AgentColRoutingDirective(
            route="research",
            research_intent={
                "question": "What is the current stable Python release?",
                "objective": "Verify it using current public evidence.",
            },
        ),
        "computation-series": AgentColRoutingDirective(
            route="computation",
            computation_intent={
                "objective": "Calculate the requested descriptive statistics.",
                "series_inputs": [
                    {
                        "name": "values",
                        "numeric_ids": [
                            "number-1",
                            "number-2",
                            "number-3",
                            "number-4",
                            "number-5",
                            "number-6",
                        ],
                    }
                ],
            },
        ),
    }
    calls: list[str] = []

    async def request(scenario: object, _repetition: int) -> object:
        calls.append(scenario.scenario_id)
        return decisions[scenario.scenario_id]

    output: list[str] = []
    exit_code = await run_routing_v2_compatibility(
        scenarios=scenarios,
        selected_scenario_id=None,
        repetitions=1,
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 0
    assert calls == list(decisions)
    assert output == [
        "direct-restraint run=1 expected=direct actual=direct pass",
        "clarify-unsupported-fraction run=1 expected=clarify actual=clarify pass",
        "source-regression run=1 expected=source actual=source pass",
        "research-regression run=1 expected=research actual=research pass",
        "computation-series run=1 expected=computation actual=computation pass",
    ]


@pytest.mark.asyncio
async def test_v2_runner_distinguishes_mismatch_and_safe_failures() -> None:
    from agent_col_routing_provider_v2 import (
        AgentColRoutingV2ProviderError,
        AgentColRoutingV2ProviderOutputError,
        AgentColRoutingV2ProviderTimeoutError,
    )
    from agent_col_routing_v2 import (
        AgentColRoutingDirective,
        RoutingDirectiveInputError,
    )
    from smoke_test_agent_col_routing_v2 import (
        RoutingV2CompatibilityScenario,
        run_routing_v2_compatibility,
    )

    scenario = RoutingV2CompatibilityScenario(
        scenario_id="safe-case",
        fixture_version="2.0",
        routing_input={"current_message": "Explain it."},
        expected_route="direct",
    )
    outcomes = (
        AgentColRoutingDirective(
            route="clarify",
            clarifying_question="What should I explain?",
        ),
        AgentColRoutingV2ProviderError("private-provider-data"),
        AgentColRoutingV2ProviderTimeoutError("private-timeout-data"),
        AgentColRoutingV2ProviderOutputError("private-model-output"),
        RoutingDirectiveInputError("private-routing-input"),
    )

    async def request(_scenario: object, repetition: int) -> object:
        outcome = outcomes[repetition - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    output: list[str] = []
    exit_code = await run_routing_v2_compatibility(
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
async def test_v2_runner_rejects_invalid_selection_or_repetitions() -> None:
    from smoke_test_agent_col_routing_v2 import (
        RoutingV2CompatibilityScenario,
        run_routing_v2_compatibility,
    )

    scenario = RoutingV2CompatibilityScenario(
        scenario_id="only",
        fixture_version="2.0",
        routing_input={"current_message": "Explain it."},
        expected_route="direct",
    )

    async def request(_scenario: object, _repetition: int) -> object:
        raise AssertionError("Provider must not be called.")

    for selected, repetitions in (("missing", 1), (None, 0), (None, 6)):
        output: list[str] = []
        exit_code = await run_routing_v2_compatibility(
            scenarios=(scenario,),
            selected_scenario_id=selected,
            repetitions=repetitions,
            request_directive=request,
            output=output.append,
        )
        assert exit_code == 2
        assert output == [
            "agent-col-routing-v2-compatibility configuration_error"
        ]


@pytest.mark.asyncio
async def test_v2_live_runner_uses_vertex_adc_and_closes_client(
    tmp_path: Path,
) -> None:
    from smoke_test_agent_col_routing_v2 import (
        run_live_routing_v2_compatibility,
    )

    fixture = write_fixture(
        tmp_path / "routing-v2.json",
        [
            {
                "scenario_id": "direct",
                "routing_input": {"current_message": "Explain idempotency."},
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
        from agent_col_routing_v2 import AgentColRoutingDirective

        return AgentColRoutingDirective(route="direct")

    output: list[str] = []
    exit_code = await run_live_routing_v2_compatibility(
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


def test_v2_main_forwards_bounded_cli_options() -> None:
    from smoke_test_agent_col_routing_v2 import (
        DEFAULT_ROUTING_V2_COMPATIBILITY_FIXTURE,
        main,
    )

    received: list[dict[str, object]] = []

    async def live_runner(**kwargs: object) -> int:
        received.append(kwargs)
        return 1

    exit_code = main(
        ["--scenario", "computation-series", "--repetitions", "3"],
        live_runner=live_runner,
    )

    assert exit_code == 1
    assert received == [
        {
            "fixture_path": DEFAULT_ROUTING_V2_COMPATIBILITY_FIXTURE,
            "selected_scenario_id": "computation-series",
            "repetitions": 3,
            "output": print,
        }
    ]
