import hashlib
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Self

from google.adk.tools import FunctionTool, ToolContext
from pydantic import (
    BaseModel,
    ConfigDict,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from agent_col_agent_jobs import AgentJob, AgentJobEvent
from agent_job_repository import (
    AgentJobConflictError,
    AgentJobRepository,
    AgentJobRepositoryError,
    AgentJobStateError,
)
from chat_turns import ChatTurnOwnershipError, ChatTurnStateError
from database import (
    MemoryProposalConflictError,
    MemoryProposalOriginConflictError,
    MemorySignalAlreadyActiveError,
)
from memory_candidate_decisions import (
    NaturalMemoryDecision,
    validate_provider_natural_memory_decision,
)
from memory_clarifications import (
    MemoryClarificationReceipt,
    MemoryClarificationSelection,
)
from memory_proposals import ProposalTurnLease
from memory_proposal_job_worker import memory_clarification_selection_job_payload
from memory_proposal_job_worker import memory_job_payload
from memory_proposal_job_worker import (
    preference_hypothesis_confirmation_job_payload,
)
from memory_proposal_job_worker import raw_memory_job_payload
from preference_learning import (
    PreferenceHypothesis,
    preference_hypothesis_confirmation_digest,
)
from schemas import (
    AgentActionReceipt,
    MemoryProposalReceiptV2,
    QueuedActionReceipt,
)
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
logger = logging.getLogger(__name__)


class MemoryProposalToolConfigurationError(RuntimeError):
    """Raised when server-owned tool context is absent or malformed."""


class MemoryProposalToolResponseError(RuntimeError):
    """Raised when an ADK proposal-tool response violates its contract."""


@dataclass(frozen=True)
class _MemoryToolServerContext:
    user_id: str
    workspace_id: str
    session_id: str
    source_message_id: str
    source_message_text: str
    memory_decision_present: bool
    memory_prequeued_for_turn: bool
    turn_lease: ProposalTurnLease | None


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
        "memory_clarification_unavailable",
        "memory_proposal_conflict",
        "memory_signal_already_active",
        "memory_job_unavailable",
        "memory_turn_conflict",
    ]


class ClarificationMemoryProposalToolResponse(_StrictToolResponse):
    status: Literal["clarification_required"]
    memory_clarification: MemoryClarificationReceipt


class QueuedMemoryProposalToolResponse(_StrictToolResponse):
    status: Literal["queued"]
    queued_action: QueuedActionReceipt

    @model_validator(mode="after")
    def require_memory_queued_action(self) -> Self:
        if self.queued_action.action_kind != "propose_memory_signal":
            raise ValueError("Queued response has the wrong action kind.")
        return self


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
    | QueuedMemoryProposalToolResponse
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
        if value.get("status") == "queued":
            return QueuedMemoryProposalToolResponse.model_validate(value)
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


def _server_context(tool_context: ToolContext) -> _MemoryToolServerContext:
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
    memory_prequeued_for_turn = state.get("memory_prequeued_for_turn", False)
    if type(memory_prequeued_for_turn) is not bool:
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        )
    if artifact_feedback_decision_present:
        raise ValueError(
            "Artifact feedback turns cannot create memory proposals."
        )
    return _MemoryToolServerContext(
        user_id=user_id,
        workspace_id=workspace_id,
        session_id=session_id,
        source_message_id=source_message_id,
        source_message_text=source_message_text,
        memory_decision_present=memory_decision_present,
        memory_prequeued_for_turn=memory_prequeued_for_turn,
        turn_lease=None,
    )


