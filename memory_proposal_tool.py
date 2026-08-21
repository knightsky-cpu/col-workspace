import re
from collections.abc import Mapping
from typing import Literal, Self

from google.adk.tools import FunctionTool, ToolContext
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from memory_proposals import ProposalTurnLease
from memory_policy import BroadRole, MemoryCategory
from schemas import AgentActionReceipt, MemoryProposalReceipt
from trusted_memory_service import (
    ProposeMemorySignalCommand,
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
    memory_proposal: MemoryProposalReceipt

    @model_validator(mode="after")
    def require_proposal_action(self) -> Self:
        if self.action.action_name != "propose_memory_signal":
            raise ValueError("Pending response has the wrong action.")
        return self


class RejectedMemoryProposalToolResponse(_StrictToolResponse):
    status: Literal["rejected"]
    error_code: Literal["invalid_memory_candidate"]


MemoryProposalToolResponse = (
    PendingMemoryProposalToolResponse | RejectedMemoryProposalToolResponse
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
        if value.get("status") == "rejected":
            return RejectedMemoryProposalToolResponse.model_validate(value)
        raise ValueError("Response status is invalid.")
    except (TypeError, ValueError, ValidationError) as exc:
        raise MemoryProposalToolResponseError(
            "Memory proposal tool response is invalid."
        ) from exc


def _server_command(
    *,
    category: MemoryCategory,
    proposed_value: str | list[BroadRole],
    tool_context: ToolContext,
) -> ProposeMemorySignalCommand:
    state = getattr(tool_context, "state", None)
    if not isinstance(state, Mapping):
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        )
    try:
        user_id = state["memory_user_id"]
        session_id = state["memory_session_id"]
        source_message_id = state["memory_source_message_id"]
        source_message_text = state["memory_source_message_text"]
        memory_decision_present = state["memory_decision_present"]
    except KeyError as exc:
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        ) from exc
    if any(
        not isinstance(value, str)
        or _IDENTIFIER_PATTERN.fullmatch(value) is None
        for value in (user_id, session_id, source_message_id)
    ):
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
        )
    if (
        not isinstance(source_message_text, str)
        or not source_message_text.strip()
        or type(memory_decision_present) is not bool
    ):
        raise MemoryProposalToolConfigurationError(
            "Memory proposal tool context is invalid."
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
    return ProposeMemorySignalCommand(
        user_id=user_id,
        session_id=session_id,
        source_message_id=source_message_id,
        source_message_text=source_message_text,
        memory_decision_present=memory_decision_present,
        category=category,
        proposed_value=proposed_value,
        turn_lease=turn_lease,
    )


def create_propose_memory_signal_tool(
    memory_service: TrustedMemoryService,
) -> FunctionTool:
    """Create the governed pending-memory proposal tool."""

    async def propose_memory_signal(
        category: MemoryCategory,
        proposed_value: str | list[BroadRole],
        tool_context: ToolContext,
    ) -> dict[str, object]:
        """Create a pending user-reviewable proposal; never activate memory."""
        command = _server_command(
            category=category,
            proposed_value=proposed_value,
            tool_context=tool_context,
        )
        try:
            result = await memory_service.propose_memory_signal(command)
        except ValueError:
            return {
                "status": "rejected",
                "error_code": "invalid_memory_candidate",
            }
        return {
            "status": "pending",
            "action": result.action.model_dump(mode="json"),
            "memory_proposal": result.proposal.model_dump(mode="json"),
        }

    return FunctionTool(propose_memory_signal)
