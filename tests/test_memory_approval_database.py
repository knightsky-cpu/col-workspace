import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore

from database import (
    MemoryEngine,
    MemoryEngineError,
    MemoryProposalConflictError,
    MemoryProposalExpiredError,
    MemoryProposalNotFoundError,
)
from schemas import ActiveMemorySignal, CollaborationProfile, MemoryProposal


NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


def install_transaction_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    def run_without_sdk_retry(callback):
        async def run(transaction, *args, **kwargs):
            return await callback(transaction, *args, **kwargs)

        return run

    monkeypatch.setattr(
        "database.firestore.async_transactional",
        run_without_sdk_retry,
    )


def pending_proposal_document(
    *,
    proposal_id: str = "response_length--proposal-1",
    category: str = "response_length",
    value: object = "concise",
    expected_signal_id: str | None = None,
    status: str = "pending",
    source_session_id: str = "source-session",
    source_message_id: str = "source-message",
) -> dict[str, object]:
    return {
        "proposal_id": proposal_id,
        "category": category,
        "proposed_value": value,
        "expected_signal_id": expected_signal_id,
        "policy_version": "1.0",
        "status": status,
        "source_session_id": source_session_id,
        "source_message_id": source_message_id,
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=24),
        "resolved_at": None,
    }


def pending_v2_proposal_document(
    *,
    proposal_id: str = "development_environments--proposal-v2",
    value: object = ("linux", "macos"),
    expected_signal_id: str | None = None,
    status: str = "pending",
) -> dict[str, object]:
    return {
        "proposal_id": proposal_id,
        "category": "development_environments",
        "proposed_value": list(value) if isinstance(value, tuple) else value,
        "expected_signal_id": expected_signal_id,
        "policy_version": "2.0",
        "status": status,
        "source_session_id": "source-session",
        "source_message_id": "source-message",
        "evidence_message_id": "source-message",
        "clarification_id": None,
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=24),
        "resolved_at": None,
    }


def active_signal_document(
    *,
    signal_id: str = "response_length--proposal-1",
    value: str = "concise",
    source_event_id: str = "response_length--proposal-1--approved",
    approved_at: datetime = NOW,
) -> dict[str, object]:
    return {
        "signal_id": signal_id,
        "category": "response_length",
        "value": value,
        "policy_version": "1.0",
        "source_event_id": source_event_id,
        "approved_at": approved_at,
    }


def governed_profile_document(
    *,
    revision: int = 1,
    signal: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "memory_schema_version": "1.0",
        "memory_revision": revision,
        "identity_context": {},
        "active_preferences": {
            "response_length": signal or active_signal_document()
        },
        "legacy_field": "private-legacy-value",
    }


def governed_v2_profile_document() -> dict[str, object]:
    signal_id = "development_environments--proposal-v1"
    return {
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
    }


def lifecycle_event_document(
    *,
    event_type: str = "approved",
    signal_id: str = "response_length--proposal-1",
    value: str = "concise",
    related_signal_id: str | None = None,
    revision: int = 1,
    source_session_id: str = "source-session",
    source_message_id: str = "source-message",
    confirmation_session_id: str | None = "confirmation-session",
    confirmation_message_id: str | None = "confirmation-message",
    created_at: datetime = NOW,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "signal_id": signal_id,
        "category": "response_length",
        "value": value,
        "policy_version": "1.0",
        "source_type": "explicit_user_feedback",
        "source_session_id": source_session_id,
        "source_message_id": source_message_id,
        "confirmation_channel": "chat_decision",
        "confirmation_session_id": confirmation_session_id,
        "confirmation_message_id": confirmation_message_id,
        "related_signal_id": related_signal_id,
        "memory_revision": revision,
        "created_at": created_at,
    }


def v2_lifecycle_event_document() -> dict[str, object]:
    return {
        "event_type": "approved",
        "signal_id": "development_environments--proposal-v1",
        "category": "development_environments",
        "value": ["macos", "linux"],
        "policy_version": "2.0",
        "source_type": "explicit_user_feedback",
        "source_session_id": "source-session",
        "source_message_id": "source-message",
        "evidence_message_id": "source-message",
        "clarification_id": None,
        "confirmation_channel": "chat_decision",
        "confirmation_session_id": "confirmation-session",
        "confirmation_message_id": "confirmation-message",
        "related_signal_id": None,
        "memory_revision": 1,
        "created_at": NOW,
    }


