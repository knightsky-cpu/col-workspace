import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
import time
from typing import Protocol, TypeVar

from google import genai
from google.genai import types

from agent_col_expert_executor import AgentColExpertExecutorConfigurationError
from agent_col_responder_context import (
    AgentColResponderContext,
    build_agent_col_responder_model_context,
)
from agent_col_routing import (
    AgentColRoute,
    AgentColRoutingDirective,
    AgentColRoutingInput,
    RoutingDirectiveInputError,
    project_routing_url_candidates,
)
from agent_col_routing_provider import (
    AgentColRoutingProviderError,
    AgentColRoutingProviderTimeoutError,
    request_agent_col_routing_directive,
)
from expert_contracts import ExpertCapability, ExpertStatus
from memory_proposals import ProposalTurnLease
from research_expert import ResearchExpertResult
from schemas import (
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


class ExpertExecutor(Protocol):
    @property
    def available_capabilities(self) -> tuple[ExpertCapability, ...]: ...

    async def execute(
        self,
        directive: AgentColRoutingDirective,
        routing_input: AgentColRoutingInput,
    ) -> AgentColResponderContext: ...


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


@dataclass(frozen=True, slots=True)
class AgentColTurnResult:
    response: str
    actions: tuple[AgentActionReceipt, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    citations: tuple[CitationReference, ...] = ()
    memory_proposals: tuple[MemoryProposalReceipt, ...] = ()


class AgentColTurnServiceError(RuntimeError):
    """Raised when cognitive turn orchestration cannot complete safely."""

    def __init__(
        self,
        message: str,
        *,
        actions: tuple[AgentActionReceipt, ...] = (),
        memory_proposals: tuple[MemoryProposalReceipt, ...] = (),
    ) -> None:
        super().__init__(message)
        self.actions = actions
        self.memory_proposals = memory_proposals


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
        routing_request: RoutingRequest = request_agent_col_routing_directive,
        turn_timeout_seconds: float = TURN_TIMEOUT_SECONDS,
        routing_timeout_seconds: float = TURN_ROUTING_TIMEOUT_SECONDS,
        expert_budget_seconds: float = TURN_EXPERT_BUDGET_SECONDS,
        responder_reserve_seconds: float = (
            TURN_RESPONDER_RESERVE_SECONDS
        ),
        clock: Callable[[], float] = time.monotonic,
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
        self._turn_timeout_seconds = turn_timeout_seconds
        self._routing_timeout_seconds = routing_timeout_seconds
        self._expert_budget_seconds = expert_budget_seconds
        self._responder_reserve_seconds = responder_reserve_seconds
        self._clock = clock

    async def run_turn(
        self,
        command: AgentColTurnCommand,
    ) -> AgentColTurnResult:
        deadline = self._clock() + self._turn_timeout_seconds
        try:
            async with asyncio.timeout(self._turn_timeout_seconds):
                return await self._run_with_deadline(command, deadline)
        except TimeoutError as exc:
            logger.error(
                "Agent_Col turn failed (%s).",
                type(exc).__name__,
            )
            raise AgentColTurnTimeoutError(
                "Agent_Col turn timed out.",
                actions=command.precompleted_actions,
                memory_proposals=command.precompleted_memory_proposals,
            ) from exc

    async def _run_with_deadline(
        self,
        command: AgentColTurnCommand,
        deadline: float,
    ) -> AgentColTurnResult:
        routing_input = AgentColRoutingInput(
            current_message=command.message,
            candidate_urls=project_routing_url_candidates(
                command.message,
                command.recent_user_messages,
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
        except AgentColRoutingProviderTimeoutError as exc:
            logger.error(
                "Agent_Col routing failed (%s).",
                type(exc).__name__,
            )
            raise AgentColTurnRoutingTimeoutError(
                "Agent_Col routing timed out.",
                actions=command.precompleted_actions,
                memory_proposals=command.precompleted_memory_proposals,
            ) from exc
        except (
            AgentColRoutingProviderError,
            RoutingDirectiveInputError,
        ) as exc:
            logger.error(
                "Agent_Col routing failed (%s).",
                type(exc).__name__,
            )
            raise AgentColTurnRoutingError(
                "Agent_Col routing failed.",
                actions=command.precompleted_actions,
                memory_proposals=command.precompleted_memory_proposals,
            ) from exc
        remaining_seconds = self._remaining_seconds(deadline)
        required_expert_time = (
            self._expert_budget_seconds
            + self._responder_reserve_seconds
        )
        if (
            directive.route in {AgentColRoute.SOURCE, AgentColRoute.RESEARCH}
            and remaining_seconds < required_expert_time
        ):
            responder_context = self._timed_out_expert_context(directive)
        else:
            try:
                responder_context = await self._expert_executor.execute(
                    directive,
                    routing_input,
                )
            except (
                AgentColExpertExecutorConfigurationError,
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
            build_agent_col_responder_model_context(responder_context),
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
    ) -> AgentColResponderContext:
        if directive.route is AgentColRoute.SOURCE:
            result = SourceExpertResult(status=ExpertStatus.TIMED_OUT)
        elif directive.route is AgentColRoute.RESEARCH:
            result = ResearchExpertResult(status=ExpertStatus.TIMED_OUT)
        else:
            raise RuntimeError("Only expert routes can be time constrained.")
        return AgentColResponderContext(
            routing_directive=directive,
            expert_result=result,
        )
