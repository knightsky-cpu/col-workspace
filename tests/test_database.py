import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore

import database
from chat_turns import ChatSessionOwnershipError, ChatTurnStateError
from database import MemoryEngine, MemoryEngineError
from schemas import AdaptationReceipt, WorkspaceCreateRequest


class AsyncSnapshotStream:
    def __init__(self, snapshots: list[object]) -> None:
        self._snapshots = snapshots

    def __aiter__(self) -> object:
        self._iterator = iter(self._snapshots)
        return self

    async def __anext__(self) -> object:
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def install_transaction_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    def run_without_sdk_retry(callback):
        async def run(transaction, *args, **kwargs):
            return await callback(transaction, *args, **kwargs)

        return run

    monkeypatch.setattr(
        database.firestore,
        "async_transactional",
        run_without_sdk_retry,
    )


def document_snapshot(*, exists: bool, data: object = None) -> SimpleNamespace:
    return SimpleNamespace(exists=exists, to_dict=lambda: data)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_session",
    (
        {"project_id": "project-1", "user_id": "other-user"},
        {"project_id": "other-project", "user_id": "user-1"},
    ),
)
async def test_save_message_rejects_session_ownership_mismatch_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    stored_session: dict[str, object],
) -> None:
    install_transaction_runner(monkeypatch)
    client = MagicMock()
    session = client.collection.return_value.document.return_value
    session.get = AsyncMock(
        return_value=document_snapshot(exists=True, data=stored_session)
    )
    transaction = client.transaction.return_value

    with pytest.raises(ChatSessionOwnershipError):
        await MemoryEngine(client).save_message(
            "session-1",
            "user",
            "hello",
            project_id="project-1",
            user_id="user-1",
        )

    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_save_message_rejects_malformed_session_ownership_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client = MagicMock()
    session = client.collection.return_value.document.return_value
    session.get = AsyncMock(
        return_value=document_snapshot(
            exists=True,
            data={"project_id": "project-1"},
        )
    )
    transaction = client.transaction.return_value

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(client).save_message(
            "session-1",
            "user",
            "hello",
            project_id="project-1",
            user_id="user-1",
        )

    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_save_message_commits_parent_and_message_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client = MagicMock()
    sessions = MagicMock()
    session = MagicMock()
    messages = MagicMock()
    message = MagicMock(id="message-1")
    transaction = MagicMock()

    client.collection.return_value = sessions
    sessions.document.return_value = session
    session.collection.return_value = messages
    messages.document.return_value = message
    client.transaction.return_value = transaction
    session.get = AsyncMock(
        return_value=document_snapshot(exists=False)
    )

    engine = MemoryEngine(client=client)
    message_id = await engine.save_message(
        "session-1",
        "user",
        "hello",
        project_id="project-1",
        user_id="user-1",
    )

    assert message_id == "message-1"
    client.collection.assert_called_once_with("sessions")
    sessions.document.assert_called_once_with("session-1")
    session.collection.assert_called_once_with("messages")
    messages.document.assert_called_once_with()
    session.get.assert_awaited_once_with(transaction=transaction)
    assert transaction.set.call_args_list == [
        call(
            session,
            {
                "project_id": "project-1",
                "user_id": "user-1",
                "updated_at": firestore.SERVER_TIMESTAMP,
                "last_message_preview": "hello",
                "last_message_role": "user",
            },
            merge=True,
        ),
        call(
            message,
            {
                "role": "user",
                "text": "hello",
                "timestamp": firestore.SERVER_TIMESTAMP,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_save_message_preserves_matching_existing_session_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client = MagicMock()
    session = client.collection.return_value.document.return_value
    message = session.collection.return_value.document.return_value
    message.id = "message-1"
    transaction = client.transaction.return_value
    session.get = AsyncMock(
        return_value=document_snapshot(
            exists=True,
            data={"project_id": "project-1", "user_id": "user-1"},
        )
    )

    await MemoryEngine(client).save_message(
        "session-1",
        "model",
        "answer",
        project_id="project-1",
        user_id="user-1",
    )

    session_write = transaction.set.call_args_list[0]
    assert session_write.args[0] is session
    assert session_write.args[1] == {
        "updated_at": firestore.SERVER_TIMESTAMP,
        "last_message_preview": "answer",
        "last_message_role": "model",
    }
    assert "project_id" not in session_write.args[1]
    assert "user_id" not in session_write.args[1]


@pytest.mark.asyncio
async def test_create_workspace_persists_user_workspace_container() -> None:
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    workspaces = MagicMock()
    workspace = MagicMock()
    batch = MagicMock()
    batch.commit = AsyncMock(return_value=[])

    client.collection.return_value = users
    users.document.return_value = user
    user.collection.return_value = workspaces
    workspaces.document.return_value = workspace
    client.batch.return_value = batch

    result = await MemoryEngine(client).create_workspace(
        user_id="user-1",
        workspace_id="project--abc--study-plans",
        request=WorkspaceCreateRequest(display_name="Study Plans"),
    )

    assert result.workspace_id == "project--abc--study-plans"
    assert result.display_name == "Study Plans"
    assert result.is_default is False
    client.collection.assert_called_once_with("users")
    users.document.assert_called_once_with("user-1")
    user.collection.assert_called_once_with("workspaces")
    workspaces.document.assert_called_once_with("project--abc--study-plans")
    assert batch.set.call_args_list == [
        call(
            user,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(
            workspace,
            {
                "workspace_contract_version": "1.0",
                "workspace_id": "project--abc--study-plans",
                "display_name": "Study Plans",
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "is_default": False,
            },
            merge=False,
        ),
    ]


@pytest.mark.asyncio
async def test_list_workspaces_does_not_synthesize_deleted_default() -> None:
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    workspaces = MagicMock()
    default_snapshot = SimpleNamespace(
        id="agent-col",
        to_dict=lambda: {
            "workspace_id": "agent-col",
            "display_name": "Agent Col",
            "deleted": True,
            "is_default": True,
        },
    )

    client.collection.return_value = users
    users.document.return_value = user
    user.collection.return_value = workspaces
    workspaces.limit.return_value.stream.return_value = AsyncSnapshotStream([
        default_snapshot
    ])

    result = await MemoryEngine(client).list_workspaces(
        user_id="user-1",
        default_workspace_id="agent-col",
        default_display_name="Agent Col",
        limit=20,
    )

    assert result.workspaces == []


@pytest.mark.asyncio
async def test_delete_synthesized_default_workspace_writes_tombstone_when_other_workspace_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    workspaces = MagicMock()
    default_ref = MagicMock()
    other_ref = MagicMock()
    transaction = MagicMock()
    other_snapshot = SimpleNamespace(
        id="project--abc--study-plans",
        to_dict=lambda: {
            "workspace_id": "project--abc--study-plans",
            "display_name": "Study Plans",
            "is_default": False,
        },
    )

    client.collection.return_value = users
    users.document.return_value = user
    user.collection.return_value = workspaces
    workspaces.document.side_effect = lambda workspace_id: {
        "agent-col": default_ref,
        "project--abc--study-plans": other_ref,
    }[workspace_id]
    workspaces.limit.return_value.stream.return_value = AsyncSnapshotStream([
        other_snapshot
    ])
    client.transaction.return_value = transaction

    await MemoryEngine(client).delete_workspace(
        user_id="user-1",
        workspace_id="agent-col",
        default_workspace_id="agent-col",
        default_display_name="Agent Col",
    )

    transaction.set.assert_any_call(
        user,
        {"updated_at": firestore.SERVER_TIMESTAMP},
        merge=True,
    )
    transaction.set.assert_any_call(
        default_ref,
        {
            "workspace_contract_version": "1.0",
            "workspace_id": "agent-col",
            "display_name": "Agent Col",
            "deleted": True,
            "is_default": True,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=False,
    )
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_non_default_workspace_removes_metadata_when_other_workspace_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    workspaces = MagicMock()
    target_ref = MagicMock()
    transaction = MagicMock()
    target_snapshot = SimpleNamespace(
        id="project--abc--study-plans",
        to_dict=lambda: {
            "workspace_id": "project--abc--study-plans",
            "display_name": "Study Plans",
            "is_default": False,
        },
    )

    client.collection.return_value = users
    users.document.return_value = user
    user.collection.return_value = workspaces
    workspaces.document.return_value = target_ref
    workspaces.limit.return_value.stream.return_value = AsyncSnapshotStream([
        target_snapshot
    ])
    client.transaction.return_value = transaction

    await MemoryEngine(client).delete_workspace(
        user_id="user-1",
        workspace_id="project--abc--study-plans",
        default_workspace_id="agent-col",
        default_display_name="Agent Col",
    )

    transaction.delete.assert_called_once_with(target_ref)


@pytest.mark.asyncio
async def test_delete_workspace_rejects_last_visible_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    workspaces = MagicMock()
    transaction = MagicMock()

    client.collection.return_value = users
    users.document.return_value = user
    user.collection.return_value = workspaces
    workspaces.document.return_value = MagicMock()
    workspaces.limit.return_value.stream.return_value = AsyncSnapshotStream([])
    client.transaction.return_value = transaction

    with pytest.raises(database.WorkspaceDeletionConflictError):
        await MemoryEngine(client).delete_workspace(
            user_id="user-1",
            workspace_id="agent-col",
            default_workspace_id="agent-col",
            default_display_name="Agent Col",
        )

    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_save_blueprint_commits_parent_and_blueprint_atomically() -> None:
    client = MagicMock()
    projects = MagicMock()
    project = MagicMock()
    blueprints = MagicMock()
    blueprint_ref = MagicMock(id="blueprint-1")
    batch = MagicMock()
    batch.commit = AsyncMock(return_value=[])

    client.collection.return_value = projects
    projects.document.return_value = project
    project.collection.return_value = blueprints
    blueprints.document.return_value = blueprint_ref
    client.batch.return_value = batch
    payload = {
        "synthesized_conceptual_model": {
            "project_name": "Agent Col",
        }
    }

    blueprint_id = await MemoryEngine(client).save_blueprint(
        "project-1",
        "session-1",
        "user-1",
        "gemini-3.6-flash",
        "2.0",
        payload,
    )

    assert blueprint_id == "blueprint-1"
    client.collection.assert_called_once_with("projects")
    projects.document.assert_called_once_with("project-1")
    project.collection.assert_called_once_with("blueprints")
    blueprints.document.assert_called_once_with()
    assert batch.set.call_args_list == [
        call(
            project,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(
            blueprint_ref,
            {
                "artifact_contract_version": "1.0",
                "artifact_type": "synthesis_blueprint",
                "created_at": firestore.SERVER_TIMESTAMP,
                "originating_session_id": "session-1",
                "originating_turn_id": None,
                "user_id": "user-1",
                "model_name": "gemini-3.6-flash",
                "schema_version": "2.0",
                "parent_artifact_id": None,
                "feedback_counts": {
                    "accepted": 0,
                    "rejected": 0,
                    "edited": 0,
                },
                "adaptation_receipts": [],
                "applied_feedback_ids": [],
                "blueprint": payload,
            },
        ),
    ]
    batch.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_save_blueprint_persists_validated_adaptation_receipt() -> None:
    client = MagicMock()
    project = MagicMock()
    blueprint_ref = MagicMock(id="blueprint-1")
    batch = MagicMock()
    batch.commit = AsyncMock(return_value=[])
    client.collection.return_value.document.return_value = project
    project.collection.return_value.document.return_value = blueprint_ref
    client.batch.return_value = batch
    receipt = AdaptationReceipt(
        signal_id="planning-granularity-signal-1",
        category="planning_granularity",
        value="micro_steps",
        source_event_id="planning-granularity-signal-1--approved",
        status="provided_to_model",
    )

    blueprint_id = await MemoryEngine(client).save_blueprint(
        "project-1",
        "session-1",
        "user-1",
        "gemini-3.6-flash",
        "2.0",
        {"synthesized_conceptual_model": {"project_name": "Agent Col"}},
        adaptations=(receipt,),
    )

    assert blueprint_id == "blueprint-1"
    stored_document = batch.set.call_args_list[1].args[1]
    assert stored_document["adaptation_receipts"] == [
        {
            "signal_id": "planning-granularity-signal-1",
            "category": "planning_granularity",
            "value": "micro_steps",
            "source_event_id": (
                "planning-granularity-signal-1--approved"
            ),
            "status": "provided_to_model",
        }
    ]
    batch.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_save_blueprint_rejects_duplicate_adaptation_categories() -> None:
    client = MagicMock()
    receipt = AdaptationReceipt(
        signal_id="planning-granularity-signal-1",
        category="planning_granularity",
        value="tasks",
        source_event_id="planning-granularity-signal-1--approved",
        status="provided_to_model",
    )

    with pytest.raises(ValueError, match="categories must be unique"):
        await MemoryEngine(client).save_blueprint(
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {"synthesized_conceptual_model": {"project_name": "Agent Col"}},
            adaptations=(receipt, receipt),
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_save_blueprint_rejects_unvalidated_adaptation_mapping() -> None:
    client = MagicMock()

    with pytest.raises(ValueError, match="valid adaptation receipts"):
        await MemoryEngine(client).save_blueprint(
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {"synthesized_conceptual_model": {"project_name": "Agent Col"}},
            adaptations=(
                {
                    "signal_id": "unvalidated-signal",
                    "category": "planning_granularity",
                    "value": "tasks",
                },
            ),
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_save_single_file_artifact_commits_parent_and_artifact_atomically(
) -> None:
    client = MagicMock()
    projects = MagicMock()
    project = MagicMock()
    artifacts = MagicMock()
    artifact_ref = MagicMock(id="artifact-1")
    batch = MagicMock()
    batch.commit = AsyncMock(return_value=[])

    client.collection.return_value = projects
    projects.document.return_value = project
    project.collection.return_value = artifacts
    artifacts.document.return_value = artifact_ref
    client.batch.return_value = batch

    artifact_id = await MemoryEngine(client).save_single_file_artifact(
        project_id="project-1",
        session_id="session-1",
        user_id="user-1",
        model_name="gemini-3.6-flash",
        artifact={
            "artifact_family": "code",
            "format": "python",
            "filename": "password_generator.py",
            "content": "import secrets\nprint(secrets.token_hex(8))\n",
            "summary": "Secure password generator.",
        },
        display_label="Password Generator",
        originating_turn_id="turn-1",
        parent_artifact_id="artifact-parent",
    )

    assert artifact_id == "artifact-1"
    client.collection.assert_called_once_with("projects")
    projects.document.assert_called_once_with("project-1")
    project.collection.assert_called_once_with("artifacts")
    artifacts.document.assert_called_once_with()
    assert batch.set.call_args_list == [
        call(
            project,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(
            artifact_ref,
            {
                "artifact_contract_version": "1.0",
                "artifact_type": "single_file_artifact",
                "created_at": firestore.SERVER_TIMESTAMP,
                "originating_session_id": "session-1",
                "originating_turn_id": "turn-1",
                "user_id": "user-1",
                "model_name": "gemini-3.6-flash",
                "schema_version": "1.0",
                "display_label": "Password Generator",
                "parent_artifact_id": "artifact-parent",
                "lifecycle_status": "active",
                "filename": "password_generator.py",
                "artifact_family": "code",
                "format": "python",
                "byte_size": 43,
                "content": "import secrets\nprint(secrets.token_hex(8))\n",
                "summary": "Secure password generator.",
            },
        ),
    ]
    batch.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_save_single_file_artifact_rejects_invalid_json_content(
) -> None:
    client = MagicMock()

    with pytest.raises(ValueError, match="JSON artifact content is invalid"):
        await MemoryEngine(client).save_single_file_artifact(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            model_name="gemini-3.6-flash",
            artifact={
                "artifact_family": "data",
                "format": "json",
                "filename": "bad.json",
                "content": "{not json}",
            },
            display_label="Bad Config",
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_archive_artifact_document_marks_project_artifact_archived(
) -> None:
    client = MagicMock()
    projects = MagicMock()
    project = MagicMock()
    artifacts = MagicMock()
    artifact_ref = MagicMock()
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "artifact_contract_version": "1.0",
        "artifact_type": "single_file_artifact",
        "schema_version": "1.0",
        "created_at": datetime.now().astimezone(),
        "originating_session_id": "session-1",
        "originating_turn_id": "turn-1",
        "display_label": "Password Generator",
        "lifecycle_status": "archived",
        "filename": "password_generator.py",
        "artifact_family": "code",
        "format": "python",
        "byte_size": 43,
        "content": "import secrets\nprint(secrets.token_hex(8))\n",
        "summary": "Secure password generator.",
    }
    artifact_ref.get = AsyncMock(return_value=snapshot)
    artifact_ref.update = AsyncMock(return_value=None)

    client.collection.return_value = projects
    projects.document.return_value = project
    project.collection.return_value = artifacts
    artifacts.document.return_value = artifact_ref

    record = await MemoryEngine(client).archive_artifact_document(
        "project-1",
        "artifact--abc",
    )

    assert record.artifact_id == "artifact--abc"
    assert record.document["lifecycle_status"] == "archived"
    client.collection.assert_called_once_with("projects")
    projects.document.assert_called_once_with("project-1")
    project.collection.assert_called_once_with("artifacts")
    artifacts.document.assert_called_once_with("artifact--abc")
    artifact_ref.update.assert_awaited_once_with(
        {
            "lifecycle_status": "archived",
            "archived_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )
    artifact_ref.get.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_restore_artifact_document_marks_project_artifact_active(
) -> None:
    client = MagicMock()
    projects = MagicMock()
    project = MagicMock()
    artifacts = MagicMock()
    artifact_ref = MagicMock()
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "artifact_contract_version": "1.0",
        "artifact_type": "single_file_artifact",
        "schema_version": "1.0",
        "created_at": datetime.now().astimezone(),
        "originating_session_id": "session-1",
        "originating_turn_id": "turn-1",
        "display_label": "Password Generator",
        "lifecycle_status": "active",
        "filename": "password_generator.py",
        "artifact_family": "code",
        "format": "python",
        "byte_size": 43,
        "content": "import secrets\nprint(secrets.token_hex(8))\n",
        "summary": "Secure password generator.",
    }
    artifact_ref.get = AsyncMock(return_value=snapshot)
    artifact_ref.update = AsyncMock(return_value=None)

    client.collection.return_value = projects
    projects.document.return_value = project
    project.collection.return_value = artifacts
    artifacts.document.return_value = artifact_ref

    record = await MemoryEngine(client).restore_artifact_document(
        "project-1",
        "artifact--abc",
    )

    assert record.artifact_id == "artifact--abc"
    assert record.document["lifecycle_status"] == "active"
    artifact_ref.update.assert_awaited_once_with(
        {
            "lifecycle_status": "active",
            "restored_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )
    artifact_ref.get.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_get_artifact_document_reads_project_artifact() -> None:
    client = MagicMock()
    projects = MagicMock()
    project = MagicMock()
    artifacts = MagicMock()
    artifact_ref = MagicMock()
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "artifact_contract_version": "1.0",
        "artifact_type": "single_file_artifact",
        "schema_version": "1.0",
    }
    artifact_ref.get = AsyncMock(return_value=snapshot)

    client.collection.return_value = projects
    projects.document.return_value = project
    project.collection.return_value = artifacts
    artifacts.document.return_value = artifact_ref

    record = await MemoryEngine(client).get_artifact_document(
        "project-1",
        "artifact--abc",
    )

    assert record.artifact_id == "artifact--abc"
    assert record.document["artifact_type"] == "single_file_artifact"
    client.collection.assert_called_once_with("projects")
    projects.document.assert_called_once_with("project-1")
    project.collection.assert_called_once_with("artifacts")
    artifacts.document.assert_called_once_with("artifact--abc")
    artifact_ref.get.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_list_artifact_documents_reads_bounded_project_artifacts(
) -> None:
    client = MagicMock()
    projects = MagicMock()
    project = MagicMock()
    artifacts = MagicMock()
    ordered_query = MagicMock()
    limited_query = MagicMock()
    snapshot_1 = MagicMock(id="artifact--2")
    snapshot_1.to_dict.return_value = {
        "artifact_contract_version": "1.0",
        "artifact_type": "single_file_artifact",
    }
    snapshot_2 = MagicMock(id="artifact--1")
    snapshot_2.to_dict.return_value = {
        "artifact_contract_version": "1.0",
        "artifact_type": "single_file_artifact",
    }
    limited_query.stream.return_value = AsyncSnapshotStream(
        [snapshot_1, snapshot_2]
    )

    client.collection.return_value = projects
    projects.document.return_value = project
    project.collection.return_value = artifacts
    artifacts.order_by.return_value = ordered_query
    ordered_query.order_by.return_value = ordered_query
    ordered_query.limit.return_value = limited_query

    page = await MemoryEngine(client).list_artifact_documents(
        "project-1",
        limit=1,
        before=None,
    )

    assert [record.artifact_id for record in page.records] == [
        "artifact--2"
    ]
    assert page.next_before == "artifact--2"
    project.collection.assert_called_once_with("artifacts")
    artifacts.order_by.assert_called_once_with(
        "created_at",
        direction=firestore.Query.DESCENDING,
    )


@pytest.mark.asyncio
async def test_save_blueprint_rejects_more_than_eight_adaptations() -> None:
    client = MagicMock()
    category_values = (
        ("preferred_name", "Avery"),
        ("broad_roles", ["student"]),
        ("response_length", "concise"),
        ("explanation_structure", "step_by_step"),
        ("example_usage", "when_helpful"),
        ("question_style", "minimal_follow_up"),
        ("planning_granularity", "tasks"),
        ("progress_check_ins", "at_milestones"),
        ("tool_use_style", "use_when_needed"),
    )
    receipts = tuple(
        AdaptationReceipt.model_validate(
            {
                "signal_id": f"signal-{index}",
                "category": category,
                "value": value,
                "source_event_id": f"signal-{index}--approved",
                "status": "provided_to_model",
            }
        )
        for index, (category, value) in enumerate(category_values, start=1)
    )

    with pytest.raises(ValueError, match="valid adaptation receipts"):
        await MemoryEngine(client).save_blueprint(
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {"synthesized_conceptual_model": {"project_name": "Agent Col"}},
            adaptations=receipts,
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    (
        (
            "",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {"key": "value"},
        ),
        (
            "project-1",
            "",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {"key": "value"},
        ),
        (
            "project-1",
            "session-1",
            " ",
            "gemini-3.6-flash",
            "2.0",
            {"key": "value"},
        ),
        (
            "project-1",
            "session-1",
            "user-1",
            "",
            "2.0",
            {"key": "value"},
        ),
        (
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "",
            {"key": "value"},
        ),
        (
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {},
        ),
        (
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            "invalid",
        ),
    ),
)
async def test_save_blueprint_rejects_invalid_input_before_access(
    arguments: tuple[object, ...],
) -> None:
    client = MagicMock()
    client.batch.return_value.commit = AsyncMock(return_value=[])

    with pytest.raises(ValueError):
        await MemoryEngine(client).save_blueprint(*arguments)

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_save_blueprint_preserves_firestore_error_safely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_value = "private-blueprint-value"
    firestore_error = ServiceUnavailable("backend unavailable")
    client = MagicMock()
    batch = MagicMock()
    batch.commit = AsyncMock(side_effect=firestore_error)
    client.batch.return_value = batch
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).save_blueprint(
            "private-project",
            "private-session",
            "private-user",
            "gemini-3.6-flash",
            "2.0",
            {"note": private_value},
        )

    assert caught.value.__cause__ is firestore_error
    assert "private-project" not in caplog.text
    assert "private-session" not in caplog.text
    assert "private-user" not in caplog.text
    assert private_value not in caplog.text


async def snapshot_stream():
    yield SimpleNamespace(
        to_dict=lambda: {"role": "user", "text": "first"}
    )
    yield SimpleNamespace(
        to_dict=lambda: {"role": "model", "text": "second"}
    )


async def snapshot_stream_from(items: list[dict[str, object]]):
    for item in items:
        yield SimpleNamespace(to_dict=lambda item=item: item)


async def snapshot_stream_with_ids(items: list[tuple[str, dict[str, object]]]):
    for snapshot_id, item in items:
        yield SimpleNamespace(
            id=snapshot_id,
            exists=True,
            to_dict=lambda item=item: item,
        )


@pytest.mark.asyncio
async def test_get_chat_history_orders_by_timestamp() -> None:
    client = MagicMock()
    sessions = MagicMock()
    session = MagicMock()
    messages = MagicMock()
    query = MagicMock()

    client.collection.return_value = sessions
    sessions.document.return_value = session
    session.get = AsyncMock(
        return_value=document_snapshot(
            exists=True,
            data={"project_id": "project-1", "user_id": "user-1"},
        )
    )
    session.collection.return_value = messages
    messages.order_by.return_value = query
    query.stream.return_value = snapshot_stream()

    engine = MemoryEngine(client=client)
    history = await engine.get_chat_history(
        "session-1",
        user_id="user-1",
        project_id="project-1",
    )

    messages.order_by.assert_called_once_with(
        "timestamp",
        direction=firestore.Query.ASCENDING,
    )
    assert history == [
        {"role": "user", "text": "first"},
        {"role": "model", "text": "second"},
    ]


@pytest.mark.asyncio
async def test_get_chat_history_returns_empty_for_missing_session_without_querying() -> None:
    client = MagicMock()
    session = client.collection.return_value.document.return_value
    session.get = AsyncMock(
        return_value=document_snapshot(exists=False)
    )

    history = await MemoryEngine(client).get_chat_history(
        "session-1",
        user_id="user-1",
        project_id="project-1",
    )

    assert history == []
    session.collection.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_session",
    (
        {"project_id": "project-1", "user_id": "other-user"},
        {"project_id": "other-project", "user_id": "user-1"},
    ),
)
async def test_get_chat_history_rejects_session_ownership_mismatch_before_query(
    stored_session: dict[str, object],
) -> None:
    client = MagicMock()
    session = client.collection.return_value.document.return_value
    session.get = AsyncMock(
        return_value=document_snapshot(exists=True, data=stored_session)
    )

    with pytest.raises(ChatSessionOwnershipError):
        await MemoryEngine(client).get_chat_history(
            "session-1",
            user_id="user-1",
            project_id="project-1",
        )

    session.collection.assert_not_called()


@pytest.mark.asyncio
async def test_get_chat_history_rejects_malformed_session_ownership_before_query() -> None:
    client = MagicMock()
    session = client.collection.return_value.document.return_value
    session.get = AsyncMock(
        return_value=document_snapshot(
            exists=True,
            data={"project_id": "project-1", "user_id": ""},
        )
    )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(client).get_chat_history(
            "session-1",
            user_id="user-1",
            project_id="project-1",
        )

    session.collection.assert_not_called()


@pytest.mark.asyncio
async def test_list_chat_sessions_filters_user_project_metadata() -> None:
    client = MagicMock()
    sessions = MagicMock()
    limited = MagicMock()
    client.collection.return_value = sessions
    sessions.limit.return_value = limited
    limited.stream.return_value = snapshot_stream_with_ids(
        [
            (
                "session-new",
                {
                    "project_id": "project-1",
                    "user_id": "user-1",
                    "updated_at": datetime(2026, 8, 24, 12, 0),
                    "last_message_preview": "new question",
                    "last_message_role": "user",
                },
            ),
            (
                "session-other-project",
                {
                    "project_id": "other-project",
                    "user_id": "user-1",
                    "updated_at": datetime(2026, 8, 24, 13, 0),
                    "last_message_preview": "private",
                    "last_message_role": "user",
                },
            ),
        ]
    )

    result = await MemoryEngine(client).list_chat_sessions(
        user_id="user-1",
        project_id="project-1",
        limit=20,
    )

    assert [session.session_id for session in result.sessions] == [
        "session-new"
    ]
    assert result.sessions[0].last_message_preview == "new question"
    sessions.limit.assert_called_once_with(200)


@pytest.mark.asyncio
async def test_get_chat_history_returns_newest_limit_chronologically() -> None:
    client = MagicMock()
    messages = MagicMock()
    query = MagicMock()
    limited_query = MagicMock()
    limited_query.stream.return_value = snapshot_stream_from(
        [
            {"role": "model", "text": "newest"},
            {"role": "user", "text": "older"},
        ]
    )
    session = client.collection.return_value.document.return_value
    session.get = AsyncMock(
        return_value=document_snapshot(
            exists=True,
            data={"project_id": "project-1", "user_id": "user-1"},
        )
    )
    session.collection.return_value = messages
    messages.order_by.return_value = query
    query.limit.return_value = limited_query

    history = await MemoryEngine(client).get_chat_history(
        "session-1",
        limit=20,
        user_id="user-1",
        project_id="project-1",
    )

    messages.order_by.assert_called_once_with(
        "timestamp",
        direction=firestore.Query.DESCENDING,
    )
    query.limit.assert_called_once_with(20)
    assert history == [
        {"role": "user", "text": "older"},
        {"role": "model", "text": "newest"},
    ]


@pytest.mark.asyncio
async def test_bounded_history_excludes_current_message_and_keeps_limit() -> None:
    client = MagicMock()
    messages = MagicMock()
    query = MagicMock()
    limited_query = MagicMock()
    current_id = "turn--digest--user"
    snapshots = [
        SimpleNamespace(
            id=current_id,
            to_dict=lambda: {"role": "user", "text": "current"},
        )
    ]
    snapshots.extend(
        SimpleNamespace(
            id=f"prior-{index}",
            to_dict=lambda index=index: {
                "role": "model",
                "text": f"prior-{index}",
            },
        )
        for index in range(20, 0, -1)
    )

    async def stream_snapshots():
        for item in snapshots:
            yield item

    limited_query.stream.return_value = stream_snapshots()
    session = client.collection.return_value.document.return_value
    session.get = AsyncMock(
        return_value=document_snapshot(
            exists=True,
            data={"project_id": "project-1", "user_id": "user-1"},
        )
    )
    session.collection.return_value = messages
    messages.order_by.return_value = query
    query.limit.return_value = limited_query

    history = await MemoryEngine(client).get_chat_history(
        "session-1",
        limit=20,
        user_id="user-1",
        project_id="project-1",
        exclude_message_id=current_id,
    )

    query.limit.assert_called_once_with(21)
    assert len(history) == 20
    assert [item["text"] for item in history] == [
        f"prior-{index}" for index in range(1, 21)
    ]
    assert all("id" not in item and "message_id" not in item for item in history)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_limit", (True, 0, 101, 1.5, "20"))
async def test_get_chat_history_rejects_invalid_limit_before_access(
    invalid_limit: object,
) -> None:
    client = MagicMock()

    with pytest.raises(ValueError):
        await MemoryEngine(client).get_chat_history(
            "session-1",
            limit=invalid_limit,
            user_id="user-1",
            project_id="project-1",
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_update_user_profile_merges_fields() -> None:
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    user.set = AsyncMock()
    client.collection.return_value = users
    users.document.return_value = user

    engine = MemoryEngine(client=client)
    await engine.update_user_profile("user-1", {"tone": "direct"})

    client.collection.assert_called_once_with("users")
    users.document.assert_called_once_with("user-1")
    user.set.assert_awaited_once_with({"tone": "direct"}, merge=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exists", "stored", "expected"),
    (
        (True, {"tone": "direct"}, {"tone": "direct"}),
        (False, None, {}),
    ),
)
async def test_get_user_profile_handles_existing_and_missing_documents(
    exists: bool,
    stored: dict[str, object] | None,
    expected: dict[str, object],
) -> None:
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    snapshot = SimpleNamespace(
        exists=exists,
        to_dict=lambda: stored,
    )
    user.get = AsyncMock(return_value=snapshot)
    client.collection.return_value = users
    users.document.return_value = user

    engine = MemoryEngine(client=client)
    assert await engine.get_user_profile("user-1") == expected


@pytest.mark.asyncio
async def test_invalid_inputs_fail_before_firestore_access() -> None:
    client = MagicMock()
    engine = MemoryEngine(client=client)
    invalid_calls = (
        (
            engine.save_message,
            ("", "user", "text"),
            {"project_id": "project-1", "user_id": "user-1"},
        ),
        (
            engine.save_message,
            ("session", " ", "text"),
            {"project_id": "project-1", "user_id": "user-1"},
        ),
        (
            engine.save_message,
            ("session", "user", " "),
            {"project_id": "project-1", "user_id": "user-1"},
        ),
        (
            engine.get_chat_history,
            (" ",),
            {"project_id": "project-1", "user_id": "user-1"},
        ),
        (engine.update_user_profile, ("", {"tone": "direct"}), {}),
        (engine.update_user_profile, ("user", {}), {}),
        (engine.get_user_profile, ("",), {}),
    )

    for operation, arguments, keywords in invalid_calls:
        with pytest.raises(ValueError):
            await operation(*arguments, **keywords)

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_firestore_errors_preserve_cause_and_hide_profile_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_value = "private profile content"
    firestore_error = ServiceUnavailable("backend unavailable")
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    user.set = AsyncMock(side_effect=firestore_error)
    client.collection.return_value = users
    users.document.return_value = user
    engine = MemoryEngine(client=client)
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await engine.update_user_profile(
            "private-user-id",
            {"note": private_value},
        )

    assert caught.value.__cause__ is firestore_error
    assert private_value not in caplog.text
    assert "private-user-id" not in caplog.text


def test_close_delegates_to_client() -> None:
    client = MagicMock()

    MemoryEngine(client=client).close()

    client.close.assert_called_once_with()
