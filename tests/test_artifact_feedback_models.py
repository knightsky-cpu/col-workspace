from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


NOW = datetime(2026, 8, 23, 18, 0, tzinfo=UTC)


def test_feedback_request_accepts_bounded_accepted_decision() -> None:
    from schemas import ArtifactFeedbackDecisionRequest

    request = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="accepted",
        feedback_text="This approval boundary is correct.",
        expected_schema_version="2.0",
    )

    assert request.decision == "accepted"
    assert request.correction_text is None


def test_feedback_request_requires_correction_only_for_edited_decision() -> None:
    from schemas import ArtifactFeedbackDecisionRequest

    edited = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="edited",
        feedback_text="The milestone needs a measurable outcome.",
        correction_text="Require a passing verification command.",
        expected_schema_version="2.0",
    )

    assert edited.correction_text == (
        "Require a passing verification command."
    )
    with pytest.raises(ValidationError):
        ArtifactFeedbackDecisionRequest(
            artifact_id="blueprint-1",
            target_id="target--0123456789abcdef01234567",
            decision="edited",
            feedback_text="The milestone needs a measurable outcome.",
            expected_schema_version="2.0",
        )
    with pytest.raises(ValidationError):
        ArtifactFeedbackDecisionRequest(
            artifact_id="blueprint-1",
            target_id="target--0123456789abcdef01234567",
            decision="rejected",
            feedback_text="This decision is unsuitable.",
            correction_text="Use a different implementation.",
            expected_schema_version="2.0",
        )


def test_feedback_request_accepts_one_prior_feedback_to_supersede() -> None:
    from schemas import ArtifactFeedbackDecisionRequest

    request = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="rejected",
        feedback_text="I am reversing my earlier acceptance.",
        expected_schema_version="2.0",
        supersedes_feedback_id=(
            "feedback--0123456789abcdef0123456789abcdef"
        ),
    )

    assert request.supersedes_feedback_id == (
        "feedback--0123456789abcdef0123456789abcdef"
    )


@pytest.mark.parametrize(
    "unsafe_text",
    ("unsafe\x00text", "unsafe\x07text", "unsafe\x1ftext"),
)
def test_feedback_request_rejects_control_characters(
    unsafe_text: str,
) -> None:
    from schemas import ArtifactFeedbackDecisionRequest

    with pytest.raises(ValidationError):
        ArtifactFeedbackDecisionRequest(
            artifact_id="blueprint-1",
            target_id="target--0123456789abcdef01234567",
            decision="accepted",
            feedback_text=unsafe_text,
            expected_schema_version="2.0",
        )


def test_feedback_reference_exposes_only_bounded_provenance() -> None:
    from schemas import ArtifactFeedbackReference

    reference = ArtifactFeedbackReference(
        feedback_id="feedback--0123456789abcdef01234567",
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        target_kind="whole_blueprint",
        decision="accepted",
        schema_version="2.0",
        created_at=NOW,
    )

    assert reference.model_dump(mode="json") == {
        "feedback_id": "feedback--0123456789abcdef01234567",
        "artifact_id": "blueprint-1",
        "target_id": "target--0123456789abcdef01234567",
        "target_kind": "whole_blueprint",
        "decision": "accepted",
        "schema_version": "2.0",
        "created_at": "2026-08-23T18:00:00Z",
    }


def test_chat_request_accepts_one_structured_artifact_feedback_decision(
) -> None:
    from schemas import ChatRequest

    request = ChatRequest.model_validate(
        {
            "project_id": "agent-col",
            "session_id": "feedback-session",
            "user_id": "user-1",
            "message": "I accept this blueprint boundary.",
            "artifact_feedback_decision": {
                "artifact_id": "blueprint-1",
                "target_id": "target--0123456789abcdef01234567",
                "decision": "accepted",
                "feedback_text": "This approval boundary is correct.",
                "expected_schema_version": "2.0",
            },
        }
    )

    assert request.artifact_feedback_decision is not None
    assert request.artifact_feedback_decision.decision == "accepted"


def test_chat_request_rejects_memory_and_artifact_decisions_together() -> None:
    from schemas import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "project_id": "agent-col",
                "session_id": "feedback-session",
                "user_id": "user-1",
                "message": "Apply both structured decisions.",
                "memory_decision": {
                    "proposal_id": "response_length--proposal-1",
                    "decision": "approve",
                },
                "artifact_feedback_decision": {
                    "artifact_id": "blueprint-1",
                    "target_id": "target--0123456789abcdef01234567",
                    "decision": "accepted",
                    "feedback_text": "This boundary is correct.",
                    "expected_schema_version": "2.0",
                },
            }
        )


def test_chat_response_carries_bounded_feedback_reference() -> None:
    from schemas import ArtifactFeedbackReference, ChatResponse

    reference = ArtifactFeedbackReference(
        feedback_id="feedback--0123456789abcdef01234567",
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        target_kind="whole_blueprint",
        decision="accepted",
        schema_version="2.0",
        created_at=NOW,
    )

    response = ChatResponse(
        response="Feedback recorded.",
        artifact_feedback=[reference],
    )

    assert response.artifact_feedback == [reference]
