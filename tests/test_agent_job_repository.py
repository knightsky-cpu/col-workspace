from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

import agent_job_repository
from agent_col_agent_jobs import (
    AgentJob,
    AgentJobEvent,
    AgentJobFailure,
    AgentJobReport,
)
from agent_job_payloads import AgentJobPayload
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
            transaction.begin()
            try:
                result = await callback(transaction, *args, **kwargs)
            except Exception:
                transaction.rollback()
                raise
            transaction.commit()
            return result

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
        self._pending: dict[tuple[str, ...], dict[str, object]] = {}
        self.fail_after_sets: int | None = None

    def begin(self) -> None:
        self._pending = {}

    def commit(self) -> None:
        self._store.documents.update(self._pending)
        self._pending = {}

    def rollback(self) -> None:
        self._pending = {}

    def set(
        self,
        document: FakeDocument,
        data: dict[str, object],
        *,
        merge: bool = False,
    ) -> None:
        if self.fail_after_sets == 0:
            raise RuntimeError("simulated transaction failure")
        if self.fail_after_sets is not None:
            self.fail_after_sets -= 1
        current = self._pending.get(
            document.path,
            self._store.documents.get(document.path, {}),
        )
        self._pending[document.path] = (
            {**current, **data} if merge else dict(data)
        )


class FakeFirestoreClient:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, ...], dict[str, object]] = {}
        self.transaction_obj = FakeTransaction(self)

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self, (name,))

    def collection_group(self, name: str) -> FakeCollectionGroupQuery:
        return FakeCollectionGroupQuery(self, name)

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
        if op_string == "==":
            return data.get(field_path) == value
        if op_string == "<=":
            stored = data.get(field_path)
            return stored is not None and stored <= value
        raise AssertionError(f"Unsupported fake query op: {op_string}")


class FakeCollectionGroupQuery(FakeQuery):
    def __init__(
        self,
        store: FakeFirestoreClient,
        collection_id: str,
        filters: tuple[tuple[str, str, object], ...] = (),
        order_field: str | None = None,
        row_limit: int | None = None,
    ) -> None:
        super().__init__(
            store,
            (collection_id,),
            filters,
            order_field,
            row_limit,
        )
        self._collection_id = collection_id

    def where(
        self,
        field_path: str,
        op_string: str,
        value: object,
    ) -> FakeCollectionGroupQuery:
        return FakeCollectionGroupQuery(
            self._store,
            self._collection_id,
            (*self._filters, (field_path, op_string, value)),
            self._order_field,
            self._row_limit,
        )

    def order_by(self, field_path: str) -> FakeCollectionGroupQuery:
        return FakeCollectionGroupQuery(
            self._store,
            self._collection_id,
            self._filters,
            field_path,
            self._row_limit,
        )

    def limit(self, limit: int) -> FakeCollectionGroupQuery:
        return FakeCollectionGroupQuery(
            self._store,
            self._collection_id,
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
            if len(path) < 2 or path[-2] != self._collection_id:
                continue
            if all(
                self._matches(data, field, op, value)
                for field, op, value in self._filters
            ):
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


def make_payload(**overrides: object) -> AgentJobPayload:
    values: dict[str, object] = {
        "job_id": "job-1",
        "user_id": "user-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "session_id": "session-1",
        "source_turn_id": "turn-1",
        "source_message_id": "message-1",
        "action_kind": "create_artifact",
        "created_at": NOW,
        "payload": {
            "artifact_family": "script",
            "filename": "repo_helper.sh",
            "source_text": "Build a Bash repository helper.",
        },
    }
    values.update(overrides)
    return AgentJobPayload(**values)


def store_job(repository: AgentJobRepository, job: AgentJob) -> None:
    repository._client.documents[
        repository._job_ref(
            job.user_id,
            job.workspace_id,
            job.job_id,
        ).path
    ] = job.model_dump(mode="python")


def make_report(**overrides: object) -> AgentJobReport:
    values: dict[str, object] = {
        "report_id": "report-1",
        "job_id": "job-1",
        "user_id": "user-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "session_id": "session-1",
        "action_kind": "propose_memory_signal",
        "agent_label": "Memory Analyst",
        "status": "completed",
        "title": "Memory proposal pending review",
        "summary": "A memory proposal was created and is pending your review.",
        "public_resource_label": "Prefers C over Python",
        "created_at": NOW,
    }
    values.update(overrides)
    return AgentJobReport(**values)


def make_running_job(**overrides: object) -> AgentJob:
    values: dict[str, object] = {
        "status": "running",
        "updated_at": NOW,
        "lease_owner": "worker-1",
        "lease_expires_at": NOW + timedelta(minutes=2),
    }
    values.update(overrides)
    return make_job(**values)


def terminal_event_for(
    job: AgentJob,
    *,
    event_type: str = "completed",
    message: str = "Artifact created.",
    observed_at: datetime = NOW + timedelta(seconds=5),
) -> AgentJobEvent:
    return make_event(
        event_id=f"{job.job_id}-{event_type}",
        job_id=job.job_id,
        event_type=event_type,
        message=message,
        created_at=observed_at,
        status=event_type,
    )


def terminal_report_for(
    job: AgentJob,
    *,
    status: str = "completed",
    title: str = "Artifact created",
    summary: str = "The requested artifact was created.",
    public_resource_label: str | None = "repo_helper.sh",
    observed_at: datetime = NOW + timedelta(seconds=5),
) -> AgentJobReport:
    return make_report(
        report_id=f"{job.job_id}-report",
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        action_kind=job.action_kind,
        agent_label=job.agent_label,
        status=status,
        title=title,
        summary=summary,
        public_resource_label=public_resource_label,
        created_at=observed_at,
    )


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
async def test_enqueue_job_with_payload_persists_private_payload_without_public_projection(
    repository: AgentJobRepository,
) -> None:
    job = make_job()
    payload = make_payload()

    created = await repository.enqueue_job_with_payload(job, payload)

    assert created == job
    assert await repository.get_job_payload(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    ) == payload
    public_job = await repository.get_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    )
    public_document = public_job.model_dump(mode="python")
    assert "payload" not in public_document
    assert "private_payload" not in public_document
    assert "tool_payload" not in public_document


