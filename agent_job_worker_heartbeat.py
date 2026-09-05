from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timedelta

from agent_col_agent_jobs import AgentJob
from agent_job_repository import AgentJobRepository


AGENT_JOB_LEASE_RENEWAL_INTERVAL_SECONDS = 40.0


class AgentJobLeaseHeartbeat:
    """Renew a running AgentJob lease for the lifetime of one worker execution."""

    def __init__(
        self,
        *,
        agent_job_repository: AgentJobRepository,
        job: AgentJob,
        lease_owner: str,
        clock: Callable[[], datetime],
        lease_seconds: int,
        renewal_interval_seconds: float = (
            AGENT_JOB_LEASE_RENEWAL_INTERVAL_SECONDS
        ),
        logger: logging.Logger,
    ) -> None:
        self._agent_job_repository = agent_job_repository
        self._job = job
        self._lease_owner = lease_owner
        self._clock = clock
        self._lease_seconds = lease_seconds
        self._renewal_interval_seconds = renewal_interval_seconds
        self._logger = logger
        self._task: asyncio.Task[None] | None = None
        self._owner_task: asyncio.Task[object] | None = None
        self._lost_error: BaseException | None = None

    async def __aenter__(self) -> AgentJobLeaseHeartbeat:
        self._owner_task = asyncio.current_task()
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        if exc_type is asyncio.CancelledError and self._lost_error is not None:
            raise self._lost_error

    def raise_if_lost(self) -> None:
        if self._lost_error is not None:
            raise self._lost_error

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._renewal_interval_seconds)
            observed_at = self._clock()
            try:
                await self._agent_job_repository.renew_job_lease(
                    user_id=self._job.user_id,
                    workspace_id=self._job.workspace_id,
                    job_id=self._job.job_id,
                    lease_owner=self._lease_owner,
                    lease_expires_at=observed_at
                    + timedelta(seconds=self._lease_seconds),
                    observed_at=observed_at,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._lost_error = exc
                self._logger.warning(
                    "AgentJob lease renewal failed for %s job %s.",
                    self._job.action_kind,
                    self._job.job_id,
                )
                if self._owner_task is not None:
                    self._owner_task.cancel()
                return
