import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore

from database import MemoryEngine, MemoryEngineError


@pytest.mark.asyncio
async def test_save_message_commits_parent_and_message_atomically() -> None:
    client = MagicMock()
    sessions = MagicMock()
    session = MagicMock()
    messages = MagicMock()
    message = MagicMock()
    batch = MagicMock()
    batch.commit = AsyncMock(return_value=[])

    client.collection.return_value = sessions
    sessions.document.return_value = session
    session.collection.return_value = messages
    messages.document.return_value = message
    client.batch.return_value = batch

    engine = MemoryEngine(client=client)
    await engine.save_message("session-1", "user", "hello")

    client.collection.assert_called_once_with("sessions")
    sessions.document.assert_called_once_with("session-1")
    session.collection.assert_called_once_with("messages")
    messages.document.assert_called_once_with()
    assert batch.set.call_args_list == [
        call(
            session,
            {"updated_at": firestore.SERVER_TIMESTAMP},
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
    batch.commit.assert_awaited_once_with()


async def snapshot_stream():
    yield SimpleNamespace(
        to_dict=lambda: {"role": "user", "text": "first"}
    )
    yield SimpleNamespace(
        to_dict=lambda: {"role": "model", "text": "second"}
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
    session.collection.return_value = messages
    messages.order_by.return_value = query
    query.stream.return_value = snapshot_stream()

    engine = MemoryEngine(client=client)
    history = await engine.get_chat_history("session-1")

    messages.order_by.assert_called_once_with(
        "timestamp",
        direction=firestore.Query.ASCENDING,
    )
    assert history == [
        {"role": "user", "text": "first"},
        {"role": "model", "text": "second"},
    ]


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
        (engine.save_message, ("", "user", "text")),
        (engine.save_message, ("session", " ", "text")),
        (engine.save_message, ("session", "user", " ")),
        (engine.get_chat_history, (" ",)),
        (engine.update_user_profile, ("", {"tone": "direct"})),
        (engine.update_user_profile, ("user", {})),
        (engine.get_user_profile, ("",)),
    )

    for operation, arguments in invalid_calls:
        with pytest.raises(ValueError):
            await operation(*arguments)

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
