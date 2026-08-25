import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore

from database import MemoryEngine, MemoryEngineError
from memory_proposals import (
    ProposalTurnLease,
    derive_proposal_origin_ids,
    derive_proposal_origin_ids_v2,
)


NOW = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)


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


def active_profile_document() -> dict[str, object]:
    return {
        "memory_schema_version": "1.0",
        "memory_revision": 1,
        "identity_context": {},
        "active_preferences": {
            "response_length": {
                "signal_id": "response_length--prior-signal",
                "category": "response_length",
                "value": "detailed",
                "policy_version": "1.0",
                "source_event_id": (
                    "response_length--prior-signal--approved"
                ),
                "approved_at": NOW - timedelta(days=1),
            }
        },
    }


def stored_proposal_document(
    *,
    proposal_id: str = (
        "response_length--e82366f7699ee2e39bff6a68154e09b7"
    ),
    value: str = "concise",
    expected_signal_id: str | None = "response_length--prior-signal",
    session_id: str = "session-1",
    message_id: str = "message-1",
    created_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(hours=24),
    status: str = "pending",
) -> dict[str, object]:
    return {
        "proposal_id": proposal_id,
        "category": "response_length",
        "proposed_value": value,
        "expected_signal_id": expected_signal_id,
        "policy_version": "1.0",
        "status": status,
        "source_session_id": session_id,
        "source_message_id": message_id,
        "created_at": created_at,
        "expires_at": expires_at,
        "resolved_at": None,
    }


def stored_origin_document(
    *,
    proposal_id: str = (
        "response_length--e82366f7699ee2e39bff6a68154e09b7"
    ),
    category: str = "response_length",
    session_id: str = "session-1",
    message_id: str = "message-1",
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "proposal_id": proposal_id,
        "category": category,
        "source_session_id": session_id,
        "source_message_id": message_id,
        "created_at": NOW,
    }


def stored_turn_document(
    *,
    turn_id: str,
    source_message_id: str,
    owner_token: str = "owner-1",
    lease_expires_at: datetime = NOW + timedelta(seconds=60),
    status: str = "in_progress",
    user_id: str = "user-1",
    actions: list[dict[str, object]] | None = None,
    memory_proposals: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "1.0",
        "status": status,
        "project_id": "project-1",
        "user_id": user_id,
        "memory_decision": None,
        "user_message_id": source_message_id,
        "model_message_id": f"turn--{turn_id}--model",
        "lease_owner": owner_token,
        "lease_expires_at": lease_expires_at,
        "created_at": NOW - timedelta(seconds=10),
        "updated_at": NOW - timedelta(seconds=10),
    }
    if actions is not None:
        document["actions"] = actions
    if memory_proposals is not None:
        document["memory_proposals"] = memory_proposals
    return document


