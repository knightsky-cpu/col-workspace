import json

import pytest

from schemas import SynthesisBlueprint


@pytest.fixture
def valid_blueprint() -> SynthesisBlueprint:
    return SynthesisBlueprint.model_validate(
        {
            "synthesized_conceptual_model": {
                "project_name": "Study Partner",
                "core_value_proposition": (
                    "Turns rubrics into executable plans."
                ),
                "in_scope": ["Planning"],
                "out_of_scope": ["Automatic deployment"],
                "assumptions": ["The user reviews each milestone"],
            },
            "personalization_trace": {
                "adaptations": [
                    {
                        "profile_key": "experience_level",
                        "architecture_change": (
                            "Adds smaller implementation steps."
                        ),
                        "reason": "Supports an early-career developer.",
                    }
                ]
            },
            "architectural_decisions": [
                {
                    "component_name": "API",
                    "proposed_solution": "FastAPI",
                    "rationale": "Matches the asynchronous backend.",
                    "alternatives": [
                        {
                            "option_name": "Flask",
                            "tradeoff": "Synchronous by default.",
                            "reason_not_selected": (
                                "Would diverge from the backend."
                            ),
                        }
                    ],
                }
            ],
            "socratic_clarifying_questions": [
                {
                    "question_text": "Which client comes first?",
                    "why_this_matters": "It sets the first API contract.",
                    "suggested_options": [
                        {
                            "label": "Web",
                            "impact": "Reuses the existing host.",
                        },
                        {
                            "label": "CLI",
                            "impact": "Optimizes terminal workflows.",
                        },
                    ],
                }
            ],
            "step_by_step_execution_roadmap": [
                {
                    "phase_name": "Phase 1: Contract",
                    "objective": "Define the public API contract.",
                    "expected_deliverable": "A tested contract.",
                    "micro_tasks": [
                        {
                            "task_description": "Write the request model.",
                            "complexity_level": "Low",
                            "verification_steps": ["Run schema tests."],
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


def test_validate_blueprint_rejects_normalized_scope_overlap(
    valid_blueprint: SynthesisBlueprint,
) -> None:
    from blueprint_validation import (
        BlueprintValidationError,
        validate_blueprint,
    )

    valid_blueprint.synthesized_conceptual_model.out_of_scope = [
        "  PLANNING  "
    ]

    with pytest.raises(
        BlueprintValidationError,
        match="scope entries overlap",
    ):
        validate_blueprint(
            valid_blueprint,
            {"experience_level": "student"},
        )


def add_duplicate(
    blueprint: SynthesisBlueprint,
    duplicate_case: str,
) -> None:
    conceptual_model = blueprint.synthesized_conceptual_model
    decision = blueprint.architectural_decisions[0]
    question = blueprint.socratic_clarifying_questions[0]
    milestone = blueprint.step_by_step_execution_roadmap[0]
    task = milestone.micro_tasks[0]

    if duplicate_case == "in_scope":
        conceptual_model.in_scope.append(" planning ")
    elif duplicate_case == "out_of_scope":
        conceptual_model.out_of_scope.append(" AUTOMATIC DEPLOYMENT ")
    elif duplicate_case == "assumptions":
        conceptual_model.assumptions.append(
            " THE USER REVIEWS EACH MILESTONE "
        )
    elif duplicate_case == "adaptations":
        blueprint.personalization_trace.adaptations.append(
            blueprint.personalization_trace.adaptations[0].model_copy(
                deep=True
            )
        )
    elif duplicate_case == "component_names":
        duplicate = decision.model_copy(deep=True)
        duplicate.component_name = " api "
        blueprint.architectural_decisions.append(duplicate)
    elif duplicate_case == "alternatives":
        duplicate = decision.alternatives[0].model_copy(deep=True)
        duplicate.option_name = " flask "
        decision.alternatives.append(duplicate)
    elif duplicate_case == "option_labels":
        duplicate = question.suggested_options[0].model_copy(deep=True)
        duplicate.label = " web "
        question.suggested_options.append(duplicate)
    elif duplicate_case == "phase_names":
        duplicate = milestone.model_copy(deep=True)
        duplicate.phase_name = " phase 1: contract "
        blueprint.step_by_step_execution_roadmap.append(duplicate)
    elif duplicate_case == "task_descriptions":
        duplicate = task.model_copy(deep=True)
        duplicate.task_description = " write the request model. "
        milestone.micro_tasks.append(duplicate)
    elif duplicate_case == "verification_steps":
        task.verification_steps.append(" run schema tests. ")
    elif duplicate_case == "warning_risks":
        duplicate = blueprint.diagnostic_warnings[0].model_copy(deep=True)
        duplicate.risk_identified = " requests may fail. "
        blueprint.diagnostic_warnings.append(duplicate)
    else:
        raise AssertionError(f"Unknown duplicate case: {duplicate_case}")


@pytest.mark.parametrize(
    "duplicate_case",
    (
        "in_scope",
        "out_of_scope",
        "assumptions",
        "adaptations",
        "component_names",
        "alternatives",
        "option_labels",
        "phase_names",
        "task_descriptions",
        "verification_steps",
        "warning_risks",
    ),
)
def test_validate_blueprint_rejects_normalized_duplicates(
    valid_blueprint: SynthesisBlueprint,
    duplicate_case: str,
) -> None:
    from blueprint_validation import (
        BlueprintValidationError,
        validate_blueprint,
    )

    add_duplicate(valid_blueprint, duplicate_case)

    with pytest.raises(
        BlueprintValidationError,
        match="duplicate values",
    ):
        validate_blueprint(
            valid_blueprint,
            {"experience_level": "student"},
        )


@pytest.mark.parametrize(
    "profile_context",
    (
        {},
        {"learning_style": "hands-on"},
    ),
)
def test_validate_blueprint_rejects_unsupported_adaptation(
    valid_blueprint: SynthesisBlueprint,
    profile_context: dict[str, object],
) -> None:
    from blueprint_validation import (
        BlueprintValidationError,
        validate_blueprint,
    )

    with pytest.raises(
        BlueprintValidationError,
        match="personalization is unsupported",
    ):
        validate_blueprint(valid_blueprint, profile_context)


def test_validate_blueprint_accepts_supported_adaptation(
    valid_blueprint: SynthesisBlueprint,
) -> None:
    from blueprint_validation import validate_blueprint

    validate_blueprint(
        valid_blueprint,
        {"experience_level": "student"},
    )


def padded_text(prefix: str, length: int = 1_500) -> str:
    return prefix + ("x" * (length - len(prefix)))


def make_oversized_blueprint(
    valid_blueprint: SynthesisBlueprint,
) -> SynthesisBlueprint:
    conceptual_model = valid_blueprint.synthesized_conceptual_model
    conceptual_model.in_scope = [
        padded_text(f"in-{index}-") for index in range(10)
    ]
    conceptual_model.out_of_scope = [
        padded_text(f"out-{index}-") for index in range(10)
    ]
    conceptual_model.assumptions = [
        padded_text(f"assumption-{index}-") for index in range(10)
    ]

    decision_template = valid_blueprint.architectural_decisions[0]
    decisions = []
    for decision_index in range(8):
        decision = decision_template.model_copy(deep=True)
        decision.component_name = f"Component {decision_index}"
        decision.proposed_solution = padded_text(
            f"solution-{decision_index}-"
        )
        decision.rationale = padded_text(f"rationale-{decision_index}-")
        decision.alternatives = []
        for alternative_index in range(3):
            alternative = decision_template.alternatives[0].model_copy(
                deep=True
            )
            alternative.option_name = (
                f"Option {decision_index}-{alternative_index}"
            )
            alternative.tradeoff = padded_text(
                f"tradeoff-{decision_index}-{alternative_index}-"
            )
            alternative.reason_not_selected = padded_text(
                f"reason-{decision_index}-{alternative_index}-"
            )
            decision.alternatives.append(alternative)
        decisions.append(decision)
    valid_blueprint.architectural_decisions = decisions
    return valid_blueprint


def test_validate_blueprint_rejects_payload_over_128_kibibytes(
    valid_blueprint: SynthesisBlueprint,
) -> None:
    from blueprint_validation import (
        MAX_BLUEPRINT_BYTES,
        BlueprintValidationError,
        validate_blueprint,
    )

    blueprint = make_oversized_blueprint(valid_blueprint)
    serialized = json.dumps(
        blueprint.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert len(serialized) > MAX_BLUEPRINT_BYTES

    with pytest.raises(
        BlueprintValidationError,
        match="storage limit",
    ) as caught:
        validate_blueprint(
            blueprint,
            {"experience_level": "private-profile-value"},
        )

    assert "private-profile-value" not in str(caught.value)
    assert "solution-0" not in str(caught.value)
