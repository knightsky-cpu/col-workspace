"""Deterministic chat-owned artifact feedback execution boundary."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from artifact_feedback_service import (
    RecordBlueprintFeedbackCommand,
    ResolvedArtifactFeedback,
)
from chat_turns import ChatTurnClaim
from database import ChatTurnFeedbackEffectResult
from schemas import (
    AgentActionReceipt,
    ArtifactFeedbackDecision,
    ArtifactFeedbackReference,
    ArtifactFeedbackTargetKind,
    ArtifactReference,
    IdentifierStr,
)


_CONTEXT_START = "[SERVER_VALIDATED_ARTIFACT_FEEDBACK_RESULT]"
_CONTEXT_END = "[/SERVER_VALIDATED_ARTIFACT_FEEDBACK_RESULT]"


class FeedbackResolver(Protocol):
    async def resolve_feedback_target(
        self,
        command: RecordBlueprintFeedbackCommand,
    ) -> ResolvedArtifactFeedback: ...


class FeedbackEffectLedger(Protocol):
    async def record_chat_turn_artifact_feedback_effect(
        self,
        claim: ChatTurnClaim,
        *,
        target_kind: ArtifactFeedbackTargetKind,
        observed_at: datetime,
    ) -> ChatTurnFeedbackEffectResult: ...


class AgentColArtifactFeedbackExecutorConfigurationError(RuntimeError):
    """Raised when feedback execution receives inconsistent authority."""


class AgentColArtifactFeedbackResponderProjection(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    operation: Literal["record_blueprint_feedback"] = (
        "record_blueprint_feedback"
    )
    artifact: ArtifactReference
    feedback: ArtifactFeedbackReference
    target_kind: ArtifactFeedbackTargetKind
    target_label: str = Field(min_length=1, max_length=200)
    decision: ArtifactFeedbackDecision
    feedback_text: str = Field(min_length=1, max_length=1_500)
    correction_text: str | None = Field(default=None, max_length=1_500)
    supersedes_feedback_id: IdentifierStr | None = None


@dataclass(frozen=True, slots=True)
class AgentColArtifactFeedbackExecutionCommand:
    claim: ChatTurnClaim
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class AgentColArtifactFeedbackExecutionResult:
    claim: ChatTurnClaim
    actions: tuple[AgentActionReceipt, ...]
    artifact_feedback: tuple[ArtifactFeedbackReference, ...]
    projection: AgentColArtifactFeedbackResponderProjection


class AgentColArtifactFeedbackExecutor:
    def __init__(
        self,
        *,
        feedback_resolver: FeedbackResolver,
        feedback_ledger: FeedbackEffectLedger,
    ) -> None:
        self._feedback_resolver = feedback_resolver
        self._feedback_ledger = feedback_ledger

    async def execute(
        self,
        command: AgentColArtifactFeedbackExecutionCommand,
    ) -> AgentColArtifactFeedbackExecutionResult:
        self._validate_command(command)
        claim = command.claim
        request = claim.request.artifact_feedback_decision
        if request is None:
            raise AgentColArtifactFeedbackExecutorConfigurationError(
                "Artifact feedback decision is unavailable."
            )
        resolved = await self._feedback_resolver.resolve_feedback_target(
            RecordBlueprintFeedbackCommand(
                project_id=claim.request.project_id,
                session_id=claim.request.session_id,
                user_id=claim.request.user_id,
                source_message_id=claim.ids.user_message_id,
                turn_id=claim.ids.turn_id,
                feedback=request,
                observed_at=command.observed_at,
            )
        )
        effect = (
            await self._feedback_ledger.record_chat_turn_artifact_feedback_effect(
                claim,
                target_kind=resolved.target.target_kind,
                observed_at=command.observed_at,
            )
        )
        if (
            effect.action.action_name != "record_blueprint_feedback"
            or effect.claim.precompleted_actions != (effect.action,)
            or effect.claim.precompleted_artifact_feedback
            != (effect.feedback,)
            or effect.feedback.feedback_id != resolved.feedback_id
            or effect.feedback.artifact_id != resolved.artifact.artifact_id
            or effect.feedback.target_id != resolved.target.target_id
            or effect.feedback.target_kind != resolved.target.target_kind
            or effect.feedback.decision != request.decision
            or effect.feedback.schema_version
            != request.expected_schema_version
        ):
            raise AgentColArtifactFeedbackExecutorConfigurationError(
                "Artifact feedback effect receipts are inconsistent."
            )
        projection = AgentColArtifactFeedbackResponderProjection(
            artifact=resolved.artifact,
            feedback=effect.feedback,
            target_kind=resolved.target.target_kind,
            target_label=resolved.target.display_label,
            decision=request.decision,
            feedback_text=request.feedback_text,
            correction_text=request.correction_text,
            supersedes_feedback_id=request.supersedes_feedback_id,
        )
        return AgentColArtifactFeedbackExecutionResult(
            claim=effect.claim,
            actions=(effect.action,),
            artifact_feedback=(effect.feedback,),
            projection=projection,
        )

    @staticmethod
    def _validate_command(
        command: AgentColArtifactFeedbackExecutionCommand,
    ) -> None:
        if not isinstance(command, AgentColArtifactFeedbackExecutionCommand):
            raise AgentColArtifactFeedbackExecutorConfigurationError(
                "Artifact feedback execution command is invalid."
            )
        claim = command.claim
        if (
            not isinstance(claim, ChatTurnClaim)
            or claim.request.artifact_feedback_decision is None
            or claim.request.memory_decision is not None
            or claim.precompleted_memory_proposals
            or claim.precompleted_artifacts
            or command.observed_at.tzinfo is None
            or command.observed_at.utcoffset() is None
        ):
            raise AgentColArtifactFeedbackExecutorConfigurationError(
                "Artifact feedback execution command is invalid."
            )


def build_agent_col_artifact_feedback_model_context(
    projection: AgentColArtifactFeedbackResponderProjection,
) -> types.Content:
    """Render bounded server-validated feedback responder context."""
    payload = json.dumps(
        projection.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    text = (
        "The application already validated and persisted this artifact "
        "feedback. Do not reroute, call an expert, mutate memory, or claim "
        "that a global preference was learned. Acknowledge only the bounded "
        "validated result below.\n"
        f"{_CONTEXT_START}\n{payload}\n{_CONTEXT_END}"
    )
    return types.Content(
        role="user",
        parts=[types.Part.from_text(text=text)],
    )