@pytest.mark.asyncio
async def test_enqueue_job_with_payload_replays_same_job_and_payload(
    repository: AgentJobRepository,
) -> None:
    job = make_job()
    payload = make_payload()

    created = await repository.enqueue_job_with_payload(job, payload)
    replayed = await repository.enqueue_job_with_payload(job, payload)

    assert created == job
    assert replayed == job
    assert await repository.get_job_payload(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    ) == payload


@pytest.mark.asyncio
async def test_enqueue_job_with_payload_rejects_private_payload_conflict(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job_with_payload(make_job(), make_payload())

    with pytest.raises(AgentJobConflictError):
        await repository.enqueue_job_with_payload(
            make_job(
                job_id="job-2",
                display_label="Create different artifact",
            ),
            make_payload(
                job_id="job-2",
                payload={
                    "artifact_family": "script",
                    "filename": "different.sh",
                    "source_text": "Build a different script.",
                },
            ),
        )

    with pytest.raises(AgentJobConflictError):
        await repository.enqueue_job_with_payload(
            make_job(),
            make_payload(
                payload={
                    "artifact_family": "script",
                    "filename": "different.sh",
                    "source_text": "Build a different script.",
                },
            ),
        )


@pytest.mark.asyncio
async def test_get_job_payload_rejects_missing_or_mismatched_owner(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job_with_payload(make_job(), make_payload())

    with pytest.raises(AgentJobNotFoundError):
        await repository.get_job_payload(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="missing",
        )

    with pytest.raises(AgentJobNotFoundError):
        await repository.get_job_payload(
            user_id="user-2",
            workspace_id="workspace-1",
            job_id="job-1",
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
async def test_list_queued_jobs_enumerates_only_queued_jobs_globally_with_limit(
    repository: AgentJobRepository,
) -> None:
    supported_action_kinds = (
        "create_artifact",
        "propose_memory_signal",
        "propose_collaborative_note",
    )
    await repository.enqueue_job(
        make_job(
            job_id="job-unsupported",
            action_kind="retrieve_chat_context",
            idempotency_key="idem-unsupported",
            created_at=NOW - timedelta(seconds=10),
            updated_at=NOW - timedelta(seconds=10),
        )
    )
    await repository.enqueue_job(
        make_job(
            job_id="job-user-1",
            idempotency_key="idem-user-1",
            created_at=NOW + timedelta(seconds=10),
            updated_at=NOW + timedelta(seconds=10),
        )
    )
    await repository.enqueue_job(
        make_job(
            job_id="job-user-2",
            user_id="user-2",
            workspace_id="workspace-2",
            idempotency_key="idem-user-2",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    await repository.enqueue_job(
        make_job(
            job_id="job-running",
            idempotency_key="idem-running",
            created_at=NOW + timedelta(seconds=5),
            updated_at=NOW + timedelta(seconds=5),
        )
    )
    await repository.lease_queued_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-running",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=2),
        observed_at=NOW + timedelta(seconds=20),
    )

    jobs = await collect(
        repository.list_queued_jobs(
            action_kinds=supported_action_kinds,
            limit=2,
        )
    )

    assert [job.job_id for job in jobs] == ["job-user-2", "job-user-1"]


@pytest.mark.asyncio
async def test_list_expired_running_jobs_enumerates_only_eligible_expired_jobs(
    repository: AgentJobRepository,
) -> None:
    supported_action_kinds = (
        "create_artifact",
        "propose_memory_signal",
        "propose_collaborative_note",
    )
    expired_memory = make_job(
        job_id="memory-job-1",
        action_kind="propose_memory_signal",
        idempotency_key="idem-memory",
        status="running",
        created_at=NOW - timedelta(minutes=5),
        updated_at=NOW - timedelta(minutes=3),
        lease_owner="memory-worker-1",
        lease_expires_at=NOW - timedelta(seconds=5),
    )
    expired_note = make_job(
        job_id="note-job-1",
        action_kind="propose_collaborative_note",
        idempotency_key="idem-note",
        status="running",
        created_at=NOW - timedelta(minutes=6),
        updated_at=NOW - timedelta(minutes=4),
        lease_owner="note-worker-1",
        lease_expires_at=NOW - timedelta(seconds=10),
    )
    unexpired_artifact = make_job(
        job_id="artifact-job-1",
        action_kind="create_artifact",
        idempotency_key="idem-artifact",
        status="running",
        created_at=NOW - timedelta(minutes=7),
        updated_at=NOW - timedelta(minutes=1),
        lease_owner="artifact-worker-1",
        lease_expires_at=NOW + timedelta(seconds=10),
    )
    unsupported = make_job(
        job_id="unsupported-job-1",
        action_kind="retrieve_chat_context",
        idempotency_key="idem-unsupported",
        status="running",
        created_at=NOW - timedelta(minutes=8),
        updated_at=NOW - timedelta(minutes=4),
        lease_owner="context-worker-1",
        lease_expires_at=NOW - timedelta(seconds=20),
    )
    queued = make_job(
        job_id="queued-job-1",
        action_kind="propose_memory_signal",
        idempotency_key="idem-queued",
        created_at=NOW - timedelta(minutes=9),
        updated_at=NOW - timedelta(minutes=9),
    )
    for job in (
        expired_memory,
        expired_note,
        unexpired_artifact,
        unsupported,
        queued,
    ):
        store_job(repository, job)

    jobs = await collect(
        repository.list_expired_running_jobs(
            action_kinds=supported_action_kinds,
            observed_at=NOW,
            limit=2,
        )
    )

    assert [job.job_id for job in jobs] == ["note-job-1", "memory-job-1"]


@pytest.mark.asyncio
async def test_reports_are_idempotent_and_listed_chronologically(
    repository: AgentJobRepository,
) -> None:
    first = make_report(report_id="report-1", created_at=NOW)
    second = make_report(
        report_id="report-2",
        job_id="job-2",
        title="Artifact created",
        summary="The artifact was created.",
        public_resource_label="check_server_status.sh",
        created_at=NOW + timedelta(seconds=5),
    )

    assert await repository.create_report(first) == first
    assert await repository.create_report(first) == first
    assert await repository.create_report(second) == second

    reports = await collect(
        repository.list_reports(
            user_id="user-1",
            workspace_id="workspace-1",
            project_id="project-1",
            session_id="session-1",
        )
    )

    assert reports == [first, second]


@pytest.mark.asyncio
async def test_list_reports_filters_by_project_and_session(
    repository: AgentJobRepository,
) -> None:
    await repository.create_report(make_report(report_id="report-1"))
    await repository.create_report(
        make_report(
            report_id="report-2",
            job_id="job-2",
            session_id="session-2",
            created_at=NOW + timedelta(seconds=5),
        )
    )
    await repository.create_report(
        make_report(
            report_id="report-3",
            job_id="job-3",
            project_id="project-2",
            created_at=NOW + timedelta(seconds=10),
        )
    )

    reports = await collect(
        repository.list_reports(
            user_id="user-1",
            workspace_id="workspace-1",
            project_id="project-1",
            session_id="session-1",
        )
    )

    assert [report.report_id for report in reports] == ["report-1"]


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
async def test_lease_next_queued_job_filters_by_action_kind(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(
        make_job(
            job_id="artifact-job",
            idempotency_key="artifact-idem",
        )
    )
    await repository.enqueue_job(
        make_job(
            job_id="memory-job",
            idempotency_key="memory-idem",
            action_kind="propose_memory_signal",
            display_label="Memory request: response_length",
            agent_label="Memory Analyst",
            created_at=NOW + timedelta(seconds=5),
            updated_at=NOW + timedelta(seconds=5),
        )
    )

    leased = await repository.lease_next_queued_job(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="memory-worker-1",
        lease_expires_at=NOW + timedelta(minutes=2),
        observed_at=NOW + timedelta(seconds=10),
        action_kind="propose_memory_signal",
    )

    assert leased is not None
    assert leased.job_id == "memory-job"
    assert leased.action_kind == "propose_memory_signal"
    assert leased.status == "running"
    artifact_job = await repository.get_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="artifact-job",
    )
    assert artifact_job.status == "queued"


@pytest.mark.asyncio
async def test_lease_queued_job_moves_specific_job_to_running(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(
        make_job(
            job_id="job-older",
            idempotency_key="idem-older",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    await repository.enqueue_job(
        make_job(
            job_id="job-target",
            idempotency_key="idem-target",
            created_at=NOW + timedelta(seconds=5),
            updated_at=NOW + timedelta(seconds=5),
        )
    )

    leased = await repository.lease_queued_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-target",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=2),
        observed_at=NOW + timedelta(seconds=10),
    )

    assert leased.job_id == "job-target"
    assert leased.status == "running"
    assert leased.lease_owner == "worker-1"
    assert leased.updated_at == NOW + timedelta(seconds=10)
    older = await repository.get_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-older",
    )
    assert older.status == "queued"


@pytest.mark.asyncio
async def test_lease_queued_job_rejects_second_concurrent_owner(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(make_job())
    await repository.lease_queued_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=2),
        observed_at=NOW,
    )

    with pytest.raises(AgentJobStateError):
        await repository.lease_queued_job(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="job-1",
            lease_owner="worker-2",
            lease_expires_at=NOW + timedelta(minutes=2),
            observed_at=NOW + timedelta(seconds=1),
        )

    job = await repository.get_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    )
    assert job.status == "running"
    assert job.lease_owner == "worker-1"


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
async def test_finalize_terminal_job_writes_completed_job_event_and_report_atomically(
    repository: AgentJobRepository,
) -> None:
    running = make_running_job()
    observed_at = NOW + timedelta(seconds=5)
    event = terminal_event_for(running, observed_at=observed_at)
    report = terminal_report_for(running, observed_at=observed_at)
    store_job(repository, running)

    completed = await repository.finalize_terminal_job(
        user_id=running.user_id,
        workspace_id=running.workspace_id,
        job_id=running.job_id,
        lease_owner="worker-1",
        observed_at=observed_at,
        status="completed",
        result_refs={"artifact_id": "artifact-1"},
        failure=None,
        event=event,
        report=report,
    )

    assert completed.status == "completed"
    assert completed.result_refs == {"artifact_id": "artifact-1"}
    assert await repository.get_job(
        user_id=running.user_id,
        workspace_id=running.workspace_id,
        job_id=running.job_id,
    ) == completed
    assert await collect(
        repository.list_events(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
            job_id=running.job_id,
        )
    ) == [event]
    assert await collect(
        repository.list_reports(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
        )
    ) == [report]


@pytest.mark.asyncio
async def test_finalize_terminal_job_writes_failed_job_event_and_report_atomically(
    repository: AgentJobRepository,
) -> None:
    running = make_running_job()
    observed_at = NOW + timedelta(seconds=5)
    failure = AgentJobFailure(
        code="artifact_creation_failed",
        summary="Artifact could not be created.",
        retryable=False,
    )
    event = terminal_event_for(
        running,
        event_type="failed",
        message="Artifact creation failed.",
        observed_at=observed_at,
    )
    report = terminal_report_for(
        running,
        status="failed",
        title="Artifact not created",
        summary="Artifact could not be created.",
        public_resource_label=None,
        observed_at=observed_at,
    )
    store_job(repository, running)

    failed = await repository.finalize_terminal_job(
        user_id=running.user_id,
        workspace_id=running.workspace_id,
        job_id=running.job_id,
        lease_owner="worker-1",
        observed_at=observed_at,
        status="failed",
        result_refs=None,
        failure=failure,
        event=event,
        report=report,
    )

    assert failed.status == "failed"
    assert failed.failure_summary == failure
    assert await collect(
        repository.list_events(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
            job_id=running.job_id,
        )
    ) == [event]
    assert await collect(
        repository.list_reports(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
        )
    ) == [report]


@pytest.mark.asyncio
async def test_finalize_terminal_job_replays_exact_terminal_state(
    repository: AgentJobRepository,
) -> None:
    running = make_running_job()
    observed_at = NOW + timedelta(seconds=5)
    event = terminal_event_for(running, observed_at=observed_at)
    report = terminal_report_for(running, observed_at=observed_at)
    store_job(repository, running)

    first = await repository.finalize_terminal_job(
        user_id=running.user_id,
        workspace_id=running.workspace_id,
        job_id=running.job_id,
        lease_owner="worker-1",
        observed_at=observed_at,
        status="completed",
        result_refs={"artifact_id": "artifact-1"},
        failure=None,
        event=event,
        report=report,
    )
    replayed = await repository.finalize_terminal_job(
        user_id=running.user_id,
        workspace_id=running.workspace_id,
        job_id=running.job_id,
        lease_owner="worker-1",
        observed_at=observed_at,
        status="completed",
        result_refs={"artifact_id": "artifact-1"},
        failure=None,
        event=event,
        report=report,
    )

    assert replayed == first
    assert len(
        await collect(
            repository.list_events(
                user_id=running.user_id,
                workspace_id=running.workspace_id,
                job_id=running.job_id,
            )
        )
    ) == 1
    assert len(
        await collect(
            repository.list_reports(
                user_id=running.user_id,
                workspace_id=running.workspace_id,
            )
        )
    ) == 1


@pytest.mark.asyncio
async def test_finalize_terminal_job_rejects_conflicting_terminal_job(
    repository: AgentJobRepository,
) -> None:
    running = make_running_job()
    observed_at = NOW + timedelta(seconds=5)
    completed = running.model_copy(
        update={
            "status": "completed",
            "updated_at": observed_at,
            "result_refs": {"artifact_id": "different-artifact"},
        }
    )
    event = terminal_event_for(running, observed_at=observed_at)
    report = terminal_report_for(running, observed_at=observed_at)
    store_job(repository, completed)

    with pytest.raises(AgentJobConflictError):
        await repository.finalize_terminal_job(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
            job_id=running.job_id,
            lease_owner="worker-1",
            observed_at=observed_at,
            status="completed",
            result_refs={"artifact_id": "artifact-1"},
            failure=None,
            event=event,
            report=report,
        )


@pytest.mark.asyncio
async def test_finalize_terminal_job_rejects_conflicting_terminal_event(
    repository: AgentJobRepository,
) -> None:
    running = make_running_job()
    observed_at = NOW + timedelta(seconds=5)
    event = terminal_event_for(running, observed_at=observed_at)
    report = terminal_report_for(running, observed_at=observed_at)
    store_job(repository, running)
    event_ref = repository._job_ref(
        running.user_id,
        running.workspace_id,
        running.job_id,
    ).collection("events").document(event.event_id)
    repository._client.documents[event_ref.path] = event.model_copy(
        update={"message": "Conflicting event."}
    ).model_dump(mode="python")

    with pytest.raises(AgentJobConflictError):
        await repository.finalize_terminal_job(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
            job_id=running.job_id,
            lease_owner="worker-1",
            observed_at=observed_at,
            status="completed",
            result_refs={"artifact_id": "artifact-1"},
            failure=None,
            event=event,
            report=report,
        )

    assert (
        await repository.get_job(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
            job_id=running.job_id,
        )
    ).status == "running"


@pytest.mark.asyncio
async def test_finalize_terminal_job_rejects_conflicting_terminal_report(
    repository: AgentJobRepository,
) -> None:
    running = make_running_job()
    observed_at = NOW + timedelta(seconds=5)
    event = terminal_event_for(running, observed_at=observed_at)
    report = terminal_report_for(running, observed_at=observed_at)
    store_job(repository, running)
    report_ref = repository._reports_collection(
        running.user_id,
        running.workspace_id,
    ).document(report.report_id)
    repository._client.documents[report_ref.path] = report.model_copy(
        update={"summary": "Conflicting report."}
    ).model_dump(mode="python")

    with pytest.raises(AgentJobConflictError):
        await repository.finalize_terminal_job(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
            job_id=running.job_id,
            lease_owner="worker-1",
            observed_at=observed_at,
            status="completed",
            result_refs={"artifact_id": "artifact-1"},
            failure=None,
            event=event,
            report=report,
        )

    assert (
        await repository.get_job(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
            job_id=running.job_id,
        )
    ).status == "running"


@pytest.mark.asyncio
async def test_finalize_terminal_job_requires_matching_live_lease(
    repository: AgentJobRepository,
) -> None:
    observed_at = NOW + timedelta(seconds=5)
    for running, lease_owner in (
        (make_running_job(job_id="wrong-owner"), "worker-2"),
        (
            make_running_job(
                job_id="expired",
                lease_expires_at=NOW + timedelta(seconds=1),
            ),
            "worker-1",
        ),
    ):
        store_job(repository, running)
        with pytest.raises(AgentJobLeaseError):
            await repository.finalize_terminal_job(
                user_id=running.user_id,
                workspace_id=running.workspace_id,
                job_id=running.job_id,
                lease_owner=lease_owner,
                observed_at=observed_at,
                status="completed",
                result_refs={"artifact_id": "artifact-1"},
                failure=None,
                event=terminal_event_for(running, observed_at=observed_at),
                report=terminal_report_for(running, observed_at=observed_at),
            )


@pytest.mark.asyncio
async def test_finalize_terminal_job_transaction_failure_leaves_no_partial_terminal_state(
    repository: AgentJobRepository,
) -> None:
    running = make_running_job()
    observed_at = NOW + timedelta(seconds=5)
    event = terminal_event_for(running, observed_at=observed_at)
    report = terminal_report_for(running, observed_at=observed_at)
    store_job(repository, running)
    repository._client.transaction_obj.fail_after_sets = 1

    with pytest.raises(RuntimeError, match="simulated transaction failure"):
        await repository.finalize_terminal_job(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
            job_id=running.job_id,
            lease_owner="worker-1",
            observed_at=observed_at,
            status="completed",
            result_refs={"artifact_id": "artifact-1"},
            failure=None,
            event=event,
            report=report,
        )

    assert (
        await repository.get_job(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
            job_id=running.job_id,
        )
    ) == running
    assert await collect(
        repository.list_events(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
            job_id=running.job_id,
        )
    ) == []
    assert await collect(
        repository.list_reports(
            user_id=running.user_id,
            workspace_id=running.workspace_id,
        )
    ) == []


@pytest.mark.asyncio
async def test_renew_job_lease_extends_matching_live_owner(
    repository: AgentJobRepository,
) -> None:
    original_payload = make_payload()
    await repository.enqueue_job_with_payload(make_job(), original_payload)
    await repository.lease_next_queued_job(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=2),
        observed_at=NOW,
    )

    renewed = await repository.renew_job_lease(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=4),
        observed_at=NOW + timedelta(seconds=30),
    )

    assert renewed.status == "running"
    assert renewed.lease_owner == "worker-1"
    assert renewed.lease_expires_at == NOW + timedelta(minutes=4)
    assert renewed.attempt_count == 1
    assert renewed.retry_of_job_id is None
    stored = await repository.get_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    )
    assert stored == renewed
    payload = await repository.get_job_payload(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    )
    assert payload == original_payload


