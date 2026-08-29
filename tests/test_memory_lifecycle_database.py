import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore

from database import (
    MemoryEngine,
    MemoryEngineError,
    MemorySignalConflictError,
    MemorySignalNotFoundError,
)


NOW = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)
SIGNAL_ID = "response_length--proposal-1"
APPROVED_EVENT_ID = f"{SIGNAL_ID}--approved"
REVOKED_EVENT_ID = f"{SIGNAL_ID}--revoked"
V2_SIGNAL_ID = "development_environments--proposal-v2"
V2_APPROVED_EVENT_ID = f"{V2_SIGNAL_ID}--approved"
V2_REVOKED_EVENT_ID = f"{V2_SIGNAL_ID}--revoked"


def install_transaction_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    def run_without_sdk_retry(callback):
        async def run(transaction, *args, **kwargs):
            return await callback(transaction, *args, **kwargs)

        return run

    monkeypatch.setattr(
        "database.firestore.async_transactional",
        run_without_sdk_retry,
    )


def active_profile_document() -> dict[str, object]:
    return {
        "memory_schema_version": "1.0",
        "memory_revision": 1,
        "identity_context": {},
        "active_preferences": {
            "response_length": {
                "signal_id": SIGNAL_ID,
                "category": "response_length",
                "value": "concise",
                "policy_version": "1.0",
                "source_event_id": APPROVED_EVENT_ID,
                "approved_at": NOW,
            }
        },
        "legacy_field": "private-legacy-value",
    }


def approved_event_document() -> dict[str, object]:
    return {
        "event_type": "approved",
        "signal_id": SIGNAL_ID,
        "category": "response_length",
        "value": "concise",
        "policy_version": "1.0",
        "source_type": "explicit_user_feedback",
        "source_session_id": "source-session",
        "source_message_id": "source-message",
        "confirmation_channel": "memory_api",
        "confirmation_session_id": None,
        "confirmation_message_id": None,
        "related_signal_id": None,
        "memory_revision": 1,
        "created_at": NOW,
    }


def revoked_event_document() -> dict[str, object]:
    document = approved_event_document()
    document.update(
        {
            "event_type": "revoked",
            "confirmation_channel": "chat_decision",
            "confirmation_session_id": "confirmation-session",
            "confirmation_message_id": "confirmation-message",
            "memory_revision": 2,
        }
    )
    return document


def active_v2_profile_document() -> dict[str, object]:
    return {
        "memory_schema_version": "2.0",
        "memory_revision": 1,
        "identity_context": {},
        "active_preferences": {
            "development_environments": {
                "signal_id": V2_SIGNAL_ID,
                "category": "development_environments",
                "value": ["macos", "linux"],
                "policy_version": "2.0",
                "source_event_id": V2_APPROVED_EVENT_ID,
                "approved_at": NOW,
            }
        },
    }


def approved_v2_event_document() -> dict[str, object]:
    return {
        "event_type": "approved",
        "signal_id": V2_SIGNAL_ID,
        "category": "development_environments",
        "value": ["macos", "linux"],
        "policy_version": "2.0",
        "source_type": "explicit_user_feedback",
        "source_session_id": "source-session",
        "source_message_id": "source-message",
        "evidence_message_id": "source-message",
        "clarification_id": None,
        "confirmation_channel": "memory_api",
        "confirmation_session_id": None,
        "confirmation_message_id": None,
        "related_signal_id": None,
        "memory_revision": 1,
        "created_at": NOW,
    }


def lifecycle_store() -> tuple[
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    dict[str, MagicMock],
]:
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    proposals = MagicMock()
    events = MagicMock()
    event_refs: dict[str, MagicMock] = {}

    client.collection.return_value = users
    users.document.return_value = user
    user.collection.side_effect = (
        lambda name: proposals if name == "memory_proposals" else events
    )

    def event_document(event_id: str) -> MagicMock:
        if event_id not in event_refs:
            event_refs[event_id] = MagicMock(name=f"event-{event_id}")
        return event_refs[event_id]

    events.document.side_effect = event_document
    return client, user, proposals, events, event_refs


