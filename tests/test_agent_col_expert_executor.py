import pytest

from agent_col_routing import (
    AgentColRoutingDirective,
    AgentColRoutingInput,
)
from expert_contracts import ExpertCapability


class RecordingSourceService:
    def __init__(self, result: object | None = None) -> None:
        self.result = result
        self.requests: list[object] = []

    async def analyze(self, request: object) -> object:
        self.requests.append(request)
        return self.result


class RecordingResearchService:
    def __init__(self, result: object | None = None) -> None:
        self.result = result
        self.requests: list[object] = []

    async def research(self, request: object) -> object:
        self.requests.append(request)
        return self.result


class FailingSourceService(RecordingSourceService):
    def __init__(self, status: str) -> None:
        super().__init__()
        self.status = status

    async def analyze(self, request: object) -> object:
        from expert_contracts import ExpertStatus
        from source_expert_service import SourceExpertServiceError

        self.requests.append(request)
        raise SourceExpertServiceError(ExpertStatus(self.status))


class FailingResearchService(RecordingResearchService):
    def __init__(self, status: str) -> None:
        super().__init__()
        self.status = status

    async def research(self, request: object) -> object:
        from expert_contracts import ExpertStatus
        from research_expert_service import ResearchExpertServiceError

        self.requests.append(request)
        raise ResearchExpertServiceError(ExpertStatus(self.status))


def completed_source_result():
    from source_expert import SourceExpertResult

    return SourceExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "Source analysis produced two grounded statements.",
            "payload": {
                "documents": [
                    {
                        "source_id": "source-1",
                        "url": "https://example.com/three",
                        "retrieval_status": "retrieved",
                        "evidence_summary": "Third page evidence.",
                    },
                    {
                        "source_id": "source-2",
                        "url": "https://example.com/one",
                        "retrieval_status": "retrieved",
                        "evidence_summary": "First page evidence.",
                    },
                ],
                "facts": [
                    {
                        "text": "Third page evidence.",
                        "source_ids": ["source-1"],
                    },
                    {
                        "text": "First page evidence.",
                        "source_ids": ["source-2"],
                    },
                ],
                "sources": [
                    {
                        "source_id": "source-1",
                        "uri": "https://example.com/three",
                        "label": "Third page",
                    },
                    {
                        "source_id": "source-2",
                        "uri": "https://example.com/one",
                        "label": "First page",
                    },
                ],
            },
            "evidence": {
                "source_ids": ["source-1", "source-2"],
                "grounded_statement_count": 2,
                "grounding_support_count": 2,
            },
        }
    )


