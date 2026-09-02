import hashlib
import logging
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Literal, Self

from google.adk.tools import FunctionTool, ToolContext
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from agent_col_agent_jobs import AgentJob, AgentJobEvent, AgentJobFailure
from agent_job_payloads import AgentJobPayload
from agent_job_repository import AgentJobRepository
from chat_turns import ChatTurnOwnershipError, ChatTurnStateError
from collaborative_note_candidates import (
    NaturalCollaborativeNoteDecision,
    NoteCandidateDecision,
    ProhibitedNoteDecision,
    validate_note_candidate_evidence,
    validate_provider_collaborative_note_decision,
)
from collaborative_note_service import (
    CollaborativeNoteProposalResult,
    CollaborativeNoteService,
    NaturalCollaborativeNoteCommand,
)
from database import (
    MemoryProposalConflictError,
    MemoryProposalOriginConflictError,
)
from memory_proposals import ProposalTurnLease
from schemas import (
    AgentActionReceipt,
    CollaborativeNoteProposal,
    QueuedActionReceipt,
)


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_PRECOMPLETED_DURABLE_EFFECT_STATE_KEY = (
    "governed_turn_has_precompleted_durable_effect"
)
_NOTE_AGENT_LABEL = "Note Curator"
_NOTE_JOB_LEASE_SECONDS = 120
logger = logging.getLogger(__name__)


class CollaborativeNoteToolConfigurationError(RuntimeError):
    """Raised when server-owned note tool context is absent or malformed."""


class CollaborativeNoteToolResponseError(RuntimeError):
    """Raised when an ADK note-tool response violates its contract."""


class _StrictToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PendingCollaborativeNoteToolResponse(_StrictToolResponse):
    status: Literal["pending"]
    action: AgentActionReceipt
    collaborative_note_proposal: CollaborativeNoteProposal

    @model_validator(mode="after")
    def require_proposal_action(self) -> Self:
        if self.action.action_name != "propose_collaborative_note":
            raise ValueError("Pending response has the wrong action.")
        return self


class RejectedCollaborativeNoteToolResponse(_StrictToolResponse):
    status: Literal["rejected"]
    error_code: Literal[
        "invalid_collaborative_note_candidate",
        "collaborative_note_proposal_conflict",
        "collaborative_note_turn_conflict",
    ]


class NoEffectCollaborativeNoteToolResponse(_StrictToolResponse):
    status: Literal["no_note", "prohibited"]


class QueuedCollaborativeNoteToolResponse(_StrictToolResponse):
    status: Literal["queued"]
    queued_action: QueuedActionReceipt


CollaborativeNoteToolResponse = (
    PendingCollaborativeNoteToolResponse
    | NoEffectCollaborativeNoteToolResponse
    | RejectedCollaborativeNoteToolResponse
    | QueuedCollaborativeNoteToolResponse
)


def parse_collaborative_note_tool_response(
    value: object,
) -> CollaborativeNoteToolResponse:
    try:
        if not isinstance(value, Mapping):
            raise ValueError("Response must be a mapping.")
        if value.get("status") == "pending":
            return PendingCollaborativeNoteToolResponse.model_validate(value)
        if value.get("status") == "queued":
            return QueuedCollaborativeNoteToolResponse.model_validate(value)
        if value.get("status") in {"no_note", "prohibited"}:
            return NoEffectCollaborativeNoteToolResponse.model_validate(value)
        if value.get("status") == "rejected":
            return RejectedCollaborativeNoteToolResponse.model_validate(value)
        raise ValueError("Response status is invalid.")
    except (TypeError, ValueError, ValidationError) as exc:
        raise CollaborativeNoteToolResponseError(
            "Collaborative note tool response is invalid."
        ) from exc


