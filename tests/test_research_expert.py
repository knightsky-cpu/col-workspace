import pytest
from google.adk.events import Event
from google.adk.models import Gemini
from google.genai import types
from pydantic import ValidationError

from vertex_config import VertexAISettings


def test_research_input_normalizes_only_task_specific_fields() -> None:
    from research_expert import ResearchExpertInput

    request = ResearchExpertInput(
        question="  What is the current stable Python release?  ",
        objective="  Establish the current release from public evidence.  ",
        constraints=("  Prefer the official Python source.  ",),
    )

    assert request.question == "What is the current stable Python release?"
    assert request.objective == (
        "Establish the current release from public evidence."
    )
    assert request.constraints == ("Prefer the official Python source.",)

    with pytest.raises(ValidationError):
        ResearchExpertInput(
            question="Current Python release?",
            objective="Establish the version.",
            user_id="private-user",
        )


@pytest.mark.parametrize(
    "overrides",
    (
        {"question": "q" * 1_001},
        {"objective": "o" * 1_001},
        {"constraints": ("bounded",) * 6},
        {"constraints": ("c" * 301,)},
    ),
)
def test_research_input_rejects_unbounded_task_data(
    overrides: dict[str, object],
) -> None:
    from research_expert import ResearchExpertInput

    values: dict[str, object] = {
        "question": "Current Python release?",
        "objective": "Establish the version.",
    }
    values.update(overrides)

    with pytest.raises(ValidationError):
        ResearchExpertInput(**values)


def test_research_payload_requires_locally_linked_provider_sources() -> None:
    from research_expert import (
        ProviderSource,
        ResearchConfidence,
        ResearchExpertPayload,
        ResearchFinding,
    )

    source = ProviderSource(
        source_id="source-1",
        uri="https://docs.python.org/3/",
        label="Python documentation",
    )
    finding = ResearchFinding(
        claim="Python 3.14 is the current documentation series.",
        evidence_summary="The official documentation identifies 3.14.",
        source_ids=("source-1",),
        confidence="high",
        uncertainty=None,
    )
    payload = ResearchExpertPayload(
        findings=(finding,),
        sources=(source,),
        unresolved_questions=(),
    )

    assert finding.confidence is ResearchConfidence.HIGH
    assert payload.findings == (finding,)
    assert payload.sources == (source,)

    with pytest.raises(ValidationError):
        ResearchExpertPayload(
            findings=(
                finding.model_copy(update={"source_ids": ("source-2",)}),
            ),
            sources=(source,),
            unresolved_questions=(),
        )


@pytest.mark.parametrize(
    "uri",
    (
        "http://127.0.0.1/private",
        "http://10.0.0.1/private",
        "http://[::1]/private",
        "https://localhost/private",
        "https://private/private",
        "https://service.internal/private",
        "https://service.local/private",
        "https://user:password@example.com/private",
    ),
)
def test_provider_source_rejects_nonpublic_or_credentialed_urls(
    uri: str,
) -> None:
    from research_expert import ProviderSource

    with pytest.raises(ValidationError):
        ProviderSource(
            source_id="source-1",
            uri=uri,
            label="Private source",
        )


@pytest.mark.parametrize(
    "invalid_field",
    (
        {"source_id": "provider-1"},
        {"label": "   "},
        {"label": "l" * 161},
    ),
)
def test_provider_source_rejects_invalid_identity_fields(
    invalid_field: dict[str, str],
) -> None:
    from research_expert import ProviderSource

    values = {
        "source_id": "source-1",
        "uri": "https://www.python.org/downloads/",
        "label": "Python downloads",
    }
    values.update(invalid_field)

    with pytest.raises(ValidationError):
        ProviderSource(**values)


def test_research_draft_accepts_bounded_model_reasoning_without_urls() -> None:
    from research_expert import (
        ResearchConfidence,
        ResearchExpertDraft,
        ResearchFindingDraft,
    )

    draft = ResearchExpertDraft(
        findings=(
            ResearchFindingDraft(
                claim="Python 3.14.7 is the current stable release.",
                evidence_summary=(
                    "The official release page identifies version 3.14.7."
                ),
                confidence="high",
                uncertainty=None,
            ),
        ),
        unresolved_questions=("When will the next patch ship?",),
    )

    assert draft.findings[0].confidence is ResearchConfidence.HIGH
    assert draft.unresolved_questions == (
        "When will the next patch ship?",
    )


