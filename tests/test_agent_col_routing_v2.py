import importlib
from copy import deepcopy

import pytest
from pydantic import ValidationError

from agent_col_numeric_projection import project_routing_numeric_candidates


def load_routing_v2():
    try:
        return importlib.import_module("agent_col_routing_v2")
    except ModuleNotFoundError:
        pytest.fail("agent_col_routing_v2 has not been implemented")


def valid_computation_directive_payload() -> dict[str, object]:
    return {
        "route": "computation",
        "computation_intent": {
            "objective": "Calculate descriptive statistics for the values.",
            "scalar_inputs": [],
            "series_inputs": [
                {
                    "name": "values",
                    "numeric_ids": ["number-1", "number-2", "number-3"],
                }
            ],
            "precision": {
                "mode": "decimal_places",
                "digits_numeric_id": "number-4",
            },
            "constraints": [],
        },
    }


def test_v2_computation_directive_selects_only_numeric_candidate_ids() -> None:
    routing = load_routing_v2()

    directive = routing.AgentColRoutingDirective.model_validate(
        valid_computation_directive_payload()
    )

    assert directive.schema_version == "2.0"
    assert directive.computation_intent is not None
    assert directive.computation_intent.series_inputs[0].numeric_ids == (
        "number-1",
        "number-2",
        "number-3",
    )
    assert directive.computation_intent.precision is not None
    assert (
        directive.computation_intent.precision.digits_numeric_id
        == "number-4"
    )


def test_v2_normalizes_all_route_specific_payloads() -> None:
    routing = load_routing_v2()

    directives = (
        routing.AgentColRoutingDirective(route="direct"),
        routing.AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Which values should I calculate?",
        ),
        routing.AgentColRoutingDirective(
            route="source",
            source_intent={
                "objective": "Analyze the supplied page.",
                "selected_url_ids": ["url-1"],
            },
        ),
        routing.AgentColRoutingDirective(
            route="research",
            research_intent={
                "question": "What is the current stable Python release?",
                "objective": "Verify it using current public evidence.",
            },
        ),
        routing.AgentColRoutingDirective.model_validate(
            valid_computation_directive_payload()
        ),
    )

    assert tuple(directive.route for directive in directives) == (
        "direct",
        "clarify",
        "source",
        "research",
        "computation",
    )
    assert all(directive.schema_version == "2.0" for directive in directives)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.update(schema_version="1.0"),
        lambda payload: payload["computation_intent"].update(values=[1, 2]),
        lambda payload: payload["computation_intent"].update(
            expression="mean(values)"
        ),
        lambda payload: payload.update(source_intent={
            "objective": "Analyze a page.",
            "selected_url_ids": ["url-1"],
        }),
        lambda payload: payload["computation_intent"].update(
            scalar_inputs=[], series_inputs=[]
        ),
        lambda payload: payload["computation_intent"].update(
            scalar_inputs=[
                {"name": "values", "numeric_id": "number-1"},
            ],
            series_inputs=[
                {"name": "values", "numeric_ids": ["number-2"]},
            ],
        ),
        lambda payload: payload["computation_intent"].update(
            scalar_inputs=[
                {"name": "first", "numeric_id": "number-1"},
            ],
            series_inputs=[
                {
                    "name": "values",
                    "numeric_ids": ["number-1", "number-2"],
                },
            ],
        ),
        lambda payload: payload["computation_intent"].update(
            scalar_inputs=[
                {"name": "Not Valid", "numeric_id": "number-1"},
            ],
            series_inputs=[],
            precision=None,
        ),
        lambda payload: payload["computation_intent"].update(
            scalar_inputs=[
                {"name": f"value_{index}", "numeric_id": "number-1"}
                for index in range(21)
            ],
            series_inputs=[],
            precision=None,
        ),
        lambda payload: payload["computation_intent"].update(
            scalar_inputs=[],
            series_inputs=[
                {"name": f"values_{index}", "numeric_ids": ["number-1"]}
                for index in range(9)
            ],
            precision=None,
        ),
        lambda payload: payload["computation_intent"].update(
            series_inputs=[
                {
                    "name": "values",
                    "numeric_ids": [
                        f"number-{index}" for index in range(1, 33)
                    ] + ["number-1"],
                }
            ],
            precision=None,
        ),
        lambda payload: payload["computation_intent"].update(
            precision={
                "mode": "decimal_places",
                "digits_numeric_id": "number-1",
            }
        ),
    ),
)
def test_v2_directive_rejects_invalid_computation_structure(mutation) -> None:
    routing = load_routing_v2()
    payload = deepcopy(valid_computation_directive_payload())
    mutation(payload)

    with pytest.raises(ValidationError):
        routing.AgentColRoutingDirective.model_validate(payload)