def approval_store() -> tuple[
    MagicMock,
    MagicMock,
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
    proposal_ref = MagicMock()
    events = MagicMock()
    event_refs: dict[str, MagicMock] = {}

    client.collection.return_value = users
    users.document.return_value = user

    def user_collection(name: str) -> MagicMock:
        return proposals if name == "memory_proposals" else events

    def event_document(event_id: str) -> MagicMock:
        if event_id not in event_refs:
            event_refs[event_id] = MagicMock(name=f"event-{event_id}")
        return event_refs[event_id]

    user.collection.side_effect = user_collection
    proposals.document.return_value = proposal_ref
    events.document.side_effect = event_document
    return client, users, user, proposals, proposal_ref, events, event_refs


def profile_store() -> tuple[MagicMock, MagicMock, MagicMock]:
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    client.collection.return_value = users
    users.document.return_value = user
    return client, users, user


@pytest.mark.asyncio
async def test_get_collaboration_profile_returns_empty_versioned_profile_when_absent(
) -> None:
    client, users, user = profile_store()
    user.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )

    result = await MemoryEngine(client).get_collaboration_profile("user-1")

    assert result == CollaborationProfile()
    client.collection.assert_called_once_with("users")
    users.document.assert_called_once_with("user-1")
    user.get.assert_awaited_once_with()
    user.set.assert_not_called()
    user.update.assert_not_called()
    client.batch.assert_not_called()
    client.transaction.assert_not_called()


@pytest.mark.asyncio
async def test_get_collaboration_profile_excludes_legacy_fields() -> None:
    client, _, user = profile_store()
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "display_name": "private-legacy-name",
                "arbitrary_preference": "private-legacy-value",
            },
        )
    )

    result = await MemoryEngine(client).get_collaboration_profile("user-1")

    assert result == CollaborationProfile()
    user.set.assert_not_called()
    user.update.assert_not_called()


@pytest.mark.asyncio
async def test_get_collaboration_profile_returns_only_governed_signals() -> None:
    client, _, user = profile_store()
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "memory_schema_version": "1.0",
                "memory_revision": 1,
                "identity_context": {},
                "active_preferences": {
                    "response_length": {
                        "signal_id": "response_length--proposal-1",
                        "category": "response_length",
                        "value": "concise",
                        "policy_version": "1.0",
                        "source_event_id": (
                            "response_length--proposal-1--approved"
                        ),
                        "approved_at": NOW,
                    }
                },
                "display_name": "private-legacy-name",
            },
        )
    )

    result = await MemoryEngine(client).get_collaboration_profile("user-1")

    signal = result.active_preferences["response_length"]
    assert isinstance(signal, ActiveMemorySignal)
    assert signal.value == "concise"
    assert result.memory_revision == 1
    assert "display_name" not in result.model_dump()
    user.set.assert_not_called()
    user.update.assert_not_called()


@pytest.mark.asyncio
async def test_get_collaboration_profile_returns_v2_profile() -> None:
    client, _, user = profile_store()
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=governed_v2_profile_document,
        )
    )

    result = await MemoryEngine(client).get_collaboration_profile("user-1")

    assert result.memory_schema_version == "2.0"
    signal = result.active_preferences["development_environments"]
    assert signal.policy_version == "2.0"
    assert signal.value == ["macos", "linux"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "document",
    (
        {
            "memory_schema_version": "1.0",
            "memory_revision": 1,
            "identity_context": {},
            "active_preferences": {
                "response_length": {
                    "signal_id": "response_length--proposal-1",
                    "category": "formatting_style",
                    "value": "bullets",
                    "policy_version": "1.0",
                    "source_event_id": (
                        "response_length--proposal-1--approved"
                    ),
                    "approved_at": NOW,
                }
            },
        },
        {
            "memory_schema_version": "1.0",
            "memory_revision": 1,
            "identity_context": {},
            "active_preferences": {
                "response_length": {"category": "response_length"}
            },
        },
    ),
)
async def test_get_collaboration_profile_rejects_malformed_governed_data_safely(
    document: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _, user = profile_store()
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: document,
        )
    )
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).get_collaboration_profile("private-user-id")

    assert isinstance(caught.value.__cause__, ValueError)
    assert "private-user-id" not in caplog.text
    assert "concise" not in caplog.text


@pytest.mark.asyncio
async def test_get_collaboration_profile_preserves_firestore_error_safely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _, user = profile_store()
    firestore_error = ServiceUnavailable("private-backend-detail")
    user.get = AsyncMock(side_effect=firestore_error)
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).get_collaboration_profile("private-user-id")

    assert caught.value.__cause__ is firestore_error
    assert str(caught.value) == (
        "Firestore get_collaboration_profile operation failed."
    )
    assert "private-user-id" not in caplog.text
    assert "private-backend-detail" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", ("", "has/slash", "x" * 129))
