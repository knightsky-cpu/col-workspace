import json

import pytest
from google.genai import types
from pydantic import ValidationError


def source_response(
    *,
    draft: dict[str, object],
    retrievals: tuple[tuple[str, types.UrlRetrievalStatus], ...],
    chunk_urls: tuple[str, ...],
    supports: tuple[types.GroundingSupport, ...],
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(text=json.dumps(draft))
                    ],
                ),
                url_context_metadata=types.UrlContextMetadata(
                    url_metadata=[
                        types.UrlMetadata(
                            retrieved_url=url,
                            url_retrieval_status=status,
                        )
                        for url, status in retrievals
                    ]
                ),
                grounding_metadata=types.GroundingMetadata(
                    grounding_chunks=[
                        types.GroundingChunk(
                            web=types.GroundingChunkWeb(
                                uri=url,
                                title=f"Source {index}",
                            )
                        )
                        for index, url in enumerate(chunk_urls, start=1)
                    ],
                    grounding_supports=list(supports),
                ),
            )
        ]
    )


def bounded_source_draft(
    *,
    statement: str = "Example Domain is reserved for documentation.",
    source_id: str = "source-1",
) -> dict[str, object]:
    return {
        "facts": [{"text": statement, "source_ids": [source_id]}],
        "requirements": [],
        "constraints": [],
        "assumptions": [],
        "open_questions": [],
    }


def test_source_input_normalizes_bounded_task_context() -> None:
    from source_expert import SourceExpertInput

    request = SourceExpertInput(
        objective="  Extract the explicit requirements.  ",
        urls=("https://example.com/specification",),
        constraints=("  Separate facts from assumptions.  ",),
    )

    assert request.objective == "Extract the explicit requirements."
    assert tuple(str(url) for url in request.urls) == (
        "https://example.com/specification",
    )
    assert request.constraints == ("Separate facts from assumptions.",)

    with pytest.raises(ValidationError):
        SourceExpertInput(
            objective="Extract requirements.",
            urls=("https://example.com/specification",),
            user_id="private-user",
        )


@pytest.mark.parametrize(
    "urls",
    (
        (),
        tuple(f"https://example.com/{index}" for index in range(4)),
        (
            "https://example.com/specification",
            "https://example.com/specification",
        ),
        ("http://127.0.0.1/private",),
        ("http://10.0.0.1/private",),
        ("http://[::1]/private",),
        ("https://localhost/private",),
        ("https://service.internal/private",),
        ("https://user:password@example.com/private",),
    ),
)
def test_source_input_rejects_disallowed_url_sets(
    urls: tuple[str, ...],
) -> None:
    from source_expert import SourceExpertInput

    with pytest.raises(ValidationError):
        SourceExpertInput(
            objective="Extract requirements.",
            urls=urls,
        )


@pytest.mark.parametrize(
    "overrides",
    (
        {"objective": "o" * 1_001},
        {"constraints": ("bounded",) * 6},
        {"constraints": ("c" * 301,)},
    ),
)
def test_source_input_rejects_unbounded_task_context(
    overrides: dict[str, object],
) -> None:
    from source_expert import SourceExpertInput

    values: dict[str, object] = {
        "objective": "Extract requirements.",
        "urls": ("https://example.com/specification",),
    }
    values.update(overrides)

    with pytest.raises(ValidationError):
        SourceExpertInput(**values)


