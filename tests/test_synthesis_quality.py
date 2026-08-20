import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import PersonalizationAdaptation, SynthesisBlueprint


def valid_scenario_definition() -> dict[str, object]:
    return {
        "scenario_id": "small-api",
        "source_text": "Design a small asynchronous API.",
        "profile": {},
        "required_concepts": [
            {
                "concept_id": "api-framework",
                "phrases": ["fastapi", "asynchronous api"],
            }
        ],
        "forbidden_claims": ["deploy to kubernetes immediately"],
        "expected_adaptation_keys": [],
        "min_architectural_decisions": 1,
        "max_architectural_decisions": 4,
        "min_clarifying_questions": 1,
        "max_clarifying_questions": 3,
        "min_roadmap_milestones": 1,
        "max_roadmap_milestones": 4,
        "min_diagnostic_warnings": 0,
        "max_diagnostic_warnings": 4,
    }


@pytest.fixture
def blueprint() -> SynthesisBlueprint:
    return SynthesisBlueprint.model_validate(
        {
            "synthesized_conceptual_model": {
                "project_name": "Study API",
                "core_value_proposition": "Plans assignments with FastAPI.",
                "in_scope": ["Asynchronous API"],
            },
            "personalization_trace": {},
            "architectural_decisions": [
                {
                    "component_name": "API",
                    "proposed_solution": "FastAPI",
                    "rationale": "Matches the asynchronous Python stack.",
                    "alternatives": [
                        {
                            "option_name": "Flask",
                            "tradeoff": "Uses synchronous handlers.",
                            "reason_not_selected": "Does not match the stack.",
                        }
                    ],
                }
            ],
            "socratic_clarifying_questions": [
                {
                    "question_text": "Which client comes first?",
                    "why_this_matters": "It determines the API contract.",
                    "suggested_options": [
                        {"label": "Web", "impact": "Browser access."},
                        {"label": "CLI", "impact": "Terminal access."},
                    ],
                }
            ],
            "step_by_step_execution_roadmap": [
                {
                    "phase_name": "Phase 1",
                    "objective": "Define the API.",
                    "expected_deliverable": "A tested endpoint.",
                    "micro_tasks": [
                        {
                            "task_description": "Write the endpoint.",
                            "complexity_level": "Low",
                            "verification_steps": ["Run the API test."],
                        }
                    ],
                }
            ],
            "diagnostic_warnings": [
                {
                    "affected_component": "API",
                    "severity": "Medium",
                    "risk_identified": "Requests may fail.",
                    "preventative_guidance": "Use bounded retries.",
                }
            ],
        }
    )


