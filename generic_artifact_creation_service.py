"""Creation service for validated generic single-file artifacts."""

from dataclasses import dataclass
from typing import Protocol

from schemas import ArtifactReference, SingleFileArtifact


GENERIC_ARTIFACT_MODEL_NAME = "agent-col-generic-artifact"


@dataclass(frozen=True, slots=True)
class GenericArtifactCreationCommand:
    project_id: str
    session_id: str
    user_id: str
    artifact: dict[str, object]
    display_label: str | None = None
    originating_turn_id: str | None = None


@dataclass(frozen=True, slots=True)
class GenericArtifactCreationResult:
    reference: ArtifactReference
    artifact: SingleFileArtifact


class GenericArtifactWriter(Protocol):
    async def save_single_file_artifact(
        self,
        *,
        project_id: str,
        session_id: str,
        user_id: str,
        model_name: str,
        artifact: dict[str, object],
        display_label: str,
        originating_turn_id: str | None = None,
    ) -> str: ...


class GenericArtifactCreationService:
    """Validate and persist one project-owned single-file artifact."""

    def __init__(self, *, artifact_writer: GenericArtifactWriter) -> None:
        self._artifact_writer = artifact_writer

    async def create_artifact(
        self,
        command: GenericArtifactCreationCommand,
    ) -> GenericArtifactCreationResult:
        artifact = SingleFileArtifact.model_validate(command.artifact)
        display_label = (
            command.display_label
            or artifact.summary
            or artifact.filename
        )
        artifact_document = artifact.model_dump(mode="json")
        artifact_id = await self._artifact_writer.save_single_file_artifact(
            project_id=command.project_id,
            session_id=command.session_id,
            user_id=command.user_id,
            model_name=GENERIC_ARTIFACT_MODEL_NAME,
            artifact=artifact_document,
            display_label=display_label,
            originating_turn_id=command.originating_turn_id,
        )
        return GenericArtifactCreationResult(
            reference=ArtifactReference(
                artifact_type="single_file_artifact",
                project_id=command.project_id,
                artifact_id=artifact_id,
                schema_version="1.0",
                display_label=display_label,
            ),
            artifact=artifact,
        )
