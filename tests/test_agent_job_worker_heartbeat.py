import asyncio
import logging
from datetime import UTC, datetime

import pytest

from agent_col_agent_jobs import AgentJob
from agent_job_worker_heartbeat import AgentJobLeaseHeartbeat


NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def make_job() -> AgentJob:
    return AgentJob(
        job_id="job-1",
        user_id="user-1",
        project_id="project-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_turn_id="turn-1",
        source_message_id="message-1",
        action_kind="create_artifact",
        status="running",
        display_label="Artifact",
        agent_label="Artifact Builder",
        created_at=NOW,
        updated_at=NOW,
        idempotency_key="job-key-1",
        attempt_count=1,
        lease_owner="worker-1",
        lease_expires_at=NOW,
    )


class NeverRenewRepository:
    async def renew_job_lease(self, **kwargs):
        raise AssertionError("external cancellation should not renew")


@pytest.mark.asyncio
async def test_heartbeat_preserves_external_cancellation_semantics() -> None:
    async def run_worker() -> None:
        async with AgentJobLeaseHeartbeat(
            agent_job_repository=NeverRenewRepository(),
            job=make_job(),
            lease_owner="worker-1",
            clock=lambda: NOW,
            lease_seconds=120,
            renewal_interval_seconds=60,
            logger=logging.getLogger(__name__),
        ):
            await asyncio.Event().wait()

    task = asyncio.create_task(run_worker())
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