@pytest.mark.parametrize(
    "overrides",
    (
        {"claim": "   "},
        {"claim": "c" * 1_001},
        {"evidence_summary": "   "},
        {"evidence_summary": "e" * 1_001},
        {"uncertainty": "   "},
        {"uncertainty": "u" * 501},
    ),
)
def test_research_finding_draft_rejects_unbounded_text(
    overrides: dict[str, object],
) -> None:
    from research_expert import ResearchFindingDraft

    values: dict[str, object] = {
        "claim": "Supported claim.",
        "evidence_summary": "Public evidence supports the claim.",
        "confidence": "medium",
        "uncertainty": None,
    }
    values.update(overrides)

    with pytest.raises(ValidationError):
        ResearchFindingDraft(**values)


@pytest.mark.parametrize(
    "overrides",
    (
        {"findings": ()},
        {
            "findings": (
                {
                    "claim": "c",
                    "evidence_summary": "e",
                    "confidence": "low",
                },
            )
            * 9
        },
        {"unresolved_questions": ("question",) * 6},
        {"unresolved_questions": ("   ",)},
        {"unresolved_questions": ("q" * 501,)},
    ),
)
def test_research_draft_rejects_unbounded_collections(
    overrides: dict[str, object],
) -> None:
    from research_expert import ResearchExpertDraft

    values: dict[str, object] = {
        "findings": (
            {
                "claim": "Supported claim.",
                "evidence_summary": "Public evidence supports the claim.",
                "confidence": "medium",
            },
        ),
        "unresolved_questions": (),
    }
    values.update(overrides)

    with pytest.raises(ValidationError):
        ResearchExpertDraft(**values)


@pytest.mark.parametrize(
    "source_ids",
    (
        (),
        ("source-1",) * 2,
        tuple(f"source-{index}" for index in range(1, 7)),
    ),
)
def test_normalized_finding_requires_unique_bounded_source_ids(
    source_ids: tuple[str, ...],
) -> None:
    from research_expert import ResearchFinding

    with pytest.raises(ValidationError):
        ResearchFinding(
            claim="Supported claim.",
            evidence_summary="Public evidence supports the claim.",
            source_ids=source_ids,
            confidence="medium",
        )


@pytest.mark.parametrize(
    "source_two",
    (
        {
            "source_id": "source-1",
            "uri": "https://www.python.org/downloads/",
            "label": "Duplicate identifier",
        },
        {
            "source_id": "source-2",
            "uri": "https://docs.python.org/3/",
            "label": "Duplicate URI",
        },
        {
            "source_id": "source-2",
            "uri": "https://peps.python.org/",
            "label": "Unreferenced source",
        },
    ),
)
def test_research_payload_rejects_duplicate_or_unreferenced_sources(
    source_two: dict[str, str],
) -> None:
    from research_expert import (
        ProviderSource,
        ResearchExpertPayload,
        ResearchFinding,
    )

    finding = ResearchFinding(
        claim="Supported claim.",
        evidence_summary="Public evidence supports the claim.",
        source_ids=("source-1",),
        confidence="medium",
    )
    source_one = ProviderSource(
        source_id="source-1",
        uri="https://docs.python.org/3/",
        label="Python documentation",
    )

    with pytest.raises(ValidationError):
        ResearchExpertPayload(
            findings=(finding,),
            sources=(source_one, ProviderSource(**source_two)),
        )


@pytest.mark.parametrize(
    "overrides",
    (
        {"findings": ()},
        {"sources": ()},
        {"unresolved_questions": ("question",) * 6},
    ),
)
def test_research_payload_rejects_unbounded_collections(
    overrides: dict[str, object],
) -> None:
    from research_expert import (
        ProviderSource,
        ResearchExpertPayload,
        ResearchFinding,
    )

    values: dict[str, object] = {
        "findings": (
            ResearchFinding(
                claim="Supported claim.",
                evidence_summary="Public evidence supports the claim.",
                source_ids=("source-1",),
                confidence="medium",
            ),
        ),
        "sources": (
            ProviderSource(
                source_id="source-1",
                uri="https://docs.python.org/3/",
                label="Python documentation",
            ),
        ),
        "unresolved_questions": (),
    }
    values.update(overrides)

    with pytest.raises(ValidationError):
        ResearchExpertPayload(**values)