def configure_delete_state(
    *,
    profile_exists: bool,
    profile_document: dict[str, object] | None,
    proposal_document: dict[str, object] | None,
    event_documents: dict[str, dict[str, object]],
) -> tuple[
    MagicMock,
    MagicMock,
    MagicMock,
    dict[str, MagicMock],
    MagicMock,
]:
    client, user, proposals, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    proposal_ref = MagicMock()
    proposals.document.return_value = proposal_ref
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=profile_exists,
            to_dict=lambda: profile_document,
        )
    )
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=proposal_document is not None,
            to_dict=lambda: proposal_document,
        )
    )
    for suffix in ("approved", "corrected", "superseded", "revoked"):
        event_id = f"{SIGNAL_ID}--{suffix}"
        document = event_documents.get(suffix)
        event_ref = event_refs.setdefault(event_id, MagicMock())
        event_ref.get = AsyncMock(
            return_value=SimpleNamespace(
                exists=document is not None,
                to_dict=lambda document=document: document,
            )
        )
    return client, user, proposal_ref, event_refs, transaction


@pytest.mark.asyncio
async def test_revoke_memory_signal_atomically_revokes_active_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, proposals, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=active_profile_document,
        )
    )
    approved_ref = event_refs.setdefault(APPROVED_EVENT_ID, MagicMock())
    approved_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=approved_event_document,
        )
    )
    revoked_ref = event_refs.setdefault(REVOKED_EVENT_ID, MagicMock())
    revoked_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )

    result = await MemoryEngine(client).revoke_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
        confirmation_channel="chat_decision",
        confirmation_session_id="confirmation-session",
        confirmation_message_id="confirmation-message",
        observed_at=NOW,
    )

    assert result.profile.memory_revision == 2
    assert result.profile.active_preferences == {}
    assert result.event.event_id == REVOKED_EVENT_ID
    assert result.event.event_type == "revoked"
    assert result.event.signal_id == SIGNAL_ID
    assert result.event.value == "concise"
    assert result.event.source_session_id == "source-session"
    assert result.event.source_message_id == "source-message"
    assert result.event.confirmation_channel == "chat_decision"
    assert result.event.confirmation_session_id == "confirmation-session"
    assert result.event.confirmation_message_id == "confirmation-message"
    assert result.event.memory_revision == 2
    assert transaction.set.call_args_list == [
        call(
            revoked_ref,
            {
                "event_type": "revoked",
                "signal_id": SIGNAL_ID,
                "category": "response_length",
                "value": "concise",
                "policy_version": "1.0",
                "source_type": "explicit_user_feedback",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "confirmation_channel": "chat_decision",
                "confirmation_session_id": "confirmation-session",
                "confirmation_message_id": "confirmation-message",
                "related_signal_id": None,
                "memory_revision": 2,
                "created_at": firestore.SERVER_TIMESTAMP,
            },
        ),
        call(
            user,
            {
                "memory_schema_version": "1.0",
                "memory_revision": 2,
                "identity_context": {},
                "active_preferences": {},
                "memory_updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
    ]
    transaction.delete.assert_not_called()
    proposals.document.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_v2_memory_signal_preserves_v2_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, proposals, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=active_v2_profile_document,
        )
    )
    approved_ref = event_refs.setdefault(V2_APPROVED_EVENT_ID, MagicMock())
    approved_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=approved_v2_event_document,
        )
    )
    revoked_ref = event_refs.setdefault(V2_REVOKED_EVENT_ID, MagicMock())
    revoked_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )

    result = await MemoryEngine(client).revoke_memory_signal(
        "user-1",
        "development_environments",
        V2_SIGNAL_ID,
        confirmation_channel="memory_api",
        confirmation_session_id=None,
        confirmation_message_id=None,
        observed_at=NOW,
    )

    assert result.profile.memory_schema_version == "2.0"
    assert result.profile.memory_revision == 2
    assert result.profile.active_preferences == {}
    assert result.event.event_id == V2_REVOKED_EVENT_ID
    assert result.event.policy_version == "2.0"
    assert result.event.evidence_message_id == "source-message"
    assert result.event.clarification_id is None
    assert transaction.set.call_args_list[0] == call(
        revoked_ref,
        {
            "event_type": "revoked",
            "signal_id": V2_SIGNAL_ID,
            "category": "development_environments",
            "value": ["macos", "linux"],
            "policy_version": "2.0",
            "source_type": "explicit_user_feedback",
            "source_session_id": "source-session",
            "source_message_id": "source-message",
            "evidence_message_id": "source-message",
            "clarification_id": None,
            "confirmation_channel": "memory_api",
            "confirmation_session_id": None,
            "confirmation_message_id": None,
            "related_signal_id": None,
            "memory_revision": 2,
            "created_at": firestore.SERVER_TIMESTAMP,
        },
    )
    proposals.document.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_memory_signal_returns_existing_event_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, _, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "memory_schema_version": "1.0",
                "memory_revision": 3,
                "identity_context": {},
                "active_preferences": {},
            },
        )
    )
    revoked_ref = event_refs.setdefault(REVOKED_EVENT_ID, MagicMock())
    revoked_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=revoked_event_document,
        )
    )

    result = await MemoryEngine(client).revoke_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
        confirmation_channel="chat_decision",
        confirmation_session_id="confirmation-session",
        confirmation_message_id="confirmation-message",
        observed_at=NOW,
    )

    assert result.profile.memory_revision == 3
    assert result.event.event_id == REVOKED_EVENT_ID
    assert result.event.memory_revision == 2
    transaction.set.assert_not_called()
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_memory_signal_rejects_different_retry_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, _, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "memory_schema_version": "1.0",
                "memory_revision": 2,
                "identity_context": {},
                "active_preferences": {},
            },
        )
    )
    revoked_ref = event_refs.setdefault(REVOKED_EVENT_ID, MagicMock())
    revoked_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=revoked_event_document,
        )
    )

    with pytest.raises(MemorySignalConflictError):
        await MemoryEngine(client).revoke_memory_signal(
            "user-1",
            "response_length",
            SIGNAL_ID,
            confirmation_channel="chat_decision",
            confirmation_session_id="different-session",
            confirmation_message_id="different-message",
            observed_at=NOW,
        )

    transaction.set.assert_not_called()
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_memory_signal_returns_not_found_for_inactive_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, _, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "memory_schema_version": "1.0",
                "memory_revision": 2,
                "identity_context": {},
                "active_preferences": {},
            },
        )
    )
    revoked_ref = event_refs.setdefault(REVOKED_EVENT_ID, MagicMock())
    revoked_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )

    with pytest.raises(MemorySignalNotFoundError):
        await MemoryEngine(client).revoke_memory_signal(
            "user-1",
            "response_length",
            SIGNAL_ID,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=NOW,
        )

    transaction.set.assert_not_called()
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_memory_signal_reads_all_documents_before_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, _, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    operations: list[str] = []

    async def read_profile(*, transaction) -> SimpleNamespace:
        operations.append("read-profile")
        return SimpleNamespace(
            exists=True,
            to_dict=active_profile_document,
        )

    async def read_revoked(*, transaction) -> SimpleNamespace:
        operations.append("read-revoked")
        return SimpleNamespace(exists=False, to_dict=lambda: None)

    async def read_source(*, transaction) -> SimpleNamespace:
        operations.append("read-source")
        return SimpleNamespace(
            exists=True,
            to_dict=approved_event_document,
        )

    user.get = AsyncMock(side_effect=read_profile)
    revoked_ref = event_refs.setdefault(REVOKED_EVENT_ID, MagicMock())
    revoked_ref.get = AsyncMock(side_effect=read_revoked)
    source_ref = event_refs.setdefault(APPROVED_EVENT_ID, MagicMock())
    source_ref.get = AsyncMock(side_effect=read_source)
    transaction.set.side_effect = lambda *args, **kwargs: operations.append(
        "write"
    )

    await MemoryEngine(client).revoke_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
        confirmation_channel="memory_api",
        confirmation_session_id=None,
        confirmation_message_id=None,
        observed_at=NOW,
    )

    assert operations == [
        "read-profile",
        "read-revoked",
        "read-source",
        "write",
        "write",
    ]


