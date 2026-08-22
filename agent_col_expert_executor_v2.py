"""Parallel routing-v2 expert execution boundary."""

from pydantic import ValidationError

from agent_col_responder_context_v2 import AgentColResponderContextV2
from agent_col_routing_v2 import (
    AgentColRoute,
    AgentColRoutingDirective,
    AgentColRoutingInput,
    validate_routing_directive_for_input,
)
from computational_expert import (
    ComputationExpertInput,
    ComputationExpertResult,
    ComputationInputs,
    ComputationResponderResult,
    NamedScalar,
    NumericSeries,
    PrecisionRule,
    build_computation_receipts,
    project_computation_responder_result,
)
from computational_expert_service import (
    ComputationalExpertService,
    ComputationalExpertServiceError,
)
from expert_contracts import ExpertCapability, ExpertStatus
from research_expert import (
    ResearchExpertInput,
    ResearchExpertResult,
    build_research_receipts,
)
from research_expert_service import (
    ResearchExpertService,
    ResearchExpertServiceError,
)
from source_expert import (
    SourceExpertInput,
    SourceExpertResult,
    build_source_receipts,
)
from source_expert_service import SourceExpertService, SourceExpertServiceError


class AgentColExpertExecutorV2ConfigurationError(RuntimeError):
    """Raised when configured experts disagree with routing availability."""


def build_computation_expert_input(
    directive: AgentColRoutingDirective,
    routing_input: AgentColRoutingInput,
) -> ComputationExpertInput:
    """Resolve validated numeric candidate IDs into one expert request."""
    validate_routing_directive_for_input(directive, routing_input)
    intent = directive.computation_intent
    if intent is None:
        raise AgentColExpertExecutorV2ConfigurationError(
            "Computation intent is required."
        )

    candidates_by_id = {
        candidate.candidate_id: candidate
        for candidate in routing_input.numeric_candidates
    }
    scalars = tuple(
        NamedScalar(
            name=selection.name,
            value=candidates_by_id[selection.numeric_id].value,
            unit=candidates_by_id[selection.numeric_id].unit_symbol,
        )
        for selection in intent.scalar_inputs
    )
    series = tuple(
        NumericSeries(
            name=selection.name,
            values=tuple(
                candidates_by_id[numeric_id].value
                for numeric_id in selection.numeric_ids
            ),
            unit=candidates_by_id[selection.numeric_ids[0]].unit_symbol,
        )
        for selection in intent.series_inputs
    )
    precision = None
    if intent.precision is not None:
        precision_candidate = candidates_by_id[
            intent.precision.digits_numeric_id
        ]
        precision = PrecisionRule(
            mode=intent.precision.mode,
            digits=int(precision_candidate.value),
        )
    return ComputationExpertInput(
        objective=intent.objective,
        inputs=ComputationInputs(
            scalars=scalars,
            series=series,
            expression=None,
        ),
        required_precision=precision,
        constraints=intent.constraints,
    )


class AgentColExpertExecutorV2:
    """Execute zero or one expert selected by a validated v2 directive."""

    def __init__(
        self,
        *,
        source_service: SourceExpertService | None = None,
        research_service: ResearchExpertService | None = None,
        computation_service: ComputationalExpertService | None = None,
    ) -> None:
        self._source_service = source_service
        self._research_service = research_service
        self._computation_service = computation_service

    @property
    def available_capabilities(self) -> tuple[ExpertCapability, ...]:
        """Return the stable capability catalog derived from dependencies."""
        capabilities: list[ExpertCapability] = []
        if self._source_service is not None:
            capabilities.append(ExpertCapability.SOURCE)
        if self._research_service is not None:
            capabilities.append(ExpertCapability.RESEARCH)
        if self._computation_service is not None:
            capabilities.append(ExpertCapability.COMPUTATION)
        return tuple(capabilities)

    async def execute(
        self,
        directive: AgentColRoutingDirective,
        routing_input: AgentColRoutingInput,
    ) -> AgentColResponderContextV2:
        """Execute the selected capability without fallback or chaining."""
        validate_routing_directive_for_input(directive, routing_input)
        if routing_input.available_capabilities != self.available_capabilities:
            raise AgentColExpertExecutorV2ConfigurationError(
                "Expert executor configuration does not match routing input."
            )
        if directive.route in {AgentColRoute.DIRECT, AgentColRoute.CLARIFY}:
            return AgentColResponderContextV2(routing_directive=directive)
        if directive.route is AgentColRoute.SOURCE:
            return await self._execute_source(directive, routing_input)
        if directive.route is AgentColRoute.RESEARCH:
            return await self._execute_research(directive)
        return await self._execute_computation(directive, routing_input)

    async def _execute_source(
        self,
        directive: AgentColRoutingDirective,
        routing_input: AgentColRoutingInput,
    ) -> AgentColResponderContextV2:
        intent = directive.source_intent
        service = self._source_service
        if intent is None or service is None:
            raise AgentColExpertExecutorV2ConfigurationError(
                "Selected Source capability is not configured."
            )
        urls_by_id = {
            candidate.candidate_id: candidate.url
            for candidate in routing_input.candidate_urls
        }
        request = SourceExpertInput(
            objective=intent.objective,
            urls=tuple(
                urls_by_id[candidate_id]
                for candidate_id in intent.selected_url_ids
            ),
            constraints=intent.constraints,
        )
        try:
            result = await service.analyze(request)
        except SourceExpertServiceError as exc:
            result = SourceExpertResult(status=exc.status)
        receipts = build_source_receipts(result)
        return AgentColResponderContextV2(
            routing_directive=directive,
            expert_result=result,
            actions=receipts.actions,
            citations=receipts.citations,
        )

    async def _execute_research(
        self,
        directive: AgentColRoutingDirective,
    ) -> AgentColResponderContextV2:
        intent = directive.research_intent
        service = self._research_service
        if intent is None or service is None:
            raise AgentColExpertExecutorV2ConfigurationError(
                "Selected Research capability is not configured."
            )
        request = ResearchExpertInput(
            question=intent.question,
            objective=intent.objective,
            constraints=intent.constraints,
        )
        try:
            result = await service.research(request)
        except ResearchExpertServiceError as exc:
            result = ResearchExpertResult(status=exc.status)
        receipts = build_research_receipts(result)
        return AgentColResponderContextV2(
            routing_directive=directive,
            expert_result=result,
            actions=receipts.actions,
            citations=receipts.citations,
        )

    async def _execute_computation(
        self,
        directive: AgentColRoutingDirective,
        routing_input: AgentColRoutingInput,
    ) -> AgentColResponderContextV2:
        service = self._computation_service
        if service is None:
            raise AgentColExpertExecutorV2ConfigurationError(
                "Selected Computation capability is not configured."
            )
        try:
            request = build_computation_expert_input(
                directive, routing_input
            )
        except ValidationError:
            projected = ComputationResponderResult(
                status=ExpertStatus.REJECTED_INPUT
            )
        else:
            try:
                result: ComputationExpertResult = await service.compute(request)
            except ComputationalExpertServiceError as exc:
                projected = ComputationResponderResult(status=exc.status)
            else:
                projected = project_computation_responder_result(result)
        receipts = build_computation_receipts(projected)
        return AgentColResponderContextV2(
            routing_directive=directive,
            expert_result=projected,
            actions=receipts.actions,
            citations=receipts.citations,
        )
