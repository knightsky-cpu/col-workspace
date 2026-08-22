import importlib

import pytest

from agent_col_numeric_projection import project_routing_numeric_candidates
from agent_col_routing_v2 import AgentColRoutingDirective, AgentColRoutingInput
from expert_contracts import ExpertCapability, ExpertStatus


def load_executor_v2():
    try:
        return importlib.import_module("agent_col_expert_executor_v2")
    except ModuleNotFoundError:
        pytest.fail("agent_col_expert_executor_v2 has not been implemented")


def mixed_numeric_routing_case():
    message = (
        "Calculate from $10, 15%, and values 12, 15, 18 using "
        "2 decimal places."
    )
    projection = project_routing_numeric_candidates(message)
    routing_input = AgentColRoutingInput(
        current_message=message,
        numeric_candidates=projection.candidates,
        numeric_projection_incomplete=(
            projection.numeric_projection_incomplete
        ),
        available_capabilities=("computation",),
    )
    directive = AgentColRoutingDirective(
        route="computation",
        computation_intent={
            "objective": "Calculate the requested summary.",
            "scalar_inputs": [
                {"name": "budget", "numeric_id": "number-1"},
                {"name": "rate", "numeric_id": "number-2"},
            ],
            "series_inputs": [
                {
                    "name": "values",
                    "numeric_ids": ["number-3", "number-4", "number-5"],
                }
            ],
            "precision": {
                "mode": "decimal_places",
                "digits_numeric_id": "number-6",
            },
            "constraints": ["Use population standard deviation."],
        },
    )
    return directive, routing_input


def test_builder_resolves_exact_values_units_order_and_precision() -> None:
    executor_v2 = load_executor_v2()
    directive, routing_input = mixed_numeric_routing_case()

    request = executor_v2.build_computation_expert_input(
        directive,
        routing_input,
    )

    assert request.objective == "Calculate the requested summary."
    assert tuple(
        (value.name, value.value, value.unit)
        for value in request.inputs.scalars
    ) == (
        ("budget", 10.0, "$"),
        ("rate", 15.0, "%"),
    )
    assert tuple(
        (series.name, series.values, series.unit)
        for series in request.inputs.series
    ) == (("values", (12.0, 15.0, 18.0), None),)
    assert request.inputs.expression is None
    assert request.required_precision is not None
    assert request.required_precision.mode == "decimal_places"
    assert request.required_precision.digits == 2
    assert request.constraints == ("Use population standard deviation.",)


def test_builder_maps_significant_figures_from_selected_candidate() -> None:
    executor_v2 = load_executor_v2()
    message = "Calculate 12.5 divided by 4 using 3 significant figures."
    projection = project_routing_numeric_candidates(message)
    routing_input = AgentColRoutingInput(
        current_message=message,
        numeric_candidates=projection.candidates,
        available_capabilities=("computation",),
    )
    directive = AgentColRoutingDirective(
        route="computation",
        computation_intent={
            "objective": "Calculate the quotient.",
            "scalar_inputs": [
                {"name": "dividend", "numeric_id": "number-1"},
                {"name": "divisor", "numeric_id": "number-2"},
            ],
            "precision": {
                "mode": "significant_figures",
                "digits_numeric_id": "number-3",
            },
        },
    )

    request = executor_v2.build_computation_expert_input(
        directive,
        routing_input,
    )

    assert request.inputs.expression is None
    assert request.required_precision is not None
    assert request.required_precision.mode == "significant_figures"
    assert request.required_precision.digits == 3


def test_builder_rejects_incompatible_directive_before_construction() -> None:
    executor_v2 = load_executor_v2()
    directive, routing_input = mixed_numeric_routing_case()
    incompatible = routing_input.model_copy(
        update={"available_capabilities": ()}
    )

    with pytest.raises(RuntimeError):
        executor_v2.build_computation_expert_input(directive, incompatible)


class RecordingComputationService:
    def __init__(self, result=None) -> None:
        self.result = result
        self.requests: list[object] = []

    async def compute(self, request):
        self.requests.append(request)
        return self.result


class FailingComputationService(RecordingComputationService):
    def __init__(self, status: ExpertStatus) -> None:
        super().__init__()
        self.status = status

    async def compute(self, request):
        from computational_expert_service import (
            ComputationalExpertServiceError,
        )

        self.requests.append(request)
        raise ComputationalExpertServiceError(self.status)


class RecordingSourceService:
    def __init__(self, result=None) -> None:
        self.result = result
        self.requests: list[object] = []

    async def analyze(self, request):
        self.requests.append(request)
        return self.result