@pytest.mark.asyncio
async def test_renew_job_lease_rejects_wrong_owner(
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
        await repository.renew_job_lease(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="job-1",
            lease_owner="worker-2",
            lease_expires_at=NOW + timedelta(minutes=4),
            observed_at=NOW + timedelta(seconds=30),
        )


@pytest.mark.asyncio
async def test_renew_job_lease_rejects_expired_lease(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job(make_job())
    await repository.lease_next_queued_job(
        user_id="user-1",
        workspace_id="workspace-1",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(seconds=10),
        observed_at=NOW,
    )

    with pytest.raises(AgentJobLeaseError):
        await repository.renew_job_lease(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="job-1",
            lease_owner="worker-1",
            lease_expires_at=NOW + timedelta(minutes=4),
            observed_at=NOW + timedelta(seconds=10),
        )


@pytest.mark.asyncio
async def test_renew_job_lease_rejects_non_extending_expiry(
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
        await repository.renew_job_lease(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="job-1",
            lease_owner="worker-1",
            lease_expires_at=NOW + timedelta(minutes=1),
            observed_at=NOW + timedelta(seconds=30),
        )


@pytest.mark.asyncio
async def test_renew_job_lease_rejects_terminal_job(
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
    await repository.complete_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        lease_owner="worker-1",
        observed_at=NOW + timedelta(seconds=5),
        result_refs={"artifact_id": "artifact-1"},
    )

    with pytest.raises(AgentJobLeaseError):
        await repository.renew_job_lease(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="job-1",
            lease_owner="worker-1",
            lease_expires_at=NOW + timedelta(minutes=4),
            observed_at=NOW + timedelta(seconds=30),
        )


@pytest.mark.asyncio
async def test_recover_expired_running_job_requeues_same_job_and_payload(
    repository: AgentJobRepository,
) -> None:
    job = make_job(
        status="running",
        created_at=NOW - timedelta(minutes=3),
        lease_owner="worker-1",
        lease_expires_at=NOW - timedelta(seconds=1),
        attempt_count=3,
        retry_of_job_id="source-job-1",
        updated_at=NOW - timedelta(minutes=2),
    )
    payload = make_payload()
    store_job(repository, job)
    repository._client.documents[
        repository._payload_ref(
            job.user_id,
            job.workspace_id,
            job.job_id,
        ).path
    ] = payload.model_dump(mode="python")

    recovered = await repository.recover_expired_running_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        observed_at=NOW,
    )

    assert recovered is not None
    assert recovered.status == "queued"
    assert recovered.job_id == job.job_id
    assert recovered.user_id == job.user_id
    assert recovered.workspace_id == job.workspace_id
    assert recovered.project_id == job.project_id
    assert recovered.session_id == job.session_id
    assert recovered.source_turn_id == job.source_turn_id
    assert recovered.source_message_id == job.source_message_id
    assert recovered.action_kind == job.action_kind
    assert recovered.idempotency_key == job.idempotency_key
    assert recovered.attempt_count == job.attempt_count
    assert recovered.retry_of_job_id == job.retry_of_job_id
    assert recovered.lease_owner is None
    assert recovered.lease_expires_at is None
    assert recovered.updated_at == NOW
    assert await repository.get_job_payload(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    ) == payload


@pytest.mark.asyncio
async def test_recover_expired_running_job_leaves_unexpired_job_running(
    repository: AgentJobRepository,
) -> None:
    job = make_job(
        status="running",
        created_at=NOW - timedelta(minutes=3),
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(seconds=1),
        updated_at=NOW - timedelta(minutes=2),
    )
    store_job(repository, job)

    recovered = await repository.recover_expired_running_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        observed_at=NOW,
    )

    assert recovered is None
    stored = await repository.get_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    )
    assert stored == job