def guarded_store() -> SimpleNamespace:
    client = MagicMock()
    users = MagicMock(name="users")
    user = MagicMock(name="user")
    origins = MagicMock(name="origins")
    origin = MagicMock(name="origin")
    proposals = MagicMock(name="proposals")
    proposal = MagicMock(name="proposal")
    sessions = MagicMock(name="sessions")
    session = MagicMock(name="session")
    turns = MagicMock(name="turns")
    turn = MagicMock(name="turn")
    transaction = MagicMock(name="transaction")

    def collection(name: str):
        if name == "users":
            return users
        if name == "sessions":
            return sessions
        raise AssertionError(f"unexpected root collection: {name}")

    def user_collection(name: str):
        if name == "memory_proposal_origins":
            return origins
        if name == "memory_proposals":
            return proposals
        raise AssertionError(f"unexpected user collection: {name}")

    client.collection.side_effect = collection
    users.document.return_value = user
    user.collection.side_effect = user_collection
    origins.document.return_value = origin
    proposals.document.return_value = proposal
    sessions.document.return_value = session
    session.collection.return_value = turns
    turns.document.return_value = turn
    client.transaction.return_value = transaction
    return SimpleNamespace(
        client=client,
        users=users,
        user=user,
        origins=origins,
        origin=origin,
        proposals=proposals,
        proposal=proposal,
        sessions=sessions,
        session=session,
        turns=turns,
        turn=turn,
        transaction=transaction,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_update",
    (
        {"user_id": ""},
        {"session_id": "invalid/session"},
        {"source_message_id": ""},
        {"category": "unknown"},
        {"proposed_value": " concise "},
        {
            "origin_ids": derive_proposal_origin_ids(
                "user-1",
                "session-1",
                "different-message",
                "response_length",
            )
        },
        {"observed_at": datetime(2026, 8, 21, 15, 0)},
        {"turn_lease": object()},
    ),
)
async def test_guarded_proposal_validates_before_firestore_access(
    invalid_update: dict[str, object],
) -> None:
    store = guarded_store()
    kwargs: dict[str, object] = {
        "user_id": "user-1",
        "session_id": "session-1",
        "source_message_id": "message-1",
        "origin_ids": derive_proposal_origin_ids(
            "user-1",
            "session-1",
            "message-1",
            "response_length",
        ),
        "category": "response_length",
        "proposed_value": "concise",
        "observed_at": NOW,
        "turn_lease": None,
    }
    kwargs.update(invalid_update)

    with pytest.raises(ValueError):
        await MemoryEngine(
            store.client
        ).create_guarded_memory_proposal(**kwargs)

    store.client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_guarded_proposal_reads_all_state_before_atomic_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = guarded_store()
    operation_order: list[str] = []

    async def read_origin(**kwargs):
        operation_order.append("origin")
        return snapshot(exists=False)

    async def read_proposal(**kwargs):
        operation_order.append("proposal")
        return snapshot(exists=False)

    async def read_profile(**kwargs):
        operation_order.append("profile")
        return snapshot(exists=True, data=active_profile_document())

    store.origin.get = AsyncMock(side_effect=read_origin)
    store.proposal.get = AsyncMock(side_effect=read_proposal)
    store.user.get = AsyncMock(side_effect=read_profile)

    def write(*args, **kwargs) -> None:
        operation_order.append("write")

    store.transaction.set.side_effect = write
    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        "message-1",
        "response_length",
    )

    result = await MemoryEngine(
        store.client
    ).create_guarded_memory_proposal(
        user_id="user-1",
        session_id="session-1",
        source_message_id="message-1",
        origin_ids=ids,
        category="response_length",
        proposed_value="concise",
        observed_at=NOW,
        turn_lease=None,
    )

    assert operation_order == ["origin", "proposal", "profile", "write", "write"]
    assert result.expected_signal_id == "response_length--prior-signal"
    assert result.created_at == NOW
    assert result.expires_at == NOW + timedelta(hours=24)
    assert store.transaction.set.call_args_list == [
        call(
            store.proposal,
            {
                "proposal_id": (
                    "response_length--e82366f7699ee2e39bff6a68154e09b7"
                ),
                "category": "response_length",
                "proposed_value": "concise",
                "expected_signal_id": "response_length--prior-signal",
                "policy_version": "1.0",
                "status": "pending",
                "source_session_id": "session-1",
                "source_message_id": "message-1",
                "created_at": firestore.SERVER_TIMESTAMP,
                "expires_at": NOW + timedelta(hours=24),
                "resolved_at": None,
            },
        ),
        call(
            store.origin,
            {
                "schema_version": "1.0",
                "proposal_id": (
                    "response_length--e82366f7699ee2e39bff6a68154e09b7"
                ),
                "category": "response_length",
                "source_session_id": "session-1",
                "source_message_id": "message-1",
                "created_at": firestore.SERVER_TIMESTAMP,
            },
        ),
    ]
    origin_document = store.transaction.set.call_args_list[1].args[1]
    assert "proposed_value" not in origin_document
    assert "source_message_text" not in origin_document


