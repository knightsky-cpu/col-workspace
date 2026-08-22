import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError


def load_evaluation_module():
    try:
        return importlib.import_module("tool_belt_routing_evaluation")
    except ModuleNotFoundError:
        pytest.fail("tool_belt_routing_evaluation has not been implemented")


def write_fixture(path: Path, scenarios: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"fixture_version": "1.0", "scenarios": scenarios}),
        encoding="utf-8",
    )
    return path


def test_fixture_loader_projects_only_current_message_candidates(
    tmp_path: Path,
) -> None:
    module = load_evaluation_module()
    fixture = write_fixture(
        tmp_path / "tool-belt.json",
        [
            {
                "scenario_id": "source-with-numeric-url",
                "message": (
                    "Analyze https://example.com/report/2026 using only "
                    "the supplied page."
                ),
                "expected_route": "source",
                "expected_url_ids": ["url-1"],
                "expected_scalar_numeric_ids": [],
                "expected_series_numeric_ids": [],
                "expected_precision_numeric_id": None,
                "manual_semantic_review": "none",
            }
        ],
    )

    scenarios = module.load_tool_belt_routing_scenarios(fixture)

    assert len(scenarios) == 1
    scenario = scenarios[0]
    assert scenario.scenario_id == "source-with-numeric-url"
    assert scenario.expected_route == "source"
    assert scenario.expected_url_ids == ("url-1",)
    assert tuple(
        candidate.candidate_id
        for candidate in scenario.routing_input.candidate_urls
    ) == ("url-1",)
    assert scenario.routing_input.numeric_candidates == ()
    assert scenario.routing_input.numeric_projection_incomplete is False
    assert tuple(scenario.routing_input.available_capabilities) == (
        "source",
        "research",
        "computation",
    )


def valid_direct_scenario() -> dict[str, object]:
    return {
        "scenario_id": "direct-case",
        "message": "Explain idempotency in stable general terms.",
        "expected_route": "direct",
        "expected_url_ids": [],
        "expected_scalar_numeric_ids": [],
        "expected_series_numeric_ids": [],
        "expected_precision_numeric_id": None,
        "manual_semantic_review": "none",
    }


