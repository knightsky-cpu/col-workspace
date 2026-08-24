from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath

from database import (
    BlueprintArtifactCursorNotFoundError,
    BlueprintArtifactNotFoundError,
    ArtifactNotFoundError,
    MemoryEngine,
)


async def snapshot_stream(items: list[object]):
    for item in items:
        yield item


def artifact_store() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    client = MagicMock()
    projects = MagicMock()
    project = MagicMock()
    blueprints = MagicMock()
    client.collection.return_value = projects
    projects.document.return_value = project
    project.collection.return_value = blueprints
    return client, projects, project, blueprints


@pytest.mark.asyncio
async def test_list_blueprint_documents_is_newest_first_and_bounded() -> None:
    client, projects, project, blueprints = artifact_store()
    first_order = MagicMock()
    second_order = MagicMock()
    limited_query = MagicMock()
    blueprints.order_by.return_value = first_order
    first_order.order_by.return_value = second_order
    second_order.limit.return_value = limited_query
    snapshots = [
        SimpleNamespace(
            id=f"blueprint-{index}",
            to_dict=lambda index=index: {"position": index},
        )
        for index in range(21)
    ]
    limited_query.stream.return_value = snapshot_stream(snapshots)

    page = await MemoryEngine(client).list_blueprint_documents(
        "project-1",
        limit=20,
        before=None,
    )

    assert len(page.records) == 20
    assert page.records[0].artifact_id == "blueprint-0"
    assert page.records[-1].artifact_id == "blueprint-19"
    assert page.next_before == "blueprint-19"
    client.collection.assert_called_once_with("projects")
    projects.document.assert_called_once_with("project-1")
    project.collection.assert_called_once_with("blueprints")
    blueprints.order_by.assert_called_once_with(
        "created_at",
        direction=firestore.Query.DESCENDING,
    )
    first_order.order_by.assert_called_once_with(
        FieldPath.document_id(),
        direction=firestore.Query.DESCENDING,
    )
    second_order.limit.assert_called_once_with(21)


@pytest.mark.asyncio
async def test_list_blueprint_documents_starts_after_project_cursor() -> None:
    client, _, _, blueprints = artifact_store()
    cursor_snapshot = SimpleNamespace(
        id="blueprint-cursor",
        exists=True,
        to_dict=lambda: {"created_at": object()},
    )
    cursor_ref = MagicMock()
    cursor_ref.get = AsyncMock(return_value=cursor_snapshot)
    blueprints.document.return_value = cursor_ref
    first_order = MagicMock()
    second_order = MagicMock()
    cursor_query = MagicMock()
    limited_query = MagicMock()
    blueprints.order_by.return_value = first_order
    first_order.order_by.return_value = second_order
    second_order.start_after.return_value = cursor_query
    cursor_query.limit.return_value = limited_query
    limited_query.stream.return_value = snapshot_stream([])

    page = await MemoryEngine(client).list_blueprint_documents(
        "project-1",
        limit=10,
        before="blueprint-cursor",
    )

    assert page.records == ()
    assert page.next_before is None
    blueprints.document.assert_called_once_with("blueprint-cursor")
    cursor_ref.get.assert_awaited_once_with()
    second_order.start_after.assert_called_once_with(cursor_snapshot)
    cursor_query.limit.assert_called_once_with(11)


@pytest.mark.asyncio
async def test_list_blueprint_documents_rejects_missing_cursor() -> None:
    client, _, _, blueprints = artifact_store()
    cursor_ref = MagicMock()
    cursor_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    blueprints.document.return_value = cursor_ref
    first_order = MagicMock()
    second_order = MagicMock()
    blueprints.order_by.return_value = first_order
    first_order.order_by.return_value = second_order

    with pytest.raises(BlueprintArtifactCursorNotFoundError):
        await MemoryEngine(client).list_blueprint_documents(
            "project-1",
            limit=20,
            before="missing-cursor",
        )

    second_order.start_after.assert_not_called()


@pytest.mark.asyncio
async def test_get_blueprint_document_returns_project_owned_record() -> None:
    client, _, _, blueprints = artifact_store()
    snapshot = SimpleNamespace(
        id="blueprint-1",
        exists=True,
        to_dict=lambda: {"schema_version": "2.0"},
    )
    blueprint_ref = MagicMock()
    blueprint_ref.get = AsyncMock(return_value=snapshot)
    blueprints.document.return_value = blueprint_ref

    record = await MemoryEngine(client).get_blueprint_document(
        "project-1",
        "blueprint-1",
    )

    assert record.artifact_id == "blueprint-1"
    assert record.document == {"schema_version": "2.0"}
    blueprints.document.assert_called_once_with("blueprint-1")
    blueprint_ref.get.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_get_blueprint_document_rejects_missing_artifact() -> None:
    client, _, _, blueprints = artifact_store()
    blueprint_ref = MagicMock()
    blueprint_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    blueprints.document.return_value = blueprint_ref

    with pytest.raises(BlueprintArtifactNotFoundError):
        await MemoryEngine(client).get_blueprint_document(
            "project-1",
            "missing-blueprint",
        )


@pytest.mark.asyncio
async def test_update_artifact_metadata_document_updates_only_public_metadata(
) -> None:
    client, projects, project, artifacts = artifact_store()
    artifact_ref = MagicMock()
    artifact_ref.update = AsyncMock()
    snapshot = SimpleNamespace(
        exists=True,
        to_dict=lambda: {
            "artifact_contract_version": "1.0",
            "artifact_type": "single_file_artifact",
            "schema_version": "1.0",
            "display_label": "Renamed Generator",
            "filename": "renamed_generator.py",
            "content": "print('unchanged')\n",
        },
    )
    artifact_ref.get = AsyncMock(return_value=snapshot)
    artifacts.document.return_value = artifact_ref

    record = await MemoryEngine(client).update_artifact_metadata_document(
        "project-1",
        "artifact--abc",
        display_label="Renamed Generator",
        filename="renamed_generator.py",
    )

    projects.document.assert_called_once_with("project-1")
    project.collection.assert_called_once_with("artifacts")
    artifacts.document.assert_called_once_with("artifact--abc")
    artifact_ref.update.assert_awaited_once_with(
        {
            "display_label": "Renamed Generator",
            "filename": "renamed_generator.py",
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )
    assert record.artifact_id == "artifact--abc"
    assert record.document["content"] == "print('unchanged')\n"


@pytest.mark.asyncio
async def test_update_artifact_metadata_document_rejects_missing_artifact(
) -> None:
    client, _, _, artifacts = artifact_store()
    artifact_ref = MagicMock()
    artifact_ref.update = AsyncMock()
    artifact_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    artifacts.document.return_value = artifact_ref

    with pytest.raises(ArtifactNotFoundError):
        await MemoryEngine(client).update_artifact_metadata_document(
            "project-1",
            "artifact--abc",
            display_label="Renamed Generator",
            filename=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", (0, 51, True, "20"))
async def test_list_blueprint_documents_validates_limit_before_access(
    limit: object,
) -> None:
    client = MagicMock()

    with pytest.raises(ValueError):
        await MemoryEngine(client).list_blueprint_documents(
            "project-1",
            limit=limit,
            before=None,
        )

    client.collection.assert_not_called()
