from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from agent_col_agent_jobs import (
    AgentJob,
    AgentJobEvent,
    AgentJobFailure,
    AgentJobReport,
    AgentJobReportStatus,
)
from agent_job_payloads import AgentJobPayload
from agent_job_repository import AgentJobRepository
from chat_turns import ChatTurnOwnershipError, ChatTurnStateError
from collaborative_note_candidates import (
    NoteCandidateDecision,
    validate_provider_collaborative_note_decision,
)
from collaborative_note_service import (
    CollaborativeNoteProposalResult,
    CollaborativeNoteService,
    NaturalCollaborativeNoteCommand,
)
from collaborative_note_tool import note_job_payload
from database import (
    MemoryProposalConflictError,
    MemoryProposalOriginConflictError,
)


logger = logging.getLogger(__name__)
_NOTE_JOB_LEASE_SECONDS = 120


def note_command_from_payload(
    payload: AgentJobPayload,
) -> NaturalCollaborativeNoteCommand:
    if payload.action_kind != "propose_collaborative_note":
        raise ValueError("AgentJobPayload is not for note proposal work.")
    data = payload.payload
    decision = validate_provider_collaborative_note_decision(
        data.get("decision")
    )
    if not isinstance(decision, NoteCandidateDecision):
        raise ValueError("Note job payload decision is invalid.")
    source_message_text = data.get("source_message_text")
    memory_decision_present = data.get("memory_decision_present")
    collaborative_note_decision_present = data.get(
        "collaborative_note_decision_present"
    )
    artifact_feedback_decision_present = data.get(
        "artifact_feedback_decision_present"
    )
    if not isinstance(source_message_text, str):
        raise ValueError("Note job source message text is invalid.")
    if (
        type(memory_decision_present) is not bool
        or type(collaborative_note_decision_present) is not bool
        or type(artifact_feedback_decision_present) is not bool
    ):
        raise ValueError("Note job decision-present flags are invalid.")
    return NaturalCollaborativeNoteCommand(
        user_id=payload.user_id,
        workspace_id=payload.workspace_id,
        session_id=payload.session_id,
        source_message_id=payload.source_message_id,
        source_message_text=source_message_text,
        memory_decision_present=memory_decision_present,
        collaborative_note_decision_present=collaborative_note_decision_present,
        artifact_feedback_decision_present=artifact_feedback_decision_present,
        decision=decision,
        observed_at=datetime.now(UTC),
        turn_lease=None,
    )


def _note_job_event(
    *,
    job: AgentJob,
    event_type: Literal["started", "completed", "failed"],
    message: str,
    observed_at: datetime,
) -> AgentJobEvent:
    return AgentJobEvent(
        event_id=f"{job.job_id}-{event_type}",
        job_id=job.job_id,
        event_type=event_type,
        message=message,
        created_at=observed_at,
        status=job.status,
    )


def _note_report_id(job: AgentJob) -> str:
    return f"{job.job_id}-report"