@pytest.mark.asyncio
async def test_revoke_memory_signal_removes_orphaned_active_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, _, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=active_profile_document,
        )
    )
    revoked_ref = event_refs.setdefault(REVOKED_EVENT_ID, MagicMock())
    revoked_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    source_ref = event_refs.setdefault(APPROVED_EVENT_ID, MagicMock())
    source_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )

    result = await MemoryEngine(client).revoke_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
        confirmation_channel="memory_api",
        confirmation_session_id=None,
        confirmation_message_id=None,
        observed_at=NOW,
    )

    assert result.profile.memory_revision == 2
    assert result.profile.active_preferences == {}
    assert result.event is None
    transaction.set.assert_called_once_with(
        user,
        {
            "memory_schema_version": "1.0",
            "memory_revision": 2,
            "identity_context": {},
            "active_preferences": {},
            "memory_updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_memory_signal_deletes_removed_projection_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, _, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    retained_signal = {
        "signal_id": "planning_granularity--signal-1",
        "category": "planning_granularity",
        "value": "tasks",
        "policy_version": "1.0",
        "source_event_id": "planning_granularity--signal-1--approved",
        "approved_at": NOW,
    }
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                **active_profile_document(),
                "active_preferences": {
                    **active_profile_document()["active_preferences"],
                    "planning_granularity": retained_signal,
                },
            },
        )
    )
    revoked_ref = event_refs.setdefault(REVOKED_EVENT_ID, MagicMock())
    revoked_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    source_ref = event_refs.setdefault(APPROVED_EVENT_ID, MagicMock())
    source_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=approved_event_document,
        )
    )

    result = await MemoryEngine(client).revoke_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
        confirmation_channel="memory_api",
        confirmation_session_id=None,
        confirmation_message_id=None,
        observed_at=NOW,
    )

    assert "response_length" not in result.profile.active_preferences
    assert result.profile.active_preferences["planning_granularity"].value == (
        "tasks"
    )
    persisted_profile = transaction.set.call_args_list[1].args[1]
    assert (
        persisted_profile["active_preferences"]["response_length"]
        is firestore.DELETE_FIELD
    )
    assert (
        persisted_profile["active_preferences"]["planning_granularity"][
            "signal_id"
        ]
        == "planning_granularity--signal-1"
    )


