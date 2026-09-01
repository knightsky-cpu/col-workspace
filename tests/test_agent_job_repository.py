from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

import agent_job_repository
from agent_col_agent_jobs import AgentJob, AgentJobEvent, AgentJobFailure
from agent_job_repository import (
    AgentJobConflictError,
    AgentJobLeaseError,
    AgentJobNotFoundError,
    AgentJobRepository,
    AgentJobStateError,
)
from database import MemoryEngine


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def install_transaction_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    def run_without_sdk_retry(callback):
        async def run(transaction, *args, **kwargs):
            return await callback(transaction, *args, **kwargs)

        return run

    monkeypatch.setattr(
        agent_job_repository.firestore,
        "async_transactional",
        run_without_sdk_retry,
    )


class FakeSnapshot:
    def __init__(
        self,
        *,
        exists: bool,
        data: dict[str, object] | None,
        reference: FakeDocument | None = None,
    ) -> None:
        self.exists = exists
        self._data = data
        self.reference = reference

    def to_dict(self) -> dict[str, object] | None:
        return self._data


class FakeTransaction:
    def __init__(self, store: FakeFirestoreClient) -> None:
        self._store = store

    def set(
        self,
        document: FakeDocument,
        data: dict[str, object],
        *,
        merge: bool = False,
    ) -> None:
        current = self._store.documents.get(document.path, {})
        self._store.documents[document.path] = (
            {**current, **data} if merge else dict(data)
        )


class FakeFirestoreClient:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, ...], dict[str, object]] = {}
        self.transaction_obj = FakeTransaction(self)

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self, (name,))

    def transaction(self) -> FakeTransaction:
        return self.transaction_obj


class FakeDocument:
    def __init__(self, store: FakeFirestoreClient, path: tuple[str, ...]) -> None:
        self._store = store
        self.path = path
        self.id = path[-1]

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self._store, (*self.path, name))

    async def get(self, *, transaction: FakeTransaction | None = None) -> FakeSnapshot:
        data = self._store.documents.get(self.path)
        return FakeSnapshot(
            exists=data is not None,
            data=dict(data) if data is not None else None,
            reference=self,
        )


class FakeCollection:
    def __init__(
        self,
        store: FakeFirestoreClient,
        path: tuple[str, ...],
    ) -> None:
        self._store = store
        self.path = path

    def document(self, document_id: str) -> FakeDocument:
        return FakeDocument(self._store, (*self.path, document_id))

    def where(self, field_path: str, op_string: str, value: object) -> FakeQuery:
        return FakeQuery(self._store, self.path).where(
            field_path,
            op_string,
            value,
        )

    def order_by(self, field_path: str) -> FakeQuery:
        return FakeQuery(self._store, self.path).order_by(field_path)

    def limit(self, limit: int) -> FakeQuery:
        return FakeQuery(self._store, self.path).limit(limit)

    async def stream(
        self,
        *,
        transaction: FakeTransaction | None = None,
    ):
        async for snapshot in FakeQuery(self._store, self.path).stream(
            transaction=transaction
        ):
            yield snapshot


class FakeQuery:
    def __init__(
        self,
        store: FakeFirestoreClient,
        collection_path: tuple[str, ...],
        filters: tuple[tuple[str, str, object], ...] = (),
        order_field: str | None = None,
        row_limit: int | None = None,
    ) -> None:
        self._store = store
        self._collection_path = collection_path
        self._filters = filters
        self._order_field = order_field
        self._row_limit = row_limit

    def where(self, field_path: str, op_string: str, value: object) -> FakeQuery:
        return FakeQuery(
            self._store,
            self._collection_path,
            (*self._filters, (field_path, op_string, value)),
            self._order_field,
            self._row_limit,
        )

    def order_by(self, field_path: str) -> FakeQuery:
        return FakeQuery(
            self._store,
            self._collection_path,
            self._filters,
            field_path,
            self._row_limit,
        )

    def limit(self, limit: int) -> FakeQuery:
        return FakeQuery(
            self._store,
            self._collection_path,
            self._filters,
            self._order_field,
            limit,
        )

    async def stream(
        self,
        *,
        transaction: FakeTransaction | None = None,
    ):
        rows = []
        for path, data in self._store.documents.items():
            if (
                path[: len(self._collection_path)] != self._collection_path
                or len(path) != len(self._collection_path) + 1
            ):
                continue
            if all(self._matches(data, field, op, value) for field, op, value in self._filters):
                rows.append((path, data))
        if self._order_field is not None:
            rows.sort(key=lambda item: item[1].get(self._order_field))
        if self._row_limit is not None:
            rows = rows[: self._row_limit]
        for path, data in rows:
            yield FakeSnapshot(
                exists=True,
                data=dict(data),
                reference=FakeDocument(self._store, path),
            )

    @staticmethod
    def _matches(
        data: dict[str, object],
        field_path: str,
        op_string: str,
        value: object,
    ) -> bool:
        if op_string != "==":
            raise AssertionError(f"Unsupported fake query op: {op_string}")
        return data.get(field_path) == value


