from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath


NOW = datetime(2026, 8, 23, 18, 30, tzinfo=UTC)
TURN_ID = "a" * 64
FEEDBACK_ID = f"feedback--{TURN_ID}"
TARGET_ID = "target--0123456789abcdef01234567"


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
    *,
    exists: bool,
    data: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(exists=exists, to_dict=lambda: data)


def blueprint_document() -> dict[str, object]:
    return {
        "artifact_contract_version": "1.0",
        "artifact_type": "synthesis_blueprint",
        "created_at": NOW,
        "originating_session_id": "origin-session",
        "originating_turn_id": "b" * 64,
        "user_id": "user-1",
        "model_name": "gemini-3.6-flash",
        "schema_version": "2.0",
        "parent_artifact_id": None,
        "feedback_counts": {
            "accepted": 0,
            "rejected": 1,
            "edited": 0,
        },
        "adaptation_receipts": [],
        "applied_feedback_ids": [],
        "blueprint": {"synthesized_conceptual_model": {"project_name": "X"}},
    }


def feedback_document(
    *,
    decision: str = "accepted",
    feedback_text: str = "This boundary is correct.",
    created_at: datetime = NOW,
) -> dict[str, object]:
    return {
        "feedback_contract_version": "1.0",
        "feedback_id": FEEDBACK_ID,
        "artifact_id": "blueprint-1",
        "target_id": TARGET_ID,
        "target_kind": "whole_blueprint",
        "decision": decision,
        "feedback_text": feedback_text,
        "correction_text": None,
        "originating_session_id": "feedback-session",
        "source_message_id": "source-message-1",
        "originating_turn_id": TURN_ID,
        "user_id": "user-1",
        "schema_version": "2.0",
        "created_at": created_at,
        "status": "active",
        "supersedes_feedback_id": None,
    }


class FeedbackStore:
    def __init__(self) -> None:
        self.client = MagicMock()
        self.projects = MagicMock()
        self.project_ref = MagicMock()
        self.blueprints = MagicMock()
        self.blueprint_ref = MagicMock()
        self.feedback = MagicMock()
        self.feedback_ref = MagicMock()
        self.prior_feedback_ref = MagicMock()
        self.supersessions = MagicMock()
        self.supersession_ref = MagicMock()
        self.transaction = MagicMock()

        self.client.collection.return_value = self.projects
        self.projects.document.return_value = self.project_ref
        self.project_ref.collection.return_value = self.blueprints
        self.blueprints.document.return_value = self.blueprint_ref

        def blueprint_collection(name: str) -> MagicMock:
            if name == "feedback":
                return self.feedback
            if name == "feedback_supersessions":
                return self.supersessions
            raise AssertionError(f"Unexpected collection: {name}")

        def feedback_ref(feedback_id: str) -> MagicMock:
            if feedback_id == "feedback--prior-event":
                return self.prior_feedback_ref
            return self.feedback_ref

        self.blueprint_ref.collection.side_effect = blueprint_collection
        self.feedback.document.side_effect = feedback_ref
        self.supersessions.document.return_value = self.supersession_ref
        self.client.transaction.return_value = self.transaction


async def snapshot_stream(items: list[object]):
    for item in items:
        yield item


class FeedbackReadStore:
    def __init__(self) -> None:
        self.client = MagicMock()
        self.projects = MagicMock()
        self.project_ref = MagicMock()
        self.blueprints = MagicMock()
        self.blueprint_ref = MagicMock()
        self.feedback = MagicMock()
        self.supersessions = MagicMock()

        self.client.collection.return_value = self.projects
        self.projects.document.return_value = self.project_ref
        self.project_ref.collection.return_value = self.blueprints
        self.blueprints.document.return_value = self.blueprint_ref
        self.blueprint_ref.collection.side_effect = self._collection

    def _collection(self, name: str) -> MagicMock:
        if name == "feedback":
            return self.feedback
        if name == "feedback_supersessions":
            return self.supersessions
        raise AssertionError(f"Unexpected collection: {name}")