def _server_command(
    *,
    decision: NaturalMemoryDecision,
    clarification_selection: MemoryClarificationSelection | None,
    tool_context: ToolContext,
) -> NaturalMemoryCommand:
    context = _server_context(tool_context)
    return NaturalMemoryCommand(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
        session_id=context.session_id,
        source_message_id=context.source_message_id,
        source_message_text=context.source_message_text,
        memory_decision_present=context.memory_decision_present,
        decision=decision,
        clarification_selection=clarification_selection,
        turn_lease=context.turn_lease,
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
        return f"Memory request: {category}"[:160]
    if command.decision.kind == "clarify":
        return "Memory clarification"[:160]
    return "Memory request"[:160]


def _raw_memory_job_digest(
    *,
    context: _MemoryToolServerContext,
    decision: dict[str, object],
    clarification_selection: dict[str, object] | None,
) -> str:
    material = json_dumps_compact(
        {
            "user_id": context.user_id,
            "workspace_id": context.workspace_id,
            "session_id": context.session_id,
            "source_message_id": context.source_message_id,
            "turn_id": (
                context.turn_lease.turn_id
                if context.turn_lease is not None
                else ""
            ),
            "decision": decision,
            "clarification_selection": clarification_selection,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _raw_memory_job_display_label(decision: dict[str, object]) -> str:
    category = decision.get("category")
    if isinstance(category, str) and category:
        return f"Memory request: {category}"[:160]
    if decision.get("kind") == "clarify":
        return "Memory clarification"[:160]
    return "Memory request"[:160]


def _clarification_selection_job_digest(
    *,
    context: _MemoryToolServerContext,
    clarification_id: str,
    selected_candidate_index: int,
) -> str:
    material = json_dumps_compact(
        {
            "user_id": context.user_id,
            "workspace_id": context.workspace_id,
            "session_id": context.session_id,
            "source_message_id": context.source_message_id,
            "clarification_id": clarification_id,
            "selected_candidate_index": selected_candidate_index,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _clarification_selection_job(
    *,
    context: _MemoryToolServerContext,
    clarification_id: str,
    selected_candidate_index: int,
) -> AgentJob:
    digest = _clarification_selection_job_digest(
        context=context,
        clarification_id=clarification_id,
        selected_candidate_index=selected_candidate_index,
    )
    observed_at = datetime.now(UTC)
    return AgentJob(
        job_id=f"memory-selection-job-{digest}",
        user_id=context.user_id,
        project_id=context.workspace_id,
        workspace_id=context.workspace_id,
        session_id=context.session_id,
        source_turn_id=context.source_message_id,
        source_message_id=context.source_message_id,
        action_kind="propose_memory_signal",
        status="queued",
        display_label="Memory clarification selection",
        agent_label=_MEMORY_AGENT_LABEL,
        created_at=observed_at,
        updated_at=observed_at,
        idempotency_key=f"memory-clarification-selection-{digest}",
    )


def _raw_memory_job(
    *,
    context: _MemoryToolServerContext,
    decision: dict[str, object],
    clarification_selection: dict[str, object] | None,
) -> AgentJob:
    digest = _raw_memory_job_digest(
        context=context,
        decision=decision,
        clarification_selection=clarification_selection,
    )
    observed_at = datetime.now(UTC)
    return AgentJob(
        job_id=f"memory-job-{digest}",
        user_id=context.user_id,
        project_id=context.workspace_id,
        workspace_id=context.workspace_id,
        session_id=context.session_id,
        source_turn_id=(
            context.turn_lease.turn_id
            if context.turn_lease
            else context.source_message_id
        ),
        source_message_id=context.source_message_id,
        action_kind="propose_memory_signal",
        status="queued",
        display_label=_raw_memory_job_display_label(decision),
        agent_label=_MEMORY_AGENT_LABEL,
        created_at=observed_at,
        updated_at=observed_at,
        idempotency_key=f"memory-proposal-{digest}",
    )


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


def _preference_hypothesis_confirmation_job(
    *,
    user_id: str,
    workspace_id: str,
    session_id: str,
    source_message_id: str,
    hypothesis: PreferenceHypothesis,
) -> AgentJob:
    if hypothesis.user_id != user_id or hypothesis.project_id != workspace_id:
        raise ValueError("Preference hypothesis scope does not match.")
    digest = preference_hypothesis_confirmation_digest(
        user_id=user_id,
        project_id=workspace_id,
        session_id=session_id,
        source_message_id=source_message_id,
        hypothesis=hypothesis,
    )
    observed_at = hypothesis.last_observed_at
    return AgentJob(
        job_id=f"memory-preference-confirmation-job-{digest}",
        user_id=user_id,
        project_id=workspace_id,
        workspace_id=workspace_id,
        session_id=session_id,
        source_turn_id=source_message_id,
        source_message_id=source_message_id,
        action_kind="propose_memory_signal",
        status="queued",
        display_label="Memory preference confirmation",
        agent_label=_MEMORY_AGENT_LABEL,
        created_at=observed_at,
        updated_at=observed_at,
        idempotency_key=f"memory-preference-confirmation-{digest}",
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
    return command.decision.kind == "profile_candidate"


async def _queue_memory_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    command: NaturalMemoryCommand,
) -> AgentJob:
    job = _memory_job(command)
    queued = await agent_job_repository.enqueue_job_with_payload(
        job,
        memory_job_payload(command, job),
    )
    await _append_memory_job_event(
        agent_job_repository=agent_job_repository,
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        event=_memory_job_event(
            job=queued,
            event_type="queued",
            message="Memory request queued.",
            observed_at=queued.created_at,
        ),
    )
    return queued


async def _try_queue_memory_agent_job(
    *,
    agent_job_repository: AgentJobRepository | None,
    command: NaturalMemoryCommand,
) -> AgentJob | None:
    if agent_job_repository is None or not _should_record_memory_job(command):
        return None
    return await _queue_memory_agent_job(
        agent_job_repository=agent_job_repository,
        command=command,
    )


async def queue_memory_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    command: NaturalMemoryCommand,
) -> QueuedActionReceipt:
    """Queue one governed memory proposal job for background execution."""
    job = await _queue_memory_agent_job(
        agent_job_repository=agent_job_repository,
        command=command,
    )
    return job.to_queued_action_receipt()


async def queue_preference_hypothesis_confirmation_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    user_id: str,
    workspace_id: str,
    session_id: str,
    source_message_id: str,
    hypothesis: PreferenceHypothesis,
) -> QueuedActionReceipt:
    """Queue one Memory-owned preference confirmation."""
    job = _preference_hypothesis_confirmation_job(
        user_id=user_id,
        workspace_id=workspace_id,
        session_id=session_id,
        source_message_id=source_message_id,
        hypothesis=hypothesis,
    )
    queued = await agent_job_repository.enqueue_job_with_payload(
        job,
        preference_hypothesis_confirmation_job_payload(
            job=job,
            hypothesis=hypothesis,
        ),
    )
    await _append_memory_job_event(
        agent_job_repository=agent_job_repository,
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        event=_memory_job_event(
            job=queued,
            event_type="queued",
            message="Memory preference confirmation queued.",
            observed_at=queued.created_at,
        ),
    )
    return queued.to_queued_action_receipt()


def _raw_tool_mapping(value: object) -> dict[str, object]:
    if isinstance(value, BaseModel):
        raw = value.model_dump(mode="python")
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise ValueError("Memory decision must be an object.")
    return raw


def _raw_optional_mapping(value: object | None) -> dict[str, object] | None:
    if value is None:
        return None
    return _raw_tool_mapping(value)


def _should_queue_raw_memory_job(decision: dict[str, object]) -> bool:
    return decision.get("kind") == "profile_candidate"


async def _queue_raw_memory_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    context: _MemoryToolServerContext,
    decision: dict[str, object],
    clarification_selection: dict[str, object] | None,
) -> AgentJob:
    job = _raw_memory_job(
        context=context,
        decision=decision,
        clarification_selection=clarification_selection,
    )
    queued = await agent_job_repository.enqueue_job_with_payload(
        job,
        raw_memory_job_payload(
            job=job,
            decision=decision,
            clarification_selection=clarification_selection,
            source_message_text=context.source_message_text,
            memory_decision_present=context.memory_decision_present,
        ),
    )
    await _append_memory_job_event(
        agent_job_repository=agent_job_repository,
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        event=_memory_job_event(
            job=queued,
            event_type="queued",
            message="Memory request queued.",
            observed_at=queued.created_at,
        ),
    )
    return queued


async def _queue_clarification_selection_agent_job(
    *,
    agent_job_repository: AgentJobRepository,
    context: _MemoryToolServerContext,
    clarification_id: str,
    selected_candidate_index: int,
) -> AgentJob:
    job = _clarification_selection_job(
        context=context,
        clarification_id=clarification_id,
        selected_candidate_index=selected_candidate_index,
    )
    queued = await agent_job_repository.enqueue_job_with_payload(
        job,
        memory_clarification_selection_job_payload(
            job=job,
            clarification_id=clarification_id,
            selected_candidate_index=selected_candidate_index,
        ),
    )
    await _append_memory_job_event(
        agent_job_repository=agent_job_repository,
        user_id=queued.user_id,
        workspace_id=queued.workspace_id,
        event=_memory_job_event(
            job=queued,
            event_type="queued",
            message="Memory clarification selection queued.",
            observed_at=queued.created_at,
        ),
    )
    return queued


def _active_memory_clarification_id(tool_context: ToolContext) -> str | None:
    state = getattr(tool_context, "state", None)
    if not callable(getattr(state, "get", None)):
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        )
    value = state.get("active_memory_clarification_id")
    if value is None:
        return None
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        )
    return value