@pytest.mark.asyncio
async def test_revoke_memory_signal_fails_closed_for_active_revoked_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, _, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=active_profile_document,
        )
    )
    revoked_ref = event_refs.setdefault(REVOKED_EVENT_ID, MagicMock())
    revoked_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=revoked_event_document,
        )
    )

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).revoke_memory_signal(
            "user-1",
            "response_length",
            SIGNAL_ID,
            confirmation_channel="chat_decision",
            confirmation_session_id="confirmation-session",
            confirmation_message_id="confirmation-message",
            observed_at=NOW,
        )

    assert isinstance(caught.value.__cause__, ValueError)
    transaction.set.assert_not_called()
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_memory_signal_fails_closed_for_mismatched_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, _, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=active_profile_document,
        )
    )
    revoked_ref = event_refs.setdefault(REVOKED_EVENT_ID, MagicMock())
    revoked_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    mismatched_source = approved_event_document()
    mismatched_source["value"] = "detailed"
    source_ref = event_refs.setdefault(APPROVED_EVENT_ID, MagicMock())
    source_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: mismatched_source,
        )
    )

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).revoke_memory_signal(
            "user-1",
            "response_length",
            SIGNAL_ID,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=NOW,
        )

    assert isinstance(caught.value.__cause__, ValueError)
    transaction.set.assert_not_called()
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_memory_signal_removes_owned_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, proposals, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    proposal_ref = MagicMock()
    proposals.document.return_value = proposal_ref
    operations: list[str] = []

    async def read_profile(*, transaction) -> SimpleNamespace:
        operations.append("read-profile")
        return SimpleNamespace(
            exists=True,
            to_dict=active_profile_document,
        )

    async def read_proposal(*, transaction) -> SimpleNamespace:
        operations.append("read-proposal")
        return SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "proposal_id": SIGNAL_ID,
                "category": "response_length",
                "proposed_value": "concise",
                "expected_signal_id": None,
                "policy_version": "1.0",
                "status": "approved",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "created_at": NOW,
                "expires_at": NOW,
                "resolved_at": NOW,
            },
        )

    user.get = AsyncMock(side_effect=read_profile)
    proposal_ref.get = AsyncMock(side_effect=read_proposal)
    for suffix in ("approved", "corrected", "superseded", "revoked"):
        event_id = f"{SIGNAL_ID}--{suffix}"
        event_ref = event_refs.setdefault(event_id, MagicMock())

        async def read_event(
            *,
            transaction,
            suffix=suffix,
        ) -> SimpleNamespace:
            operations.append(f"read-{suffix}")
            if suffix == "approved":
                return SimpleNamespace(
                    exists=True,
                    to_dict=approved_event_document,
                )
            return SimpleNamespace(exists=False, to_dict=lambda: None)

        event_ref.get = AsyncMock(side_effect=read_event)

    transaction.set.side_effect = lambda *args, **kwargs: operations.append(
        "write"
    )
    transaction.delete.side_effect = lambda *args: operations.append(
        "delete"
    )

    result = await MemoryEngine(client).delete_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
    )

    assert result.profile.memory_revision == 2
    assert result.profile.active_preferences == {}
    assert result.artifacts_deleted is True
    assert operations == [
        "read-profile",
        "read-proposal",
        "read-approved",
        "read-corrected",
        "read-superseded",
        "read-revoked",
        "write",
        "delete",
        "delete",
    ]
    transaction.set.assert_called_once_with(
        user,
        {
            "memory_schema_version": "1.0",
            "memory_revision": 2,
            "identity_context": {},
            "active_preferences": {},
            "memory_updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    assert transaction.delete.call_args_list == [
        call(proposal_ref),
        call(event_refs[APPROVED_EVENT_ID]),
    ]


@pytest.mark.asyncio
async def test_delete_v2_memory_signal_removes_versioned_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    origin_id = "354190760312f71edeae96c0d3372634"
    signal_id = f"development_environments--{origin_id}"
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    proposals = MagicMock()
    proposal_ref = MagicMock(name="proposal")
    origins = MagicMock()
    origin_ref = MagicMock(name="origin")
    events = MagicMock()
    event_refs: dict[str, MagicMock] = {}
    transaction = MagicMock()
    client.collection.return_value = users
    users.document.return_value = user
    client.transaction.return_value = transaction
    user.collection.side_effect = lambda name: {
        "memory_proposals": proposals,
        "memory_proposal_origins": origins,
        "memory_events": events,
    }[name]
    proposals.document.return_value = proposal_ref
    origins.document.return_value = origin_ref

    def event_document(event_id: str) -> MagicMock:
        return event_refs.setdefault(event_id, MagicMock(name=event_id))

    events.document.side_effect = event_document
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "memory_schema_version": "2.0",
                "memory_revision": 1,
                "identity_context": {},
                "active_preferences": {
                    "development_environments": {
                        "signal_id": signal_id,
                        "category": "development_environments",
                        "value": ["macos", "linux"],
                        "policy_version": "2.0",
                        "source_event_id": f"{signal_id}--approved",
                        "approved_at": NOW,
                    }
                },
            },
        )
    )
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "proposal_id": signal_id,
                "category": "development_environments",
                "proposed_value": ["macos", "linux"],
                "expected_signal_id": None,
                "policy_version": "2.0",
                "status": "approved",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "evidence_message_id": "source-message",
                "clarification_id": None,
                "created_at": NOW,
                "expires_at": NOW,
                "resolved_at": NOW,
            },
        )
    )
    origin_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "schema_version": "2.0",
                "proposal_id": signal_id,
                "category": "development_environments",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "evidence_message_id": "source-message",
                "clarification_id": None,
                "created_at": NOW,
            },
        )
    )
    for event_type in ("approved", "corrected", "superseded", "revoked"):
        event_id = f"{signal_id}--{event_type}"
        event_ref = event_document(event_id)
        event_ref.get = AsyncMock(
            return_value=SimpleNamespace(
                exists=event_type == "approved",
                to_dict=(
                    lambda event_type=event_type: {
                        **approved_v2_event_document(),
                        "signal_id": signal_id,
                    }
                    if event_type == "approved"
                    else None
                ),
            )
        )

    result = await MemoryEngine(client).delete_memory_signal(
        "user-1",
        "development_environments",
        signal_id,
    )

    assert result.artifacts_deleted is True
    assert result.profile.memory_schema_version == "2.0"
    assert result.profile.memory_revision == 2
    assert result.profile.active_preferences == {}
    assert transaction.delete.call_args_list == [
        call(proposal_ref),
        call(origin_ref),
        call(event_refs[f"{signal_id}--approved"]),
    ]


