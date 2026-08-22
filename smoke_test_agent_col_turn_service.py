import asyncio
import logging

from agent_col_responder_context import AgentColResponderContext
from agent_col_routing import AgentColRoute, AgentColRoutingDirective
from agent_col_routing_provider import AgentColRoutingProviderError
from agent_col_turn_service import (
    AgentColTurnCommand,
    AgentColTurnRoutingError,
    AgentColTurnService,
)
from expert_contracts import ExpertCapability
from source_expert import SourceExpertResult, build_source_receipts
from supervisor_runtime import SupervisorTurnResult


_SUCCESS = (
    "r3.3c turn-orchestration-service pass routes=2 max_experts=1 "
    "reserve=true routing_failure_contained=true"
)


class _RoutingRequest:
    def __init__(
        self,
        directive: AgentColRoutingDirective | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.directive = directive
        self.error = error
        self.calls = 0

    async def __call__(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.directive is None:
            raise RuntimeError("Smoke routing directive is missing.")
        return self.directive


class _ExpertExecutor:
    available_capabilities = (
        ExpertCapability.SOURCE,
        ExpertCapability.RESEARCH,
    )

    def __init__(self, source_context: AgentColResponderContext) -> None:
        self.source_context = source_context
        self.dispatches = 0
        self.expert_attempts = 0

    async def execute(
        self,
        directive: AgentColRoutingDirective,
        routing_input: object,
    ) -> AgentColResponderContext:
        del routing_input
        self.dispatches += 1
        if directive.route is AgentColRoute.SOURCE:
            self.expert_attempts += 1
            return self.source_context
        return AgentColResponderContext(routing_directive=directive)


class _Responder:
    def __init__(self) -> None:
        self.contexts: list[object] = []

    async def run_turn(self, context: object) -> SupervisorTurnResult:
        self.contexts.append(context)
        return SupervisorTurnResult(response="Agent_Col owned final response.")


class _Clock:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)
        self._last = values[-1]

    def __call__(self) -> float:
        try:
            self._last = next(self._values)
        except StopIteration:
            pass
        return self._last


def _source_context() -> AgentColResponderContext:
    directive = AgentColRoutingDirective(
        route="source",
        source_intent={
            "objective": "Explain the selected public page.",
            "selected_url_ids": ["url-1"],
        },
    )
    result = SourceExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "The page supplies grounded documentation evidence.",
            "payload": {
                "documents": [
                    {
                        "source_id": "source-1",
                        "url": "https://example.com/",
                        "retrieval_status": "retrieved",
                        "evidence_summary": "Example Domain documentation.",
                    }
                ],
                "facts": [
                    {
                        "text": "Example Domain is used in documentation.",
                        "source_ids": ["source-1"],
                    }
                ],
                "sources": [
                    {
                        "source_id": "source-1",
                        "uri": "https://example.com/",
                        "label": "Example Domain",
                    }
                ],
            },
            "evidence": {
                "source_ids": ["source-1"],
                "grounded_statement_count": 1,
                "grounding_support_count": 1,
            },
        }
    )
    receipts = build_source_receipts(result)
    return AgentColResponderContext(
        routing_directive=directive,
        expert_result=result,
        actions=receipts.actions,
        citations=receipts.citations,
    )


def _command(message: str) -> AgentColTurnCommand:
    return AgentColTurnCommand(
        project_id="smoke-project",
        session_id="smoke-session",
        user_id="smoke-user",
        message=message,
    )


async def run_smoke() -> str:
    """Exercise the real orchestration service with offline collaborators."""
    source_context = _source_context()
    executor = _ExpertExecutor(source_context)
    responder = _Responder()

    direct_service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=_RoutingRequest(
            AgentColRoutingDirective(route="direct")
        ),
    )
    direct = await direct_service.run_turn(
        _command("Explain one stable concept directly.")
    )

    source_service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=_RoutingRequest(source_context.routing_directive),
    )
    source = await source_service.run_turn(
        _command("Analyze https://example.com/ using supplied evidence.")
    )

    reserve_service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=_RoutingRequest(source_context.routing_directive),
        clock=_Clock(0.0, 0.0, 26.0, 26.0),
    )
    reserved = await reserve_service.run_turn(
        _command("Analyze https://example.com/ without losing response time.")
    )

    failing_executor = _ExpertExecutor(source_context)
    failing_responder = _Responder()
    failing_service = AgentColTurnService(
        routing_client=object(),
        expert_executor=failing_executor,
        responder_runtime=failing_responder,
        routing_request=_RoutingRequest(
            error=AgentColRoutingProviderError("hidden-provider-error")
        ),
    )
    try:
        await failing_service.run_turn(_command("Routing failure request."))
    except AgentColTurnRoutingError:
        routing_failure_contained = True
    else:
        routing_failure_contained = False

    if direct.actions or direct.citations:
        raise RuntimeError("Direct route created cognitive receipts.")
    if tuple(action.action_name for action in source.actions) != (
        "url_context",
    ) or len(source.citations) != 1:
        raise RuntimeError("Completed Source receipts are invalid.")
    if reserved.actions or reserved.citations:
        raise RuntimeError("Reserved responder time created false receipts.")
    if executor.expert_attempts != 1:
        raise RuntimeError("Expert attempt bound is invalid.")
    if len(responder.contexts) != 3:
        raise RuntimeError("Agent_Col final response ownership is invalid.")
    if (
        not routing_failure_contained
        or failing_executor.dispatches
        or failing_responder.contexts
    ):
        raise RuntimeError("Routing failure containment is invalid.")
    return _SUCCESS


def main() -> None:
    logging.disable(logging.CRITICAL)
    print(asyncio.run(run_smoke()))


if __name__ == "__main__":
    main()