def _server_command(
    *,
    decision: NaturalCollaborativeNoteDecision,
    tool_context: ToolContext,
) -> NaturalCollaborativeNoteCommand:
    state = getattr(tool_context, "state", None)
    if not callable(getattr(state, "get", None)):
        raise CollaborativeNoteToolConfigurationError(
            "Collaborative note tool context is invalid."
        )
    try:
        user_id = state["note_user_id"]
        workspace_id = state["note_workspace_id"]
        session_id = state["note_session_id"]
        source_message_id = state["note_source_message_id"]
        source_message_text = state["note_source_message_text"]
        memory_decision_present = state["memory_decision_present"]
        collaborative_note_decision_present = state[
            "collaborative_note_decision_present"
        ]
        artifact_feedback_decision_present = state[
            "artifact_feedback_decision_present"
        ]
    except KeyError as exc:
        raise CollaborativeNoteToolConfigurationError(
            "Collaborative note tool context is invalid."
        ) from exc
    if any(
        not isinstance(value, str)
        or _IDENTIFIER_PATTERN.fullmatch(value) is None
        for value in (user_id, workspace_id, session_id, source_message_id)
    ):
        raise CollaborativeNoteToolConfigurationError(
            "Collaborative note tool context is invalid."
        )
    if (
        not isinstance(source_message_text, str)
        or not source_message_text.strip()
        or type(memory_decision_present) is not bool
        or type(collaborative_note_decision_present) is not bool
        or type(artifact_feedback_decision_present) is not bool
    ):
        raise CollaborativeNoteToolConfigurationError(
            "Collaborative note tool context is invalid."
        )
    turn_id = state.get("note_turn_id")
    owner_token = state.get("note_turn_owner_token")
    if (turn_id is None) != (owner_token is None):
        raise CollaborativeNoteToolConfigurationError(
            "Collaborative note tool context is invalid."
        )
    try:
        turn_lease = (
            ProposalTurnLease(turn_id=turn_id, owner_token=owner_token)
            if turn_id is not None
            else None
        )
    except ValueError as exc:
        raise CollaborativeNoteToolConfigurationError(
            "Collaborative note tool context is invalid."
        ) from exc
    return NaturalCollaborativeNoteCommand(
        user_id=user_id,
        workspace_id=workspace_id,
        session_id=session_id,
        source_message_id=source_message_id,
        source_message_text=source_message_text,
        memory_decision_present=memory_decision_present,
        collaborative_note_decision_present=collaborative_note_decision_present,
        artifact_feedback_decision_present=artifact_feedback_decision_present,
        decision=decision,
        observed_at=datetime.now(UTC),
        turn_lease=turn_lease,
    )


def _turn_has_precompleted_durable_effect(tool_context: ToolContext) -> bool:
    state = getattr(tool_context, "state", None)
    if not callable(getattr(state, "get", None)):
        raise CollaborativeNoteToolConfigurationError(
            "Collaborative note tool context is invalid."
        )
    value = state.get(_PRECOMPLETED_DURABLE_EFFECT_STATE_KEY, False)
    if type(value) is not bool:
        raise CollaborativeNoteToolConfigurationError(
            "Collaborative note tool context is invalid."
        )
    return value


def _note_job_digest(command: NaturalCollaborativeNoteCommand) -> str:
    turn_id = command.turn_lease.turn_id if command.turn_lease else ""
    material = "\0".join(
        (
            command.user_id,
            command.workspace_id,
            command.session_id,
            command.source_message_id,
            turn_id,
            str(command.accepted_action_index)
            if command.accepted_action_index is not None
            else "",
            command.decision.note_kind,
            command.decision.title,
            command.decision.body,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _note_job(command: NaturalCollaborativeNoteCommand) -> AgentJob:
    digest = _note_job_digest(command)
    title = command.decision.title.strip()
    display_label = f"Workspace note: {title}"[:160]
    return AgentJob(
        job_id=f"note-job-{digest}",
        user_id=command.user_id,
        project_id=command.workspace_id,
        workspace_id=command.workspace_id,
        session_id=command.session_id,
        source_turn_id=(
            command.turn_lease.turn_id
            if command.turn_lease
            else command.source_message_id
        ),
        source_message_id=command.source_message_id,
        action_kind="propose_collaborative_note",
        status="queued",
        display_label=display_label,
        agent_label=_NOTE_AGENT_LABEL,
        created_at=command.observed_at,
        updated_at=command.observed_at,
        idempotency_key=f"note-proposal-{digest}",
    )


def note_job_payload(
    command: NaturalCollaborativeNoteCommand,
    job: AgentJob,
) -> AgentJobPayload:
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
            "source_message_text": command.source_message_text,
            "memory_decision_present": command.memory_decision_present,
            "collaborative_note_decision_present": (
                command.collaborative_note_decision_present
            ),
            "artifact_feedback_decision_present": (
                command.artifact_feedback_decision_present
            ),
        },
    )


