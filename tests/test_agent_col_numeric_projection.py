import importlib

import pytest
from pydantic import ValidationError


def load_numeric_projection():
    try:
        return importlib.import_module("agent_col_numeric_projection")
    except ModuleNotFoundError:
        pytest.fail("agent_col_numeric_projection has not been implemented")


def test_projection_preserves_supported_literals_and_exact_spans() -> None:
    projection_module = load_numeric_projection()
    message = "Use -2, 1,234.5, .75, 6e2, 5%, and $9.99."

    projection = projection_module.project_routing_numeric_candidates(
        message
    )

    assert projection.numeric_projection_incomplete is False
    assert tuple(
        candidate.candidate_id for candidate in projection.candidates
    ) == (
        "number-1",
        "number-2",
        "number-3",
        "number-4",
        "number-5",
        "number-6",
    )
    assert tuple(candidate.raw_text for candidate in projection.candidates) == (
        "-2",
        "1,234.5",
        ".75",
        "6e2",
        "5%",
        "$9.99",
    )
    assert tuple(candidate.value for candidate in projection.candidates) == (
        -2.0,
        1234.5,
        0.75,
        600.0,
        5.0,
        9.99,
    )
    assert tuple(
        candidate.unit_symbol for candidate in projection.candidates
    ) == (None, None, None, None, "%", "$")
    for candidate in projection.candidates:
        assert message[candidate.start_index:candidate.end_index] == (
            candidate.raw_text
        )


def test_projection_keeps_repeated_values_as_distinct_candidates() -> None:
    projection_module = load_numeric_projection()

    projection = projection_module.project_routing_numeric_candidates(
        "Compare 7 with 7."
    )

    assert tuple(
        (candidate.candidate_id, candidate.value)
        for candidate in projection.candidates
    ) == (("number-1", 7.0), ("number-2", 7.0))


@pytest.mark.parametrize(
    "payload",
    (
        {
            "candidate_id": "number-1",
            "raw_text": "1",
            "value": 1,
            "notation": "plain",
            "unit_symbol": None,
            "start_index": 0,
            "end_index": 1,
            "unexpected": True,
        },
        {
            "candidate_id": "number-33",
            "raw_text": "1",
            "value": 1,
            "notation": "plain",
            "unit_symbol": None,
            "start_index": 0,
            "end_index": 1,
        },
        {
            "candidate_id": "number-1",
            "raw_text": "inf",
            "value": float("inf"),
            "notation": "plain",
            "unit_symbol": None,
            "start_index": 0,
            "end_index": 3,
        },
        {
            "candidate_id": "number-1",
            "raw_text": "1",
            "value": 1,
            "notation": "plain",
            "unit_symbol": "points",
            "start_index": 0,
            "end_index": 1,
        },
        {
            "candidate_id": "number-1",
            "raw_text": "1",
            "value": 1,
            "notation": "plain",
            "unit_symbol": None,
            "start_index": 2,
            "end_index": 1,
        },
        {
            "candidate_id": "number-1",
            "raw_text": "2",
            "value": 3,
            "notation": "plain",
            "unit_symbol": None,
            "start_index": 0,
            "end_index": 1,
        },
        {
            "candidate_id": "number-1",
            "raw_text": "5%",
            "value": 0.05,
            "notation": "percent",
            "unit_symbol": "%",
            "start_index": 0,
            "end_index": 2,
        },
    ),
)
def test_numeric_candidate_rejects_invalid_contract_shapes(
    payload: dict[str, object],
) -> None:
    projection_module = load_numeric_projection()

    with pytest.raises(ValidationError):
        projection_module.RoutingNumericCandidate.model_validate(payload)


@pytest.mark.parametrize(
    "message",
    (
        "Use 1/2 and 4.",
        "Use a 3:1 ratio and 4.",
        "Use the range 5-10 and 4.",
        "Use the date 2026-08-22 and 4.",
        "Use 12:30 and 4.",
        "Use version 3.14 and 4.",
        "Use v3.14 and 4.",
    ),
)
def test_ambiguous_numeric_syntax_marks_projection_incomplete(
    message: str,
) -> None:
    projection_module = load_numeric_projection()

    projection = projection_module.project_routing_numeric_candidates(message)

    assert projection.numeric_projection_incomplete is True
    assert tuple(candidate.raw_text for candidate in projection.candidates) == (
        "4",
    )
    assert projection_module.contains_numeric_like_text(message) is True


def test_projection_masks_url_numbers_without_claiming_incomplete() -> None:
    projection_module = load_numeric_projection()

    projection = projection_module.project_routing_numeric_candidates(
        "Analyze https://example.com/v2?limit=10"
    )

    assert projection.candidates == ()
    assert projection.numeric_projection_incomplete is False


def test_projection_exposes_first_32_candidates_and_reports_overflow() -> None:
    projection_module = load_numeric_projection()
    message = "Values: " + ", ".join(str(value) for value in range(1, 34))

    projection = projection_module.project_routing_numeric_candidates(message)

    assert len(projection.candidates) == 32
    assert projection.candidates[-1].raw_text == "32"
    assert projection.numeric_projection_incomplete is True


def test_projection_ignores_spelled_out_numbers() -> None:
    projection_module = load_numeric_projection()

    projection = projection_module.project_routing_numeric_candidates(
        "Calculate the mean of one, two, and three."
    )

    assert projection.candidates == ()
    assert projection.numeric_projection_incomplete is False
    assert projection_module.contains_numeric_like_text(
        "Calculate the mean of one, two, and three."
    ) is False


@pytest.mark.parametrize(
    "message",
    (
        "Use item123 and 4.",
        "Use $5% and 4.",
        "Use invalid grouping 12,34 and 4.",
    ),
)
def test_unsupported_numeric_like_text_is_not_decomposed(
    message: str,
) -> None:
    projection_module = load_numeric_projection()

    projection = projection_module.project_routing_numeric_candidates(message)

    assert projection.numeric_projection_incomplete is True
    assert tuple(candidate.raw_text for candidate in projection.candidates) == (
        "4",
    )
