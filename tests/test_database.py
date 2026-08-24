import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.cloud import firestore

from database import MemoryEngine, MemoryEngineError
from schemas import AdaptationReceipt


@pytest.mark.asyncio
async def test_save_message_commits_parent_and_message_atomically() -> None:
    client = MagicMock()
    sessions = MagicMock()
    session = MagicMock()
    messages = MagicMock()
    message = MagicMock(id="message-1")
    batch = MagicMock()
    batch.commit = AsyncMock(return_value=[])

    client.collection.return_value = sessions
    sessions.document.return_value = session
    session.collection.return_value = messages
    messages.document.return_value = message
    client.batch.return_value = batch

    engine = MemoryEngine(client=client)
    message_id = await engine.save_message(
        "session-1",
        "user",
        "hello",
        project_id="project-1",
        user_id="user-1",
    )

    assert message_id == "message-1"
    client.collection.assert_called_once_with("sessions")
    sessions.document.assert_called_once_with("session-1")
    session.collection.assert_called_once_with("messages")
    messages.document.assert_called_once_with()
    assert batch.set.call_args_list == [
        call(
            session,
            {
                "project_id": "project-1",
                "user_id": "user-1",
                "updated_at": firestore.SERVER_TIMESTAMP,
                "last_message_preview": "hello",
                "last_message_role": "user",
            },
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


@pytest.mark.asyncio
async def test_save_blueprint_commits_parent_and_blueprint_atomically() -> None:
    client = MagicMock()
    projects = MagicMock()
    project = MagicMock()
    blueprints = MagicMock()
    blueprint_ref = MagicMock(id="blueprint-1")
    batch = MagicMock()
    batch.commit = AsyncMock(return_value=[])

    client.collection.return_value = projects
    projects.document.return_value = project
    project.collection.return_value = blueprints
    blueprints.document.return_value = blueprint_ref
    client.batch.return_value = batch
    payload = {
        "synthesized_conceptual_model": {
            "project_name": "Agent Col",
        }
    }

    blueprint_id = await MemoryEngine(client).save_blueprint(
        "project-1",
        "session-1",
        "user-1",
        "gemini-3.6-flash",
        "2.0",
        payload,
    )

    assert blueprint_id == "blueprint-1"
    client.collection.assert_called_once_with("projects")
    projects.document.assert_called_once_with("project-1")
    project.collection.assert_called_once_with("blueprints")
    blueprints.document.assert_called_once_with()
    assert batch.set.call_args_list == [
        call(
            project,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(
            blueprint_ref,
            {
                "artifact_contract_version": "1.0",
                "artifact_type": "synthesis_blueprint",
                "created_at": firestore.SERVER_TIMESTAMP,
                "originating_session_id": "session-1",
                "originating_turn_id": None,
                "user_id": "user-1",
                "model_name": "gemini-3.6-flash",
                "schema_version": "2.0",
                "parent_artifact_id": None,
                "feedback_counts": {
                    "accepted": 0,
                    "rejected": 0,
                    "edited": 0,
                },
                "adaptation_receipts": [],
                "applied_feedback_ids": [],
                "blueprint": payload,
            },
        ),
    ]
    batch.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_save_blueprint_persists_validated_adaptation_receipt() -> None:
    client = MagicMock()
    project = MagicMock()
    blueprint_ref = MagicMock(id="blueprint-1")
    batch = MagicMock()
    batch.commit = AsyncMock(return_value=[])
    client.collection.return_value.document.return_value = project
    project.collection.return_value.document.return_value = blueprint_ref
    client.batch.return_value = batch
    receipt = AdaptationReceipt(
        signal_id="planning-granularity-signal-1",
        category="planning_granularity",
        value="micro_steps",
        source_event_id="planning-granularity-signal-1--approved",
        status="provided_to_model",
    )

    blueprint_id = await MemoryEngine(client).save_blueprint(
        "project-1",
        "session-1",
        "user-1",
        "gemini-3.6-flash",
        "2.0",
        {"synthesized_conceptual_model": {"project_name": "Agent Col"}},
        adaptations=(receipt,),
    )

    assert blueprint_id == "blueprint-1"
    stored_document = batch.set.call_args_list[1].args[1]
    assert stored_document["adaptation_receipts"] == [
        {
            "signal_id": "planning-granularity-signal-1",
            "category": "planning_granularity",
            "value": "micro_steps",
            "source_event_id": (
                "planning-granularity-signal-1--approved"
            ),
            "status": "provided_to_model",
        }
    ]
    batch.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_save_blueprint_rejects_duplicate_adaptation_categories() -> None:
    client = MagicMock()
    receipt = AdaptationReceipt(
        signal_id="planning-granularity-signal-1",
        category="planning_granularity",
        value="tasks",
        source_event_id="planning-granularity-signal-1--approved",
        status="provided_to_model",
    )

    with pytest.raises(ValueError, match="categories must be unique"):
        await MemoryEngine(client).save_blueprint(
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {"synthesized_conceptual_model": {"project_name": "Agent Col"}},
            adaptations=(receipt, receipt),
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_save_blueprint_rejects_unvalidated_adaptation_mapping() -> None:
    client = MagicMock()

    with pytest.raises(ValueError, match="valid adaptation receipts"):
        await MemoryEngine(client).save_blueprint(
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {"synthesized_conceptual_model": {"project_name": "Agent Col"}},
            adaptations=(
                {
                    "signal_id": "unvalidated-signal",
                    "category": "planning_granularity",
                    "value": "tasks",
                },
            ),
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_save_blueprint_rejects_more_than_eight_adaptations() -> None:
    client = MagicMock()
    category_values = (
        ("preferred_name", "Avery"),
        ("broad_roles", ["student"]),
        ("response_length", "concise"),
        ("explanation_structure", "step_by_step"),
        ("example_usage", "when_helpful"),
        ("question_style", "minimal_follow_up"),
        ("planning_granularity", "tasks"),
        ("progress_check_ins", "at_milestones"),
        ("tool_use_style", "use_when_needed"),
    )
    receipts = tuple(
        AdaptationReceipt.model_validate(
            {
                "signal_id": f"signal-{index}",
                "category": category,
                "value": value,
                "source_event_id": f"signal-{index}--approved",
                "status": "provided_to_model",
            }
        )
        for index, (category, value) in enumerate(category_values, start=1)
    )

    with pytest.raises(ValueError, match="valid adaptation receipts"):
        await MemoryEngine(client).save_blueprint(
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {"synthesized_conceptual_model": {"project_name": "Agent Col"}},
            adaptations=receipts,
        )

    client.collection.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    (
        (
            "",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {"key": "value"},
        ),
        (
            "project-1",
            "",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {"key": "value"},
        ),
        (
            "project-1",
            "session-1",
            " ",
            "gemini-3.6-flash",
            "2.0",
            {"key": "value"},
        ),
        (
            "project-1",
            "session-1",
            "user-1",
            "",
            "2.0",
            {"key": "value"},
        ),
        (
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "",
            {"key": "value"},
        ),
        (
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            {},
        ),
        (
            "project-1",
            "session-1",
            "user-1",
            "gemini-3.6-flash",
            "2.0",
            "invalid",
        ),
    ),
)
async def test_save_blueprint_rejects_invalid_input_before_access(
    arguments: tuple[object, ...],
) -> None:
    client = MagicMock()
    client.batch.return_value.commit = AsyncMock(return_value=[])

    with pytest.raises(ValueError):
        await MemoryEngine(client).save_blueprint(*arguments)

    client.collection.assert_not_called()


@pytest.mark.asyncio
async def test_save_blueprint_preserves_firestore_error_safely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_value = "private-blueprint-value"
    firestore_error = ServiceUnavailable("backend unavailable")
    client = MagicMock()
    batch = MagicMock()
    batch.commit = AsyncMock(side_effect=firestore_error)
    client.batch.return_value = batch
    caplog.set_level(logging.ERROR, logger="database")

    with pytest.raises(MemoryEngineError) as caught:
        await MemoryEngine(client).save_blueprint(
            "private-project",
            "private-session",
            "private-user",
            "gemini-3.6-flash",
            "2.0",
            {"note": private_value},
        )

    assert caught.value.__cause__ is firestore_error
    assert "private-project" not in caplog.text
    assert "private-session" not in caplog.text
    assert "private-user" not in caplog.text
    assert private_value not in caplog.text


async def snapshot_stream():
    yield SimpleNamespace(
        to_dict=lambda: {"role": "user", "text": "first"}
    )
    yield SimpleNamespace(
        to_dict=lambda: {"role": "model", "text": "second"}
    )


async def snapshot_stream_from(items: list[dict[str, object]]):
    for item in items:
        yield SimpleNamespace(to_dict=lambda item=item: item)


async def snapshot_stream_with_ids(items: list[tuple[str, dict[str, object]]]):
    for snapshot_id, item in items:
        yield SimpleNamespace(
            id=snapshot_id,
            exists=True,
            to_dict=lambda item=item: item,
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
async def test_list_chat_sessions_filters_user_project_metadata() -> None:
    client = MagicMock()
    sessions = MagicMock()
    limited = MagicMock()
    client.collection.return_value = sessions
    sessions.limit.return_value = limited
    limited.stream.return_value = snapshot_stream_with_ids(
        [
            (
                "session-new",
                {
                    "project_id": "project-1",
                    "user_id": "user-1",
                    "updated_at": datetime(2026, 8, 24, 12, 0),
                    "last_message_preview": "new question",
                    "last_message_role": "user",
                },
            ),
            (
                "session-other-project",
                {
                    "project_id": "other-project",
                    "user_id": "user-1",
                    "updated_at": datetime(2026, 8, 24, 13, 0),
                    "last_message_preview": "private",
                    "last_message_role": "user",
                },
            ),
        ]
    )

    result = await MemoryEngine(client).list_chat_sessions(
        user_id="user-1",
        project_id="project-1",
        limit=20,
    )

    assert [session.session_id for session in result.sessions] == [
        "session-new"
    ]
    assert result.sessions[0].last_message_preview == "new question"
    sessions.limit.assert_called_once_with(200)


@pytest.mark.asyncio
async def test_get_chat_history_returns_newest_limit_chronologically() -> None:
    client = MagicMock()
    messages = MagicMock()
    query = MagicMock()
    limited_query = MagicMock()
    limited_query.stream.return_value = snapshot_stream_from(
        [
            {"role": "model", "text": "newest"},
            {"role": "user", "text": "older"},
        ]
    )
    session = client.collection.return_value.document.return_value
    session.collection.return_value = messages
    messages.order_by.return_value = query
    query.limit.return_value = limited_query

    history = await MemoryEngine(client).get_chat_history(
        "session-1",
        limit=20,
    )

    messages.order_by.assert_called_once_with(
        "timestamp",
        direction=firestore.Query.DESCENDING,
    )
    query.limit.assert_called_once_with(20)
    assert history == [
        {"role": "user", "text": "older"},
        {"role": "model", "text": "newest"},
    ]


@pytest.mark.asyncio
async def test_bounded_history_excludes_current_message_and_keeps_limit() -> None:
    client = MagicMock()
    messages = MagicMock()
    query = MagicMock()
    limited_query = MagicMock()
    current_id = "turn--digest--user"
    snapshots = [
        SimpleNamespace(
            id=current_id,
            to_dict=lambda: {"role": "user", "text": "current"},
        )
    ]
    snapshots.extend(
        SimpleNamespace(
            id=f"prior-{index}",
            to_dict=lambda index=index: {
                "role": "model",
                "text": f"prior-{index}",
            },
        )
        for index in range(20, 0, -1)
    )

    async def stream_snapshots():
        for item in snapshots:
            yield item

    limited_query.stream.return_value = stream_snapshots()
    session = client.collection.return_value.document.return_value
    session.collection.return_value = messages
    messages.order_by.return_value = query
    query.limit.return_value = limited_query

    history = await MemoryEngine(client).get_chat_history(
        "session-1",
        limit=20,
        exclude_message_id=current_id,
    )

    query.limit.assert_called_once_with(21)
    assert len(history) == 20
    assert [item["text"] for item in history] == [
        f"prior-{index}" for index in range(1, 21)
    ]
    assert all("id" not in item and "message_id" not in item for item in history)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_limit", (True, 0, 101, 1.5, "20"))
async def test_get_chat_history_rejects_invalid_limit_before_access(
    invalid_limit: object,
) -> None:
    client = MagicMock()

    with pytest.raises(ValueError):
        await MemoryEngine(client).get_chat_history(
            "session-1",
            limit=invalid_limit,
        )

    client.collection.assert_not_called()


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
