import pytest
from google.adk.events import Event
from google.genai import types


def research_call_event() -> Event:
    return Event(
        author="Agent_Col",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id="research-call-1",
                        name="research_expert",
                        args={
                            "question": "What is the current Python release?",
                            "objective": "Establish the current release.",
                        },
                    )
                )
            ],
        ),
    )


def grounded_research_event() -> Event:
    claim = "Python 3.14.7 is the current stable release."
    return Event(
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
        grounding_metadata=types.GroundingMetadata(
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
        ),
    )


@pytest.mark.asyncio
async def test_research_turn_tracker_claims_and_maps_grounded_receipts(
) -> None:
    from research_expert_runtime import ResearchExpertTurnTracker

    tracker = ResearchExpertTurnTracker()

    await tracker.observe(research_call_event())
    await tracker.observe(grounded_research_event())
    receipts = tracker.finalize()

    assert [action.model_dump(mode="json") for action in receipts.actions] == [
        {"action_name": "google_search", "status": "completed"}
    ]


@pytest.mark.asyncio
async def test_research_tracker_accepts_live_event_without_node_output(
) -> None:
    from research_expert_runtime import ResearchExpertTurnTracker

    tracker = ResearchExpertTurnTracker()
    await tracker.observe(research_call_event())
    live_event = grounded_research_event().model_copy(
        update={"output": None}
    )

    await tracker.observe(live_event)
    receipts = tracker.finalize()

    assert [action.action_name for action in receipts.actions] == [
        "google_search"
    ]
    assert [str(citation.uri) for citation in receipts.citations] == [
        "https://www.python.org/downloads/"
    ]
    assert [
        citation.model_dump(mode="json") for citation in receipts.citations
    ] == [
        {
            "uri": "https://www.python.org/downloads/",
            "label": "Python downloads",
        }
    ]


@pytest.mark.asyncio
async def test_research_turn_tracker_rejects_unclaimed_expert_output() -> None:
    from expert_contracts import ExpertStatus
    from research_expert_runtime import (
        ResearchExpertRuntimeError,
        ResearchExpertTurnTracker,
    )

    tracker = ResearchExpertTurnTracker()

    with pytest.raises(ResearchExpertRuntimeError) as exc_info:
        await tracker.observe(grounded_research_event())

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT
    assert str(exc_info.value) == "Research Expert execution failed."
    assert exc_info.value.__cause__ is None


@pytest.mark.asyncio
async def test_research_turn_tracker_rejects_ungrounded_output() -> None:
    from expert_contracts import ExpertStatus
    from research_expert_runtime import (
        ResearchExpertRuntimeError,
        ResearchExpertTurnTracker,
    )

    tracker = ResearchExpertTurnTracker()
    await tracker.observe(research_call_event())
    ungrounded = grounded_research_event().model_copy(
        update={"grounding_metadata": None}
    )

    with pytest.raises(ResearchExpertRuntimeError) as exc_info:
        await tracker.observe(ungrounded)

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT
    assert tracker.finalize().actions == ()
    assert tracker.finalize().citations == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    (
        ("ValidationError", "rejected_input"),
        ("NodeTimeoutError", "timed_out"),
        ("ServerError", "unavailable"),
    ),
)
async def test_research_turn_tracker_contains_child_failure_events(
    error_code: str,
    expected_status: str,
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert_runtime import (
        ResearchExpertRuntimeError,
        ResearchExpertTurnTracker,
    )

    tracker = ResearchExpertTurnTracker()
    await tracker.observe(research_call_event())
    failure = Event(
        author="research_expert",
        error_code=error_code,
        error_message="provider echoed private-user-input",
    )

    with pytest.raises(ResearchExpertRuntimeError) as exc_info:
        await tracker.observe(failure)

    assert exc_info.value.status is ExpertStatus(expected_status)
    assert str(exc_info.value) == "Research Expert execution failed."
    assert "private-user-input" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


@pytest.mark.asyncio
async def test_research_turn_tracker_rejects_claim_without_result() -> None:
    from expert_contracts import ExpertStatus
    from research_expert_runtime import (
        ResearchExpertRuntimeError,
        ResearchExpertTurnTracker,
    )

    tracker = ResearchExpertTurnTracker()
    await tracker.observe(research_call_event())

    with pytest.raises(ResearchExpertRuntimeError) as exc_info:
        tracker.finalize()

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT


@pytest.mark.asyncio
async def test_research_turn_tracker_denies_nonroot_delegation() -> None:
    from expert_delegation import (
        ExpertDelegationDeniedError,
        ExpertDelegationDenialReason,
    )
    from research_expert_runtime import ResearchExpertTurnTracker

    tracker = ResearchExpertTurnTracker()
    nested_call = research_call_event().model_copy(
        update={"author": "research_expert"}
    )

    with pytest.raises(ExpertDelegationDeniedError) as exc_info:
        await tracker.observe(nested_call)

    assert exc_info.value.reason is ExpertDelegationDenialReason.INVALID_DEPTH