@pytest.mark.asyncio
async def test_recover_expired_running_job_revalidates_renewed_stale_candidate(
    repository: AgentJobRepository,
) -> None:
    job = make_job(
        status="running",
        created_at=NOW - timedelta(minutes=3),
        lease_owner="worker-1",
        lease_expires_at=NOW - timedelta(seconds=1),
        updated_at=NOW - timedelta(minutes=2),
    )
    store_job(repository, job)
    await repository.renew_job_lease(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=2),
        observed_at=NOW - timedelta(seconds=2),
    )

    recovered = await repository.recover_expired_running_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        observed_at=NOW,
    )

    assert recovered is None
    stored = await repository.get_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    )
    assert stored.status == "running"
    assert stored.lease_owner == "worker-1"
    assert stored.lease_expires_at == NOW + timedelta(minutes=2)


@pytest.mark.asyncio
async def test_recover_expired_running_job_is_safe_when_repeated(
    repository: AgentJobRepository,
) -> None:
    job = make_job(
        status="running",
        created_at=NOW - timedelta(minutes=3),
        lease_owner="worker-1",
        lease_expires_at=NOW - timedelta(seconds=1),
        updated_at=NOW - timedelta(minutes=2),
    )
    store_job(repository, job)

    first = await repository.recover_expired_running_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        observed_at=NOW,
    )
    second = await repository.recover_expired_running_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
        observed_at=NOW + timedelta(seconds=1),
    )

    assert first is not None
    assert first.status == "queued"
    assert second is None
    stored = await repository.get_job(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id="job-1",
    )
    assert stored == first


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
    await repository.enqueue_job_with_payload(make_job(), make_payload())
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
@pytest.mark.parametrize(
    ("action_kind", "private_payload"),
    (
        (
            "propose_memory_signal",
            {
                "work_type": "natural_memory_decision",
                "source_message_text": "Remember that I prefer terse answers.",
                "decision": {
                    "category": "response_length",
                    "action": "set",
                    "value": "terse",
                    "confidence": 0.92,
                    "reason": "User explicitly asked for terse answers.",
                },
                "memory_decision_present": False,
            },
        ),
        (
            "propose_collaborative_note",
            {
                "source_message_text": "Draft a deployment checklist note.",
                "decision": {
                    "note_kind": "project_plan",
                    "title": "Deployment checklist",
                    "body": "Verify build, deploy, and smoke tests.",
                    "confidence": 0.88,
                    "reason": "User asked for a checklist note.",
                },
                "memory_decision_present": False,
                "collaborative_note_decision_present": False,
                "artifact_feedback_decision_present": False,
            },
        ),
        (
            "create_artifact",
            {
                "artifact_family": "script",
                "artifact_format": "single_file",
                "filename": "deploy_check.sh",
                "source_text": "Create a deployment check script.",
                "display_label": "Create deploy_check.sh",
            },
        ),
    ),
)
async def test_retry_job_preserves_private_payload_for_worker_load(
    repository: AgentJobRepository,
    action_kind: str,
    private_payload: dict[str, object],
) -> None:
    source_job = make_job(action_kind=action_kind)
    source_payload = make_payload(
        action_kind=action_kind,
        payload=private_payload,
    )
    await repository.enqueue_job_with_payload(source_job, source_payload)
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
            summary="Worker timed out.",
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

    retry_payload = await repository.get_job_payload(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id=retry.job_id,
    )
    original_payload = await repository.get_job_payload(
        user_id="user-1",
        workspace_id="workspace-1",
        job_id=source_job.job_id,
    )
    assert retry_payload.job_id == retry.job_id
    assert retry_payload.created_at == source_payload.created_at
    assert retry_payload.payload == source_payload.payload
    assert original_payload == source_payload