def test_evaluator_reports_missing_required_concept_without_content(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_quality import (
        QualityScenario,
        RequiredConcept,
        evaluate_blueprint,
    )

    scenario = QualityScenario(
        scenario_id="private-scenario",
        fixture_version="1.1",
        source_text="private-source",
        profile={},
        required_concepts=(
            RequiredConcept(
                concept_id="api-framework",
                phrases=("fastapi", "starlette"),
            ),
            RequiredConcept(
                concept_id="persistence",
                phrases=(
                    "private-firestore-phrase",
                    "document database",
                ),
            ),
        ),
    )

    findings = evaluate_blueprint(scenario, blueprint)

    assert tuple(finding.code for finding in findings) == (
        "missing_required_concept:persistence",
    )
    assert "private-firestore-phrase" not in repr(findings)
    assert "private-source" not in repr(findings)


def test_agent_col_role_accepts_collaborative_engineering_assistant(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_quality import (
        QualityScenario,
        evaluate_blueprint,
        load_quality_scenarios,
    )

    agent_col = next(
        scenario
        for scenario in load_quality_scenarios()
        if scenario.scenario_id == "agent-col-architecture"
    )
    collaborative_role = next(
        concept
        for concept in agent_col.required_concepts
        if concept.concept_id == "collaborative-role"
    )
    blueprint.synthesized_conceptual_model.core_value_proposition = (
        "A collaborative engineering assistant for students."
    )
    scenario = QualityScenario(
        scenario_id="equivalent-collaborative-role",
        fixture_version="1.1",
        source_text="Design an engineering assistant.",
        profile={},
        required_concepts=(collaborative_role,),
    )

    findings = evaluate_blueprint(scenario, blueprint)

    assert findings == ()


def test_evaluator_reports_forbidden_claim_case_insensitively(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_quality import (
        QualityScenario,
        RequiredConcept,
        evaluate_blueprint,
    )

    scenario = QualityScenario(
        scenario_id="forbidden-claim",
        fixture_version="1.1",
        source_text="Evaluate a small API.",
        profile={},
        forbidden_claims=("fAsTaPi",),
    )

    findings = evaluate_blueprint(scenario, blueprint)

    assert tuple(finding.code for finding in findings) == (
        "forbidden_claim",
    )


def test_evaluator_rejects_semantically_invalid_blueprint_first(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_quality import (
        QualityScenario,
        RequiredConcept,
        evaluate_blueprint,
    )

    blueprint.synthesized_conceptual_model.out_of_scope = [" API "]
    blueprint.synthesized_conceptual_model.in_scope = ["api"]
    scenario = QualityScenario(
        scenario_id="invalid-blueprint",
        fixture_version="1.1",
        source_text="private-source",
        profile={},
        required_concepts=(
            RequiredConcept(
                concept_id="private-safe-rule",
                phrases=("private-missing-concept",),
            ),
        ),
    )

    findings = evaluate_blueprint(scenario, blueprint)

    assert tuple(finding.code for finding in findings) == (
        "invalid_blueprint",
    )
    assert "private-missing-concept" not in repr(findings)


@pytest.mark.parametrize(
    ("constraint", "value", "expected_code"),
    (
        ("min_architectural_decisions", 2, "too_few_decisions"),
        ("max_architectural_decisions", 0, "too_many_decisions"),
        ("min_clarifying_questions", 2, "too_few_questions"),
        ("max_clarifying_questions", 0, "too_many_questions"),
        ("min_roadmap_milestones", 2, "too_few_milestones"),
        ("max_roadmap_milestones", 0, "too_many_milestones"),
        ("min_diagnostic_warnings", 2, "too_few_warnings"),
        ("max_diagnostic_warnings", 0, "too_many_warnings"),
    ),
)
def test_evaluator_reports_structural_expectation_failure(
    blueprint: SynthesisBlueprint,
    constraint: str,
    value: int,
    expected_code: str,
) -> None:
    from synthesis_quality import QualityScenario, evaluate_blueprint

    scenario = QualityScenario(
        scenario_id="structural-expectation",
        fixture_version="1.1",
        source_text="Evaluate structure.",
        profile={},
        **{constraint: value},
    )

    findings = evaluate_blueprint(scenario, blueprint)

    assert tuple(finding.code for finding in findings) == (
        expected_code,
    )


def test_evaluator_reports_missing_expected_adaptation(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_quality import QualityScenario, evaluate_blueprint

    scenario = QualityScenario(
        scenario_id="profile-aware",
        fixture_version="1.1",
        source_text="Adapt this design.",
        profile={"experience_level": "student"},
        expected_adaptation_keys=("experience_level",),
    )

    findings = evaluate_blueprint(scenario, blueprint)

    assert tuple(finding.code for finding in findings) == (
        "missing_expected_adaptation",
    )


def test_evaluator_reports_unexpected_adaptation(
    blueprint: SynthesisBlueprint,
) -> None:
    from synthesis_quality import QualityScenario, evaluate_blueprint

    blueprint.personalization_trace.adaptations = [
        PersonalizationAdaptation(
            profile_key="experience_level",
            architecture_change="Adds smaller implementation steps.",
            reason="Supports a student developer.",
        )
    ]
    scenario = QualityScenario(
        scenario_id="no-personalization-expected",
        fixture_version="1.1",
        source_text="Design a generic API.",
        profile={"experience_level": "student"},
    )

    findings = evaluate_blueprint(scenario, blueprint)

    assert tuple(finding.code for finding in findings) == (
        "unexpected_adaptation",
    )


def write_fixture(path: Path, scenarios: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "fixture_version": "1.1",
                "scenarios": scenarios,
            }
        ),
        encoding="utf-8",
    )


def write_fixture_document(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def test_load_quality_scenarios_returns_immutable_versioned_contract(
    tmp_path: Path,
) -> None:
    from synthesis_quality import load_quality_scenarios

    fixture_path = tmp_path / "quality.json"
    write_fixture(fixture_path, [valid_scenario_definition()])

    scenarios = load_quality_scenarios(fixture_path)

    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "small-api"
    assert scenarios[0].fixture_version == "1.1"
    assert scenarios[0].required_concepts[0].concept_id == "api-framework"
    assert scenarios[0].required_concepts[0].phrases == (
        "fastapi",
        "asynchronous api",
    )
    with pytest.raises(FrozenInstanceError):
        scenarios[0].scenario_id = "changed"  # type: ignore[misc]


def test_load_quality_scenarios_rejects_duplicate_ids(
    tmp_path: Path,
) -> None:
    from synthesis_quality import load_quality_scenarios

    fixture_path = tmp_path / "quality.json"
    scenario = valid_scenario_definition()
    write_fixture(fixture_path, [scenario, scenario])

    with pytest.raises(ValidationError):
        load_quality_scenarios(fixture_path)


@pytest.mark.parametrize(
    "invalid_case",
    (
        "unsupported_version",
        "empty_scenarios",
        "extra_field",
        "invalid_scenario_id",
        "blank_source",
        "unsupported_profile_key",
        "empty_concept_phrases",
        "duplicate_concept_id",
        "blank_phrase",
        "missing_expected_profile_key",
        "duplicate_expected_key",
        "negative_bound",
        "bound_above_schema_limit",
        "inverted_bounds",
    ),
)
def test_load_quality_scenarios_rejects_malformed_definition(
    tmp_path: Path,
    invalid_case: str,
) -> None:
    from synthesis_quality import load_quality_scenarios

    scenario = valid_scenario_definition()
    document: dict[str, object] = {
        "fixture_version": "1.1",
        "scenarios": [scenario],
    }
    if invalid_case == "unsupported_version":
        document["fixture_version"] = "2.0"
    elif invalid_case == "empty_scenarios":
        document["scenarios"] = []
    elif invalid_case == "extra_field":
        scenario["unexpected"] = True
    elif invalid_case == "invalid_scenario_id":
        scenario["scenario_id"] = "Invalid ID"
    elif invalid_case == "blank_source":
        scenario["source_text"] = "   "
    elif invalid_case == "unsupported_profile_key":
        scenario["profile"] = {"private_note": "secret"}
    elif invalid_case == "empty_concept_phrases":
        scenario["required_concepts"] = [
            {"concept_id": "empty", "phrases": []}
        ]
    elif invalid_case == "duplicate_concept_id":
        scenario["required_concepts"] = [
            {"concept_id": "duplicate", "phrases": ["one"]},
            {"concept_id": "duplicate", "phrases": ["two"]},
        ]
    elif invalid_case == "blank_phrase":
        scenario["forbidden_claims"] = ["   "]
    elif invalid_case == "missing_expected_profile_key":
        scenario["expected_adaptation_keys"] = ["experience_level"]
    elif invalid_case == "duplicate_expected_key":
        scenario["profile"] = {"experience_level": "student"}
        scenario["expected_adaptation_keys"] = [
            "experience_level",
            "experience_level",
        ]
    elif invalid_case == "negative_bound":
        scenario["min_architectural_decisions"] = -1
    elif invalid_case == "bound_above_schema_limit":
        scenario["max_architectural_decisions"] = 9
    elif invalid_case == "inverted_bounds":
        scenario["min_architectural_decisions"] = 4
        scenario["max_architectural_decisions"] = 2
    else:
        raise AssertionError(f"Unknown invalid case: {invalid_case}")
    fixture_path = tmp_path / "quality.json"
    write_fixture_document(fixture_path, document)

    with pytest.raises(ValidationError):
        load_quality_scenarios(fixture_path)


def test_default_quality_fixture_contains_eight_approved_scenarios() -> None:
    from synthesis_quality import load_quality_scenarios

    scenarios = load_quality_scenarios()

    assert tuple(scenario.scenario_id for scenario in scenarios) == (
        "small-api",
        "contradictory-requirements",
        "empty-profile",
        "profile-aware-adaptation",
        "prompt-injection",
        "agent-col-architecture",
        "ambiguous-requirements",
        "repetitive-input",
    )