def _note_job_event(
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


async def _append_note_job_event(
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


async def _queue_note_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    command: NaturalCollaborativeNoteCommand,
) -> AgentJob:
    job = _note_job(command)
    queued = await agent_job_repository.enqueue_job_with_payload(
        job,
        note_job_payload(command, job),
    )
    await _append_note_job_event(
        agent_job_repository=agent_job_repository,
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        event=_note_job_event(
            job=queued,
            event_type="queued",
            message="Workspace note proposal queued.",
            observed_at=command.observed_at,
        ),
    )
    return queued


async def queue_collaborative_note_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    command: NaturalCollaborativeNoteCommand,
) -> QueuedActionReceipt:
    queued = await _queue_note_agent_job(
        agent_job_repository=agent_job_repository,
        command=command,
    )
    return queued.to_queued_action_receipt()


async def _start_note_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    command: NaturalCollaborativeNoteCommand,
) -> tuple[AgentJob, str]:
    queued = await agent_job_repository.enqueue_job(_note_job(command))
    await _append_note_job_event(
        agent_job_repository=agent_job_repository,
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        event=_note_job_event(
            job=queued,
            event_type="queued",
            message="Workspace note proposal queued.",
            observed_at=command.observed_at,
        ),
    )
    lease_owner = f"note-tool-{_note_job_digest(command)}"[:128]
    running_at = datetime.now(UTC)
    running = await agent_job_repository.lease_queued_job(
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        job_id=queued.job_id,
        lease_owner=lease_owner,
        lease_expires_at=running_at + timedelta(seconds=_NOTE_JOB_LEASE_SECONDS),
        observed_at=running_at,
    )
    await _append_note_job_event(
        agent_job_repository=agent_job_repository,
        user_id=running.user_id,
        workspace_id=running.workspace_id,
        event=_note_job_event(
            job=running,
            event_type="started",
            message="Workspace note proposal started.",
            observed_at=running_at,
        ),
    )
    return running, lease_owner


async def _complete_note_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    job: AgentJob,
    lease_owner: str,
    proposal_id: str,
) -> None:
    observed_at = datetime.now(UTC)
    completed = await agent_job_repository.complete_job(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        job_id=job.job_id,
        lease_owner=lease_owner,
        observed_at=observed_at,
        result_refs={"proposal_id": proposal_id},
    )
    await _append_note_job_event(
        agent_job_repository=agent_job_repository,
        user_id=completed.user_id,
        workspace_id=completed.workspace_id,
        event=_note_job_event(
            job=completed,
            event_type="completed",
            message="Workspace note proposal created.",
            observed_at=observed_at,
        ),
    )


async def _fail_note_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    job: AgentJob,
    lease_owner: str,
    error_code: str,
) -> None:
    observed_at = datetime.now(UTC)
    failed = await agent_job_repository.fail_job(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        job_id=job.job_id,
        lease_owner=lease_owner,
        observed_at=observed_at,
        failure=AgentJobFailure(
            code=error_code,
            summary="Workspace note proposal could not be created.",
            retryable=False,
        ),
    )
    await _append_note_job_event(
        agent_job_repository=agent_job_repository,
        user_id=failed.user_id,
        workspace_id=failed.workspace_id,
        event=_note_job_event(
            job=failed,
            event_type="failed",
            message="Workspace note proposal failed.",
            observed_at=observed_at,
        ),
    )


async def _try_start_note_agent_job(
    *,
    agent_job_repository: AgentJobRepository | None,
    command: NaturalCollaborativeNoteCommand,
) -> tuple[AgentJob | None, str | None]:
    if agent_job_repository is None:
        return None, None
    try:
        return await _start_note_agent_job(
            agent_job_repository=agent_job_repository,
            command=command,
        )
    except Exception:
        logger.exception(
            "Agent Col note job lifecycle could not start for source message."
        )
        return None, None


