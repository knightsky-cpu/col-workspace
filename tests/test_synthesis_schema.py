import json


def test_provider_schema_removes_local_only_string_constraints() -> None:
    from synthesis_schema import build_gemini_response_schema

    schema = build_gemini_response_schema()
    serialized = json.dumps(schema, sort_keys=True)

    assert '"minLength"' not in serialized
    assert '"maxLength"' not in serialized
    assert '"pattern"' not in serialized


def test_provider_schema_preserves_structural_constraints() -> None:
    from synthesis_schema import build_gemini_response_schema

    schema = build_gemini_response_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "synthesized_conceptual_model",
        "personalization_trace",
        "architectural_decisions_and_feedback",
        "socratic_clarifying_questions",
        "step_by_step_execution_roadmap",
    ]
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    conceptual_model = schema["properties"]
    assert isinstance(conceptual_model, dict)
    assert conceptual_model["synthesized_conceptual_model"] == {
        "$ref": "#/$defs/ConceptualModel"
    }

    diagnostic_warning = definitions["DiagnosticWarning"]
    assert isinstance(diagnostic_warning, dict)
    warning_properties = diagnostic_warning["properties"]
    assert isinstance(warning_properties, dict)
    assert warning_properties["severity"]["enum"] == [
        "Low",
        "Medium",
        "High",
        "Critical",
    ]

    micro_task = definitions["MicroTask"]
    assert isinstance(micro_task, dict)
    task_properties = micro_task["properties"]
    assert isinstance(task_properties, dict)
    assert task_properties["complexity_level"]["enum"] == [
        "Low",
        "Medium",
        "High",
    ]

    clarifying_question = definitions["ClarifyingQuestion"]
    assert isinstance(clarifying_question, dict)
    question_properties = clarifying_question["properties"]
    assert isinstance(question_properties, dict)
    options = question_properties["suggested_options"]
    assert options["minItems"] == 2
    assert options["maxItems"] == 3


def test_adapter_preserves_named_fields_and_does_not_mutate_input() -> None:
    from synthesis_schema import adapt_schema_for_gemini

    canonical = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "pattern": "^[a-z]+$",
            }
        },
        "$defs": {
            "maxLength": {
                "type": "string",
                "maxLength": 10,
            }
        },
    }

    adapted = adapt_schema_for_gemini(canonical)

    assert adapted == {
        "type": "object",
        "properties": {"pattern": {"type": "string"}},
        "$defs": {"maxLength": {"type": "string"}},
    }
    assert canonical["properties"]["pattern"]["pattern"] == (
        "^[a-z]+$"
    )
    assert canonical["$defs"]["maxLength"]["maxLength"] == 10


def test_provider_schema_results_are_independent() -> None:
    from synthesis_schema import build_gemini_response_schema

    first = build_gemini_response_schema()
    second = build_gemini_response_schema()
    first_properties = first["properties"]
    second_properties = second["properties"]
    assert isinstance(first_properties, dict)
    assert isinstance(second_properties, dict)

    first_properties.clear()

    assert "synthesized_conceptual_model" in second_properties