@pytest.mark.asyncio
async def test_retry_job_replays_existing_retry_with_exact_private_payload(
    repository: AgentJobRepository,
) -> None:
    source_payload = make_payload(
        payload={
            "artifact_family": "script",
            "artifact_format": "single_file",
            "filename": "deploy_check.sh",
            "source_text": "Create a deployment check script.",
            "display_label": "Create deploy_check.sh",
        },
    )
    await repository.enqueue_job_with_payload(make_job(), source_payload)
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
            summary="Worker timed out.",
            retryable=True,
        ),
    )
    first = await repository.retry_job(
        user_id="user-1",
        workspace_id="workspace-1",
        source_job_id="job-1",
        retry_job_id="job-1-retry",
        idempotency_key="idem-1-retry",
        observed_at=NOW + timedelta(seconds=5),
    )

    replay = await repository.retry_job(
        user_id="user-1",
        workspace_id="workspace-1",
        source_job_id="job-1",
        retry_job_id="job-1-retry",
        idempotency_key="idem-1-retry",
        observed_at=NOW + timedelta(seconds=10),
    )

    assert replay == first


@pytest.mark.asyncio
async def test_retry_job_rejects_existing_retry_with_changed_payload_body(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job_with_payload(make_job(), make_payload())
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
            summary="Worker timed out.",
            retryable=True,
        ),
    )
    await repository.retry_job(
        user_id="user-1",
        workspace_id="workspace-1",
        source_job_id="job-1",
        retry_job_id="job-1-retry",
        idempotency_key="idem-1-retry",
        observed_at=NOW + timedelta(seconds=5),
    )
    repository._client.documents[
        (
            "users",
            "user-1",
            "workspaces",
            "workspace-1",
            "agent_jobs",
            "job-1-retry",
            "private_payloads",
            "payload",
        )
    ]["payload"] = {
        "artifact_family": "script",
        "filename": "different.sh",
        "source_text": "Different private instructions.",
    }

    with pytest.raises(AgentJobConflictError):
        await repository.retry_job(
            user_id="user-1",
            workspace_id="workspace-1",
            source_job_id="job-1",
            retry_job_id="job-1-retry",
            idempotency_key="idem-1-retry",
            observed_at=NOW + timedelta(seconds=10),
        )


