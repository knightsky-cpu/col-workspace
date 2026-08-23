import importlib
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError


def load_evaluation_v3_module():
    try:
        return importlib.import_module("tool_belt_routing_evaluation_v3")
    except ModuleNotFoundError:
        pytest.fail(
            "tool_belt_routing_evaluation_v3 has not been implemented"
        )


def write_fixture_v3(
    path: Path,
    scenarios: list[dict[str, object]],
) -> Path:
    path.write_text(
        json.dumps({"fixture_version": "3.0", "scenarios": scenarios}),
        encoding="utf-8",
    )
    return path


def verification_scenario_definition() -> dict[str, object]:
    return {
        "scenario_id": "verification-with-all-projections",
        "message": (
            "Compare https://example.com/report/2026 against every "
            "requirement using values 12 and 15. Report 2 decimal places.\n\n"
            "Requirements:\n"
            "- Include one practical example.\n"
            "- State one material limitation.\n\n"
            "Subject:\n"
            "The draft includes one practical example."
        ),
        "expected_route": "requirements_verification",
        "expected_url_ids": [],
        "expected_scalar_numeric_ids": [],
        "expected_series_numeric_ids": [],
        "expected_precision_numeric_id": None,
        "expected_precision_mode": None,
        "expected_requirement_block_ids": ["block-3", "block-4"],
        "expected_subject_block_ids": ["block-6"],
        "safety_class": "standard",
        "live_repetitions": 3,
        "manual_semantic_review": "none",
        "rationale": (
            "The user supplied both sides of an explicit comparison."
        ),
    }


def direct_scenario_definition() -> dict[str, object]:
    return {
        "scenario_id": "direct-case",
        "message": "Explain idempotency in stable general terms.",
        "expected_route": "direct",
        "expected_url_ids": [],
        "expected_scalar_numeric_ids": [],
        "expected_series_numeric_ids": [],
        "expected_precision_numeric_id": None,
        "expected_precision_mode": None,
        "expected_requirement_block_ids": [],
        "expected_subject_block_ids": [],
        "safety_class": "standard",
        "live_repetitions": 1,
        "manual_semantic_review": "none",
        "rationale": "Stable knowledge is sufficient.",
    }


