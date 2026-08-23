import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import time
from typing import Protocol, TypeVar

from google import genai
from google.genai import types

from agent_col_expert_executor_v3 import (
    AgentColExpertExecutorV3ConfigurationError,
)
from agent_col_artifact_executor import (
    AgentColArtifactExecutionCommand,
    AgentColArtifactExecutionResult,
    AgentColArtifactExecutorConfigurationError,
    build_agent_col_artifact_model_context,
)
from agent_col_numeric_projection import project_routing_numeric_candidates
from agent_col_responder_context_v3 import (
    AgentColResponderContextV3,
    build_agent_col_responder_v3_model_context,
)
from agent_col_routing import project_routing_url_candidates
from agent_col_routing_v3 import (
    AgentColRoute,
    AgentColRoutingDirective,
    AgentColRoutingInput,
    RoutingDirectiveInputError,
)
from agent_col_routing_provider_v3 import (
    AgentColRoutingV3ProviderError,
    AgentColRoutingV3ProviderTimeoutError,
    request_agent_col_routing_v3_directive,
)
from agent_col_routing_provider_v4 import (
    AgentColRoutingV4ProviderError,
    AgentColRoutingV4ProviderTimeoutError,
    request_agent_col_routing_v4_directive,
)
from agent_col_routing_v4 import (
    AgentColRoute as AgentColRouteV4,
    AgentColRoutingDirective as AgentColRoutingDirectiveV4,
    AgentColRoutingInput as AgentColRoutingInputV4,
    RoutingDirectiveInputError as RoutingDirectiveInputErrorV4,
)
from agent_col_text_projection import project_routing_text_blocks
from chat_turns import ChatTurnClaim
from computational_expert import ComputationResponderResult
from expert_contracts import ExpertCapability, ExpertStatus
from memory_proposals import ProposalTurnLease
from research_expert import ResearchExpertResult
from requirements_verification import RequirementsVerificationResult
from schemas import (
    AdaptationReceipt,
    AgentActionReceipt,
    ArtifactReference,
    CitationReference,
    MemoryProposalReceipt,
)
from source_expert import SourceExpertResult
from supervisor_runtime import (
    SupervisorRuntimeError,
    SupervisorTimeoutError,
    SupervisorTurnContext,
    SupervisorTurnResult,
)


TURN_ROUTING_TIMEOUT_SECONDS = 15.0
TURN_TIMEOUT_SECONDS = 90.0
TURN_EXPERT_BUDGET_SECONDS = 45.0
TURN_RESPONDER_RESERVE_SECONDS = 20.0
logger = logging.getLogger(__name__)
ReceiptT = TypeVar("ReceiptT")


class RoutingRequest(Protocol):
    async def __call__(
        self,
        client: genai.Client,
        routing_input: AgentColRoutingInput,
        *,
        timeout_seconds: float,
    ) -> AgentColRoutingDirective: ...


class ArtifactRoutingRequest(Protocol):
    async def __call__(
        self,
        client: genai.Client,
        routing_input: AgentColRoutingInputV4,
        *,
        timeout_seconds: float,
    ) -> AgentColRoutingDirectiveV4: ...


class ArtifactExecutor(Protocol):
    async def execute(
        self,
        command: AgentColArtifactExecutionCommand,
    ) -> AgentColArtifactExecutionResult: ...


class ExpertExecutor(Protocol):
    @property
    def available_capabilities(self) -> tuple[ExpertCapability, ...]: ...

    async def execute(
        self,
        directive: AgentColRoutingDirective,
        routing_input: AgentColRoutingInput,
    ) -> AgentColResponderContextV3: ...


class ResponderRuntime(Protocol):
    async def run_turn(
        self,
        context: SupervisorTurnContext,
    ) -> SupervisorTurnResult: ...


@dataclass(frozen=True, slots=True)
class AgentColTurnCommand:
    project_id: str
    session_id: str
    user_id: str
    message: str
    recent_user_messages: tuple[str, ...] = ()
    model_input_context: tuple[types.Content, ...] = ()
    source_message_id: str | None = None
    memory_decision_present: bool = False
    turn_lease: ProposalTurnLease | None = None
    precompleted_actions: tuple[AgentActionReceipt, ...] = ()
    precompleted_memory_proposals: tuple[MemoryProposalReceipt, ...] = ()
    chat_turn_claim: ChatTurnClaim | None = None


