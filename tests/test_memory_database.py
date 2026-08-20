import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore

from database import MemoryEngine, MemoryEngineError
from schemas import MemoryProposal


NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


def proposal(
    *,
    proposal_id: str = "response_length--proposal-1",
    value: str = "concise",
    status: str = "pending",
    created_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(hours=24),
) -> MemoryProposal:
    return MemoryProposal.model_validate(
        {
            "proposal_id": proposal_id,
            "category": "response_length",
            "proposed_value": value,
            "expected_signal_id": None,
            "policy_version": "1.0",
            "status": status,
            "source_session_id": "source-session",
            "source_message_id": "source-message",
            "created_at": created_at,
            "expires_at": expires_at,
        }
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


def proposal_store() -> tuple[
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    proposals = MagicMock()
    proposal_ref = MagicMock()
    client.collection.return_value = users
    users.document.return_value = user
    user.collection.return_value = proposals
    proposals.document.return_value = proposal_ref
    return client, users, user, proposals, proposal_ref


def stored_proposal(
    candidate: MemoryProposal,
    *,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    status: str | None = None,
) -> dict[str, object]:
    document = candidate.model_dump(mode="python")
    document["created_at"] = created_at or candidate.created_at
    document["expires_at"] = expires_at or candidate.expires_at
    document["status"] = status or candidate.status
    document["resolved_at"] = None
    return document


@pytest.mark.asyncio
async def test_create_memory_proposal_writes_only_category_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, users, user, proposals, proposal_ref = proposal_store()
    transaction = MagicMock()
    snapshot = SimpleNamespace(exists=False, to_dict=lambda: None)
    proposal_ref.get = AsyncMock(return_value=snapshot)
    client.transaction.return_value = transaction
    candidate = proposal()

    result = await MemoryEngine(client).create_memory_proposal(
        "user-1",
        candidate,
        observed_at=NOW,
    )

    assert result is candidate
    client.collection.assert_called_once_with("users")
    users.document.assert_called_once_with("user-1")
    user.collection.assert_called_once_with("memory_proposals")
    proposals.document.assert_called_once_with("response_length")
    proposal_ref.get.assert_awaited_once_with(transaction=transaction)
    transaction.set.assert_called_once_with(
        proposal_ref,
        {
            "proposal_id": "response_length--proposal-1",
            "category": "response_length",
            "proposed_value": "concise",
            "expected_signal_id": None,
            "policy_version": "1.0",
            "status": "pending",
            "source_session_id": "source-session",
            "source_message_id": "source-message",
            "created_at": firestore.SERVER_TIMESTAMP,
            "expires_at": NOW + timedelta(hours=24),
            "resolved_at": None,
        },
    )
    user.get.assert_not_called()
    user.set.assert_not_called()


@pytest.mark.asyncio
async def test_create_memory_proposal_reads_before_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, _, _, proposal_ref = proposal_store()
    transaction = MagicMock()
    operation_order: list[str] = []

    async def read_snapshot(*, transaction):
        operation_order.append("read")
        return SimpleNamespace(exists=False, to_dict=lambda: None)

    def write_proposal(*args, **kwargs) -> None:
        operation_order.append("write")

    proposal_ref.get = AsyncMock(side_effect=read_snapshot)
    transaction.set.side_effect = write_proposal
    client.transaction.return_value = transaction

    await MemoryEngine(client).create_memory_proposal(
        "user-1",
        proposal(),
        observed_at=NOW,
    )

    assert operation_order == ["read", "write"]


@pytest.mark.asyncio
async def test_create_memory_proposal_returns_identical_unexpired_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, _, _, proposal_ref = proposal_store()
    transaction = MagicMock()
    candidate = proposal()
    stored_created_at = NOW + timedelta(milliseconds=20)
    snapshot = SimpleNamespace(
        exists=True,
        to_dict=lambda: stored_proposal(
            candidate,
            created_at=stored_created_at,
        ),
    )
    proposal_ref.get = AsyncMock(return_value=snapshot)
    client.transaction.return_value = transaction

    result = await MemoryEngine(client).create_memory_proposal(
        "user-1",
        candidate,
        observed_at=NOW + timedelta(seconds=1),
    )

    assert result.proposal_id == candidate.proposal_id
    assert result.created_at == stored_created_at
    transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_create_memory_proposal_rejects_different_unexpired_slot(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from database import MemoryProposalConflictError

    install_transaction_runner(monkeypatch)
    client, _, _, _, proposal_ref = proposal_store()
    transaction = MagicMock()
    existing = proposal()
    snapshot = SimpleNamespace(
        exists=True,
        to_dict=lambda: stored_proposal(existing),
    )
    proposal_ref.get = AsyncMock(return_value=snapshot)
    client.transaction.return_value = transaction
    candidate = proposal(
        proposal_id="response_length--proposal-2",
        value="detailed",
    )
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryProposalConflictError) as caught:
        await MemoryEngine(client).create_memory_proposal(
            "user-1",
            candidate,
            observed_at=NOW + timedelta(seconds=1),
        )

    assert str(caught.value) == (
        "An unexpired memory proposal already occupies this category."
    )
    transaction.set.assert_not_called()
    assert caplog.text == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_status", "stored_expires_at"),
    (
        ("pending", NOW - timedelta(seconds=1)),
        ("approved", NOW + timedelta(hours=1)),
        ("rejected", NOW + timedelta(hours=1)),
    ),
)
async def test_create_memory_proposal_replaces_expired_or_resolved_slot(
    monkeypatch: pytest.MonkeyPatch,
    stored_status: str,
    stored_expires_at: datetime,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, user, _, proposal_ref = proposal_store()
    transaction = MagicMock()
    existing = proposal()
    snapshot = SimpleNamespace(
        exists=True,
        to_dict=lambda: stored_proposal(
            existing,
            expires_at=stored_expires_at,
            status=stored_status,
        ),
    )
    proposal_ref.get = AsyncMock(return_value=snapshot)
    client.transaction.return_value = transaction
    candidate = proposal(
        proposal_id="response_length--proposal-2",
        value="detailed",
    )

    result = await MemoryEngine(client).create_memory_proposal(
        "user-1",
        candidate,
        observed_at=NOW,
    )

    assert result is candidate
    transaction.set.assert_called_once_with(
        proposal_ref,
        {
            "proposal_id": "response_length--proposal-2",
            "category": "response_length",
            "proposed_value": "detailed",
            "expected_signal_id": None,
            "policy_version": "1.0",
            "status": "pending",
            "source_session_id": "source-session",
            "source_message_id": "source-message",
            "created_at": firestore.SERVER_TIMESTAMP,
            "expires_at": NOW + timedelta(hours=24),
            "resolved_at": None,
        },
    )
    user.get.assert_not_called()
    user.set.assert_not_called()


@pytest.mark.asyncio
async def test_create_memory_proposal_treats_deadline_as_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, _, _, proposal_ref = proposal_store()
    transaction = MagicMock()
    existing = proposal()
    snapshot = SimpleNamespace(
        exists=True,
        to_dict=lambda: stored_proposal(
            existing,
            expires_at=NOW,
        ),
    )
    proposal_ref.get = AsyncMock(return_value=snapshot)
    client.transaction.return_value = transaction
    candidate = proposal(
        proposal_id="response_length--proposal-2",
        value="detailed",
    )

    result = await MemoryEngine(client).create_memory_proposal(
        "user-1",
        candidate,
        observed_at=NOW,
    )

    assert result is candidate
    transaction.set.assert_called_once()


NAIVE_NOW = datetime(2026, 8, 20, 15, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "candidate", "observed_at"),
    (
        ("", proposal(), NOW),
        ("user/other", proposal(), NOW),
        ("x" * 129, proposal(), NOW),
        ("user-1", object(), NOW),
        ("user-1", proposal(status="approved"), NOW),
        (
            "user-1",
            proposal(proposal_id="formatting_style--proposal-1"),
            NOW,
        ),
        (
            "user-1",
            proposal(expires_at=NOW + timedelta(hours=23)),
            NOW,
        ),
        ("user-1", proposal(expires_at=NOW), NOW),
        ("user-1", proposal(), NAIVE_NOW),
        (
            "user-1",
            proposal(
                created_at=NAIVE_NOW,
                expires_at=NAIVE_NOW + timedelta(hours=24),
            ),
            NOW,
        ),
        (
            "user-1",
            proposal(expires_at=NAIVE_NOW + timedelta(hours=24)),
            NOW,
        ),
        (
            "user-1",
            proposal(
                created_at=NOW + timedelta(seconds=1),
                expires_at=NOW + timedelta(hours=24, seconds=1),
            ),
            NOW,
        ),
        (
            "user-1",
            proposal(proposal_id="response_length--"),
            NOW,
        ),
    ),
)
async def test_create_memory_proposal_rejects_invalid_input_before_access(
    monkeypatch: pytest.MonkeyPatch,
    user_id: str,
    candidate: object,
    observed_at: datetime,
) -> None:
    install_transaction_runner(monkeypatch)
    client = MagicMock()

    with pytest.raises(ValueError):
        await MemoryEngine(client).create_memory_proposal(
            user_id,
            candidate,
            observed_at=observed_at,
        )

    client.collection.assert_not_called()
    client.transaction.assert_not_called()


@pytest.mark.asyncio
async def test_create_memory_proposal_preserves_firestore_error_safely(
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
    candidate = proposal()
    private_values = (
        "private-user-id",
        "source-session",
        "source-message",
        "concise",
        "private-backend-detail",
    )
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).create_memory_proposal(
            "private-user-id",
            candidate,
            observed_at=NOW,
        )

    assert caught.value.__cause__ is firestore_error
    assert str(caught.value) == (
        "Firestore create_memory_proposal operation failed."
    )
    for private_text in private_values:
        assert private_text not in caplog.text


@pytest.mark.asyncio
async def test_create_memory_proposal_translates_invalid_stored_document(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, _, _, proposal_ref = proposal_store()
    transaction = MagicMock()
    candidate = proposal()
    invalid_document = stored_proposal(candidate)
    invalid_document.pop("source_message_id")
    snapshot = SimpleNamespace(
        exists=True,
        to_dict=lambda: invalid_document,
    )
    proposal_ref.get = AsyncMock(return_value=snapshot)
    client.transaction.return_value = transaction
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).create_memory_proposal(
            "private-user-id",
            candidate,
            observed_at=NOW,
        )

    assert isinstance(caught.value.__cause__, ValueError)
    assert "private-user-id" not in caplog.text
    assert "source-session" not in caplog.text
    assert "source-message" not in caplog.text
    assert "concise" not in caplog.text


@pytest.mark.asyncio
async def test_create_memory_proposal_translates_non_mapping_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, _, _, _, proposal_ref = proposal_store()
    transaction = MagicMock()
    snapshot = SimpleNamespace(exists=True, to_dict=lambda: None)
    proposal_ref.get = AsyncMock(return_value=snapshot)
    client.transaction.return_value = transaction

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).create_memory_proposal(
            "private-user-id",
            proposal(),
            observed_at=NOW,
        )

    assert isinstance(caught.value.__cause__, ValueError)