@pytest.fixture
def repository(monkeypatch: pytest.MonkeyPatch) -> AgentJobRepository:
    install_transaction_runner(monkeypatch)
    return AgentJobRepository(FakeFirestoreClient())


def make_job(**overrides: object) -> AgentJob:
    values: dict[str, object] = {
        "job_id": "job-1",
        "user_id": "user-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "session_id": "session-1",
        "source_turn_id": "turn-1",
        "source_message_id": "message-1",
        "action_kind": "create_artifact",
        "status": "queued",
        "display_label": "Create repo_helper.sh",
        "agent_label": "Artifact Agent",
        "created_at": NOW,
        "updated_at": NOW,
        "idempotency_key": "idem-1",
    }
    values.update(overrides)
    return AgentJob(**values)


def make_event(**overrides: object) -> AgentJobEvent:
    values: dict[str, object] = {
        "event_id": "event-1",
        "job_id": "job-1",
        "event_type": "queued",
        "message": "Queued artifact work.",
        "created_at": NOW,
        "status": "queued",
    }
    values.update(overrides)
    return AgentJobEvent(**values)


async def collect(async_iterable: Any) -> list[Any]:
    return [item async for item in async_iterable]


def test_memory_engine_exposes_agent_job_repository() -> None:
    client = FakeFirestoreClient()

    repository = MemoryEngine(client).agent_jobs()

    assert isinstance(repository, AgentJobRepository)


@pytest.mark.asyncio
async def test_enqueue_job_creates_and_replays_same_idempotent_job(
    repository: AgentJobRepository,
) -> None:
    job = make_job()

    created = await repository.enqueue_job(job)
    replayed = await repository.enqueue_job(job)

    assert created == job
    assert replayed == job
    assert await repository.get_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    ) == job