@pytest.mark.asyncio
async def test_guarded_proposal_rejects_already_active_value_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import MemorySignalAlreadyActiveError

    install_transaction_runner(monkeypatch)
    store = guarded_store()
    profile = active_profile_document()
    profile["active_preferences"]["response_length"]["value"] = "concise"
    store.origin.get = AsyncMock(return_value=snapshot(exists=False))
    store.proposal.get = AsyncMock(return_value=snapshot(exists=False))
    store.user.get = AsyncMock(
        return_value=snapshot(exists=True, data=profile)
    )
    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        "message-1",
        "response_length",
    )

    with pytest.raises(MemorySignalAlreadyActiveError):
        await MemoryEngine(
            store.client
        ).create_guarded_memory_proposal(
            user_id="user-1",
            session_id="session-1",
            source_message_id="message-1",
            origin_ids=ids,
            category="response_length",
            proposed_value="concise",
            observed_at=NOW,
            turn_lease=None,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_guarded_proposal_preserves_unexpired_category_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import MemoryProposalConflictError

    install_transaction_runner(monkeypatch)
    store = guarded_store()
    store.origin.get = AsyncMock(return_value=snapshot(exists=False))
    store.proposal.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=stored_proposal_document(
                proposal_id="response_length--other-origin",
                value="detailed",
                expected_signal_id=None,
                session_id="another-session",
                message_id="another-message",
            ),
        )
    )
    store.user.get = AsyncMock(return_value=snapshot(exists=False))
    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        "message-1",
        "response_length",
    )

    with pytest.raises(MemoryProposalConflictError):
        await MemoryEngine(
            store.client
        ).create_guarded_memory_proposal(
            user_id="user-1",
            session_id="session-1",
            source_message_id="message-1",
            origin_ids=ids,
            category="response_length",
            proposed_value="concise",
            observed_at=NOW,
            turn_lease=None,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_guarded_proposal_identical_origin_retry_preserves_first_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = guarded_store()
    first_created_at = NOW - timedelta(hours=1)
    first_expires_at = NOW + timedelta(hours=23)
    store.origin.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_origin_document())
    )
    store.proposal.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=stored_proposal_document(
                created_at=first_created_at,
                expires_at=first_expires_at,
            ),
        )
    )
    store.user.get = AsyncMock(
        return_value=snapshot(exists=True, data=active_profile_document())
    )
    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        "message-1",
        "response_length",
    )

    result = await MemoryEngine(
        store.client
    ).create_guarded_memory_proposal(
        user_id="user-1",
        session_id="session-1",
        source_message_id="message-1",
        origin_ids=ids,
        category="response_length",
        proposed_value="concise",
        observed_at=NOW,
        turn_lease=None,
    )

    assert result.created_at == first_created_at
    assert result.expires_at == first_expires_at
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_guarded_proposal_changed_origin_retry_conflicts_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import MemoryProposalOriginConflictError

    install_transaction_runner(monkeypatch)
    store = guarded_store()
    store.origin.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_origin_document())
    )
    store.proposal.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=stored_proposal_document(value="detailed"),
        )
    )
    store.user.get = AsyncMock(
        return_value=snapshot(exists=True, data=active_profile_document())
    )
    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        "message-1",
        "response_length",
    )

    with pytest.raises(MemoryProposalOriginConflictError):
        await MemoryEngine(
            store.client
        ).create_guarded_memory_proposal(
            user_id="user-1",
            session_id="session-1",
            source_message_id="message-1",
            origin_ids=ids,
            category="response_length",
            proposed_value="concise",
            observed_at=NOW,
            turn_lease=None,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stale_state", ("expected_signal", "status"))
async def test_guarded_proposal_stale_origin_retry_conflicts_without_write(
    monkeypatch: pytest.MonkeyPatch,
    stale_state: str,
) -> None:
    from database import MemoryProposalOriginConflictError

    install_transaction_runner(monkeypatch)
    store = guarded_store()
    profile = active_profile_document()
    proposal_data = stored_proposal_document()
    if stale_state == "expected_signal":
        profile["active_preferences"]["response_length"]["signal_id"] = (
            "response_length--newer-signal"
        )
    else:
        proposal_data["status"] = "approved"
    store.origin.get = AsyncMock(
        return_value=snapshot(exists=True, data=stored_origin_document())
    )
    store.proposal.get = AsyncMock(
        return_value=snapshot(exists=True, data=proposal_data)
    )
    store.user.get = AsyncMock(
        return_value=snapshot(exists=True, data=profile)
    )
    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        "message-1",
        "response_length",
    )

    with pytest.raises(MemoryProposalOriginConflictError):
        await MemoryEngine(
            store.client
        ).create_guarded_memory_proposal(
            user_id="user-1",
            session_id="session-1",
            source_message_id="message-1",
            origin_ids=ids,
            category="response_length",
            proposed_value="concise",
            observed_at=NOW,
            turn_lease=None,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_guarded_proposal_records_owned_turn_effect_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = guarded_store()
    turn_id = "a" * 64
    source_message_id = f"turn--{turn_id}--user"
    operation_order: list[str] = []

    async def read_origin(**kwargs):
        operation_order.append("origin")
        return snapshot(exists=False)

    async def read_proposal(**kwargs):
        operation_order.append("proposal")
        return snapshot(exists=False)

    async def read_profile(**kwargs):
        operation_order.append("profile")
        return snapshot(exists=False)

    async def read_turn(**kwargs):
        operation_order.append("turn")
        return snapshot(
            exists=True,
            data=stored_turn_document(
                turn_id=turn_id,
                source_message_id=source_message_id,
            ),
        )

    store.origin.get = AsyncMock(side_effect=read_origin)
    store.proposal.get = AsyncMock(side_effect=read_proposal)
    store.user.get = AsyncMock(side_effect=read_profile)
    store.turn.get = AsyncMock(side_effect=read_turn)
    store.transaction.set.side_effect = lambda *args, **kwargs: (
        operation_order.append("write")
    )
    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        source_message_id,
        "response_length",
    )

    result = await MemoryEngine(
        store.client
    ).create_guarded_memory_proposal(
        user_id="user-1",
        session_id="session-1",
        source_message_id=source_message_id,
        origin_ids=ids,
        category="response_length",
        proposed_value="concise",
        observed_at=NOW,
        turn_lease=ProposalTurnLease(
            turn_id=turn_id,
            owner_token="owner-1",
        ),
    )

    assert operation_order == [
        "origin",
        "proposal",
        "profile",
        "turn",
        "write",
        "write",
        "write",
    ]
    assert store.transaction.set.call_args_list[-1] == call(
        store.turn,
        {
            "actions": [
                {
                    "action_name": "propose_memory_signal",
                    "status": "completed",
                }
            ],
            "memory_proposals": [
                {
                    "proposal_id": result.proposal_id,
                    "category": "response_length",
                    "proposed_value": "concise",
                    "expires_at": NOW + timedelta(hours=24),
                }
            ],
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_guarded_v2_proposal_persists_provenance_and_turn_effect_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = guarded_store()
    turn_id = "b" * 64
    source_message_id = f"turn--{turn_id}--user"
    store.origin.get = AsyncMock(return_value=snapshot(exists=False))
    store.proposal.get = AsyncMock(return_value=snapshot(exists=False))
    store.user.get = AsyncMock(return_value=snapshot(exists=False))
    store.turn.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=stored_turn_document(
                turn_id=turn_id,
                source_message_id=source_message_id,
            ),
        )
    )
    ids = derive_proposal_origin_ids_v2(
        "user-1",
        "session-1",
        source_message_id,
        "development_environments",
    )

    result = await MemoryEngine(
        store.client
    ).create_guarded_memory_proposal_v2(
        user_id="user-1",
        session_id="session-1",
        source_message_id=source_message_id,
        evidence_message_id=source_message_id,
        clarification_id=None,
        origin_ids=ids,
        category="development_environments",
        proposed_value=["linux", "macos"],
        observed_at=NOW,
        turn_lease=ProposalTurnLease(
            turn_id=turn_id,
            owner_token="owner-1",
        ),
    )

    assert result.policy_version == "2.0"
    assert result.evidence_message_id == source_message_id
    assert store.transaction.set.call_args_list == [
        call(
            store.proposal,
            {
                "proposal_id": ids.proposal_id,
                "category": "development_environments",
                "proposed_value": ["macos", "linux"],
                "expected_signal_id": None,
                "policy_version": "2.0",
                "status": "pending",
                "source_session_id": "session-1",
                "source_message_id": source_message_id,
                "evidence_message_id": source_message_id,
                "clarification_id": None,
                "created_at": firestore.SERVER_TIMESTAMP,
                "expires_at": NOW + timedelta(hours=24),
            },
        ),
        call(
            store.origin,
            {
                "schema_version": "2.0",
                "proposal_id": ids.proposal_id,
                "category": "development_environments",
                "source_session_id": "session-1",
                "source_message_id": source_message_id,
                "evidence_message_id": source_message_id,
                "clarification_id": None,
                "created_at": firestore.SERVER_TIMESTAMP,
            },
        ),
        call(
            store.turn,
            {
                "actions": [
                    {
                        "action_name": "propose_memory_signal",
                        "status": "completed",
                    }
                ],
                "memory_proposals": [
                    {
                        "proposal_id": ids.proposal_id,
                        "category": "development_environments",
                        "proposed_value": ["macos", "linux"],
                        "policy_version": "2.0",
                        "expires_at": NOW + timedelta(hours=24),
                    }
                ],
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "turn_updates",
    (
        {"owner_token": "another-owner"},
        {"lease_expires_at": NOW},
        {"status": "completed"},
        {"user_id": "another-user"},
        {"stored_source_message_id": "another-message"},
    ),
)
async def test_guarded_proposal_rejects_stale_or_mismatched_turn_before_write(
    monkeypatch: pytest.MonkeyPatch,
    turn_updates: dict[str, object],
) -> None:
    from chat_turns import ChatTurnOwnershipError

    install_transaction_runner(monkeypatch)
    store = guarded_store()
    turn_id = "a" * 64
    source_message_id = f"turn--{turn_id}--user"
    store.origin.get = AsyncMock(return_value=snapshot(exists=False))
    store.proposal.get = AsyncMock(return_value=snapshot(exists=False))
    store.user.get = AsyncMock(return_value=snapshot(exists=False))
    stored_updates = dict(turn_updates)
    stored_source_message_id = stored_updates.pop(
        "stored_source_message_id",
        source_message_id,
    )
    turn_data = stored_turn_document(
        turn_id=turn_id,
        source_message_id=stored_source_message_id,
        **stored_updates,
    )
    store.turn.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_data)
    )
    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        source_message_id,
        "response_length",
    )

    with pytest.raises(ChatTurnOwnershipError):
        await MemoryEngine(
            store.client
        ).create_guarded_memory_proposal(
            user_id="user-1",
            session_id="session-1",
            source_message_id=source_message_id,
            origin_ids=ids,
            category="response_length",
            proposed_value="concise",
            observed_at=NOW,
            turn_lease=ProposalTurnLease(
                turn_id=turn_id,
                owner_token="owner-1",
            ),
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("conflicting", (False, True))
async def test_guarded_proposal_validates_precompleted_turn_effect(
    monkeypatch: pytest.MonkeyPatch,
    conflicting: bool,
) -> None:
    from chat_turns import ChatTurnStateError

    install_transaction_runner(monkeypatch)
    store = guarded_store()
    turn_id = "a" * 64
    source_message_id = f"turn--{turn_id}--user"
    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        source_message_id,
        "response_length",
    )
    proposal_data = stored_proposal_document(
        proposal_id=ids.proposal_id,
        expected_signal_id=None,
        message_id=source_message_id,
    )
    origin_data = stored_origin_document(
        proposal_id=ids.proposal_id,
        message_id=source_message_id,
    )
    receipt_value = "detailed" if conflicting else "concise"
    store.origin.get = AsyncMock(
        return_value=snapshot(exists=True, data=origin_data)
    )
    store.proposal.get = AsyncMock(
        return_value=snapshot(exists=True, data=proposal_data)
    )
    store.user.get = AsyncMock(return_value=snapshot(exists=False))
    store.turn.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=stored_turn_document(
                turn_id=turn_id,
                source_message_id=source_message_id,
                actions=[
                    {
                        "action_name": "propose_memory_signal",
                        "status": "completed",
                    }
                ],
                memory_proposals=[
                    {
                        "proposal_id": ids.proposal_id,
                        "category": "response_length",
                        "proposed_value": receipt_value,
                        "expires_at": NOW + timedelta(hours=24),
                    }
                ],
            ),
        )
    )

    invocation = MemoryEngine(store.client).create_guarded_memory_proposal(
        user_id="user-1",
        session_id="session-1",
        source_message_id=source_message_id,
        origin_ids=ids,
        category="response_length",
        proposed_value="concise",
        observed_at=NOW,
        turn_lease=ProposalTurnLease(
            turn_id=turn_id,
            owner_token="owner-1",
        ),
    )
    if conflicting:
        with pytest.raises(ChatTurnStateError):
            await invocation
    else:
        result = await invocation
        assert result.proposal_id == ids.proposal_id

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_guarded_proposal_preserves_unrelated_turn_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = guarded_store()
    turn_id = "a" * 64
    source_message_id = f"turn--{turn_id}--user"
    store.origin.get = AsyncMock(return_value=snapshot(exists=False))
    store.proposal.get = AsyncMock(return_value=snapshot(exists=False))
    store.user.get = AsyncMock(return_value=snapshot(exists=False))
    unrelated_action = {
        "action_name": "google_search",
        "status": "completed",
    }
    store.turn.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=stored_turn_document(
                turn_id=turn_id,
                source_message_id=source_message_id,
                actions=[unrelated_action],
            ),
        )
    )
    ids = derive_proposal_origin_ids(
        "user-1",
        "session-1",
        source_message_id,
        "response_length",
    )

    await MemoryEngine(store.client).create_guarded_memory_proposal(
        user_id="user-1",
        session_id="session-1",
        source_message_id=source_message_id,
        origin_ids=ids,
        category="response_length",
        proposed_value="concise",
        observed_at=NOW,
        turn_lease=ProposalTurnLease(
            turn_id=turn_id,
            owner_token="owner-1",
        ),
    )

    turn_update = store.transaction.set.call_args_list[-1]
    assert turn_update == call(
        store.turn,
        {
            "actions": [
                unrelated_action,
                {
                    "action_name": "propose_memory_signal",
                    "status": "completed",
                },
            ],
            "memory_proposals": [
                {
                    "proposal_id": ids.proposal_id,
                    "category": "response_length",
                    "proposed_value": "concise",
                    "expires_at": NOW + timedelta(hours=24),
                }
            ],
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


@pytest.mark.asyncio
async def test_guarded_proposal_preserves_firestore_error_safely(
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
    store = guarded_store()
    source_message_id = "private-source-message"
    ids = derive_proposal_origin_ids(
        "private-user-id",
        "private-session-id",
        source_message_id,
        "response_length",
    )
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(
            store.client
        ).create_guarded_memory_proposal(
            user_id="private-user-id",
            session_id="private-session-id",
            source_message_id=source_message_id,
            origin_ids=ids,
            category="response_length",
            proposed_value="concise",
            observed_at=NOW,
            turn_lease=None,
        )

    assert caught.value.__cause__ is firestore_error
    assert str(caught.value) == (
        "Firestore create_guarded_memory_proposal operation failed."
    )
    for private_text in (
        "private-user-id",
        "private-session-id",
        source_message_id,
        "concise",
        "private-backend-detail",
    ):
        assert private_text not in caplog.text
