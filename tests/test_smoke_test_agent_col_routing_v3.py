import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def write_fixture(path: Path, scenarios: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"fixture_version": "3.0", "scenarios": scenarios}),
        encoding="utf-8",
    )
    return path


def direct_scenario(scenario_id: str = "direct") -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "message": "Explain idempotency.",
        "expected_route": "direct",
        "expected_requirement_block_ids": [],
        "expected_subject_block_ids": [],
    }


def test_default_v3_fixture_covers_all_routes_and_exact_text_provenance() -> None:
    from smoke_test_agent_col_routing_v3 import (
        DEFAULT_ROUTING_V3_COMPATIBILITY_FIXTURE,
        load_routing_v3_compatibility_scenarios,
    )

    scenarios = load_routing_v3_compatibility_scenarios(
        DEFAULT_ROUTING_V3_COMPATIBILITY_FIXTURE
    )

    assert tuple(scenario.scenario_id for scenario in scenarios) == (
        "direct-general-requirements-advice",
        "direct-explicit-no-expert",
        "clarify-missing-subject",
        "clarify-missing-requirements",
        "clarify-url-plus-verification",
        "source-regression",
        "research-regression",
        "computation-regression",
        "requirements-verification",
    )
    assert set(scenario.expected_route for scenario in scenarios) == {
        "direct",
        "clarify",
        "source",
        "research",
        "computation",
        "requirements_verification",
    }
    verification = scenarios[-1]
    assert verification.expected_requirement_block_ids == (
        "block-3",
        "block-4",
    )
    assert verification.expected_subject_block_ids == ("block-6",)
    candidates = {
        candidate.candidate_id: candidate
        for candidate in verification.routing_input.text_block_candidates
    }
    assert candidates["block-3"].text == "- Include one practical example."
    assert candidates["block-4"].text == "- State a material limitation."
    assert candidates["block-6"].text == (
        "The response includes one practical example but does not state a limitation."
    )
    assert all(
        verification.routing_input.current_message[
            candidate.start_index:candidate.end_index
        ]
        == candidate.text
        for candidate in candidates.values()
    )


@pytest.mark.parametrize(
    "scenarios",
    (
        [direct_scenario("duplicate"), direct_scenario("duplicate")],
        [{**direct_scenario(), "unexpected": True}],
        [
            {
                **direct_scenario(),
                "expected_requirement_block_ids": ["block-1"],
            }
        ],
        [
            {
                **direct_scenario(),
                "expected_route": "requirements_verification",
            }
        ],
    ),
)
def test_v3_fixture_rejects_invalid_contracts(
    tmp_path: Path,
    scenarios: list[dict[str, object]],
) -> None:
    from pydantic import ValidationError
    from smoke_test_agent_col_routing_v3 import (
        load_routing_v3_compatibility_scenarios,
    )

    fixture = write_fixture(tmp_path / "invalid.json", scenarios)

    with pytest.raises(ValidationError):
        load_routing_v3_compatibility_scenarios(fixture)


