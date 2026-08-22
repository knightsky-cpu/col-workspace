from agent_col_responder_context import AgentColResponderContext
from agent_col_routing import (
    AgentColRoute,
    AgentColRoutingDirective,
    AgentColRoutingInput,
    validate_routing_directive_for_input,
)
from expert_contracts import ExpertCapability
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
from source_expert_service import (
    SourceExpertService,
    SourceExpertServiceError,
)


class AgentColExpertExecutorConfigurationError(RuntimeError):
    """Raised when configured experts disagree with routing availability."""


class AgentColExpertExecutor:
    """Execute only the expert selected by a validated routing directive."""

    def __init__(
        self,
        *,
        source_service: SourceExpertService | None = None,
        research_service: ResearchExpertService | None = None,
    ) -> None:
        self._source_service = source_service
        self._research_service = research_service

    @property
    def available_capabilities(self) -> tuple[ExpertCapability, ...]:
        """Return the stable capability catalog derived from dependencies."""
        capabilities: list[ExpertCapability] = []
        if self._source_service is not None:
            capabilities.append(ExpertCapability.SOURCE)
        if self._research_service is not None:
            capabilities.append(ExpertCapability.RESEARCH)
        return tuple(capabilities)

    async def execute(
        self,
        directive: AgentColRoutingDirective,
        routing_input: AgentColRoutingInput,
    ) -> AgentColResponderContext:
        """Execute zero or one expert and return validated responder context."""
        validate_routing_directive_for_input(directive, routing_input)
        if (
            routing_input.available_capabilities
            != self.available_capabilities
        ):
            raise AgentColExpertExecutorConfigurationError(
                "Expert executor configuration does not match routing input."
            )
        if directive.route in {AgentColRoute.DIRECT, AgentColRoute.CLARIFY}:
            return AgentColResponderContext(routing_directive=directive)
        if directive.route is AgentColRoute.SOURCE:
            source_intent = directive.source_intent
            source_service = self._source_service
            if source_intent is None or source_service is None:
                raise AgentColExpertExecutorConfigurationError(
                    "Selected Source capability is not configured."
                )
            urls_by_id = {
                candidate.candidate_id: candidate.url
                for candidate in routing_input.candidate_urls
            }
            request = SourceExpertInput(
                objective=source_intent.objective,
                urls=tuple(
                    urls_by_id[candidate_id]
                    for candidate_id
                    in source_intent.selected_url_ids
                ),
                constraints=source_intent.constraints,
            )
            try:
                result = await source_service.analyze(request)
            except SourceExpertServiceError as exc:
                result = SourceExpertResult(status=exc.status)
            receipts = build_source_receipts(result)
            return AgentColResponderContext(
                routing_directive=directive,
                expert_result=result,
                actions=receipts.actions,
                citations=receipts.citations,
            )
        research_intent = directive.research_intent
        research_service = self._research_service
        if research_intent is None or research_service is None:
            raise AgentColExpertExecutorConfigurationError(
                "Selected Research capability is not configured."
            )
        request = ResearchExpertInput(
            question=research_intent.question,
            objective=research_intent.objective,
            constraints=research_intent.constraints,
        )
        try:
            result = await research_service.research(request)
        except ResearchExpertServiceError as exc:
            result = ResearchExpertResult(status=exc.status)
        receipts = build_research_receipts(result)
        return AgentColResponderContext(
            routing_directive=directive,
            expert_result=result,
            actions=receipts.actions,
            citations=receipts.citations,
        )