@pytest.mark.asyncio
async def test_delete_memory_signal_removes_owned_proposal_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    origin_id = "e82366f7699ee2e39bff6a68154e09b7"
    signal_id = f"response_length--{origin_id}"
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    proposals = MagicMock()
    proposal_ref = MagicMock(name="proposal")
    origins = MagicMock()
    origin_ref = MagicMock(name="origin")
    events = MagicMock()
    transaction = MagicMock()
    operations: list[str] = []

    client.collection.return_value = users
    client.transaction.return_value = transaction
    users.document.return_value = user
    proposals.document.return_value = proposal_ref
    origins.document.return_value = origin_ref
    user.collection.side_effect = lambda name: {
        "memory_proposals": proposals,
        "memory_proposal_origins": origins,
        "memory_events": events,
    }[name]

    async def read_profile(*, transaction) -> SimpleNamespace:
        operations.append("read-profile")
        return SimpleNamespace(exists=False, to_dict=lambda: None)

    async def read_proposal(*, transaction) -> SimpleNamespace:
        operations.append("read-proposal")
        return SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "proposal_id": signal_id,
                "category": "response_length",
                "proposed_value": "concise",
                "expected_signal_id": None,
                "policy_version": "1.0",
                "status": "approved",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "created_at": NOW,
                "expires_at": NOW,
                "resolved_at": NOW,
            },
        )

    async def read_origin(*, transaction) -> SimpleNamespace:
        operations.append("read-origin")
        return SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "schema_version": "1.0",
                "proposal_id": signal_id,
                "category": "response_length",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "created_at": NOW,
            },
        )

    user.get = AsyncMock(side_effect=read_profile)
    proposal_ref.get = AsyncMock(side_effect=read_proposal)
    origin_ref.get = AsyncMock(side_effect=read_origin)
    event_refs: dict[str, MagicMock] = {}

    def event_document(event_id: str) -> MagicMock:
        if event_id not in event_refs:
            suffix = event_id.rsplit("--", maxsplit=1)[-1]
            event_ref = MagicMock(name=f"event-{suffix}")

            async def read_event(*, transaction, suffix=suffix):
                operations.append(f"read-{suffix}")
                return SimpleNamespace(exists=False, to_dict=lambda: None)

            event_ref.get = AsyncMock(side_effect=read_event)
            event_refs[event_id] = event_ref
        return event_refs[event_id]

    events.document.side_effect = event_document
    transaction.set.side_effect = lambda *args, **kwargs: operations.append(
        "write"
    )
    transaction.delete.side_effect = lambda *args: operations.append(
        "delete"
    )

    result = await MemoryEngine(client).delete_memory_signal(
        "user-1",
        "response_length",
        signal_id,
    )

    assert result.artifacts_deleted is True
    assert operations == [
        "read-profile",
        "read-proposal",
        "read-origin",
        "read-approved",
        "read-corrected",
        "read-superseded",
        "read-revoked",
        "write",
        "delete",
        "delete",
    ]
    assert transaction.delete.call_args_list == [
        call(proposal_ref),
        call(origin_ref),
    ]


