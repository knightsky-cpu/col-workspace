from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore

import database
from chat_turns import (
    ChatTurnClaim,
    ChatTurnConflictError,
    ChatTurnIds,
    ChatTurnInProgressError,
    ChatTurnOwnershipError,
    ChatTurnReplay,
    ChatTurnRequest,
    ChatTurnStateError,
    derive_chat_turn_ids,
)
from database import MemoryEngine, MemoryEngineError
from schemas import ChatResponse, MemoryDecisionRequest


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


def snapshot(
    *, exists: bool, data: dict[str, object] | None = None
) -> SimpleNamespace:
    return SimpleNamespace(exists=exists, to_dict=lambda: data)


class ChatTurnStore:
    def __init__(self, ids: ChatTurnIds) -> None:
        self.client = MagicMock()
        self.sessions = MagicMock()
        self.session_ref = MagicMock()
        self.turns = MagicMock()
        self.messages = MagicMock()
        self.turn_ref = MagicMock()
        self.user_message_ref = MagicMock()
        self.model_message_ref = MagicMock()
        self.transaction = MagicMock()

        self.client.collection.return_value = self.sessions
        self.sessions.document.return_value = self.session_ref

        def session_collection(name: str) -> MagicMock:
            if name == "turns":
                return self.turns
            if name == "messages":
                return self.messages
            raise AssertionError(f"Unexpected collection: {name}")

        def message_document(message_id: str) -> MagicMock:
            if message_id == ids.user_message_id:
                return self.user_message_ref
            if message_id == ids.model_message_id:
                return self.model_message_ref
            raise AssertionError(f"Unexpected message ID: {message_id}")

        self.session_ref.collection.side_effect = session_collection
        self.turns.document.return_value = self.turn_ref
        self.messages.document.side_effect = message_document
        self.client.transaction.return_value = self.transaction


def turn_document(
    ids: ChatTurnIds,
    *,
    status: str = "in_progress",
    project_id: str = "agent-col",
    user_id: str = "user-1",
    owner: str = "existing-owner",
    lease_expires_at: datetime = NOW + timedelta(seconds=30),
) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": "1.0",
        "status": status,
        "project_id": project_id,
        "user_id": user_id,
        "memory_decision": None,
        "user_message_id": ids.user_message_id,
        "model_message_id": ids.model_message_id,
        "created_at": NOW - timedelta(seconds=1),
        "updated_at": NOW - timedelta(seconds=1),
    }
    if status == "in_progress":
        data["lease_owner"] = owner
        data["lease_expires_at"] = lease_expires_at
    else:
        data.update(
            {
                "actions": [],
                "artifacts": [],
                "citations": [],
                "adaptations": [],
                "completed_at": NOW - timedelta(seconds=1),
            }
        )
    return data


def user_message_document(
    text: str = "Remember one logical turn.",
) -> dict[str, object]:
    return {"role": "user", "text": text, "timestamp": NOW}


def claimed_store(
    *,
    owner: str = "owner-token",
    lease_expires_at: datetime = NOW + timedelta(seconds=30),
) -> tuple[ChatTurnStore, ChatTurnClaim]:
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )
    claim = ChatTurnClaim(
        request=request,
        ids=ids,
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=turn_document(
                ids,
                owner=owner,
                lease_expires_at=lease_expires_at,
            ),
        )
    )
    return store, claim