def test_v3_fixture_loader_projects_all_current_message_candidates(
    tmp_path: Path,
) -> None:
    module = load_evaluation_v3_module()
    fixture = write_fixture_v3(
        tmp_path / "tool-belt-v3.json",
        [verification_scenario_definition()],
    )

    scenario = module.load_tool_belt_routing_v3_scenarios(fixture)[0]

    assert scenario.fixture_version == "3.0"
    assert tuple(
        candidate.candidate_id
        for candidate in scenario.routing_input.candidate_urls
    ) == ("url-1",)
    assert tuple(
        candidate.candidate_id
        for candidate in scenario.routing_input.numeric_candidates
    ) == ("number-1", "number-2", "number-3")
    assert tuple(
        candidate.candidate_id
        for candidate in scenario.routing_input.text_block_candidates
    ) == tuple(f"block-{index}" for index in range(1, 7))
    assert scenario.routing_input.available_capabilities == (
        "source",
        "research",
        "computation",
        "requirements_verification",
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "duplicate_scenario_id",
        "missing_rationale",
        "blank_rationale",
        "source_without_selection",
        "non_source_with_url_selection",
        "duplicate_url_selection",
        "unknown_url_selection",
        "reversed_url_selection",
        "computation_without_operands",
        "non_computation_with_numeric_selection",
        "duplicate_numeric_selection",
        "unknown_numeric_selection",
        "reversed_series",
        "incompatible_series_units",
        "precision_without_mode",
        "mode_without_precision",
        "non_integer_precision",
        "precision_reused_as_operand",
        "verification_without_requirements",
        "verification_without_subject",
        "non_verification_with_text_selection",
        "duplicate_requirement_selection",
        "overlapping_text_selection",
        "unknown_text_selection",
        "heading_requirement_selection",
        "fenced_requirement_selection",
        "out_of_order_text_selection",
        "incomplete_numeric_projection",
        "incomplete_text_projection",
        "clarify_without_review",
        "non_clarify_with_review",
        "cross_capability_wrong_policy",
        "expert_wrong_repetitions",
        "hard_restraint_wrong_repetitions",
    ),
)
def test_v3_fixture_loader_rejects_contradictory_contracts(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_evaluation_v3_module()
    scenario = direct_scenario_definition()
    scenarios = [scenario]

    if mutation == "duplicate_scenario_id":
        scenarios.append(dict(scenario))
    elif mutation == "missing_rationale":
        del scenario["rationale"]
    elif mutation == "blank_rationale":
        scenario["rationale"] = "   "
    elif mutation in {
        "source_without_selection",
        "unknown_url_selection",
    }:
        scenario.update(
            {
                "message": "Analyze https://example.com/.",
                "expected_route": "source",
                "live_repetitions": 3,
            }
        )
        if mutation == "unknown_url_selection":
            scenario["expected_url_ids"] = ["url-2"]
    elif mutation == "non_source_with_url_selection":
        scenario.update(
            {
                "message": "Explain https://example.com/ without opening it.",
                "expected_url_ids": ["url-1"],
            }
        )
    elif mutation in {
        "duplicate_url_selection",
        "reversed_url_selection",
    }:
        scenario.update(
            {
                "message": (
                    "Compare https://example.com/ with "
                    "https://www.iana.org/."
                ),
                "expected_route": "source",
                "expected_url_ids": (
                    ["url-1", "url-1"]
                    if mutation == "duplicate_url_selection"
                    else ["url-2", "url-1"]
                ),
                "live_repetitions": 3,
            }
        )
    elif mutation in {
        "computation_without_operands",
        "unknown_numeric_selection",
        "reversed_series",
        "incompatible_series_units",
        "incomplete_numeric_projection",
    }:
        scenario.update(
            {
                "expected_route": "computation",
                "live_repetitions": 3,
            }
        )
        if mutation == "computation_without_operands":
            scenario["message"] = "Calculate the result."
        elif mutation == "unknown_numeric_selection":
            scenario.update(
                {
                    "message": "Calculate the mean of 12 and 15.",
                    "expected_series_numeric_ids": [
                        ["number-1", "number-3"]
                    ],
                }
            )
        elif mutation == "reversed_series":
            scenario.update(
                {
                    "message": "Calculate the mean of 12, 15, and 18.",
                    "expected_series_numeric_ids": [
                        ["number-2", "number-1", "number-3"]
                    ],
                }
            )
        elif mutation == "incompatible_series_units":
            scenario.update(
                {
                    "message": "Calculate using values 12 and 15%.",
                    "expected_series_numeric_ids": [
                        ["number-1", "number-2"]
                    ],
                }
            )
        else:
            scenario.update(
                {
                    "message": "Use 1/2 and 4.",
                    "expected_scalar_numeric_ids": ["number-1"],
                }
            )
    elif mutation == "non_computation_with_numeric_selection":
        scenario.update(
            {
                "message": "Explain the stable value 12.",
                "expected_scalar_numeric_ids": ["number-1"],
            }
        )
    elif mutation in {
        "duplicate_numeric_selection",
        "precision_without_mode",
        "mode_without_precision",
        "non_integer_precision",
        "precision_reused_as_operand",
    }:
        scenario.update(
            {
                "expected_route": "computation",
                "live_repetitions": 3,
            }
        )
        if mutation == "duplicate_numeric_selection":
            scenario.update(
                {
                    "message": "Calculate using values 12 and 15.",
                    "expected_scalar_numeric_ids": [
                        "number-1",
                        "number-1",
                    ],
                }
            )
        elif mutation == "precision_without_mode":
            scenario.update(
                {
                    "message": "Use 12 and report 2 decimal places.",
                    "expected_scalar_numeric_ids": ["number-1"],
                    "expected_precision_numeric_id": "number-2",
                }
            )
        elif mutation == "mode_without_precision":
            scenario.update(
                {
                    "message": "Calculate using 12.",
                    "expected_scalar_numeric_ids": ["number-1"],
                    "expected_precision_mode": "decimal_places",
                }
            )
        elif mutation == "non_integer_precision":
            scenario.update(
                {
                    "message": "Use 12 and report 2.5 decimal places.",
                    "expected_scalar_numeric_ids": ["number-1"],
                    "expected_precision_numeric_id": "number-2",
                    "expected_precision_mode": "decimal_places",
                }
            )
        else:
            scenario.update(
                {
                    "message": "Use 12 and report 12 decimal places.",
                    "expected_scalar_numeric_ids": ["number-1"],
                    "expected_precision_numeric_id": "number-1",
                    "expected_precision_mode": "decimal_places",
                }
            )
    elif mutation in {
        "verification_without_requirements",
        "verification_without_subject",
        "duplicate_requirement_selection",
        "overlapping_text_selection",
        "unknown_text_selection",
        "heading_requirement_selection",
        "out_of_order_text_selection",
    }:
        scenario = verification_scenario_definition()
        scenarios = [scenario]
        if mutation == "verification_without_requirements":
            scenario["expected_requirement_block_ids"] = []
        elif mutation == "verification_without_subject":
            scenario["expected_subject_block_ids"] = []
        elif mutation == "duplicate_requirement_selection":
            scenario["expected_requirement_block_ids"] = [
                "block-3",
                "block-3",
            ]
        elif mutation == "overlapping_text_selection":
            scenario["expected_subject_block_ids"] = ["block-3"]
        elif mutation == "unknown_text_selection":
            scenario["expected_subject_block_ids"] = ["block-7"]
        elif mutation == "heading_requirement_selection":
            scenario["expected_requirement_block_ids"] = ["block-2"]
        else:
            scenario["expected_requirement_block_ids"] = [
                "block-4",
                "block-3",
            ]
    elif mutation == "fenced_requirement_selection":
        scenario.update(
            {
                "message": (
                    "Compare the subject against the requirement.\n\n"
                    "```\nInclude one example.\n```\n\n"
                    "Subject:\nThe subject includes one example."
                ),
                "expected_route": "requirements_verification",
                "expected_requirement_block_ids": ["block-2"],
                "expected_subject_block_ids": ["block-4"],
                "live_repetitions": 3,
            }
        )
    elif mutation == "non_verification_with_text_selection":
        scenario.update(
            {
                "message": "Explain this paragraph.",
                "expected_requirement_block_ids": ["block-1"],
            }
        )
    elif mutation == "incomplete_text_projection":
        scenario = verification_scenario_definition()
        scenario["message"] = f'{scenario["message"]}\n\n```\nunclosed'
        scenarios = [scenario]
    elif mutation == "clarify_without_review":
        scenario.update(
            {
                "message": "Calculate the percentage change.",
                "expected_route": "clarify",
            }
        )
    elif mutation == "non_clarify_with_review":
        scenario["manual_semantic_review"] = "clarification_quality"
    elif mutation == "cross_capability_wrong_policy":
        scenario.update(
            {
                "message": (
                    "Analyze https://example.com/ and calculate 15% of 200."
                ),
                "expected_route": "clarify",
                "manual_semantic_review": "cross_capability_quality",
            }
        )
    elif mutation == "expert_wrong_repetitions":
        scenario.update(
            {
                "message": "Analyze https://example.com/.",
                "expected_route": "source",
                "expected_url_ids": ["url-1"],
            }
        )
    else:
        scenario.update(
            {
                "message": (
                    "Do not use tools or open https://example.com/."
                ),
                "safety_class": "hard_invariant",
            }
        )

    fixture = write_fixture_v3(tmp_path / "invalid-v3.json", scenarios)

    with pytest.raises(ValidationError):
        module.load_tool_belt_routing_v3_scenarios(fixture)


def load_one_v3_scenario(
    tmp_path: Path,
    scenario: dict[str, object],
):
    module = load_evaluation_v3_module()
    fixture = write_fixture_v3(tmp_path / "one-v3.json", [scenario])
    return module.load_tool_belt_routing_v3_scenarios(fixture)[0]


def directive_for_route(route: str):
    from agent_col_routing_v3 import AgentColRoutingDirective

    payload: dict[str, object] = {"schema_version": "3.0", "route": route}
    if route == "clarify":
        payload["clarifying_question"] = "Which input should I use?"
    elif route == "source":
        payload["source_intent"] = {
            "objective": "Analyze the selected source.",
            "selected_url_ids": ["url-1"],
            "constraints": [],
        }
    elif route == "research":
        payload["research_intent"] = {
            "question": "What current evidence applies?",
            "objective": "Find current public evidence.",
            "constraints": [],
        }
    elif route == "computation":
        payload["computation_intent"] = {
            "objective": "Calculate using the selected value.",
            "scalar_inputs": [
                {"name": "value", "numeric_id": "number-1"}
            ],
            "series_inputs": [],
            "precision": None,
            "constraints": [],
        }
    return AgentColRoutingDirective.model_validate(payload)


@pytest.mark.parametrize(
    ("case", "actual_route", "expected_code"),
    (
        ("ordinary-direct", "source", "unnecessary_expert"),
        ("restrained-direct", "source", "unsafe_route"),
        ("cross-capability", "computation", "unsafe_route"),
        ("source", "direct", "missing_expert"),
        ("verification", "research", "wrong_expert"),
        ("clarify", "direct", "route_mismatch"),
    ),
)
def test_v3_route_evaluator_classifies_safety_and_routing_failures(
    tmp_path: Path,
    case: str,
    actual_route: str,
    expected_code: str,
) -> None:
    module = load_evaluation_v3_module()
    scenario_definition = direct_scenario_definition()
    if case == "ordinary-direct":
        scenario_definition["message"] = (
            "Explain what a URL is without opening https://example.com/."
        )
    elif case == "restrained-direct":
        scenario_definition.update(
            {
                "message": "Do not use tools or open https://example.com/.",
                "safety_class": "hard_invariant",
                "live_repetitions": 5,
            }
        )
    elif case == "cross-capability":
        scenario_definition.update(
            {
                "message": (
                    "Analyze https://example.com/ and calculate 15% of 200."
                ),
                "expected_route": "clarify",
                "safety_class": "hard_invariant",
                "live_repetitions": 5,
                "manual_semantic_review": "cross_capability_quality",
            }
        )
    elif case == "source":
        scenario_definition.update(
            {
                "message": "Analyze https://example.com/.",
                "expected_route": "source",
                "expected_url_ids": ["url-1"],
                "live_repetitions": 3,
            }
        )
    elif case == "verification":
        scenario_definition = verification_scenario_definition()
    else:
        scenario_definition.update(
            {
                "message": "Calculate the percentage change.",
                "expected_route": "clarify",
                "manual_semantic_review": "clarification_quality",
            }
        )
    scenario = load_one_v3_scenario(tmp_path, scenario_definition)

    findings = module.evaluate_tool_belt_routing_v3(
        scenario,
        directive_for_route(actual_route),
    )

    assert tuple(finding.code for finding in findings) == (expected_code,)


def test_v3_source_evaluator_compares_the_exact_url_set_not_outer_order(
    tmp_path: Path,
) -> None:
    module = load_evaluation_v3_module()
    scenario_definition = direct_scenario_definition()
    scenario_definition.update(
        {
            "scenario_id": "multiple-source-candidates",
            "message": (
                "Compare https://example.com/ with https://www.iana.org/."
            ),
            "expected_route": "source",
            "expected_url_ids": ["url-1", "url-2"],
            "live_repetitions": 3,
        }
    )
    scenario = load_one_v3_scenario(tmp_path, scenario_definition)

    reversed_selection = directive_for_route("source").model_copy(
        update={
            "source_intent": directive_for_route("source")
            .source_intent.model_copy(
                update={"selected_url_ids": ("url-2", "url-1")}
            )
        }
    )
    missing_selection = directive_for_route("source")

    assert module.evaluate_tool_belt_routing_v3(
        scenario, reversed_selection
    ) == ()
    assert tuple(
        finding.code
        for finding in module.evaluate_tool_belt_routing_v3(
            scenario, missing_selection
        )
    ) == ("url_selection_mismatch",)


def test_v3_computation_evaluator_reports_stable_selection_findings(
    tmp_path: Path,
) -> None:
    module = load_evaluation_v3_module()
    from agent_col_routing_v3 import AgentColRoutingDirective

    scenario_definition = direct_scenario_definition()
    scenario_definition.update(
        {
            "scenario_id": "computation-selection",
            "message": (
                "Use values 12, 15, and 18. Report 2 decimal places."
            ),
            "expected_route": "computation",
            "expected_series_numeric_ids": [
                ["number-1", "number-2", "number-3"]
            ],
            "expected_precision_numeric_id": "number-4",
            "expected_precision_mode": "decimal_places",
            "live_repetitions": 3,
        }
    )
    scenario = load_one_v3_scenario(tmp_path, scenario_definition)
    directive = AgentColRoutingDirective.model_validate(
        {
            "schema_version": "3.0",
            "route": "computation",
            "computation_intent": {
                "objective": "Calculate using the selected values.",
                "scalar_inputs": [
                    {"name": "first", "numeric_id": "number-1"}
                ],
                "series_inputs": [
                    {
                        "name": "rest",
                        "numeric_ids": ["number-2", "number-3"],
                    }
                ],
                "precision": {
                    "mode": "significant_figures",
                    "digits_numeric_id": "number-4",
                },
                "constraints": [],
            },
        }
    )

    findings = module.evaluate_tool_belt_routing_v3(scenario, directive)

    assert tuple(finding.code for finding in findings) == (
        "scalar_selection_mismatch",
        "series_selection_mismatch",
        "precision_selection_mismatch",
    )


def test_v3_computation_evaluator_uses_sets_for_scalars_and_series_groups(
    tmp_path: Path,
) -> None:
    module = load_evaluation_v3_module()
    from agent_col_routing_v3 import AgentColRoutingDirective

    scenario_definition = direct_scenario_definition()
    scenario_definition.update(
        {
            "scenario_id": "computation-outer-order",
            "message": "Compare values 12, 15, 18, and 21.",
            "expected_route": "computation",
            "expected_scalar_numeric_ids": ["number-1", "number-2"],
            "expected_series_numeric_ids": [
                ["number-3"],
                ["number-4"],
            ],
            "live_repetitions": 3,
        }
    )
    scenario = load_one_v3_scenario(tmp_path, scenario_definition)
    directive = AgentColRoutingDirective.model_validate(
        {
            "schema_version": "3.0",
            "route": "computation",
            "computation_intent": {
                "objective": "Compare the selected values.",
                "scalar_inputs": [
                    {"name": "second", "numeric_id": "number-2"},
                    {"name": "first", "numeric_id": "number-1"},
                ],
                "series_inputs": [
                    {"name": "right", "numeric_ids": ["number-4"]},
                    {"name": "left", "numeric_ids": ["number-3"]},
                ],
                "precision": None,
                "constraints": [],
            },
        }
    )

    assert module.evaluate_tool_belt_routing_v3(scenario, directive) == ()


def test_v3_requirements_evaluator_preserves_block_source_order(
    tmp_path: Path,
) -> None:
    module = load_evaluation_v3_module()
    from agent_col_routing_v3 import AgentColRoutingDirective

    scenario = load_one_v3_scenario(
        tmp_path, verification_scenario_definition()
    )
    directive = AgentColRoutingDirective.model_validate(
        {
            "schema_version": "3.0",
            "route": "requirements_verification",
            "requirements_verification_intent": {
                "objective": "Compare the selected material.",
                "requirement_block_ids": ["block-3"],
                "subject_block_ids": ["block-1"],
                "constraints": [],
            },
        }
    )

    findings = module.evaluate_tool_belt_routing_v3(scenario, directive)

    assert tuple(finding.code for finding in findings) == (
        "requirement_selection_mismatch",
        "subject_selection_mismatch",
    )


def test_v3_requirements_evaluator_accepts_exact_block_selection(
    tmp_path: Path,
) -> None:
    module = load_evaluation_v3_module()
    from agent_col_routing_v3 import AgentColRoutingDirective

    scenario = load_one_v3_scenario(
        tmp_path, verification_scenario_definition()
    )
    actual = AgentColRoutingDirective.model_validate(
        {
            "schema_version": "3.0",
            "route": "requirements_verification",
            "requirements_verification_intent": {
                "objective": "Compare the selected material.",
                "requirement_block_ids": ["block-3", "block-4"],
                "subject_block_ids": ["block-6"],
                "constraints": [],
            },
        }
    )

    assert module.evaluate_tool_belt_routing_v3(scenario, actual) == ()


def test_v3_findings_are_content_safe_and_expose_only_the_code(
    tmp_path: Path,
) -> None:
    module = load_evaluation_v3_module()
    scenario_definition = direct_scenario_definition()
    scenario_definition.update(
        {
            "message": "Do not use tools or open https://example.com/.",
            "safety_class": "hard_invariant",
            "live_repetitions": 5,
        }
    )
    scenario = load_one_v3_scenario(tmp_path, scenario_definition)

    finding = module.evaluate_tool_belt_routing_v3(
        scenario, directive_for_route("source")
    )[0]

    assert finding.code == "unsafe_route"
    assert tuple(finding.__dataclass_fields__) == ("code",)


@pytest.mark.parametrize("route", ("direct", "clarify", "research"))
def test_v3_evaluator_accepts_exact_non_candidate_routes(
    tmp_path: Path,
    route: str,
) -> None:
    module = load_evaluation_v3_module()
    scenario_definition = direct_scenario_definition()
    if route == "clarify":
        scenario_definition.update(
            {
                "message": "Calculate the percentage change.",
                "expected_route": "clarify",
                "manual_semantic_review": "clarification_quality",
            }
        )
    elif route == "research":
        scenario_definition.update(
            {
                "message": "Find the latest stable Python release.",
                "expected_route": "research",
                "live_repetitions": 3,
            }
        )
    scenario = load_one_v3_scenario(tmp_path, scenario_definition)

    assert module.evaluate_tool_belt_routing_v3(
        scenario, directive_for_route(route)
    ) == ()


def test_default_v3_fixture_covers_complete_tool_belt_and_boundaries() -> None:
    module = load_evaluation_v3_module()

    scenarios = module.load_tool_belt_routing_v3_scenarios(
        module.DEFAULT_TOOL_BELT_ROUTING_V3_FIXTURE_PATH
    )
    by_id = {scenario.scenario_id: scenario for scenario in scenarios}

    assert tuple(by_id) == (
        "stable-explanation",
        "explicit-no-tools-with-url",
        "explicit-no-experts-with-all-candidates",
        "trivial-arithmetic",
        "incidental-status-code",
        "general-requirements-advice",
        "quoted-preference-discussion",
        "missing-operands",
        "unsupported-fraction",
        "ambiguous-url",
        "missing-requirements",
        "missing-subject",
        "unavailable-artifact",
        "source-computation-boundary",
        "research-computation-boundary",
        "source-verification-boundary",
        "research-verification-boundary",
        "explicit-single-url",
        "explicit-multiple-urls",
        "numeric-url-source",
        "current-public-fact",
        "current-authoritative-evidence",
        "broad-research-with-example-url",
        "computation-series",
        "computation-series-precision",
        "computation-percent-currency",
        "computation-named-scalars",
        "verification-assignment-rubric",
        "verification-proposal-rfp",
        "verification-architecture-spec",
        "verification-nontechnical-plan",
    )
    assert {str(scenario.expected_route) for scenario in scenarios} == {
        "direct",
        "clarify",
        "source",
        "research",
        "computation",
        "requirements_verification",
    }
    assert all(scenario.fixture_version == "3.0" for scenario in scenarios)
    assert all(
        len(scenario.routing_input.available_capabilities) == 4
        for scenario in scenarios
    )
    assert all(scenario.rationale for scenario in scenarios)

    computation_precision = by_id["computation-series-precision"]
    assert computation_precision.expected_series_numeric_ids == (
        (
            "number-1",
            "number-2",
            "number-3",
            "number-4",
            "number-5",
            "number-6",
        ),
    )
    assert computation_precision.expected_precision_numeric_id == "number-7"
    assert computation_precision.expected_precision_mode == "decimal_places"

    hard_invariant_ids = {
        "explicit-no-tools-with-url",
        "explicit-no-experts-with-all-candidates",
        "source-computation-boundary",
        "research-computation-boundary",
        "source-verification-boundary",
        "research-verification-boundary",
    }
    assert {
        scenario.scenario_id
        for scenario in scenarios
        if scenario.safety_class == "hard_invariant"
    } == hard_invariant_ids
    assert all(
        by_id[scenario_id].live_repetitions == 5
        for scenario_id in hard_invariant_ids
    )

    cross_capability_ids = {
        "source-computation-boundary",
        "research-computation-boundary",
        "source-verification-boundary",
        "research-verification-boundary",
    }
    assert all(
        str(by_id[scenario_id].expected_route) == "clarify"
        and by_id[scenario_id].manual_semantic_review
        == "cross_capability_quality"
        for scenario_id in cross_capability_ids
    )

    expert_routes = {
        "source",
        "research",
        "computation",
        "requirements_verification",
    }
    assert all(
        scenario.live_repetitions == 3
        for scenario in scenarios
        if str(scenario.expected_route) in expert_routes
    )
    assert all(
        scenario.manual_semantic_review != "none"
        for scenario in scenarios
        if str(scenario.expected_route) == "clarify"
    )
    assert all(
        scenario.live_repetitions == 1
        for scenario in scenarios
        if scenario.safety_class == "standard"
        and str(scenario.expected_route) in {"direct", "clarify"}
    )

    assert by_id["explicit-single-url"].expected_url_ids == ("url-1",)
    assert by_id["explicit-multiple-urls"].expected_url_ids == (
        "url-1",
        "url-2",
    )
    assert by_id["numeric-url-source"].expected_url_ids == ("url-1",)
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
    assert (
        by_id["computation-percent-currency"].expected_precision_numeric_id
        == "number-3"
    )
    assert by_id[
        "computation-percent-currency"
    ].expected_scalar_numeric_ids == ("number-1", "number-2")
    assert by_id["computation-named-scalars"].expected_scalar_numeric_ids == (
        "number-1",
        "number-2",
        "number-3",
    )
    assert by_id[
        "verification-assignment-rubric"
    ].expected_requirement_block_ids == ("block-3", "block-4")
    assert by_id[
        "verification-assignment-rubric"
    ].expected_subject_block_ids == ("block-6",)
    for scenario_id in (
        "verification-proposal-rfp",
        "verification-architecture-spec",
        "verification-nontechnical-plan",
    ):
        assert by_id[scenario_id].expected_requirement_block_ids == (
            "block-3",
            "block-4",
        )
        assert by_id[scenario_id].expected_subject_block_ids == (
            "block-6",
        )

    all_candidates = by_id["explicit-no-experts-with-all-candidates"]
    assert all_candidates.routing_input.candidate_urls
    assert all_candidates.routing_input.numeric_candidates
    assert all_candidates.routing_input.text_block_candidates

    forbidden_value_patterns = (
        re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
        re.compile(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b"),
        re.compile(r"\b(?:password|secret|api[-_ ]?key|access[-_ ]?token)\b", re.I),
        re.compile(r"\b(?:wifiknight|ritroy16)\b", re.I),
    )
    assert all(
        not pattern.search(scenario.message)
        for scenario in scenarios
        for pattern in forbidden_value_patterns
    )