@pytest.mark.asyncio
async def test_delete_memory_signal_removes_inactive_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    revoked_document = revoked_event_document()
    client, user, proposal_ref, event_refs, transaction = (
        configure_delete_state(
            profile_exists=True,
            profile_document={
                "memory_schema_version": "1.0",
                "memory_revision": 2,
                "identity_context": {},
                "active_preferences": {},
            },
            proposal_document=None,
            event_documents={
                "approved": approved_event_document(),
                "revoked": revoked_document,
            },
        )
    )

    result = await MemoryEngine(client).delete_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
    )

    assert result.profile.memory_revision == 3
    assert result.artifacts_deleted is True
    transaction.set.assert_called_once()
    assert transaction.delete.call_args_list == [
        call(event_refs[APPROVED_EVENT_ID]),
        call(event_refs[REVOKED_EVENT_ID]),
    ]
    proposal_ref.get.assert_awaited_once_with(transaction=transaction)
    user.get.assert_awaited_once_with(transaction=transaction)


@pytest.mark.asyncio
async def test_delete_memory_signal_creates_revision_root_for_orphan_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, _, event_refs, transaction = configure_delete_state(
        profile_exists=False,
        profile_document=None,
        proposal_document=None,
        event_documents={"approved": approved_event_document()},
    )

    result = await MemoryEngine(client).delete_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
    )

    assert result.profile.memory_revision == 1
    assert result.profile.active_preferences == {}
    assert result.artifacts_deleted is True
    transaction.set.assert_called_once_with(
        user,
        {
            "memory_schema_version": "1.0",
            "memory_revision": 1,
            "identity_context": {},
            "active_preferences": {},
            "memory_updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    transaction.delete.assert_called_once_with(
        event_refs[APPROVED_EVENT_ID]
    )


@pytest.mark.asyncio
async def test_delete_memory_signal_deletes_removed_projection_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    retained_signal = {
        "signal_id": "planning_granularity--signal-1",
        "category": "planning_granularity",
        "value": "tasks",
        "policy_version": "1.0",
        "source_event_id": "planning_granularity--signal-1--approved",
        "approved_at": NOW,
    }
    client, _, _, _, transaction = configure_delete_state(
        profile_exists=True,
        profile_document={
            **active_profile_document(),
            "active_preferences": {
                **active_profile_document()["active_preferences"],
                "planning_granularity": retained_signal,
            },
        },
        proposal_document=None,
        event_documents={"approved": approved_event_document()},
    )

    result = await MemoryEngine(client).delete_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
    )

    assert "response_length" not in result.profile.active_preferences
    assert result.profile.active_preferences["planning_granularity"].value == (
        "tasks"
    )
    persisted_profile = transaction.set.call_args.args[1]
    assert (
        persisted_profile["active_preferences"]["response_length"]
        is firestore.DELETE_FIELD
    )
    assert (
        persisted_profile["active_preferences"]["planning_granularity"][
            "signal_id"
        ]
        == "planning_granularity--signal-1"
    )