@pytest.mark.asyncio
async def test_retry_job_rejects_existing_retry_with_missing_private_payload(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job_with_payload(make_job(), make_payload())
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
            summary="Worker timed out.",
            retryable=True,
        ),
    )
    await repository.retry_job(
        user_id="user-1",
        workspace_id="workspace-1",
        source_job_id="job-1",
        retry_job_id="job-1-retry",
        idempotency_key="idem-1-retry",
        observed_at=NOW + timedelta(seconds=5),
    )
    del repository._client.documents[
        (
            "users",
            "user-1",
            "workspaces",
            "workspace-1",
            "agent_jobs",
            "job-1-retry",
            "private_payloads",
            "payload",
        )
    ]

    with pytest.raises(AgentJobNotFoundError):
        await repository.retry_job(
            user_id="user-1",
            workspace_id="workspace-1",
            source_job_id="job-1",
            retry_job_id="job-1-retry",
            idempotency_key="idem-1-retry",
            observed_at=NOW + timedelta(seconds=10),
        )


@pytest.mark.asyncio
async def test_retry_job_rejects_existing_retry_with_corrupt_private_payload(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job_with_payload(make_job(), make_payload())
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
            summary="Worker timed out.",
            retryable=True,
        ),
    )
    await repository.retry_job(
        user_id="user-1",
        workspace_id="workspace-1",
        source_job_id="job-1",
        retry_job_id="job-1-retry",
        idempotency_key="idem-1-retry",
        observed_at=NOW + timedelta(seconds=5),
    )
    repository._client.documents[
        (
            "users",
            "user-1",
            "workspaces",
            "workspace-1",
            "agent_jobs",
            "job-1-retry",
            "private_payloads",
            "payload",
        )
    ]["job_id"] = "different-job"

    with pytest.raises(AgentJobStateError):
        await repository.retry_job(
            user_id="user-1",
            workspace_id="workspace-1",
            source_job_id="job-1",
            retry_job_id="job-1-retry",
            idempotency_key="idem-1-retry",
            observed_at=NOW + timedelta(seconds=10),
        )