async def _try_complete_note_agent_job(
    *,
    agent_job_repository: AgentJobRepository | None,
    job: AgentJob | None,
    lease_owner: str | None,
    proposal_id: str,
) -> None:
    if agent_job_repository is None or job is None or lease_owner is None:
        return
    try:
        await _complete_note_agent_job(
            agent_job_repository=agent_job_repository,
            job=job,
            lease_owner=lease_owner,
            proposal_id=proposal_id,
        )
    except Exception:
        logger.exception(
            "Agent Col note job lifecycle could not complete for source message."
        )


async def _try_fail_note_agent_job(
    *,
    agent_job_repository: AgentJobRepository | None,
    job: AgentJob | None,
    lease_owner: str | None,
    error_code: str,
) -> None:
    if agent_job_repository is None or job is None or lease_owner is None:
        return
    try:
        await _fail_note_agent_job(
            agent_job_repository=agent_job_repository,
            job=job,
            lease_owner=lease_owner,
            error_code=error_code,
        )
    except Exception:
        logger.exception(
            "Agent Col note job lifecycle could not fail for source message."
        )


def create_propose_collaborative_note_tool(
    note_service: CollaborativeNoteService,
    *,
    agent_job_repository: AgentJobRepository | None = None,
    note_job_dispatcher: Callable[[AgentJob], None] | None = None,
) -> FunctionTool:
    async def propose_collaborative_note(
        decision: NaturalCollaborativeNoteDecision,
        tool_context: ToolContext,
    ) -> dict[str, object]:
        """Create a pending workspace-note proposal; never activate a note."""
        job: AgentJob | None = None
        lease_owner: str | None = None
        try:
            validated_decision = validate_provider_collaborative_note_decision(
                decision
            )
            if isinstance(validated_decision, ProhibitedNoteDecision):
                return {"status": "prohibited"}
            if not isinstance(validated_decision, NoteCandidateDecision):
                return {"status": "no_note"}
            if _turn_has_precompleted_durable_effect(tool_context):
                return {"status": "no_note"}
            command = _server_command(
                decision=validated_decision,
                tool_context=tool_context,
            )
            validate_note_candidate_evidence(
                validated_decision,
                command.source_message_text,
            )
            if (
                agent_job_repository is not None
                and note_job_dispatcher is not None
            ):
                queued_job = await _queue_note_agent_job(
                    agent_job_repository=agent_job_repository,
                    command=command,
                )
                note_job_dispatcher(queued_job)
                return {
                    "status": "queued",
                    "queued_action": (
                        queued_job.to_queued_action_receipt().model_dump(
                            mode="json"
                        )
                    ),
                }
            job, lease_owner = await _try_start_note_agent_job(
                agent_job_repository=agent_job_repository,
                command=command,
            )
            result = await note_service.create_natural_proposal(command)
        except ValueError:
            return {
                "status": "rejected",
                "error_code": "invalid_collaborative_note_candidate",
            }
        except (
            MemoryProposalConflictError,
            MemoryProposalOriginConflictError,
        ):
            await _try_fail_note_agent_job(
                agent_job_repository=agent_job_repository,
                job=job,
                lease_owner=lease_owner,
                error_code="collaborative_note_proposal_conflict",
            )
            return {
                "status": "rejected",
                "error_code": "collaborative_note_proposal_conflict",
            }
        except (ChatTurnOwnershipError, ChatTurnStateError):
            await _try_fail_note_agent_job(
                agent_job_repository=agent_job_repository,
                job=job,
                lease_owner=lease_owner,
                error_code="collaborative_note_turn_conflict",
            )
            return {
                "status": "rejected",
                "error_code": "collaborative_note_turn_conflict",
            }
        if isinstance(result, CollaborativeNoteProposalResult):
            if result.action is None:
                raise CollaborativeNoteToolResponseError(
                    "Collaborative note proposal action is missing."
                )
            await _try_complete_note_agent_job(
                agent_job_repository=agent_job_repository,
                job=job,
                lease_owner=lease_owner,
                proposal_id=result.proposal.proposal_id,
            )
            return {
                "status": "pending",
                "action": result.action.model_dump(mode="json"),
                "collaborative_note_proposal": result.proposal.model_dump(
                    mode="json"
                ),
            }
        raise CollaborativeNoteToolResponseError(
            "Collaborative note service result is invalid."
        )

    return FunctionTool(propose_collaborative_note)