@pytest.mark.asyncio
async def test_delete_memory_signal_is_idempotent_when_artifacts_are_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, _, _, transaction = configure_delete_state(
        profile_exists=True,
        profile_document={
            "memory_schema_version": "1.0",
            "memory_revision": 3,
            "identity_context": {},
            "active_preferences": {},
        },
        proposal_document=None,
        event_documents={},
    )

    result = await MemoryEngine(client).delete_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
    )

    assert result.profile.memory_revision == 3
    assert result.artifacts_deleted is False
    transaction.set.assert_not_called()
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_memory_signal_preserves_newer_projection_and_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    newer_signal_id = "response_length--proposal-2"
    newer_approved_at = datetime(2026, 8, 20, 19, 0, tzinfo=UTC)
    newer_proposal = {
        "proposal_id": newer_signal_id,
        "category": "response_length",
        "proposed_value": "detailed",
        "expected_signal_id": SIGNAL_ID,
        "policy_version": "1.0",
        "status": "approved",
        "source_session_id": "new-source-session",
        "source_message_id": "new-source-message",
        "created_at": NOW,
        "expires_at": NOW,
    }
    client, user, proposal_ref, event_refs, transaction = (
        configure_delete_state(
            profile_exists=True,
            profile_document={
                "memory_schema_version": "1.0",
                "memory_revision": 2,
                "identity_context": {},
                "active_preferences": {
                    "response_length": {
                        "signal_id": newer_signal_id,
                        "category": "response_length",
                        "value": "detailed",
                        "policy_version": "1.0",
                        "source_event_id": (
                            f"{newer_signal_id}--corrected"
                        ),
                        "approved_at": newer_approved_at,
                    }
                },
            },
            proposal_document=newer_proposal,
            event_documents={"approved": approved_event_document()},
        )
    )

    result = await MemoryEngine(client).delete_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
    )

    active = result.profile.active_preferences["response_length"]
    assert active.signal_id == newer_signal_id
    assert active.approved_at == newer_approved_at
    persisted_profile = transaction.set.call_args.args[1]
    persisted_active = persisted_profile["active_preferences"][
        "response_length"
    ]
    assert persisted_active["signal_id"] == newer_signal_id
    assert persisted_active["approved_at"] == newer_approved_at
    proposal_ref.get.assert_awaited_once_with(transaction=transaction)
    assert call(proposal_ref) not in transaction.delete.call_args_list
    assert transaction.delete.call_args_list == [
        call(event_refs[APPROVED_EVENT_ID])
    ]