def create_select_memory_clarification_tool(
    memory_service: TrustedMemoryService,
    *,
    agent_job_repository: AgentJobRepository | None = None,
    memory_job_dispatcher: Callable[[AgentJob], None] | None = None,
) -> FunctionTool:
    """Create a tool that queues Memory-owned clarification selection."""

    async def select_memory_clarification_candidate(
        selected_candidate_index: int,
        tool_context: ToolContext,
    ) -> dict[str, object]:
        """Queue selection of a server-validated active clarification."""
        try:
            context = _server_context(tool_context)
            clarification_id = _active_memory_clarification_id(tool_context)
            if clarification_id is None or agent_job_repository is None:
                return {
                    "status": "rejected",
                    "error_code": "memory_clarification_unavailable",
                }
            if (
                type(selected_candidate_index) is not int
                or not 0 <= selected_candidate_index <= 4
            ):
                return {
                    "status": "rejected",
                    "error_code": "invalid_memory_candidate",
                }
            queued_job = await _queue_clarification_selection_agent_job(
                agent_job_repository=agent_job_repository,
                context=context,
                clarification_id=clarification_id,
                selected_candidate_index=selected_candidate_index,
            )
            if memory_job_dispatcher is not None:
                memory_job_dispatcher(queued_job)
            return {
                "status": "queued",
                "queued_action": queued_job.to_queued_action_receipt().model_dump(
                    mode="json"
                ),
            }
        except AgentJobConflictError:
            logger.exception(
                "Agent Col memory clarification job queue conflicted."
            )
            return {
                "status": "rejected",
                "error_code": "memory_proposal_conflict",
            }
        except (AgentJobRepositoryError, AgentJobStateError):
            logger.exception("Agent Col memory clarification job queue failed.")
            return {
                "status": "rejected",
                "error_code": "memory_job_unavailable",
            }

    return FunctionTool(select_memory_clarification_candidate)