class RecordingResearchService:
    def __init__(self, result=None) -> None:
        self.result = result
        self.requests: list[object] = []

    async def research(self, request):
        self.requests.append(request)
        return self.result


def completed_computation_for_request(request):
    from computational_expert import ComputationExpertResult

    return ComputationExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "Computation completed with 1 verified run.",
            "payload": {
                "method": "Provider-executed Python computation.",
                "inputs_used": request.inputs.model_dump(mode="json"),
                "result": "Mean 15.00; population standard deviation 2.45.",
                "execution_runs": [
                    {
                        "language": "python",
                        "code": "print('RAW_EXECUTOR_CODE')",
                        "outcome": "success",
                        "output": "RAW_EXECUTOR_OUTPUT\n",
                    }
                ],
            },
            "evidence": {
                "execution_count": 1,
                "successful_execution_count": 1,
                "code_character_count": 26,
                "output_character_count": 20,
            },
        }
    )


def completed_source_result():
    from source_expert import SourceExpertResult

    return SourceExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "One grounded source statement.",
            "payload": {
                "documents": [
                    {
                        "source_id": "source-1",
                        "url": "https://example.com/",
                        "retrieval_status": "retrieved",
                        "evidence_summary": "Example evidence.",
                    }
                ],
                "facts": [
                    {"text": "Example evidence.", "source_ids": ["source-1"]}
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


def completed_research_result():
    from research_expert import ResearchExpertResult

    return ResearchExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "One grounded finding.",
            "payload": {
                "findings": [
                    {
                        "claim": "Python publishes release details.",
                        "evidence_summary": "Official downloads page.",
                        "source_ids": ["source-1"],
                        "confidence": "high",
                    }
                ],
                "sources": [
                    {
                        "source_id": "source-1",
                        "uri": "https://www.python.org/downloads/",
                        "label": "Python downloads",
                    }
                ],
            },
            "evidence": {
                "source_ids": ["source-1"],
                "grounded_finding_count": 1,
                "grounding_support_count": 1,
            },
        }
    )


def test_executor_v2_derives_stable_capability_order() -> None:
    executor_v2 = load_executor_v2()

    executor = executor_v2.AgentColExpertExecutorV2(
        source_service=RecordingSourceService(),
        research_service=RecordingResearchService(),
        computation_service=RecordingComputationService(),
    )

    assert executor.available_capabilities == (
        ExpertCapability.SOURCE,
        ExpertCapability.RESEARCH,
        ExpertCapability.COMPUTATION,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "directive",
    (
        AgentColRoutingDirective(route="direct"),
        AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Which values should I calculate?",
        ),
    ),
)
async def test_executor_v2_uses_zero_experts_for_direct_and_clarify(
    directive,
) -> None:
    executor_v2 = load_executor_v2()
    computation = RecordingComputationService()
    executor = executor_v2.AgentColExpertExecutorV2(
        computation_service=computation
    )
    routing_input = AgentColRoutingInput(
        current_message="Explain the request.",
        available_capabilities=("computation",),
    )

    context = await executor.execute(directive, routing_input)

    assert context.routing_directive == directive
    assert context.expert_result is None
    assert context.actions == ()
    assert context.citations == ()
    assert computation.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ("source", "research"))
async def test_executor_v2_preserves_one_call_source_and_research_parity(
    route: str,
) -> None:
    executor_v2 = load_executor_v2()
    source = RecordingSourceService(completed_source_result())
    research = RecordingResearchService(completed_research_result())
    executor = executor_v2.AgentColExpertExecutorV2(
        source_service=source,
        research_service=research,
    )
    routing_input = AgentColRoutingInput(
        current_message="Use the selected expert.",
        candidate_urls=(
            {
                "candidate_id": "url-1",
                "url": "https://example.com/",
                "source": "current_message",
            },
        ),
        available_capabilities=("source", "research"),
    )
    directive = (
        AgentColRoutingDirective(
            route="source",
            source_intent={
                "objective": "Analyze the supplied page.",
                "selected_url_ids": ["url-1"],
                "constraints": ["Use retrieved evidence."],
            },
        )
        if route == "source"
        else AgentColRoutingDirective(
            route="research",
            research_intent={
                "question": "What is current?",
                "objective": "Verify with public evidence.",
                "constraints": ["Prefer an official source."],
            },
        )
    )

    context = await executor.execute(directive, routing_input)

    assert len(source.requests) == (1 if route == "source" else 0)
    assert len(research.requests) == (1 if route == "research" else 0)
    assert context.expert_result is not None
    assert context.expert_result.status is ExpertStatus.COMPLETED
    assert len(context.actions) == 1
    assert len(context.citations) == 1


