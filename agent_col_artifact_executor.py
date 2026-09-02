"""Deterministic synchronous artifact execution for routed Agent_Col turns."""

import hashlib
import json
import logging
import re
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from agent_col_agent_jobs import (
    AgentJob,
    AgentJobEvent,
    AgentJobFailure,
    AgentJobReport,
    AgentJobReportStatus,
)
from agent_job_payloads import AgentJobPayload
from agent_job_repository import AgentJobRepository
from agent_col_routing_v4 import AgentColRoute, AgentColRoutingDirective
from artifact_read_service import GetBlueprintArtifactCommand
from chat_turns import ChatTurnClaim
from database import ChatTurnArtifactEffectResult
from generic_artifact_creation_service import GenericArtifactCreationCommand
from generic_artifact_generation import (
    GENERIC_ARTIFACT_MODEL_NAME,
    GenericArtifactGenerationRequest,
)
from generic_artifact_service import GetGenericArtifactCommand
from schemas import (
    SYNTHESIS_BLUEPRINT_SCHEMA_VERSION,
    AgentActionReceipt,
    ArtifactReference,
    BlueprintArtifactDetailResponse,
    QueuedActionReceipt,
    SingleFileArtifact,
    SingleFileArtifactDetailResponse,
    VersionedAdaptationReceipt,
    derive_single_file_artifact_display_label,
)
from synthesis import SYNTHESIS_MODEL_NAME
from synthesis_service import (
    GovernedSynthesisGenerationResult,
    SynthesisCommand,
)


_CONTEXT_START = "[SERVER_VALIDATED_ARTIFACT_RESULT]"
_CONTEXT_END = "[/SERVER_VALIDATED_ARTIFACT_RESULT]"
_ARTIFACT_REFERENCE_WORDS = re.compile(
    r"\b(?:that|this|it|above|previous|conversation|chat)\b",
    re.IGNORECASE,
)
_ARTIFACT_TRIGGER_WORDS = re.compile(
    r"\b(?:artifact|blueprint|deliverable|markdown|text|json|pdf|printable)\b",
    re.IGNORECASE,
)
_MAX_RECENT_ARTIFACT_CONTEXT_MESSAGES = 6
_ARTIFACT_AGENT_LABEL = "Artifact Builder"
_ARTIFACT_JOB_LEASE_SECONDS = 120
logger = logging.getLogger(__name__)


class ArtifactSynthesisService(Protocol):
    async def generate_governed_blueprint(
        self,
        command: SynthesisCommand,
    ) -> GovernedSynthesisGenerationResult: ...

    async def synthesize(self, command: SynthesisCommand) -> object: ...


class ArtifactEffectLedger(Protocol):
    async def record_chat_turn_blueprint_effect(
        self,
        claim: ChatTurnClaim,
        *,
        model_name: str,
        schema_version: str,
        blueprint: dict[str, object],
        display_label: str,
        observed_at: datetime,
        adaptations: tuple[VersionedAdaptationReceipt, ...],
    ) -> ChatTurnArtifactEffectResult: ...

    async def record_chat_turn_single_file_artifact_effect(
        self,
        claim: ChatTurnClaim,
        *,
        model_name: str,
        artifact: dict[str, object],
        display_label: str,
        observed_at: datetime,
    ) -> ChatTurnArtifactEffectResult: ...


class ArtifactReader(Protocol):
    async def get_blueprint(
        self,
        command: GetBlueprintArtifactCommand,
    ) -> BlueprintArtifactDetailResponse: ...


class GenericArtifactGenerator(Protocol):
    async def __call__(
        self,
        client: object,
        request: GenericArtifactGenerationRequest,
    ) -> SingleFileArtifact: ...


class GenericArtifactCreator(Protocol):
    async def create_artifact(
        self,
        command: GenericArtifactCreationCommand,
    ) -> object: ...


class GenericArtifactReader(Protocol):
    async def get_artifact(
        self,
        command: GetGenericArtifactCommand,
    ) -> SingleFileArtifactDetailResponse: ...


class AgentColArtifactExecutorConfigurationError(RuntimeError):
    """Raised when artifact execution receives inconsistent authority."""