def computation_routing_input(routing):
    message = (
        "Calculate the mean of 12, 15, and 18 with precision set at "
        "2 decimal places."
    )
    projection = project_routing_numeric_candidates(message)
    return routing.AgentColRoutingInput(
        current_message=message,
        numeric_candidates=projection.candidates,
        numeric_projection_incomplete=(
            projection.numeric_projection_incomplete
        ),
        available_capabilities=("source", "research", "computation"),
    )


def computation_directive(routing, **intent_changes):
    payload = valid_computation_directive_payload()
    payload["computation_intent"].update(intent_changes)
    return routing.AgentColRoutingDirective.model_validate(payload)


def test_v2_routing_input_accepts_bounded_url_and_numeric_candidates() -> None:
    routing = load_routing_v2()
    message = "Calculate 12 plus 15 using https://example.com/specification."
    projection = project_routing_numeric_candidates(message)

    routing_input = routing.AgentColRoutingInput(
        current_message=message,
        candidate_urls=(
            {
                "candidate_id": "url-1",
                "url": "https://example.com/specification",
                "source": "current_message",
            },
        ),
        numeric_candidates=projection.candidates,
        numeric_projection_incomplete=False,
        available_capabilities=("source", "research", "computation"),
    )

    assert tuple(
        candidate.raw_text for candidate in routing_input.numeric_candidates
    ) == ("12", "15")
    assert routing_input.available_capabilities == (
        "source",
        "research",
        "computation",
    )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.update(
            numeric_candidates=[
                {**payload["numeric_candidates"][0], "candidate_id": "number-2"},
                payload["numeric_candidates"][1],
                payload["numeric_candidates"][2],
                payload["numeric_candidates"][3],
            ]
        ),
        lambda payload: payload["numeric_candidates"][0].update(raw_text="21"),
        lambda payload: payload["numeric_candidates"][1].update(
            start_index=payload["numeric_candidates"][0]["start_index"]
        ),
        lambda payload: payload.update(
            available_capabilities=["source", "computation", "computation"]
        ),
        lambda payload: payload.update(
            available_capabilities=["requirements_verification"]
        ),
    ),
)
def test_v2_routing_input_rejects_invalid_bounded_context(mutation) -> None:
    routing = load_routing_v2()
    payload = computation_routing_input(routing).model_dump(mode="json")
    mutation(payload)

    with pytest.raises(ValidationError):
        routing.AgentColRoutingInput.model_validate(payload)


def test_v2_computation_directive_validates_for_exact_routing_input() -> None:
    routing = load_routing_v2()
    routing_input = computation_routing_input(routing)
    directive = computation_directive(routing)

    assert (
        routing.validate_routing_directive_for_input(directive, routing_input)
        is directive
    )


def mixed_unit_routing_input(routing):
    message = "Calculate the mean of $12 and 15."
    projection = project_routing_numeric_candidates(message)
    return routing.AgentColRoutingInput(
        current_message=message,
        numeric_candidates=projection.candidates,
        available_capabilities=("computation",),
    )


