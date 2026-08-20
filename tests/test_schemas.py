import copy

import pytest
from pydantic import ValidationError

from schemas import SynthesisBlueprint, SynthesisRequest, SynthesisResponse


def set_nested_value(
    container: dict[str, object],
    path: tuple[str | int, ...],
    value: object,
) -> None:
    target: object = container
    for key in path[:-1]:
        if isinstance(key, int):
            assert isinstance(target, list)
        else:
            assert isinstance(target, dict)
        target = target[key]

    final_key = path[-1]
    if isinstance(final_key, int):
        assert isinstance(target, list)
    else:
        assert isinstance(target, dict)
    target[final_key] = value


def get_nested_value(
    container: dict[str, object],
    path: tuple[str | int, ...],
) -> object:
    target: object = container
    for key in path:
        if isinstance(key, int):
            assert isinstance(target, list)
        else:
            assert isinstance(target, dict)
        target = target[key]
    return target


@pytest.fixture
def valid_blueprint_payload() -> dict[str, object]:
    return {
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


def test_synthesis_blueprint_accepts_complete_valid_payload(
    valid_blueprint_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_blueprint_payload)

    blueprint = SynthesisBlueprint.model_validate(payload)

    assert blueprint.model_dump(mode="json") == payload


def test_blueprint_v2_uses_architectural_decisions(
    valid_blueprint_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_blueprint_payload)

    blueprint = SynthesisBlueprint.model_validate(payload)

    assert blueprint.architectural_decisions


def test_blueprint_v2_rejects_legacy_decisions_field(
    valid_blueprint_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_blueprint_payload)
    decisions = payload.pop("architectural_decisions")
    payload["architectural_decisions_and_feedback"] = decisions

    with pytest.raises(ValidationError):
        SynthesisBlueprint.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "maximum"),
    (
        (("synthesized_conceptual_model", "project_name"), 120),
        (("architectural_decisions", 0, "component_name"), 160),
        (
            (
                "synthesized_conceptual_model",
                "core_value_proposition",
            ),
            1_500,
        ),
        (
            (
                "step_by_step_execution_roadmap",
                0,
                "micro_tasks",
                0,
                "verification_steps",
                0,
            ),
            500,
        ),
    ),
)
def test_generated_string_types_enforce_upper_bounds(
    valid_blueprint_payload: dict[str, object],
    path: tuple[str | int, ...],
    maximum: int,
) -> None:
    accepted = copy.deepcopy(valid_blueprint_payload)
    rejected = copy.deepcopy(valid_blueprint_payload)
    set_nested_value(accepted, path, "x" * maximum)
    set_nested_value(rejected, path, "x" * (maximum + 1))

    SynthesisBlueprint.model_validate(accepted)
    with pytest.raises(ValidationError):
        SynthesisBlueprint.model_validate(rejected)


@pytest.mark.parametrize(
    ("path", "maximum"),
    (
        (("synthesized_conceptual_model", "in_scope"), 10),
        (("synthesized_conceptual_model", "out_of_scope"), 10),
        (("synthesized_conceptual_model", "assumptions"), 10),
        (("personalization_trace", "adaptations"), 8),
        (("architectural_decisions",), 8),
        (("architectural_decisions", 0, "alternatives"), 3),
        (("socratic_clarifying_questions",), 5),
        (
            (
                "socratic_clarifying_questions",
                0,
                "suggested_options",
            ),
            3,
        ),
        (("step_by_step_execution_roadmap",), 8),
        (
            (
                "step_by_step_execution_roadmap",
                0,
                "micro_tasks",
            ),
            10,
        ),
        (
            (
                "step_by_step_execution_roadmap",
                0,
                "micro_tasks",
                0,
                "verification_steps",
            ),
            5,
        ),
    ),
)
def test_generated_collections_enforce_upper_bounds(
    valid_blueprint_payload: dict[str, object],
    path: tuple[str | int, ...],
    maximum: int,
) -> None:
    accepted = copy.deepcopy(valid_blueprint_payload)
    rejected = copy.deepcopy(valid_blueprint_payload)
    item = get_nested_value(accepted, path)[0]
    set_nested_value(
        accepted,
        path,
        [copy.deepcopy(item) for _ in range(maximum)],
    )
    set_nested_value(
        rejected,
        path,
        [copy.deepcopy(item) for _ in range(maximum + 1)],
    )

    SynthesisBlueprint.model_validate(accepted)
    with pytest.raises(ValidationError):
        SynthesisBlueprint.model_validate(rejected)


