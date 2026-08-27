from types import SimpleNamespace

from google.genai import types


def test_generate_content_summary_reports_metadata_without_text() -> None:
    from research_provider_compatibility_check import (
        summarize_generate_content_response,
    )

    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(
                            text="Private generated research answer."
                        )
                    ],
                ),
                grounding_metadata=types.GroundingMetadata(
                    grounding_chunks=[
                        types.GroundingChunk(
                            web=types.GroundingChunkWeb(
                                uri="https://example.com/",
                                title="Example Domain",
                            )
                        )
                    ],
                    grounding_supports=[
                        types.GroundingSupport(
                            segment=types.Segment(
                                text="Private generated research answer."
                            ),
                            grounding_chunk_indices=[0],
                        )
                    ],
                ),
            )
        ]
    )

    observation = summarize_generate_content_response(
        probe_id="direct-generate-content",
        response=response,
    )
    line = observation.to_report_line()

    assert line == (
        "research-provider probe=direct-generate-content "
        "surface=generate_content status=completed error_class=none "
        "api_status=none candidates=1 grounding_metadata=true "
        "grounding_chunks=1 grounding_supports=1 steps=none "
        "google_search_calls=0 google_search_results=0 model_outputs=0 "
        "annotations=0 invalid_output_reason=none"
    )
    assert "Private generated research answer" not in line
    assert "example.com" not in line


def test_interaction_summary_counts_search_steps_and_annotations() -> None:
    from research_provider_compatibility_check import summarize_interaction

    interaction = SimpleNamespace(
        status="completed",
        steps=[
            SimpleNamespace(type="google_search_call"),
            SimpleNamespace(type="google_search_result"),
            SimpleNamespace(
                type="model_output",
                content=[
                    SimpleNamespace(
                        type="text",
                        text="Private interaction answer.",
                        annotations=[
                            SimpleNamespace(type="url_citation"),
                            SimpleNamespace(type="url_citation"),
                        ],
                    )
                ],
            ),
        ],
    )

    observation = summarize_interaction(
        probe_id="interactions-auto",
        interaction=interaction,
    )
    line = observation.to_report_line()

    assert line == (
        "research-provider probe=interactions-auto "
        "surface=interactions status=completed error_class=none "
        "api_status=none candidates=0 grounding_metadata=false "
        "grounding_chunks=0 grounding_supports=0 "
        "steps=google_search_call,google_search_result,model_output "
        "google_search_calls=1 google_search_results=1 model_outputs=1 "
        "annotations=2 invalid_output_reason=none"
    )
    assert "Private interaction answer" not in line


def test_probe_error_summary_reports_only_exception_class() -> None:
    from research_provider_compatibility_check import summarize_probe_error

    observation = summarize_probe_error(
        probe_id="interactions-forced",
        surface="interactions",
        exc=RuntimeError("secret provider detail"),
    )
    line = observation.to_report_line()

    assert line == (
        "research-provider probe=interactions-forced "
        "surface=interactions status=error error_class=RuntimeError "
        "api_status=none candidates=0 grounding_metadata=false "
        "grounding_chunks=0 grounding_supports=0 steps=none "
        "google_search_calls=0 google_search_results=0 model_outputs=0 "
        "annotations=0 invalid_output_reason=none"
    )
    assert "secret provider detail" not in line
