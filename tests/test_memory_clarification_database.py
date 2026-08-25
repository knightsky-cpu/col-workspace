from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.cloud import firestore

from database import MemoryEngine
from memory_clarifications import (
    MemoryClarificationEnvelope,
    clarification_receipt,
    derive_memory_clarification_id,
)
from memory_proposals import ProposalTurnLease


NOW = datetime(2026, 8, 24, 19, 0, tzinfo=UTC)
TURN_ID = "a" * 64
PRIOR_TURN_ID = "b" * 64


def prior_clarification_id() -> str:
    return derive_memory_clarification_id(
        user_id="user-1",
        session_id="session-1",
        evidence_message_id="prior-message",
        clarification_turn_id=PRIOR_TURN_ID,
    )


def install_transaction_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    def run_without_sdk_retry(callback):
        async def run(transaction, *args, **kwargs):
            return await callback(transaction, *args, **kwargs)

        return run

    monkeypatch.setattr(
        "database.firestore.async_transactional",
        run_without_sdk_retry,
    )


def snapshot(*, exists: bool, data: object = None) -> SimpleNamespace:
    return SimpleNamespace(exists=exists, to_dict=lambda: data)


def envelope(**updates: object) -> MemoryClarificationEnvelope:
    payload: dict[str, object] = {
        "clarification_id": derive_memory_clarification_id(
            user_id="user-1",
            session_id="session-1",
            evidence_message_id="message-1",
            clarification_turn_id=TURN_ID,
        ),
        "user_id": "user-1",
        "session_id": "session-1",
        "workspace_id": "workspace-1",
        "evidence_message_id": "message-1",
        "clarification_turn_id": TURN_ID,
        "candidates": [
            {
                "category": "preferred_name",
                "canonical_value": "wifiknight",
            },
            {
                "category": "development_environments",
                "canonical_value": ["macos", "linux"],
            },
        ],
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=15),
        "status": "open",
    }
    payload.update(updates)
    return MemoryClarificationEnvelope.model_validate(payload)


def turn_document(
    *,
    memory_clarifications: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "1.0",
        "status": "in_progress",
        "project_id": "workspace-1",
        "user_id": "user-1",
        "user_message_id": "message-1",
        "lease_owner": "owner-1",
        "lease_expires_at": NOW + timedelta(minutes=1),
    }
    if memory_clarifications is not None:
        document["memory_clarifications"] = memory_clarifications
    return document


def clarification_store() -> SimpleNamespace:
    client = MagicMock(name="client")
    sessions = MagicMock(name="sessions")
    session = MagicMock(name="session")
    clarifications = MagicMock(name="clarifications")
    clarification = MagicMock(name="clarification")
    prior = MagicMock(name="prior")
    turns = MagicMock(name="turns")
    turn = MagicMock(name="turn")
    transaction = MagicMock(name="transaction")

    client.collection.return_value = sessions
    sessions.document.return_value = session

    def session_collection(name: str):
        if name == "memory_clarifications":
            return clarifications
        if name == "turns":
            return turns
        raise AssertionError(f"unexpected session collection: {name}")

    session.collection.side_effect = session_collection

    def clarification_document(document_id: str):
        if document_id == envelope().clarification_id:
            return clarification
        if document_id == prior_clarification_id():
            return prior
        raise AssertionError(f"unexpected clarification: {document_id}")

    clarifications.document.side_effect = clarification_document
    turns.document.return_value = turn
    client.transaction.return_value = transaction
    return SimpleNamespace(
        client=client,
        session=session,
        clarification=clarification,
        prior=prior,
        turn=turn,
        transaction=transaction,
    )


def lease() -> ProposalTurnLease:
    return ProposalTurnLease(turn_id=TURN_ID, owner_token="owner-1")


