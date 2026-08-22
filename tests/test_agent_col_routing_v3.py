import importlib
from copy import deepcopy

import pytest
from pydantic import ValidationError

from agent_col_numeric_projection import project_routing_numeric_candidates
from agent_col_routing import project_routing_url_candidates
from agent_col_text_projection import project_routing_text_blocks


def load_routing_v3():
    try:
        return importlib.import_module("agent_col_routing_v3")
    except ModuleNotFoundError:
        pytest.fail("agent_col_routing_v3 has not been implemented")


def valid_requirements_directive_payload() -> dict[str, object]:
    return {
        "route": "requirements_verification",
        "requirements_verification_intent": {
            "objective": "Compare every requirement with the supplied draft.",
            "requirement_block_ids": ["block-3", "block-4"],
            "subject_block_ids": ["block-6"],
            "constraints": ["Do not infer missing evidence."],
        },
    }


def requirements_routing_input(routing):
    message = (
        "Compare the subject against every requirement.\n\n"
        "Requirements:\n"
        "- Include one practical example.\n"
        "- State a material limitation.\n\n"
        "Subject:\n"
        "The response includes one practical example."
    )
    text_projection = project_routing_text_blocks(message)
    numeric_projection = project_routing_numeric_candidates(message)
    return routing.AgentColRoutingInput(
        current_message=message,
        candidate_urls=project_routing_url_candidates(message, ()),
        numeric_candidates=numeric_projection.candidates,
        numeric_projection_incomplete=(
            numeric_projection.numeric_projection_incomplete
        ),
        text_block_candidates=text_projection.candidates,
        text_projection_incomplete=text_projection.text_projection_incomplete,
        available_capabilities=(
            "source",
            "research",
            "computation",
            "requirements_verification",
        ),
    )


def test_v3_requirements_directive_selects_only_text_block_ids() -> None:
    routing = load_routing_v3()

    directive = routing.AgentColRoutingDirective(
        route="requirements_verification",
        requirements_verification_intent={
            "objective": "Compare every requirement with the supplied draft.",
            "requirement_block_ids": ["block-3", "block-4"],
            "subject_block_ids": ["block-6"],
            "constraints": ["Do not infer missing evidence."],
        },
    )

    assert directive.schema_version == "3.0"
    assert directive.requirements_verification_intent is not None
    assert directive.requirements_verification_intent.requirement_block_ids == (
        "block-3",
        "block-4",
    )
    assert directive.requirements_verification_intent.subject_block_ids == (
        "block-6",
    )


@pytest.mark.parametrize(
    ("route", "payload"),
    [
        ("direct", {}),
        ("clarify", {"clarifying_question": "Which material should I compare?"}),
        (
            "source",
            {
                "source_intent": {
                    "objective": "Analyze the supplied page.",
                    "selected_url_ids": ["url-1"],
                }
            },
        ),
        (
            "research",
            {
                "research_intent": {
                    "question": "What is the current stable release?",
                    "objective": "Find current authoritative evidence.",
                }
            },
        ),
        (
            "computation",
            {
                "computation_intent": {
                    "objective": "Calculate the arithmetic mean.",
                    "scalar_inputs": [
                        {"name": "value", "numeric_id": "number-1"}
                    ],
                }
            },
        ),
    ],
)
def test_v3_directive_accepts_each_existing_route_shape(
    route: str,
    payload: dict[str, object],
) -> None:
    routing = load_routing_v3()

    directive = routing.AgentColRoutingDirective(route=route, **payload)

    assert directive.schema_version == "3.0"
    assert directive.route == route


def test_v3_routing_input_accepts_all_bounded_candidate_types() -> None:
    routing = load_routing_v3()

    routing_input = requirements_routing_input(routing)

    assert len(routing_input.text_block_candidates) == 6
    assert routing_input.available_capabilities == (
        "source",
        "research",
        "computation",
        "requirements_verification",
    )


