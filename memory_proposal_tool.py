import re
from collections.abc import Mapping
from typing import Literal, Self

from google.adk.tools import FunctionTool, ToolContext
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from memory_candidate_decisions import NaturalMemoryDecision
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
    error_code: Literal["invalid_memory_candidate"]


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


def create_propose_memory_signal_tool(
    memory_service: TrustedMemoryService,
) -> FunctionTool:
    """Create the governed pending-memory proposal tool."""

    async def propose_memory_signal(
        decision: NaturalMemoryDecision,
        tool_context: ToolContext,
        clarification_selection: MemoryClarificationSelection | None = None,
    ) -> dict[str, object]:
        """Create a pending user-reviewable proposal; never activate memory."""
        try:
            command = _server_command(
                decision=decision,
                clarification_selection=clarification_selection,
                tool_context=tool_context,
            )
            result = await memory_service.handle_natural_memory_decision(
                command
            )
        except ValueError:
            return {
                "status": "rejected",
                "error_code": "invalid_memory_candidate",
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
