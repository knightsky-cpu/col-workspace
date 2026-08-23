from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from artifact_read_service import GetBlueprintArtifactCommand
from database import (
    BlueprintFeedbackDocumentPage,
    BlueprintFeedbackDocumentRecord,
)
from schemas import (
    ArtifactFeedbackCounts,
    ArtifactFeedbackDecisionRequest,
    ArtifactFeedbackReference,
    ArtifactFeedbackTarget,
    ArtifactReference,
    BlueprintArtifactDetailResponse,
    BlueprintArtifactMetadata,
    SynthesisBlueprint,
)


NOW = datetime(2026, 8, 23, 19, 0, tzinfo=UTC)
TURN_ID = "c" * 64
TARGET_ID = "target--0123456789abcdef01234567"


def blueprint() -> SynthesisBlueprint:
    return SynthesisBlueprint.model_validate(
        {
            "synthesized_conceptual_model": {
                "project_name": "Collaborative Study Partner",
                "core_value_proposition": "Creates verifiable study plans.",
                "in_scope": ["Collaborative planning"],
            },
            "personalization_trace": {},
            "architectural_decisions": [
                {
                    "component_name": "Approval boundary",
                    "proposed_solution": "Explicit structured decisions",
                    "rationale": "Keeps changes user controlled.",
                    "alternatives": [
                        {
                            "option_name": "Inferred approval",
                            "tradeoff": "Lower friction.",
                            "reason_not_selected": "Cannot prove consent.",
                        }
                    ],
                }
            ],
            "socratic_clarifying_questions": [
                {
                    "question_text": "Which goal comes first?",
                    "why_this_matters": "It determines the first milestone.",
                    "suggested_options": [
                        {"label": "Theory", "impact": "Start conceptually."},
                        {"label": "Practice", "impact": "Start hands-on."},
                    ],
                }
            ],
            "step_by_step_execution_roadmap": [
                {
                    "phase_name": "Foundation",
                    "objective": "Define the learning goal.",
                    "expected_deliverable": "An approved milestone.",
                    "micro_tasks": [
                        {
                            "task_description": "Choose the first goal.",
                            "complexity_level": "Low",
                            "verification_steps": ["Record approval."],
                        }
                    ],
                }
            ],
        }
    )


def detail() -> BlueprintArtifactDetailResponse:
    artifact = ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id="project-1",
        artifact_id="blueprint-1",
        schema_version="2.0",
        display_label="Collaborative Study Partner",
    )
    return BlueprintArtifactDetailResponse(
        metadata=BlueprintArtifactMetadata(
            reference=artifact,
            created_at=NOW,
            originating_session_id="origin-session",
            originating_turn_id="b" * 64,
            feedback_counts=ArtifactFeedbackCounts(),
        ),
        blueprint=blueprint(),
        feedback_targets=[
            ArtifactFeedbackTarget(
                target_id=TARGET_ID,
                target_kind="whole_blueprint",
                display_label="Collaborative Study Partner",
            )
        ],
    )


def request(
    *,
    target_id: str = TARGET_ID,
    expected_schema_version: str = "2.0",
    supersedes_feedback_id: str | None = None,
) -> ArtifactFeedbackDecisionRequest:
    return ArtifactFeedbackDecisionRequest.model_validate(
        {
            "artifact_id": "blueprint-1",
            "target_id": target_id,
            "decision": "accepted",
            "feedback_text": "The approval boundary is correct.",
            "expected_schema_version": expected_schema_version,
            "supersedes_feedback_id": supersedes_feedback_id,
        }
    )


@dataclass
class FakeReader:
    result: BlueprintArtifactDetailResponse

    def __post_init__(self) -> None:
        self.commands: list[GetBlueprintArtifactCommand] = []

    async def get_blueprint(
        self,
        command: GetBlueprintArtifactCommand,
    ) -> BlueprintArtifactDetailResponse:
        self.commands.append(command)
        return self.result


class FakeRepository:
    def __init__(
        self,
        result: ArtifactFeedbackReference,
        *,
        list_result: BlueprintFeedbackDocumentPage | None = None,
    ) -> None:
        self.result = result
        self.list_result = list_result
        self.calls: list[dict[str, object]] = []
        self.list_calls: list[tuple[str, str, int, str | None]] = []

    async def record_blueprint_feedback(self, **kwargs):
        self.calls.append(kwargs)
        return self.result

    async def list_blueprint_feedback_documents(
        self,
        project_id: str,
        blueprint_id: str,
        *,
        limit: int,
        before: str | None,
    ) -> BlueprintFeedbackDocumentPage:
        self.list_calls.append((project_id, blueprint_id, limit, before))
        if self.list_result is None:
            raise AssertionError("Feedback list result is unavailable.")
        return self.list_result


