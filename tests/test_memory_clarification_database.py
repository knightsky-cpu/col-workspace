from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, call

import pytest
from google.cloud import firestore

from database import MemoryEngine
from memory_clarifications import (
    MemoryClarificationEnvelope,
    MemoryClarificationSelection,
    derive_memory_clarification_id,
)
from memory_proposals import (
    derive_proposal_origin_ids_v2,
)
from schemas import MemoryProposalV2


NOW = datetime(2026, 8, 24, 19, 0, tzinfo=UTC)
TURN_ID = "a" * 64
PRIOR_TURN_ID = "b" * 64
DIRECT_SOURCE_MESSAGE_ID = "message-1"


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


def direct_envelope(**updates: object) -> MemoryClarificationEnvelope:
    payload: dict[str, object] = {
        "clarification_id": derive_memory_clarification_id(
            user_id="user-1",
            session_id="session-1",
            evidence_message_id=DIRECT_SOURCE_MESSAGE_ID,
            clarification_turn_id=DIRECT_SOURCE_MESSAGE_ID,
        ),
        "user_id": "user-1",
        "session_id": "session-1",
        "workspace_id": "workspace-1",
        "evidence_message_id": DIRECT_SOURCE_MESSAGE_ID,
        "clarification_turn_id": DIRECT_SOURCE_MESSAGE_ID,
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
        if document_id in {
            envelope().clarification_id,
            direct_envelope().clarification_id,
        }:
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


def clarification_consumption_store() -> SimpleNamespace:
    store = clarification_store()
    users = MagicMock(name="users")
    user = MagicMock(name="user")
    origins = MagicMock(name="origins")
    origin = MagicMock(name="origin")
    proposals = MagicMock(name="proposals")
    proposal = MagicMock(name="proposal")

    def root_collection(name: str):
        if name == "sessions":
            return store.client.collection.return_value
        if name == "users":
            return users
        raise AssertionError(f"unexpected root collection: {name}")

    sessions = store.client.collection.return_value
    store.client.collection.side_effect = root_collection
    users.document.return_value = user

    def user_collection(name: str):
        if name == "memory_proposal_origins":
            return origins
        if name == "memory_proposals":
            return proposals
        raise AssertionError(f"unexpected user collection: {name}")

    user.collection.side_effect = user_collection
    origins.document.return_value = origin
    proposals.document.return_value = proposal
    return SimpleNamespace(
        **store.__dict__,
        sessions=sessions,
        user=user,
        origin=origin,
        proposal=proposal,
    )


@pytest.mark.asyncio
async def test_clarification_validates_before_firestore_access() -> None:
    store = clarification_store()

    with pytest.raises(ValueError, match="clarification_id"):
        await MemoryEngine(store.client).create_memory_clarification(
            envelope=direct_envelope(clarification_id="memory-clarification--bad"),
            observed_at=NOW,
        )

    store.client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_clarification_creation_rejects_turn_lease_argument() -> None:
    store = clarification_store()

    with pytest.raises(TypeError, match="turn_lease"):
        await MemoryEngine(store.client).create_memory_clarification(
            envelope=direct_envelope(),
            observed_at=NOW,
            turn_lease=object(),
        )

    store.client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_clarification_creation_writes_envelope_and_pointer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = clarification_store()
    direct = direct_envelope()
    store.session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"user_id": "user-1", "project_id": "workspace-1"},
        )
    )
    store.clarification.get = AsyncMock(return_value=snapshot(exists=False))

    result = await MemoryEngine(store.client).create_memory_clarification(
        envelope=direct,
        observed_at=NOW,
    )

    assert result == direct
    store.turn.get.assert_not_called()
    assert store.transaction.set.call_args_list == [
        call(
            store.clarification,
            direct.model_dump(mode="python", exclude_none=True),
        ),
        call(
            store.session,
            {
                "active_memory_clarification_id": direct.clarification_id,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
    ]


@pytest.mark.asyncio
async def test_clarification_exact_retry_returns_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = clarification_store()
    direct = direct_envelope()
    store.session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "user_id": "user-1",
                "project_id": "workspace-1",
                "active_memory_clarification_id": direct.clarification_id,
            },
        )
    )
    store.clarification.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=direct.model_dump(mode="python"),
        )
    )

    result = await MemoryEngine(store.client).create_memory_clarification(
        envelope=direct,
        observed_at=NOW,
    )

    assert result == direct
    store.turn.get.assert_not_called()
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_clarification_selection_atomically_consumes_and_creates_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = clarification_consumption_store()
    selecting_turn_id = "c" * 64
    selecting_message_id = f"turn--{selecting_turn_id}--user"
    ids = derive_proposal_origin_ids_v2(
        "user-1",
        "session-1",
        selecting_message_id,
        "development_environments",
    )
    store.session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "user_id": "user-1",
                "project_id": "workspace-1",
                "active_memory_clarification_id": envelope().clarification_id,
                "last_completed_turn_id": TURN_ID,
            },
        )
    )
    store.clarification.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=envelope().model_dump(mode="python"),
        )
    )
    store.origin.get = AsyncMock(return_value=snapshot(exists=False))
    store.proposal.get = AsyncMock(return_value=snapshot(exists=False))
    store.user.get = AsyncMock(return_value=snapshot(exists=False))

    result = await MemoryEngine(
        store.client
    ).consume_memory_clarification_to_proposal_v2(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_id=selecting_message_id,
        selection=MemoryClarificationSelection(
            selected_candidate_index=1,
        ),
        expected_clarification_id=envelope().clarification_id,
        observed_at=NOW + timedelta(minutes=1),
    )

    assert result.proposal_id == ids.proposal_id
    assert result.category == "development_environments"
    assert result.proposed_value == ["macos", "linux"]
    assert result.evidence_message_id == "message-1"
    assert result.clarification_id == envelope().clarification_id
    writes = store.transaction.set.call_args_list
    assert call(
        store.clarification,
        {
            "status": "consumed",
            "consuming_turn_id": selecting_message_id,
            "consuming_message_id": selecting_message_id,
            "selected_candidate_index": 1,
        },
        merge=True,
    ) in writes
    assert call(
        store.session,
        {
            "active_memory_clarification_id": firestore.DELETE_FIELD,
            "last_consumed_memory_clarification_id": (
                envelope().clarification_id
            ),
            "last_consuming_memory_turn_id": selecting_message_id,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    ) in writes
    assert call(store.proposal, ANY) in writes
    assert call(store.origin, ANY) in writes
    store.turn.get.assert_not_called()
    assert all(write.args[0] is not store.turn for write in writes)


@pytest.mark.asyncio
async def test_clarification_selection_rejects_a_different_public_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import MemoryClarificationSelectionError

    install_transaction_runner(monkeypatch)
    store = clarification_consumption_store()
    selecting_turn_id = "c" * 64
    selecting_message_id = f"turn--{selecting_turn_id}--user"
    store.session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "user_id": "user-1",
                "project_id": "workspace-1",
                "active_memory_clarification_id": (
                    envelope().clarification_id
                ),
                "last_completed_turn_id": TURN_ID,
            },
        )
    )

    with pytest.raises(
        MemoryClarificationSelectionError,
        match="does not match",
    ):
        await MemoryEngine(
            store.client
        ).consume_memory_clarification_to_proposal_v2(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-1",
            source_message_id=selecting_message_id,
            selection=MemoryClarificationSelection(
                selected_candidate_index=1,
            ),
            expected_clarification_id=(
                "memory-clarification--different-clarification"
            ),
            observed_at=NOW + timedelta(minutes=1),
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_clarification_selection_exact_retry_reuses_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = clarification_consumption_store()
    selecting_turn_id = "c" * 64
    selecting_message_id = f"turn--{selecting_turn_id}--user"
    origin_ids = derive_proposal_origin_ids_v2(
        "user-1",
        "session-1",
        selecting_message_id,
        "development_environments",
    )
    consumed = envelope(
        status="consumed",
        consuming_turn_id=selecting_message_id,
        consuming_message_id=selecting_message_id,
        selected_candidate_index=1,
    )
    proposal = MemoryProposalV2(
        proposal_id=origin_ids.proposal_id,
        category="development_environments",
        proposed_value=["macos", "linux"],
        expected_signal_id=None,
        status="pending",
        source_session_id="session-1",
        source_message_id=selecting_message_id,
        evidence_message_id="message-1",
        clarification_id=consumed.clarification_id,
        created_at=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=24),
    )
    store.session.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "user_id": "user-1",
                "project_id": "workspace-1",
                "last_consumed_memory_clarification_id": (
                    consumed.clarification_id
                ),
                "last_consuming_memory_turn_id": selecting_message_id,
                "last_completed_turn_id": TURN_ID,
            },
        )
    )
    store.clarification.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=consumed.model_dump(mode="python"),
        )
    )
    store.origin.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "schema_version": "2.0",
                "proposal_id": proposal.proposal_id,
                "category": proposal.category,
                "source_session_id": proposal.source_session_id,
                "source_message_id": proposal.source_message_id,
                "evidence_message_id": proposal.evidence_message_id,
                "clarification_id": proposal.clarification_id,
                "created_at": NOW + timedelta(minutes=1),
            },
        )
    )
    store.proposal.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=proposal.model_dump(mode="python"),
        )
    )
    store.user.get = AsyncMock(return_value=snapshot(exists=False))

    result = await MemoryEngine(
        store.client
    ).consume_memory_clarification_to_proposal_v2(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_id=selecting_message_id,
        selection=MemoryClarificationSelection(
            selected_candidate_index=1,
        ),
        expected_clarification_id=consumed.clarification_id,
        observed_at=NOW + timedelta(minutes=2),
    )

    assert result == proposal
    assert all(
        write.args[0] not in (store.clarification, store.session)
        for write in store.transaction.set.call_args_list
    )


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

    with pytest.raises(MemoryClarificationConflictError):
        await MemoryEngine(store.client).create_memory_clarification(
            envelope=envelope(),
            observed_at=NOW,
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

    await MemoryEngine(store.client).create_memory_clarification(
        envelope=envelope(),
        observed_at=NOW,
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

    with pytest.raises(MemoryClarificationStateError, match="pointer"):
        await MemoryEngine(store.client).create_memory_clarification(
            envelope=envelope(),
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


def test_stored_clarification_rejects_non_deterministic_id() -> None:
    from database import MemoryClarificationStateError

    invalid_document = envelope().model_dump(mode="python")
    invalid_document["clarification_id"] = "tampered-clarification"

    with pytest.raises(MemoryClarificationStateError, match="invalid"):
        MemoryEngine._memory_clarification_from_document(invalid_document)