@pytest.mark.asyncio
async def test_v3_runner_reports_routes_and_exact_selections() -> None:
    from agent_col_routing_v3 import AgentColRoutingDirective
    from smoke_test_agent_col_routing_v3 import (
        DEFAULT_ROUTING_V3_COMPATIBILITY_FIXTURE,
        load_routing_v3_compatibility_scenarios,
        run_routing_v3_compatibility,
    )

    scenarios = load_routing_v3_compatibility_scenarios(
        DEFAULT_ROUTING_V3_COMPATIBILITY_FIXTURE
    )
    decisions = {
        "direct-general-requirements-advice": AgentColRoutingDirective(
            route="direct"
        ),
        "direct-explicit-no-expert": AgentColRoutingDirective(route="direct"),
        "clarify-missing-subject": AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Please provide the subject to assess.",
        ),
        "clarify-missing-requirements": AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Please provide the requirements.",
        ),
        "clarify-url-plus-verification": AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Should I retrieve or verify first?",
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
                "question": "What is the latest stable Python release?",
                "objective": "Verify with current public evidence.",
            },
        ),
        "computation-regression": AgentColRoutingDirective(
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
        "requirements-verification": AgentColRoutingDirective(
            route="requirements_verification",
            requirements_verification_intent={
                "objective": "Compare every requirement with the supplied subject.",
                "requirement_block_ids": ["block-3", "block-4"],
                "subject_block_ids": ["block-6"],
            },
        ),
    }
    calls: list[str] = []

    async def request(scenario: object, _repetition: int) -> object:
        calls.append(scenario.scenario_id)
        return decisions[scenario.scenario_id]

    output: list[str] = []
    exit_code = await run_routing_v3_compatibility(
        scenarios=scenarios,
        selected_scenario_id=None,
        repetitions=1,
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 0
    assert calls == list(decisions)
    assert len(output) == 9
    assert output[-1] == (
        "requirements-verification run=1 "
        "expected=requirements_verification "
        "actual=requirements_verification pass"
    )
    assert all("pass" in line for line in output)


@pytest.mark.asyncio
async def test_v3_runner_distinguishes_route_and_selection_mismatches() -> None:
    from agent_col_routing_v3 import AgentColRoutingDirective
    from smoke_test_agent_col_routing_v3 import (
        RoutingV3CompatibilityScenario,
        run_routing_v3_compatibility,
    )

    scenario = RoutingV3CompatibilityScenario(
        scenario_id="verification-case",
        fixture_version="3.0",
        routing_input={
            "current_message": "requirement\n\nsubject one\n\nsubject two",
            "text_block_candidates": [
                {
                    "candidate_id": "block-1",
                    "text": "requirement",
                    "start_index": 0,
                    "end_index": 11,
                    "structural_kind": "paragraph",
                },
                {
                    "candidate_id": "block-2",
                    "text": "subject one",
                    "start_index": 13,
                    "end_index": 24,
                    "structural_kind": "paragraph",
                },
                {
                    "candidate_id": "block-3",
                    "text": "subject two",
                    "start_index": 26,
                    "end_index": 37,
                    "structural_kind": "paragraph",
                },
            ],
            "available_capabilities": ["requirements_verification"],
        },
        expected_route="requirements_verification",
        expected_requirement_block_ids=["block-1"],
        expected_subject_block_ids=["block-2"],
    )
    outcomes = (
        AgentColRoutingDirective(route="direct"),
        AgentColRoutingDirective(
            route="requirements_verification",
            requirements_verification_intent={
                "objective": "Compare the supplied material.",
                "requirement_block_ids": ["block-1"],
                "subject_block_ids": ["block-3"],
            },
        ),
    )

    async def request(_scenario: object, repetition: int) -> object:
        return outcomes[repetition - 1]

    output: list[str] = []
    exit_code = await run_routing_v3_compatibility(
        scenarios=(scenario,),
        selected_scenario_id=None,
        repetitions=2,
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 1
    assert output == [
        "verification-case run=1 expected=requirements_verification "
        "actual=direct route_mismatch",
        "verification-case run=2 expected=requirements_verification "
        "actual=requirements_verification selection_mismatch",
    ]


@pytest.mark.asyncio
async def test_v3_runner_reports_content_safe_execution_failures() -> None:
    from agent_col_routing_provider_v3 import (
        AgentColRoutingV3InvalidOutputReason,
        AgentColRoutingV3ProviderError,
        AgentColRoutingV3ProviderOutputError,
        AgentColRoutingV3ProviderTimeoutError,
    )
    from agent_col_routing_v3 import RoutingDirectiveInputError
    from smoke_test_agent_col_routing_v3 import (
        RoutingV3CompatibilityScenario,
        run_routing_v3_compatibility,
    )

    scenario = RoutingV3CompatibilityScenario(
        scenario_id="safe-case",
        fixture_version="3.0",
        routing_input={"current_message": "Explain it."},
        expected_route="direct",
        expected_requirement_block_ids=[],
        expected_subject_block_ids=[],
    )
    outcomes = (
        AgentColRoutingV3ProviderError("private-provider-data"),
        AgentColRoutingV3ProviderTimeoutError("private-timeout-data"),
        AgentColRoutingV3ProviderOutputError(
            AgentColRoutingV3InvalidOutputReason.SCHEMA_VALIDATION_FAILED
        ),
        RoutingDirectiveInputError("private-routing-input"),
    )

    async def request(_scenario: object, repetition: int) -> object:
        raise outcomes[repetition - 1]

    output: list[str] = []
    exit_code = await run_routing_v3_compatibility(
        scenarios=(scenario,),
        selected_scenario_id=None,
        repetitions=4,
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 2
    assert output == [
        "safe-case run=1 provider_error",
        "safe-case run=2 timeout_error",
        "safe-case run=3 model_output_error",
        "safe-case run=4 directive_input_error",
    ]
    assert "private" not in " ".join(output)


@pytest.mark.asyncio
async def test_v3_runner_rejects_invalid_selection_or_repetitions() -> None:
    from smoke_test_agent_col_routing_v3 import (
        RoutingV3CompatibilityScenario,
        run_routing_v3_compatibility,
    )

    scenario = RoutingV3CompatibilityScenario(
        scenario_id="only",
        fixture_version="3.0",
        routing_input={"current_message": "Explain it."},
        expected_route="direct",
        expected_requirement_block_ids=[],
        expected_subject_block_ids=[],
    )

    async def request(_scenario: object, _repetition: int) -> object:
        raise AssertionError("Provider must not be called.")

    for selected, repetitions in (("missing", 1), (None, 0), (None, 6)):
        output: list[str] = []
        exit_code = await run_routing_v3_compatibility(
            scenarios=(scenario,),
            selected_scenario_id=selected,
            repetitions=repetitions,
            request_directive=request,
            output=output.append,
        )
        assert exit_code == 2
        assert output == [
            "agent-col-routing-v3-compatibility configuration_error"
        ]


@pytest.mark.asyncio
async def test_v3_fixture_runner_classifies_fixture_errors(tmp_path: Path) -> None:
    from smoke_test_agent_col_routing_v3 import (
        run_routing_v3_compatibility_fixture,
    )

    async def request(_scenario: object, _repetition: int) -> object:
        raise AssertionError("Provider must not be called.")

    output: list[str] = []
    exit_code = await run_routing_v3_compatibility_fixture(
        fixture_path=tmp_path / "missing.json",
        selected_scenario_id=None,
        repetitions=1,
        request_directive=request,
        output=output.append,
    )

    assert exit_code == 2
    assert output == ["agent-col-routing-v3-compatibility configuration_error"]


@pytest.mark.asyncio
async def test_v3_live_runner_uses_vertex_adc_and_closes_client(
    tmp_path: Path,
) -> None:
    from smoke_test_agent_col_routing_v3 import (
        run_live_routing_v3_compatibility,
    )

    fixture = write_fixture(tmp_path / "routing-v3.json", [direct_scenario()])

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
        from agent_col_routing_v3 import AgentColRoutingDirective

        return AgentColRoutingDirective(route="direct")

    output: list[str] = []
    exit_code = await run_live_routing_v3_compatibility(
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


def test_v3_main_forwards_bounded_cli_options() -> None:
    from smoke_test_agent_col_routing_v3 import (
        DEFAULT_ROUTING_V3_COMPATIBILITY_FIXTURE,
        main,
    )

    received: list[dict[str, object]] = []

    async def live_runner(**kwargs: object) -> int:
        received.append(kwargs)
        return 1

    exit_code = main(
        ["--scenario", "requirements-verification", "--repetitions", "3"],
        live_runner=live_runner,
    )

    assert exit_code == 1
    assert received == [
        {
            "fixture_path": DEFAULT_ROUTING_V3_COMPATIBILITY_FIXTURE,
            "selected_scenario_id": "requirements-verification",
            "repetitions": 3,
            "output": print,
        }
    ]


def test_v3_runner_imports_no_runtime_or_persistence_surfaces() -> None:
    script = (
        "import sys; import smoke_test_agent_col_routing_v3; "
        "forbidden={'main','agent_col_turn_service','agent_col_expert_executor_v2',"
        "'google.adk.runners','google.cloud.firestore'}; "
        "loaded=forbidden.intersection(sys.modules); "
        "raise SystemExit(1 if loaded else 0)"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
