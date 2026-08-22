import pytest
from pydantic import ValidationError


def test_valid_directives_normalize_route_specific_payloads() -> None:
    from agent_col_routing import AgentColRoutingDirective

    direct = AgentColRoutingDirective(route="direct")
    clarification = AgentColRoutingDirective(
        route="clarify",
        clarifying_question="  Which supplied page should I analyze?  ",
    )
    source = AgentColRoutingDirective(
        route="source",
        source_intent={
            "objective": "  Compare the two supplied pages.  ",
            "selected_url_ids": ["url-1", "url-2"],
            "constraints": ["  Use only retrieved evidence.  "],
        },
    )
    research = AgentColRoutingDirective(
        route="research",
        research_intent={
            "question": "  What is the current stable Python release?  ",
            "objective": "  Verify it with current public evidence.  ",
            "constraints": [],
        },
    )

    assert direct.schema_version == "1.0"
    assert direct.clarifying_question is None
    assert clarification.clarifying_question == (
        "Which supplied page should I analyze?"
    )
    assert source.source_intent is not None
    assert source.source_intent.objective == "Compare the two supplied pages."
    assert source.source_intent.selected_url_ids == ("url-1", "url-2")
    assert source.source_intent.constraints == (
        "Use only retrieved evidence.",
    )
    assert research.research_intent is not None
    assert research.research_intent.question == (
        "What is the current stable Python release?"
    )
    assert research.research_intent.objective == (
        "Verify it with current public evidence."
    )
    assert research.research_intent.constraints == ()


@pytest.mark.parametrize(
    "payload",
    (
        {"route": "direct", "private_reasoning": "hidden"},
        {"schema_version": "2.0", "route": "direct"},
        {"route": "direct", "clarifying_question": "Why?"},
        {"route": "clarify"},
        {
            "route": "clarify",
            "clarifying_question": "Which source?",
            "source_intent": {
                "objective": "Analyze it.",
                "selected_url_ids": ["url-1"],
            },
        },
        {"route": "source"},
        {
            "route": "source",
            "source_intent": {
                "objective": "Analyze it.",
                "selected_url_ids": ["url-1"],
            },
            "research_intent": {
                "question": "What is current?",
                "objective": "Verify it.",
            },
        },
        {"route": "research"},
        {
            "route": "source",
            "source_intent": {
                "objective": "Analyze it.",
                "selected_url_ids": ["url-1", "url-1"],
            },
        },
        {
            "route": "source",
            "source_intent": {
                "objective": "Analyze it.",
                "selected_url_ids": [
                    "url-1",
                    "url-2",
                    "url-3",
                    "url-4",
                ],
            },
        },
        {
            "route": "research",
            "research_intent": {
                "question": "What is current?",
                "objective": "Verify it.",
                "constraints": ["bounded"] * 6,
            },
        },
        {
            "route": "source",
            "source_intent": {
                "objective": "   ",
                "selected_url_ids": ["url-1"],
            },
        },
        {
            "route": "clarify",
            "clarifying_question": "q" * 301,
        },
    ),
)
def test_directive_rejects_invalid_or_mismatched_structure(
    payload: dict[str, object],
) -> None:
    from agent_col_routing import AgentColRoutingDirective

    with pytest.raises(ValidationError):
        AgentColRoutingDirective.model_validate(payload)


def test_projection_returns_bounded_user_authored_public_urls() -> None:
    from agent_col_routing import project_routing_url_candidates

    candidates = project_routing_url_candidates(
        current_message=(
            "Compare https://example.com/specification and "
            "https://docs.python.org/3/library/asyncio.html."
        ),
        recent_user_messages=(
            "Do not use http://127.0.0.1/private.",
            (
                "Earlier I shared https://example.com/specification and "
                "(https://fastapi.tiangolo.com/)."
            ),
        ),
    )

    assert tuple(candidate.candidate_id for candidate in candidates) == (
        "url-1",
        "url-2",
        "url-3",
    )
    assert tuple(str(candidate.url) for candidate in candidates) == (
        "https://example.com/specification",
        "https://docs.python.org/3/library/asyncio.html",
        "https://fastapi.tiangolo.com/",
    )
    assert tuple(candidate.source for candidate in candidates) == (
        "current_message",
        "current_message",
        "recent_user_history",
    )


