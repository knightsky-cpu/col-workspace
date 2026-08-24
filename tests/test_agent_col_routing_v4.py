import pytest
from pydantic import ValidationError


def artifact_routing_input(**overrides: object) -> object:
    from agent_col_routing_v4 import AgentColRoutingInput

    payload: dict[str, object] = {
        "current_message": (
            "Create a structured blueprint from this complete project "
            "description: build a study partner with approved memory, "
            "verifiable milestones, and explicit user control."
        ),
        "available_capabilities": (
            "source",
            "research",
            "computation",
            "requirements_verification",
        ),
        "artifact_creation_available": True,
        "structured_decision_present": False,
        "recent_user_messages": (),
    }
    payload.update(overrides)
    return AgentColRoutingInput.model_validate(payload)


def artifact_directive(**intent_overrides: object) -> object:
    from agent_col_routing_v4 import AgentColRoutingDirective

    intent: dict[str, object] = {
        "operation": "create_blueprint",
        "objective": "Create the requested structured blueprint.",
    }
    intent.update(intent_overrides)
    return AgentColRoutingDirective.model_validate(
        {
            "schema_version": "4.0",
            "route": "artifact",
            "artifact_intent": intent,
        }
    )


def test_v4_accepts_one_bounded_artifact_creation_directive() -> None:
    from agent_col_routing_v4 import (
        AgentColRoute,
        AgentColRoutingDirective,
        validate_routing_directive_for_input,
    )

    routing_input = artifact_routing_input()
    directive = AgentColRoutingDirective.model_validate(
        {
            "schema_version": "4.0",
            "route": "artifact",
            "artifact_intent": {
                "operation": "create_blueprint",
                "objective": "Create the requested structured blueprint.",
            },
        }
    )

    assert directive.route is AgentColRoute.ARTIFACT
    assert directive.artifact_intent is not None
    assert directive.artifact_intent.operation == "create_blueprint"
    assert (
        validate_routing_directive_for_input(directive, routing_input)
        is directive
    )


def test_v4_accepts_single_file_artifact_creation_directive() -> None:
    from agent_col_routing_v4 import (
        AgentColRoute,
        AgentColRoutingDirective,
        validate_routing_directive_for_input,
    )

    routing_input = artifact_routing_input(
        current_message=(
            "Create a Python code artifact for a password generator using "
            "uppercase letters, lowercase letters, numbers, and symbols."
        )
    )
    directive = AgentColRoutingDirective.model_validate(
        {
            "schema_version": "4.0",
            "route": "artifact",
            "artifact_intent": {
                "operation": "create_single_file_artifact",
                "objective": "Create the requested password generator code artifact.",
                "artifact_family": "code",
                "format": "python",
                "filename": "password_generator.py",
            },
        }
    )

    assert directive.route is AgentColRoute.ARTIFACT
    assert directive.artifact_intent is not None
    assert directive.artifact_intent.operation == "create_single_file_artifact"
    assert directive.artifact_intent.artifact_family == "code"
    assert directive.artifact_intent.format == "python"
    assert directive.artifact_intent.filename == "password_generator.py"
    assert (
        validate_routing_directive_for_input(directive, routing_input)
        is directive
    )


def test_v4_single_file_artifact_intent_rejects_family_format_mismatch(
) -> None:
    with pytest.raises(ValidationError):
        artifact_directive(
            operation="create_single_file_artifact",
            artifact_family="document",
            format="python",
            filename="password_generator.py",
        )


def test_v4_routing_input_accepts_bounded_recent_user_context() -> None:
    routing_input = artifact_routing_input(
        current_message="Turn that into a markdown deliverable.",
        recent_user_messages=(
            "I need a simple Pomodoro timer with work and break intervals.",
        ),
    )

    assert routing_input.current_message == (
        "Turn that into a markdown deliverable."
    )
    assert routing_input.recent_user_messages == (
        "I need a simple Pomodoro timer with work and break intervals.",
    )


def test_v4_provider_instruction_accepts_common_artifact_words() -> None:
    from agent_col_routing_provider_v4 import (
        AGENT_COL_ROUTING_V4_SYSTEM_INSTRUCTION,
    )

    instruction = AGENT_COL_ROUTING_V4_SYSTEM_INSTRUCTION.casefold()

    for phrase in (
        "artifact",
        "deliverable",
        "markdown",
        "text",
        "json",
        "pdf",
        "recent user-authored context",
        "simple common artifacts",
    ):
        assert phrase in instruction


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("source_text", "private project source"),
        ("project_id", "project-1"),
        ("artifact_id", "artifact-1"),
        ("schema_version", "2.0"),
        ("profile_value", "concise"),
    ),
)
def test_v4_artifact_intent_rejects_model_supplied_authority(
    field_name: str,
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        artifact_directive(**{field_name: value})


def test_v4_artifact_route_rejects_mixed_expert_intent() -> None:
    from agent_col_routing_v4 import AgentColRoutingDirective

    with pytest.raises(ValidationError):
        AgentColRoutingDirective.model_validate(
            {
                "schema_version": "4.0",
                "route": "artifact",
                "artifact_intent": {
                    "operation": "create_blueprint",
                    "objective": "Create the requested structured blueprint.",
                },
                "research_intent": {
                    "objective": "Find current public evidence.",
                    "constraints": [],
                },
            }
        )


@pytest.mark.parametrize(
    ("input_overrides", "expected_reason"),
    (
        ({"artifact_creation_available": False}, "artifact_unavailable"),
        (
            {"structured_decision_present": True},
            "structured_decision_present",
        ),
    ),
)
def test_v4_artifact_route_rejects_server_boundary_conflicts(
    input_overrides: dict[str, object],
    expected_reason: str,
) -> None:
    from agent_col_routing_v4 import (
        RoutingDirectiveInputError,
        validate_routing_directive_for_input,
    )

    with pytest.raises(RoutingDirectiveInputError) as error:
        validate_routing_directive_for_input(
            artifact_directive(),
            artifact_routing_input(**input_overrides),
        )

    assert error.value.reason == expected_reason


def test_v4_artifact_objective_rejects_numeric_source_material() -> None:
    from agent_col_routing_v4 import (
        RoutingDirectiveInputError,
        validate_routing_directive_for_input,
    )

    with pytest.raises(RoutingDirectiveInputError) as error:
        validate_routing_directive_for_input(
            artifact_directive(
                objective="Create a blueprint with 3 implementation phases."
            ),
            artifact_routing_input(),
        )

    assert error.value.reason == "unsafe_task_text"


@pytest.mark.parametrize(
    "directive_payload",
    (
        {"schema_version": "4.0", "route": "direct"},
        {
            "schema_version": "4.0",
            "route": "clarify",
            "clarifying_question": "What outcome should the blueprint target?",
        },
        {
            "schema_version": "4.0",
            "route": "research",
            "research_intent": {
                "question": "What current public evidence is available?",
                "objective": "Verify the requested current claim.",
            },
        },
    ),
)
def test_v4_preserves_existing_non_artifact_route_validation(
    directive_payload: dict[str, object],
) -> None:
    from agent_col_routing_v4 import (
        AgentColRoutingDirective,
        validate_routing_directive_for_input,
    )

    directive = AgentColRoutingDirective.model_validate(directive_payload)

    assert (
        validate_routing_directive_for_input(
            directive,
            artifact_routing_input(),
        )
        is directive
    )