def test_v3_routing_input_preserves_boundary_whitespace_for_exact_spans() -> None:
    routing = load_routing_v3()
    message = " \nSubject text.\n "
    projection = project_routing_text_blocks(message)

    routing_input = routing.AgentColRoutingInput(
        current_message=message,
        text_block_candidates=projection.candidates,
    )

    assert routing_input.current_message == message
    assert routing_input.text_block_candidates[0].start_index == 2
    assert routing_input.text_block_candidates[0].text == "Subject text."


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.update(schema_version="2.0"),
        lambda payload: payload["requirements_verification_intent"].update(
            requirements=["Do something."]
        ),
        lambda payload: payload["requirements_verification_intent"].update(
            subject="A draft."
        ),
        lambda payload: payload["requirements_verification_intent"].update(
            character_offsets=[0, 10]
        ),
        lambda payload: payload.update(hidden_rationale="private"),
        lambda payload: payload.update(
            source_intent={
                "objective": "Analyze a page.",
                "selected_url_ids": ["url-1"],
            }
        ),
        lambda payload: payload["requirements_verification_intent"].update(
            requirement_block_ids=[]
        ),
        lambda payload: payload["requirements_verification_intent"].update(
            subject_block_ids=[]
        ),
        lambda payload: payload["requirements_verification_intent"].update(
            requirement_block_ids=[
                f"block-{index}" for index in range(1, 52)
            ],
            subject_block_ids=["block-64"],
        ),
        lambda payload: payload["requirements_verification_intent"].update(
            requirement_block_ids=["block-64"],
            subject_block_ids=[
                f"block-{index}" for index in range(1, 34)
            ],
        ),
        lambda payload: payload["requirements_verification_intent"].update(
            constraints=[f"constraint {index}" for index in range(6)]
        ),
        lambda payload: payload["requirements_verification_intent"].update(
            requirement_block_ids=["block-3", "block-3"]
        ),
        lambda payload: payload["requirements_verification_intent"].update(
            subject_block_ids=["block-6", "block-6"]
        ),
        lambda payload: payload["requirements_verification_intent"].update(
            subject_block_ids=["block-4"]
        ),
    ),
)
def test_v3_directive_rejects_invalid_requirements_structure(mutation) -> None:
    routing = load_routing_v3()
    payload = deepcopy(valid_requirements_directive_payload())
    mutation(payload)

    with pytest.raises(ValidationError):
        routing.AgentColRoutingDirective.model_validate(payload)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload["text_block_candidates"][1].update(
            candidate_id="block-1"
        ),
        lambda payload: payload["text_block_candidates"][1].update(
            candidate_id="block-3"
        ),
        lambda payload: payload["text_block_candidates"][0].update(
            text="wrong slice"
        ),
        lambda payload: payload["text_block_candidates"][1].update(
            start_index=payload["text_block_candidates"][0]["start_index"]
        ),
        lambda payload: payload.update(
            available_capabilities=[
                "source",
                "research",
                "computation",
                "requirements_verification",
                "source",
            ]
        ),
        lambda payload: payload.update(
            available_capabilities=["source", "source"]
        ),
        lambda payload: payload.update(
            available_capabilities=["unknown_capability"]
        ),
    ),
)
def test_v3_routing_input_rejects_invalid_bounded_context(mutation) -> None:
    routing = load_routing_v3()
    payload = requirements_routing_input(routing).model_dump(mode="json")
    mutation(payload)

    with pytest.raises(ValidationError):
        routing.AgentColRoutingInput.model_validate(payload)


def requirements_directive(routing, **intent_changes):
    payload = valid_requirements_directive_payload()
    payload["requirements_verification_intent"].update(intent_changes)
    return routing.AgentColRoutingDirective.model_validate(payload)


def test_v3_requirements_directive_validates_for_exact_routing_input() -> None:
    routing = load_routing_v3()
    routing_input = requirements_routing_input(routing)
    directive = requirements_directive(routing)

    assert (
        routing.validate_routing_directive_for_input(directive, routing_input)
        is directive
    )


def routing_input_from_blocks(routing, blocks):
    message = "\n\n".join(text for _, text in blocks)
    candidates = []
    offset = 0
    for index, (kind, text) in enumerate(blocks, start=1):
        candidates.append(
            {
                "candidate_id": f"block-{index}",
                "text": text,
                "start_index": offset,
                "end_index": offset + len(text),
                "structural_kind": kind,
            }
        )
        offset += len(text) + 2
    return routing.AgentColRoutingInput(
        current_message=message,
        text_block_candidates=candidates,
        available_capabilities=("requirements_verification",),
    )


