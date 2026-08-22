import importlib

import pytest
from pydantic import ValidationError


def load_text_projection():
    try:
        return importlib.import_module("agent_col_text_projection")
    except ModuleNotFoundError:
        pytest.fail("agent_col_text_projection has not been implemented")


def test_projection_preserves_structured_blocks_and_exact_spans() -> None:
    projection_module = load_text_projection()
    message = (
        "Compare the draft.\n\n"
        "Requirements:\n"
        "- Include sources.\n"
        "- State limitations.\n\n"
        "Subject:\n"
        "The draft includes sources."
    )

    projection = projection_module.project_routing_text_blocks(message)

    assert projection.text_projection_incomplete is False
    assert tuple(
        (candidate.candidate_id, candidate.structural_kind, candidate.text)
        for candidate in projection.candidates
    ) == (
        ("block-1", "paragraph", "Compare the draft."),
        ("block-2", "heading", "Requirements:"),
        ("block-3", "list_item", "- Include sources."),
        ("block-4", "list_item", "- State limitations."),
        ("block-5", "heading", "Subject:"),
        ("block-6", "paragraph", "The draft includes sources."),
    )
    for candidate in projection.candidates:
        assert message[candidate.start_index:candidate.end_index] == (
            candidate.text
        )


def test_repeated_text_receives_distinct_ids_and_spans() -> None:
    projection_module = load_text_projection()
    message = "Same text.\n\nSame text."

    projection = projection_module.project_routing_text_blocks(message)

    assert tuple(
        (candidate.candidate_id, candidate.start_index, candidate.end_index)
        for candidate in projection.candidates
    ) == (("block-1", 0, 10), ("block-2", 12, 22))


def test_heading_and_ordered_list_syntax_is_projected() -> None:
    projection_module = load_text_projection()
    label = "a" * 119 + ":"
    long_label = "b" * 120 + ":"
    message = f"## Heading\n{label}\n1. First\n2) Second\n\n{long_label}"

    projection = projection_module.project_routing_text_blocks(message)

    assert tuple(
        (candidate.structural_kind, candidate.text)
        for candidate in projection.candidates
    ) == (
        ("heading", "## Heading"),
        ("heading", label),
        ("list_item", "1. First"),
        ("list_item", "2) Second"),
        ("paragraph", long_label),
    )


def test_complete_fences_are_opaque_blocks() -> None:
    projection_module = load_text_projection()
    message = "```text\nalpha\n```\n\n~~~\nbeta\n~~~~"

    projection = projection_module.project_routing_text_blocks(message)

    assert projection.text_projection_incomplete is False
    assert tuple(
        (candidate.structural_kind, candidate.text)
        for candidate in projection.candidates
    ) == (
        ("fenced_block", "```text\nalpha\n```"),
        ("fenced_block", "~~~\nbeta\n~~~~"),
    )


def test_unclosed_fence_is_not_exposed_and_marks_projection_incomplete() -> None:
    projection_module = load_text_projection()
    message = "Visible paragraph.\n\n```text\nsecret partial content"

    projection = projection_module.project_routing_text_blocks(message)

    assert tuple(candidate.text for candidate in projection.candidates) == (
        "Visible paragraph.",
    )
    assert projection.text_projection_incomplete is True


def test_projection_retains_first_64_blocks_and_marks_overflow() -> None:
    projection_module = load_text_projection()
    message = "\n\n".join(f"paragraph {index}" for index in range(65))

    projection = projection_module.project_routing_text_blocks(message)

    assert tuple(
        candidate.candidate_id for candidate in projection.candidates
    ) == tuple(f"block-{index}" for index in range(1, 65))
    assert projection.text_projection_incomplete is True


def test_oversized_block_is_omitted_and_marks_projection_incomplete() -> None:
    projection_module = load_text_projection()

    projection = projection_module.project_routing_text_blocks("x" * 8_001)

    assert projection.candidates == ()
    assert projection.text_projection_incomplete is True


@pytest.mark.parametrize("message", ["", " \t\n", "x" * 10_001])
def test_invalid_message_boundaries_are_rejected(message: str) -> None:
    projection_module = load_text_projection()

    with pytest.raises(ValidationError):
        projection_module.project_routing_text_blocks(message)


def test_crlf_source_slices_remain_exact() -> None:
    projection_module = load_text_projection()
    message = "Requirements:\r\n- First.\r\n\r\nSubject:\r\nDraft text."

    projection = projection_module.project_routing_text_blocks(message)

    assert tuple(candidate.text for candidate in projection.candidates) == (
        "Requirements:",
        "- First.",
        "Subject:",
        "Draft text.",
    )
    assert all(
        message[candidate.start_index:candidate.end_index] == candidate.text
        for candidate in projection.candidates
    )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "candidate_id": "block-1",
            "text": "valid",
            "start_index": 0,
            "end_index": 5,
            "structural_kind": "paragraph",
            "extra": True,
        },
        {
            "candidate_id": "block-65",
            "text": "valid",
            "start_index": 0,
            "end_index": 5,
            "structural_kind": "paragraph",
        },
        {
            "candidate_id": "block-1",
            "text": "valid",
            "start_index": 0,
            "end_index": 5,
            "structural_kind": "semantic_requirement",
        },
        {
            "candidate_id": "block-1",
            "text": "",
            "start_index": 0,
            "end_index": 1,
            "structural_kind": "paragraph",
        },
        {
            "candidate_id": "block-1",
            "text": "x" * 8_001,
            "start_index": 0,
            "end_index": 8_001,
            "structural_kind": "paragraph",
        },
        {
            "candidate_id": "block-1",
            "text": "valid",
            "start_index": 5,
            "end_index": 5,
            "structural_kind": "paragraph",
        },
    ],
)
def test_candidate_model_rejects_invalid_contracts(
    payload: dict[str, object],
) -> None:
    projection_module = load_text_projection()

    with pytest.raises(ValidationError):
        projection_module.RoutingTextBlockCandidate.model_validate(payload)