class AgentColArtifactResponderProjection(BaseModel):
    """Bounded canonical artifact facts allowed into the responder."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    operation: Literal[
        "create_blueprint", "create_single_file_artifact"
    ] = "create_blueprint"
    artifact: ArtifactReference
    project_name: str | None = Field(default=None, min_length=1, max_length=120)
    core_value_proposition: str | None = Field(
        default=None,
        min_length=1,
        max_length=1_500,
    )
    socratic_questions: tuple[str, ...] = Field(max_length=5)
    adaptations: tuple[VersionedAdaptationReceipt, ...] = Field(
        default_factory=tuple
    )
    limitations: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    artifact_family: str | None = Field(default=None, min_length=1, max_length=40)
    format: str | None = Field(default=None, min_length=1, max_length=40)
    filename: str | None = Field(default=None, min_length=1, max_length=160)
    summary: str | None = Field(default=None, min_length=1, max_length=1_500)


@dataclass(frozen=True, slots=True)
class AgentColArtifactExecutionCommand:
    claim: ChatTurnClaim
    routing_directive: AgentColRoutingDirective
    observed_at: datetime
    source_text: str | None = None
    accepted_action_index: int | None = None


@dataclass(frozen=True, slots=True)
class AgentColArtifactExecutionResult:
    claim: ChatTurnClaim
    actions: tuple[AgentActionReceipt, ...]
    artifacts: tuple[ArtifactReference, ...]
    adaptations: tuple[VersionedAdaptationReceipt, ...]
    projection: AgentColArtifactResponderProjection


@dataclass(frozen=True, slots=True)
class AgentColArtifactQueueResult:
    claim: ChatTurnClaim
    queued_actions: tuple[QueuedActionReceipt, ...]
    actions: tuple[AgentActionReceipt, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()


def _artifact_job_digest(command: AgentColArtifactExecutionCommand) -> str:
    intent = command.routing_directive.artifact_intent
    assert intent is not None
    material = json.dumps(
        {
            "project_id": command.claim.request.project_id,
            "session_id": command.claim.request.session_id,
            "user_id": command.claim.request.user_id,
            "turn_id": command.claim.ids.turn_id,
            "source_message_id": command.claim.ids.user_message_id,
            "accepted_action_index": command.accepted_action_index,
            "operation": intent.operation,
            "artifact_family": intent.artifact_family,
            "format": intent.format,
            "filename": intent.filename,
            "source_text": command.source_text or command.claim.request.message,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _artifact_job_display_label(
    command: AgentColArtifactExecutionCommand,
) -> str:
    intent = command.routing_directive.artifact_intent
    assert intent is not None
    if intent.filename:
        return f"Artifact: {intent.filename}"[:160]
    return "Artifact: structured blueprint"[:160]


def _artifact_job(command: AgentColArtifactExecutionCommand) -> AgentJob:
    digest = _artifact_job_digest(command)
    return AgentJob(
        job_id=f"artifact-job-{digest}",
        user_id=command.claim.request.user_id,
        project_id=command.claim.request.project_id,
        workspace_id=command.claim.request.project_id,
        session_id=command.claim.request.session_id,
        source_turn_id=command.claim.ids.turn_id,
        source_message_id=command.claim.ids.user_message_id,
        action_kind="create_artifact",
        status="queued",
        display_label=_artifact_job_display_label(command),
        agent_label=_ARTIFACT_AGENT_LABEL,
        created_at=command.observed_at,
        updated_at=command.observed_at,
        idempotency_key=f"artifact-create-{digest}",
    )


def artifact_job_payload(
    command: AgentColArtifactExecutionCommand,
    job: AgentJob,
) -> AgentJobPayload:
    """Build the private payload needed for background artifact creation."""
    intent = command.routing_directive.artifact_intent
    assert intent is not None
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
            "artifact_intent": intent.model_dump(mode="json"),
            "source_text": command.source_text or command.claim.request.message,
        },
    )


def _artifact_job_event(
    *,
    job: AgentJob,
    event_type: Literal["queued", "started", "completed", "failed"],
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


async def _append_artifact_job_event(
    *,
    agent_job_repository: AgentJobRepository,
    user_id: str,
    workspace_id: str,
    event: AgentJobEvent,
) -> None:
    await agent_job_repository.append_event(
        user_id=user_id,
        workspace_id=workspace_id,
        event=event,
    )


async def _start_artifact_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    command: AgentColArtifactExecutionCommand,
) -> tuple[AgentJob, str]:
    queued = await agent_job_repository.enqueue_job(_artifact_job(command))
    await _append_artifact_job_event(
        agent_job_repository=agent_job_repository,
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        event=_artifact_job_event(
            job=queued,
            event_type="queued",
            message="Artifact creation queued.",
            observed_at=queued.created_at,
        ),
    )
    lease_owner = f"artifact-tool-{_artifact_job_digest(command)}"[:128]
    running_at = datetime.now(UTC)
    running = await agent_job_repository.lease_queued_job(
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        job_id=queued.job_id,
        lease_owner=lease_owner,
        lease_expires_at=running_at + timedelta(
            seconds=_ARTIFACT_JOB_LEASE_SECONDS
        ),
        observed_at=running_at,
    )
    await _append_artifact_job_event(
        agent_job_repository=agent_job_repository,
        user_id=running.user_id,
        workspace_id=running.workspace_id,
        event=_artifact_job_event(
            job=running,
            event_type="started",
            message="Artifact creation started.",
            observed_at=running_at,
        ),
    )
    return running, lease_owner


async def _queue_artifact_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    command: AgentColArtifactExecutionCommand,
) -> AgentJob:
    job = _artifact_job(command)
    queued = await agent_job_repository.enqueue_job_with_payload(
        job,
        artifact_job_payload(command, job),
    )
    await _append_artifact_job_event(
        agent_job_repository=agent_job_repository,
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        event=_artifact_job_event(
            job=queued,
            event_type="queued",
            message="Artifact creation queued.",
            observed_at=queued.created_at,
        ),
    )
    return queued


async def _complete_artifact_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    job: AgentJob,
    lease_owner: str,
    artifact_id: str,
) -> None:
    observed_at = datetime.now(UTC)
    completed = await agent_job_repository.complete_job(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        job_id=job.job_id,
        lease_owner=lease_owner,
        observed_at=observed_at,
        result_refs={"artifact_id": artifact_id},
    )
    await _append_artifact_job_event(
        agent_job_repository=agent_job_repository,
        user_id=completed.user_id,
        workspace_id=completed.workspace_id,
        event=_artifact_job_event(
            job=completed,
            event_type="completed",
            message="Artifact created.",
            observed_at=observed_at,
        ),
    )


async def _fail_artifact_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    job: AgentJob,
    lease_owner: str,
) -> None:
    observed_at = datetime.now(UTC)
    failed = await agent_job_repository.fail_job(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        job_id=job.job_id,
        lease_owner=lease_owner,
        observed_at=observed_at,
        failure=AgentJobFailure(
            code="artifact_creation_failed",
            summary="Artifact could not be created.",
            retryable=False,
        ),
    )
    await _append_artifact_job_event(
        agent_job_repository=agent_job_repository,
        user_id=failed.user_id,
        workspace_id=failed.workspace_id,
        event=_artifact_job_event(
            job=failed,
            event_type="failed",
            message="Artifact creation failed.",
            observed_at=observed_at,
        ),
    )


async def _try_start_artifact_agent_job(
    *,
    agent_job_repository: AgentJobRepository | None,
    command: AgentColArtifactExecutionCommand,
) -> tuple[AgentJob | None, str | None]:
    if agent_job_repository is None:
        return None, None
    try:
        return await _start_artifact_agent_job(
            agent_job_repository=agent_job_repository,
            command=command,
        )
    except Exception:
        logger.exception(
            "Agent Col artifact job lifecycle could not start for source turn."
        )
        return None, None


async def _try_complete_artifact_agent_job(
    *,
    agent_job_repository: AgentJobRepository | None,
    job: AgentJob | None,
    lease_owner: str | None,
    artifact_id: str,
) -> None:
    if agent_job_repository is None or job is None or lease_owner is None:
        return
    try:
        await _complete_artifact_agent_job(
            agent_job_repository=agent_job_repository,
            job=job,
            lease_owner=lease_owner,
            artifact_id=artifact_id,
        )
    except Exception:
        logger.exception(
            "Agent Col artifact job lifecycle could not complete for source turn."
        )


async def _try_fail_artifact_agent_job(
    *,
    agent_job_repository: AgentJobRepository | None,
    job: AgentJob | None,
    lease_owner: str | None,
) -> None:
    if agent_job_repository is None or job is None or lease_owner is None:
        return
    try:
        await _fail_artifact_agent_job(
            agent_job_repository=agent_job_repository,
            job=job,
            lease_owner=lease_owner,
        )
    except Exception:
        logger.exception(
            "Agent Col artifact job lifecycle could not fail for source turn."
        )


class AgentColArtifactCreationJobWorker:
    """Execute queued artifact creation jobs outside the chat response path."""

    def __init__(
        self,
        *,
        agent_job_repository: AgentJobRepository,
        synthesis_service: ArtifactSynthesisService,
        generic_artifact_generator: GenericArtifactGenerator | None = None,
        generic_artifact_creator: GenericArtifactCreator | None = None,
        genai_client: object | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        lease_seconds: int = _ARTIFACT_JOB_LEASE_SECONDS,
    ) -> None:
        self._agent_job_repository = agent_job_repository
        self._synthesis_service = synthesis_service
        self._generic_artifact_generator = generic_artifact_generator
        self._generic_artifact_creator = generic_artifact_creator
        self._genai_client = genai_client
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
                lease_owner=f"artifact-worker-{job.job_id}"[:128],
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
            action_kind="create_artifact",
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
            message="Artifact creation started.",
            observed_at=started_at,
        )
        try:
            payload = await self._agent_job_repository.get_job_payload(
                user_id=job.user_id,
                workspace_id=job.workspace_id,
                job_id=job.job_id,
            )
            artifact_id, label = await self._execute_payload(payload)
        except Exception:
            return await self._fail_job(
                job=job,
                lease_owner=lease_owner,
            )
        return await self._complete_job(
            job=job,
            lease_owner=lease_owner,
            artifact_id=artifact_id,
            public_resource_label=label,
        )

    async def _execute_payload(
        self,
        payload: AgentJobPayload,
    ) -> tuple[str, str]:
        if payload.action_kind != "create_artifact":
            raise ValueError("AgentJobPayload is not for artifact work.")
        data = payload.payload
        intent = data.get("artifact_intent")
        source_text = data.get("source_text")
        if not isinstance(intent, dict) or not isinstance(source_text, str):
            raise ValueError("Artifact job payload is invalid.")
        operation = intent.get("operation")
        if operation == "create_single_file_artifact":
            return await self._execute_single_file_payload(
                payload,
                intent,
                source_text,
            )
        if operation == "create_blueprint":
            return await self._execute_blueprint_payload(payload, source_text)
        raise ValueError("Artifact job operation is invalid.")

    async def _execute_blueprint_payload(
        self,
        payload: AgentJobPayload,
        source_text: str,
    ) -> tuple[str, str]:
        result = await self._synthesis_service.synthesize(
            SynthesisCommand(
                project_id=payload.project_id,
                session_id=payload.session_id,
                user_id=payload.user_id,
                source_text=source_text,
            )
        )
        blueprint = result.blueprint
        label = blueprint.synthesized_conceptual_model.project_name
        return result.blueprint_id, label

    async def _execute_single_file_payload(
        self,
        payload: AgentJobPayload,
        intent: dict[str, object],
        source_text: str,
    ) -> tuple[str, str]:
        if (
            self._generic_artifact_generator is None
            or self._generic_artifact_creator is None
            or self._genai_client is None
        ):
            raise AgentColArtifactExecutorConfigurationError(
                "Generic artifact worker dependencies are unavailable."
            )
        family = intent.get("artifact_family")
        format_name = intent.get("format")
        filename = intent.get("filename")
        if (
            not isinstance(family, str)
            or not isinstance(format_name, str)
            or not isinstance(filename, str)
        ):
            raise ValueError("Single-file artifact intent is invalid.")
        generated = await self._generic_artifact_generator(
            self._genai_client,
            GenericArtifactGenerationRequest(
                artifact_family=family,
                artifact_format=format_name,
                filename=filename,
                source_text=source_text,
                context_messages=(),
            ),
        )
        created = await self._generic_artifact_creator.create_artifact(
            GenericArtifactCreationCommand(
                project_id=payload.project_id,
                session_id=payload.session_id,
                user_id=payload.user_id,
                artifact=generated.model_dump(mode="json"),
                display_label=None,
                originating_turn_id=payload.source_turn_id,
            )
        )
        return created.reference.artifact_id, created.reference.display_label

    async def _complete_job(
        self,
        *,
        job: AgentJob,
        lease_owner: str,
        artifact_id: str,
        public_resource_label: str,
    ) -> AgentJob:
        observed_at = self._clock()
        completed = await self._agent_job_repository.complete_job(
            user_id=job.user_id,
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            lease_owner=lease_owner,
            observed_at=observed_at,
            result_refs={"artifact_id": artifact_id},
        )
        await self._append_event(
            job=completed,
            event_type="completed",
            message="Artifact created.",
            observed_at=observed_at,
        )
        await self._create_report(
            job=completed,
            status="completed",
            title="Artifact created",
            summary="The requested artifact was created.",
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
                code="artifact_creation_failed",
                summary="Artifact could not be created.",
                retryable=False,
            ),
        )
        await self._append_event(
            job=failed,
            event_type="failed",
            message="Artifact creation failed.",
            observed_at=observed_at,
        )
        await self._create_report(
            job=failed,
            status="failed",
            title="Artifact not created",
            summary="Artifact could not be created.",
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
            report_id=_artifact_report_id(job),
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
            event=_artifact_job_event(
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
            logger.exception("Artifact creation background job failed.")


def _artifact_report_id(job: AgentJob) -> str:
    digest = hashlib.sha256(job.job_id.encode("utf-8")).hexdigest()[:32]
    return f"agent-job-report-{digest}"


class AgentColArtifactExecutor:
    def __init__(
        self,
        *,
        synthesis_service: ArtifactSynthesisService,
        artifact_ledger: ArtifactEffectLedger,
        artifact_reader: ArtifactReader,
        generic_artifact_generator: GenericArtifactGenerator | None = None,
        generic_artifact_reader: GenericArtifactReader | None = None,
        genai_client: object | None = None,
        agent_job_repository: AgentJobRepository | None = None,
        artifact_job_dispatcher: Callable[[AgentJob], None] | None = None,
    ) -> None:
        self._synthesis_service = synthesis_service
        self._artifact_ledger = artifact_ledger
        self._artifact_reader = artifact_reader
        self._generic_artifact_generator = generic_artifact_generator
        self._generic_artifact_reader = generic_artifact_reader
        self._genai_client = genai_client
        self._agent_job_repository = agent_job_repository
        self._artifact_job_dispatcher = artifact_job_dispatcher

    async def execute(
        self,
        command: AgentColArtifactExecutionCommand,
    ) -> AgentColArtifactExecutionResult:
        claim = command.claim
        self._validate_command(command)
        assert command.routing_directive.artifact_intent is not None
        operation = command.routing_directive.artifact_intent.operation
        if operation == "create_single_file_artifact":
            return await self._execute_single_file_artifact(command)
        return await self._execute_blueprint(command)

    async def queue(
        self,
        command: AgentColArtifactExecutionCommand,
    ) -> AgentColArtifactQueueResult:
        self._validate_command(command)
        if self._agent_job_repository is None:
            raise AgentColArtifactExecutorConfigurationError(
                "Artifact job repository is unavailable."
            )
        queued = await _queue_artifact_agent_job(
            agent_job_repository=self._agent_job_repository,
            command=command,
        )
        if self._artifact_job_dispatcher is not None:
            self._artifact_job_dispatcher(queued)
        return AgentColArtifactQueueResult(
            claim=command.claim,
            queued_actions=(queued.to_queued_action_receipt(),),
        )

    async def _execute_blueprint(
        self,
        command: AgentColArtifactExecutionCommand,
    ) -> AgentColArtifactExecutionResult:
        claim = command.claim
        artifact = self._precompleted_artifact(
            claim,
            expected_action_name="synthesize_project",
        )
        job: AgentJob | None = None
        lease_owner: str | None = None
        if artifact is None:
            job, lease_owner = await _try_start_artifact_agent_job(
                agent_job_repository=self._agent_job_repository,
                command=command,
            )
            try:
                generated = await (
                    self._synthesis_service.generate_governed_blueprint(
                        SynthesisCommand(
                            project_id=claim.request.project_id,
                            session_id=claim.request.session_id,
                            user_id=claim.request.user_id,
                            source_text=(
                                command.source_text or claim.request.message
                            ),
                        )
                    )
                )
                blueprint = generated.blueprint
                effect = (
                    await self._artifact_ledger.record_chat_turn_blueprint_effect(
                        claim,
                        model_name=SYNTHESIS_MODEL_NAME,
                        schema_version=SYNTHESIS_BLUEPRINT_SCHEMA_VERSION,
                        blueprint=blueprint.model_dump(mode="json"),
                        display_label=(
                            blueprint.synthesized_conceptual_model.project_name
                        ),
                        observed_at=command.observed_at,
                        adaptations=generated.adaptations,
                    )
                )
                claim = effect.claim
                artifact = effect.artifact
            except Exception:
                await _try_fail_artifact_agent_job(
                    agent_job_repository=self._agent_job_repository,
                    job=job,
                    lease_owner=lease_owner,
                )
                raise

        if artifact.artifact_type != "synthesis_blueprint":
            raise AgentColArtifactExecutorConfigurationError(
                "Precompleted artifact effects are inconsistent."
            )
        try:
            detail = await self._artifact_reader.get_blueprint(
                GetBlueprintArtifactCommand(
                    project_id=claim.request.project_id,
                    blueprint_id=artifact.artifact_id,
                )
            )
            self._validate_canonical_detail(claim, artifact, detail)
        except Exception:
            await _try_fail_artifact_agent_job(
                agent_job_repository=self._agent_job_repository,
                job=job,
                lease_owner=lease_owner,
            )
            raise
        action = AgentActionReceipt(
            action_name="synthesize_project",
            status="completed",
        )
        if claim.precompleted_actions != (action,) or (
            claim.precompleted_artifacts != (artifact,)
        ):
            raise AgentColArtifactExecutorConfigurationError(
                "Artifact effect receipts are inconsistent."
            )
        projection = self._projection(detail)
        await _try_complete_artifact_agent_job(
            agent_job_repository=self._agent_job_repository,
            job=job,
            lease_owner=lease_owner,
            artifact_id=artifact.artifact_id,
        )
        return AgentColArtifactExecutionResult(
            claim=claim,
            actions=(action,),
            artifacts=(artifact,),
            adaptations=tuple(detail.adaptations),
            projection=projection,
        )

    async def _execute_single_file_artifact(
        self,
        command: AgentColArtifactExecutionCommand,
    ) -> AgentColArtifactExecutionResult:
        claim = command.claim
        intent = command.routing_directive.artifact_intent
        if (
            intent is None
            or intent.operation != "create_single_file_artifact"
            or intent.artifact_family is None
            or intent.format is None
            or intent.filename is None
            or self._generic_artifact_generator is None
            or self._generic_artifact_reader is None
            or self._genai_client is None
        ):
            raise AgentColArtifactExecutorConfigurationError(
                "Artifact execution command is invalid."
            )
        artifact = self._precompleted_artifact(
            claim,
            expected_action_name="create_artifact",
        )
        job: AgentJob | None = None
        lease_owner: str | None = None
        if artifact is None:
            job, lease_owner = await _try_start_artifact_agent_job(
                agent_job_repository=self._agent_job_repository,
                command=command,
            )
            try:
                generated = await self._generic_artifact_generator(
                    self._genai_client,
                    GenericArtifactGenerationRequest(
                        artifact_family=intent.artifact_family,
                        artifact_format=intent.format,
                        filename=intent.filename,
                        source_text=command.source_text or claim.request.message,
                        context_messages=(),
                    ),
                )
                effect = await (
                    self._artifact_ledger
                    .record_chat_turn_single_file_artifact_effect(
                        claim,
                        model_name=GENERIC_ARTIFACT_MODEL_NAME,
                        artifact=generated.model_dump(mode="json"),
                        display_label=derive_single_file_artifact_display_label(
                            display_label=None,
                            summary=generated.summary,
                            filename=generated.filename,
                        ),
                        observed_at=command.observed_at,
                    )
                )
                claim = effect.claim
                artifact = effect.artifact
            except Exception:
                await _try_fail_artifact_agent_job(
                    agent_job_repository=self._agent_job_repository,
                    job=job,
                    lease_owner=lease_owner,
                )
                raise
        if artifact.artifact_type != "single_file_artifact":
            raise AgentColArtifactExecutorConfigurationError(
                "Precompleted artifact effects are inconsistent."
            )
        try:
            detail = await self._generic_artifact_reader.get_artifact(
                GetGenericArtifactCommand(
                    project_id=claim.request.project_id,
                    artifact_id=artifact.artifact_id,
                )
            )
            self._validate_single_file_canonical_detail(claim, artifact, detail)
        except Exception:
            await _try_fail_artifact_agent_job(
                agent_job_repository=self._agent_job_repository,
                job=job,
                lease_owner=lease_owner,
            )
            raise
        action = AgentActionReceipt(
            action_name="create_artifact",
            status="completed",
        )
        if claim.precompleted_actions != (action,) or (
            claim.precompleted_artifacts != (artifact,)
        ):
            raise AgentColArtifactExecutorConfigurationError(
                "Artifact effect receipts are inconsistent."
            )
        projection = self._single_file_projection(detail)
        await _try_complete_artifact_agent_job(
            agent_job_repository=self._agent_job_repository,
            job=job,
            lease_owner=lease_owner,
            artifact_id=artifact.artifact_id,
        )
        return AgentColArtifactExecutionResult(
            claim=claim,
            actions=(action,),
            artifacts=(artifact,),
            adaptations=(),
            projection=projection,
        )

    @staticmethod
    def _validate_command(command: AgentColArtifactExecutionCommand) -> None:
        if not isinstance(command, AgentColArtifactExecutionCommand):
            raise AgentColArtifactExecutorConfigurationError(
                "Artifact execution command is invalid."
            )
        claim = command.claim
        directive = command.routing_directive
        if (
            not isinstance(claim, ChatTurnClaim)
            or not isinstance(directive, AgentColRoutingDirective)
            or directive.route is not AgentColRoute.ARTIFACT
            or directive.artifact_intent is None
            or claim.request.memory_decision is not None
            or claim.request.artifact_feedback_decision is not None
            or claim.precompleted_memory_proposals
            or claim.precompleted_artifact_feedback
            or command.observed_at.tzinfo is None
            or command.observed_at.utcoffset() is None
        ):
            raise AgentColArtifactExecutorConfigurationError(
                "Artifact execution command is invalid."
            )

    @staticmethod
    def _precompleted_artifact(
        claim: ChatTurnClaim,
        *,
        expected_action_name: Literal["synthesize_project", "create_artifact"],
    ) -> ArtifactReference | None:
        action = AgentActionReceipt(
            action_name=expected_action_name,
            status="completed",
        )
        if (
            not claim.precompleted_actions
            and not claim.precompleted_artifacts
        ):
            return None
        if (
            claim.precompleted_actions != (action,)
            or len(claim.precompleted_artifacts) != 1
        ):
            raise AgentColArtifactExecutorConfigurationError(
                "Precompleted artifact effects are inconsistent."
            )
        return claim.precompleted_artifacts[0]

    @staticmethod
    def _validate_canonical_detail(
        claim: ChatTurnClaim,
        artifact: ArtifactReference,
        detail: BlueprintArtifactDetailResponse,
    ) -> None:
        metadata = detail.metadata
        if (
            metadata.reference != artifact
            or metadata.originating_session_id != claim.request.session_id
            or metadata.originating_turn_id != claim.ids.turn_id
        ):
            raise AgentColArtifactExecutorConfigurationError(
                "Canonical artifact does not match its turn effect."
            )

    @staticmethod
    def _validate_single_file_canonical_detail(
        claim: ChatTurnClaim,
        artifact: ArtifactReference,
        detail: SingleFileArtifactDetailResponse,
    ) -> None:
        metadata = detail.metadata
        if (
            metadata.reference != artifact
            or metadata.originating_session_id != claim.request.session_id
            or metadata.originating_turn_id != claim.ids.turn_id
        ):
            raise AgentColArtifactExecutorConfigurationError(
                "Canonical artifact does not match its turn effect."
            )

    @staticmethod
    def _projection(
        detail: BlueprintArtifactDetailResponse,
    ) -> AgentColArtifactResponderProjection:
        conceptual_model = detail.blueprint.synthesized_conceptual_model
        return AgentColArtifactResponderProjection(
            artifact=detail.metadata.reference,
            project_name=conceptual_model.project_name,
            core_value_proposition=conceptual_model.core_value_proposition,
            socratic_questions=tuple(
                question.question_text
                for question in detail.blueprint.socratic_clarifying_questions
            ),
            adaptations=tuple(detail.adaptations),
        )

    @staticmethod
    def _single_file_projection(
        detail: SingleFileArtifactDetailResponse,
    ) -> AgentColArtifactResponderProjection:
        artifact = detail.artifact
        return AgentColArtifactResponderProjection(
            operation="create_single_file_artifact",
            artifact=detail.metadata.reference,
            socratic_questions=(),
            artifact_family=artifact.artifact_family,
            format=artifact.format,
            filename=artifact.filename,
            summary=artifact.summary or detail.metadata.reference.display_label,
        )


def build_agent_col_artifact_model_context(
    projection: AgentColArtifactResponderProjection,
) -> types.Content:
    """Render one bounded server-validated artifact responder context."""
    payload = json.dumps(
        projection.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    text = (
        "The application already created and persisted the authoritative "
        "artifact. Do not reroute, call an expert, regenerate the artifact, "
        "or invent artifact contents. Explain only the bounded validated "
        "projection below. The action, artifact, and adaptation receipts are "
        "application-owned and must not be changed.\n"
        f"{_CONTEXT_START}\n"
        f"{payload}\n"
        f"{_CONTEXT_END}"
    )
    return types.Content(
        role="user",
        parts=[types.Part.from_text(text=text)],
    )


def build_agent_col_artifact_queued_model_context(
    queued_action: QueuedActionReceipt,
) -> types.Content:
    payload = json.dumps(
        queued_action.model_dump(mode="json", exclude={"job_id"}),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    text = (
        "The application queued artifact creation. Artifact work is queued "
        "for background processing. "
        "Do not claim the artifact is already created, persisted, visible, "
        "or inspectable yet. You may acknowledge that artifact work is queued "
        "and direct the user to the artifact surface or job reports for the "
        "final result. Do not expose internal job identifiers.\n"
        f"{payload}"
    )
    return types.Content(
        role="user",
        parts=[types.Part.from_text(text=text)],
    )


def build_artifact_source_text(
    *,
    current_message: str,
    recent_user_messages: Sequence[str] = (),
) -> str:
    """Build the exact server-owned source text supplied to synthesis.

    Self-contained artifact requests remain a single-source command. Short
    reference-style requests can include recent user-authored messages, making
    turns such as "turn that into a markdown artifact" useful without letting
    the model choose persistence input.
    """
    current = current_message.strip()
    if not current:
        raise AgentColArtifactExecutorConfigurationError(
            "Artifact source text is invalid."
        )
    if not _should_include_recent_artifact_context(current):
        return current

    recent = tuple(
        message.strip()
        for message in recent_user_messages[-_MAX_RECENT_ARTIFACT_CONTEXT_MESSAGES:]
        if message.strip()
    )
    if not recent:
        return current
    recent_context = "\n\n".join(recent)
    return (
        "[CURRENT_ARTIFACT_REQUEST]\n"
        f"{current}\n"
        "[/CURRENT_ARTIFACT_REQUEST]\n\n"
        "[RECENT_USER_CONTEXT]\n"
        f"{recent_context}\n"
        "[/RECENT_USER_CONTEXT]"
    )


def _should_include_recent_artifact_context(current_message: str) -> bool:
    word_count = len(re.findall(r"\b[\w'-]+\b", current_message))
    return bool(
        _ARTIFACT_TRIGGER_WORDS.search(current_message)
        and (
            word_count < 10
            or _ARTIFACT_REFERENCE_WORDS.search(current_message)
        )
    )
