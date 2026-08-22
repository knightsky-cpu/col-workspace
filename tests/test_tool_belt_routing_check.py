import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_check_module():
    try:
        return importlib.import_module("tool_belt_routing_check")
    except ModuleNotFoundError:
        pytest.fail("tool_belt_routing_check has not been implemented")


def write_fixture(path: Path, scenarios: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"fixture_version": "1.0", "scenarios": scenarios}),
        encoding="utf-8",
    )
    return path


def direct_definition(scenario_id: str = "direct-case") -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "message": "Explain idempotency in stable general terms.",
        "expected_route": "direct",
        "expected_url_ids": [],
        "expected_scalar_numeric_ids": [],
        "expected_series_numeric_ids": [],
        "expected_precision_numeric_id": None,
        "manual_semantic_review": "none",
    }


def source_definition() -> dict[str, object]:
    return {
        "scenario_id": "source-case",
        "message": "Analyze https://example.com/ using only that page.",
        "expected_route": "source",
        "expected_url_ids": ["url-1"],
        "expected_scalar_numeric_ids": [],
        "expected_series_numeric_ids": [],
        "expected_precision_numeric_id": None,
        "manual_semantic_review": "none",
    }


@pytest.mark.asyncio
async def test_decision_check_reports_pass_and_manual_review_without_content(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_v2 import AgentColRoutingDirective
    from tool_belt_routing_evaluation import load_tool_belt_routing_scenarios

    clarification = direct_definition("clarify-case")
    clarification.update(
        {
            "message": "Calculate the percentage change for my results.",
            "expected_route": "clarify",
            "manual_semantic_review": "clarification_quality",
        }
    )
    fixture = write_fixture(
        tmp_path / "routing.json",
        [direct_definition(), clarification],
    )
    scenarios = load_tool_belt_routing_scenarios(fixture)

    async def request_directive(scenario, _repetition: int):
        if scenario.expected_route == "clarify":
            return AgentColRoutingDirective(
                route="clarify",
                clarifying_question="Which values should I compare?",
            )
        return AgentColRoutingDirective(route="direct")

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=None,
        repetitions=1,
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 0
    assert output == [
        "direct-case run=1 expected=direct actual=direct pass",
        (
            "clarify-case run=1 expected=clarify actual=clarify pass "
            "manual_review_required"
        ),
    ]
    assert all("idempotency" not in line for line in output)
    assert all("Which values" not in line for line in output)


@pytest.mark.asyncio
async def test_decision_check_distinguishes_quality_and_provider_failures(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_provider_v2 import (
        AgentColRoutingV2InvalidOutputReason,
        AgentColRoutingV2ProviderOutputError,
        AgentColRoutingV2SchemaFailureReason,
    )
    from agent_col_routing_v2 import AgentColRoutingDirective
    from tool_belt_routing_evaluation import load_tool_belt_routing_scenarios

    fixture = write_fixture(
        tmp_path / "routing.json",
        [direct_definition("quality-case"), direct_definition("provider-case")],
    )
    scenarios = load_tool_belt_routing_scenarios(fixture)

    async def request_directive(scenario, _repetition: int):
        if scenario.scenario_id == "provider-case":
            raise AgentColRoutingV2ProviderOutputError(
                AgentColRoutingV2InvalidOutputReason.SCHEMA_VALIDATION_FAILED,
                schema_failure_reason=(
                    AgentColRoutingV2SchemaFailureReason.ROUTE_PAYLOAD_MISMATCH
                ),
            )
        return AgentColRoutingDirective(
            route="clarify",
            clarifying_question="What should I explain?",
        )

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=None,
        repetitions=1,
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [
        "quality-case run=1 expected=direct actual=clarify route_mismatch",
        (
            "provider-case run=1 "
            "model_output_error:schema_validation_failed:"
            "route_payload_mismatch"
        ),
    ]
    assert all("private provider text" not in line for line in output)


@pytest.mark.asyncio
async def test_decision_check_projects_only_safe_field_locator(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_provider_v2 import (
        AgentColRoutingV2FieldConstraint,
        AgentColRoutingV2InvalidOutputReason,
        AgentColRoutingV2ProviderOutputError,
        AgentColRoutingV2SchemaFailureReason,
        AgentColRoutingV2SchemaField,
    )
    from tool_belt_routing_evaluation import load_tool_belt_routing_scenarios

    fixture = write_fixture(
        tmp_path / "routing.json",
        [direct_definition("field-case")],
    )
    scenarios = load_tool_belt_routing_scenarios(fixture)

    async def request_directive(_scenario, _repetition: int):
        raise AgentColRoutingV2ProviderOutputError(
            AgentColRoutingV2InvalidOutputReason.SCHEMA_VALIDATION_FAILED,
            schema_failure_reason=(
                AgentColRoutingV2SchemaFailureReason.FIELD_CONSTRAINT_FAILED
            ),
            schema_failure_field=(
                AgentColRoutingV2SchemaField.CLARIFYING_QUESTION
            ),
            schema_failure_constraint=(
                AgentColRoutingV2FieldConstraint.STRING_TOO_LONG
            ),
        )

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=None,
        repetitions=1,
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [
        "field-case run=1 model_output_error:schema_validation_failed:"
        "field_constraint_failed:clarifying_question:string_too_long"
    ]
    assert all("private" not in line for line in output)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_type", "expected_result"),
    (
        ("timeout", "timeout_error"),
        ("provider", "provider_error"),
        ("directive", "directive_input_error"),
    ),
)
async def test_decision_check_classifies_each_execution_failure(
    tmp_path: Path,
    error_type: str,
    expected_result: str,
) -> None:
    module = load_check_module()
    from agent_col_routing_provider_v2 import (
        AgentColRoutingV2ProviderError,
        AgentColRoutingV2ProviderTimeoutError,
    )
    from agent_col_routing_v2 import RoutingDirectiveInputError
    from tool_belt_routing_evaluation import load_tool_belt_routing_scenarios

    fixture = write_fixture(
        tmp_path / "routing.json",
        [direct_definition()],
    )
    scenarios = load_tool_belt_routing_scenarios(fixture)
    errors = {
        "timeout": AgentColRoutingV2ProviderTimeoutError("private timeout"),
        "provider": AgentColRoutingV2ProviderError("private provider"),
        "directive": RoutingDirectiveInputError("private input"),
    }

    async def request_directive(_scenario, _repetition: int):
        raise errors[error_type]

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=None,
        repetitions=1,
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [f"direct-case run=1 {expected_result}"]
    assert all("private" not in line for line in output)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selected_scenario_id", "repetitions"),
    (("missing", 1), (None, 0), (None, 6)),
)
async def test_decision_check_rejects_unbounded_or_missing_selection(
    tmp_path: Path,
    selected_scenario_id: str | None,
    repetitions: int,
) -> None:
    module = load_check_module()
    from tool_belt_routing_evaluation import load_tool_belt_routing_scenarios

    fixture = write_fixture(
        tmp_path / "routing.json",
        [direct_definition()],
    )
    scenarios = load_tool_belt_routing_scenarios(fixture)

    async def unused_request(_scenario, _repetition: int):
        raise AssertionError("request must not execute")

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=selected_scenario_id,
        repetitions=repetitions,
        request_directive=unused_request,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["tool-belt-routing-check configuration_error"]


@pytest.mark.asyncio
async def test_live_decision_runner_uses_vertex_adc_input_and_closes_client(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_v2 import AgentColRoutingDirective

    fixture = write_fixture(
        tmp_path / "routing.json",
        [source_definition()],
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
    provider_inputs: list[object] = []

    def client_factory(**kwargs: object) -> ClosableClient:
        client_arguments.append(kwargs)
        return client

    async def provider_request(_client: object, routing_input: object):
        provider_inputs.append(routing_input)
        return AgentColRoutingDirective.model_validate(
            {
                "route": "source",
                "source_intent": {
                    "objective": "Analyze the supplied page.",
                    "selected_url_ids": ["url-1"],
                },
            }
        )

    output: list[str] = []
    exit_code = await module.run_live_tool_belt_routing_evaluation(
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
        provider_request=provider_request,
    )

    assert exit_code == 0
    assert client_arguments == [
        {
            "enterprise": True,
            "project": "project-1",
            "location": "global",
        }
    ]
    assert len(provider_inputs) == 1
    routing_input = provider_inputs[0]
    assert routing_input.current_message == source_definition()["message"]
    assert tuple(
        candidate.candidate_id for candidate in routing_input.candidate_urls
    ) == ("url-1",)
    assert client.async_closed is True
    assert client.closed is True


@pytest.mark.asyncio
async def test_fixture_runner_returns_configuration_error_for_invalid_json(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    fixture = tmp_path / "invalid.json"
    fixture.write_text("not-json", encoding="utf-8")

    async def unused_request(_scenario, _repetition: int):
        raise AssertionError("request must not execute")

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_fixture(
        fixture_path=fixture,
        selected_scenario_id=None,
        repetitions=1,
        request_directive=unused_request,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["tool-belt-routing-check configuration_error"]


@pytest.mark.asyncio
async def test_live_runner_rejects_invalid_vertex_configuration_before_client(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    fixture = write_fixture(
        tmp_path / "routing.json",
        [direct_definition()],
    )

    def forbidden_client_factory(**_kwargs: object):
        raise AssertionError("client must not be created")

    output: list[str] = []
    exit_code = await module.run_live_tool_belt_routing_evaluation(
        fixture_path=fixture,
        selected_scenario_id=None,
        repetitions=1,
        output=output.append,
        environment={
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "wrong-region",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        },
        client_factory=forbidden_client_factory,
    )

    assert exit_code == 2
    assert output == ["tool-belt-routing-check configuration_error"]


def test_main_forwards_bounded_cli_options() -> None:
    module = load_check_module()
    received: list[dict[str, object]] = []

    async def live_runner(**kwargs: object) -> int:
        received.append(kwargs)
        return 1

    exit_code = module.main(
        ["--scenario", "computation-series", "--repetitions", "3"],
        live_runner=live_runner,
    )

    assert exit_code == 1
    assert received == [
        {
            "fixture_path": module.DEFAULT_TOOL_BELT_ROUTING_FIXTURE_PATH,
            "selected_scenario_id": "computation-series",
            "repetitions": 3,
            "output": print,
        }
    ]
