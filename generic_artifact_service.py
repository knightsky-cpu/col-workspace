"""Read projection service for generic single-file artifacts."""

import logging
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from database import ArtifactDocumentPage, ArtifactDocumentRecord
from schemas import (
    ARTIFACT_CONTRACT_VERSION,
    ArtifactReference,
    SingleFileArtifact,
    SingleFileArtifactDetailResponse,
    SingleFileArtifactLifecycleResponse,
    SingleFileArtifactListResponse,
    SingleFileArtifactMetadata,
)


logger = logging.getLogger(__name__)


class ArtifactReadStateError(RuntimeError):
    """Raised when a stored generic artifact violates the read contract."""


@dataclass(frozen=True, slots=True)
class ListGenericArtifactsCommand:
    project_id: str
    limit: int = 20
    before: str | None = None


@dataclass(frozen=True, slots=True)
class GetGenericArtifactCommand:
    project_id: str
    artifact_id: str


@dataclass(frozen=True, slots=True)
class ArchiveGenericArtifactCommand:
    project_id: str
    artifact_id: str


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
            and not self._is_archived(record)
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
        return record.document.get("lifecycle_status") == "archived"

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
