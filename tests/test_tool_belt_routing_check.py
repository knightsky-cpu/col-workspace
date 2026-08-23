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


def write_v3_fixture(
    path: Path,
    scenarios: list[dict[str, object]],
) -> Path:
    path.write_text(
        json.dumps({"fixture_version": "3.0", "scenarios": scenarios}),
        encoding="utf-8",
    )
    return path


def v3_direct_definition(
    scenario_id: str = "direct-v3",
) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "message": "Explain idempotency in stable general terms.",
        "expected_route": "direct",
        "safety_class": "standard",
        "live_repetitions": 1,
        "manual_semantic_review": "none",
        "rationale": "Stable knowledge should be answered directly.",
    }


def v3_source_definition() -> dict[str, object]:
    return {
        "scenario_id": "source-v3",
        "message": "Analyze https://example.com/ using only that page.",
        "expected_route": "source",
        "expected_url_ids": ["url-1"],
        "safety_class": "standard",
        "live_repetitions": 3,
        "manual_semantic_review": "none",
        "rationale": "The supplied page is the bounded evidence target.",
    }


def v3_directive_for_expected_route(scenario):
    from agent_col_routing_v3 import AgentColRoutingDirective

    if str(scenario.expected_route) == "source":
        return AgentColRoutingDirective.model_validate(
            {
                "schema_version": "3.0",
                "route": "source",
                "source_intent": {
                    "objective": "Analyze the selected source.",
                    "selected_url_ids": ["url-1"],
                    "constraints": [],
                },
            }
        )
    return AgentColRoutingDirective.model_validate(
        {"schema_version": "3.0", "route": "direct"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_calls"),
    (
        ("baseline", (("direct-v3", 1), ("source-v3", 1))),
        (
            "declared",
            (
                ("direct-v3", 1),
                ("source-v3", 1),
                ("source-v3", 2),
                ("source-v3", 3),
            ),
        ),
    ),
)
async def test_v3_decision_check_uses_bounded_mode_attempt_policy(
    tmp_path: Path,
    mode: str,
    expected_calls: tuple[tuple[str, int], ...],
) -> None:
    module = load_check_module()
    from tool_belt_routing_evaluation_v3 import (
        load_tool_belt_routing_v3_scenarios,
    )

    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [v3_direct_definition(), v3_source_definition()],
    )
    scenarios = load_tool_belt_routing_v3_scenarios(fixture)
    calls: list[tuple[str, int]] = []

    async def request_directive(scenario, repetition: int):
        calls.append((scenario.scenario_id, repetition))
        return v3_directive_for_expected_route(scenario)

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=None,
        mode=mode,
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 0
    assert tuple(calls) == expected_calls


@pytest.mark.asyncio
async def test_v3_decision_check_rejects_missing_scenario_without_request(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from tool_belt_routing_evaluation_v3 import (
        load_tool_belt_routing_v3_scenarios,
    )

    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [v3_direct_definition()],
    )
    scenarios = load_tool_belt_routing_v3_scenarios(fixture)

    async def forbidden_request(_scenario, _repetition: int):
        raise AssertionError("provider request must not execute")

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id="missing",
        mode="baseline",
        request_directive=forbidden_request,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["tool-belt-routing-check configuration_error"]


