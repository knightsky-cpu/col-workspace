import asyncio
from copy import deepcopy
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


class InMemoryPreferenceDocument:
    def __init__(self, store, path: tuple[str, ...]) -> None:
        self.store = store
        self.path = path

    def collection(self, name: str):
        return InMemoryPreferenceCollection(self.store, (*self.path, name))

    async def get(self, transaction=None):
        data = (
            transaction.read(self.path)
            if transaction is not None
            else self.store.documents.get(self.path)
        )
        return SimpleNamespace(
            exists=data is not None,
            to_dict=lambda: deepcopy(data),
        )


class InMemoryPreferenceCollection:
    def __init__(self, store, path: tuple[str, ...]) -> None:
        self.store = store
        self.path = path

    def document(self, name: str):
        return InMemoryPreferenceDocument(self.store, (*self.path, name))


class InMemoryPreferenceTransaction:
    def __init__(self, store) -> None:
        self.store = store
        self.documents = {}
        self.writes = {}
        self.reads = []

    def begin(self) -> None:
        self.documents = deepcopy(self.store.documents)
        self.writes = {}
        self.reads = []

    def read(self, path: tuple[str, ...]):
        data = self.documents.get(path)
        self.reads.append((path, deepcopy(data)))
        return data

    def set(self, document, data) -> None:
        self.writes[document.path] = deepcopy(data)

    def commit(self) -> None:
        self.store.documents.update(deepcopy(self.writes))
        self.store.write_count += len(self.writes)


class InMemoryPreferenceStore:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, ...], object] = {}
        self.write_count = 0
        self.lock = asyncio.Lock()

    def collection(self, name: str):
        return InMemoryPreferenceCollection(self, (name,))

    def transaction(self):
        return InMemoryPreferenceTransaction(self)


def install_atomic_runner(
    monkeypatch: pytest.MonkeyPatch,
    store: InMemoryPreferenceStore,
) -> None:
    def run_serially(callback):
        async def run(transaction, *args, **kwargs):
            async with store.lock:
                transaction.begin()
                result = await callback(transaction, *args, **kwargs)
                transaction.commit()
                return result

        return run

    monkeypatch.setattr(
        "database.firestore.async_transactional",
        run_serially,
    )


def install_forced_conflict_runner(
    monkeypatch: pytest.MonkeyPatch,
    store: InMemoryPreferenceStore,
) -> dict[str, object]:
    competing_read_complete = asyncio.Event()
    winner_committed = asyncio.Event()
    stats: dict[str, object] = {
        "callback_count": 0,
        "retry_count": 0,
        "initial_hypothesis_reads": [],
        "retry_hypothesis_read": None,
    }
    invocation_count = 0

    def hypothesis_read(transaction):
        return next(
            (
                data
                for path, data in transaction.reads
                if "preference_hypotheses" in path
            ),
            None,
        )

    def run_with_one_forced_retry(callback):
        async def run(transaction, *args, **kwargs):
            nonlocal invocation_count
            invocation = invocation_count
            invocation_count += 1
            transaction.begin()
            result = await callback(transaction, *args, **kwargs)
            stats["callback_count"] += 1
            stats["initial_hypothesis_reads"].append(
                hypothesis_read(transaction)
            )

            if invocation == 0:
                await competing_read_complete.wait()
                transaction.commit()
                winner_committed.set()
                return result

            competing_read_complete.set()
            await winner_committed.wait()
            stats["retry_count"] += 1
            transaction.begin()
            result = await callback(transaction, *args, **kwargs)
            stats["callback_count"] += 1
            stats["retry_hypothesis_read"] = hypothesis_read(transaction)
            transaction.commit()
            return result

        return run

    monkeypatch.setattr(
        "database.firestore.async_transactional",
        run_with_one_forced_retry,
    )
    return stats


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


@pytest.mark.asyncio
async def test_atomic_preference_capture_exact_retry_returns_stable_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryPreferenceStore()
    install_atomic_runner(monkeypatch, store)
    engine = MemoryEngine(store)
    item = observation()

    first = await engine.capture_preference_observation(
        item,
        observed_at=NOW,
    )
    writes_after_first = store.write_count
    second = await engine.capture_preference_observation(
        observation(created_at=NOW.replace(minute=1)),
        observed_at=NOW.replace(minute=1),
    )

    assert second == first
    assert second.observation == item
    assert second.hypothesis.evidence_count == 1
    assert second.surfaced_hypothesis is None
    assert store.write_count == writes_after_first


@pytest.mark.asyncio
async def test_atomic_preference_capture_keeps_concurrent_distinct_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryPreferenceStore()
    retry_stats = install_forced_conflict_runner(monkeypatch, store)
    engine = MemoryEngine(store)
    first = observation()
    second = observation(
        observation_id="pref-obs--turn-2",
        source_turn_id="turn-2",
        source_message_id="message-2",
    )

    await asyncio.gather(
        engine.capture_preference_observation(first, observed_at=NOW),
        engine.capture_preference_observation(second, observed_at=NOW),
    )
    stored = await engine.get_preference_hypothesis(
        "user-1",
        "project-a",
        "pref-hyp--user-1--project-a--response_length",
    )

    assert stored is not None
    assert stored.evidence_count == 2
    assert stored.confidence == 0.70
    assert set(stored.source_observation_ids) == {
        first.observation_id,
        second.observation_id,
    }
    assert retry_stats["initial_hypothesis_reads"] == [None, None]
    assert retry_stats["retry_count"] == 1
    assert retry_stats["callback_count"] == 3
    assert retry_stats["retry_hypothesis_read"] is not None


@pytest.mark.asyncio
async def test_atomic_preference_capture_preserves_stable_surface_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryPreferenceStore()
    install_atomic_runner(monkeypatch, store)
    engine = MemoryEngine(store)
    first = observation()
    second = observation(
        observation_id="pref-obs--turn-2",
        source_turn_id="turn-2",
        source_message_id="message-2",
    )

    first_outcome = await engine.capture_preference_observation(
        first,
        observed_at=NOW,
    )
    surfaced = await engine.capture_preference_observation(
        second,
        observed_at=NOW,
    )
    retry = await engine.capture_preference_observation(
        second,
        observed_at=NOW,
    )

    assert first_outcome.surfaced_hypothesis is None
    assert surfaced.surfaced_hypothesis is not None
    assert surfaced.surfaced_hypothesis.evidence_count == 2
    assert surfaced.surfaced_hypothesis.confidence == 0.70
    assert retry == surfaced
