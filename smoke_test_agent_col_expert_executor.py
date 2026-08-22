import asyncio
from collections.abc import AsyncIterator

from google.adk.events import Event
from google.genai import types

from agent_col_expert_executor import AgentColExpertExecutor
from agent_col_routing import AgentColRoutingDirective, AgentColRoutingInput
from expert_contracts import ExpertStatus
from research_expert_service import ResearchExpertService
from source_expert import SourceExpertResult
from source_expert_service import SourceExpertServiceError


_SUCCESS = (
    "r3.3b deterministic-expert-executor pass routes=4 "
    "max_experts=1 research_cleanup=true"
)


class _Sessions:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.deleted: list[dict[str, object]] = []

    async def create_session(self, **kwargs: object) -> object:
        self.created.append(kwargs)
        return object()

    async def delete_session(self, **kwargs: object) -> None:
        self.deleted.append(kwargs)


class _ResearchRunner:
    def __init__(self, event: Event) -> None:
        self.event = event
        self.calls = 0

    async def run_async(self, **kwargs: object) -> AsyncIterator[Event]:
        del kwargs
        self.calls += 1
        yield self.event


class _SourceService:
    def __init__(self, result: SourceExpertResult) -> None:
        self.result = result
        self.calls = 0

    async def analyze(self, request: object) -> SourceExpertResult:
        del request
        self.calls += 1
        return self.result


class _FailingSourceService:
    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, request: object) -> SourceExpertResult:
        del request
        self.calls += 1
        raise SourceExpertServiceError(ExpertStatus.UNAVAILABLE)


def _source_result() -> SourceExpertResult:
    return SourceExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "One grounded Source statement.",
            "payload": {
                "documents": [
                    {
                        "source_id": "source-1",
                        "url": "https://example.com/",
                        "retrieval_status": "retrieved",
                        "evidence_summary": "Example source evidence.",
                    }
                ],
                "facts": [
                    {
                        "text": "Example source evidence.",
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


def _research_event() -> Event:
    claim = "Python publishes release information."
    return Event(
        author="research_expert",
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=claim)],
        ),
        output=claim,
        grounding_metadata=types.GroundingMetadata(
            grounding_chunks=[
                types.GroundingChunk(
                    web=types.GroundingChunkWeb(
                        uri="https://www.python.org/downloads/",
                        title="Python downloads",
                    )
                )
            ],
            grounding_supports=[
                types.GroundingSupport(
                    segment=types.Segment(text=claim),
                    grounding_chunk_indices=[0],
                )
            ],
        ),
    )


def _routing_input(*, with_url: bool) -> AgentColRoutingInput:
    candidates = (
        (
            {
                "candidate_id": "url-1",
                "url": "https://example.com/",
                "source": "current_message",
            },
        )
        if with_url
        else ()
    )
    return AgentColRoutingInput(
        current_message="Bounded offline smoke request.",
        candidate_urls=candidates,
        available_capabilities=("source", "research"),
    )


async def run_smoke() -> str:
    """Verify all deterministic executor routes without external I/O."""
    sessions = _Sessions()
    research_runner = _ResearchRunner(_research_event())
    research_service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=research_runner,
        session_service=sessions,
    )
    source_service = _SourceService(_source_result())
    executor = AgentColExpertExecutor(
        source_service=source_service,  # type: ignore[arg-type]
        research_service=research_service,
    )

    direct = await executor.execute(
        AgentColRoutingDirective(route="direct"),
        _routing_input(with_url=False),
    )
    clarify = await executor.execute(
        AgentColRoutingDirective(
            route="clarify",
            clarifying_question="Which source should I analyze?",
        ),
        _routing_input(with_url=False),
    )
    source = await executor.execute(
        AgentColRoutingDirective(
            route="source",
            source_intent={
                "objective": "Analyze the selected source.",
                "selected_url_ids": ["url-1"],
            },
        ),
        _routing_input(with_url=True),
    )
    research = await executor.execute(
        AgentColRoutingDirective(
            route="research",
            research_intent={
                "question": "What does Python publish?",
                "objective": "Verify one current public fact.",
            },
        ),
        _routing_input(with_url=False),
    )

    if direct.expert_result is not None or clarify.expert_result is not None:
        raise RuntimeError("Direct or clarify executed an expert.")
    if source_service.calls != 1 or research_runner.calls != 1:
        raise RuntimeError("Selected expert count is invalid.")
    if tuple(action.action_name for action in source.actions) != (
        "url_context",
    ):
        raise RuntimeError("Source receipts are invalid.")
    if tuple(action.action_name for action in research.actions) != (
        "google_search",
    ):
        raise RuntimeError("Research receipts are invalid.")
    if sessions.created != sessions.deleted or len(sessions.deleted) != 1:
        raise RuntimeError("Research session cleanup is invalid.")

    failing_source = _FailingSourceService()
    failure_executor = AgentColExpertExecutor(
        source_service=failing_source,  # type: ignore[arg-type]
        research_service=research_service,
    )
    failed = await failure_executor.execute(
        AgentColRoutingDirective(
            route="source",
            source_intent={
                "objective": "Analyze the selected source.",
                "selected_url_ids": ["url-1"],
            },
        ),
        _routing_input(with_url=True),
    )
    if (
        failing_source.calls != 1
        or research_runner.calls != 1
        or failed.actions
        or failed.citations
    ):
        raise RuntimeError("Expert failure containment is invalid.")
    return _SUCCESS


def main() -> None:
    print(asyncio.run(run_smoke()))


if __name__ == "__main__":
    main()
