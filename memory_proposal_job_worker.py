from __future__ import annotations

import asyncio
import hashlib
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
from database import (
    MemoryProposalConflictError,
    MemoryProposalOriginConflictError,
    MemorySignalAlreadyActiveError,
)
from memory_candidate_decisions import (
    validate_provider_natural_memory_decision,
)
from memory_clarifications import MemoryClarificationSelection
from pydantic import TypeAdapter
from trusted_memory_service import (
    NaturalMemoryClarificationResult,
    NaturalMemoryCommand,
    NaturalMemoryNoEffectResult,
    NaturalMemoryProposalResult,
    TrustedMemoryService,
)


logger = logging.getLogger(__name__)
_CLARIFICATION_SELECTION_ADAPTER = TypeAdapter(MemoryClarificationSelection)
_MEMORY_JOB_LEASE_SECONDS = 120


def memory_job_payload(
    command: NaturalMemoryCommand,
    job: AgentJob,
) -> AgentJobPayload:
    """Build the private payload needed to execute one memory proposal job."""
    return AgentJobPayload(
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        source_turn_id=job.source_turn_id,
        source_message_id=job.source_message_id,
        action_kind=job.action_kind,
        created_at=job.created_at,
        payload={
            "decision": command.decision.model_dump(mode="json"),
            "clarification_selection": (
                command.clarification_selection.model_dump(mode="json")
                if command.clarification_selection is not None
                else None
            ),
            "source_message_text": command.source_message_text,
            "memory_decision_present": command.memory_decision_present,
        },
    )


def raw_memory_job_payload(
    *,
    job: AgentJob,
    decision: dict[str, object],
    clarification_selection: dict[str, object] | None,
    source_message_text: str,
    memory_decision_present: bool,
) -> AgentJobPayload:
    """Build a private job payload before governed memory validation runs."""
    return AgentJobPayload(
        job_id=job.job_id,
        user_id=job.user_id,
        project_id=job.project_id,
        workspace_id=job.workspace_id,
        session_id=job.session_id,
        source_turn_id=job.source_turn_id,
        source_message_id=job.source_message_id,
        action_kind=job.action_kind,
        created_at=job.created_at,
        payload={
            "decision": decision,
            "clarification_selection": clarification_selection,
            "source_message_text": source_message_text,
            "memory_decision_present": memory_decision_present,
        },
    )


def memory_command_from_payload(payload: AgentJobPayload) -> NaturalMemoryCommand:
    """Restore a governed memory command from a private AgentJob payload."""
    if payload.action_kind != "propose_memory_signal":
        raise ValueError("AgentJobPayload is not for memory proposal work.")
    data = payload.payload
    decision = validate_provider_natural_memory_decision(data.get("decision"))
    selection_data = data.get("clarification_selection")
    selection = (
        None
        if selection_data is None
        else _CLARIFICATION_SELECTION_ADAPTER.validate_python(selection_data)
    )
    source_message_text = data.get("source_message_text")
    memory_decision_present = data.get("memory_decision_present")
    if not isinstance(source_message_text, str):
        raise ValueError("Memory job source message text is invalid.")
    if type(memory_decision_present) is not bool:
        raise ValueError("Memory job decision-present flag is invalid.")
    return NaturalMemoryCommand(
        user_id=payload.user_id,
        workspace_id=payload.workspace_id,
        session_id=payload.session_id,
        source_message_id=payload.source_message_id,
        source_message_text=source_message_text,
        memory_decision_present=memory_decision_present,
        decision=decision,
        clarification_selection=selection,
        turn_lease=None,
    )