async def record_feedback(engine):
    return await engine.record_blueprint_feedback(
        project_id="project-1",
        blueprint_id="blueprint-1",
        feedback_id=FEEDBACK_ID,
        target_id=TARGET_ID,
        target_kind="whole_blueprint",
        decision="accepted",
        feedback_text="This boundary is correct.",
        correction_text=None,
        supersedes_feedback_id=None,
        expected_schema_version="2.0",
        session_id="feedback-session",
        user_id="user-1",
        source_message_id="source-message-1",
        turn_id=TURN_ID,
        observed_at=NOW,
    )


@pytest.mark.asyncio
async def test_record_feedback_atomically_writes_event_and_updates_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import MemoryEngine

    install_transaction_runner(monkeypatch)
    store = FeedbackStore()
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=blueprint_document())
    )
    store.feedback_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    result = await record_feedback(MemoryEngine(store.client))

    assert result.model_dump(mode="json") == {
        "feedback_id": FEEDBACK_ID,
        "artifact_id": "blueprint-1",
        "target_id": TARGET_ID,
        "target_kind": "whole_blueprint",
        "decision": "accepted",
        "schema_version": "2.0",
        "created_at": "2026-08-23T18:30:00Z",
    }
    assert store.transaction.set.call_args_list == [
        call(
            store.project_ref,
            {"updated_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        ),
        call(store.feedback_ref, feedback_document()),
        call(
            store.blueprint_ref,
            {
                "feedback_counts": {
                    "accepted": 1,
                    "rejected": 1,
                    "edited": 0,
                }
            },
            merge=True,
        ),
    ]


@pytest.mark.asyncio
async def test_record_feedback_identical_retry_does_not_increment_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import MemoryEngine

    install_transaction_runner(monkeypatch)
    store = FeedbackStore()
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=blueprint_document())
    )
    original_created_at = NOW - timedelta(minutes=5)
    store.feedback_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=feedback_document(created_at=original_created_at),
        )
    )

    result = await record_feedback(MemoryEngine(store.client))

    assert result.feedback_id == FEEDBACK_ID
    assert result.created_at == original_created_at
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_record_feedback_rejects_future_existing_event_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import BlueprintFeedbackStateError, MemoryEngine

    install_transaction_runner(monkeypatch)
    store = FeedbackStore()
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=blueprint_document())
    )
    store.feedback_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=feedback_document(created_at=NOW + timedelta(minutes=5)),
        )
    )

    with pytest.raises(BlueprintFeedbackStateError):
        await record_feedback(MemoryEngine(store.client))

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_record_feedback_conflicting_retry_preserves_existing_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import BlueprintFeedbackConflictError, MemoryEngine

    install_transaction_runner(monkeypatch)
    store = FeedbackStore()
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=blueprint_document())
    )
    store.feedback_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data=feedback_document(
                decision="rejected",
                feedback_text="A conflicting stored decision.",
            ),
        )
    )

    with pytest.raises(BlueprintFeedbackConflictError):
        await record_feedback(MemoryEngine(store.client))

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_record_feedback_missing_artifact_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import BlueprintArtifactNotFoundError, MemoryEngine

    install_transaction_runner(monkeypatch)
    store = FeedbackStore()
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )
    store.feedback_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    with pytest.raises(BlueprintArtifactNotFoundError):
        await record_feedback(MemoryEngine(store.client))

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_record_feedback_supersession_preserves_prior_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import MemoryEngine

    install_transaction_runner(monkeypatch)
    store = FeedbackStore()
    prior_feedback_id = "feedback--prior-event"
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                **blueprint_document(),
                "feedback_counts": {
                    "accepted": 1,
                    "rejected": 0,
                    "edited": 0,
                },
            },
        )
    )
    store.feedback_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.prior_feedback_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                **feedback_document(created_at=NOW - timedelta(minutes=5)),
                "feedback_id": prior_feedback_id,
            },
        )
    )
    store.supersession_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    result = await MemoryEngine(store.client).record_blueprint_feedback(
        project_id="project-1",
        blueprint_id="blueprint-1",
        feedback_id=FEEDBACK_ID,
        target_id=TARGET_ID,
        target_kind="whole_blueprint",
        decision="rejected",
        feedback_text="I am reversing my earlier acceptance.",
        correction_text=None,
        supersedes_feedback_id=prior_feedback_id,
        expected_schema_version="2.0",
        session_id="feedback-session-2",
        user_id="user-1",
        source_message_id="source-message-2",
        turn_id=TURN_ID,
        observed_at=NOW,
    )

    assert result.decision == "rejected"
    assert store.transaction.set.call_args_list[1].args[1][
        "supersedes_feedback_id"
    ] == prior_feedback_id
    assert store.transaction.set.call_args_list[2] == call(
        store.supersession_ref,
        {
            "supersession_contract_version": "1.0",
            "supersedes_feedback_id": prior_feedback_id,
            "superseded_by_feedback_id": FEEDBACK_ID,
            "created_at": NOW,
        },
    )
    assert store.transaction.set.call_args_list[3] == call(
        store.blueprint_ref,
        {
            "feedback_counts": {
                "accepted": 0,
                "rejected": 1,
                "edited": 0,
            }
        },
        merge=True,
    )
    assert all(
        item.args[0] is not store.prior_feedback_ref
        for item in store.transaction.set.call_args_list
    )


