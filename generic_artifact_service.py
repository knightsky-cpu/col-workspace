"""Read projection service for generic single-file artifacts."""

import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import ValidationError

from database import ArtifactDocumentPage, ArtifactDocumentRecord
from schemas import (
    ARTIFACT_CONTRACT_VERSION,
    ArtifactReference,
    SingleFileArtifact,
    SingleFileArtifactCreateResponse,
    SingleFileArtifactDetailResponse,
    SingleFileArtifactLifecycleResponse,
    SingleFileArtifactListResponse,
    SingleFileArtifactMetadata,
    derive_single_file_artifact_display_label,
)


logger = logging.getLogger(__name__)
GENERIC_ARTIFACT_VERSION_MODEL_NAME = "agent-col-generic-artifact-version"


class ArtifactReadStateError(RuntimeError):
    """Raised when a stored generic artifact violates the read contract."""


@dataclass(frozen=True, slots=True)
class ListGenericArtifactsCommand:
    project_id: str
    limit: int = 20
    before: str | None = None
    lifecycle_status: Literal["active", "archived"] = "active"


@dataclass(frozen=True, slots=True)
class GetGenericArtifactCommand:
    project_id: str
    artifact_id: str


@dataclass(frozen=True, slots=True)
class ArchiveGenericArtifactCommand:
    project_id: str
    artifact_id: str


@dataclass(frozen=True, slots=True)
class RestoreGenericArtifactCommand:
    project_id: str
    artifact_id: str


@dataclass(frozen=True, slots=True)
class UpdateGenericArtifactMetadataCommand:
    project_id: str
    artifact_id: str
    display_label: str | None = None
    filename: str | None = None


@dataclass(frozen=True, slots=True)
class CreateGenericArtifactVersionCommand:
    project_id: str
    artifact_id: str
    session_id: str
    user_id: str
    content: str
    filename: str | None = None
    display_label: str | None = None
    summary: str | None = None
    originating_turn_id: str | None = None


class GenericArtifactDatabase(Protocol):
    async def list_artifact_documents(
        self,
        project_id: str,
        *,
        limit: int,
        before: str | None,
    ) -> ArtifactDocumentPage: ...

    async def get_artifact_document(
        self,
        project_id: str,
        artifact_id: str,
    ) -> ArtifactDocumentRecord: ...

    async def archive_artifact_document(
        self,
        project_id: str,
        artifact_id: str,
    ) -> ArtifactDocumentRecord: ...

    async def restore_artifact_document(
        self,
        project_id: str,
        artifact_id: str,
    ) -> ArtifactDocumentRecord: ...

    async def update_artifact_metadata_document(
        self,
        project_id: str,
        artifact_id: str,
        *,
        display_label: str | None,
        filename: str | None,
    ) -> ArtifactDocumentRecord: ...

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
        parent_artifact_id: str | None = None,
    ) -> str: ...


