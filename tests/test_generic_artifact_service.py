from datetime import UTC, datetime

import pytest


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


class FakeArtifactDatabase:
    def __init__(self, records: tuple[object, ...]) -> None:
        self.records = records
        self.archive_calls: list[tuple[str, str]] = []

    async def list_artifact_documents(
        self,
        project_id: str,
        *,
        limit: int,
        before: str | None,
    ) -> object:
        from database import ArtifactDocumentPage

        self.project_id = project_id
        self.limit = limit
        self.before = before
        return ArtifactDocumentPage(
            records=self.records,
            next_before="artifact--next",
        )

    async def get_artifact_document(
        self,
        project_id: str,
        artifact_id: str,
    ) -> object:
        self.project_id = project_id
        self.artifact_id = artifact_id
        return self.records[0]

    async def archive_artifact_document(
        self,
        project_id: str,
        artifact_id: str,
    ) -> object:
        self.archive_calls.append((project_id, artifact_id))
        return self.records[0]


def stored_single_file_document() -> dict[str, object]:
    return {
        "artifact_contract_version": "1.0",
        "artifact_type": "single_file_artifact",
        "created_at": NOW,
        "originating_session_id": "session-1",
        "originating_turn_id": "turn-1",
        "user_id": "user-1",
        "model_name": "gemini-3.6-flash",
        "schema_version": "1.0",
        "display_label": "Password Generator",
        "filename": "password_generator.py",
        "artifact_family": "code",
        "format": "python",
        "byte_size": 43,
        "content": "import secrets\nprint(secrets.token_hex(8))\n",
        "summary": "Secure password generator.",
    }


@pytest.mark.asyncio
async def test_generic_artifact_service_lists_single_file_metadata() -> None:
    from database import ArtifactDocumentRecord
    from generic_artifact_service import (
        GenericArtifactReadService,
        ListGenericArtifactsCommand,
    )

    database = FakeArtifactDatabase(
        (
            ArtifactDocumentRecord(
                artifact_id="artifact--abc",
                document=stored_single_file_document(),
            ),
        )
    )

    listing = await GenericArtifactReadService(
        database=database
    ).list_artifacts(
        ListGenericArtifactsCommand(project_id="project-1", limit=10)
    )

    assert listing.next_before == "artifact--next"
    assert listing.artifacts[0].reference.artifact_type == (
        "single_file_artifact"
    )
    assert listing.artifacts[0].reference.display_label == (
        "Password Generator"
    )
    assert listing.artifacts[0].filename == "password_generator.py"
    assert listing.artifacts[0].format == "python"
    assert listing.artifacts[0].lifecycle_status == "active"


@pytest.mark.asyncio
async def test_generic_artifact_service_omits_archived_single_file_metadata(
) -> None:
    from database import ArtifactDocumentRecord
    from generic_artifact_service import (
        GenericArtifactReadService,
        ListGenericArtifactsCommand,
    )

    archived = {
        **stored_single_file_document(),
        "lifecycle_status": "archived",
    }
    database = FakeArtifactDatabase(
        (
            ArtifactDocumentRecord(
                artifact_id="artifact--archived",
                document=archived,
            ),
            ArtifactDocumentRecord(
                artifact_id="artifact--active",
                document=stored_single_file_document(),
            ),
        )
    )

    listing = await GenericArtifactReadService(
        database=database
    ).list_artifacts(
        ListGenericArtifactsCommand(project_id="project-1", limit=10)
    )

    assert [
        item.reference.artifact_id for item in listing.artifacts
    ] == ["artifact--active"]


@pytest.mark.asyncio
async def test_generic_artifact_service_gets_single_file_detail() -> None:
    from database import ArtifactDocumentRecord
    from generic_artifact_service import (
        GenericArtifactReadService,
        GetGenericArtifactCommand,
    )

    database = FakeArtifactDatabase(
        (
            ArtifactDocumentRecord(
                artifact_id="artifact--abc",
                document=stored_single_file_document(),
            ),
        )
    )

    detail = await GenericArtifactReadService(database=database).get_artifact(
        GetGenericArtifactCommand(
            project_id="project-1",
            artifact_id="artifact--abc",
        )
    )

    assert detail.metadata.filename == "password_generator.py"
    assert detail.artifact.content.startswith("import secrets")


@pytest.mark.asyncio
async def test_generic_artifact_service_archives_single_file_artifact(
) -> None:
    from database import ArtifactDocumentRecord
    from generic_artifact_service import (
        ArchiveGenericArtifactCommand,
        GenericArtifactReadService,
    )

    database = FakeArtifactDatabase(
        (
            ArtifactDocumentRecord(
                artifact_id="artifact--abc",
                document={
                    **stored_single_file_document(),
                    "lifecycle_status": "archived",
                },
            ),
        )
    )

    result = await GenericArtifactReadService(
        database=database
    ).archive_artifact(
        ArchiveGenericArtifactCommand(
            project_id="project-1",
            artifact_id="artifact--abc",
        )
    )

    assert database.archive_calls == [("project-1", "artifact--abc")]
    assert result.metadata.lifecycle_status == "archived"


@pytest.mark.asyncio
async def test_generic_artifact_service_rejects_blueprint_documents() -> None:
    from database import ArtifactDocumentRecord
    from generic_artifact_service import (
        ArtifactReadStateError,
        GenericArtifactReadService,
        GetGenericArtifactCommand,
    )

    database = FakeArtifactDatabase(
        (
            ArtifactDocumentRecord(
                artifact_id="blueprint--abc",
                document={
                    "artifact_contract_version": "1.0",
                    "artifact_type": "synthesis_blueprint",
                    "schema_version": "2.0",
                },
            ),
        )
    )

    with pytest.raises(ArtifactReadStateError):
        await GenericArtifactReadService(database=database).get_artifact(
            GetGenericArtifactCommand(
                project_id="project-1",
                artifact_id="blueprint--abc",
            )
        )