def reference() -> ArtifactFeedbackReference:
    return ArtifactFeedbackReference(
        feedback_id=f"feedback--{TURN_ID}",
        artifact_id="blueprint-1",
        target_id=TARGET_ID,
        target_kind="whole_blueprint",
        decision="accepted",
        schema_version="2.0",
        created_at=NOW,
    )


def command(feedback_request: ArtifactFeedbackDecisionRequest):
    from artifact_feedback_service import RecordBlueprintFeedbackCommand

    return RecordBlueprintFeedbackCommand(
        project_id="project-1",
        session_id="feedback-session",
        user_id="user-1",
        source_message_id="source-message-1",
        turn_id=TURN_ID,
        feedback=feedback_request,
        observed_at=NOW,
    )


@pytest.mark.asyncio
async def test_feedback_service_resolves_target_and_records_bounded_event(
) -> None:
    from artifact_feedback_service import ArtifactFeedbackService

    reader = FakeReader(detail())
    repository = FakeRepository(reference())
    service = ArtifactFeedbackService(
        artifact_reader=reader,
        feedback_repository=repository,
    )

    result = await service.record_feedback(command(request()))

    assert reader.commands == [
        GetBlueprintArtifactCommand(
            project_id="project-1",
            blueprint_id="blueprint-1",
        )
    ]
    assert repository.calls == [
        {
            "project_id": "project-1",
            "blueprint_id": "blueprint-1",
            "feedback_id": f"feedback--{TURN_ID}",
            "target_id": TARGET_ID,
            "target_kind": "whole_blueprint",
            "decision": "accepted",
            "feedback_text": "The approval boundary is correct.",
            "correction_text": None,
            "supersedes_feedback_id": None,
            "expected_schema_version": "2.0",
            "session_id": "feedback-session",
            "user_id": "user-1",
            "source_message_id": "source-message-1",
            "turn_id": TURN_ID,
            "observed_at": NOW,
        }
    ]
    assert result.action.model_dump(mode="json") == {
        "action_name": "record_blueprint_feedback",
        "status": "completed",
    }
    assert result.feedback == reference()


@pytest.mark.asyncio
async def test_feedback_service_forwards_explicit_supersession_authority(
) -> None:
    from artifact_feedback_service import ArtifactFeedbackService

    prior_feedback_id = "feedback--prior-event"
    repository = FakeRepository(reference())
    service = ArtifactFeedbackService(
        artifact_reader=FakeReader(detail()),
        feedback_repository=repository,
    )

    await service.record_feedback(
        command(request(supersedes_feedback_id=prior_feedback_id))
    )

    assert repository.calls[0]["supersedes_feedback_id"] == prior_feedback_id


@pytest.mark.asyncio
async def test_feedback_service_rejects_unknown_server_target_before_write(
) -> None:
    from artifact_feedback_service import (
        ArtifactFeedbackService,
        ArtifactFeedbackTargetNotFoundError,
    )

    repository = FakeRepository(reference())
    service = ArtifactFeedbackService(
        artifact_reader=FakeReader(detail()),
        feedback_repository=repository,
    )

    with pytest.raises(ArtifactFeedbackTargetNotFoundError):
        await service.record_feedback(
            command(request(target_id="target--ffffffffffffffffffffffff"))
        )

    assert repository.calls == []


@pytest.mark.asyncio
async def test_feedback_service_rejects_stale_schema_before_write() -> None:
    from artifact_feedback_service import (
        ArtifactFeedbackSchemaConflictError,
        ArtifactFeedbackService,
    )

    stale_request = request().model_copy(
        update={"expected_schema_version": "1.0"}
    )
    repository = FakeRepository(reference())
    service = ArtifactFeedbackService(
        artifact_reader=FakeReader(detail()),
        feedback_repository=repository,
    )

    with pytest.raises(ArtifactFeedbackSchemaConflictError):
        await service.record_feedback(command(stale_request))

    assert repository.calls == []


@pytest.mark.asyncio
async def test_feedback_service_rejects_mismatched_repository_receipt() -> None:
    from artifact_feedback_service import (
        ArtifactFeedbackService,
        ArtifactFeedbackStateError,
    )

    mismatched = reference().model_copy(
        update={"feedback_id": "feedback--different"}
    )
    service = ArtifactFeedbackService(
        artifact_reader=FakeReader(detail()),
        feedback_repository=FakeRepository(mismatched),
    )

    with pytest.raises(ArtifactFeedbackStateError):
        await service.record_feedback(command(request()))