@pytest.mark.asyncio
async def test_executor_v2_executes_computation_once_and_projects_result(
) -> None:
    executor_v2 = load_executor_v2()
    directive, routing_input = mixed_numeric_routing_case()
    request = executor_v2.build_computation_expert_input(
        directive, routing_input
    )
    computation = RecordingComputationService(
        completed_computation_for_request(request)
    )
    executor = executor_v2.AgentColExpertExecutorV2(
        computation_service=computation
    )

    context = await executor.execute(directive, routing_input)

    assert computation.requests == [request]
    assert context.expert_result is not None
    assert context.expert_result.status is ExpertStatus.COMPLETED
    assert context.actions[0].model_dump() == {
        "action_name": "run_computation",
        "status": "completed",
    }
    assert context.citations == ()
    serialized = context.model_dump_json()
    assert "RAW_EXECUTOR_CODE" not in serialized
    assert "RAW_EXECUTOR_OUTPUT" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    (
        ExpertStatus.REJECTED_INPUT,
        ExpertStatus.UNAVAILABLE,
        ExpertStatus.TIMED_OUT,
        ExpertStatus.INVALID_OUTPUT,
    ),
)
async def test_executor_v2_contains_computation_failure_without_fallback(
    status: ExpertStatus,
) -> None:
    executor_v2 = load_executor_v2()
    directive, routing_input = mixed_numeric_routing_case()
    computation = FailingComputationService(status)
    source = RecordingSourceService()
    research = RecordingResearchService()
    executor = executor_v2.AgentColExpertExecutorV2(
        source_service=source,
        research_service=research,
        computation_service=computation,
    )
    routing_input = routing_input.model_copy(
        update={
            "available_capabilities": (
                "source",
                "research",
                "computation",
            )
        }
    )

    context = await executor.execute(directive, routing_input)

    assert len(computation.requests) == 1
    assert source.requests == []
    assert research.requests == []
    assert context.expert_result is not None
    assert context.expert_result.status is status
    assert context.expert_result.summary is None
    assert context.expert_result.payload is None
    assert context.expert_result.evidence is None
    assert context.actions == ()
    assert context.citations == ()


@pytest.mark.asyncio
async def test_executor_v2_contains_request_construction_drift_as_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor_v2 = load_executor_v2()
    directive, routing_input = mixed_numeric_routing_case()
    computation = RecordingComputationService()
    executor = executor_v2.AgentColExpertExecutorV2(
        computation_service=computation
    )

    def reject_internal_construction(*_args):
        from computational_expert import ComputationExpertInput

        return ComputationExpertInput.model_validate(
            {"objective": " ", "inputs": {}}
        )

    monkeypatch.setattr(
        executor_v2,
        "build_computation_expert_input",
        reject_internal_construction,
    )

    context = await executor.execute(directive, routing_input)

    assert computation.requests == []
    assert context.expert_result is not None
    assert context.expert_result.status is ExpertStatus.REJECTED_INPUT
    assert context.expert_result.summary is None
    assert context.expert_result.payload is None
    assert context.expert_result.evidence is None
    assert context.actions == ()
    assert context.citations == ()


@pytest.mark.asyncio
async def test_executor_v2_rejects_configuration_mismatch_before_access(
) -> None:
    executor_v2 = load_executor_v2()
    computation = RecordingComputationService()
    executor = executor_v2.AgentColExpertExecutorV2(
        computation_service=computation
    )
    routing_input = AgentColRoutingInput(
        current_message="Answer directly.",
        available_capabilities=("source", "computation"),
    )

    with pytest.raises(
        executor_v2.AgentColExpertExecutorV2ConfigurationError
    ):
        await executor.execute(
            AgentColRoutingDirective(route="direct"), routing_input
        )

    assert computation.requests == []


@pytest.mark.asyncio
async def test_executor_v2_does_not_hide_unexpected_computation_error(
) -> None:
    executor_v2 = load_executor_v2()
    directive, routing_input = mixed_numeric_routing_case()

    class BrokenComputationService(RecordingComputationService):
        async def compute(self, request):
            self.requests.append(request)
            raise RuntimeError("programming defect")

    computation = BrokenComputationService()
    executor = executor_v2.AgentColExpertExecutorV2(
        computation_service=computation
    )

    with pytest.raises(RuntimeError, match="programming defect"):
        await executor.execute(directive, routing_input)

    assert len(computation.requests) == 1