@pytest.mark.parametrize(
    "case",
    (
        "capability_absent",
        "projection_incomplete",
        "unknown_id",
        "heading_requirement",
        "heading_subject",
        "requirements_out_of_order",
    ),
)
def test_v3_requirements_directive_rejects_incompatible_input_without_leak(
    case: str,
) -> None:
    routing = load_routing_v3()
    routing_input = requirements_routing_input(routing)
    directive_changes: dict[str, object] = {}

    if case == "capability_absent":
        routing_input = routing_input.model_copy(
            update={
                "available_capabilities": (
                    "source",
                    "research",
                    "computation",
                )
            }
        )
    elif case == "projection_incomplete":
        routing_input = routing_input.model_copy(
            update={"text_projection_incomplete": True}
        )
    elif case == "unknown_id":
        directive_changes["subject_block_ids"] = ["block-7"]
    elif case == "heading_requirement":
        directive_changes["requirement_block_ids"] = ["block-2"]
    elif case == "heading_subject":
        directive_changes["subject_block_ids"] = ["block-5"]
    elif case == "requirements_out_of_order":
        directive_changes["requirement_block_ids"] = ["block-4", "block-3"]

    directive = requirements_directive(routing, **directive_changes)

    with pytest.raises(routing.RoutingDirectiveInputError) as error:
        routing.validate_routing_directive_for_input(directive, routing_input)

    assert str(error.value) == "Routing directive is incompatible with its input."
    assert "practical example" not in str(error.value)


def test_v3_requirements_rejects_fenced_requirement() -> None:
    routing = load_routing_v3()
    routing_input = routing_input_from_blocks(
        routing,
        (("fenced_block", "```\nrequirement\n```"), ("paragraph", "draft")),
    )
    directive = requirements_directive(
        routing,
        requirement_block_ids=["block-1"],
        subject_block_ids=["block-2"],
    )

    with pytest.raises(routing.RoutingDirectiveInputError):
        routing.validate_routing_directive_for_input(directive, routing_input)


def test_v3_requirements_rejects_subject_selection_out_of_order() -> None:
    routing = load_routing_v3()
    routing_input = routing_input_from_blocks(
        routing,
        (
            ("list_item", "- requirement"),
            ("paragraph", "subject one"),
            ("paragraph", "subject two"),
        ),
    )
    directive = requirements_directive(
        routing,
        requirement_block_ids=["block-1"],
        subject_block_ids=["block-3", "block-2"],
    )

    with pytest.raises(routing.RoutingDirectiveInputError):
        routing.validate_routing_directive_for_input(directive, routing_input)


@pytest.mark.parametrize(
    ("blocks", "requirement_ids", "subject_ids"),
    (
        (
            (("paragraph", "r" * 1_001), ("paragraph", "subject")),
            ("block-1",),
            ("block-2",),
        ),
        (
            tuple(("paragraph", "r" * 900) for _ in range(7))
            + (("paragraph", "subject"),),
            tuple(f"block-{index}" for index in range(1, 8)),
            ("block-8",),
        ),
        (
            (
                ("list_item", "- requirement"),
                ("paragraph", "s" * 4_100),
                ("paragraph", "t" * 4_100),
            ),
            ("block-1",),
            ("block-2", "block-3"),
        ),
        (
            (
                ("paragraph", "r" * 600),
                ("paragraph", "q" * 600),
                ("paragraph", "s" * 7_801),
            ),
            ("block-1", "block-2"),
            ("block-3",),
        ),
    ),
)
def test_v3_requirements_rejects_selected_text_over_bounds(
    blocks,
    requirement_ids,
    subject_ids,
) -> None:
    routing = load_routing_v3()
    routing_input = routing_input_from_blocks(routing, blocks)
    directive = requirements_directive(
        routing,
        requirement_block_ids=requirement_ids,
        subject_block_ids=subject_ids,
    )

    with pytest.raises(routing.RoutingDirectiveInputError) as error:
        routing.validate_routing_directive_for_input(directive, routing_input)

    assert str(error.value) == "Routing directive is incompatible with its input."