async def test_get_collaboration_profile_rejects_invalid_user_before_access(
    user_id: str,
) -> None:
    client = MagicMock()

    with pytest.raises(ValueError):
        await MemoryEngine(client).get_collaboration_profile(user_id)

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_atomically_creates_event_and_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    (
        client,
        _,
        user,
        _,
        proposal_ref,
        _,
        event_refs,
    ) = approval_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=pending_proposal_document,
        )
    )
    user.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    approved_event_id = "response_length--proposal-1--approved"
    corrected_event_id = "response_length--proposal-1--corrected"
    for event_id in (approved_event_id, corrected_event_id):
        event_refs.setdefault(event_id, MagicMock())
        event_refs[event_id].get = AsyncMock(
            return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
        )

    result = await MemoryEngine(client).approve_memory_proposal(
        "user-1",
        "response_length",
        "response_length--proposal-1",
        confirmation_channel="chat_decision",
        confirmation_session_id="confirmation-session",
        confirmation_message_id="confirmation-message",
        observed_at=NOW,
    )

    assert result.profile.memory_revision == 1
    assert result.event.event_id == approved_event_id
    assert result.event.event_type == "approved"
    assert result.event.created_at == NOW
    assert result.superseded_event is None
    signal = result.profile.active_preferences["response_length"]
    assert signal.signal_id == "response_length--proposal-1"
    assert signal.source_event_id == approved_event_id
    assert signal.approved_at == NOW
    assert transaction.set.call_args_list == [
        call(
            event_refs[approved_event_id],
            {
                "event_type": "approved",
                "signal_id": "response_length--proposal-1",
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
                "memory_revision": 1,
                "created_at": firestore.SERVER_TIMESTAMP,
            },
        ),
        call(
            user,
            {
                "memory_schema_version": "1.0",
                "memory_revision": 1,
                "identity_context": {},
                "active_preferences": {
                    "response_length": {
                        "signal_id": "response_length--proposal-1",
                        "category": "response_length",
                        "value": "concise",
                        "policy_version": "1.0",
                        "source_event_id": approved_event_id,
                        "approved_at": firestore.SERVER_TIMESTAMP,
                    }
                },
                "memory_updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
        call(
            proposal_ref,
            {
                "status": "approved",
                "resolved_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
    ]


@pytest.mark.asyncio
async def test_approve_v2_memory_proposal_creates_v2_event_and_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, user, _, proposal_ref, _, event_refs = approval_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    proposal_id = "development_environments--proposal-v2"
    approved_event_id = f"{proposal_id}--approved"
    corrected_event_id = f"{proposal_id}--corrected"
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=pending_v2_proposal_document,
        )
    )
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=False,
            to_dict=lambda: None,
        )
    )
    for event_id in (approved_event_id, corrected_event_id):
        event_refs.setdefault(event_id, MagicMock())
        event_refs[event_id].get = AsyncMock(
            return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
        )

    result = await MemoryEngine(client).approve_memory_proposal(
        "user-1",
        "development_environments",
        proposal_id,
        confirmation_channel="chat_decision",
        confirmation_session_id="confirmation-session",
        confirmation_message_id="confirmation-message",
        observed_at=NOW,
    )

    assert result.profile.memory_schema_version == "2.0"
    signal = result.profile.active_preferences["development_environments"]
    assert signal.policy_version == "2.0"
    assert signal.value == ["macos", "linux"]
    assert result.event.policy_version == "2.0"
    assert result.event.evidence_message_id == "source-message"
    assert result.event.clarification_id is None
    assert transaction.set.call_args_list[0] == call(
        event_refs[approved_event_id],
        {
            "event_type": "approved",
            "signal_id": proposal_id,
            "category": "development_environments",
            "value": ["macos", "linux"],
            "policy_version": "2.0",
            "source_type": "explicit_user_feedback",
            "source_session_id": "source-session",
            "source_message_id": "source-message",
            "evidence_message_id": "source-message",
            "clarification_id": None,
            "confirmation_channel": "chat_decision",
            "confirmation_session_id": "confirmation-session",
            "confirmation_message_id": "confirmation-message",
            "related_signal_id": None,
            "memory_revision": 1,
            "created_at": firestore.SERVER_TIMESTAMP,
        },
    )


