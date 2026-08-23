from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


NOW = datetime(2026, 8, 23, 19, 0, tzinfo=UTC)


def test_feedback_list_projects_bounded_lifecycle_and_provenance() -> None:
    import schemas

    response_type = getattr(
        schemas,
        "BlueprintArtifactFeedbackListResponse",
        None,
    )
    assert response_type is not None

    response = response_type.model_validate(
        {
            "artifact_id": "blueprint-1",
            "events": [
                {
                    "reference": {
                        "feedback_id": "feedback--new-event",
                        "artifact_id": "blueprint-1",
                        "target_id": (
                            "target--0123456789abcdef01234567"
                        ),
                        "target_kind": "whole_blueprint",
                        "decision": "rejected",
                        "schema_version": "2.0",
                        "created_at": NOW,
                    },
                    "feedback_text": "I reversed my earlier acceptance.",
                    "correction_text": None,
                    "originating_session_id": "session-2",
                    "source_message_id": "message-2",
                    "originating_turn_id": "turn-2",
                    "status": "active",
                    "supersedes_feedback_id": "feedback--prior-event",
                    "superseded_by_feedback_id": None,
                },
                {
                    "reference": {
                        "feedback_id": "feedback--prior-event",
                        "artifact_id": "blueprint-1",
                        "target_id": (
                            "target--0123456789abcdef01234567"
                        ),
                        "target_kind": "whole_blueprint",
                        "decision": "accepted",
                        "schema_version": "2.0",
                        "created_at": NOW,
                    },
                    "feedback_text": "I accepted this initially.",
                    "correction_text": None,
                    "originating_session_id": "session-1",
                    "source_message_id": "message-1",
                    "originating_turn_id": "turn-1",
                    "status": "superseded",
                    "supersedes_feedback_id": None,
                    "superseded_by_feedback_id": "feedback--new-event",
                },
            ],
            "next_before": "feedback--prior-event",
        }
    )

    assert response.feedback_contract_version == "1.0"
    assert response.artifact_id == "blueprint-1"
    assert response.events[0].status == "active"
    assert response.events[1].status == "superseded"
    assert response.events[1].superseded_by_feedback_id == (
        "feedback--new-event"
    )


def test_feedback_event_rejects_inconsistent_derived_lifecycle() -> None:
    from schemas import ArtifactFeedbackEvent

    base_event = {
        "reference": {
            "feedback_id": "feedback--event-1",
            "artifact_id": "blueprint-1",
            "target_id": "target--0123456789abcdef01234567",
            "target_kind": "whole_blueprint",
            "decision": "accepted",
            "schema_version": "2.0",
            "created_at": NOW,
        },
        "feedback_text": "This boundary is correct.",
        "originating_session_id": "session-1",
        "source_message_id": "message-1",
        "originating_turn_id": "turn-1",
    }

    with pytest.raises(ValidationError):
        ArtifactFeedbackEvent.model_validate(
            {
                **base_event,
                "status": "active",
                "superseded_by_feedback_id": "feedback--event-2",
            }
        )
    with pytest.raises(ValidationError):
        ArtifactFeedbackEvent.model_validate(
            {
                **base_event,
                "status": "superseded",
                "superseded_by_feedback_id": None,
            }
        )
    with pytest.raises(ValidationError):
        ArtifactFeedbackEvent.model_validate(
            {
                **base_event,
                "status": "superseded",
                "superseded_by_feedback_id": "feedback--event-1",
            }
        )
