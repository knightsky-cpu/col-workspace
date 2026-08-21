import pytest
from google.genai import types

from expert_contracts import ExpertStatus
from tests.test_source_expert_tool import completed_source_result


class FunctionResponseEvent:
    def __init__(self, response: object, *, name: str = "analyze_source"):
        self._response = types.FunctionResponse(
            name=name,
            response=response,
        )

    def get_function_responses(self) -> list[types.FunctionResponse]:
        return [self._response]


def completed_response() -> dict[str, object]:
    return {
        "status": "completed",
        "result": completed_source_result().model_dump(mode="json"),
    }


def test_source_tracker_maps_only_validated_completed_response() -> None:
    from source_expert_runtime import SourceExpertTurnTracker

    tracker = SourceExpertTurnTracker()

    tracker.observe(FunctionResponseEvent(completed_response()))
    receipts = tracker.finalize()

    assert [action.model_dump(mode="json") for action in receipts.actions] == [
        {"action_name": "url_context", "status": "completed"}
    ]
    assert [
        citation.model_dump(mode="json") for citation in receipts.citations
    ] == [
        {
            "uri": "https://example.com/",
            "label": "Example Domain",
        }
    ]


@pytest.mark.parametrize(
    "status",
    (
        ExpertStatus.REJECTED_INPUT,
        ExpertStatus.UNAVAILABLE,
        ExpertStatus.TIMED_OUT,
        ExpertStatus.INVALID_OUTPUT,
    ),
)
def test_source_tracker_emits_no_receipt_for_safe_failure(
    status: ExpertStatus,
) -> None:
    from source_expert_runtime import SourceExpertTurnTracker

    tracker = SourceExpertTurnTracker()

    tracker.observe(
        FunctionResponseEvent(
            {
                "status": status.value,
                "message": "Source analysis could not be completed.",
            }
        )
    )

    assert tracker.finalize().actions == ()
    assert tracker.finalize().citations == ()


@pytest.mark.parametrize(
    "response",
    (
        {"status": "completed", "result": {}},
        {
            "status": "unavailable",
            "message": "Source analysis could not be completed.",
            "private_detail": "must-not-survive",
        },
    ),
)
def test_source_tracker_rejects_malformed_response(response: object) -> None:
    from source_expert_runtime import (
        SourceExpertRuntimeError,
        SourceExpertTurnTracker,
    )

    tracker = SourceExpertTurnTracker()

    with pytest.raises(SourceExpertRuntimeError) as exc_info:
        tracker.observe(FunctionResponseEvent(response))

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT
    assert str(exc_info.value) == "Source Expert execution failed."
    assert "private" not in str(exc_info.value).lower()


def test_source_tracker_rejects_repeated_source_responses() -> None:
    from source_expert_runtime import (
        SourceExpertRuntimeError,
        SourceExpertTurnTracker,
    )

    tracker = SourceExpertTurnTracker()
    tracker.observe(FunctionResponseEvent(completed_response()))

    with pytest.raises(SourceExpertRuntimeError) as exc_info:
        tracker.observe(FunctionResponseEvent(completed_response()))

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT


def test_source_tracker_ignores_unrelated_function_response() -> None:
    from source_expert_runtime import SourceExpertTurnTracker

    tracker = SourceExpertTurnTracker()
    tracker.observe(
        FunctionResponseEvent(
            {"private_payload": "ignored"},
            name="unrelated_tool",
        )
    )

    assert tracker.finalize().actions == ()
