from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath

from database import (
    MemoryEngine,
    MemoryEngineError,
    MemoryEventCursorNotFoundError,
)
from memory_policy import MEMORY_CATEGORY_ORDER
from schemas import CollaborationProfile, MemoryProposal


NOW = datetime(2026, 8, 20, 21, 0, tzinfo=UTC)


def proposal_document(
    *,
    proposal_id: str,
    category: str,
    status: str,
    expires_at: datetime,
) -> dict[str, object]:
    values = {
        "response_length": "concise",
        "example_usage": "when_helpful",
        "question_style": "ask_before_assuming",
        "formatting_style": "mixed",
    }
    return {
        "proposal_id": proposal_id,
        "category": category,
        "proposed_value": values[category],
        "expected_signal_id": None,
        "policy_version": "1.0",
        "status": status,
        "source_session_id": "source-session",
        "source_message_id": "source-message",
        "created_at": NOW - timedelta(hours=1),
        "expires_at": expires_at,
        "resolved_at": None,
    }


def event_document(*, event_number: int) -> dict[str, object]:
    return {
        "event_type": "approved",
        "signal_id": f"response_length--signal-{event_number}",
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
        "memory_revision": event_number + 1,
        "created_at": NOW,
    }


async def snapshot_stream(items: list[SimpleNamespace]):
    for item in items:
        yield item


def inspection_store() -> tuple[
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
    events = MagicMock()
    client.collection.return_value = users
    users.document.return_value = user
    user.collection.side_effect = lambda name: {
        "memory_proposals": proposals,
        "memory_events": events,
    }[name]
    return client, users, user, proposals, events


@pytest.mark.asyncio
async def test_memory_inspection_reads_only_governed_pending_slots() -> None:
    client, users, user, proposals, events = inspection_store()
    user.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "memory_schema_version": "1.0",
                "memory_revision": 4,
                "identity_context": {},
                "active_preferences": {},
            },
        )
    )
    proposal_refs = {
        category: MagicMock(name=f"proposal-{category}")
        for category in MEMORY_CATEGORY_ORDER
    }
    proposals.document.side_effect = proposal_refs.__getitem__
    client.get_all.return_value = snapshot_stream(
        [
            SimpleNamespace(
                exists=True,
                to_dict=lambda: proposal_document(
                    proposal_id="question_style--rejected",
                    category="question_style",
                    status="rejected",
                    expires_at=NOW + timedelta(hours=1),
                ),
            ),
            SimpleNamespace(
                exists=True,
                to_dict=lambda: proposal_document(
                    proposal_id="response_length--pending",
                    category="response_length",
                    status="pending",
                    expires_at=NOW + timedelta(hours=1),
                ),
            ),
            SimpleNamespace(
                exists=True,
                to_dict=lambda: proposal_document(
                    proposal_id="example_usage--expired",
                    category="example_usage",
                    status="pending",
                    expires_at=NOW,
                ),
            ),
            SimpleNamespace(
                exists=True,
                to_dict=lambda: proposal_document(
                    proposal_id="formatting_style--pending",
                    category="formatting_style",
                    status="pending",
                    expires_at=NOW + timedelta(hours=1),
                ),
            ),
        ]
    )
    first_order = MagicMock()
    second_order = MagicMock()
    limited_query = MagicMock()
    events.order_by.return_value = first_order
    first_order.order_by.return_value = second_order
    second_order.limit.return_value = limited_query
    limited_query.stream.return_value = snapshot_stream([])

    result = await MemoryEngine(client).get_memory_inspection(
        "user-1",
        observed_at=NOW,
    )

    assert result.profile == CollaborationProfile(memory_revision=4)
    assert result.unresolved_proposals == (
        MemoryProposal(
            proposal_id="response_length--pending",
            category="response_length",
            proposed_value="concise",
            expected_signal_id=None,
            status="pending",
            source_session_id="source-session",
            source_message_id="source-message",
            created_at=NOW - timedelta(hours=1),
            expires_at=NOW + timedelta(hours=1),
        ),
        MemoryProposal(
            proposal_id="formatting_style--pending",
            category="formatting_style",
            proposed_value="mixed",
            expected_signal_id=None,
            status="pending",
            source_session_id="source-session",
            source_message_id="source-message",
            created_at=NOW - timedelta(hours=1),
            expires_at=NOW + timedelta(hours=1),
        ),
    )
    assert result.events == ()
    assert result.next_event_id is None
    client.collection.assert_called_once_with("users")
    users.document.assert_called_once_with("user-1")
    proposals.document.assert_has_calls(
        [call(category) for category in MEMORY_CATEGORY_ORDER]
    )
    assert proposals.document.call_count == len(MEMORY_CATEGORY_ORDER)
    client.get_all.assert_called_once_with(
        [proposal_refs[category] for category in MEMORY_CATEGORY_ORDER]
    )
    events.order_by.assert_called_once_with(
        "created_at",
        direction=firestore.Query.DESCENDING,
    )
    first_order.order_by.assert_called_once_with(
        FieldPath.document_id(),
        direction=firestore.Query.DESCENDING,
    )
    second_order.limit.assert_called_once_with(51)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_event_count", "expected_next_event_id"),
    (
        (50, None),
        (51, "response_length--event-49"),
    ),
)
async def test_memory_inspection_bounds_events_and_next_cursor(
    stored_event_count: int,
    expected_next_event_id: str | None,
) -> None:
    client, _, user, proposals, events = inspection_store()
    user.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    proposals.document.side_effect = lambda category: MagicMock(
        name=f"proposal-{category}"
    )
    client.get_all.return_value = snapshot_stream([])
    event_snapshots = [
        SimpleNamespace(
            id=f"response_length--event-{event_number}",
            to_dict=lambda event_number=event_number: event_document(
                event_number=event_number
            ),
        )
        for event_number in range(stored_event_count)
    ]
    first_order = MagicMock()
    second_order = MagicMock()
    limited_query = MagicMock()
    events.order_by.return_value = first_order
    first_order.order_by.return_value = second_order
    second_order.limit.return_value = limited_query
    limited_query.stream.return_value = snapshot_stream(event_snapshots)

    result = await MemoryEngine(client).get_memory_inspection(
        "user-1",
        observed_at=NOW,
    )

    assert len(result.events) == 50
    assert result.events[0].event_id == "response_length--event-0"
    assert result.events[-1].event_id == "response_length--event-49"
    assert result.next_event_id == expected_next_event_id