def test_completed_research_result_requires_matching_server_evidence() -> None:
    from expert_contracts import ExpertCapability, ExpertStatus
    from research_expert import (
        ProviderSource,
        ResearchExpertEvidence,
        ResearchExpertPayload,
        ResearchExpertResult,
        ResearchFinding,
    )

    payload = ResearchExpertPayload(
        findings=(
            ResearchFinding(
                claim="Supported claim.",
                evidence_summary="Public evidence supports the claim.",
                source_ids=("source-1",),
                confidence="medium",
            ),
        ),
        sources=(
            ProviderSource(
                source_id="source-1",
                uri="https://docs.python.org/3/",
                label="Python documentation",
            ),
        ),
    )
    evidence = ResearchExpertEvidence(
        source_ids=("source-1",),
        grounded_finding_count=1,
        grounding_support_count=1,
    )

    result = ResearchExpertResult(
        status="completed",
        summary="Public evidence supports one finding.",
        payload=payload,
        evidence=evidence,
    )

    assert result.capability is ExpertCapability.RESEARCH
    assert result.status is ExpertStatus.COMPLETED

    with pytest.raises(ValidationError):
        ResearchExpertResult(
            status="completed",
            summary="Public evidence supports one finding.",
            payload=payload,
            evidence=evidence.model_copy(
                update={"source_ids": ("source-2",)}
            ),
        )


def test_provider_sources_come_only_from_valid_grounding_chunks() -> None:
    from research_expert import extract_provider_sources

    metadata = types.GroundingMetadata(
        grounding_chunks=[
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://docs.python.org/3/",
                    title="  Python documentation  ",
                )
            ),
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://docs.python.org/3/",
                    title="Duplicate",
                )
            ),
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="http://127.0.0.1/private",
                    title="Private",
                )
            ),
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://www.python.org/downloads/",
                    title=None,
                )
            ),
            types.GroundingChunk(),
        ]
    )

    sources = extract_provider_sources(metadata)

    assert [source.model_dump(mode="json") for source in sources] == [
        {
            "source_id": "source-1",
            "uri": "https://docs.python.org/3/",
            "label": "Python documentation",
        },
        {
            "source_id": "source-2",
            "uri": "https://www.python.org/downloads/",
            "label": "www.python.org",
        },
    ]


def test_research_output_maps_findings_to_provider_supports() -> None:
    from expert_contracts import ExpertStatus
    from research_expert import (
        ResearchExpertDraft,
        normalize_research_output,
    )

    draft = ResearchExpertDraft(
        findings=(
            {
                "claim": "Python 3.14.7 is the current stable release.",
                "evidence_summary": "Python.org identifies version 3.14.7.",
                "confidence": "high",
            },
            {
                "claim": "Python 3.14 receives regular maintenance updates.",
                "evidence_summary": "The release page lists patch releases.",
                "confidence": "medium",
                "uncertainty": "The next patch date is not specified.",
            },
        ),
        unresolved_questions=("When will the next patch ship?",),
    )
    metadata = types.GroundingMetadata(
        grounding_chunks=[
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://www.python.org/downloads/",
                    title="Python downloads",
                )
            ),
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://docs.python.org/3/",
                    title="Python documentation",
                )
            ),
        ],
        grounding_supports=[
            types.GroundingSupport(
                segment=types.Segment(
                    text=(
                        "Python 3.14.7 is the current stable release."
                    )
                ),
                grounding_chunk_indices=[0],
            ),
            types.GroundingSupport(
                segment=types.Segment(
                    text=(
                        "Python 3.14 receives regular maintenance updates."
                    )
                ),
                grounding_chunk_indices=[0, 1],
            ),
        ],
    )

    result = normalize_research_output(
        raw_output=draft,
        response_text=draft.model_dump_json(),
        metadata=metadata,
    )

    assert result.status is ExpertStatus.COMPLETED
    assert result.summary == (
        "Research produced 2 grounded findings from 2 public sources."
    )
    assert result.payload is not None
    assert [finding.source_ids for finding in result.payload.findings] == [
        ("source-1",),
        ("source-1", "source-2"),
    ]
    assert result.payload.unresolved_questions == (
        "When will the next patch ship?",
    )
    assert result.evidence is not None
    assert result.evidence.source_ids == ("source-1", "source-2")
    assert result.evidence.grounded_finding_count == 2
    assert result.evidence.grounding_support_count == 2