@pytest.mark.asyncio
async def test_feedback_service_accepts_original_timestamp_on_retry() -> None:
    from artifact_feedback_service import ArtifactFeedbackService

    original = reference().model_copy(
        update={"created_at": NOW - timedelta(minutes=5)}
    )
    service = ArtifactFeedbackService(
        artifact_reader=FakeReader(detail()),
        feedback_repository=FakeRepository(original),
    )

    result = await service.record_feedback(command(request()))

    assert result.feedback == original


@pytest.mark.asyncio
async def test_feedback_service_rejects_future_repository_timestamp() -> None:
    from artifact_feedback_service import (
        ArtifactFeedbackService,
        ArtifactFeedbackStateError,
    )

    future = reference().model_copy(
        update={"created_at": NOW + timedelta(minutes=5)}
    )
    service = ArtifactFeedbackService(
        artifact_reader=FakeReader(detail()),
        feedback_repository=FakeRepository(future),
    )

    with pytest.raises(ArtifactFeedbackStateError):
        await service.record_feedback(command(request()))


@pytest.mark.asyncio
async def test_feedback_service_resolves_server_issued_target_without_write(
) -> None:
    from artifact_feedback_service import ArtifactFeedbackService

    reader = FakeReader(detail())
    repository = FakeRepository(reference())
    service = ArtifactFeedbackService(
        artifact_reader=reader,
        feedback_repository=repository,
    )

    resolved = await service.resolve_feedback_target(command(request()))

    assert resolved.feedback_id == f"feedback--{TURN_ID}"
    assert resolved.artifact == detail().metadata.reference
    assert resolved.target == detail().feedback_targets[0]
    assert repository.calls == []


@pytest.mark.asyncio
async def test_feedback_service_projects_immutable_events_and_derived_status(
) -> None:
    import artifact_feedback_service

    command_type = getattr(
        artifact_feedback_service,
        "ListArtifactFeedbackCommand",
        None,
    )
    assert command_type is not None
    ArtifactFeedbackService = artifact_feedback_service.ArtifactFeedbackService

    new_feedback_id = "feedback--new-event"
    prior_feedback_id = "feedback--prior-event"
    page = BlueprintFeedbackDocumentPage(
        records=(
            BlueprintFeedbackDocumentRecord(
                feedback_id=new_feedback_id,
                document={
                    "feedback_contract_version": "1.0",
                    "feedback_id": new_feedback_id,
                    "artifact_id": "blueprint-1",
                    "target_id": TARGET_ID,
                    "target_kind": "whole_blueprint",
                    "decision": "rejected",
                    "feedback_text": "I reversed the prior acceptance.",
                    "correction_text": None,
                    "originating_session_id": "session-2",
                    "source_message_id": "message-2",
                    "originating_turn_id": "turn-2",
                    "user_id": "user-1",
                    "schema_version": "2.0",
                    "created_at": NOW,
                    "status": "active",
                    "supersedes_feedback_id": prior_feedback_id,
                },
                superseded_by_feedback_id=None,
            ),
            BlueprintFeedbackDocumentRecord(
                feedback_id=prior_feedback_id,
                document={
                    "feedback_contract_version": "1.0",
                    "feedback_id": prior_feedback_id,
                    "artifact_id": "blueprint-1",
                    "target_id": TARGET_ID,
                    "target_kind": "whole_blueprint",
                    "decision": "accepted",
                    "feedback_text": "I accepted this initially.",
                    "correction_text": None,
                    "originating_session_id": "session-1",
                    "source_message_id": "message-1",
                    "originating_turn_id": "turn-1",
                    "user_id": "user-1",
                    "schema_version": "2.0",
                    "created_at": NOW - timedelta(minutes=5),
                    "status": "active",
                    "supersedes_feedback_id": None,
                },
                superseded_by_feedback_id=new_feedback_id,
            ),
        ),
        next_before=prior_feedback_id,
    )
    repository = FakeRepository(reference(), list_result=page)
    service = ArtifactFeedbackService(
        artifact_reader=FakeReader(detail()),
        feedback_repository=repository,
    )
    assert hasattr(service, "list_feedback")

    result = await service.list_feedback(
        command_type(
            project_id="project-1",
            artifact_id="blueprint-1",
            limit=20,
            before=None,
        )
    )

    assert repository.list_calls == [
        ("project-1", "blueprint-1", 20, None)
    ]
    assert result.artifact_id == "blueprint-1"
    assert result.events[0].status == "active"
    assert result.events[0].supersedes_feedback_id == prior_feedback_id
    assert result.events[1].status == "superseded"
    assert result.events[1].superseded_by_feedback_id == new_feedback_id
    assert result.next_before == prior_feedback_id