@pytest.mark.asyncio
async def test_delete_memory_signal_fails_closed_for_mismatched_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    mismatched = approved_event_document()
    mismatched["signal_id"] = "response_length--different-signal"
    client, _, _, _, transaction = configure_delete_state(
        profile_exists=True,
        profile_document={
            "memory_schema_version": "1.0",
            "memory_revision": 2,
            "identity_context": {},
            "active_preferences": {},
        },
        proposal_document=None,
        event_documents={"approved": mismatched},
    )

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).delete_memory_signal(
            "user-1",
            "response_length",
            SIGNAL_ID,
        )

    assert isinstance(caught.value.__cause__, ValueError)
    transaction.set.assert_not_called()
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_memory_signal_uses_bounded_target_paths_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    superseded = approved_event_document()
    superseded.update(
        {
            "event_type": "superseded",
            "related_signal_id": "response_length--proposal-2",
            "memory_revision": 2,
        }
    )
    client, _, _, event_refs, transaction = configure_delete_state(
        profile_exists=True,
        profile_document={
            "memory_schema_version": "1.0",
            "memory_revision": 2,
            "identity_context": {},
            "active_preferences": {},
        },
        proposal_document=None,
        event_documents={"superseded": superseded},
    )
    events = client.collection.return_value.document.return_value.collection(
        "memory_events"
    )

    result = await MemoryEngine(client).delete_memory_signal(
        "user-1",
        "response_length",
        SIGNAL_ID,
    )

    assert result.artifacts_deleted is True
    requested_event_ids = [
        invocation.args[0] for invocation in events.document.call_args_list
    ]
    assert requested_event_ids == [
        f"{SIGNAL_ID}--approved",
        f"{SIGNAL_ID}--corrected",
        f"{SIGNAL_ID}--superseded",
        f"{SIGNAL_ID}--revoked",
    ]
    assert "response_length--proposal-2--corrected" not in requested_event_ids
    transaction.delete.assert_called_once_with(
        event_refs[f"{SIGNAL_ID}--superseded"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "category", "signal_id"),
    (
        ("has/slash", "response_length", SIGNAL_ID),
        ("user-1", "unknown", SIGNAL_ID),
        ("user-1", "response_length", "formatting_style--proposal-1"),
        (
            "user-1",
            "response_length",
            f"response_length--{'x' * 105}",
        ),
    ),
)
async def test_memory_signal_mutations_reject_invalid_locator_before_access(
    user_id: str,
    category: str,
    signal_id: str,
) -> None:
    for operation in ("revoke", "delete"):
        client = MagicMock()
        engine = MemoryEngine(client)

        with pytest.raises(ValueError):
            if operation == "revoke":
                await engine.revoke_memory_signal(
                    user_id,
                    category,
                    signal_id,
                    confirmation_channel="memory_api",
                    confirmation_session_id=None,
                    confirmation_message_id=None,
                    observed_at=NOW,
                )
            else:
                await engine.delete_memory_signal(
                    user_id,
                    category,
                    signal_id,
                )

        client.collection.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "expected_message"),
    (
        (
            "revoke",
            "Firestore revoke_memory_signal operation failed.",
        ),
        (
            "delete",
            "Firestore delete_memory_signal operation failed.",
        ),
    ),
)
async def test_memory_signal_mutations_preserve_firestore_error_and_log_safely(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    operation: str,
    expected_message: str,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, proposals, _, event_refs = lifecycle_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    firestore_error = ServiceUnavailable("private-backend-detail")
    user.get = AsyncMock(side_effect=firestore_error)
    proposal_ref = MagicMock()
    proposals.document.return_value = proposal_ref
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    for suffix in ("approved", "corrected", "superseded", "revoked"):
        event_ref = event_refs.setdefault(
            f"{SIGNAL_ID}--{suffix}",
            MagicMock(),
        )
        event_ref.get = AsyncMock(
            return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
        )
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        if operation == "revoke":
            await MemoryEngine(client).revoke_memory_signal(
                "private-user-id",
                "response_length",
                SIGNAL_ID,
                confirmation_channel="chat_decision",
                confirmation_session_id="private-confirmation-session",
                confirmation_message_id="private-confirmation-message",
                observed_at=NOW,
            )
        else:
            await MemoryEngine(client).delete_memory_signal(
                "private-user-id",
                "response_length",
                SIGNAL_ID,
            )

    assert caught.value.__cause__ is firestore_error
    assert str(caught.value) == expected_message
    for private_value in (
        "private-user-id",
        SIGNAL_ID,
        "concise",
        "private-confirmation-session",
        "private-confirmation-message",
        "private-backend-detail",
    ):
        assert private_value not in caplog.text