def create_propose_memory_signal_tool(
    memory_service: TrustedMemoryService,
    *,
    agent_job_repository: AgentJobRepository | None = None,
    memory_job_dispatcher: Callable[[AgentJob], None] | None = None,
) -> FunctionTool:
    """Create the governed pending-memory proposal tool."""

    async def propose_memory_signal(
        decision: dict[str, object],
        tool_context: ToolContext,
    ) -> dict[str, object]:
        """Create a pending user-reviewable proposal; never activate memory."""
        try:
            raw_decision = _raw_tool_mapping(decision)
            raw_selection = None
            context = _server_context(tool_context)
            if context.memory_prequeued_for_turn:
                return {"status": "no_memory"}
            if (
                agent_job_repository is not None
                and _should_queue_raw_memory_job(raw_decision)
            ):
                queued_job = await _queue_raw_memory_agent_job(
                    agent_job_repository=agent_job_repository,
                    context=context,
                    decision=raw_decision,
                    clarification_selection=raw_selection,
                )
                if memory_job_dispatcher is not None:
                    memory_job_dispatcher(queued_job)
                return {
                    "status": "queued",
                    "queued_action": (
                        queued_job.to_queued_action_receipt().model_dump(
                            mode="json"
                        )
                    ),
                }
            validated_decision = validate_provider_natural_memory_decision(
                raw_decision
            )
            validated_selection = (
                None
                if raw_selection is None
                else _CLARIFICATION_SELECTION_ADAPTER.validate_python(
                    raw_selection
                )
            )
            command = _server_command(
                decision=validated_decision,
                clarification_selection=validated_selection,
                tool_context=tool_context,
            )
            queued_job = await _try_queue_memory_agent_job(
                agent_job_repository=agent_job_repository,
                command=command,
            )
            if queued_job is not None:
                if memory_job_dispatcher is not None:
                    memory_job_dispatcher(queued_job)
                return {
                    "status": "queued",
                    "queued_action": (
                        queued_job.to_queued_action_receipt().model_dump(
                            mode="json"
                        )
                    ),
                }
            result = await memory_service.handle_natural_memory_decision(
                command
            )
        except AgentJobConflictError:
            logger.exception(
                "Agent Col memory job queue conflicted for source message."
            )
            return {
                "status": "rejected",
                "error_code": "memory_proposal_conflict",
            }
        except (AgentJobRepositoryError, AgentJobStateError):
            logger.exception(
                "Agent Col memory job queue failed for source message."
            )
            return {
                "status": "rejected",
                "error_code": "memory_job_unavailable",
            }
        except ValueError:
            return {
                "status": "rejected",
                "error_code": "invalid_memory_candidate",
            }
        except (
            MemoryProposalConflictError,
            MemoryProposalOriginConflictError,
        ):
            return {
                "status": "rejected",
                "error_code": "memory_proposal_conflict",
            }
        except MemorySignalAlreadyActiveError:
            return {
                "status": "rejected",
                "error_code": "memory_signal_already_active",
            }
        except (ChatTurnOwnershipError, ChatTurnStateError):
            return {
                "status": "rejected",
                "error_code": "memory_turn_conflict",
            }
        if isinstance(result, NaturalMemoryProposalResult):
            return {
                "status": "pending",
                "action": result.action.model_dump(mode="json"),
                "memory_proposal": result.proposal.model_dump(mode="json"),
            }
        if isinstance(result, NaturalMemoryClarificationResult):
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