def test_v3_requirements_defensively_rejects_oversized_subject_block() -> None:
    routing = load_routing_v3()
    candidate_type = routing.RoutingTextBlockCandidate
    message = "requirement\n\n" + "s" * 8_001
    routing_input = routing.AgentColRoutingInput.model_construct(
        current_message=message,
        candidate_urls=(),
        numeric_candidates=(),
        numeric_projection_incomplete=False,
        text_block_candidates=(
            candidate_type(
                candidate_id="block-1",
                text="requirement",
                start_index=0,
                end_index=11,
                structural_kind="paragraph",
            ),
            candidate_type.model_construct(
                candidate_id="block-2",
                text="s" * 8_001,
                start_index=13,
                end_index=8_014,
                structural_kind="paragraph",
            ),
        ),
        text_projection_incomplete=False,
        available_capabilities=("requirements_verification",),
    )
    directive = requirements_directive(
        routing,
        requirement_block_ids=["block-1"],
        subject_block_ids=["block-2"],
    )

    with pytest.raises(routing.RoutingDirectiveInputError):
        routing.validate_routing_directive_for_input(directive, routing_input)


@pytest.mark.parametrize(
    "field,value",
    (
        ("objective", "x" * 1_001),
        ("constraints", ["x" * 301]),
    ),
)
def test_v3_requirements_rejects_over_bound_task_text(
    field: str,
    value: object,
) -> None:
    routing = load_routing_v3()

    with pytest.raises(ValidationError):
        requirements_directive(routing, **{field: value})


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


def computation_routing_input(routing):
    message = (
        "Calculate the mean of 12, 15, and 18 with precision set at "
        "2 decimal places."
    )
    projection = project_routing_numeric_candidates(message)
    return routing.AgentColRoutingInput(
        current_message=message,
        numeric_candidates=projection.candidates,
        numeric_projection_incomplete=projection.numeric_projection_incomplete,
        available_capabilities=("source", "research", "computation"),
    )


def computation_directive(routing, **intent_changes):
    payload = valid_computation_directive_payload()
    payload["computation_intent"].update(intent_changes)
    return routing.AgentColRoutingDirective.model_validate(payload)


@pytest.mark.parametrize(
    ("directive_payload", "routing_input_payload"),
    (
        ({"route": "direct"}, {"current_message": "Answer directly."}),
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
                "current_message": "Analyze https://example.com/.",
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
def test_v3_preserves_existing_route_cross_validation(
    directive_payload: dict[str, object],
    routing_input_payload: dict[str, object],
) -> None:
    routing = load_routing_v3()
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


def test_v3_preserves_computation_cross_validation() -> None:
    routing = load_routing_v3()
    directive = computation_directive(routing)
    routing_input = computation_routing_input(routing)

    assert (
        routing.validate_routing_directive_for_input(directive, routing_input)
        is directive
    )


@pytest.mark.parametrize(
    "case",
    ("source_capability", "source_unknown_id", "research_capability"),
)
def test_v3_existing_expert_routes_reject_incompatible_input(case: str) -> None:
    routing = load_routing_v3()
    if case.startswith("source"):
        directive = routing.AgentColRoutingDirective(
            route="source",
            source_intent={
                "objective": "Analyze the supplied page.",
                "selected_url_ids": [
                    "url-2" if case == "source_unknown_id" else "url-1"
                ],
            },
        )
        routing_input = routing.AgentColRoutingInput(
            current_message="Analyze https://example.com/.",
            candidate_urls=(
                {
                    "candidate_id": "url-1",
                    "url": "https://example.com/",
                    "source": "current_message",
                },
            ),
            available_capabilities=(
                () if case == "source_capability" else ("source",)
            ),
        )
    else:
        directive = routing.AgentColRoutingDirective(
            route="research",
            research_intent={
                "question": "What changed?",
                "objective": "Find current public evidence.",
            },
        )
        routing_input = routing.AgentColRoutingInput(
            current_message="What changed?",
        )

    with pytest.raises(routing.RoutingDirectiveInputError) as error:
        routing.validate_routing_directive_for_input(directive, routing_input)

    assert str(error.value) == "Routing directive is incompatible with its input."


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
def test_v3_computation_rejects_incompatible_input(case: str) -> None:
    routing = load_routing_v3()
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
        message = "Calculate the mean of $12 and 15."
        projection = project_routing_numeric_candidates(message)
        routing_input = routing.AgentColRoutingInput(
            current_message=message,
            numeric_candidates=projection.candidates,
            available_capabilities=("computation",),
        )
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

    assert str(error.value) == "Routing directive is incompatible with its input."
    assert "private.example" not in str(error.value)