@pytest.mark.asyncio
async def test_clarification_validates_before_firestore_access() -> None:
    store = clarification_store()

    with pytest.raises(ValueError, match="turn lease"):
        await MemoryEngine(store.client).create_memory_clarification(
            envelope=envelope(),
            observed_at=NOW,
            turn_lease=None,
        )

    store.client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_clarification_creation_writes_envelope_receipt_and_pointer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = clarification_store()
    store.session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"user_id": "user-1", "project_id": "workspace-1"},
        )
    )
    store.clarification.get = AsyncMock(return_value=snapshot(exists=False))
    store.turn.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_document())
    )

    result = await MemoryEngine(store.client).create_memory_clarification(
        envelope=envelope(),
        observed_at=NOW,
        turn_lease=lease(),
    )

    expected_receipt = clarification_receipt(envelope()).model_dump(
        mode="python"
    )
    assert result == envelope()
    expected_envelope_document = envelope().model_dump(
        mode="python",
        exclude_none=True,
    )
    assert store.transaction.set.call_args_list == [
        call(
            store.clarification,
            expected_envelope_document,
        ),
        call(
            store.turn,
            {
                "memory_clarifications": [expected_receipt],
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
        call(
            store.session,
            {
                "active_memory_clarification_id": (
                    envelope().clarification_id
                ),
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
    ]
    stored_envelope = store.transaction.set.call_args_list[0].args[1]
    assert "choices" not in stored_envelope
    assert "evidence_text" not in str(stored_envelope)


@pytest.mark.asyncio
async def test_clarification_exact_retry_returns_existing_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = clarification_store()
    receipt = clarification_receipt(envelope()).model_dump(mode="python")
    store.session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "user_id": "user-1",
                "project_id": "workspace-1",
                "active_memory_clarification_id": envelope().clarification_id,
            },
        )
    )
    store.clarification.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=envelope().model_dump(mode="python"),
        )
    )
    store.turn.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=turn_document(memory_clarifications=[receipt]),
        )
    )

    result = await MemoryEngine(store.client).create_memory_clarification(
        envelope=envelope(),
        observed_at=NOW,
        turn_lease=lease(),
    )

    assert result == envelope()
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_clarification_changed_retry_conflicts_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import MemoryClarificationConflictError

    install_transaction_runner(monkeypatch)
    store = clarification_store()
    changed = envelope().model_dump(mode="python")
    changed["candidates"][0]["canonical_value"] = "different-name"
    store.session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "user_id": "user-1",
                "project_id": "workspace-1",
                "active_memory_clarification_id": envelope().clarification_id,
            },
        )
    )
    store.clarification.get = AsyncMock(
        return_value=snapshot(exists=True, data=changed)
    )
    store.turn.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_document())
    )

    with pytest.raises(MemoryClarificationConflictError):
        await MemoryEngine(store.client).create_memory_clarification(
            envelope=envelope(),
            observed_at=NOW,
            turn_lease=lease(),
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_clarification_expires_different_prior_open_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = clarification_store()
    prior_envelope = envelope(
        clarification_id=prior_clarification_id(),
        clarification_turn_id=PRIOR_TURN_ID,
        evidence_message_id="prior-message",
        created_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=10),
    )
    store.session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "user_id": "user-1",
                "project_id": "workspace-1",
                "active_memory_clarification_id": prior_clarification_id(),
            },
        )
    )
    store.clarification.get = AsyncMock(return_value=snapshot(exists=False))
    store.prior.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=prior_envelope.model_dump(mode="python"),
        )
    )
    store.turn.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_document())
    )

    await MemoryEngine(store.client).create_memory_clarification(
        envelope=envelope(),
        observed_at=NOW,
        turn_lease=lease(),
    )

    assert store.transaction.set.call_args_list[0] == call(
        store.prior,
        {"status": "expired"},
        merge=True,
    )


@pytest.mark.asyncio
async def test_clarification_rejects_pointer_document_id_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import MemoryClarificationStateError

    install_transaction_runner(monkeypatch)
    store = clarification_store()
    mismatched_id = derive_memory_clarification_id(
        user_id="user-1",
        session_id="session-1",
        evidence_message_id="different-prior-message",
        clarification_turn_id="different-prior-turn",
    )
    mismatched_prior = envelope(
        clarification_id=mismatched_id,
        clarification_turn_id="different-prior-turn",
        evidence_message_id="different-prior-message",
        created_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=10),
    )
    store.session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "user_id": "user-1",
                "project_id": "workspace-1",
                "active_memory_clarification_id": prior_clarification_id(),
            },
        )
    )
    store.clarification.get = AsyncMock(return_value=snapshot(exists=False))
    store.prior.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=mismatched_prior.model_dump(mode="python"),
        )
    )
    store.turn.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_document())
    )

    with pytest.raises(MemoryClarificationStateError, match="pointer"):
        await MemoryEngine(store.client).create_memory_clarification(
            envelope=envelope(),
            observed_at=NOW,
            turn_lease=lease(),
        )

    store.transaction.set.assert_not_called()


def test_stored_clarification_rejects_non_deterministic_id() -> None:
    from database import MemoryClarificationStateError

    invalid_document = envelope().model_dump(mode="python")
    invalid_document["clarification_id"] = "tampered-clarification"

    with pytest.raises(MemoryClarificationStateError, match="invalid"):
        MemoryEngine._memory_clarification_from_document(invalid_document)