@pytest.mark.asyncio
async def test_v3_decision_check_returns_one_for_candidate_mismatch(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_v3 import AgentColRoutingDirective
    from tool_belt_routing_evaluation_v3 import (
        load_tool_belt_routing_v3_scenarios,
    )

    source = v3_source_definition()
    source.update(
        {
            "message": (
                "Compare https://example.com/ with https://www.iana.org/."
            ),
            "expected_url_ids": ["url-1", "url-2"],
        }
    )
    fixture = write_v3_fixture(tmp_path / "routing-v3.json", [source])
    scenarios = load_tool_belt_routing_v3_scenarios(fixture)

    async def request_directive(_scenario, _repetition: int):
        return AgentColRoutingDirective.model_validate(
            {
                "schema_version": "3.0",
                "route": "source",
                "source_intent": {
                    "objective": "Analyze the selected source.",
                    "selected_url_ids": ["url-1"],
                    "constraints": [],
                },
            }
        )

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=None,
        mode="baseline",
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 1
    assert output == [
        "source-v3 run=1 expected=source actual=source "
        "url_selection_mismatch"
    ]


@pytest.mark.asyncio
async def test_v3_declared_mode_preserves_all_attempts_after_failure(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_provider_v3 import AgentColRoutingV3ProviderError
    from tool_belt_routing_evaluation_v3 import (
        load_tool_belt_routing_v3_scenarios,
    )

    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [v3_source_definition()],
    )
    scenarios = load_tool_belt_routing_v3_scenarios(fixture)
    attempts: list[int] = []

    async def request_directive(scenario, repetition: int):
        attempts.append(repetition)
        if repetition == 1:
            raise AgentColRoutingV3ProviderError("private first failure")
        return v3_directive_for_expected_route(scenario)

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=None,
        mode="declared",
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 2
    assert attempts == [1, 2, 3]
    assert output == [
        "source-v3 run=1 provider_error",
        "source-v3 run=2 expected=source actual=source pass",
        "source-v3 run=3 expected=source actual=source pass",
    ]
    assert all("private first failure" not in line for line in output)


def v3_clarify_definition() -> dict[str, object]:
    return {
        "scenario_id": "clarify-v3",
        "message": "Calculate the percentage change for my results.",
        "expected_route": "clarify",
        "safety_class": "standard",
        "live_repetitions": 1,
        "manual_semantic_review": "clarification_quality",
        "rationale": "The required operands are missing.",
    }


@pytest.mark.asyncio
async def test_v3_fixture_runner_preserves_semantic_and_execution_failures(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_provider_v3 import (
        AgentColRoutingV3InvalidOutputReason,
        AgentColRoutingV3ProviderOutputError,
        AgentColRoutingV3SchemaFailureReason,
    )
    from agent_col_routing_v3 import AgentColRoutingDirective

    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [
            v3_direct_definition("quality-v3"),
            v3_direct_definition("provider-v3"),
        ],
    )

    async def request_directive(scenario, _repetition: int):
        if scenario.scenario_id == "provider-v3":
            raise AgentColRoutingV3ProviderOutputError(
                AgentColRoutingV3InvalidOutputReason.SCHEMA_VALIDATION_FAILED,
                schema_failure_reason=(
                    AgentColRoutingV3SchemaFailureReason.ROUTE_PAYLOAD_MISMATCH
                ),
            )
        return AgentColRoutingDirective.model_validate(
            {
                "schema_version": "3.0",
                "route": "clarify",
                "clarifying_question": "What should I explain?",
            }
        )

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_fixture(
        fixture_path=fixture,
        selected_scenario_id=None,
        mode="baseline",
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [
        "quality-v3 run=1 expected=direct actual=clarify route_mismatch",
        (
            "provider-v3 run=1 "
            "model_output_error:schema_validation_failed:"
            "route_payload_mismatch"
        ),
    ]
    assert all("What should I explain" not in line for line in output)
    assert all("idempotency" not in line for line in output)


@pytest.mark.asyncio
async def test_v3_fixture_runner_reports_manual_review_without_content(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_v3 import AgentColRoutingDirective

    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [v3_clarify_definition()],
    )

    async def request_directive(_scenario, _repetition: int):
        return AgentColRoutingDirective.model_validate(
            {
                "schema_version": "3.0",
                "route": "clarify",
                "clarifying_question": "Which exact values should I use?",
            }
        )

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_fixture(
        fixture_path=fixture,
        selected_scenario_id=None,
        mode="baseline",
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 0
    assert output == [
        "clarify-v3 run=1 expected=clarify actual=clarify pass "
        "manual_review_required"
    ]
    assert all("Which exact values" not in line for line in output)


@pytest.mark.asyncio
async def test_v3_fixture_runner_projects_only_safe_field_locator(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_provider_v3 import (
        AgentColRoutingV3FieldConstraint,
        AgentColRoutingV3InvalidOutputReason,
        AgentColRoutingV3ProviderOutputError,
        AgentColRoutingV3SchemaFailureReason,
        AgentColRoutingV3SchemaField,
    )

    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [v3_direct_definition()],
    )

    async def request_directive(_scenario, _repetition: int):
        raise AgentColRoutingV3ProviderOutputError(
            AgentColRoutingV3InvalidOutputReason.SCHEMA_VALIDATION_FAILED,
            schema_failure_reason=(
                AgentColRoutingV3SchemaFailureReason.FIELD_CONSTRAINT_FAILED
            ),
            schema_failure_field=(
                AgentColRoutingV3SchemaField.CLARIFYING_QUESTION
            ),
            schema_failure_constraint=(
                AgentColRoutingV3FieldConstraint.STRING_TOO_LONG
            ),
        )

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_fixture(
        fixture_path=fixture,
        selected_scenario_id=None,
        mode="baseline",
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [
        "direct-v3 run=1 model_output_error:schema_validation_failed:"
        "field_constraint_failed:clarifying_question:string_too_long"
    ]


@pytest.mark.asyncio
async def test_v3_live_runner_reports_metadata_uses_adc_and_closes_client(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_v3 import AgentColRoutingDirective

    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [v3_source_definition()],
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
                "schema_version": "3.0",
                "route": "source",
                "source_intent": {
                    "objective": "Analyze the selected source.",
                    "selected_url_ids": ["url-1"],
                    "constraints": [],
                },
            }
        )

    clock_values = iter((10.0, 10.125))
    output: list[str] = []
    exit_code = await module.run_live_tool_belt_routing_evaluation(
        fixture_path=fixture,
        selected_scenario_id=None,
        mode="baseline",
        output=output.append,
        environment={
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        },
        client_factory=client_factory,
        provider_request=provider_request,
        repository_commit="abc1234",
        repository_dirty=True,
        monotonic=lambda: next(clock_values),
    )

    assert exit_code == 0
    assert output == [
        (
            "tool-belt-routing-check fixture=3.0 schema=3.0 "
            "commit=abc1234 worktree=dirty model=gemini-3.6-flash "
            "provider=vertex_ai "
            "mode=baseline scenarios=1 planned_attempts=1"
        ),
        "source-v3 run=1 expected=source actual=source pass",
        (
            "tool-belt-routing-check summary planned_attempts=1 "
            "provider_calls=1 manual_review_attempts=0 "
            "elapsed_ms=125 exit=0"
        ),
    ]
    assert client_arguments == [
        {
            "enterprise": True,
            "project": "project-1",
            "location": "global",
        }
    ]
    assert len(provider_inputs) == 1
    routing_input = provider_inputs[0]
    assert routing_input.current_message == v3_source_definition()["message"]
    assert tuple(
        candidate.candidate_id for candidate in routing_input.candidate_urls
    ) == ("url-1",)
    assert client.async_closed is True
    assert client.closed is True
    assert all("Analyze https" not in line for line in output)


def test_v3_main_forwards_mode_and_default_fixture() -> None:
    module = load_check_module()
    received: list[dict[str, object]] = []

    async def live_runner(**kwargs: object) -> int:
        received.append(kwargs)
        return 1

    exit_code = module.main(
        ["--scenario", "computation-series", "--mode", "declared"],
        live_runner=live_runner,
    )

    assert exit_code == 1
    assert received == [
        {
            "fixture_path": (
                module.DEFAULT_TOOL_BELT_ROUTING_V3_FIXTURE_PATH
            ),
            "selected_scenario_id": "computation-series",
            "mode": "declared",
            "output": print,
        }
    ]


@pytest.mark.asyncio
async def test_v3_live_summary_counts_only_reached_manual_reviews(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from agent_col_routing_provider_v3 import AgentColRoutingV3ProviderError

    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [v3_clarify_definition()],
    )

    class ClosableClient:
        def __init__(self) -> None:
            self.aio = SimpleNamespace(aclose=self.aclose)

        async def aclose(self) -> None:
            return None

        def close(self) -> None:
            return None

    async def provider_request(_client: object, _routing_input: object):
        raise AgentColRoutingV3ProviderError("private provider failure")

    clock_values = iter((20.0, 20.05))
    output: list[str] = []
    exit_code = await module.run_live_tool_belt_routing_evaluation(
        fixture_path=fixture,
        selected_scenario_id=None,
        mode="baseline",
        output=output.append,
        environment={
            "GOOGLE_CLOUD_PROJECT": "project-1",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_ENTERPRISE": "True",
        },
        client_factory=lambda **_kwargs: ClosableClient(),
        provider_request=provider_request,
        repository_commit="abc1234",
        repository_dirty=False,
        monotonic=lambda: next(clock_values),
    )

    assert exit_code == 2
    assert output[-2:] == [
        "clarify-v3 run=1 provider_error",
        (
            "tool-belt-routing-check summary planned_attempts=1 "
            "provider_calls=1 manual_review_attempts=0 "
            "elapsed_ms=50 exit=2"
        ),
    ]
    assert all("private provider failure" not in line for line in output)


def test_v3_cli_rejects_removed_arbitrary_repetitions() -> None:
    module = load_check_module()

    with pytest.raises(SystemExit) as exc_info:
        module.main(["--repetitions", "3"])

    assert exc_info.value.code == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_type", "expected_result"),
    (
        ("timeout", "timeout_error"),
        ("provider", "provider_error"),
        ("directive", "directive_input_error"),
    ),
)
async def test_v3_decision_check_classifies_execution_failures_without_content(
    tmp_path: Path,
    error_type: str,
    expected_result: str,
) -> None:
    module = load_check_module()
    from agent_col_routing_provider_v3 import (
        AgentColRoutingV3ProviderError,
        AgentColRoutingV3ProviderTimeoutError,
    )
    from agent_col_routing_v3 import RoutingDirectiveInputError
    from tool_belt_routing_evaluation_v3 import (
        load_tool_belt_routing_v3_scenarios,
    )

    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [v3_direct_definition()],
    )
    scenarios = load_tool_belt_routing_v3_scenarios(fixture)
    errors = {
        "timeout": AgentColRoutingV3ProviderTimeoutError("private timeout"),
        "provider": AgentColRoutingV3ProviderError("private provider"),
        "directive": RoutingDirectiveInputError("private input"),
    }

    async def request_directive(_scenario, _repetition: int):
        raise errors[error_type]

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=None,
        mode="baseline",
        request_directive=request_directive,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [f"direct-v3 run=1 {expected_result}"]
    assert all("private" not in line for line in output)


@pytest.mark.asyncio
async def test_v3_decision_check_rejects_invalid_mode_without_request(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    from tool_belt_routing_evaluation_v3 import (
        load_tool_belt_routing_v3_scenarios,
    )

    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [v3_direct_definition()],
    )
    scenarios = load_tool_belt_routing_v3_scenarios(fixture)

    async def forbidden_request(_scenario, _repetition: int):
        raise AssertionError("provider request must not execute")

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_evaluation(
        scenarios=scenarios,
        selected_scenario_id=None,
        mode="invalid",
        request_directive=forbidden_request,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["tool-belt-routing-check configuration_error"]


@pytest.mark.asyncio
async def test_v3_fixture_runner_rejects_invalid_json_without_request(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    fixture = tmp_path / "invalid.json"
    fixture.write_text("not-json", encoding="utf-8")

    async def forbidden_request(_scenario, _repetition: int):
        raise AssertionError("provider request must not execute")

    output: list[str] = []
    exit_code = await module.run_tool_belt_routing_fixture(
        fixture_path=fixture,
        selected_scenario_id=None,
        mode="baseline",
        request_directive=forbidden_request,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["tool-belt-routing-check configuration_error"]


@pytest.mark.asyncio
async def test_v3_live_runner_rejects_invalid_configuration_before_client(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    fixture = write_v3_fixture(
        tmp_path / "routing-v3.json",
        [v3_direct_definition()],
    )

    def forbidden_client_factory(**_kwargs: object):
        raise AssertionError("client must not be created")

    output: list[str] = []
    exit_code = await module.run_live_tool_belt_routing_evaluation(
        fixture_path=fixture,
        selected_scenario_id=None,
        mode="baseline",
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


def test_repository_commit_resolver_returns_content_safe_head() -> None:
    module = load_check_module()

    commit = module.resolve_repository_commit()

    assert len(commit) == 40
    assert set(commit) <= set("0123456789abcdef")
