import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal, Self

from google.adk.tools import FunctionTool, ToolContext
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

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
from schemas import AgentActionReceipt, CollaborativeNoteProposal


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_PRECOMPLETED_DURABLE_EFFECT_STATE_KEY = (
    "governed_turn_has_precompleted_durable_effect"
)


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


CollaborativeNoteToolResponse = (
    PendingCollaborativeNoteToolResponse
    | NoEffectCollaborativeNoteToolResponse
    | RejectedCollaborativeNoteToolResponse
)


def parse_collaborative_note_tool_response(
    value: object,
) -> CollaborativeNoteToolResponse:
    try:
        if not isinstance(value, Mapping):
            raise ValueError("Response must be a mapping.")
        if value.get("status") == "pending":
            return PendingCollaborativeNoteToolResponse.model_validate(value)
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


def create_propose_collaborative_note_tool(
    note_service: CollaborativeNoteService,
) -> FunctionTool:
    async def propose_collaborative_note(
        decision: NaturalCollaborativeNoteDecision,
        tool_context: ToolContext,
    ) -> dict[str, object]:
        """Create a pending workspace-note proposal; never activate a note."""
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
            return {
                "status": "rejected",
                "error_code": "collaborative_note_proposal_conflict",
            }
        except (ChatTurnOwnershipError, ChatTurnStateError):
            return {
                "status": "rejected",
                "error_code": "collaborative_note_turn_conflict",
            }
        if isinstance(result, CollaborativeNoteProposalResult):
            if result.action is None:
                raise CollaborativeNoteToolResponseError(
                    "Collaborative note proposal action is missing."
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