def test_diagnostic_warnings_enforce_ten_item_maximum(
    valid_blueprint_payload: dict[str, object],
) -> None:
    warning = {
        "affected_component": "API",
        "severity": "Medium",
        "risk_identified": "Requests may fail.",
        "preventative_guidance": "Use bounded retries.",
    }
    accepted = copy.deepcopy(valid_blueprint_payload)
    rejected = copy.deepcopy(valid_blueprint_payload)
    accepted["diagnostic_warnings"] = [
        copy.deepcopy(warning) for _ in range(10)
    ]
    rejected["diagnostic_warnings"] = [
        copy.deepcopy(warning) for _ in range(11)
    ]

    SynthesisBlueprint.model_validate(accepted)
    with pytest.raises(ValidationError):
        SynthesisBlueprint.model_validate(rejected)


def test_generated_fields_have_provider_guidance_descriptions() -> None:
    schema = SynthesisBlueprint.model_json_schema()
    model_schemas = [schema, *schema["$defs"].values()]

    for model_schema in model_schemas:
        properties = model_schema.get("properties", {})
        for property_schema in properties.values():
            description = property_schema.get("description")
            assert isinstance(description, str)
            assert description.strip()


def test_synthesis_blueprint_forbids_extra_fields(
    valid_blueprint_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_blueprint_payload)
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        SynthesisBlueprint.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    (
        ("synthesized_conceptual_model", "project_name"),
        (
            "personalization_trace",
            "adaptations",
            0,
            "architecture_change",
        ),
        (
            "architectural_decisions",
            0,
            "alternatives",
            0,
            "tradeoff",
        ),
        (
            "socratic_clarifying_questions",
            0,
            "suggested_options",
            0,
            "label",
        ),
        (
            "step_by_step_execution_roadmap",
            0,
            "micro_tasks",
            0,
            "verification_steps",
            0,
        ),
    ),
)
def test_generated_strings_reject_whitespace(
    valid_blueprint_payload: dict[str, object],
    path: tuple[str | int, ...],
) -> None:
    payload = copy.deepcopy(valid_blueprint_payload)
    set_nested_value(payload, path, "   ")

    with pytest.raises(ValidationError):
        SynthesisBlueprint.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "invalid_value"),
    (
        (("synthesized_conceptual_model", "in_scope"), []),
        (("architectural_decisions",), []),
        (
            (
                "architectural_decisions",
                0,
                "alternatives",
            ),
            [],
        ),
        (("socratic_clarifying_questions",), []),
        (
            (
                "socratic_clarifying_questions",
                0,
                "suggested_options",
            ),
            [{"label": "Only", "impact": "Insufficient choice."}],
        ),
        (
            (
                "socratic_clarifying_questions",
                0,
                "suggested_options",
            ),
            [
                {"label": str(index), "impact": "Too many choices."}
                for index in range(4)
            ],
        ),
        (("step_by_step_execution_roadmap",), []),
        (
            ("step_by_step_execution_roadmap", 0, "micro_tasks"),
            [],
        ),
        (
            (
                "step_by_step_execution_roadmap",
                0,
                "micro_tasks",
                0,
                "verification_steps",
            ),
            [],
        ),
    ),
)
def test_synthesis_blueprint_rejects_invalid_collection_bounds(
    valid_blueprint_payload: dict[str, object],
    path: tuple[str | int, ...],
    invalid_value: object,
) -> None:
    payload = copy.deepcopy(valid_blueprint_payload)
    set_nested_value(payload, path, invalid_value)

    with pytest.raises(ValidationError):
        SynthesisBlueprint.model_validate(payload)


def test_micro_task_rejects_unknown_complexity(
    valid_blueprint_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_blueprint_payload)
    set_nested_value(
        payload,
        (
            "step_by_step_execution_roadmap",
            0,
            "micro_tasks",
            0,
            "complexity_level",
        ),
        "Extreme",
    )

    with pytest.raises(ValidationError):
        SynthesisBlueprint.model_validate(payload)


def test_diagnostic_warning_rejects_unknown_severity(
    valid_blueprint_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_blueprint_payload)
    payload["diagnostic_warnings"] = [
        {
            "affected_component": "API",
            "severity": "Urgent",
            "risk_identified": "Requests may fail.",
            "preventative_guidance": "Add bounded retries.",
        }
    ]

    with pytest.raises(ValidationError):
        SynthesisBlueprint.model_validate(payload)


