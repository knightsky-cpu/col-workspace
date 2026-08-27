from datetime import UTC, datetime

import pytest


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


class FakeArtifactDatabase:
    def __init__(self, records: tuple[object, ...]) -> None:
        self.records = records
        self.archive_calls: list[tuple[str, str]] = []
        self.update_calls: list[tuple[str, str, str | None, str | None]] = []
        self.save_calls: list[dict[str, object]] = []

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

    async def update_artifact_metadata_document(
        self,
        project_id: str,
        artifact_id: str,
        *,
        display_label: str | None,
        filename: str | None,
    ) -> object:
        self.update_calls.append(
            (project_id, artifact_id, display_label, filename)
        )
        return self.records[0]

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
    ) -> str:
        self.save_calls.append(
            {
                "project_id": project_id,
                "session_id": session_id,
                "user_id": user_id,
                "model_name": model_name,
                "artifact": artifact,
                "display_label": display_label,
                "originating_turn_id": originating_turn_id,
                "parent_artifact_id": parent_artifact_id,
            }
        )
        return "artifact--replacement"


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
async def test_generic_artifact_service_lists_archived_single_file_metadata(
) -> None:
    from database import ArtifactDocumentRecord
    from generic_artifact_service import (
        GenericArtifactReadService,
        ListGenericArtifactsCommand,
    )

    database = FakeArtifactDatabase(
        (
            ArtifactDocumentRecord(
                artifact_id="artifact--archived",
                document={
                    **stored_single_file_document(),
                    "lifecycle_status": "archived",
                },
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
        ListGenericArtifactsCommand(
            project_id="project-1",
            limit=10,
            lifecycle_status="archived",
        )
    )

    assert [
        item.reference.artifact_id for item in listing.artifacts
    ] == ["artifact--archived"]
    assert listing.artifacts[0].lifecycle_status == "archived"


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
async def test_generic_artifact_service_restores_single_file_artifact(
) -> None:
    from database import ArtifactDocumentRecord
    from generic_artifact_service import (
        GenericArtifactReadService,
        RestoreGenericArtifactCommand,
    )

    class RestoreDatabase(FakeArtifactDatabase):
        def __init__(self, records: tuple[object, ...]) -> None:
            super().__init__(records)
            self.restore_calls: list[tuple[str, str]] = []

        async def restore_artifact_document(
            self,
            project_id: str,
            artifact_id: str,
        ) -> object:
            self.restore_calls.append((project_id, artifact_id))
            return self.records[0]

    database = RestoreDatabase(
        (
            ArtifactDocumentRecord(
                artifact_id="artifact--abc",
                document=stored_single_file_document(),
            ),
        )
    )

    result = await GenericArtifactReadService(
        database=database
    ).restore_artifact(
        RestoreGenericArtifactCommand(
            project_id="project-1",
            artifact_id="artifact--abc",
        )
    )

    assert database.restore_calls == [("project-1", "artifact--abc")]
    assert result.metadata.lifecycle_status == "active"


@pytest.mark.asyncio
async def test_generic_artifact_service_updates_single_file_artifact_metadata(
) -> None:
    from database import ArtifactDocumentRecord
    from generic_artifact_service import (
        GenericArtifactReadService,
        UpdateGenericArtifactMetadataCommand,
    )

    updated_document = {
        **stored_single_file_document(),
        "display_label": "Renamed Generator",
        "filename": "renamed_generator.py",
    }
    database = FakeArtifactDatabase(
        (
            ArtifactDocumentRecord(
                artifact_id="artifact--abc",
                document=updated_document,
            ),
        )
    )

    result = await GenericArtifactReadService(
        database=database
    ).update_artifact_metadata(
        UpdateGenericArtifactMetadataCommand(
            project_id="project-1",
            artifact_id="artifact--abc",
            display_label="Renamed Generator",
            filename="renamed_generator.py",
        )
    )

    assert database.update_calls == [
        (
            "project-1",
            "artifact--abc",
            "Renamed Generator",
            "renamed_generator.py",
        )
    ]
    assert result.metadata.reference.display_label == "Renamed Generator"
    assert result.metadata.filename == "renamed_generator.py"


@pytest.mark.asyncio
async def test_generic_artifact_service_creates_linked_content_replacement(
) -> None:
    from database import ArtifactDocumentRecord
    from generic_artifact_service import (
        CreateGenericArtifactVersionCommand,
        GENERIC_ARTIFACT_VERSION_MODEL_NAME,
        GenericArtifactReadService,
    )

    database = FakeArtifactDatabase(
        (
            ArtifactDocumentRecord(
                artifact_id="artifact--abc",
                document=stored_single_file_document(),
            ),
        )
    )

    result = await GenericArtifactReadService(
        database=database
    ).create_artifact_version(
        CreateGenericArtifactVersionCommand(
            project_id="project-1",
            artifact_id="artifact--abc",
            session_id="session-2",
            user_id="user-1",
            content="import secrets\nprint('replacement')\n",
            filename="password_generator_v2.py",
            display_label="Password Generator v2",
            originating_turn_id="turn-2",
        )
    )

    assert result.reference.artifact_id == "artifact--replacement"
    assert result.reference.display_label == "Password Generator v2"
    assert result.artifact.filename == "password_generator_v2.py"
    assert result.artifact.artifact_family == "code"
    assert result.artifact.format == "python"
    assert database.save_calls == [
        {
            "project_id": "project-1",
            "session_id": "session-2",
            "user_id": "user-1",
            "model_name": GENERIC_ARTIFACT_VERSION_MODEL_NAME,
            "artifact": {
                "artifact_family": "code",
                "format": "python",
                "filename": "password_generator_v2.py",
                "content": "import secrets\nprint('replacement')\n",
                "summary": "Secure password generator.",
            },
            "display_label": "Password Generator v2",
            "originating_turn_id": "turn-2",
            "parent_artifact_id": "artifact--abc",
        }
    ]


@pytest.mark.asyncio
async def test_generic_artifact_service_bounds_summary_derived_version_label(
) -> None:
    from database import ArtifactDocumentRecord
    from generic_artifact_service import (
        CreateGenericArtifactVersionCommand,
        GenericArtifactReadService,
    )

    database = FakeArtifactDatabase(
        (
            ArtifactDocumentRecord(
                artifact_id="artifact--abc",
                document=stored_single_file_document(),
            ),
        )
    )
    long_summary = "A" * 300

    result = await GenericArtifactReadService(
        database=database
    ).create_artifact_version(
        CreateGenericArtifactVersionCommand(
            project_id="project-1",
            artifact_id="artifact--abc",
            session_id="session-2",
            user_id="user-1",
            content="import secrets\nprint('replacement')\n",
            summary=long_summary,
            originating_turn_id="turn-2",
        )
    )

    assert result.artifact.summary == long_summary
    assert result.reference.display_label == long_summary[:160]
    assert database.save_calls[0]["artifact"]["summary"] == long_summary
    assert database.save_calls[0]["display_label"] == long_summary[:160]


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