@pytest.mark.asyncio
async def test_approve_memory_proposal_reads_every_document_before_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, user, _, proposal_ref, _, event_refs = approval_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    operations: list[str] = []

    async def read_proposal(*, transaction) -> SimpleNamespace:
        operations.append("read-proposal")
        return SimpleNamespace(
            exists=True,
            to_dict=pending_proposal_document,
        )

    async def read_profile(*, transaction) -> SimpleNamespace:
        operations.append("read-profile")
        return SimpleNamespace(exists=False, to_dict=lambda: None)

    proposal_ref.get = AsyncMock(side_effect=read_proposal)
    user.get = AsyncMock(side_effect=read_profile)
    for event_id, operation in (
        ("response_length--proposal-1--approved", "read-approved"),
        ("response_length--proposal-1--corrected", "read-corrected"),
    ):
        event_ref = MagicMock()

        async def read_event(*, transaction, operation=operation):
            operations.append(operation)
            return SimpleNamespace(exists=False, to_dict=lambda: None)

        event_ref.get = AsyncMock(side_effect=read_event)
        event_refs[event_id] = event_ref

    transaction.set.side_effect = lambda *args, **kwargs: operations.append(
        "write"
    )

    await MemoryEngine(client).approve_memory_proposal(
        "user-1",
        "response_length",
        "response_length--proposal-1",
        confirmation_channel="chat_decision",
        confirmation_session_id="confirmation-session",
        confirmation_message_id="confirmation-message",
        observed_at=NOW,
    )

    assert operations == [
        "read-proposal",
        "read-profile",
        "read-approved",
        "read-corrected",
        "write",
        "write",
        "write",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("category", "proposal_id", "value", "expected_map"),
    (
        (
            "response_length",
            "response_length--proposal-1",
            "concise",
            "active_preferences",
        ),
        (
            "preferred_name",
            "preferred_name--proposal-1",
            "Avery",
            "identity_context",
        ),
    ),
)
async def test_approve_memory_proposal_routes_category_to_governed_map(
    monkeypatch: pytest.MonkeyPatch,
    category: str,
    proposal_id: str,
    value: str,
    expected_map: str,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, user, _, proposal_ref, _, event_refs = approval_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: pending_proposal_document(
                proposal_id=proposal_id,
                category=category,
                value=value,
            ),
        )
    )
    user.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    for suffix in ("approved", "corrected"):
        event_id = f"{proposal_id}--{suffix}"
        event_ref = MagicMock()
        event_ref.get = AsyncMock(
            return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
        )
        event_refs[event_id] = event_ref

    result = await MemoryEngine(client).approve_memory_proposal(
        "user-1",
        category,
        proposal_id,
        confirmation_channel="memory_api",
        confirmation_session_id=None,
        confirmation_message_id=None,
        observed_at=NOW,
    )

    expected_signals = getattr(result.profile, expected_map)
    other_map = (
        result.profile.identity_context
        if expected_map == "active_preferences"
        else result.profile.active_preferences
    )
    assert expected_signals[category].value == value
    assert other_map == {}


@pytest.mark.asyncio
async def test_approve_memory_proposal_returns_existing_approval_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, user, _, proposal_ref, _, event_refs = approval_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: pending_proposal_document(status="approved"),
        )
    )
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=governed_profile_document,
        )
    )
    approved_event_id = "response_length--proposal-1--approved"
    approved_ref = MagicMock()
    approved_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lifecycle_event_document,
        )
    )
    corrected_ref = MagicMock()
    corrected_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    event_refs[approved_event_id] = approved_ref
    event_refs["response_length--proposal-1--corrected"] = corrected_ref

    result = await MemoryEngine(client).approve_memory_proposal(
        "user-1",
        "response_length",
        "response_length--proposal-1",
        confirmation_channel="chat_decision",
        confirmation_session_id="confirmation-session",
        confirmation_message_id="confirmation-message",
        observed_at=NOW + timedelta(minutes=5),
    )

    assert result.profile.memory_revision == 1
    assert result.event.event_id == approved_event_id
    assert result.event.created_at == NOW
    assert result.superseded_event is None
    transaction.set.assert_not_called()


def configure_approval_state(
    *,
    proposal_exists: bool = True,
    proposal_document: dict[str, object] | None = None,
    profile_exists: bool = False,
    profile_document: dict[str, object] | None = None,
    approved_exists: bool = False,
    approved_document: dict[str, object] | None = None,
    corrected_exists: bool = False,
    corrected_document: dict[str, object] | None = None,
) -> tuple[MagicMock, MagicMock]:
    client, _, user, _, proposal_ref, _, event_refs = approval_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=proposal_exists,
            to_dict=lambda: proposal_document
            or pending_proposal_document(),
        )
    )
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=profile_exists,
            to_dict=lambda: profile_document or governed_profile_document(),
        )
    )
    approved_ref = MagicMock()
    approved_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=approved_exists,
            to_dict=lambda: approved_document or lifecycle_event_document(),
        )
    )
    corrected_ref = MagicMock()
    corrected_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=corrected_exists,
            to_dict=lambda: corrected_document
            or lifecycle_event_document(event_type="corrected"),
        )
    )
    event_refs["response_length--proposal-1--approved"] = approved_ref
    event_refs["response_length--proposal-1--corrected"] = corrected_ref
    return client, transaction