@pytest.mark.asyncio
async def test_enqueue_job_rejects_idempotency_conflict(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(make_job())

    with pytest.raises(AgentJobConflictError):
        await repository.enqueue_job(
            make_job(
                job_id="job-2",
                display_label="Create different artifact",
            )
        )


@pytest.mark.asyncio
async def test_get_job_rejects_missing_or_mismatched_owner(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(make_job())

    with pytest.raises(AgentJobNotFoundError):
        await repository.get_job(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="missing",
        )

    with pytest.raises(AgentJobNotFoundError):
        await repository.get_job(
            user_id="user-2",
            workspace_id="workspace-1",
            job_id="job-1",
        )


@pytest.mark.asyncio
async def test_list_jobs_filters_by_project_and_session(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(make_job(job_id="job-1", idempotency_key="idem-1"))
    await repository.enqueue_job(
        make_job(
            job_id="job-2",
            session_id="session-2",
            idempotency_key="idem-2",
            created_at=NOW + timedelta(seconds=5),
            updated_at=NOW + timedelta(seconds=5),
        )
    )
    await repository.enqueue_job(
        make_job(
            job_id="job-3",
            project_id="project-2",
            idempotency_key="idem-3",
            created_at=NOW + timedelta(seconds=10),
            updated_at=NOW + timedelta(seconds=10),
        )
    )

    jobs = await collect(
        repository.list_jobs(
            user_id="user-1",
            workspace_id="workspace-1",
            project_id="project-1",
            session_id="session-1",
        )
    )

    assert [job.job_id for job in jobs] == ["job-1"]


@pytest.mark.asyncio
async def test_lease_next_queued_job_moves_oldest_job_to_running(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(
        make_job(
            job_id="job-2",
            idempotency_key="idem-2",
            created_at=NOW + timedelta(seconds=5),
            updated_at=NOW + timedelta(seconds=5),
        )
    )
    await repository.enqueue_job(make_job(job_id="job-1", idempotency_key="idem-1"))

    leased = await repository.lease_next_queued_job(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=2),
        observed_at=NOW + timedelta(seconds=10),
    )

    assert leased is not None
    assert leased.job_id == "job-1"
    assert leased.status == "running"
    assert leased.lease_owner == "worker-1"
    assert leased.updated_at == NOW + timedelta(seconds=10)


@pytest.mark.asyncio
async def test_complete_job_requires_matching_live_lease(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(make_job())
    await repository.lease_next_queued_job(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=2),
        observed_at=NOW,
    )

    with pytest.raises(AgentJobLeaseError):
        await repository.complete_job(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="job-1",
            lease_owner="worker-2",
            observed_at=NOW + timedelta(seconds=5),
            result_refs={"artifact_id": "artifact-1"},
        )

    completed = await repository.complete_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        lease_owner="worker-1",
        observed_at=NOW + timedelta(seconds=5),
        result_refs={"artifact_id": "artifact-1"},
    )

    assert completed.status == "completed"
    assert completed.result_refs == {"artifact_id": "artifact-1"}


@pytest.mark.asyncio
async def test_fail_job_requires_matching_live_lease(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(make_job())
    await repository.lease_next_queued_job(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=2),
        observed_at=NOW,
    )

    failed = await repository.fail_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        lease_owner="worker-1",
        observed_at=NOW + timedelta(seconds=5),
        failure=AgentJobFailure(
            code="provider_timeout",
            summary="Artifact generation timed out.",
            retryable=True,
        ),
    )

    assert failed.status == "failed"
    assert failed.failure_summary is not None
    assert failed.failure_summary.retryable is True


@pytest.mark.asyncio
async def test_cancel_job_only_marks_non_terminal_jobs(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(make_job())

    cancelled = await repository.cancel_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        observed_at=NOW + timedelta(seconds=5),
    )

    assert cancelled.status == "cancelled"

    with pytest.raises(AgentJobStateError):
        await repository.cancel_job(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="job-1",
            observed_at=NOW + timedelta(seconds=10),
        )


@pytest.mark.asyncio
async def test_retry_job_links_to_failed_retryable_source(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(make_job())
    await repository.lease_next_queued_job(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=2),
        observed_at=NOW,
    )
    await repository.fail_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        lease_owner="worker-1",
        observed_at=NOW + timedelta(seconds=2),
        failure=AgentJobFailure(
            code="provider_timeout",
            summary="Artifact generation timed out.",
            retryable=True,
        ),
    )

    retry = await repository.retry_job(
        user_id="user-1",
        workspace_id="workspace-1",
        source_job_id="job-1",
        retry_job_id="job-1-retry",
        idempotency_key="idem-1-retry",
        observed_at=NOW + timedelta(seconds=5),
    )

    assert retry.status == "queued"
    assert retry.retry_of_job_id == "job-1"
    assert retry.attempt_count == 2


@pytest.mark.asyncio
async def test_events_are_idempotent_and_list_only_public_events(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(make_job())
    public_event = make_event(event_id="event-1")
    private_event = make_event(
        event_id="event-2",
        message="Internal diagnostic.",
        public_visibility=False,
        created_at=NOW + timedelta(seconds=1),
    )

    assert await repository.append_event(
        user_id="user-1",
        workspace_id="workspace-1",
        event=public_event,
    ) == public_event
    assert await repository.append_event(
        user_id="user-1",
        workspace_id="workspace-1",
        event=public_event,
    ) == public_event
    await repository.append_event(
        user_id="user-1",
        workspace_id="workspace-1",
        event=private_event,
    )

    events = await collect(
        repository.list_events(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="job-1",
        )
    )

    assert [event.event_id for event in events] == ["event-1"]