@pytest.mark.parametrize(
    "case",
    (
        "capability_absent",
        "projection_incomplete",
        "unknown_id",
        "reordered_series",
        "mixed_series_units",
        "non_integer_precision",
        "zero_significant_figures",
        "numeric_objective",
        "numeric_constraint",
        "unsafe_objective",
    ),
)
def test_v2_computation_directive_rejects_incompatible_input_without_leak(
    case: str,
) -> None:
    routing = load_routing_v2()
    routing_input = computation_routing_input(routing)
    directive_changes: dict[str, object] = {}

    if case == "capability_absent":
        routing_input = routing_input.model_copy(
            update={"available_capabilities": ("source", "research")}
        )
    elif case == "projection_incomplete":
        routing_input = routing_input.model_copy(
            update={"numeric_projection_incomplete": True}
        )
    elif case == "unknown_id":
        directive_changes["series_inputs"] = [
            {
                "name": "values",
                "numeric_ids": ["number-1", "number-2", "number-5"],
            }
        ]
    elif case == "reordered_series":
        directive_changes["series_inputs"] = [
            {
                "name": "values",
                "numeric_ids": ["number-2", "number-1", "number-3"],
            }
        ]
    elif case == "mixed_series_units":
        routing_input = mixed_unit_routing_input(routing)
        directive_changes["series_inputs"] = [
            {"name": "values", "numeric_ids": ["number-1", "number-2"]}
        ]
        directive_changes["precision"] = None
    elif case == "non_integer_precision":
        message = (
            "Calculate the mean of 12, 15, and 18 with precision set at "
            "2.5 decimal places."
        )
        projection = project_routing_numeric_candidates(message)
        routing_input = routing.AgentColRoutingInput(
            current_message=message,
            numeric_candidates=projection.candidates,
            available_capabilities=("computation",),
        )
    elif case == "zero_significant_figures":
        message = (
            "Calculate the mean of 12, 15, and 18 with precision set at "
            "0 significant figures."
        )
        projection = project_routing_numeric_candidates(message)
        routing_input = routing.AgentColRoutingInput(
            current_message=message,
            numeric_candidates=projection.candidates,
            available_capabilities=("computation",),
        )
        directive_changes["precision"] = {
            "mode": "significant_figures",
            "digits_numeric_id": "number-4",
        }
    elif case == "numeric_objective":
        directive_changes["objective"] = "Calculate 3 statistics."
    elif case == "numeric_constraint":
        directive_changes["constraints"] = ["Round to 2 places."]
    elif case == "unsafe_objective":
        directive_changes["objective"] = "Fetch https://private.example/data."

    directive = computation_directive(routing, **directive_changes)

    with pytest.raises(routing.RoutingDirectiveInputError) as error:
        routing.validate_routing_directive_for_input(directive, routing_input)

    assert str(error.value) == (
        "Routing directive is incompatible with its input."
    )
    assert "private.example" not in str(error.value)


@pytest.mark.parametrize(
    "directive_payload,routing_input_payload",
    (
        (
            {"route": "direct"},
            {"current_message": "Answer directly."},
        ),
        (
            {
                "route": "clarify",
                "clarifying_question": "Which page should I analyze?",
            },
            {"current_message": "Please analyze it."},
        ),
        (
            {
                "route": "source",
                "source_intent": {
                    "objective": "Analyze the supplied page.",
                    "selected_url_ids": ["url-1"],
                },
            },
            {
                "current_message": "Analyze the page.",
                "candidate_urls": [
                    {
                        "candidate_id": "url-1",
                        "url": "https://example.com/",
                        "source": "current_message",
                    }
                ],
                "available_capabilities": ["source"],
            },
        ),
        (
            {
                "route": "research",
                "research_intent": {
                    "question": "What changed this week?",
                    "objective": "Verify it with current public evidence.",
                },
            },
            {
                "current_message": "What changed this week?",
                "available_capabilities": ["research"],
            },
        ),
    ),
)
def test_v2_preserves_v1_route_cross_validation(
    directive_payload: dict[str, object],
    routing_input_payload: dict[str, object],
) -> None:
    routing = load_routing_v2()
    directive = routing.AgentColRoutingDirective.model_validate(
        directive_payload
    )
    routing_input = routing.AgentColRoutingInput.model_validate(
        routing_input_payload
    )

    assert (
        routing.validate_routing_directive_for_input(directive, routing_input)
        is directive
    )