@pytest.mark.asyncio
async def test_record_feedback_rejects_incomplete_supersession_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import BlueprintFeedbackStateError, MemoryEngine

    install_transaction_runner(monkeypatch)
    store = FeedbackStore()
    prior_feedback_id = "feedback--prior-event"
    reversal_text = "I am reversing my earlier acceptance."
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                **blueprint_document(),
                "feedback_counts": {
                    "accepted": 1,
                    "rejected": 0,
                    "edited": 0,
                },
            },
        )
    )
    store.feedback_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                **feedback_document(
                    decision="rejected",
                    feedback_text=reversal_text,
                ),
                "originating_session_id": "feedback-session-2",
                "source_message_id": "source-message-2",
                "supersedes_feedback_id": prior_feedback_id,
            },
        )
    )
    store.prior_feedback_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                **feedback_document(created_at=NOW - timedelta(minutes=5)),
                "feedback_id": prior_feedback_id,
            },
        )
    )
    store.supersession_ref.get = AsyncMock(
        return_value=snapshot(exists=False)
    )

    with pytest.raises(
        BlueprintFeedbackStateError,
        match="supersession is incomplete",
    ):
        await MemoryEngine(store.client).record_blueprint_feedback(
            project_id="project-1",
            blueprint_id="blueprint-1",
            feedback_id=FEEDBACK_ID,
            target_id=TARGET_ID,
            target_kind="whole_blueprint",
            decision="rejected",
            feedback_text=reversal_text,
            correction_text=None,
            supersedes_feedback_id=prior_feedback_id,
            expected_schema_version="2.0",
            session_id="feedback-session-2",
            user_id="user-1",
            source_message_id="source-message-2",
            turn_id=TURN_ID,
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_record_feedback_supersession_retry_preserves_first_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import MemoryEngine

    install_transaction_runner(monkeypatch)
    store = FeedbackStore()
    prior_feedback_id = "feedback--prior-event"
    reversal_text = "I am reversing my earlier acceptance."
    original_created_at = NOW - timedelta(minutes=2)
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                **blueprint_document(),
                "feedback_counts": {
                    "accepted": 0,
                    "rejected": 1,
                    "edited": 0,
                },
            },
        )
    )
    store.feedback_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                **feedback_document(
                    decision="rejected",
                    feedback_text=reversal_text,
                    created_at=original_created_at,
                ),
                "originating_session_id": "feedback-session-2",
                "source_message_id": "source-message-2",
                "supersedes_feedback_id": prior_feedback_id,
            },
        )
    )
    store.prior_feedback_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                **feedback_document(created_at=NOW - timedelta(minutes=5)),
                "feedback_id": prior_feedback_id,
            },
        )
    )
    store.supersession_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "supersession_contract_version": "1.0",
                "supersedes_feedback_id": prior_feedback_id,
                "superseded_by_feedback_id": FEEDBACK_ID,
                "created_at": original_created_at,
            },
        )
    )

    result = await MemoryEngine(store.client).record_blueprint_feedback(
        project_id="project-1",
        blueprint_id="blueprint-1",
        feedback_id=FEEDBACK_ID,
        target_id=TARGET_ID,
        target_kind="whole_blueprint",
        decision="rejected",
        feedback_text=reversal_text,
        correction_text=None,
        supersedes_feedback_id=prior_feedback_id,
        expected_schema_version="2.0",
        session_id="feedback-session-2",
        user_id="user-1",
        source_message_id="source-message-2",
        turn_id=TURN_ID,
        observed_at=NOW,
    )

    assert result.created_at == original_created_at
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_list_feedback_documents_is_bounded_and_resolves_supersession(
) -> None:
    from database import MemoryEngine

    assert hasattr(MemoryEngine, "list_blueprint_feedback_documents")
    store = FeedbackReadStore()
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=blueprint_document())
    )
    first_order = MagicMock()
    second_order = MagicMock()
    limited_query = MagicMock()
    store.feedback.order_by.return_value = first_order
    first_order.order_by.return_value = second_order
    second_order.limit.return_value = limited_query
    feedback_snapshots = [
        SimpleNamespace(
            id=f"feedback--event-{index}",
            to_dict=lambda index=index: {
                **feedback_document(),
                "feedback_id": f"feedback--event-{index}",
            },
        )
        for index in range(3)
    ]
    limited_query.stream.return_value = snapshot_stream(feedback_snapshots)

    link_refs: dict[str, MagicMock] = {}

    def link_ref(feedback_id: str) -> MagicMock:
        ref = MagicMock()
        ref.get = AsyncMock(
            return_value=snapshot(
                exists=feedback_id == "feedback--event-1",
                data=(
                    {
                        "supersession_contract_version": "1.0",
                        "supersedes_feedback_id": "feedback--event-1",
                        "superseded_by_feedback_id": "feedback--event-0",
                        "created_at": NOW,
                    }
                    if feedback_id == "feedback--event-1"
                    else None
                ),
            )
        )
        link_refs[feedback_id] = ref
        return ref

    store.supersessions.document.side_effect = link_ref

    page = await MemoryEngine(
        store.client
    ).list_blueprint_feedback_documents(
        "project-1",
        "blueprint-1",
        limit=2,
        before=None,
    )

    assert [record.feedback_id for record in page.records] == [
        "feedback--event-0",
        "feedback--event-1",
    ]
    assert page.records[0].superseded_by_feedback_id is None
    assert page.records[1].superseded_by_feedback_id == "feedback--event-0"
    assert page.next_before == "feedback--event-1"
    store.feedback.order_by.assert_called_once_with(
        "created_at",
        direction=firestore.Query.DESCENDING,
    )
    first_order.order_by.assert_called_once_with(
        FieldPath.document_id(),
        direction=firestore.Query.DESCENDING,
    )
    second_order.limit.assert_called_once_with(3)


@pytest.mark.asyncio
async def test_list_feedback_documents_rejects_invalid_parent_artifact(
) -> None:
    from database import BlueprintFeedbackStateError, MemoryEngine

    store = FeedbackReadStore()
    store.blueprint_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data={"artifact_type": "other"})
    )

    with pytest.raises(BlueprintFeedbackStateError):
        await MemoryEngine(
            store.client
        ).list_blueprint_feedback_documents(
            "project-1",
            "blueprint-1",
            limit=20,
            before=None,
        )

    store.feedback.order_by.assert_not_called()