def test_projection_preserves_url_path_and_query_punctuation() -> None:
    from agent_col_routing import project_routing_url_candidates

    candidates = project_routing_url_candidates(
        current_message=(
            "Read https://example.com/search?q=why? and "
            "https://example.com/path!."
        ),
        recent_user_messages=(),
    )

    assert tuple(str(candidate.url) for candidate in candidates) == (
        "https://example.com/search?q=why?",
        "https://example.com/path!",
    )


def test_projection_caps_candidates_at_eight() -> None:
    from agent_col_routing import project_routing_url_candidates

    candidates = project_routing_url_candidates(
        current_message=" ".join(
            f"https://example.com/source-{index}" for index in range(1, 10)
        ),
        recent_user_messages=(),
    )

    assert len(candidates) == 8
    assert candidates[-1].candidate_id == "url-8"
    assert str(candidates[-1].url) == "https://example.com/source-8"


def test_routing_input_normalizes_bounded_context() -> None:
    from agent_col_routing import AgentColRoutingInput

    routing_input = AgentColRoutingInput(
        current_message="  Analyze the supplied page.  ",
        candidate_urls=(
            {
                "candidate_id": "url-1",
                "url": "https://example.com/specification",
                "source": "current_message",
            },
        ),
        available_capabilities=("source", "research"),
    )

    assert routing_input.current_message == "Analyze the supplied page."
    assert tuple(
        str(candidate.url) for candidate in routing_input.candidate_urls
    ) == ("https://example.com/specification",)
    assert routing_input.available_capabilities == ("source", "research")


@pytest.mark.parametrize(
    "payload",
    (
        {
            "current_message": "   ",
            "available_capabilities": ["source"],
        },
        {
            "current_message": "m" * 10_001,
            "available_capabilities": ["source"],
        },
        {
            "current_message": "Analyze sources.",
            "candidate_urls": [
                {
                    "candidate_id": f"url-{index}",
                    "url": f"https://example.com/{index}",
                    "source": "current_message",
                }
                for index in range(1, 10)
            ],
            "available_capabilities": ["source"],
        },
        {
            "current_message": "Analyze sources.",
            "candidate_urls": [
                {
                    "candidate_id": "url-1",
                    "url": "https://example.com/one",
                    "source": "current_message",
                },
                {
                    "candidate_id": "url-1",
                    "url": "https://example.com/two",
                    "source": "current_message",
                },
            ],
            "available_capabilities": ["source"],
        },
        {
            "current_message": "Analyze sources.",
            "candidate_urls": [
                {
                    "candidate_id": "url-1",
                    "url": "https://example.com/same",
                    "source": "current_message",
                },
                {
                    "candidate_id": "url-2",
                    "url": "https://example.com/same",
                    "source": "recent_user_history",
                },
            ],
            "available_capabilities": ["source"],
        },
        {
            "current_message": "Analyze a source.",
            "candidate_urls": [
                {
                    "candidate_id": "url-1",
                    "url": "http://127.0.0.1/private",
                    "source": "current_message",
                },
            ],
            "available_capabilities": ["source"],
        },
        {
            "current_message": "Analyze a source.",
            "candidate_urls": [
                {
                    "candidate_id": "url-1",
                    "url": "https://example.com/",
                    "source": "model_history",
                },
            ],
            "available_capabilities": ["source"],
        },
        {
            "current_message": "Calculate it.",
            "available_capabilities": ["computation"],
        },
        {
            "current_message": "Research it.",
            "available_capabilities": ["research", "research"],
        },
        {
            "current_message": "Private context must not enter routing.",
            "available_capabilities": ["source"],
            "user_id": "private-user",
        },
        {
            "current_message": "Private context must not enter routing.",
            "available_capabilities": ["source"],
            "profile": {"preferred_name": "Private"},
        },
    ),
)
def test_routing_input_rejects_unbounded_or_private_context(
    payload: dict[str, object],
) -> None:
    from agent_col_routing import AgentColRoutingInput

    with pytest.raises(ValidationError):
        AgentColRoutingInput.model_validate(payload)


