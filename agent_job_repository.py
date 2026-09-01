from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import NoReturn

from google.api_core.exceptions import GoogleAPIError
from google.cloud import firestore
from google.cloud.firestore import AsyncClient, AsyncTransaction
from pydantic import ValidationError

from agent_col_agent_jobs import (
    TERMINAL_AGENT_JOB_STATUSES,
    AgentJob,
    AgentJobEvent,
    AgentJobFailure,
    AgentJobStatus,
    transition_agent_job,
)


logger = logging.getLogger(__name__)


class AgentJobRepositoryError(RuntimeError):
    """Raised when an Agent Job persistence operation fails."""


class AgentJobConflictError(RuntimeError):
    """Raised when an idempotent Agent Job write conflicts."""


class AgentJobNotFoundError(RuntimeError):
    """Raised when an Agent Job cannot be found in the owner scope."""


class AgentJobLeaseError(RuntimeError):
    """Raised when a worker does not hold the required live job lease."""


class AgentJobStateError(RuntimeError):
    """Raised when stored Agent Job state is invalid for the requested action."""


class AgentJobRepository:
    """Firestore-backed persistence for Agent Col background jobs."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def enqueue_job(self, job: AgentJob) -> AgentJob:
        if job.status != "queued":
            raise AgentJobStateError("Only queued AgentJobs can be enqueued.")
        try:
            jobs_ref = self._jobs_collection(job.user_id, job.workspace_id)
            job_ref = jobs_ref.document(job.job_id)
            transaction = self._client.transaction()

            async def enqueue_in_transaction(
                transaction: AsyncTransaction,
            ) -> AgentJob:
                snapshot = await job_ref.get(transaction=transaction)
                if snapshot.exists:
                    stored = self._job_from_snapshot(snapshot)
                    if stored != job:
                        raise AgentJobConflictError(
                            "AgentJob conflicts with existing job_id."
                        )
                    return stored
                existing = [
                    self._job_from_snapshot(match)
                    async for match in jobs_ref.where(
                        "idempotency_key",
                        "==",
                        job.idempotency_key,
                    )
                    .limit(1)
                    .stream(transaction=transaction)
                ]
                if existing:
                    raise AgentJobConflictError(
                        "AgentJob conflicts with existing idempotency key."
                    )
                transaction.set(job_ref, self._job_document(job))
                return job

            run_transaction = firestore.async_transactional(
                enqueue_in_transaction
            )
            return await run_transaction(transaction)
        except (AgentJobConflictError, AgentJobStateError):
            raise
        except ValidationError as exc:
            raise AgentJobStateError("Stored AgentJob state is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("enqueue_job", exc)

    async def get_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
    ) -> AgentJob:
        try:
            snapshot = await self._job_ref(
                user_id,
                workspace_id,
                job_id,
            ).get()
            if not snapshot.exists:
                raise AgentJobNotFoundError("AgentJob is unavailable.")
            job = self._job_from_snapshot(snapshot)
            self._validate_job_scope(
                job,
                user_id=user_id,
                workspace_id=workspace_id,
            )
            return job
        except (AgentJobNotFoundError, AgentJobStateError):
            raise
        except ValidationError as exc:
            raise AgentJobStateError("Stored AgentJob state is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("get_job", exc)

    async def list_jobs(
        self,
        *,
        user_id: str,
        workspace_id: str,
        project_id: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
    ) -> AsyncIterator[AgentJob]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        try:
            query = self._jobs_collection(user_id, workspace_id).order_by(
                "created_at"
            )
            count = 0
            async for snapshot in query.stream():
                job = self._job_from_snapshot(snapshot)
                self._validate_job_scope(
                    job,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
                if project_id is not None and job.project_id != project_id:
                    continue
                if session_id is not None and job.session_id != session_id:
                    continue
                yield job
                count += 1
                if count >= limit:
                    return
        except (AgentJobStateError, ValueError):
            raise
        except ValidationError as exc:
            raise AgentJobStateError("Stored AgentJob state is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("list_jobs", exc)

    async def lease_next_queued_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        lease_owner: str,
        lease_expires_at: datetime,
        observed_at: datetime,
    ) -> AgentJob | None:
        try:
            jobs_ref = self._jobs_collection(user_id, workspace_id)
            transaction = self._client.transaction()

            async def lease_in_transaction(
                transaction: AsyncTransaction,
            ) -> AgentJob | None:
                matches = [
                    snapshot
                    async for snapshot in jobs_ref.where(
                        "status",
                        "==",
                        "queued",
                    ).stream(transaction=transaction)
                ]
                if not matches:
                    return None
                candidates = []
                for snapshot in matches:
                    job = self._job_from_snapshot(snapshot)
                    self._validate_job_scope(
                        job,
                        user_id=user_id,
                        workspace_id=workspace_id,
                    )
                    candidates.append((job.created_at, snapshot, job))
                _, snapshot, job = min(candidates, key=lambda item: item[0])
                leased = transition_agent_job(
                    job,
                    status="running",
                    updated_at=observed_at,
                    lease_owner=lease_owner,
                    lease_expires_at=lease_expires_at,
                )
                transaction.set(
                    snapshot.reference,
                    self._job_document(leased),
                    merge=True,
                )
                return leased

            run_transaction = firestore.async_transactional(lease_in_transaction)
            return await run_transaction(transaction)
        except (AgentJobLeaseError, AgentJobStateError):
            raise
        except ValidationError as exc:
            raise AgentJobStateError("Stored AgentJob state is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("lease_next_queued_job", exc)

    async def complete_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
        lease_owner: str,
        observed_at: datetime,
        result_refs: dict[str, str],
    ) -> AgentJob:
        return await self._finish_leased_job(
            user_id=user_id,
            workspace_id=workspace_id,
            job_id=job_id,
            lease_owner=lease_owner,
            observed_at=observed_at,
            status="completed",
            result_refs=result_refs,
            failure=None,
        )

    async def fail_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
        lease_owner: str,
        observed_at: datetime,
        failure: AgentJobFailure,
    ) -> AgentJob:
        return await self._finish_leased_job(
            user_id=user_id,
            workspace_id=workspace_id,
            job_id=job_id,
            lease_owner=lease_owner,
            observed_at=observed_at,
            status="failed",
            result_refs=None,
            failure=failure,
        )

    async def cancel_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
        observed_at: datetime,
    ) -> AgentJob:
        try:
            job_ref = self._job_ref(user_id, workspace_id, job_id)
            transaction = self._client.transaction()

            async def cancel_in_transaction(
                transaction: AsyncTransaction,
            ) -> AgentJob:
                snapshot = await job_ref.get(transaction=transaction)
                job = self._available_scoped_job(
                    snapshot,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
                if job.status in TERMINAL_AGENT_JOB_STATUSES:
                    raise AgentJobStateError("Terminal AgentJob cannot cancel.")
                cancelled = transition_agent_job(
                    job,
                    status="cancelled",
                    updated_at=observed_at,
                )
                transaction.set(
                    job_ref,
                    self._job_document(cancelled),
                    merge=True,
                )
                return cancelled

            run_transaction = firestore.async_transactional(
                cancel_in_transaction
            )
            return await run_transaction(transaction)
        except (AgentJobNotFoundError, AgentJobStateError):
            raise
        except ValidationError as exc:
            raise AgentJobStateError("Stored AgentJob state is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("cancel_job", exc)

    async def retry_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        source_job_id: str,
        retry_job_id: str,
        idempotency_key: str,
        observed_at: datetime,
    ) -> AgentJob:
        try:
            source_ref = self._job_ref(user_id, workspace_id, source_job_id)
            retry_ref = self._job_ref(user_id, workspace_id, retry_job_id)
            jobs_ref = self._jobs_collection(user_id, workspace_id)
            transaction = self._client.transaction()

            async def retry_in_transaction(
                transaction: AsyncTransaction,
            ) -> AgentJob:
                source_snapshot = await source_ref.get(transaction=transaction)
                source = self._available_scoped_job(
                    source_snapshot,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
                if source.status != "failed" or not (
                    source.failure_summary
                    and source.failure_summary.retryable
                ):
                    raise AgentJobStateError("AgentJob is not retryable.")

                retry_snapshot = await retry_ref.get(transaction=transaction)
                if retry_snapshot.exists:
                    stored = self._job_from_snapshot(retry_snapshot)
                    if (
                        stored.retry_of_job_id != source.job_id
                        or stored.idempotency_key != idempotency_key
                    ):
                        raise AgentJobConflictError(
                            "Retry AgentJob conflicts with existing state."
                        )
                    return stored

                existing = [
                    self._job_from_snapshot(match)
                    async for match in jobs_ref.where(
                        "idempotency_key",
                        "==",
                        idempotency_key,
                    )
                    .limit(1)
                    .stream(transaction=transaction)
                ]
                if existing:
                    raise AgentJobConflictError(
                        "Retry AgentJob conflicts with existing idempotency key."
                    )
                retry = AgentJob(
                    job_id=retry_job_id,
                    user_id=source.user_id,
                    project_id=source.project_id,
                    workspace_id=source.workspace_id,
                    session_id=source.session_id,
                    source_turn_id=source.source_turn_id,
                    source_message_id=source.source_message_id,
                    action_kind=source.action_kind,
                    status="queued",
                    display_label=source.display_label,
                    agent_label=source.agent_label,
                    created_at=observed_at,
                    updated_at=observed_at,
                    idempotency_key=idempotency_key,
                    attempt_count=source.attempt_count + 1,
                    retry_of_job_id=source.job_id,
                )
                transaction.set(retry_ref, self._job_document(retry))
                return retry

            run_transaction = firestore.async_transactional(retry_in_transaction)
            return await run_transaction(transaction)
        except (
            AgentJobConflictError,
            AgentJobNotFoundError,
            AgentJobStateError,
        ):
            raise
        except ValidationError as exc:
            raise AgentJobStateError("Stored AgentJob state is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("retry_job", exc)

    async def append_event(
        self,
        *,
        user_id: str,
        workspace_id: str,
        event: AgentJobEvent,
    ) -> AgentJobEvent:
        try:
            job_ref = self._job_ref(user_id, workspace_id, event.job_id)
            event_ref = job_ref.collection("events").document(event.event_id)
            transaction = self._client.transaction()

            async def append_in_transaction(
                transaction: AsyncTransaction,
            ) -> AgentJobEvent:
                job_snapshot = await job_ref.get(transaction=transaction)
                self._available_scoped_job(
                    job_snapshot,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
                event_snapshot = await event_ref.get(transaction=transaction)
                if event_snapshot.exists:
                    stored = self._event_from_snapshot(event_snapshot)
                    if stored != event:
                        raise AgentJobConflictError(
                            "AgentJobEvent conflicts with existing event_id."
                        )
                    return stored
                transaction.set(event_ref, self._event_document(event))
                return event

            run_transaction = firestore.async_transactional(
                append_in_transaction
            )
            return await run_transaction(transaction)
        except (
            AgentJobConflictError,
            AgentJobNotFoundError,
            AgentJobStateError,
        ):
            raise
        except ValidationError as exc:
            raise AgentJobStateError("Stored AgentJobEvent state is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("append_event", exc)

    async def list_events(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
        limit: int = 50,
    ) -> AsyncIterator[AgentJobEvent]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        try:
            job = await self.get_job(
                user_id=user_id,
                workspace_id=workspace_id,
                job_id=job_id,
            )
            events_ref = self._job_ref(
                job.user_id,
                job.workspace_id,
                job.job_id,
            ).collection("events")
            query = events_ref.order_by("created_at").limit(limit)
            async for snapshot in query.stream():
                event = self._event_from_snapshot(snapshot)
                if event.job_id != job_id:
                    raise AgentJobStateError(
                        "Stored AgentJobEvent has mismatched job_id."
                    )
                if event.public_visibility:
                    yield event
        except (
            AgentJobNotFoundError,
            AgentJobStateError,
            ValueError,
        ):
            raise
        except ValidationError as exc:
            raise AgentJobStateError("Stored AgentJobEvent state is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("list_events", exc)

    async def _finish_leased_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
        lease_owner: str,
        observed_at: datetime,
        status: AgentJobStatus,
        result_refs: dict[str, str] | None,
        failure: AgentJobFailure | None,
    ) -> AgentJob:
        try:
            job_ref = self._job_ref(user_id, workspace_id, job_id)
            transaction = self._client.transaction()

            async def finish_in_transaction(
                transaction: AsyncTransaction,
            ) -> AgentJob:
                snapshot = await job_ref.get(transaction=transaction)
                job = self._available_scoped_job(
                    snapshot,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
                self._validate_live_lease(
                    job,
                    lease_owner=lease_owner,
                    observed_at=observed_at,
                )
                finished = transition_agent_job(
                    job,
                    status=status,
                    updated_at=observed_at,
                    result_refs=result_refs,
                    failure=failure,
                )
                transaction.set(
                    job_ref,
                    self._job_document(finished),
                    merge=True,
                )
                return finished

            run_transaction = firestore.async_transactional(
                finish_in_transaction
            )
            return await run_transaction(transaction)
        except (
            AgentJobLeaseError,
            AgentJobNotFoundError,
            AgentJobStateError,
        ):
            raise
        except ValidationError as exc:
            raise AgentJobStateError("Stored AgentJob state is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("_finish_leased_job", exc)

    def _jobs_collection(self, user_id: str, workspace_id: str):
        return (
            self._client.collection("users")
            .document(user_id)
            .collection("workspaces")
            .document(workspace_id)
            .collection("agent_jobs")
        )

    def _job_ref(self, user_id: str, workspace_id: str, job_id: str):
        return self._jobs_collection(user_id, workspace_id).document(job_id)

    @staticmethod
    def _available_scoped_job(
        snapshot: object,
        *,
        user_id: str,
        workspace_id: str,
    ) -> AgentJob:
        if not snapshot.exists:
            raise AgentJobNotFoundError("AgentJob is unavailable.")
        job = AgentJobRepository._job_from_snapshot(snapshot)
        AgentJobRepository._validate_job_scope(
            job,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return job

    @staticmethod
    def _validate_live_lease(
        job: AgentJob,
        *,
        lease_owner: str,
        observed_at: datetime,
    ) -> None:
        if (
            job.status != "running"
            or job.lease_owner != lease_owner
            or job.lease_expires_at is None
            or job.lease_expires_at <= observed_at
        ):
            raise AgentJobLeaseError(
                "AgentJob does not have a matching live lease."
            )

    @staticmethod
    def _validate_job_scope(
        job: AgentJob,
        *,
        user_id: str,
        workspace_id: str,
    ) -> None:
        if job.user_id != user_id or job.workspace_id != workspace_id:
            raise AgentJobStateError("Stored AgentJob owner scope is invalid.")

    @staticmethod
    def _job_document(job: AgentJob) -> dict[str, object]:
        return job.model_dump(mode="python")

    @staticmethod
    def _event_document(event: AgentJobEvent) -> dict[str, object]:
        return event.model_dump(mode="python")

    @staticmethod
    def _job_from_snapshot(snapshot: object) -> AgentJob:
        document = snapshot.to_dict()
        if document is None:
            raise AgentJobNotFoundError("AgentJob is unavailable.")
        return AgentJob.model_validate(document)

    @staticmethod
    def _event_from_snapshot(snapshot: object) -> AgentJobEvent:
        document = snapshot.to_dict()
        if document is None:
            raise AgentJobNotFoundError("AgentJobEvent is unavailable.")
        return AgentJobEvent.model_validate(document)

    @staticmethod
    def _raise_firestore_error(
        operation: str,
        error: Exception,
    ) -> NoReturn:
        logger.error("Firestore %s operation failed.", operation)
        raise AgentJobRepositoryError(
            f"Firestore {operation} operation failed."
        ) from error