@pytest.mark.asyncio
async def test_memory_inspection_starts_after_user_owned_cursor() -> None:
    client, _, user, proposals, events = inspection_store()
    user.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    proposals.document.side_effect = lambda category: MagicMock(
        name=f"proposal-{category}"
    )
    client.get_all.return_value = snapshot_stream([])
    cursor_id = "response_length--cursor--approved"
    cursor_snapshot = SimpleNamespace(
        id=cursor_id,
        exists=True,
        to_dict=lambda: event_document(event_number=9),
    )
    cursor_ref = MagicMock()
    cursor_ref.get = AsyncMock(return_value=cursor_snapshot)
    events.document.return_value = cursor_ref
    first_order = MagicMock()
    second_order = MagicMock()
    cursor_query = MagicMock()
    limited_query = MagicMock()
    events.order_by.return_value = first_order
    first_order.order_by.return_value = second_order
    second_order.start_after.return_value = cursor_query
    second_order.limit.return_value = limited_query
    cursor_query.limit.return_value = limited_query
    limited_query.stream.return_value = snapshot_stream([])

    result = await MemoryEngine(client).get_memory_inspection(
        "user-1",
        observed_at=NOW,
        after_event_id=cursor_id,
    )

    assert result.events == ()
    events.document.assert_called_once_with(cursor_id)
    cursor_ref.get.assert_awaited_once_with()
    second_order.start_after.assert_called_once_with(cursor_snapshot)
    cursor_query.limit.assert_called_once_with(51)


@pytest.mark.asyncio
async def test_memory_inspection_rejects_missing_user_cursor() -> None:
    client, _, user, proposals, events = inspection_store()
    user.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    proposals.document.side_effect = lambda category: MagicMock(
        name=f"proposal-{category}"
    )
    client.get_all.return_value = snapshot_stream([])
    cursor_ref = MagicMock()
    cursor_ref.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    events.document.return_value = cursor_ref
    first_order = MagicMock()
    second_order = MagicMock()
    cursor_query = MagicMock()
    limited_query = MagicMock()
    events.order_by.return_value = first_order
    first_order.order_by.return_value = second_order
    second_order.start_after.return_value = cursor_query
    cursor_query.limit.return_value = limited_query
    limited_query.stream.return_value = snapshot_stream([])

    with pytest.raises(MemoryEventCursorNotFoundError):
        await MemoryEngine(client).get_memory_inspection(
            "user-1",
            observed_at=NOW,
            after_event_id="response_length--foreign-or-missing--approved",
        )

    second_order.start_after.assert_not_called()


@pytest.mark.asyncio
async def test_memory_inspection_fails_closed_for_malformed_cursor() -> None:
    client, _, user, proposals, events = inspection_store()
    user.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )
    proposals.document.side_effect = lambda category: MagicMock(
        name=f"proposal-{category}"
    )
    client.get_all.return_value = snapshot_stream([])
    cursor_ref = MagicMock()
    cursor_ref.get = AsyncMock(
        return_value=SimpleNamespace(
            id="response_length--malformed--approved",
            exists=True,
            to_dict=lambda: {"unexpected": "private-memory-value"},
        )
    )
    events.document.return_value = cursor_ref
    first_order = MagicMock()
    second_order = MagicMock()
    events.order_by.return_value = first_order
    first_order.order_by.return_value = second_order

    with pytest.raises(MemoryEngineError):
        await MemoryEngine(client).get_memory_inspection(
            "user-1",
            observed_at=NOW,
            after_event_id="response_length--malformed--approved",
        )

    second_order.start_after.assert_not_called()


@pytest.mark.asyncio
async def test_memory_inspection_rejects_naive_observation_before_access(
) -> None:
    client = MagicMock()

    with pytest.raises(
        ValueError,
        match="observed_at must be a timezone-aware datetime",
    ):
        await MemoryEngine(client).get_memory_inspection(
            "user-1",
            observed_at=datetime(2026, 8, 20, 21, 0),
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_memory_inspection_rejects_invalid_cursor_before_access(
) -> None:
    client = MagicMock()

    with pytest.raises(
        ValueError,
        match="after_event_id must be a valid identifier",
    ):
        await MemoryEngine(client).get_memory_inspection(
            "user-1",
            observed_at=NOW,
            after_event_id="invalid/cursor",
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_memory_inspection_rejects_invalid_user_before_access() -> None:
    client = MagicMock()

    with pytest.raises(
        ValueError,
        match="user_id must be a valid identifier",
    ):
        await MemoryEngine(client).get_memory_inspection(
            "invalid/user",
            observed_at=NOW,
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_memory_inspection_preserves_firestore_error_safely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    firestore_error = ServiceUnavailable("private-backend-detail")
    client, _, user, _, _ = inspection_store()
    user.get = AsyncMock(side_effect=firestore_error)
    caplog.set_level("ERROR", logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).get_memory_inspection(
            "private-user",
            observed_at=NOW,
        )

    assert caught.value.__cause__ is firestore_error
    assert "private-user" not in caplog.text
    assert "private-backend-detail" not in caplog.text