async def approve_default(client: MagicMock) -> object:
    return await MemoryEngine(client).approve_memory_proposal(
        "user-1",
        "response_length",
        "response_length--proposal-1",
        confirmation_channel="chat_decision",
        confirmation_session_id="confirmation-session",
        confirmation_message_id="confirmation-message",
        observed_at=NOW,
    )


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_missing_slot_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_approval_state(proposal_exists=False)

    with pytest.raises(MemoryProposalNotFoundError):
        await approve_default(client)

    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_replaced_slot_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_approval_state(
        proposal_document=pending_proposal_document(
            proposal_id="response_length--another-proposal"
        )
    )

    with pytest.raises(MemoryProposalConflictError):
        await approve_default(client)

    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_expired_proposal_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    expired = pending_proposal_document()
    expired["expires_at"] = NOW
    client, transaction = configure_approval_state(
        proposal_document=expired
    )

    with pytest.raises(MemoryProposalExpiredError):
        await approve_default(client)

    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_rejected_proposal_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_approval_state(
        proposal_document=pending_proposal_document(status="rejected")
    )

    with pytest.raises(MemoryProposalConflictError):
        await approve_default(client)

    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_approved_slot_missing_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_approval_state(
        proposal_document=pending_proposal_document(status="approved")
    )

    with pytest.raises(MemoryEngineError) as caught:
        await approve_default(client)

    assert isinstance(caught.value.__cause__, ValueError)
    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_two_completion_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_approval_state(
        proposal_document=pending_proposal_document(status="approved"),
        profile_exists=True,
        approved_exists=True,
        corrected_exists=True,
    )

    with pytest.raises(MemoryEngineError) as caught:
        await approve_default(client)

    assert isinstance(caught.value.__cause__, ValueError)
    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_differing_existing_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_approval_state(
        proposal_document=pending_proposal_document(status="approved"),
        profile_exists=True,
        approved_exists=True,
        approved_document=lifecycle_event_document(
            confirmation_message_id="different-confirmation"
        ),
    )

    with pytest.raises(MemoryProposalConflictError):
        await approve_default(client)

    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_initial_expected_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_approval_state(
        proposal_document=pending_proposal_document(
            expected_signal_id="response_length--prior-signal"
        )
    )

    with pytest.raises(MemoryProposalConflictError):
        await approve_default(client)

    transaction.set.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    (
        {"user_id": "has/slash"},
        {"category": "unknown_category"},
        {"proposal_id": "formatting_style--proposal-1"},
        {"proposal_id": f"response_length--{'x' * 105}"},
        {"confirmation_channel": "unknown"},
        {"confirmation_session_id": None},
        {"confirmation_message_id": "has/slash"},
        {"observed_at": datetime(2026, 8, 20, 15, 0)},
    ),
)
async def test_approve_memory_proposal_rejects_invalid_input_before_access(
    overrides: dict[str, object],
) -> None:
    arguments: dict[str, object] = {
        "user_id": "user-1",
        "category": "response_length",
        "proposal_id": "response_length--proposal-1",
        "confirmation_channel": "chat_decision",
        "confirmation_session_id": "confirmation-session",
        "confirmation_message_id": "confirmation-message",
        "observed_at": NOW,
    }
    arguments.update(overrides)
    client = MagicMock()

    with pytest.raises(ValueError):
        await MemoryEngine(client).approve_memory_proposal(**arguments)

    client.collection.assert_not_called()
    client.transaction.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_preserves_firestore_error_safely(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    firestore_error = ServiceUnavailable("private-backend-detail")

    def install_failing_runner(callback):
        async def run(transaction, *args, **kwargs):
            raise firestore_error

        return run

    monkeypatch.setattr(
        "database.firestore.async_transactional",
        install_failing_runner,
    )
    client = MagicMock()
    private_values = (
        "private-user-id",
        "response_length--proposal-1",
        "confirmation-session",
        "confirmation-message",
        "private-backend-detail",
    )
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).approve_memory_proposal(
            "private-user-id",
            "response_length",
            "response_length--proposal-1",
            confirmation_channel="chat_decision",
            confirmation_session_id="confirmation-session",
            confirmation_message_id="confirmation-message",
            observed_at=NOW,
        )

    assert caught.value.__cause__ is firestore_error
    assert str(caught.value) == (
        "Firestore approve_memory_proposal operation failed."
    )
    for private_value in private_values:
        assert private_value not in caplog.text