@pytest.mark.parametrize(
    "mutation",
    (
        "duplicate_scenario_id",
        "source_without_selection",
        "duplicate_url_selection",
        "direct_with_selection",
        "unknown_numeric_id",
        "computation_without_operands",
        "reversed_series_order",
        "incompatible_series_units",
        "invalid_precision_value",
        "precision_without_mode",
        "clarify_without_review",
        "direct_with_clarification_review",
    ),
)
def test_fixture_loader_rejects_duplicate_or_contradictory_contracts(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_evaluation_module()
    scenario = valid_direct_scenario()
    scenarios = [scenario]
    if mutation == "duplicate_scenario_id":
        scenarios.append(dict(scenario))
    elif mutation == "source_without_selection":
        scenario["expected_route"] = "source"
    elif mutation == "duplicate_url_selection":
        scenario.update(
            {
                "message": (
                    "Compare https://example.com/ and "
                    "https://www.iana.org/."
                ),
                "expected_route": "source",
                "expected_url_ids": ["url-1", "url-1"],
            }
        )
    elif mutation == "direct_with_selection":
        scenario["message"] = "Explain https://example.com/ without opening it."
        scenario["expected_url_ids"] = ["url-1"]
    elif mutation == "unknown_numeric_id":
        scenario.update(
            {
                "message": "Calculate the mean of 12 and 15.",
                "expected_route": "computation",
                "expected_series_numeric_ids": [["number-1", "number-3"]],
            }
        )
    elif mutation == "computation_without_operands":
        scenario.update(
            {
                "message": "Calculate the result.",
                "expected_route": "computation",
            }
        )
    elif mutation == "reversed_series_order":
        scenario.update(
            {
                "message": "Calculate the mean of values 12, 15, and 18.",
                "expected_route": "computation",
                "expected_series_numeric_ids": [
                    ["number-2", "number-1", "number-3"]
                ],
            }
        )
    elif mutation == "incompatible_series_units":
        scenario.update(
            {
                "message": "Calculate using values 12 and 15%.",
                "expected_route": "computation",
                "expected_series_numeric_ids": [
                    ["number-1", "number-2"]
                ],
            }
        )
    elif mutation == "invalid_precision_value":
        scenario.update(
            {
                "message": "Use value 12. Report 0 significant figures.",
                "expected_route": "computation",
                "expected_scalar_numeric_ids": ["number-1"],
                "expected_precision_numeric_id": "number-2",
                "expected_precision_mode": "significant_figures",
            }
        )
    elif mutation == "precision_without_mode":
        scenario.update(
            {
                "message": "Use 12 and 15. Report 2 decimal places.",
                "expected_route": "computation",
                "expected_scalar_numeric_ids": ["number-1", "number-2"],
                "expected_precision_numeric_id": "number-3",
            }
        )
    elif mutation == "clarify_without_review":
        scenario["expected_route"] = "clarify"
    else:
        scenario["manual_semantic_review"] = "clarification_quality"

    fixture = write_fixture(tmp_path / "invalid.json", scenarios)

    with pytest.raises(ValidationError):
        module.load_tool_belt_routing_scenarios(fixture)


def load_one_scenario(
    tmp_path: Path,
    scenario: dict[str, object],
):
    module = load_evaluation_module()
    fixture = write_fixture(tmp_path / "one-scenario.json", [scenario])
    return module.load_tool_belt_routing_scenarios(fixture)[0]


@pytest.mark.parametrize(
    ("expected_route", "actual_route", "expected_code"),
    (
        ("direct", "source", "unnecessary_expert"),
        ("source", "direct", "missing_expert"),
        ("source", "research", "wrong_expert"),
        ("clarify", "direct", "route_mismatch"),
    ),
)
def test_route_evaluator_classifies_restraint_and_routing_failures(
    tmp_path: Path,
    expected_route: str,
    actual_route: str,
    expected_code: str,
) -> None:
    module = load_evaluation_module()
    from agent_col_routing_v2 import (
        AgentColRoutingDirective,
        ResearchRoutingIntent,
        SourceRoutingIntent,
    )

    scenario_definition = valid_direct_scenario()
    scenario_definition["expected_route"] = expected_route
    if expected_route == "source":
        scenario_definition["message"] = "Analyze https://example.com/."
        scenario_definition["expected_url_ids"] = ["url-1"]
    elif expected_route == "clarify":
        scenario_definition["message"] = "Calculate the percentage change."
        scenario_definition["manual_semantic_review"] = (
            "clarification_quality"
        )
    scenario = load_one_scenario(tmp_path, scenario_definition)

    directive_data: dict[str, object] = {
        "schema_version": "2.0",
        "route": actual_route,
    }
    if actual_route == "source":
        directive_data["source_intent"] = SourceRoutingIntent(
            objective="Analyze the supplied page.",
            selected_url_ids=("url-1",),
        )
    elif actual_route == "research":
        directive_data["research_intent"] = ResearchRoutingIntent(
            question="What current evidence applies?",
            objective="Find current public evidence.",
        )
    directive = AgentColRoutingDirective.model_validate(directive_data)

    findings = module.evaluate_tool_belt_routing(scenario, directive)

    assert tuple(finding.code for finding in findings) == (expected_code,)


def test_source_evaluator_requires_the_exact_candidate_selection(
    tmp_path: Path,
) -> None:
    module = load_evaluation_module()
    from agent_col_routing_v2 import (
        AgentColRoutingDirective,
        SourceRoutingIntent,
    )

    scenario = load_one_scenario(
        tmp_path,
        {
            "scenario_id": "multiple-source-candidates",
            "message": (
                "Compare https://example.com/ with https://www.iana.org/."
            ),
            "expected_route": "source",
            "expected_url_ids": ["url-1", "url-2"],
            "expected_scalar_numeric_ids": [],
            "expected_series_numeric_ids": [],
            "expected_precision_numeric_id": None,
            "manual_semantic_review": "none",
        },
    )
    directive = AgentColRoutingDirective(
        route="source",
        source_intent=SourceRoutingIntent(
            objective="Inspect one supplied page.",
            selected_url_ids=("url-1",),
        ),
    )

    findings = module.evaluate_tool_belt_routing(scenario, directive)

    assert tuple(finding.code for finding in findings) == (
        "url_selection_mismatch",
    )


def test_source_evaluator_accepts_the_same_candidate_set_in_any_order(
    tmp_path: Path,
) -> None:
    module = load_evaluation_module()
    from agent_col_routing_v2 import (
        AgentColRoutingDirective,
        SourceRoutingIntent,
    )

    scenario = load_one_scenario(
        tmp_path,
        {
            "scenario_id": "multiple-source-candidates",
            "message": (
                "Compare https://example.com/ with https://www.iana.org/."
            ),
            "expected_route": "source",
            "expected_url_ids": ["url-1", "url-2"],
            "expected_scalar_numeric_ids": [],
            "expected_series_numeric_ids": [],
            "expected_precision_numeric_id": None,
            "manual_semantic_review": "none",
        },
    )
    directive = AgentColRoutingDirective(
        route="source",
        source_intent=SourceRoutingIntent(
            objective="Compare the supplied pages.",
            selected_url_ids=("url-2", "url-1"),
        ),
    )

    assert module.evaluate_tool_belt_routing(scenario, directive) == ()


def test_computation_evaluator_requires_exact_operand_grouping_and_precision(
    tmp_path: Path,
) -> None:
    module = load_evaluation_module()
    from agent_col_routing_v2 import (
        AgentColRoutingDirective,
        ComputationPrecisionSelection,
        ComputationRoutingIntent,
        ComputationScalarSelection,
        ComputationSeriesSelection,
    )

    scenario = load_one_scenario(
        tmp_path,
        {
            "scenario_id": "series-with-precision",
            "message": (
                "Use values 12, 15, and 18. Report 2 decimal places."
            ),
            "expected_route": "computation",
            "expected_url_ids": [],
            "expected_scalar_numeric_ids": [],
            "expected_series_numeric_ids": [
                ["number-1", "number-2", "number-3"]
            ],
            "expected_precision_numeric_id": "number-4",
            "expected_precision_mode": "decimal_places",
            "manual_semantic_review": "none",
        },
    )
    directive = AgentColRoutingDirective(
        route="computation",
        computation_intent=ComputationRoutingIntent(
            objective="Calculate the requested mean.",
            scalar_inputs=(
                ComputationScalarSelection(
                    name="first_value",
                    numeric_id="number-1",
                ),
            ),
            series_inputs=(
                ComputationSeriesSelection(
                    name="remaining_values",
                    numeric_ids=("number-2", "number-3"),
                ),
            ),
            precision=ComputationPrecisionSelection(
                mode="decimal_places",
                digits_numeric_id="number-4",
            ),
        ),
    )

    findings = module.evaluate_tool_belt_routing(scenario, directive)

    assert tuple(finding.code for finding in findings) == (
        "scalar_selection_mismatch",
        "series_selection_mismatch",
    )


def test_computation_evaluator_accepts_scalar_set_in_any_order(
    tmp_path: Path,
) -> None:
    module = load_evaluation_module()
    from agent_col_routing_v2 import (
        AgentColRoutingDirective,
        ComputationRoutingIntent,
        ComputationScalarSelection,
    )

    scenario = load_one_scenario(
        tmp_path,
        {
            "scenario_id": "two-scalars",
            "message": "Calculate using exact values 12 and 15.",
            "expected_route": "computation",
            "expected_url_ids": [],
            "expected_scalar_numeric_ids": ["number-1", "number-2"],
            "expected_series_numeric_ids": [],
            "expected_precision_numeric_id": None,
            "manual_semantic_review": "none",
        },
    )
    directive = AgentColRoutingDirective(
        route="computation",
        computation_intent=ComputationRoutingIntent(
            objective="Calculate using the supplied values.",
            scalar_inputs=(
                ComputationScalarSelection(
                    name="second_value",
                    numeric_id="number-2",
                ),
                ComputationScalarSelection(
                    name="first_value",
                    numeric_id="number-1",
                ),
            ),
        ),
    )

    assert module.evaluate_tool_belt_routing(scenario, directive) == ()


def test_computation_evaluator_accepts_series_groups_in_any_order(
    tmp_path: Path,
) -> None:
    module = load_evaluation_module()
    from agent_col_routing_v2 import (
        AgentColRoutingDirective,
        ComputationRoutingIntent,
        ComputationSeriesSelection,
    )

    scenario = load_one_scenario(
        tmp_path,
        {
            "scenario_id": "two-series",
            "message": "Compare series with values 12, 15, 18, and 21.",
            "expected_route": "computation",
            "expected_url_ids": [],
            "expected_scalar_numeric_ids": [],
            "expected_series_numeric_ids": [
                ["number-1", "number-2"],
                ["number-3", "number-4"],
            ],
            "expected_precision_numeric_id": None,
            "manual_semantic_review": "none",
        },
    )
    directive = AgentColRoutingDirective(
        route="computation",
        computation_intent=ComputationRoutingIntent(
            objective="Compare the supplied series.",
            series_inputs=(
                ComputationSeriesSelection(
                    name="second_series",
                    numeric_ids=("number-3", "number-4"),
                ),
                ComputationSeriesSelection(
                    name="first_series",
                    numeric_ids=("number-1", "number-2"),
                ),
            ),
        ),
    )

    assert module.evaluate_tool_belt_routing(scenario, directive) == ()


def test_route_evaluator_accepts_exact_computation_selection(
    tmp_path: Path,
) -> None:
    module = load_evaluation_module()
    from agent_col_routing_v2 import (
        AgentColRoutingDirective,
        ComputationPrecisionSelection,
        ComputationRoutingIntent,
        ComputationSeriesSelection,
    )

    scenario = load_one_scenario(
        tmp_path,
        {
            "scenario_id": "exact-series",
            "message": (
                "Use values 12, 15, and 18. Report 2 decimal places."
            ),
            "expected_route": "computation",
            "expected_url_ids": [],
            "expected_scalar_numeric_ids": [],
            "expected_series_numeric_ids": [
                ["number-1", "number-2", "number-3"]
            ],
            "expected_precision_numeric_id": "number-4",
            "expected_precision_mode": "decimal_places",
            "manual_semantic_review": "none",
        },
    )
    directive = AgentColRoutingDirective(
        route="computation",
        computation_intent=ComputationRoutingIntent(
            objective="Calculate the requested mean.",
            series_inputs=(
                ComputationSeriesSelection(
                    name="values",
                    numeric_ids=("number-1", "number-2", "number-3"),
                ),
            ),
            precision=ComputationPrecisionSelection(
                mode="decimal_places",
                digits_numeric_id="number-4",
            ),
        ),
    )

    assert module.evaluate_tool_belt_routing(scenario, directive) == ()


def test_fixture_loader_preserves_expected_precision_mode(
    tmp_path: Path,
) -> None:
    definition = {
        "scenario_id": "precision-mode",
        "message": "Use values 12 and 15. Report 2 decimal places.",
        "expected_route": "computation",
        "expected_url_ids": [],
        "expected_scalar_numeric_ids": [],
        "expected_series_numeric_ids": [["number-1", "number-2"]],
        "expected_precision_numeric_id": "number-3",
        "expected_precision_mode": "decimal_places",
        "manual_semantic_review": "none",
    }
    scenario = load_one_scenario(tmp_path, definition)

    assert scenario.expected_precision_mode == "decimal_places"


def test_computation_evaluator_rejects_wrong_precision_mode(
    tmp_path: Path,
) -> None:
    module = load_evaluation_module()
    from agent_col_routing_v2 import (
        AgentColRoutingDirective,
        ComputationPrecisionSelection,
        ComputationRoutingIntent,
        ComputationSeriesSelection,
    )

    scenario = load_one_scenario(
        tmp_path,
        {
            "scenario_id": "precision-mode",
            "message": "Use values 12 and 15. Report 2 decimal places.",
            "expected_route": "computation",
            "expected_url_ids": [],
            "expected_scalar_numeric_ids": [],
            "expected_series_numeric_ids": [["number-1", "number-2"]],
            "expected_precision_numeric_id": "number-3",
            "expected_precision_mode": "decimal_places",
            "manual_semantic_review": "none",
        },
    )
    directive = AgentColRoutingDirective(
        route="computation",
        computation_intent=ComputationRoutingIntent(
            objective="Calculate the requested result.",
            series_inputs=(
                ComputationSeriesSelection(
                    name="values",
                    numeric_ids=("number-1", "number-2"),
                ),
            ),
            precision=ComputationPrecisionSelection(
                mode="significant_figures",
                digits_numeric_id="number-3",
            ),
        ),
    )

    findings = module.evaluate_tool_belt_routing(scenario, directive)

    assert tuple(finding.code for finding in findings) == (
        "precision_selection_mismatch",
    )


def test_default_fixture_covers_complete_tool_belt_and_boundary_cases() -> None:
    module = load_evaluation_module()

    scenarios = module.load_tool_belt_routing_scenarios(
        module.DEFAULT_TOOL_BELT_ROUTING_FIXTURE_PATH
    )

    assert tuple(scenario.scenario_id for scenario in scenarios) == (
        "stable-explanation",
        "explicit-no-tools-with-url",
        "trivial-arithmetic",
        "incidental-status-code",
        "missing-operands",
        "unsupported-fraction",
        "cross-capability-boundary",
        "explicit-single-url",
        "explicit-multiple-urls",
        "numeric-url-source",
        "current-public-fact",
        "current-authoritative-evidence",
        "computation-series",
        "computation-percent-currency",
    )
    assert {scenario.expected_route for scenario in scenarios} == {
        "direct",
        "clarify",
        "source",
        "research",
        "computation",
    }
    by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    assert by_id["explicit-multiple-urls"].expected_url_ids == (
        "url-1",
        "url-2",
    )
    assert by_id["computation-series"].expected_series_numeric_ids == (
        (
            "number-1",
            "number-2",
            "number-3",
            "number-4",
            "number-5",
            "number-6",
        ),
    )
    assert by_id[
        "computation-percent-currency"
    ].expected_scalar_numeric_ids == ("number-1", "number-2")
    assert by_id[
        "computation-percent-currency"
    ].expected_precision_numeric_id == "number-3"
    assert by_id[
        "cross-capability-boundary"
    ].manual_semantic_review == "cross_capability_quality"
