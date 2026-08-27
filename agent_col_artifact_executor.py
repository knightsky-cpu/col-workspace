"""Deterministic synchronous artifact execution for routed Agent_Col turns."""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from agent_col_routing_v4 import AgentColRoute, AgentColRoutingDirective
from artifact_read_service import GetBlueprintArtifactCommand
from chat_turns import ChatTurnClaim
from database import ChatTurnArtifactEffectResult
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


class ArtifactSynthesisService(Protocol):
    async def generate_governed_blueprint(
        self,
        command: SynthesisCommand,
    ) -> GovernedSynthesisGenerationResult: ...


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


@dataclass(frozen=True, slots=True)
class AgentColArtifactExecutionResult:
    claim: ChatTurnClaim
    actions: tuple[AgentActionReceipt, ...]
    artifacts: tuple[ArtifactReference, ...]
    adaptations: tuple[VersionedAdaptationReceipt, ...]
    projection: AgentColArtifactResponderProjection


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
    ) -> None:
        self._synthesis_service = synthesis_service
        self._artifact_ledger = artifact_ledger
        self._artifact_reader = artifact_reader
        self._generic_artifact_generator = generic_artifact_generator
        self._generic_artifact_reader = generic_artifact_reader
        self._genai_client = genai_client

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

    async def _execute_blueprint(
        self,
        command: AgentColArtifactExecutionCommand,
    ) -> AgentColArtifactExecutionResult:
        claim = command.claim
        artifact = self._precompleted_artifact(
            claim,
            expected_action_name="synthesize_project",
        )
        if artifact is None:
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

        if artifact.artifact_type != "synthesis_blueprint":
            raise AgentColArtifactExecutorConfigurationError(
                "Precompleted artifact effects are inconsistent."
            )
        detail = await self._artifact_reader.get_blueprint(
            GetBlueprintArtifactCommand(
                project_id=claim.request.project_id,
                blueprint_id=artifact.artifact_id,
            )
        )
        self._validate_canonical_detail(claim, artifact, detail)
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
        if artifact is None:
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
        if artifact.artifact_type != "single_file_artifact":
            raise AgentColArtifactExecutorConfigurationError(
                "Precompleted artifact effects are inconsistent."
            )
        detail = await self._generic_artifact_reader.get_artifact(
            GetGenericArtifactCommand(
                project_id=claim.request.project_id,
                artifact_id=artifact.artifact_id,
            )
        )
        self._validate_single_file_canonical_detail(claim, artifact, detail)
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