class GenericArtifactReadService:
    """Project validated Firestore generic artifacts into public models."""

    def __init__(self, *, database: GenericArtifactDatabase) -> None:
        self._database = database

    async def list_artifacts(
        self,
        command: ListGenericArtifactsCommand,
    ) -> SingleFileArtifactListResponse:
        page = await self._database.list_artifact_documents(
            command.project_id,
            limit=command.limit,
            before=command.before,
        )
        artifacts = [
            self._project_metadata(command.project_id, record)
            for record in page.records
            if self._uses_single_file_contract(record)
            and self._lifecycle_status(record) == command.lifecycle_status
        ]
        return SingleFileArtifactListResponse(
            artifacts=artifacts,
            next_before=page.next_before,
        )

    async def get_artifact(
        self,
        command: GetGenericArtifactCommand,
    ) -> SingleFileArtifactDetailResponse:
        record = await self._database.get_artifact_document(
            command.project_id,
            command.artifact_id,
        )
        artifact = self._project_artifact(record)
        return SingleFileArtifactDetailResponse(
            metadata=self._project_metadata(command.project_id, record),
            artifact=artifact,
        )

    async def archive_artifact(
        self,
        command: ArchiveGenericArtifactCommand,
    ) -> SingleFileArtifactLifecycleResponse:
        record = await self._database.archive_artifact_document(
            command.project_id,
            command.artifact_id,
        )
        if not self._is_archived(record):
            raise ArtifactReadStateError(
                "Archived generic artifact state is invalid."
            )
        return SingleFileArtifactLifecycleResponse(
            metadata=self._project_metadata(command.project_id, record)
        )

    async def restore_artifact(
        self,
        command: RestoreGenericArtifactCommand,
    ) -> SingleFileArtifactLifecycleResponse:
        record = await self._database.restore_artifact_document(
            command.project_id,
            command.artifact_id,
        )
        if self._lifecycle_status(record) != "active":
            raise ArtifactReadStateError(
                "Restored generic artifact state is invalid."
            )
        return SingleFileArtifactLifecycleResponse(
            metadata=self._project_metadata(command.project_id, record)
        )

    async def update_artifact_metadata(
        self,
        command: UpdateGenericArtifactMetadataCommand,
    ) -> SingleFileArtifactLifecycleResponse:
        record = await self._database.update_artifact_metadata_document(
            command.project_id,
            command.artifact_id,
            display_label=command.display_label,
            filename=command.filename,
        )
        return SingleFileArtifactLifecycleResponse(
            metadata=self._project_metadata(command.project_id, record)
        )

    async def create_artifact_version(
        self,
        command: CreateGenericArtifactVersionCommand,
    ) -> SingleFileArtifactCreateResponse:
        parent_record = await self._database.get_artifact_document(
            command.project_id,
            command.artifact_id,
        )
        parent_artifact = self._project_artifact(parent_record)
        artifact = SingleFileArtifact.model_validate(
            {
                "artifact_family": parent_artifact.artifact_family,
                "format": parent_artifact.format,
                "filename": command.filename or parent_artifact.filename,
                "content": command.content,
                "summary": command.summary or parent_artifact.summary,
            }
        )
        if command.display_label is not None or artifact.summary is not None:
            display_label = derive_single_file_artifact_display_label(
                display_label=command.display_label,
                summary=artifact.summary,
                filename=artifact.filename,
            )
        else:
            display_label = (
                parent_record.document.get("display_label")
                or artifact.filename
            )
        artifact_id = await self._database.save_single_file_artifact(
            project_id=command.project_id,
            session_id=command.session_id,
            user_id=command.user_id,
            model_name=GENERIC_ARTIFACT_VERSION_MODEL_NAME,
            artifact=artifact.model_dump(mode="json"),
            display_label=display_label,
            originating_turn_id=command.originating_turn_id,
            parent_artifact_id=command.artifact_id,
        )
        return SingleFileArtifactCreateResponse(
            reference=ArtifactReference(
                artifact_type="single_file_artifact",
                project_id=command.project_id,
                artifact_id=artifact_id,
                schema_version="1.0",
                display_label=display_label,
            ),
            artifact=artifact,
        )

    @staticmethod
    def _uses_single_file_contract(record: ArtifactDocumentRecord) -> bool:
        document = record.document
        return (
            isinstance(document, dict)
            and document.get("artifact_contract_version")
            == ARTIFACT_CONTRACT_VERSION
            and document.get("artifact_type") == "single_file_artifact"
            and document.get("schema_version") == "1.0"
        )

    @staticmethod
    def _is_archived(record: ArtifactDocumentRecord) -> bool:
        return GenericArtifactReadService._lifecycle_status(record) == "archived"

    @staticmethod
    def _lifecycle_status(
        record: ArtifactDocumentRecord,
    ) -> Literal["active", "archived"]:
        status = record.document.get("lifecycle_status", "active")
        if status == "archived":
            return "archived"
        return "active"

    @classmethod
    def _project_artifact(
        cls,
        record: ArtifactDocumentRecord,
    ) -> SingleFileArtifact:
        document = record.document
        if not cls._uses_single_file_contract(record):
            raise ArtifactReadStateError(
                "Stored generic artifact is invalid."
            )
        try:
            return SingleFileArtifact.model_validate(
                {
                    "artifact_family": document.get("artifact_family"),
                    "format": document.get("format"),
                    "filename": document.get("filename"),
                    "content": document.get("content"),
                    "summary": document.get("summary"),
                }
            )
        except ValidationError as exc:
            logger.warning(
                "Stored generic artifact content is invalid (%s).",
                exc,
            )
            raise ArtifactReadStateError(
                "Stored generic artifact is invalid."
            ) from exc

    @classmethod
    def _project_metadata(
        cls,
        project_id: str,
        record: ArtifactDocumentRecord,
    ) -> SingleFileArtifactMetadata:
        document = record.document
        artifact = cls._project_artifact(record)
        try:
            return SingleFileArtifactMetadata.model_validate(
                {
                    "reference": ArtifactReference(
                        artifact_type="single_file_artifact",
                        project_id=project_id,
                        artifact_id=record.artifact_id,
                        schema_version=document.get("schema_version"),
                        display_label=document.get("display_label"),
                    ),
                    "created_at": document.get("created_at"),
                    "originating_session_id": document.get(
                        "originating_session_id"
                    ),
                    "originating_turn_id": document.get(
                        "originating_turn_id"
                    ),
                    "parent_artifact_id": document.get(
                        "parent_artifact_id"
                    ),
                    "filename": artifact.filename,
                    "artifact_family": artifact.artifact_family,
                    "format": artifact.format,
                    "byte_size": document.get("byte_size"),
                    "lifecycle_status": document.get(
                        "lifecycle_status",
                        "active",
                    ),
                }
            )
        except ValidationError as exc:
            logger.warning(
                "Stored generic artifact metadata is invalid (%s).",
                exc,
            )
            raise ArtifactReadStateError(
                "Stored generic artifact is invalid."
            ) from exc
