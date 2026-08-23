"""Deterministic validation and persistence boundary for artifact feedback."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from artifact_read_service import GetBlueprintArtifactCommand
from schemas import (
    AgentActionReceipt,
    ArtifactFeedbackDecisionRequest,
    ArtifactFeedbackReference,
    ArtifactFeedbackTarget,
    ArtifactReference,
    BlueprintArtifactDetailResponse,
)


class ArtifactFeedbackTargetNotFoundError(RuntimeError):
    """Raised when a target was not issued for the selected artifact."""


class ArtifactFeedbackSchemaConflictError(RuntimeError):
    """Raised when feedback targets a stale artifact schema."""


class ArtifactFeedbackStateError(RuntimeError):
    """Raised when a trusted feedback boundary returns inconsistent state."""


class ArtifactReader(Protocol):
    async def get_blueprint(
        self,
        command: GetBlueprintArtifactCommand,
    ) -> BlueprintArtifactDetailResponse: ...


class FeedbackRepository(Protocol):
    async def record_blueprint_feedback(
        self,
        **kwargs: object,
    ) -> ArtifactFeedbackReference: ...


@dataclass(frozen=True, slots=True)
class RecordBlueprintFeedbackCommand:
    project_id: str
    session_id: str
    user_id: str
    source_message_id: str
    turn_id: str
    feedback: ArtifactFeedbackDecisionRequest
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class RecordBlueprintFeedbackResult:
    action: AgentActionReceipt
    feedback: ArtifactFeedbackReference


@dataclass(frozen=True, slots=True)
class ResolvedArtifactFeedback:
    feedback_id: str
    artifact: ArtifactReference
    target: ArtifactFeedbackTarget


def derive_feedback_id(turn_id: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{1,118}", turn_id) is None:
        raise ValueError("turn_id must be a valid feedback origin.")
    return f"feedback--{turn_id}"


class ArtifactFeedbackService:
    def __init__(
        self,
        *,
        artifact_reader: ArtifactReader,
        feedback_repository: FeedbackRepository,
    ) -> None:
        self._artifact_reader = artifact_reader
        self._feedback_repository = feedback_repository

    async def record_feedback(
        self,
        command: RecordBlueprintFeedbackCommand,
    ) -> RecordBlueprintFeedbackResult:
        resolved = await self.resolve_feedback_target(command)
        request = command.feedback
        feedback_id = resolved.feedback_id
        target = resolved.target
        expected_reference = ArtifactFeedbackReference(
            feedback_id=feedback_id,
            artifact_id=request.artifact_id,
            target_id=request.target_id,
            target_kind=target.target_kind,
            decision=request.decision,
            schema_version=request.expected_schema_version,
            created_at=command.observed_at,
        )
        stored_reference = (
            await self._feedback_repository.record_blueprint_feedback(
                project_id=command.project_id,
                blueprint_id=request.artifact_id,
                feedback_id=feedback_id,
                target_id=request.target_id,
                target_kind=target.target_kind,
                decision=request.decision,
                feedback_text=request.feedback_text,
                correction_text=request.correction_text,
                expected_schema_version=(
                    request.expected_schema_version
                ),
                session_id=command.session_id,
                user_id=command.user_id,
                source_message_id=command.source_message_id,
                turn_id=command.turn_id,
                observed_at=command.observed_at,
            )
        )
        stable_stored_reference = stored_reference.model_dump(
            exclude={"created_at"}
        )
        stable_expected_reference = expected_reference.model_dump(
            exclude={"created_at"}
        )
        if (
            stable_stored_reference != stable_expected_reference
            or stored_reference.created_at > command.observed_at
        ):
            raise ArtifactFeedbackStateError(
                "Stored artifact feedback receipt is inconsistent."
            )
        return RecordBlueprintFeedbackResult(
            action=AgentActionReceipt(
                action_name="record_blueprint_feedback",
                status="completed",
            ),
            feedback=stored_reference,
        )

    async def resolve_feedback_target(
        self,
        command: RecordBlueprintFeedbackCommand,
    ) -> ResolvedArtifactFeedback:
        """Resolve one feedback locator against canonical artifact detail."""
        self._validate_command(command)
        request = command.feedback
        detail = await self._artifact_reader.get_blueprint(
            GetBlueprintArtifactCommand(
                project_id=command.project_id,
                blueprint_id=request.artifact_id,
            )
        )
        reference = detail.metadata.reference
        if (
            reference.project_id != command.project_id
            or reference.artifact_id != request.artifact_id
        ):
            raise ArtifactFeedbackStateError(
                "Canonical artifact reference is inconsistent."
            )
        if reference.schema_version != request.expected_schema_version:
            raise ArtifactFeedbackSchemaConflictError(
                "Artifact schema conflicts with feedback command."
            )
        targets = tuple(
            target
            for target in detail.feedback_targets
            if target.target_id == request.target_id
        )
        if len(targets) != 1:
            raise ArtifactFeedbackTargetNotFoundError(
                "Artifact feedback target was not found."
            )
        target = targets[0]
        feedback_id = derive_feedback_id(command.turn_id)
        return ResolvedArtifactFeedback(
            feedback_id=feedback_id,
            artifact=reference,
            target=target,
        )

    @staticmethod
    def _validate_command(command: RecordBlueprintFeedbackCommand) -> None:
        if not isinstance(command, RecordBlueprintFeedbackCommand):
            raise ValueError("feedback command is invalid.")
        for value, field_name in (
            (command.project_id, "project_id"),
            (command.session_id, "session_id"),
            (command.user_id, "user_id"),
            (command.source_message_id, "source_message_id"),
        ):
            if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is None:
                raise ValueError(f"{field_name} must be a valid identifier.")
        derive_feedback_id(command.turn_id)
        if not isinstance(command.feedback, ArtifactFeedbackDecisionRequest):
            raise ValueError("feedback request is invalid.")
        if command.feedback.expected_schema_version != "2.0":
            raise ArtifactFeedbackSchemaConflictError(
                "Artifact schema conflicts with feedback command."
            )
        if (
            command.observed_at.tzinfo is None
            or command.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be timezone aware.")