@pytest.mark.asyncio
async def test_approve_memory_proposal_atomically_corrects_and_supersedes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, user, _, proposal_ref, _, event_refs = approval_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    old_signal_id = "response_length--proposal-1"
    new_signal_id = "response_length--proposal-2"
    old_source_event_id = f"{old_signal_id}--approved"
    new_approved_event_id = f"{new_signal_id}--approved"
    corrected_event_id = f"{new_signal_id}--corrected"
    superseded_event_id = f"{old_signal_id}--superseded"
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: pending_proposal_document(
                proposal_id=new_signal_id,
                value="detailed",
                expected_signal_id=old_signal_id,
                source_session_id="new-source-session",
                source_message_id="new-source-message",
            ),
        )
    )
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=governed_profile_document,
        )
    )
    for event_id in (new_approved_event_id, corrected_event_id):
        event_ref = MagicMock()
        event_ref.get = AsyncMock(
            return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
        )
        event_refs[event_id] = event_ref
    old_source_ref = MagicMock()
    operation_order: list[str] = []

    async def read_old_source(*, transaction) -> SimpleNamespace:
        operation_order.append("read-source")
        return SimpleNamespace(
            exists=True,
            to_dict=lifecycle_event_document,
        )

    old_source_ref.get = AsyncMock(side_effect=read_old_source)
    event_refs[old_source_event_id] = old_source_ref
    superseded_ref = MagicMock()

    async def read_superseded(*, transaction) -> SimpleNamespace:
        operation_order.append("read-superseded")
        return SimpleNamespace(exists=False, to_dict=lambda: None)

    superseded_ref.get = AsyncMock(side_effect=read_superseded)
    event_refs[superseded_event_id] = superseded_ref
    transaction.set.side_effect = lambda *args, **kwargs: operation_order.append(
        "write"
    )

    result = await MemoryEngine(client).approve_memory_proposal(
        "user-1",
        "response_length",
        new_signal_id,
        confirmation_channel="chat_decision",
        confirmation_session_id="correction-session",
        confirmation_message_id="correction-message",
        observed_at=NOW + timedelta(hours=1),
    )

    assert result.profile.memory_revision == 2
    assert result.event.event_id == corrected_event_id
    assert result.event.event_type == "corrected"
    assert result.event.related_signal_id == old_signal_id
    assert result.event.source_session_id == "new-source-session"
    assert result.superseded_event is not None
    assert result.superseded_event.event_id == superseded_event_id
    assert result.superseded_event.event_type == "superseded"
    assert result.superseded_event.signal_id == old_signal_id
    assert result.superseded_event.related_signal_id == new_signal_id
    assert result.superseded_event.source_session_id == "source-session"
    assert (
        result.superseded_event.confirmation_message_id
        == "correction-message"
    )
    active = result.profile.active_preferences["response_length"]
    assert active.signal_id == new_signal_id
    assert active.value == "detailed"
    assert operation_order == [
        "read-source",
        "read-superseded",
        "write",
        "write",
        "write",
        "write",
    ]
    assert transaction.set.call_args_list == [
        call(
            event_refs[corrected_event_id],
            {
                "event_type": "corrected",
                "signal_id": new_signal_id,
                "category": "response_length",
                "value": "detailed",
                "policy_version": "1.0",
                "source_type": "explicit_user_feedback",
                "source_session_id": "new-source-session",
                "source_message_id": "new-source-message",
                "confirmation_channel": "chat_decision",
                "confirmation_session_id": "correction-session",
                "confirmation_message_id": "correction-message",
                "related_signal_id": old_signal_id,
                "memory_revision": 2,
                "created_at": firestore.SERVER_TIMESTAMP,
            },
        ),
        call(
            event_refs[superseded_event_id],
            {
                "event_type": "superseded",
                "signal_id": old_signal_id,
                "category": "response_length",
                "value": "concise",
                "policy_version": "1.0",
                "source_type": "explicit_user_feedback",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "confirmation_channel": "chat_decision",
                "confirmation_session_id": "correction-session",
                "confirmation_message_id": "correction-message",
                "related_signal_id": new_signal_id,
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
                "active_preferences": {
                    "response_length": {
                        "signal_id": new_signal_id,
                        "category": "response_length",
                        "value": "detailed",
                        "policy_version": "1.0",
                        "source_event_id": corrected_event_id,
                        "approved_at": firestore.SERVER_TIMESTAMP,
                    }
                },
                "memory_updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
        call(
            proposal_ref,
            {
                "status": "approved",
                "resolved_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
    ]


def configure_correction_state(
    *,
    proposal_status: str = "pending",
    expected_signal_id: str | None = "response_length--proposal-1",
    profile_document: dict[str, object] | None = None,
    corrected_exists: bool = False,
    corrected_document: dict[str, object] | None = None,
    source_exists: bool = True,
    source_document: dict[str, object] | None = None,
    superseded_exists: bool = False,
    superseded_document: dict[str, object] | None = None,
) -> tuple[MagicMock, MagicMock]:
    client, _, user, _, proposal_ref, _, event_refs = approval_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    old_signal_id = "response_length--proposal-1"
    new_signal_id = "response_length--proposal-2"
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: pending_proposal_document(
                proposal_id=new_signal_id,
                value="detailed",
                expected_signal_id=expected_signal_id,
                status=proposal_status,
                source_session_id="new-source-session",
                source_message_id="new-source-message",
            ),
        )
    )
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: profile_document or governed_profile_document(),
        )
    )
    approved_ref = MagicMock()
    approved_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    corrected_ref = MagicMock()
    corrected_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=corrected_exists,
            to_dict=lambda: corrected_document
            or lifecycle_event_document(
                event_type="corrected",
                signal_id=new_signal_id,
                value="detailed",
                related_signal_id=old_signal_id,
                revision=2,
                source_session_id="new-source-session",
                source_message_id="new-source-message",
                confirmation_session_id="correction-session",
                confirmation_message_id="correction-message",
            ),
        )
    )
    source_ref = MagicMock()
    source_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=source_exists,
            to_dict=lambda: source_document or lifecycle_event_document(),
        )
    )
    superseded_ref = MagicMock()
    superseded_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=superseded_exists,
            to_dict=lambda: superseded_document
            or lifecycle_event_document(
                event_type="superseded",
                related_signal_id=new_signal_id,
                revision=2,
                confirmation_session_id="correction-session",
                confirmation_message_id="correction-message",
            ),
        )
    )
    event_refs[f"{new_signal_id}--approved"] = approved_ref
    event_refs[f"{new_signal_id}--corrected"] = corrected_ref
    event_refs[f"{old_signal_id}--approved"] = source_ref
    event_refs[f"{old_signal_id}--superseded"] = superseded_ref
    return client, transaction