@dataclass(frozen=True, slots=True)
class AgentColTurnResult:
    response: str
    actions: tuple[AgentActionReceipt, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    citations: tuple[CitationReference, ...] = ()
    memory_proposals: tuple[MemoryProposalReceipt, ...] = ()
    adaptations: tuple[AdaptationReceipt, ...] = ()
    chat_turn_claim: ChatTurnClaim | None = None


class AgentColTurnServiceError(RuntimeError):
    """Raised when cognitive turn orchestration cannot complete safely."""

    def __init__(
        self,
        message: str,
        *,
        actions: tuple[AgentActionReceipt, ...] = (),
        artifacts: tuple[ArtifactReference, ...] = (),
        memory_proposals: tuple[MemoryProposalReceipt, ...] = (),
        adaptations: tuple[AdaptationReceipt, ...] = (),
        chat_turn_claim: ChatTurnClaim | None = None,
    ) -> None:
        super().__init__(message)
        self.actions = actions
        self.artifacts = artifacts
        self.memory_proposals = memory_proposals
        self.adaptations = adaptations
        self.chat_turn_claim = chat_turn_claim


class AgentColTurnRoutingError(AgentColTurnServiceError):
    """Raised when the routing boundary fails or returns invalid output."""


class AgentColTurnRoutingTimeoutError(AgentColTurnServiceError):
    """Raised when the routing provider exceeds its bounded deadline."""


class AgentColTurnResponderError(AgentColTurnServiceError):
    """Raised when responder-only Agent_Col cannot finish a turn."""


class AgentColTurnTimeoutError(AgentColTurnServiceError):
    """Raised when the complete cognitive turn exceeds its deadline."""


def _stable_merge(
    *groups: tuple[ReceiptT, ...],
) -> tuple[ReceiptT, ...]:
    merged: list[ReceiptT] = []
    for group in groups:
        for item in group:
            if item not in merged:
                merged.append(item)
    return tuple(merged)


class AgentColTurnService:
    def __init__(
        self,
        *,
        routing_client: genai.Client,
        expert_executor: ExpertExecutor,
        responder_runtime: ResponderRuntime,
        routing_request: RoutingRequest = (
            request_agent_col_routing_v3_directive
        ),
        artifact_executor: ArtifactExecutor | None = None,
        artifact_routing_request: ArtifactRoutingRequest = (
            request_agent_col_routing_v4_directive
        ),
        turn_timeout_seconds: float = TURN_TIMEOUT_SECONDS,
        routing_timeout_seconds: float = TURN_ROUTING_TIMEOUT_SECONDS,
        expert_budget_seconds: float = TURN_EXPERT_BUDGET_SECONDS,
        responder_reserve_seconds: float = (
            TURN_RESPONDER_RESERVE_SECONDS
        ),
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        for name, value in (
            ("turn_timeout_seconds", turn_timeout_seconds),
            ("routing_timeout_seconds", routing_timeout_seconds),
            ("expert_budget_seconds", expert_budget_seconds),
            ("responder_reserve_seconds", responder_reserve_seconds),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive.")
        self._routing_client = routing_client
        self._expert_executor = expert_executor
        self._responder_runtime = responder_runtime
        self._routing_request = routing_request
        self._artifact_executor = artifact_executor
        self._artifact_routing_request = artifact_routing_request
        self._turn_timeout_seconds = turn_timeout_seconds
        self._routing_timeout_seconds = routing_timeout_seconds
        self._expert_budget_seconds = expert_budget_seconds
        self._responder_reserve_seconds = responder_reserve_seconds
        self._clock = clock
        self._wall_clock = wall_clock

    async def run_turn(
        self,
        command: AgentColTurnCommand,
    ) -> AgentColTurnResult:
        deadline = self._clock() + self._turn_timeout_seconds
        try:
            async with asyncio.timeout(self._turn_timeout_seconds):
                if (
                    self._artifact_executor is not None
                    and command.chat_turn_claim is not None
                ):
                    return await self._run_artifact_capable_with_deadline(
                        command,
                        deadline,
                    )
                return await self._run_with_deadline(command, deadline)
        except TimeoutError as exc:
            logger.error(
                "Agent_Col turn failed (%s).",
                type(exc).__name__,
            )
            raise AgentColTurnTimeoutError(
                "Agent_Col turn timed out.",
                actions=command.precompleted_actions,
                artifacts=(
                    command.chat_turn_claim.precompleted_artifacts
                    if command.chat_turn_claim is not None
                    else ()
                ),
                memory_proposals=command.precompleted_memory_proposals,
                chat_turn_claim=command.chat_turn_claim,
            ) from exc

    async def _run_artifact_capable_with_deadline(
        self,
        command: AgentColTurnCommand,
        deadline: float,
    ) -> AgentColTurnResult:
        claim = command.chat_turn_claim
        artifact_executor = self._artifact_executor
        if claim is None or artifact_executor is None:
            raise AgentColTurnServiceError(
                "Agent_Col artifact authority is unavailable."
            )
        self._validate_artifact_claim(command, claim)
        numeric_projection = project_routing_numeric_candidates(
            command.message
        )
        text_projection = project_routing_text_blocks(command.message)
        routing_input = AgentColRoutingInputV4(
            current_message=command.message,
            candidate_urls=project_routing_url_candidates(
                command.message,
                command.recent_user_messages,
            ),
            numeric_candidates=numeric_projection.candidates,
            numeric_projection_incomplete=(
                numeric_projection.numeric_projection_incomplete
            ),
            text_block_candidates=text_projection.candidates,
            text_projection_incomplete=(
                text_projection.text_projection_incomplete
            ),
            available_capabilities=(
                self._expert_executor.available_capabilities
            ),
            artifact_creation_available=(
                claim.request.memory_decision is None
            ),
            structured_decision_present=(
                claim.request.memory_decision is not None
            ),
        )
        try:
            routing_timeout = min(
                self._routing_timeout_seconds,
                self._remaining_seconds(deadline),
            )
            directive = await self._artifact_routing_request(
                self._routing_client,
                routing_input,
                timeout_seconds=routing_timeout,
            )
        except AgentColRoutingV4ProviderTimeoutError as exc:
            raise AgentColTurnRoutingTimeoutError(
                "Agent_Col routing timed out.",
                actions=claim.precompleted_actions,
                artifacts=claim.precompleted_artifacts,
                memory_proposals=claim.precompleted_memory_proposals,
                chat_turn_claim=claim,
            ) from exc
        except (
            AgentColRoutingV4ProviderError,
            RoutingDirectiveInputErrorV4,
        ) as exc:
            raise AgentColTurnRoutingError(
                "Agent_Col routing failed.",
                actions=claim.precompleted_actions,
                artifacts=claim.precompleted_artifacts,
                memory_proposals=claim.precompleted_memory_proposals,
                chat_turn_claim=claim,
            ) from exc

        if directive.route is AgentColRouteV4.ARTIFACT:
            return await self._complete_artifact_turn(
                command,
                claim,
                directive,
                deadline,
            )

        v3_directive = AgentColRoutingDirective.model_validate(
            directive.model_dump(
                exclude={"artifact_intent", "schema_version"}
            )
            | {"schema_version": "3.0"}
        )
        v3_input = AgentColRoutingInput.model_validate(
            routing_input.model_dump(
                exclude={
                    "artifact_creation_available",
                    "structured_decision_present",
                }
            )
        )
        return await self._run_with_deadline(
            command,
            deadline,
            routing_input=v3_input,
            directive=v3_directive,
        )

    async def _complete_artifact_turn(
        self,
        command: AgentColTurnCommand,
        claim: ChatTurnClaim,
        directive: AgentColRoutingDirectiveV4,
        deadline: float,
    ) -> AgentColTurnResult:
        artifact_executor = self._artifact_executor
        if artifact_executor is None:
            raise AgentColTurnServiceError(
                "Agent_Col artifact authority is unavailable."
            )
        try:
            execution = await artifact_executor.execute(
                AgentColArtifactExecutionCommand(
                    claim=claim,
                    routing_directive=directive,
                    observed_at=self._wall_clock(),
                )
            )
        except AgentColArtifactExecutorConfigurationError as exc:
            raise AgentColTurnServiceError(
                "Agent_Col artifact execution failed.",
                actions=claim.precompleted_actions,
                artifacts=claim.precompleted_artifacts,
                memory_proposals=claim.precompleted_memory_proposals,
                chat_turn_claim=claim,
            ) from exc

        model_input_context = (
            *command.model_input_context,
            build_agent_col_artifact_model_context(execution.projection),
        )
        authoritative_actions = _stable_merge(
            command.precompleted_actions,
            execution.actions,
        )
        try:
            async with asyncio.timeout(self._remaining_seconds(deadline)):
                result = await self._responder_runtime.run_turn(
                    SupervisorTurnContext(
                        project_id=command.project_id,
                        session_id=command.session_id,
                        user_id=command.user_id,
                        message=command.message,
                        model_input_context=model_input_context,
                        source_message_id=command.source_message_id,
                        memory_decision_present=(
                            command.memory_decision_present
                        ),
                        turn_lease=command.turn_lease,
                        precompleted_actions=authoritative_actions,
                        precompleted_memory_proposals=(
                            command.precompleted_memory_proposals
                        ),
                    )
                )
        except SupervisorTimeoutError as exc:
            raise AgentColTurnTimeoutError(
                "Agent_Col turn timed out.",
                actions=_stable_merge(
                    authoritative_actions,
                    exc.actions,
                ),
                artifacts=execution.artifacts,
                memory_proposals=_stable_merge(
                    command.precompleted_memory_proposals,
                    exc.memory_proposals,
                ),
                adaptations=execution.adaptations,
                chat_turn_claim=execution.claim,
            ) from exc
        except SupervisorRuntimeError as exc:
            raise AgentColTurnResponderError(
                "Agent_Col responder failed.",
                actions=_stable_merge(
                    authoritative_actions,
                    exc.actions,
                ),
                artifacts=execution.artifacts,
                memory_proposals=_stable_merge(
                    command.precompleted_memory_proposals,
                    exc.memory_proposals,
                ),
                adaptations=execution.adaptations,
                chat_turn_claim=execution.claim,
            ) from exc
        return AgentColTurnResult(
            response=result.response,
            actions=_stable_merge(authoritative_actions, result.actions),
            artifacts=execution.artifacts,
            citations=result.citations,
            memory_proposals=_stable_merge(
                command.precompleted_memory_proposals,
                result.memory_proposals,
            ),
            adaptations=execution.adaptations,
            chat_turn_claim=execution.claim,
        )

    @staticmethod
    def _validate_artifact_claim(
        command: AgentColTurnCommand,
        claim: ChatTurnClaim,
    ) -> None:
        request = claim.request
        if (
            request.project_id != command.project_id
            or request.session_id != command.session_id
            or request.user_id != command.user_id
            or request.message != command.message
            or bool(request.memory_decision)
            != command.memory_decision_present
            or claim.precompleted_actions
            != command.precompleted_actions
            or claim.precompleted_memory_proposals
            != command.precompleted_memory_proposals
        ):
            raise AgentColTurnServiceError(
                "Agent_Col artifact claim is inconsistent."
            )

    async def _run_with_deadline(
        self,
        command: AgentColTurnCommand,
        deadline: float,
        routing_input: AgentColRoutingInput | None = None,
        directive: AgentColRoutingDirective | None = None,
    ) -> AgentColTurnResult:
        if routing_input is None or directive is None:
            numeric_projection = project_routing_numeric_candidates(
                command.message
            )
            text_projection = project_routing_text_blocks(command.message)
            routing_input = AgentColRoutingInput(
                current_message=command.message,
                candidate_urls=project_routing_url_candidates(
                    command.message,
                    command.recent_user_messages,
                ),
                numeric_candidates=numeric_projection.candidates,
                numeric_projection_incomplete=(
                    numeric_projection.numeric_projection_incomplete
                ),
                text_block_candidates=text_projection.candidates,
                text_projection_incomplete=(
                    text_projection.text_projection_incomplete
                ),
                available_capabilities=(
                    self._expert_executor.available_capabilities
                ),
            )
            try:
                routing_timeout = min(
                    self._routing_timeout_seconds,
                    self._remaining_seconds(deadline),
                )
                directive = await self._routing_request(
                    self._routing_client,
                    routing_input,
                    timeout_seconds=routing_timeout,
                )
            except AgentColRoutingV3ProviderTimeoutError as exc:
                logger.error(
                    "Agent_Col routing failed (%s).",
                    type(exc).__name__,
                )
                raise AgentColTurnRoutingTimeoutError(
                    "Agent_Col routing timed out.",
                    actions=command.precompleted_actions,
                    memory_proposals=(
                        command.precompleted_memory_proposals
                    ),
                ) from exc
            except (
                AgentColRoutingV3ProviderError,
                RoutingDirectiveInputError,
            ) as exc:
                failure_classification = type(exc).__name__
                if isinstance(exc, RoutingDirectiveInputError):
                    failure_classification = (
                        f"routing_directive_input:{exc.reason.value}"
                    )
                logger.error(
                    "Agent_Col routing failed (%s).",
                    failure_classification,
                )
                raise AgentColTurnRoutingError(
                    "Agent_Col routing failed.",
                    actions=command.precompleted_actions,
                    memory_proposals=(
                        command.precompleted_memory_proposals
                    ),
                ) from exc
        expert_routes = {
            AgentColRoute.SOURCE,
            AgentColRoute.RESEARCH,
            AgentColRoute.COMPUTATION,
            AgentColRoute.REQUIREMENTS_VERIFICATION,
        }
        if directive.route in expert_routes:
            remaining_expert_time = (
                self._remaining_seconds(deadline)
                - self._responder_reserve_seconds
            )
            if remaining_expert_time <= 0:
                responder_context = self._timed_out_expert_context(directive)
            else:
                expert_timeout = min(
                    self._expert_budget_seconds,
                    remaining_expert_time,
                )
                try:
                    async with asyncio.timeout(expert_timeout):
                        responder_context = (
                            await self._expert_executor.execute(
                                directive,
                                routing_input,
                            )
                        )
                except TimeoutError:
                    responder_context = self._timed_out_expert_context(
                        directive
                    )
                except (
                    AgentColExpertExecutorV3ConfigurationError,
                    RoutingDirectiveInputError,
                ) as exc:
                    logger.error(
                        "Agent_Col expert execution failed (%s).",
                        type(exc).__name__,
                    )
                    raise AgentColTurnServiceError(
                        "Agent_Col expert execution failed.",
                        actions=command.precompleted_actions,
                        memory_proposals=(
                            command.precompleted_memory_proposals
                        ),
                    ) from exc
        else:
            try:
                responder_context = await self._expert_executor.execute(
                    directive,
                    routing_input,
                )
            except (
                AgentColExpertExecutorV3ConfigurationError,
                RoutingDirectiveInputError,
            ) as exc:
                logger.error(
                    "Agent_Col expert execution failed (%s).",
                    type(exc).__name__,
                )
                raise AgentColTurnServiceError(
                    "Agent_Col expert execution failed.",
                    actions=command.precompleted_actions,
                    memory_proposals=(
                        command.precompleted_memory_proposals
                    ),
                ) from exc
        model_input_context = (
            *command.model_input_context,
            build_agent_col_responder_v3_model_context(responder_context),
        )
        try:
            async with asyncio.timeout(self._remaining_seconds(deadline)):
                result = await self._responder_runtime.run_turn(
                    SupervisorTurnContext(
                        project_id=command.project_id,
                        session_id=command.session_id,
                        user_id=command.user_id,
                        message=command.message,
                        model_input_context=model_input_context,
                        source_message_id=command.source_message_id,
                        memory_decision_present=(
                            command.memory_decision_present
                        ),
                        turn_lease=command.turn_lease,
                        precompleted_actions=command.precompleted_actions,
                        precompleted_memory_proposals=(
                            command.precompleted_memory_proposals
                        ),
                    )
                )
        except SupervisorTimeoutError as exc:
            logger.error(
                "Agent_Col responder failed (%s).",
                type(exc).__name__,
            )
            raise AgentColTurnTimeoutError(
                "Agent_Col turn timed out.",
                actions=_stable_merge(
                    command.precompleted_actions,
                    responder_context.actions,
                    exc.actions,
                ),
                memory_proposals=_stable_merge(
                    command.precompleted_memory_proposals,
                    exc.memory_proposals,
                ),
            ) from exc
        except SupervisorRuntimeError as exc:
            logger.error(
                "Agent_Col responder failed (%s).",
                type(exc).__name__,
            )
            raise AgentColTurnResponderError(
                "Agent_Col responder failed.",
                actions=_stable_merge(
                    command.precompleted_actions,
                    responder_context.actions,
                    exc.actions,
                ),
                memory_proposals=_stable_merge(
                    command.precompleted_memory_proposals,
                    exc.memory_proposals,
                ),
            ) from exc
        return AgentColTurnResult(
            response=result.response,
            actions=_stable_merge(
                command.precompleted_actions,
                responder_context.actions,
                result.actions,
            ),
            artifacts=result.artifacts,
            citations=_stable_merge(
                responder_context.citations,
                result.citations,
            ),
            memory_proposals=_stable_merge(
                command.precompleted_memory_proposals,
                result.memory_proposals,
            ),
        )

    def _remaining_seconds(self, deadline: float) -> float:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise TimeoutError
        return remaining

    @staticmethod
    def _timed_out_expert_context(
        directive: AgentColRoutingDirective,
    ) -> AgentColResponderContextV3:
        if directive.route is AgentColRoute.SOURCE:
            result = SourceExpertResult(status=ExpertStatus.TIMED_OUT)
        elif directive.route is AgentColRoute.RESEARCH:
            result = ResearchExpertResult(status=ExpertStatus.TIMED_OUT)
        elif directive.route is AgentColRoute.COMPUTATION:
            result = ComputationResponderResult(status=ExpertStatus.TIMED_OUT)
        elif directive.route is AgentColRoute.REQUIREMENTS_VERIFICATION:
            result = RequirementsVerificationResult(
                status=ExpertStatus.TIMED_OUT
            )
        else:
            raise RuntimeError("Only expert routes can be time constrained.")
        return AgentColResponderContextV3(
            routing_directive=directive,
            expert_result=result,
        )