@pytest.mark.asyncio
async def test_retry_job_rejects_missing_private_payload_without_retry_document(
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
            summary="Worker timed out.",
            retryable=True,
        ),
    )

    with pytest.raises(AgentJobNotFoundError):
        await repository.retry_job(
            user_id="user-1",
            workspace_id="workspace-1",
            source_job_id="job-1",
            retry_job_id="job-1-retry",
            idempotency_key="idem-1-retry",
            observed_at=NOW + timedelta(seconds=5),
        )
    with pytest.raises(AgentJobNotFoundError):
        await repository.get_job(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="job-1-retry",
        )


@pytest.mark.asyncio
async def test_retry_job_rejects_corrupt_private_payload_without_retry_document(
    repository: AgentJobRepository,
) -> None:
    await repository.enqueue_job_with_payload(make_job(), make_payload())
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
            summary="Worker timed out.",
            retryable=True,
        ),
    )
    repository._client.documents[
        (
            "users",
            "user-1",
            "workspaces",
            "workspace-1",
            "agent_jobs",
            "job-1",
            "private_payloads",
            "payload",
        )
    ]["job_id"] = "different-job"

    with pytest.raises(AgentJobStateError):
        await repository.retry_job(
            user_id="user-1",
            workspace_id="workspace-1",
            source_job_id="job-1",
            retry_job_id="job-1-retry",
            idempotency_key="idem-1-retry",
            observed_at=NOW + timedelta(seconds=5),
        )
    with pytest.raises(AgentJobNotFoundError):
        await repository.get_job(
            user_id="user-1",
            workspace_id="workspace-1",
            job_id="job-1-retry",
        )


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