async def approve_correction(client: MagicMock) -> object:
    return await MemoryEngine(client).approve_memory_proposal(
        "user-1",
        "response_length",
        "response_length--proposal-2",
        confirmation_channel="chat_decision",
        confirmation_session_id="correction-session",
        confirmation_message_id="correction-message",
        observed_at=NOW + timedelta(hours=1),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expected_signal_id",
    (None, "response_length--different-signal"),
)
async def test_approve_memory_proposal_rejects_stale_correction_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    expected_signal_id: str | None,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_correction_state(
        expected_signal_id=expected_signal_id
    )

    with pytest.raises(MemoryProposalConflictError):
        await approve_correction(client)

    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_missing_correction_source_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_correction_state(source_exists=False)

    with pytest.raises(MemoryEngineError) as caught:
        await approve_correction(client)

    assert isinstance(caught.value.__cause__, ValueError)
    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_mismatched_correction_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_correction_state(
        source_document=lifecycle_event_document(value="detailed")
    )

    with pytest.raises(MemoryEngineError) as caught:
        await approve_correction(client)

    assert isinstance(caught.value.__cause__, ValueError)
    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_existing_superseded_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_correction_state(
        superseded_exists=True
    )

    with pytest.raises(MemoryProposalConflictError):
        await approve_correction(client)

    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_preserves_unrelated_active_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    profile = governed_profile_document()
    profile["identity_context"] = {
        "preferred_name": {
            "signal_id": "preferred_name--proposal-1",
            "category": "preferred_name",
            "value": "Avery",
            "policy_version": "1.0",
            "source_event_id": "preferred_name--proposal-1--approved",
            "approved_at": NOW,
        }
    }
    profile["active_preferences"]["formatting_style"] = {
        "signal_id": "formatting_style--proposal-1",
        "category": "formatting_style",
        "value": "bullets",
        "policy_version": "1.0",
        "source_event_id": "formatting_style--proposal-1--approved",
        "approved_at": NOW,
    }
    client, _ = configure_correction_state(profile_document=profile)

    result = await approve_correction(client)

    assert result.profile.identity_context["preferred_name"].value == "Avery"
    assert result.profile.active_preferences["formatting_style"].value == (
        "bullets"
    )
    corrected = result.profile.active_preferences["response_length"]
    assert corrected.signal_id == "response_length--proposal-2"
    assert corrected.value == "detailed"