def completed_research_result():
    from research_expert import ResearchExpertResult

    return ResearchExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "Research produced one grounded finding.",
            "payload": {
                "findings": [
                    {
                        "claim": "Python publishes current release details.",
                        "evidence_summary": "The official downloads page.",
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "directive",
    (
        AgentColRoutingDirective(route="direct"),
        AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Which supplied page should I analyze?",
        ),
    ),
)
async def test_executor_uses_zero_experts_for_direct_and_clarify(
    directive: AgentColRoutingDirective,
) -> None:
    from agent_col_expert_executor import AgentColExpertExecutor

    source = RecordingSourceService()
    research = RecordingResearchService()
    executor = AgentColExpertExecutor(
        source_service=source,
        research_service=research,
    )
    routing_input = AgentColRoutingInput(
        current_message="Help me understand this request.",
        available_capabilities=("source", "research"),
    )

    context = await executor.execute(directive, routing_input)

    assert context.routing_directive == directive
    assert context.expert_result is None
    assert context.actions == ()
    assert context.citations == ()
    assert source.requests == []
    assert research.requests == []


@pytest.mark.asyncio
async def test_executor_maps_selected_source_ids_in_directive_order() -> None:
    from agent_col_expert_executor import AgentColExpertExecutor
    from source_expert import SourceExpertInput, build_source_receipts

    source_result = completed_source_result()
    source = RecordingSourceService(source_result)
    research = RecordingResearchService()
    executor = AgentColExpertExecutor(
        source_service=source,
        research_service=research,
    )
    routing_input = AgentColRoutingInput(
        current_message="Compare the selected pages.",
        candidate_urls=(
            {
                "candidate_id": "url-1",
                "url": "https://example.com/one",
                "source": "current_message",
            },
            {
                "candidate_id": "url-3",
                "url": "https://example.com/three",
                "source": "recent_user_history",
            },
            {
                "candidate_id": "url-2",
                "url": "https://example.com/two",
                "source": "current_message",
            },
        ),
        available_capabilities=("source", "research"),
    )
    directive = AgentColRoutingDirective(
        route="source",
        source_intent={
            "objective": "Compare the third and first pages.",
            "selected_url_ids": ["url-3", "url-1"],
            "constraints": ["Use only retrieved evidence."],
        },
    )

    context = await executor.execute(directive, routing_input)

    assert len(source.requests) == 1
    request = source.requests[0]
    assert isinstance(request, SourceExpertInput)
    assert request.objective == "Compare the third and first pages."
    assert tuple(str(url) for url in request.urls) == (
        "https://example.com/three",
        "https://example.com/one",
    )
    assert request.constraints == ("Use only retrieved evidence.",)
    assert research.requests == []
    assert context.routing_directive == directive
    assert context.expert_result == source_result
    receipts = build_source_receipts(source_result)
    assert context.actions == receipts.actions
    assert context.citations == receipts.citations


@pytest.mark.asyncio
async def test_executor_rejects_unknown_source_id_before_expert_access(
) -> None:
    from agent_col_expert_executor import AgentColExpertExecutor
    from agent_col_routing import RoutingDirectiveInputError

    source = RecordingSourceService(completed_source_result())
    executor = AgentColExpertExecutor(source_service=source)
    routing_input = AgentColRoutingInput(
        current_message="Analyze the page.",
        candidate_urls=(
            {
                "candidate_id": "url-1",
                "url": "https://example.com/one",
                "source": "current_message",
            },
        ),
        available_capabilities=("source",),
    )
    directive = AgentColRoutingDirective(
        route="source",
        source_intent={
            "objective": "Analyze another page.",
            "selected_url_ids": ["url-2"],
        },
    )

    with pytest.raises(RoutingDirectiveInputError):
        await executor.execute(directive, routing_input)

    assert source.requests == []


@pytest.mark.asyncio
async def test_executor_maps_exact_research_intent_once() -> None:
    from agent_col_expert_executor import AgentColExpertExecutor
    from research_expert import ResearchExpertInput, build_research_receipts

    research_result = completed_research_result()
    source = RecordingSourceService()
    research = RecordingResearchService(research_result)
    executor = AgentColExpertExecutor(
        source_service=source,
        research_service=research,
    )
    routing_input = AgentColRoutingInput(
        current_message="What is the current Python release?",
        available_capabilities=("source", "research"),
    )
    directive = AgentColRoutingDirective(
        route="research",
        research_intent={
            "question": "What is the current stable Python release?",
            "objective": "Verify it with current public evidence.",
            "constraints": ["Prefer the official Python source."],
        },
    )

    context = await executor.execute(directive, routing_input)

    assert source.requests == []
    assert len(research.requests) == 1
    request = research.requests[0]
    assert isinstance(request, ResearchExpertInput)
    assert request.question == "What is the current stable Python release?"
    assert request.objective == "Verify it with current public evidence."
    assert request.constraints == ("Prefer the official Python source.",)
    assert context.routing_directive == directive
    assert context.expert_result == research_result
    receipts = build_research_receipts(research_result)
    assert context.actions == receipts.actions
    assert context.citations == receipts.citations


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", ("source", "research"))
@pytest.mark.parametrize(
    "status",
    ("rejected_input", "unavailable", "timed_out", "invalid_output"),
)
async def test_executor_contains_typed_failure_without_fallback_or_receipts(
    capability: str,
    status: str,
) -> None:
    from agent_col_expert_executor import AgentColExpertExecutor
    from expert_contracts import ExpertStatus
    from research_expert import ResearchExpertResult
    from source_expert import SourceExpertResult

    source = (
        FailingSourceService(status)
        if capability == "source"
        else RecordingSourceService()
    )
    research = (
        FailingResearchService(status)
        if capability == "research"
        else RecordingResearchService()
    )
    executor = AgentColExpertExecutor(
        source_service=source,
        research_service=research,
    )
    routing_input = AgentColRoutingInput(
        current_message="Private request content.",
        candidate_urls=(
            {
                "candidate_id": "url-1",
                "url": "https://example.com/private-path",
                "source": "current_message",
            },
        ),
        available_capabilities=("source", "research"),
    )
    directive = (
        AgentColRoutingDirective(
            route="source",
            source_intent={
                "objective": "Private source objective.",
                "selected_url_ids": ["url-1"],
            },
        )
        if capability == "source"
        else AgentColRoutingDirective(
            route="research",
            research_intent={
                "question": "Private research question?",
                "objective": "Private research objective.",
            },
        )
    )

    context = await executor.execute(directive, routing_input)

    expected_type = (
        SourceExpertResult
        if capability == "source"
        else ResearchExpertResult
    )
    assert isinstance(context.expert_result, expected_type)
    assert context.expert_result.status is ExpertStatus(status)
    assert context.expert_result.summary is None
    assert context.expert_result.limitations == ()
    assert context.expert_result.payload is None
    assert context.expert_result.evidence is None
    assert context.actions == ()
    assert context.citations == ()
    assert len(source.requests) == (1 if capability == "source" else 0)
    assert len(research.requests) == (
        1 if capability == "research" else 0
    )
    serialized = context.expert_result.model_dump_json()
    assert "Private" not in serialized
    assert "private-path" not in serialized


@pytest.mark.asyncio
async def test_executor_does_not_disguise_unexpected_programming_error(
) -> None:
    from agent_col_expert_executor import AgentColExpertExecutor

    class BrokenSourceService(RecordingSourceService):
        async def analyze(self, request: object) -> object:
            self.requests.append(request)
            raise RuntimeError("programming defect")

    source = BrokenSourceService()
    research = RecordingResearchService()
    executor = AgentColExpertExecutor(
        source_service=source,
        research_service=research,
    )
    routing_input = AgentColRoutingInput(
        current_message="Analyze the URL.",
        candidate_urls=(
            {
                "candidate_id": "url-1",
                "url": "https://example.com/",
                "source": "current_message",
            },
        ),
        available_capabilities=("source", "research"),
    )
    directive = AgentColRoutingDirective(
        route="source",
        source_intent={
            "objective": "Analyze the page.",
            "selected_url_ids": ["url-1"],
        },
    )

    with pytest.raises(RuntimeError, match="programming defect"):
        await executor.execute(directive, routing_input)

    assert len(source.requests) == 1
    assert research.requests == []


def test_executor_derives_available_capabilities_from_services() -> None:
    from agent_col_expert_executor import AgentColExpertExecutor

    assert AgentColExpertExecutor().available_capabilities == ()
    assert AgentColExpertExecutor(
        source_service=RecordingSourceService()
    ).available_capabilities == (ExpertCapability.SOURCE,)
    assert AgentColExpertExecutor(
        research_service=RecordingResearchService()
    ).available_capabilities == (ExpertCapability.RESEARCH,)
    assert AgentColExpertExecutor(
        source_service=RecordingSourceService(),
        research_service=RecordingResearchService(),
    ).available_capabilities == (
        ExpertCapability.SOURCE,
        ExpertCapability.RESEARCH,
    )


@pytest.mark.asyncio
async def test_executor_rejects_capability_configuration_mismatch() -> None:
    from agent_col_expert_executor import (
        AgentColExpertExecutor,
        AgentColExpertExecutorConfigurationError,
    )

    research = RecordingResearchService()
    executor = AgentColExpertExecutor(research_service=research)
    routing_input = AgentColRoutingInput(
        current_message="Answer directly.",
        available_capabilities=("source", "research"),
    )

    with pytest.raises(AgentColExpertExecutorConfigurationError) as exc_info:
        await executor.execute(
            AgentColRoutingDirective(route="direct"),
            routing_input,
        )

    assert str(exc_info.value) == (
        "Expert executor configuration does not match routing input."
    )
    assert research.requests == []