def _memory_job_event(
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


class MemoryProposalJobWorker:
    """Execute queued memory proposal jobs outside the chat response path."""

    def __init__(
        self,
        *,
        agent_job_repository: AgentJobRepository,
        memory_service: TrustedMemoryService,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        lease_seconds: int = _MEMORY_JOB_LEASE_SECONDS,
    ) -> None:
        self._agent_job_repository = agent_job_repository
        self._memory_service = memory_service
        self._clock = clock
        self._lease_seconds = lease_seconds

    def dispatch(
        self,
        job: AgentJob,
        *,
        task_set: set[asyncio.Task[AgentJob | None]] | None = None,
    ) -> asyncio.Task[AgentJob | None]:
        """Start one best-effort in-process memory job task."""
        task = asyncio.create_task(
            self.run_job(
                job,
                lease_owner=f"memory-worker-{job.job_id}"[:128],
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
            action_kind="propose_memory_signal",
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
            message="Memory proposal started.",
            observed_at=started_at,
        )
        try:
            payload = await self._agent_job_repository.get_job_payload(
                user_id=job.user_id,
                workspace_id=job.workspace_id,
                job_id=job.job_id,
            )
            result = await self._memory_service.handle_natural_memory_decision(
                memory_command_from_payload(payload)
            )
        except ValueError:
            return await self._fail_job(
                job=job,
                lease_owner=lease_owner,
                error_code="invalid_memory_candidate",
            )
        except (
            MemoryProposalConflictError,
            MemoryProposalOriginConflictError,
        ):
            return await self._fail_job(
                job=job,
                lease_owner=lease_owner,
                error_code="memory_proposal_conflict",
            )
        except MemorySignalAlreadyActiveError:
            return await self._fail_job(
                job=job,
                lease_owner=lease_owner,
                error_code="memory_signal_already_active",
            )
        except (ChatTurnOwnershipError, ChatTurnStateError):
            return await self._fail_job(
                job=job,
                lease_owner=lease_owner,
                error_code="memory_turn_conflict",
            )
        if isinstance(result, NaturalMemoryProposalResult):
            return await self._complete_job(
                job=job,
                lease_owner=lease_owner,
                result_refs={"proposal_id": result.proposal.proposal_id},
                message="Memory proposal created.",
                report_title="Memory proposal pending review",
                report_summary=(
                    "A memory proposal was created and is pending your review."
                ),
                public_resource_label=result.proposal.proposed_value,
            )
        if isinstance(result, NaturalMemoryClarificationResult):
            return await self._complete_job(
                job=job,
                lease_owner=lease_owner,
                result_refs={
                    "clarification_id": result.clarification.clarification_id
                },
                message="Memory clarification created.",
                report_title="Memory clarification pending response",
                report_summary=(
                    "A memory clarification was created and is pending your response."
                ),
                public_resource_label=None,
            )
        if isinstance(result, NaturalMemoryNoEffectResult):
            return await self._complete_job(
                job=job,
                lease_owner=lease_owner,
                result_refs={"status": result.status},
                message="Memory request required no durable effect.",
                report_title="Memory request did not need changes",
                report_summary="No durable memory change was needed for this request.",
                public_resource_label=None,
            )
        return await self._fail_job(
            job=job,
            lease_owner=lease_owner,
            error_code="invalid_memory_candidate",
        )

    async def _complete_job(
        self,
        *,
        job: AgentJob,
        lease_owner: str,
        result_refs: dict[str, str],
        message: str,
        report_title: str,
        report_summary: str,
        public_resource_label: str | None,
    ) -> AgentJob:
        observed_at = self._clock()
        completed = await self._agent_job_repository.complete_job(
            user_id=job.user_id,
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            lease_owner=lease_owner,
            observed_at=observed_at,
            result_refs=result_refs,
        )
        await self._append_event(
            job=completed,
            event_type="completed",
            message=message,
            observed_at=observed_at,
        )
        await self._create_report(
            job=completed,
            status="completed",
            title=report_title,
            summary=report_summary,
            public_resource_label=public_resource_label,
            observed_at=observed_at,
        )
        return completed

    async def _fail_job(
        self,
        *,
        job: AgentJob,
        lease_owner: str,
        error_code: str,
    ) -> AgentJob:
        observed_at = self._clock()
        failure_title, failure_summary = _memory_failure_report(error_code)
        failed = await self._agent_job_repository.fail_job(
            user_id=job.user_id,
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            lease_owner=lease_owner,
            observed_at=observed_at,
            failure=AgentJobFailure(
                code=error_code,
                summary=failure_summary,
                retryable=False,
            ),
        )
        await self._append_event(
            job=failed,
            event_type="failed",
            message="Memory proposal failed.",
            observed_at=observed_at,
        )
        await self._create_report(
            job=failed,
            status="failed",
            title=failure_title,
            summary=failure_summary,
            public_resource_label=None,
            observed_at=observed_at,
        )
        return failed

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
            report_id=_memory_report_id(job),
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
            event=_memory_job_event(
                job=job,
                event_type=event_type,
                message=message,
                observed_at=observed_at,
            ),
        )

    @staticmethod
    def _log_background_failure(task: asyncio.Task[AgentJob | None]) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Memory proposal background job failed.")


def _memory_report_id(job: AgentJob) -> str:
    digest = hashlib.sha256(job.job_id.encode("utf-8")).hexdigest()[:32]
    return f"agent-job-report-{digest}"


def _memory_failure_report(error_code: str) -> tuple[str, str]:
    if error_code == "memory_proposal_conflict":
        return (
            "Memory proposal not created",
            "A pending memory proposal already exists for this category.",
        )
    if error_code == "memory_signal_already_active":
        return (
            "Memory proposal not created",
            "That memory is already active.",
        )
    if error_code == "memory_turn_conflict":
        return (
            "Memory proposal not created",
            "The memory request could not be attached to the current turn.",
        )
    return (
        "Memory proposal not created",
        "Memory proposal could not be created.",
    )
