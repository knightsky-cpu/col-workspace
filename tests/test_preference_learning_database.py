from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from database import MemoryEngine


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def observation(**updates: object):
    from preference_learning import PreferenceObservation

    payload = {
        "observation_id": "pref-obs--turn-1",
        "user_id": "user-1",
        "project_id": "project-a",
        "session_id": "session-1",
        "source_turn_id": "turn-1",
        "source_message_id": "message-1",
        "category": "response_length",
        "canonical_value": "concise",
        "evidence_kind": "user_correction",
        "evidence_summary": "User corrected the answer to be shorter.",
        "confidence_delta": 0.35,
        "created_at": NOW,
    }
    payload.update(updates)
    return PreferenceObservation.model_validate(payload)


def hypothesis(**updates: object):
    from preference_learning import PreferenceHypothesis

    payload = {
        "hypothesis_id": "pref-hyp--user-1--project-a--response_length",
        "user_id": "user-1",
        "project_id": "project-a",
        "category": "response_length",
        "canonical_value": "concise",
        "evidence_count": 2,
        "contradiction_count": 0,
        "confidence": 0.75,
        "source_observation_ids": ("pref-obs--turn-1", "pref-obs--turn-2"),
        "first_observed_at": NOW,
        "last_observed_at": NOW,
    }
    payload.update(updates)
    return PreferenceHypothesis.model_validate(payload)


class AsyncSnapshots:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    def __aiter__(self):
        self._iterator = iter(self.snapshots)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def preference_store():
    client = MagicMock()
    users = MagicMock()
    user = MagicMock()
    workspaces = MagicMock()
    workspace = MagicMock()
    collection = MagicMock()
    document = MagicMock()
    client.collection.return_value = users
    users.document.return_value = user
    user.collection.return_value = workspaces
    workspaces.document.return_value = workspace
    workspace.collection.return_value = collection
    collection.document.return_value = document
    document.set = AsyncMock()
    return client, users, user, workspaces, workspace, collection, document


@pytest.mark.asyncio
async def test_save_preference_observation_writes_workspace_scoped_document():
    client, users, user, workspaces, workspace, collection, document = (
        preference_store()
    )
    item = observation()

    await MemoryEngine(client).save_preference_observation(item)

    client.collection.assert_called_once_with("users")
    users.document.assert_called_once_with("user-1")
    user.collection.assert_called_once_with("workspaces")
    workspaces.document.assert_called_once_with("project-a")
    workspace.collection.assert_called_once_with("preference_observations")
    collection.document.assert_called_once_with("pref-obs--turn-1")
    document.set.assert_awaited_once_with(item.model_dump(mode="python"))


@pytest.mark.asyncio
async def test_list_recent_preference_observations_reads_workspace_scope():
    client, _, _, _, workspace, collection, _ = preference_store()
    item = observation()
    query = MagicMock()
    collection.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = AsyncSnapshots(
        [
            SimpleNamespace(
                exists=True,
                to_dict=lambda: item.model_dump(mode="python"),
            )
        ]
    )

    result = await MemoryEngine(client).list_recent_preference_observations(
        "user-1",
        "project-a",
    )

    assert result == (item,)
    workspace.collection.assert_called_once_with("preference_observations")
    collection.order_by.assert_called_once()
    query.limit.assert_called_once_with(20)


@pytest.mark.asyncio
async def test_preference_hypothesis_round_trips_by_workspace():
    client, users, user, workspaces, workspace, collection, document = (
        preference_store()
    )
    stored = hypothesis()
    document.get = AsyncMock(
        return_value=SimpleNamespace(
            exists=True,
            to_dict=lambda: stored.model_dump(mode="python"),
        )
    )

    engine = MemoryEngine(client)
    await engine.save_preference_hypothesis(stored)
    loaded = await engine.get_preference_hypothesis(
        "user-1",
        "project-a",
        stored.hypothesis_id,
    )

    assert loaded == stored
    client.collection.assert_called_with("users")
    users.document.assert_called_with("user-1")
    user.collection.assert_called_with("workspaces")
    workspaces.document.assert_called_with("project-a")
    workspace.collection.assert_called_with("preference_hypotheses")
    collection.document.assert_called_with(stored.hypothesis_id)
    document.set.assert_awaited_once_with(stored.model_dump(mode="python"))


@pytest.mark.asyncio
async def test_missing_preference_hypothesis_returns_none():
    client, _, _, _, _, collection, document = preference_store()
    document.get = AsyncMock(
        return_value=SimpleNamespace(exists=False, to_dict=lambda: None)
    )

    result = await MemoryEngine(client).get_preference_hypothesis(
        "user-1",
        "project-b",
        "pref-hyp--user-1--project-b--response_length",
    )

    assert result is None
    collection.document.assert_called_once_with(
        "pref-hyp--user-1--project-b--response_length"
    )