@pytest.mark.parametrize(
    ("raw_output", "metadata"),
    (
        (
            '{"findings": invalid}',
            types.GroundingMetadata(
                grounding_chunks=[
                    types.GroundingChunk(
                        web=types.GroundingChunkWeb(
                            uri="https://docs.python.org/3/",
                            title="Python documentation",
                        )
                    )
                ],
                grounding_supports=[
                    types.GroundingSupport(
                        segment=types.Segment(text="Supported claim."),
                        grounding_chunk_indices=[0],
                    )
                ],
            ),
        ),
        (
            {
                "findings": [
                    {
                        "claim": "Supported claim.",
                        "evidence_summary": "Claimed evidence.",
                        "confidence": "high",
                    }
                ]
            },
            None,
        ),
        (
            {
                "findings": [
                    {
                        "claim": "Unsupported claim.",
                        "evidence_summary": "Claimed evidence.",
                        "confidence": "high",
                    }
                ]
            },
            types.GroundingMetadata(
                grounding_chunks=[
                    types.GroundingChunk(
                        web=types.GroundingChunkWeb(
                            uri="https://docs.python.org/3/",
                            title="Python documentation",
                        )
                    )
                ],
                grounding_supports=[
                    types.GroundingSupport(
                        segment=types.Segment(text="Different claim."),
                        grounding_chunk_indices=[0],
                    )
                ],
            ),
        ),
    ),
)
def test_invalid_or_ungrounded_research_output_fails_closed(
    raw_output: object,
    metadata: types.GroundingMetadata | None,
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert import normalize_research_output

    private_response = (
        "Provider prose includes https://untrusted.example/private"
    )

    result = normalize_research_output(
        raw_output=raw_output,
        response_text=private_response,
        metadata=metadata,
    )

    assert result.status is ExpertStatus.INVALID_OUTPUT
    assert result.summary is None
    assert result.limitations == ()
    assert result.payload is None
    assert result.evidence is None
    assert "untrusted.example" not in str(result)


def test_research_output_uses_provider_byte_offsets_when_text_is_absent(
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert import normalize_research_output

    claim = "Python 3.14.7 is stable."
    prefix = "Résumé: "
    response_text = f"{prefix}{claim}"
    start = len(prefix.encode("utf-8"))
    end = len(response_text.encode("utf-8"))
    metadata = types.GroundingMetadata(
        grounding_chunks=[
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://www.python.org/downloads/",
                    title="Python downloads",
                )
            )
        ],
        grounding_supports=[
            types.GroundingSupport(
                segment=types.Segment(start_index=start, end_index=end),
                grounding_chunk_indices=[0],
            )
        ],
    )

    result = normalize_research_output(
        raw_output={
            "findings": [
                {
                    "claim": claim,
                    "evidence_summary": "Python.org supports the claim.",
                    "confidence": "high",
                }
            ]
        },
        response_text=response_text,
        metadata=metadata,
    )

    assert result.status is ExpertStatus.COMPLETED
    assert result.summary == (
        "Research produced 1 grounded finding from 1 public source."
    )
    assert result.payload is not None
    assert result.payload.findings[0].source_ids == ("source-1",)


