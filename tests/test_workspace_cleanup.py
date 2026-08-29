from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from auth import google_subject_to_workspace_project_id
from workspace_cleanup import (
    WorkspaceCleanupCandidate,
    cleanup_deleted_workspace_data,
    default_workspace_id_for_user,
    discover_deleted_workspace_cleanup_candidates,
)


class AsyncStream:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        self._iterator = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeSnapshot:
    def __init__(self, reference, data):
        self.reference = reference
        self.id = reference.id
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


class FakeDocument:
    def __init__(self, collection, doc_id, data=None):
        self.collection_ref = collection
        self.id = doc_id
        self._data = data
        self.delete = AsyncMock()
        self._collections = {}

    async def get(self):
        return FakeSnapshot(self, self._data)

    def collection(self, name):
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]


class FakeCollection:
    def __init__(self):
        self.documents = {}

    def document(self, doc_id):
        if doc_id not in self.documents:
            self.documents[doc_id] = FakeDocument(self, doc_id)
        return self.documents[doc_id]

    def add_document(self, doc_id, data=None):
        document = FakeDocument(self, doc_id, data)
        self.documents[doc_id] = document
        return document

    def stream(self):
        snapshots = [
            FakeSnapshot(document, document._data)
            for document in self.documents.values()
            if document._data is not None
        ]
        return AsyncStream(snapshots)

    def list_documents(self, page_size=None):
        return AsyncStream(self.documents.values())


class FakeClient:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


def test_default_workspace_id_for_user_uses_google_subject_hash() -> None:
    assert default_workspace_id_for_user("google--109876543210") == (
        google_subject_to_workspace_project_id("109876543210")
    )
    assert default_workspace_id_for_user("wifiknight") == "agent-col"


@pytest.mark.asyncio
async def test_discovery_selects_deleted_and_orphaned_workspace_data() -> None:
    client = FakeClient()
    users = client.collection("users")
    user = users.add_document("google--109876543210", {"updated_at": "now"})
    default_workspace_id = default_workspace_id_for_user(user.id)
    workspaces = user.collection("workspaces")
    workspaces.add_document(
        default_workspace_id,
        {
            "workspace_id": default_workspace_id,
            "display_name": "Private Google workspace",
            "deleted": True,
            "is_default": True,
        },
    )
    workspaces.add_document(
        f"{default_workspace_id}--active",
        {
            "workspace_id": f"{default_workspace_id}--active",
            "display_name": "Active",
        },
    )
    workspaces.add_document(
        f"{default_workspace_id}--legacy-deleted",
        {
            "workspace_id": f"{default_workspace_id}--legacy-deleted",
            "display_name": "Legacy Deleted",
            "deleted": True,
        },
    )
    workspaces.add_document(f"{default_workspace_id}--orphaned")
    client.collection("projects").add_document(
        f"{default_workspace_id}--project-only",
        {"updated_at": "legacy"},
    )
    client.collection("sessions").add_document(
        "session--legacy",
        {
            "user_id": user.id,
            "project_id": f"{default_workspace_id}--session-only",
        },
    )

    candidates = await discover_deleted_workspace_cleanup_candidates(
        client,
        user_id=user.id,
    )

    assert candidates == [
        WorkspaceCleanupCandidate(
            user_id=user.id,
            workspace_id=default_workspace_id,
            reason="default_tombstone_owned_data",
            preserve_workspace_document=True,
        ),
        WorkspaceCleanupCandidate(
            user_id=user.id,
            workspace_id=f"{default_workspace_id}--legacy-deleted",
            reason="deleted_non_default_workspace",
            preserve_workspace_document=False,
        ),
        WorkspaceCleanupCandidate(
            user_id=user.id,
            workspace_id=f"{default_workspace_id}--orphaned",
            reason="orphaned_workspace_reference",
            preserve_workspace_document=False,
        ),
        WorkspaceCleanupCandidate(
            user_id=user.id,
            workspace_id=f"{default_workspace_id}--project-only",
            reason="orphaned_project_document",
            preserve_workspace_document=False,
        ),
        WorkspaceCleanupCandidate(
            user_id=user.id,
            workspace_id=f"{default_workspace_id}--session-only",
            reason="orphaned_chat_session",
            preserve_workspace_document=False,
        ),
    ]


@pytest.mark.asyncio
async def test_cleanup_dry_run_reports_without_deleting() -> None:
    engine = SimpleNamespace(
        _delete_non_default_workspace_owned_data=AsyncMock(),
        _client=MagicMock(),
    )
    candidate = WorkspaceCleanupCandidate(
        user_id="user-1",
        workspace_id="agent-col--legacy",
        reason="orphaned_project_document",
        preserve_workspace_document=False,
    )

    results = await cleanup_deleted_workspace_data(
        engine,
        [candidate],
        apply=False,
    )

    assert results[0].status == "dry-run"
    engine._delete_non_default_workspace_owned_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_apply_preserves_default_tombstone_metadata() -> None:
    workspace_ref = MagicMock()
    workspace_ref.delete = AsyncMock()
    workspaces = MagicMock()
    workspaces.document.return_value = workspace_ref
    user_ref = MagicMock()
    user_ref.collection.return_value = workspaces
    users = MagicMock()
    users.document.return_value = user_ref
    client = MagicMock()
    client.collection.return_value = users
    engine = SimpleNamespace(
        _delete_non_default_workspace_owned_data=AsyncMock(),
        _client=client,
    )
    candidate = WorkspaceCleanupCandidate(
        user_id="user-1",
        workspace_id="agent-col",
        reason="default_tombstone_owned_data",
        preserve_workspace_document=True,
    )

    results = await cleanup_deleted_workspace_data(
        engine,
        [candidate],
        apply=True,
    )

    assert results[0].status == "deleted-owned-data"
    engine._delete_non_default_workspace_owned_data.assert_awaited_once_with(
        "user-1",
        "agent-col",
    )
    workspace_ref.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_apply_deletes_non_default_workspace_metadata() -> None:
    workspace_ref = MagicMock()
    workspace_ref.delete = AsyncMock()
    workspaces = MagicMock()
    workspaces.document.return_value = workspace_ref
    user_ref = MagicMock()
    user_ref.collection.return_value = workspaces
    users = MagicMock()
    users.document.return_value = user_ref
    client = MagicMock()
    client.collection.return_value = users
    engine = SimpleNamespace(
        _delete_non_default_workspace_owned_data=AsyncMock(),
        _client=client,
    )
    candidate = WorkspaceCleanupCandidate(
        user_id="user-1",
        workspace_id="agent-col--legacy",
        reason="orphaned_project_document",
        preserve_workspace_document=False,
    )

    results = await cleanup_deleted_workspace_data(
        engine,
        [candidate],
        apply=True,
    )

    assert results[0].status == "deleted-owned-data-and-metadata"
    engine._delete_non_default_workspace_owned_data.assert_awaited_once_with(
        "user-1",
        "agent-col--legacy",
    )
    workspace_ref.delete.assert_awaited_once_with()