def test_source_normalization_preserves_mixed_retrieval_and_grounding(
) -> None:
    from expert_contracts import ExpertStatus
    from source_expert import (
        SourceExpertInput,
        SourceRetrievalStatus,
        normalize_source_response,
    )

    statement = "Example Domain is reserved for documentation."
    request = SourceExpertInput(
        objective="Identify the documented purpose.",
        urls=(
            "https://example.com/",
            "https://example.com/missing",
        ),
    )
    response = source_response(
        draft=bounded_source_draft(statement=statement),
        retrievals=(
            (
                "https://example.com/",
                types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_SUCCESS,
            ),
            (
                "https://example.com/missing",
                types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_ERROR,
            ),
        ),
        chunk_urls=("https://example.com/",),
        supports=(
            types.GroundingSupport(
                segment=types.Segment(text=statement),
                grounding_chunk_indices=[0],
            ),
        ),
    )

    result = normalize_source_response(request=request, response=response)

    assert result.status is ExpertStatus.COMPLETED
    assert result.payload is not None
    assert [document.retrieval_status for document in result.payload.documents] == [
        SourceRetrievalStatus.RETRIEVED,
        SourceRetrievalStatus.ERROR,
    ]
    assert result.payload.facts[0].source_ids == ("source-1",)
    assert [source.source_id for source in result.payload.sources] == [
        "source-1"
    ]
    assert result.evidence is not None
    assert result.evidence.grounding_support_count == 1
    assert result.limitations == ("1 source could not be retrieved.",)


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_url_metadata",
        "unlisted_retrieval_url",
        "unlisted_grounding_url",
        "invalid_grounding_index",
        "missing_grounding_support",
    ),
)
def test_source_normalization_rejects_untrusted_or_incomplete_metadata(
    mutation: str,
) -> None:
    from expert_contracts import ExpertStatus
    from source_expert import SourceExpertInput, normalize_source_response

    statement = "Example Domain is reserved for documentation."
    request = SourceExpertInput(
        objective="Identify the documented purpose.",
        urls=("https://example.com/",),
    )
    retrievals = (
        (
            "https://example.com/",
            types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_SUCCESS,
        ),
    )
    chunk_urls = ("https://example.com/",)
    supports = (
        types.GroundingSupport(
            segment=types.Segment(text=statement),
            grounding_chunk_indices=[0],
        ),
    )
    if mutation == "unlisted_retrieval_url":
        retrievals = (
            (
                "https://attacker.example.net/",
                types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_SUCCESS,
            ),
        )
    elif mutation == "unlisted_grounding_url":
        chunk_urls = ("https://attacker.example.net/",)
    elif mutation == "invalid_grounding_index":
        supports = (
            types.GroundingSupport(
                segment=types.Segment(text=statement),
                grounding_chunk_indices=[4],
            ),
        )
    elif mutation == "missing_grounding_support":
        supports = ()
    response = source_response(
        draft=bounded_source_draft(statement=statement),
        retrievals=retrievals,
        chunk_urls=chunk_urls,
        supports=supports,
    )
    if mutation == "missing_url_metadata":
        response.candidates[0].url_context_metadata = None

    result = normalize_source_response(request=request, response=response)

    assert result.status is ExpertStatus.INVALID_OUTPUT
    assert result.payload is None
    assert result.evidence is None


@pytest.mark.parametrize(
    ("provider_status", "expected_status"),
    (
        (
            types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_ERROR,
            "error",
        ),
        (
            types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_PAYWALL,
            "paywall",
        ),
        (
            types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_UNSAFE,
            "unsafe",
        ),
    ),
)
def test_source_normalization_preserves_failed_provider_statuses(
    provider_status: types.UrlRetrievalStatus,
    expected_status: str,
) -> None:
    from expert_contracts import ExpertStatus
    from source_expert import SourceExpertInput, normalize_source_response

    request = SourceExpertInput(
        objective="Inspect the source.",
        urls=("https://example.com/", "https://example.com/secondary"),
    )
    statement = "Example Domain is reserved for documentation."
    response = source_response(
        draft=bounded_source_draft(statement=statement),
        retrievals=(
            (
                "https://example.com/",
                types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_SUCCESS,
            ),
            ("https://example.com/secondary", provider_status),
        ),
        chunk_urls=("https://example.com/",),
        supports=(
            types.GroundingSupport(
                segment=types.Segment(text=statement),
                grounding_chunk_indices=[0],
            ),
        ),
    )

    result = normalize_source_response(request=request, response=response)

    assert result.status is ExpertStatus.COMPLETED
    assert result.payload is not None
    assert result.payload.documents[1].retrieval_status.value == expected_status


def test_source_receipts_include_only_validated_grounded_sources() -> None:
    from source_expert import (
        SourceExpertInput,
        build_source_receipts,
        normalize_source_response,
    )

    statement = "Example Domain is reserved for documentation."
    request = SourceExpertInput(
        objective="Identify the documented purpose.",
        urls=("https://example.com/",),
    )
    result = normalize_source_response(
        request=request,
        response=source_response(
            draft=bounded_source_draft(statement=statement),
            retrievals=(
                (
                    "https://example.com/",
                    types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_SUCCESS,
                ),
            ),
            chunk_urls=("https://example.com/",),
            supports=(
                types.GroundingSupport(
                    segment=types.Segment(text=statement),
                    grounding_chunk_indices=[0],
                ),
            ),
        ),
    )

    receipts = build_source_receipts(result)

    assert [action.model_dump(mode="json") for action in receipts.actions] == [
        {"action_name": "url_context", "status": "completed"}
    ]
    assert [
        citation.model_dump(mode="json") for citation in receipts.citations
    ] == [
        {"uri": "https://example.com/", "label": "Source 1"}
    ]