@pytest.mark.parametrize(
    "status",
    ("rejected_input", "unavailable", "timed_out"),
)
def test_research_failure_normalization_carries_no_provider_content(
    status: str,
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert import normalize_research_failure

    result = normalize_research_failure(ExpertStatus(status))

    assert result.status is ExpertStatus(status)
    assert result.summary is None
    assert result.limitations == ()
    assert result.payload is None
    assert result.evidence is None

    with pytest.raises(ValueError):
        normalize_research_failure(ExpertStatus.COMPLETED)

    with pytest.raises(ValueError) as exc_info:
        normalize_research_failure(status)  # type: ignore[arg-type]
    assert exc_info.value.__cause__ is None


def test_create_research_expert_is_an_isolated_single_turn_search_agent(
) -> None:
    from google.adk.tools.google_search_tool import google_search

    from research_expert import (
        RESEARCH_EXPERT_INSTRUCTION,
        RESEARCH_EXPERT_MODEL_NAME,
        RESEARCH_EXPERT_TIMEOUT_SECONDS,
        ResearchExpertDraft,
        ResearchExpertInput,
        create_research_expert,
    )

    agent = create_research_expert(
        vertex_settings=VertexAISettings(
            project="project-1",
            location="global",
        )
    )

    assert agent.name == "research_expert"
    assert agent.mode == "single_turn"
    assert RESEARCH_EXPERT_TIMEOUT_SECONDS == 45
    assert agent.timeout == RESEARCH_EXPERT_TIMEOUT_SECONDS
    assert agent.input_schema is ResearchExpertInput
    assert agent.output_schema is ResearchExpertDraft
    assert isinstance(agent.model, Gemini)
    assert agent.model.model == RESEARCH_EXPERT_MODEL_NAME
    assert agent.model.client_kwargs == {
        "enterprise": True,
        "project": "project-1",
        "location": "global",
    }
    assert agent.tools == [google_search]
    assert agent.sub_agents == []
    assert agent.disallow_transfer_to_parent is True
    assert agent.disallow_transfer_to_peers is True
    assert agent.include_contents == "none"
    assert agent.instruction == RESEARCH_EXPERT_INSTRUCTION
    assert "untrusted task data" in RESEARCH_EXPERT_INSTRUCTION
    assert "Google Search" in RESEARCH_EXPERT_INSTRUCTION
    assert "Do not ask the user" in RESEARCH_EXPERT_INSTRUCTION


def test_research_event_adapter_uses_real_adk_output_and_metadata() -> None:
    from expert_contracts import ExpertStatus
    from research_expert import normalize_research_event

    claim = "Python 3.14.7 is the current stable release."
    metadata = types.GroundingMetadata(
        grounding_chunks=[
            types.GroundingChunk(
                web=types.GroundingChunkWeb(
                    uri="https://www.python.org/downloads/",
                    title="Python downloads",
                )
            )
        ],
        grounding_supports=[
            types.GroundingSupport(
                segment=types.Segment(text=claim),
                grounding_chunk_indices=[0],
            )
        ],
    )
    event = Event(
        author="research_expert",
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=claim)],
        ),
        output={
            "findings": [
                {
                    "claim": claim,
                    "evidence_summary": "Python.org supports the claim.",
                    "confidence": "high",
                }
            ]
        },
        grounding_metadata=metadata,
    )

    result = normalize_research_event(event)

    assert result.status is ExpertStatus.COMPLETED
    assert result.payload is not None
    assert str(result.payload.sources[0].uri) == (
        "https://www.python.org/downloads/"
    )

    wrong_author = event.model_copy(update={"author": "Agent_Col"})
    rejected = normalize_research_event(wrong_author)
    assert rejected.status is ExpertStatus.INVALID_OUTPUT


def test_research_receipts_map_only_completed_provider_evidence() -> None:
    from expert_contracts import ExpertStatus
    from research_expert import (
        ProviderSource,
        ResearchExpertEvidence,
        ResearchExpertPayload,
        ResearchExpertResult,
        ResearchFinding,
        build_research_receipts,
        normalize_research_failure,
    )

    completed = ResearchExpertResult(
        status="completed",
        summary="Research produced one grounded finding.",
        payload=ResearchExpertPayload(
            findings=(
                ResearchFinding(
                    claim="Supported claim.",
                    evidence_summary="Public evidence supports the claim.",
                    source_ids=("source-1",),
                    confidence="high",
                ),
            ),
            sources=(
                ProviderSource(
                    source_id="source-1",
                    uri="https://docs.python.org/3/",
                    label="Python documentation",
                ),
            ),
        ),
        evidence=ResearchExpertEvidence(
            source_ids=("source-1",),
            grounded_finding_count=1,
            grounding_support_count=1,
        ),
    )

    receipts = build_research_receipts(completed)

    assert [action.model_dump(mode="json") for action in receipts.actions] == [
        {"action_name": "google_search", "status": "completed"}
    ]
    assert [
        citation.model_dump(mode="json")
        for citation in receipts.citations
    ] == [
        {
            "uri": "https://docs.python.org/3/",
            "label": "Python documentation",
        }
    ]

    failed = build_research_receipts(
        normalize_research_failure(ExpertStatus.UNAVAILABLE)
    )
    assert failed.actions == ()
    assert failed.citations == ()