class CollaborativeNoteProposalJobWorker:
    """Execute queued collaborative note proposal jobs outside chat."""

    def __init__(
        self,
        *,
        agent_job_repository: AgentJobRepository,
        note_service: CollaborativeNoteService,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        lease_seconds: int = _NOTE_JOB_LEASE_SECONDS,
    ) -> None:
        self._agent_job_repository = agent_job_repository
        self._note_service = note_service
        self._clock = clock
        self._lease_seconds = lease_seconds

    def dispatch(
        self,
        job: AgentJob,
        *,
        task_set: set[asyncio.Task[AgentJob | None]] | None = None,
    ) -> asyncio.Task[AgentJob | None]:
        task = asyncio.create_task(
            self.run_job(
                job,
                lease_owner=f"note-worker-{job.job_id}"[:128],
            )
        )
        if task_set is not None:
            task_set.add(task)
            task.add_done_callback(task_set.discard)
        task.add_done_callback(self._log_background_failure)
        return task

    async def run_one(
        self,
        *,
        user_id: str,
        workspace_id: str,
        lease_owner: str,
    ) -> AgentJob | None:
        observed_at = self._clock()
        job = await self._agent_job_repository.lease_next_queued_job(
            user_id=user_id,
            workspace_id=workspace_id,
            lease_owner=lease_owner,
            lease_expires_at=observed_at
            + timedelta(seconds=self._lease_seconds),
            observed_at=observed_at,
            action_kind="propose_collaborative_note",
        )
        if job is None:
            return None
        return await self._execute_leased_job(
            job,
            lease_owner=lease_owner,
            started_at=observed_at,
        )

    async def run_job(
        self,
        job: AgentJob,
        *,
        lease_owner: str,
    ) -> AgentJob | None:
        observed_at = self._clock()
        leased = await self._agent_job_repository.lease_queued_job(
            user_id=job.user_id,
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            lease_owner=lease_owner,
            lease_expires_at=observed_at
            + timedelta(seconds=self._lease_seconds),
            observed_at=observed_at,
        )
        return await self._execute_leased_job(
            leased,
            lease_owner=lease_owner,
            started_at=observed_at,
        )

    async def _execute_leased_job(
        self,
        job: AgentJob,
        *,
        lease_owner: str,
        started_at: datetime,
    ) -> AgentJob:
        await self._append_event(
            job=job,
            event_type="started",
            message="Workspace note proposal started.",
            observed_at=started_at,
        )
        try:
            payload = await self._agent_job_repository.get_job_payload(
                user_id=job.user_id,
                workspace_id=job.workspace_id,
                job_id=job.job_id,
            )
            result = await self._note_service.create_natural_proposal(
                note_command_from_payload(payload)
            )
        except ValueError:
            return await self._fail_job(job=job, lease_owner=lease_owner)
        except (
            MemoryProposalConflictError,
            MemoryProposalOriginConflictError,
            ChatTurnOwnershipError,
            ChatTurnStateError,
        ):
            return await self._fail_job(job=job, lease_owner=lease_owner)
        if isinstance(result, CollaborativeNoteProposalResult):
            return await self._complete_job(
                job=job,
                lease_owner=lease_owner,
                proposal_id=result.proposal.proposal_id,
                public_resource_label=result.proposal.title,
            )
        return await self._fail_job(job=job, lease_owner=lease_owner)

    async def _complete_job(
        self,
        *,
        job: AgentJob,
        lease_owner: str,
        proposal_id: str,
        public_resource_label: str,
    ) -> AgentJob:
        observed_at = self._clock()
        completed = await self._agent_job_repository.complete_job(
            user_id=job.user_id,
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            lease_owner=lease_owner,
            observed_at=observed_at,
            result_refs={"proposal_id": proposal_id},
        )
        await self._append_event(
            job=completed,
            event_type="completed",
            message="Workspace note proposal created.",
            observed_at=observed_at,
        )
        await self._create_report(
            job=completed,
            status="completed",
            title="Workspace note proposal pending review",
            summary=(
                "A workspace note proposal was created and is pending your review."
            ),
            public_resource_label=public_resource_label,
            observed_at=observed_at,
        )
        return completed

    async def _fail_job(
        self,
        *,
        job: AgentJob,
        lease_owner: str,
    ) -> AgentJob:
        observed_at = self._clock()
        failed = await self._agent_job_repository.fail_job(
            user_id=job.user_id,
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            lease_owner=lease_owner,
            observed_at=observed_at,
            failure=AgentJobFailure(
                code="collaborative_note_proposal_conflict",
                summary="Workspace note proposal could not be created.",
                retryable=False,
            ),
        )
        await self._append_event(
            job=failed,
            event_type="failed",
            message="Workspace note proposal failed.",
            observed_at=observed_at,
        )
        await self._create_report(
            job=failed,
            status="failed",
            title="Workspace note proposal not created",
            summary="Workspace note proposal could not be created.",
            public_resource_label=None,
            observed_at=observed_at,
        )
        return failed

    async def _append_event(
        self,
        *,
        job: AgentJob,
        event_type: Literal["started", "completed", "failed"],
        message: str,
        observed_at: datetime,
    ) -> None:
        await self._agent_job_repository.append_event(
            user_id=job.user_id,
            workspace_id=job.workspace_id,
            event=_note_job_event(
                job=job,
                event_type=event_type,
                message=message,
                observed_at=observed_at,
            ),
        )

    async def _create_report(
        self,
        *,
        job: AgentJob,
        status: AgentJobReportStatus,
        title: str,
        summary: str,
        public_resource_label: str | None,
        observed_at: datetime,
    ) -> AgentJobReport:
        report = AgentJobReport(
            report_id=_note_report_id(job),
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
        return await self._agent_job_repository.create_report(report)

    @staticmethod
    def _log_background_failure(task: asyncio.Task[AgentJob | None]) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Background note proposal job failed unexpectedly.")