@pytest.mark.asyncio
async def test_claim_chat_turn_atomically_creates_turn_and_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    token_hex = MagicMock(return_value="owner-token")
    monkeypatch.setattr(
        database,
        "secrets",
        SimpleNamespace(token_hex=token_hex),
        raising=False,
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    claim = await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert claim.owner_token == "owner-token"
    assert claim.resumed is False
    assert claim.lease_expires_at == NOW + timedelta(seconds=120)
    assert claim.ids == ids
    token_hex.assert_called_once_with(16)
    assert store.transaction.set.call_args_list == [
        call(
            store.session_ref,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(
            store.turn_ref,
            {
                "schema_version": "1.0",
                "status": "in_progress",
                "project_id": "agent-col",
                "user_id": "user-1",
                "memory_decision": None,
                "user_message_id": ids.user_message_id,
                "model_message_id": ids.model_message_id,
                "lease_owner": "owner-token",
                "lease_expires_at": NOW + timedelta(seconds=120),
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        ),
        call(
            store.user_message_ref,
            {
                "role": "user",
                "text": "Remember one logical turn.",
                "timestamp": firestore.SERVER_TIMESTAMP,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_request_mismatch_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_document(ids))
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=user_message_document("different message"),
        )
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    with pytest.raises(ChatTurnConflictError):
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_unexpired_lease_with_retry_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_document(ids))
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=user_message_document(),
        )
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    with pytest.raises(ChatTurnInProgressError) as caught:
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW + timedelta(milliseconds=500),
        )

    assert caught.value.retry_after_seconds == 30
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_reclaims_expired_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=turn_document(
                ids,
                lease_expires_at=NOW - timedelta(seconds=1),
            ),
        )
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    monkeypatch.setattr(database.secrets, "token_hex", lambda _: "new-owner")
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    claim = await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert claim.resumed is True
    assert claim.owner_token == "new-owner"
    store.transaction.set.assert_called_once_with(
        store.turn_ref,
        {
            "lease_owner": "new-owner",
            "lease_expires_at": NOW + timedelta(seconds=120),
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_claim_chat_turn_replays_completed_response_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=turn_document(ids, status="completed"),
        )
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"role": "model", "text": "Durable answer.", "timestamp": NOW},
        )
    )
    request = ChatTurnRequest(
        project_id="agent-col",
        session_id="session-1",
        user_id="user-1",
        message="Remember one logical turn.",
    )

    result = await MemoryEngine(store.client).claim_chat_turn(
        request,
        idempotency_key="request-1",
        observed_at=NOW,
    )

    assert result == ChatTurnReplay(
        response=ChatResponse(response="Durable answer.")
    )
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_orphaned_turn_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_document(ids))
    )
    store.user_message_ref.get = AsyncMock(return_value=snapshot(exists=False))
    request = ChatTurnRequest("agent-col", "session-1", "user-1", "message")

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_rejects_missing_lease_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    stored_turn = turn_document(ids)
    stored_turn.pop("lease_owner")
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.user_message_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=user_message_document())
    )
    request = ChatTurnRequest(
        "agent-col",
        "session-1",
        "user-1",
        "Remember one logical turn.",
    )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_validates_before_firestore_access() -> None:
    client = MagicMock()
    request = ChatTurnRequest("agent-col", "session-1", "user-1", "message")

    with pytest.raises(ValueError, match="observed_at"):
        await MemoryEngine(client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=datetime(2026, 8, 20),
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "turn_request",
    [
        ChatTurnRequest("project/1", "session-1", "user-1", "message"),
        ChatTurnRequest("agent-col", "session 1", "user-1", "message"),
        ChatTurnRequest("agent-col", "session-1", "user.1", "message"),
        ChatTurnRequest(
            "agent-col",
            "session-1",
            "user-1",
            "message",
            cast(MemoryDecisionRequest, object()),
        ),
    ],
)
async def test_claim_chat_turn_rejects_invalid_request_before_firestore(
    turn_request: ChatTurnRequest,
) -> None:
    client = MagicMock()

    with pytest.raises(ValueError):
        await MemoryEngine(client).claim_chat_turn(
            turn_request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_claim_chat_turn_preserves_firestore_failure_as_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    ids = derive_chat_turn_ids("request-1")
    store = ChatTurnStore(ids)
    provider_error = ServiceUnavailable("private provider detail")
    store.turn_ref.get = AsyncMock(side_effect=provider_error)
    request = ChatTurnRequest("agent-col", "session-1", "user-1", "message")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(store.client).claim_chat_turn(
            request,
            idempotency_key="request-1",
            observed_at=NOW,
        )

    assert caught.value.__cause__ is provider_error


@pytest.mark.asyncio
async def test_renew_chat_turn_lease_extends_matching_unexpired_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()

    renewed = await MemoryEngine(store.client).renew_chat_turn_lease(
        claim,
        observed_at=NOW,
    )

    assert renewed.owner_token == claim.owner_token
    assert renewed.lease_expires_at == NOW + timedelta(seconds=120)
    store.transaction.set.assert_called_once_with(
        store.turn_ref,
        {
            "lease_expires_at": NOW + timedelta(seconds=120),
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_renew_chat_turn_lease_rejects_expired_owner_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store(
        lease_expires_at=NOW - timedelta(seconds=1)
    )

    with pytest.raises(ChatTurnOwnershipError):
        await MemoryEngine(store.client).renew_chat_turn_lease(
            claim,
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_release_chat_turn_expires_matching_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()

    await MemoryEngine(store.client).release_chat_turn(
        claim,
        observed_at=NOW,
    )

    store.transaction.set.assert_called_once_with(
        store.turn_ref,
        {
            "lease_expires_at": NOW,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_release_chat_turn_is_idempotent_for_expired_matching_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store(lease_expires_at=NOW)

    await MemoryEngine(store.client).release_chat_turn(
        claim,
        observed_at=NOW,
    )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_release_chat_turn_rejects_reclaimed_owner_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store(owner="new-owner")

    with pytest.raises(ChatTurnOwnershipError):
        await MemoryEngine(store.client).release_chat_turn(
            claim,
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_atomically_stores_response_and_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    response = ChatResponse(response="A durable answer.")

    await MemoryEngine(store.client).complete_chat_turn(
        claim,
        response,
        observed_at=NOW,
    )

    assert store.transaction.set.call_args_list == [
        call(
            store.session_ref,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(
            store.model_message_ref,
            {
                "role": "model",
                "text": "A durable answer.",
                "timestamp": firestore.SERVER_TIMESTAMP,
            },
        ),
        call(
            store.turn_ref,
            {
                "status": "completed",
                "actions": [],
                "artifacts": [],
                "citations": [],
                "adaptations": [],
                "completed_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "lease_owner": firestore.DELETE_FIELD,
                "lease_expires_at": firestore.DELETE_FIELD,
            },
            merge=True,
        ),
    ]


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_expired_lease_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store(
        lease_expires_at=NOW - timedelta(seconds=1)
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    with pytest.raises(ChatTurnOwnershipError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            ChatResponse(response="A durable answer."),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_reclaimed_owner_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store(owner="new-owner")
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    with pytest.raises(ChatTurnOwnershipError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            ChatResponse(response="A durable answer."),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_preexisting_model_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"role": "model", "text": "Existing", "timestamp": NOW},
        )
    )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            ChatResponse(response="A durable answer."),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_invalid_claim_before_firestore(
) -> None:
    client = MagicMock()
    request = ChatTurnRequest("agent-col", "session-1", "user-1", "message")
    invalid_claim = ChatTurnClaim(
        request=request,
        ids=ChatTurnIds(
            turn_id="invalid",
            user_message_id="wrong-user-message",
            model_message_id="wrong-model-message",
        ),
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=30),
        resumed=False,
    )

    with pytest.raises(ValueError, match="claim"):
        await MemoryEngine(client).complete_chat_turn(
            invalid_claim,
            ChatResponse(response="A durable answer."),
            observed_at=NOW,
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_complete_chat_turn_rejects_mismatched_stored_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store, claim = claimed_store()
    stored_turn = turn_document(
        claim.ids,
        project_id="different-project",
        owner=claim.owner_token,
    )
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_turn)
    )
    store.model_message_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    with pytest.raises(ChatTurnStateError):
        await MemoryEngine(store.client).complete_chat_turn(
            claim,
            ChatResponse(response="A durable answer."),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()