def test_directive_validates_for_input_with_exact_context() -> None:
    from agent_col_routing import (
        AgentColRoutingDirective,
        AgentColRoutingInput,
        validate_routing_directive_for_input,
    )

    routing_input = AgentColRoutingInput(
        current_message="Compare the supplied pages.",
        candidate_urls=(
            {
                "candidate_id": "url-1",
                "url": "https://example.com/one",
                "source": "current_message",
            },
            {
                "candidate_id": "url-2",
                "url": "https://example.com/two",
                "source": "recent_user_history",
            },
        ),
        available_capabilities=("source", "research"),
    )
    source = AgentColRoutingDirective(
        route="source",
        source_intent={
            "objective": "Compare both pages.",
            "selected_url_ids": ("url-2", "url-1"),
        },
    )
    research = AgentColRoutingDirective(
        route="research",
        research_intent={
            "question": "What changed this week?",
            "objective": "Verify the change with current evidence.",
        },
    )

    assert validate_routing_directive_for_input(source, routing_input) is source
    assert source.source_intent is not None
    assert source.source_intent.selected_url_ids == ("url-2", "url-1")
    assert (
        validate_routing_directive_for_input(research, routing_input)
        is research
    )


@pytest.mark.parametrize(
    "directive_payload,routing_input_payload",
    (
        (
            {"route": "direct"},
            {
                "current_message": "Answer directly.",
                "available_capabilities": [],
            },
        ),
        (
            {
                "route": "clarify",
                "clarifying_question": "Which page should I analyze?",
            },
            {
                "current_message": "Please analyze it.",
                "available_capabilities": [],
            },
        ),
    ),
)
def test_nonexpert_directive_validates_for_input_without_expert_access(
    directive_payload: dict[str, object],
    routing_input_payload: dict[str, object],
) -> None:
    from agent_col_routing import (
        AgentColRoutingDirective,
        AgentColRoutingInput,
        validate_routing_directive_for_input,
    )

    directive = AgentColRoutingDirective.model_validate(directive_payload)
    routing_input = AgentColRoutingInput.model_validate(routing_input_payload)

    assert (
        validate_routing_directive_for_input(directive, routing_input)
        is directive
    )


@pytest.mark.parametrize(
    "directive_payload,routing_input_payload",
    (
        (
            {
                "route": "source",
                "source_intent": {
                    "objective": "Analyze the missing page.",
                    "selected_url_ids": ["url-2"],
                },
            },
            {
                "current_message": "Analyze the page.",
                "candidate_urls": [
                    {
                        "candidate_id": "url-1",
                        "url": "https://example.com/private-task-name",
                        "source": "current_message",
                    },
                ],
                "available_capabilities": ["source"],
            },
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
                        "url": "https://example.com/private-task-name",
                        "source": "current_message",
                    },
                ],
                "available_capabilities": [],
            },
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
                "available_capabilities": ["source"],
            },
        ),
        (
            {
                "route": "research",
                "research_intent": {
                    "question": "What changed?",
                    "objective": "Verify the change.",
                },
            },
            {
                "current_message": "What changed?",
                "available_capabilities": ["source"],
            },
        ),
    ),
)
def test_directive_rejects_incompatible_routing_input_for_input_without_leak(
    directive_payload: dict[str, object],
    routing_input_payload: dict[str, object],
) -> None:
    from agent_col_routing import (
        AgentColRoutingDirective,
        AgentColRoutingInput,
        RoutingDirectiveInputError,
        validate_routing_directive_for_input,
    )

    directive = AgentColRoutingDirective.model_validate(directive_payload)
    routing_input = AgentColRoutingInput.model_validate(routing_input_payload)

    with pytest.raises(RoutingDirectiveInputError) as error:
        validate_routing_directive_for_input(directive, routing_input)

    assert str(error.value) == (
        "Routing directive is incompatible with its input."
    )
    assert "private-task-name" not in str(error.value)
