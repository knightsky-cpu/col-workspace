def test_synthesis_blueprint_accepts_complete_valid_payload() -> None:
    from schemas import SynthesisBlueprint

    payload = {
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
        "architectural_decisions_and_feedback": [
            {
                "component_name": "API",
                "proposed_solution": "FastAPI",
                "rationale": (
                    "Matches the existing asynchronous backend."
                ),
                "alternatives": [
                    {
                        "option_name": "Flask",
                        "tradeoff": (
                            "Simpler but synchronous by default."
                        ),
                        "reason_not_selected": (
                            "Would diverge from the backend."
                        ),
                    }
                ],
            }
        ],
        "socratic_clarifying_questions": [
            {
                "question_text": (
                    "Which client should be supported first?"
                ),
                "why_this_matters": (
                    "It determines the first API contract."
                ),
                "suggested_options": [
                    {
                        "label": "Web",
                        "impact": "Reuses the existing FastAPI host.",
                    },
                    {
                        "label": "CLI",
                        "impact": "Optimizes for terminal workflows.",
                    },
                ],
            }
        ],
        "step_by_step_execution_roadmap": [
            {
                "phase_name": "Phase 1: Contract",
                "objective": (
                    "Define the public request and response."
                ),
                "expected_deliverable": (
                    "A tested Pydantic contract."
                ),
                "micro_tasks": [
                    {
                        "task_description": "Write the request model.",
                        "complexity_level": "Low",
                        "verification_steps": [
                            "Run the schema tests."
                        ],
                    }
                ],
            }
        ],
        "diagnostic_warnings": [],
    }

    blueprint = SynthesisBlueprint.model_validate(payload)

    assert blueprint.model_dump(mode="json") == payload
