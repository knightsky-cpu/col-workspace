import hashlib
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Literal, Self

from google.adk.tools import FunctionTool, ToolContext
from pydantic import (
    BaseModel,
    ConfigDict,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from agent_col_agent_jobs import AgentJob, AgentJobEvent, AgentJobFailure
from agent_job_repository import AgentJobRepository
from chat_turns import ChatTurnOwnershipError, ChatTurnStateError
from database import (
    MemoryProposalConflictError,
    MemoryProposalOriginConflictError,
    MemorySignalAlreadyActiveError,
)
from memory_candidate_decisions import (
    NaturalMemoryDecision,
    ProviderNaturalMemoryDecision,
    validate_provider_natural_memory_decision,
)
from memory_clarifications import (
    MemoryClarificationReceipt,
    MemoryClarificationSelection,
)
from memory_proposals import ProposalTurnLease
from schemas import AgentActionReceipt, MemoryProposalReceiptV2
from trusted_memory_service import (
    NaturalMemoryClarificationResult,
    NaturalMemoryCommand,
    NaturalMemoryNoEffectResult,
    NaturalMemoryProposalResult,
    TrustedMemoryService,
)


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_CLARIFICATION_SELECTION_ADAPTER = TypeAdapter(MemoryClarificationSelection)
_MEMORY_AGENT_LABEL = "Memory Analyst"
_MEMORY_JOB_LEASE_SECONDS = 120
logger = logging.getLogger(__name__)


class MemoryProposalToolConfigurationError(RuntimeError):
    """Raised when server-owned tool context is absent or malformed."""


class MemoryProposalToolResponseError(RuntimeError):
    """Raised when an ADK proposal-tool response violates its contract."""


class _StrictToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PendingMemoryProposalToolResponse(_StrictToolResponse):
    status: Literal["pending"]
    action: AgentActionReceipt
    memory_proposal: MemoryProposalReceiptV2

    @model_validator(mode="after")
    def require_proposal_action(self) -> Self:
        if self.action.action_name != "propose_memory_signal":
            raise ValueError("Pending response has the wrong action.")
        return self


class RejectedMemoryProposalToolResponse(_StrictToolResponse):
    status: Literal["rejected"]
    error_code: Literal[
        "invalid_memory_candidate",
        "memory_proposal_conflict",
        "memory_signal_already_active",
        "memory_turn_conflict",
    ]


class ClarificationMemoryProposalToolResponse(_StrictToolResponse):
    status: Literal["clarification_required"]
    memory_clarification: MemoryClarificationReceipt


class NoEffectMemoryProposalToolResponse(_StrictToolResponse):
    status: Literal[
        "no_memory",
        "session_only",
        "workspace_note",
        "unsupported",
        "prohibited",
    ]


MemoryProposalToolResponse = (
    PendingMemoryProposalToolResponse
    | ClarificationMemoryProposalToolResponse
    | NoEffectMemoryProposalToolResponse
    | RejectedMemoryProposalToolResponse
)


def parse_memory_proposal_tool_response(
    value: object,
) -> MemoryProposalToolResponse:
    """Validate one public ADK proposal-tool response envelope."""
    try:
        if not isinstance(value, Mapping):
            raise ValueError("Response must be a mapping.")
        if value.get("status") == "pending":
            return PendingMemoryProposalToolResponse.model_validate(value)
        if value.get("status") == "clarification_required":
            return ClarificationMemoryProposalToolResponse.model_validate(
                value
            )
        if value.get("status") in {
            "no_memory",
            "session_only",
            "workspace_note",
            "unsupported",
            "prohibited",
        }:
            return NoEffectMemoryProposalToolResponse.model_validate(value)
        if value.get("status") == "rejected":
            return RejectedMemoryProposalToolResponse.model_validate(value)
        raise ValueError("Response status is invalid.")
    except (TypeError, ValueError, ValidationError) as exc:
        raise MemoryProposalToolResponseError(
            "Memory proposal tool response is invalid."
        ) from exc


def _server_command(
    *,
    decision: NaturalMemoryDecision,
    clarification_selection: MemoryClarificationSelection | None,
    tool_context: ToolContext,
) -> NaturalMemoryCommand:
    state = getattr(tool_context, "state", None)
    if not callable(getattr(state, "get", None)):
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        )
    try:
        user_id = state["memory_user_id"]
        workspace_id = state["memory_workspace_id"]
        session_id = state["memory_session_id"]
        source_message_id = state["memory_source_message_id"]
        source_message_text = state["memory_source_message_text"]
        memory_decision_present = state["memory_decision_present"]
        artifact_feedback_decision_present = state[
            "artifact_feedback_decision_present"
        ]
    except KeyError as exc:
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        ) from exc
    if any(
        not isinstance(value, str)
        or _IDENTIFIER_PATTERN.fullmatch(value) is None
        for value in (user_id, workspace_id, session_id, source_message_id)
    ):
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        )
    if (
        not isinstance(source_message_text, str)
        or not source_message_text.strip()
        or type(memory_decision_present) is not bool
        or type(artifact_feedback_decision_present) is not bool
    ):
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        )
    if artifact_feedback_decision_present:
        raise ValueError(
            "Artifact feedback turns cannot create memory proposals."
        )
    turn_id = state.get("memory_turn_id")
    owner_token = state.get("memory_turn_owner_token")
    if (turn_id is None) != (owner_token is None):
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        )
    try:
        turn_lease = (
            ProposalTurnLease(turn_id=turn_id, owner_token=owner_token)
            if turn_id is not None
            else None
        )
    except ValueError as exc:
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        ) from exc
    return NaturalMemoryCommand(
        user_id=user_id,
        workspace_id=workspace_id,
        session_id=session_id,
        source_message_id=source_message_id,
        source_message_text=source_message_text,
        memory_decision_present=memory_decision_present,
        decision=decision,
        clarification_selection=clarification_selection,
        turn_lease=turn_lease,
    )