@pytest.mark.asyncio
async def test_approve_memory_proposal_returns_existing_correction_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    corrected_signal = active_signal_document(
        signal_id="response_length--proposal-2",
        value="detailed",
        source_event_id="response_length--proposal-2--corrected",
        approved_at=NOW + timedelta(hours=1),
    )
    corrected_profile = governed_profile_document(
        revision=2,
        signal=corrected_signal,
    )
    client, transaction = configure_correction_state(
        proposal_status="approved",
        profile_document=corrected_profile,
        corrected_exists=True,
        superseded_exists=True,
    )

    result = await approve_correction(client)

    assert result.profile.memory_revision == 2
    assert result.event.event_id == "response_length--proposal-2--corrected"
    assert result.superseded_event is not None
    assert result.superseded_event.event_id == (
        "response_length--proposal-1--superseded"
    )
    transaction.set.assert_not_called()


def corrected_profile_document() -> dict[str, object]:
    return governed_profile_document(
        revision=2,
        signal=active_signal_document(
            signal_id="response_length--proposal-2",
            value="detailed",
            source_event_id="response_length--proposal-2--corrected",
            approved_at=NOW + timedelta(hours=1),
        ),
    )


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_missing_retry_superseded_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_correction_state(
        proposal_status="approved",
        profile_document=corrected_profile_document(),
        corrected_exists=True,
        superseded_exists=False,
    )

    with pytest.raises(MemoryEngineError) as caught:
        await approve_correction(client)

    assert isinstance(caught.value.__cause__, ValueError)
    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_differing_retry_superseded_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, transaction = configure_correction_state(
        proposal_status="approved",
        profile_document=corrected_profile_document(),
        corrected_exists=True,
        superseded_exists=True,
        superseded_document=lifecycle_event_document(
            event_type="superseded",
            related_signal_id="response_length--proposal-2",
            revision=2,
            confirmation_session_id="correction-session",
            confirmation_message_id="different-message",
        ),
    )

    with pytest.raises(MemoryProposalConflictError):
        await approve_correction(client)

    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_memory_proposal_rejects_oversized_stored_event_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    long_signal_id = f"response_length--{'x' * 103}"
    profile = governed_profile_document(
        signal=active_signal_document(
            signal_id=long_signal_id,
            source_event_id="bounded-source-event",
        )
    )
    client, transaction = configure_correction_state(
        expected_signal_id=long_signal_id,
        profile_document=profile,
    )

    with pytest.raises(MemoryEngineError) as caught:
        await approve_correction(client)

    assert isinstance(caught.value.__cause__, ValueError)
    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_v2_memory_correction_preserves_v2_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, user, _, proposal_ref, _, event_refs = approval_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    old_signal_id = "development_environments--proposal-v1"
    new_signal_id = "development_environments--proposal-v2"
    approved_event_id = f"{new_signal_id}--approved"
    corrected_event_id = f"{new_signal_id}--corrected"
    source_event_id = f"{old_signal_id}--approved"
    superseded_event_id = f"{old_signal_id}--superseded"
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: pending_v2_proposal_document(
                value=("windows",),
                expected_signal_id=old_signal_id,
            ),
        )
    )
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=governed_v2_profile_document,
        )
    )
    for event_id in (approved_event_id, corrected_event_id):
        event_refs.setdefault(event_id, MagicMock())
        event_refs[event_id].get = AsyncMock(
            return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
        )
    event_refs.setdefault(source_event_id, MagicMock())
    event_refs[source_event_id].get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=v2_lifecycle_event_document,
        )
    )
    event_refs.setdefault(superseded_event_id, MagicMock())
    event_refs[superseded_event_id].get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )

    result = await MemoryEngine(client).approve_memory_proposal(
        "user-1",
        "development_environments",
        new_signal_id,
        confirmation_channel="chat_decision",
        confirmation_session_id="correction-session",
        confirmation_message_id="correction-message",
        observed_at=NOW + timedelta(hours=1),
    )

    assert result.profile.memory_schema_version == "2.0"
    assert result.profile.memory_revision == 2
    assert result.event.event_type == "corrected"
    assert result.event.policy_version == "2.0"
    assert result.event.evidence_message_id == "source-message"
    assert result.superseded_event is not None
    assert result.superseded_event.event_type == "superseded"
    assert result.superseded_event.policy_version == "2.0"
    assert result.superseded_event.evidence_message_id == "source-message"
    active = result.profile.active_preferences["development_environments"]
    assert active.signal_id == new_signal_id
    assert active.value == ["windows"]