def test_optional_generated_lists_default_empty(
    valid_blueprint_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_blueprint_payload)
    conceptual_model = payload["synthesized_conceptual_model"]
    assert isinstance(conceptual_model, dict)
    conceptual_model.pop("out_of_scope")
    conceptual_model.pop("assumptions")
    payload["personalization_trace"] = {}
    payload.pop("diagnostic_warnings")

    blueprint = SynthesisBlueprint.model_validate(payload)

    assert blueprint.synthesized_conceptual_model.out_of_scope == []
    assert blueprint.synthesized_conceptual_model.assumptions == []
    assert blueprint.personalization_trace.adaptations == []
    assert blueprint.diagnostic_warnings == []


def test_synthesis_request_accepts_project_owned_payload() -> None:
    request = SynthesisRequest.model_validate(
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "Build a study partner.",
        }
    )

    assert request.model_dump() == {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "source_text": "Build a study partner.",
    }


@pytest.mark.parametrize(
    "request_payload",
    (
        {
            "project_id": "bad/id",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": " ",
            "user_id": "user-1",
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "x" * 129,
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": " ",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "x" * 10_001,
        },
    ),
)
def test_synthesis_request_rejects_invalid_boundaries(
    request_payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SynthesisRequest.model_validate(request_payload)


def test_synthesis_request_strips_string_boundaries() -> None:
    request = SynthesisRequest.model_validate(
        {
            "project_id": " project-1 ",
            "session_id": " session-1 ",
            "user_id": " user-1 ",
            "source_text": " Build a study partner. ",
        }
    )

    assert request.model_dump() == {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "source_text": "Build a study partner.",
    }


def test_synthesis_response_accepts_valid_blueprint(
    valid_blueprint_payload: dict[str, object],
) -> None:
    response = SynthesisResponse.model_validate(
        {
            "blueprint_id": "blueprint-1",
            "blueprint": valid_blueprint_payload,
        }
    )

    assert response.blueprint_id == "blueprint-1"
    assert response.blueprint.model_dump(mode="json") == (
        valid_blueprint_payload
    )


def test_synthesis_response_rejects_blank_blueprint_id(
    valid_blueprint_payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SynthesisResponse.model_validate(
            {
                "blueprint_id": "   ",
                "blueprint": valid_blueprint_payload,
            }
        )


def test_chat_contract_is_project_owned_and_defaults_empty_receipts() -> None:
    from schemas import ChatRequest, ChatResponse

    request = ChatRequest.model_validate(
        {
            "project_id": " project-1 ",
            "session_id": " session-1 ",
            "user_id": " user-1 ",
            "message": " Help me plan this. ",
        }
    )
    response = ChatResponse(response=" Collaborative answer. ")

    assert request.model_dump() == {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "message": "Help me plan this.",
    }
    assert response.model_dump(mode="json") == {
        "response": "Collaborative answer.",
        "actions": [],
        "artifacts": [],
        "citations": [],
    }


@pytest.mark.parametrize(
    "payload",
    (
        {
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Hello",
        },
        {
            "project_id": "bad/project",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Hello",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "   ",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Hello",
            "unexpected": True,
        },
    ),
)
def test_chat_request_rejects_invalid_project_owned_payloads(
    payload: dict[str, object],
) -> None:
    from schemas import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest.model_validate(payload)


@pytest.mark.parametrize(
    "receipt_payload",
    (
        {
            "action_name": "unapproved_action",
            "status": "completed",
        },
        {
            "action_name": "synthesize_project",
            "status": "failed",
        },
    ),
)
def test_action_receipt_rejects_unverified_public_values(
    receipt_payload: dict[str, object],
) -> None:
    from schemas import AgentActionReceipt

    with pytest.raises(ValidationError):
        AgentActionReceipt.model_validate(receipt_payload)


def test_artifact_and_citation_references_validate_public_fields() -> None:
    from schemas import ArtifactReference, CitationReference

    artifact = ArtifactReference.model_validate(
        {
            "artifact_type": "synthesis_blueprint",
            "project_id": "project-1",
            "artifact_id": "blueprint-1",
            "schema_version": "2.0",
            "display_label": "Agent Col blueprint",
        }
    )
    citation = CitationReference.model_validate(
        {
            "uri": "https://example.com/reference",
            "label": "Reference",
        }
    )

    assert artifact.artifact_id == "blueprint-1"
    assert str(citation.uri) == "https://example.com/reference"

    with pytest.raises(ValidationError):
        ArtifactReference.model_validate(
            {
                "artifact_type": "synthesis_blueprint",
                "project_id": "project-1",
                "artifact_id": "blueprint-1",
                "schema_version": "1.0",
                "display_label": "Legacy blueprint",
            }
        )

    with pytest.raises(ValidationError):
        CitationReference.model_validate(
            {"uri": "ftp://example.com/file", "label": "Reference"}
        )
