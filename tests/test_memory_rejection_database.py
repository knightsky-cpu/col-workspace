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


NOW = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)
PROPOSAL_ID = "response_length--proposal-1"


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
    status: str = "pending",
    proposal_id: str = PROPOSAL_ID,
) -> dict[str, object]:
    return {
        "proposal_id": proposal_id,
        "category": "response_length",
        "proposed_value": "concise",
        "expected_signal_id": None,
        "policy_version": "1.0",
        "status": status,
        "source_session_id": "source-session",
        "source_message_id": "source-message",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=24),
        "resolved_at": None,
    }


def rejection_store() -> tuple[
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
    return client, user, proposal_ref, proposals


@pytest.mark.asyncio
async def test_reject_memory_proposal_resolves_without_activating_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, proposal_ref, _ = rejection_store()
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
        return SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "memory_schema_version": "1.0",
                "memory_revision": 0,
                "identity_context": {},
                "active_preferences": {},
            },
        )

    proposal_ref.get = AsyncMock(side_effect=read_proposal)
    user.get = AsyncMock(side_effect=read_profile)
    transaction.set.side_effect = lambda *args, **kwargs: operations.append(
        "write"
    )

    result = await MemoryEngine(client).reject_memory_proposal(
        "user-1",
        "response_length",
        PROPOSAL_ID,
        observed_at=NOW,
    )

    assert result.profile.memory_revision == 0
    assert result.profile.identity_context == {}
    assert result.profile.active_preferences == {}
    assert result.proposal.proposal_id == PROPOSAL_ID
    assert result.proposal.status == "rejected"
    assert operations == ["read-proposal", "read-profile", "write"]
    transaction.set.assert_called_once_with(
        proposal_ref,
        {
            "status": "rejected",
            "resolved_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    transaction.delete.assert_not_called()
    user.set.assert_not_called()
    assert call("memory_events") not in user.collection.call_args_list


@pytest.mark.asyncio
async def test_reject_memory_proposal_returns_existing_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, proposal_ref, _ = rejection_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: pending_proposal_document(status="rejected"),
        )
    )
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

    result = await MemoryEngine(client).reject_memory_proposal(
        "user-1",
        "response_length",
        PROPOSAL_ID,
        observed_at=NOW + timedelta(hours=1),
    )

    assert result.profile.memory_revision == 2
    assert result.proposal.status == "rejected"
    transaction.set.assert_not_called()
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exists", "document", "error_type"),
    (
        (False, None, MemoryProposalNotFoundError),
        (
            True,
            pending_proposal_document(status="approved"),
            MemoryProposalConflictError,
        ),
        (
            True,
            pending_proposal_document(
                proposal_id="response_length--newer-proposal"
            ),
            MemoryProposalConflictError,
        ),
    ),
)
async def test_reject_memory_proposal_fails_for_unavailable_decision(
    monkeypatch: pytest.MonkeyPatch,
    exists: bool,
    document: dict[str, object] | None,
    error_type: type[RuntimeError],
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, proposal_ref, _ = rejection_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    proposal_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=exists,
            to_dict=lambda: document,
        )
    )
    user.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )

    with pytest.raises(error_type):
        await MemoryEngine(client).reject_memory_proposal(
            "user-1",
            "response_length",
            PROPOSAL_ID,
            observed_at=NOW,
        )

    transaction.set.assert_not_called()
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
async def test_reject_memory_proposal_rejects_expired_pending_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, proposal_ref, _ = rejection_store()
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

    with pytest.raises(MemoryProposalExpiredError):
        await MemoryEngine(client).reject_memory_proposal(
            "user-1",
            "response_length",
            PROPOSAL_ID,
            observed_at=NOW + timedelta(hours=24),
        )

    transaction.set.assert_not_called()
    transaction.delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "category", "proposal_id", "observed_at"),
    (
        ("has/slash", "response_length", PROPOSAL_ID, NOW),
        ("user-1", "unknown", PROPOSAL_ID, NOW),
        (
            "user-1",
            "response_length",
            "formatting_style--proposal-1",
            NOW,
        ),
        ("user-1", "response_length", PROPOSAL_ID, NOW.replace(tzinfo=None)),
    ),
)
async def test_reject_memory_proposal_validates_before_firestore_access(
    user_id: str,
    category: str,
    proposal_id: str,
    observed_at: datetime,
) -> None:
    client = MagicMock()

    with pytest.raises(ValueError):
        await MemoryEngine(client).reject_memory_proposal(
            user_id,
            category,
            proposal_id,
            observed_at=observed_at,
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_reject_memory_proposal_preserves_firestore_error_safely(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    install_transaction_runner(monkeypatch)
    client, user, proposal_ref, _ = rejection_store()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    firestore_error = ServiceUnavailable("private-backend-detail")
    proposal_ref.get = AsyncMock(side_effect=firestore_error)
    user.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).reject_memory_proposal(
            "private-user-id",
            "response_length",
            PROPOSAL_ID,
            observed_at=NOW,
        )

    assert caught.value.__cause__ is firestore_error
    assert str(caught.value) == (
        "Firestore reject_memory_proposal operation failed."
    )
    for private_value in (
        "private-user-id",
        PROPOSAL_ID,
        "concise",
        "private-backend-detail",
    ):
        assert private_value not in caplog.text