def _memory_job_digest(command: NaturalMemoryCommand) -> str:
    turn_id = command.turn_lease.turn_id if command.turn_lease else ""
    selection = (
        command.clarification_selection.model_dump(mode="json")
        if command.clarification_selection is not None
        else None
    )
    material = json_dumps_compact(
        {
            "user_id": command.user_id,
            "workspace_id": command.workspace_id,
            "session_id": command.session_id,
            "source_message_id": command.source_message_id,
            "turn_id": turn_id,
            "decision": command.decision.model_dump(mode="json"),
            "clarification_selection": selection,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def json_dumps_compact(value: object) -> str:
    import json

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _memory_job_display_label(command: NaturalMemoryCommand) -> str:
    category = getattr(command.decision, "category", None)
    if isinstance(category, str) and category:
        return f"Memory proposal: {category}"[:160]
    if command.decision.kind == "clarify":
        return "Memory clarification"[:160]
    return "Memory proposal"[:160]


def _memory_job(command: NaturalMemoryCommand) -> AgentJob:
    digest = _memory_job_digest(command)
    observed_at = datetime.now(UTC)
    return AgentJob(
        job_id=f"memory-job-{digest}",
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
        action_kind="propose_memory_signal",
        status="queued",
        display_label=_memory_job_display_label(command),
        agent_label=_MEMORY_AGENT_LABEL,
        created_at=observed_at,
        updated_at=observed_at,
        idempotency_key=f"memory-proposal-{digest}",
    )


def _memory_job_event(
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


async def _append_memory_job_event(
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


def _should_record_memory_job(command: NaturalMemoryCommand) -> bool:
    return command.decision.kind in {"profile_candidate", "clarify"}


async def _start_memory_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    command: NaturalMemoryCommand,
) -> tuple[AgentJob, str]:
    queued = await agent_job_repository.enqueue_job(_memory_job(command))
    await _append_memory_job_event(
        agent_job_repository=agent_job_repository,
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        event=_memory_job_event(
            job=queued,
            event_type="queued",
            message="Memory proposal queued.",
            observed_at=queued.created_at,
        ),
    )
    lease_owner = f"memory-tool-{_memory_job_digest(command)}"[:128]
    running_at = datetime.now(UTC)
    running = await agent_job_repository.lease_queued_job(
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        job_id=queued.job_id,
        lease_owner=lease_owner,
        lease_expires_at=running_at + timedelta(
            seconds=_MEMORY_JOB_LEASE_SECONDS
        ),
        observed_at=running_at,
    )
    await _append_memory_job_event(
        agent_job_repository=agent_job_repository,
        user_id=running.user_id,
        workspace_id=running.workspace_id,
        event=_memory_job_event(
            job=running,
            event_type="started",
            message="Memory proposal started.",
            observed_at=running_at,
        ),
    )
    return running, lease_owner


async def _complete_memory_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    job: AgentJob,
    lease_owner: str,
    result_refs: dict[str, str],
    message: str,
) -> None:
    observed_at = datetime.now(UTC)
    completed = await agent_job_repository.complete_job(
        user_id=job.user_id,
        workspace_id=job.workspace_id,
        job_id=job.job_id,
        lease_owner=lease_owner,
        observed_at=observed_at,
        result_refs=result_refs,
    )
    await _append_memory_job_event(
        agent_job_repository=agent_job_repository,
        user_id=completed.user_id,
        workspace_id=completed.workspace_id,
        event=_memory_job_event(
            job=completed,
            event_type="completed",
            message=message,
            observed_at=observed_at,
        ),
    )


async def _fail_memory_agent_job(
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
            summary="Memory proposal could not be created.",
            retryable=False,
        ),
    )
    await _append_memory_job_event(
        agent_job_repository=agent_job_repository,
        user_id=failed.user_id,
        workspace_id=failed.workspace_id,
        event=_memory_job_event(
            job=failed,
            event_type="failed",
            message="Memory proposal failed.",
            observed_at=observed_at,
        ),
    )


async def _try_start_memory_agent_job(
    *,
    agent_job_repository: AgentJobRepository | None,
    command: NaturalMemoryCommand,
) -> tuple[AgentJob | None, str | None]:
    if agent_job_repository is None or not _should_record_memory_job(command):
        return None, None
    try:
        return await _start_memory_agent_job(
            agent_job_repository=agent_job_repository,
            command=command,
        )
    except Exception:
        logger.exception(
            "Agent Col memory job lifecycle could not start for source message."
        )
        return None, None


async def _try_complete_memory_agent_job(
    *,
    agent_job_repository: AgentJobRepository | None,
    job: AgentJob | None,
    lease_owner: str | None,
    result_refs: dict[str, str],
    message: str,
) -> None:
    if agent_job_repository is None or job is None or lease_owner is None:
        return
    try:
        await _complete_memory_agent_job(
            agent_job_repository=agent_job_repository,
            job=job,
            lease_owner=lease_owner,
            result_refs=result_refs,
            message=message,
        )
    except Exception:
        logger.exception(
            "Agent Col memory job lifecycle could not complete for source message."
        )


async def _try_fail_memory_agent_job(
    *,
    agent_job_repository: AgentJobRepository | None,
    job: AgentJob | None,
    lease_owner: str | None,
    error_code: str,
) -> None:
    if agent_job_repository is None or job is None or lease_owner is None:
        return
    try:
        await _fail_memory_agent_job(
            agent_job_repository=agent_job_repository,
            job=job,
            lease_owner=lease_owner,
            error_code=error_code,
        )
    except Exception:
        logger.exception(
            "Agent Col memory job lifecycle could not fail for source message."
        )


def create_propose_memory_signal_tool(
    memory_service: TrustedMemoryService,
    *,
    agent_job_repository: AgentJobRepository | None = None,
) -> FunctionTool:
    """Create the governed pending-memory proposal tool."""

    async def propose_memory_signal(
        decision: ProviderNaturalMemoryDecision,
        tool_context: ToolContext,
        clarification_selection: MemoryClarificationSelection | None = None,
    ) -> dict[str, object]:
        """Create a pending user-reviewable proposal; never activate memory."""
        job: AgentJob | None = None
        lease_owner: str | None = None
        try:
            validated_decision = validate_provider_natural_memory_decision(
                decision
            )
            validated_selection = (
                None
                if clarification_selection is None
                else _CLARIFICATION_SELECTION_ADAPTER.validate_python(
                    clarification_selection
                )
            )
            command = _server_command(
                decision=validated_decision,
                clarification_selection=validated_selection,
                tool_context=tool_context,
            )
            job, lease_owner = await _try_start_memory_agent_job(
                agent_job_repository=agent_job_repository,
                command=command,
            )
            result = await memory_service.handle_natural_memory_decision(
                command
            )
        except ValueError:
            await _try_fail_memory_agent_job(
                agent_job_repository=agent_job_repository,
                job=job,
                lease_owner=lease_owner,
                error_code="invalid_memory_candidate",
            )
            return {
                "status": "rejected",
                "error_code": "invalid_memory_candidate",
            }
        except (
            MemoryProposalConflictError,
            MemoryProposalOriginConflictError,
        ):
            await _try_fail_memory_agent_job(
                agent_job_repository=agent_job_repository,
                job=job,
                lease_owner=lease_owner,
                error_code="memory_proposal_conflict",
            )
            return {
                "status": "rejected",
                "error_code": "memory_proposal_conflict",
            }
        except MemorySignalAlreadyActiveError:
            await _try_fail_memory_agent_job(
                agent_job_repository=agent_job_repository,
                job=job,
                lease_owner=lease_owner,
                error_code="memory_signal_already_active",
            )
            return {
                "status": "rejected",
                "error_code": "memory_signal_already_active",
            }
        except (ChatTurnOwnershipError, ChatTurnStateError):
            await _try_fail_memory_agent_job(
                agent_job_repository=agent_job_repository,
                job=job,
                lease_owner=lease_owner,
                error_code="memory_turn_conflict",
            )
            return {
                "status": "rejected",
                "error_code": "memory_turn_conflict",
            }
        if isinstance(result, NaturalMemoryProposalResult):
            await _try_complete_memory_agent_job(
                agent_job_repository=agent_job_repository,
                job=job,
                lease_owner=lease_owner,
                result_refs={"proposal_id": result.proposal.proposal_id},
                message="Memory proposal created.",
            )
            return {
                "status": "pending",
                "action": result.action.model_dump(mode="json"),
                "memory_proposal": result.proposal.model_dump(mode="json"),
            }
        if isinstance(result, NaturalMemoryClarificationResult):
            await _try_complete_memory_agent_job(
                agent_job_repository=agent_job_repository,
                job=job,
                lease_owner=lease_owner,
                result_refs={
                    "clarification_id": result.clarification.clarification_id
                },
                message="Memory clarification created.",
            )
            return {
                "status": "clarification_required",
                "memory_clarification": result.clarification.model_dump(
                    mode="json"
                ),
            }
        if isinstance(result, NaturalMemoryNoEffectResult):
            return {"status": result.status}
        raise MemoryProposalToolResponseError(
            "Memory proposal service result is invalid."
        )

    return FunctionTool(propose_memory_signal)
