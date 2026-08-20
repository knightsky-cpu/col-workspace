import json


def test_provider_schema_removes_local_only_constraints() -> None:
    from synthesis_schema import build_gemini_response_schema

    schema = build_gemini_response_schema()
    serialized = json.dumps(schema, sort_keys=True)

    assert '"minLength"' not in serialized
    assert '"maxLength"' not in serialized
    assert '"pattern"' not in serialized
    assert '"maxItems"' not in serialized


def test_canonical_schema_retains_local_collection_limits() -> None:
    from schemas import SynthesisBlueprint

    schema = SynthesisBlueprint.model_json_schema()
    serialized = json.dumps(schema, sort_keys=True)

    assert '"maxItems"' in serialized


def test_provider_schema_preserves_structural_constraints() -> None:
    from synthesis_schema import build_gemini_response_schema

    schema = build_gemini_response_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "synthesized_conceptual_model",
        "personalization_trace",
        "architectural_decisions",
        "socratic_clarifying_questions",
        "step_by_step_execution_roadmap",
    ]
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    conceptual_model = schema["properties"]
    assert isinstance(conceptual_model, dict)
    conceptual_model_reference = conceptual_model[
        "synthesized_conceptual_model"
    ]
    assert conceptual_model_reference["$ref"] == (
        "#/$defs/ConceptualModel"
    )
    assert conceptual_model_reference["description"]

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
    assert "maxItems" not in options


def test_adapter_preserves_named_fields_and_does_not_mutate_input() -> None:
    from synthesis_schema import adapt_schema_for_gemini

    canonical = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "pattern": "^[a-z]+$",
            },
            "maxItems": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 2,
            },
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
        "properties": {
            "pattern": {"type": "string"},
            "maxItems": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
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
