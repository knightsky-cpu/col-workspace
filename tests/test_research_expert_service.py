import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from google.adk.events import Event
from google.adk.agents.run_config import RunConfig
from google.adk.tools.google_search_tool import google_search
from google.adk.workflow import NodeTimeoutError, Workflow
from google.genai import types
from pydantic import ValidationError

from research_expert import (
    BoundedResearchAgent,
    RESEARCH_EXPERT_TIMEOUT_SECONDS,
    ResearchExpertInput,
)
from vertex_config import VertexAISettings


class RecordingSessionService:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.deleted: list[dict[str, object]] = []

    async def create_session(self, **kwargs: object) -> object:
        self.created.append(kwargs)
        return object()

    async def delete_session(self, **kwargs: object) -> None:
        self.deleted.append(kwargs)


class RecordingRunner:
    def __init__(self, events: tuple[Event, ...]) -> None:
        self.events = events
        self.calls: list[dict[str, object]] = []

    async def run_async(self, **kwargs: object) -> AsyncIterator[Event]:
        self.calls.append(kwargs)
        for event in self.events:
            yield event


class FailingRunner:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    async def run_async(self, **kwargs: object) -> AsyncIterator[Event]:
        del kwargs
        self.calls += 1
        raise self.error
        yield  # pragma: no cover


class BlockingRunner:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def run_async(self, **kwargs: object) -> AsyncIterator[Event]:
        del kwargs
        self.started.set()
        await asyncio.Event().wait()
        yield  # pragma: no cover


class FailingCreateSessionService(RecordingSessionService):
    async def create_session(self, **kwargs: object) -> object:
        self.created.append(kwargs)
        raise RuntimeError("private-session-create-payload")


def grounded_workflow_event() -> Event:
    claim = "Python 3.14.7 is a current Python release."
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


def research_workflow_event(
    *,
    response_text: str,
    grounding_chunks: list[types.GroundingChunk],
    grounding_supports: list[types.GroundingSupport],
) -> Event:
    return Event(
        author="research_expert",
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=response_text)],
        ),
        output=response_text,
        grounding_metadata=types.GroundingMetadata(
            grounding_chunks=grounding_chunks,
            grounding_supports=grounding_supports,
        ),
    )


def public_grounding_chunk(index: int = 0) -> types.GroundingChunk:
    return types.GroundingChunk(
        web=types.GroundingChunkWeb(
            uri=f"https://source-{index}.example.org/evidence",
            title=f"Provider title {index}",
        )
    )


def test_research_service_uses_one_node_isolated_workflow_topology() -> None:
    from research_expert_service import (
        RESEARCH_EXPERT_APP_NAME,
        RESEARCH_EXPERT_WORKFLOW_NAME,
        ResearchExpertService,
    )

    service = ResearchExpertService.from_vertex_settings(
        VertexAISettings(project="project-1", location="global")
    )

    app = service.app
    assert app.name == RESEARCH_EXPERT_APP_NAME == "agent_col_research"
    assert isinstance(app.root_agent, Workflow)
    assert app.root_agent.name == RESEARCH_EXPERT_WORKFLOW_NAME == (
        "research_workflow"
    )
    assert app.root_agent.graph is not None
    assert len(app.root_agent.graph.edges) == 1
    edge = app.root_agent.graph.edges[0]
    assert edge.from_node.name == "__START__"
    assert isinstance(edge.to_node, BoundedResearchAgent)

    expert = edge.to_node
    assert expert.name == "research_expert"
    assert expert.mode == "single_turn"
    assert expert.input_schema is ResearchExpertInput
    assert expert.tools == [google_search]
    assert expert.sub_agents == []
    assert expert.disallow_transfer_to_parent is True
    assert expert.disallow_transfer_to_peers is True
    assert expert.include_contents == "none"
    assert expert.timeout == RESEARCH_EXPERT_TIMEOUT_SECONDS == 45


@pytest.mark.asyncio
async def test_research_service_projects_exact_request_and_cleans_session(
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert_service import (
        RESEARCH_EXPERT_APP_NAME,
        RESEARCH_EXPERT_MAX_LLM_CALLS,
        RESEARCH_EXPERT_SERVICE_USER_ID,
        ResearchExpertService,
    )

    sessions = RecordingSessionService()
    runner = RecordingRunner((grounded_workflow_event(),))
    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=runner,
        session_service=sessions,
    )
    request = ResearchExpertInput(
        question="What is the current Python release?",
        objective="Establish the current stable release.",
        constraints=("Prefer the official Python source.",),
    )

    result = await service.research(request)

    assert result.status is ExpertStatus.COMPLETED
    assert result.payload is not None
    assert result.payload.findings[0].claim == (
        "Python 3.14.7 is a current Python release."
    )
    assert len(sessions.created) == 1
    assert len(sessions.deleted) == 1
    create_call = sessions.created[0]
    delete_call = sessions.deleted[0]
    assert create_call == delete_call
    assert create_call["app_name"] == RESEARCH_EXPERT_APP_NAME
    assert RESEARCH_EXPERT_SERVICE_USER_ID == "research_service"
    assert create_call["user_id"] == RESEARCH_EXPERT_SERVICE_USER_ID
    session_id = create_call["session_id"]
    assert isinstance(session_id, str)
    assert len(session_id) == 32

    assert len(runner.calls) == 1
    run_call = runner.calls[0]
    assert run_call["user_id"] == RESEARCH_EXPERT_SERVICE_USER_ID
    assert run_call["session_id"] == session_id
    message = run_call["new_message"]
    assert isinstance(message, types.Content)
    assert message.role == "user"
    assert len(message.parts or ()) == 1
    assert message.parts[0].text == request.model_dump_json()
    assert json.loads(message.parts[0].text) == request.model_dump(
        mode="json"
    )
    config = run_call["run_config"]
    assert isinstance(config, RunConfig)
    assert RESEARCH_EXPERT_MAX_LLM_CALLS == 2
    assert config.max_llm_calls == RESEARCH_EXPERT_MAX_LLM_CALLS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "events",
    (
        (),
        (grounded_workflow_event(), grounded_workflow_event()),
        (
            grounded_workflow_event().model_copy(
                update={"grounding_metadata": None}
            ),
        ),
    ),
)
async def test_research_service_rejects_invalid_event_streams_and_cleans_up(
    events: tuple[Event, ...],
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert_service import (
        ResearchExpertService,
        ResearchExpertServiceError,
    )

    sessions = RecordingSessionService()
    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=RecordingRunner(events),
        session_service=sessions,
    )

    with pytest.raises(ResearchExpertServiceError) as exc_info:
        await service.research(
            ResearchExpertInput(question="Question?", objective="Objective")
        )

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT
    assert str(exc_info.value) == "Research Expert execution failed."
    assert exc_info.value.__cause__ is None
    assert len(sessions.deleted) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("events", "expected_reason"),
    (
        ((), "missing_final_event"),
        (
            (grounded_workflow_event(), grounded_workflow_event()),
            "multiple_final_events",
        ),
        (
            (
                grounded_workflow_event().model_copy(
                    update={"grounding_metadata": None}
                ),
            ),
            "missing_grounding_metadata",
        ),
        (
            (
                grounded_workflow_event().model_copy(
                    update={
                        "grounding_metadata": types.GroundingMetadata(
                            grounding_chunks=[]
                        )
                    }
                ),
            ),
            "missing_grounding_chunks",
        ),
        (
            (
                grounded_workflow_event().model_copy(
                    update={
                        "grounding_metadata": types.GroundingMetadata(
                            grounding_chunks=[
                                types.GroundingChunk(
                                    web=types.GroundingChunkWeb(
                                        uri=(
                                            "https://www.python.org/"
                                            "downloads/"
                                        ),
                                        title="Private provider title",
                                    )
                                )
                            ],
                            grounding_supports=[],
                        )
                    }
                ),
            ),
            "missing_grounding_supports",
        ),
    ),
)
async def test_research_service_reports_content_safe_invalid_output_reason(
    events: tuple[Event, ...],
    expected_reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert_service import (
        ResearchExpertService,
        ResearchExpertServiceError,
    )

    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=RecordingRunner(events),
        session_service=RecordingSessionService(),
    )

    with pytest.raises(ResearchExpertServiceError) as exc_info:
        await service.research(
            ResearchExpertInput(
                question="Private user question marker?",
                objective="Private user objective marker.",
            )
        )

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT
    assert getattr(exc_info.value, "invalid_output_reason", None) == (
        expected_reason
    )
    assert (
        f"Research Expert output rejected ({expected_reason})."
        in caplog.text
    )
    assert "Private user question marker" not in caplog.text
    assert "Private user objective marker" not in caplog.text
    assert "Private provider title" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "expected_reason"),
    (
        (
            research_workflow_event(
                response_text="",
                grounding_chunks=[public_grounding_chunk()],
                grounding_supports=[
                    types.GroundingSupport(
                        segment=types.Segment(text="Private claim marker."),
                        grounding_chunk_indices=[0],
                    )
                ],
            ),
            "missing_response_text",
        ),
        (
            research_workflow_event(
                response_text="Private claim marker.",
                grounding_chunks=[
                    types.GroundingChunk(
                        web=types.GroundingChunkWeb(
                            uri="https://private.invalid/evidence",
                            title="Private provider title",
                        )
                    )
                ],
                grounding_supports=[
                    types.GroundingSupport(
                        segment=types.Segment(text="Private claim marker."),
                        grounding_chunk_indices=[0],
                    )
                ],
            ),
            "no_valid_public_sources",
        ),
        (
            research_workflow_event(
                response_text="Private claim marker.",
                grounding_chunks=[public_grounding_chunk()],
                grounding_supports=[
                    types.GroundingSupport(
                        segment=types.Segment(text="Private claim marker."),
                        grounding_chunk_indices=[0],
                    )
                ]
                * 41,
            ),
            "too_many_grounding_supports",
        ),
        (
            research_workflow_event(
                response_text="Private claim marker.",
                grounding_chunks=[public_grounding_chunk()],
                grounding_supports=[
                    types.GroundingSupport(
                        segment=types.Segment(start_index=10, end_index=5),
                        grounding_chunk_indices=[0],
                    )
                ],
            ),
            "no_mappable_grounding_claims",
        ),
        (
            research_workflow_event(
                response_text="Private claim marker.",
                grounding_chunks=[public_grounding_chunk()],
                grounding_supports=[
                    types.GroundingSupport(
                        segment=types.Segment(text="Private claim marker."),
                        grounding_chunk_indices=[99],
                    )
                ],
            ),
            "grounded_claim_without_source",
        ),
        (
            research_workflow_event(
                response_text="Private claim marker.",
                grounding_chunks=[
                    public_grounding_chunk(index) for index in range(6)
                ],
                grounding_supports=[
                    types.GroundingSupport(
                        segment=types.Segment(text="Private claim marker."),
                        grounding_chunk_indices=list(range(6)),
                    )
                ],
            ),
            "too_many_sources_for_claim",
        ),
        (
            research_workflow_event(
                response_text="x" * 1_001,
                grounding_chunks=[public_grounding_chunk()],
                grounding_supports=[
                    types.GroundingSupport(
                        segment=types.Segment(text="x" * 1_001),
                        grounding_chunk_indices=[0],
                    )
                ],
            ),
            "normalized_result_validation_failed",
        ),
    ),
)
async def test_research_service_distinguishes_normalization_rejection_reason(
    event: Event,
    expected_reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert_service import (
        ResearchExpertService,
        ResearchExpertServiceError,
    )

    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=RecordingRunner((event,)),
        session_service=RecordingSessionService(),
    )

    with pytest.raises(ResearchExpertServiceError) as exc_info:
        await service.research(
            ResearchExpertInput(
                question="Private user question marker?",
                objective="Private user objective marker.",
            )
        )

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT
    assert getattr(exc_info.value, "invalid_output_reason", None) == (
        expected_reason
    )
    assert (
        f"Research Expert output rejected ({expected_reason})."
        in caplog.text
    )
    for private_marker in (
        "Private user question marker",
        "Private user objective marker",
        "Private provider title",
        "Private claim marker",
    ):
        assert private_marker not in caplog.text


@pytest.mark.asyncio
async def test_research_service_compacts_extra_valid_grounded_claims(
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert_service import ResearchExpertService

    claims = tuple(
        f"Documented public fact {index}." for index in range(1, 10)
    )
    event = research_workflow_event(
        response_text=" ".join(claims),
        grounding_chunks=[public_grounding_chunk()],
        grounding_supports=[
            types.GroundingSupport(
                segment=types.Segment(text=claim),
                grounding_chunk_indices=[0],
            )
            for claim in claims
        ],
    )
    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=RecordingRunner((event,)),
        session_service=RecordingSessionService(),
    )

    result = await service.research(
        ResearchExpertInput(
            question="Which public facts are documented?",
            objective="Return bounded public evidence.",
        )
    )

    assert result.status is ExpertStatus.COMPLETED
    assert result.payload is not None
    assert len(result.payload.findings) == 8
    assert result.evidence is not None
    assert result.evidence.grounded_finding_count == 8
    assert result.evidence.grounding_support_count == 9


def rejected_input_error() -> ValidationError:
    try:
        ResearchExpertInput.model_validate(
            {"question": "", "objective": "Objective"}
        )
    except ValidationError as exc:
        return exc
    raise AssertionError("Expected invalid Research input fixture.")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_error", "expected_status"),
    (
        (rejected_input_error(), "rejected_input"),
        (
            NodeTimeoutError(node_name="research_expert", timeout=45),
            "timed_out",
        ),
        (RuntimeError("private-provider-payload"), "unavailable"),
    ),
)
async def test_research_service_maps_runtime_failures_without_content_leak(
    provider_error: Exception,
    expected_status: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert_service import (
        ResearchExpertService,
        ResearchExpertServiceError,
    )

    sessions = RecordingSessionService()
    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=FailingRunner(provider_error),
        session_service=sessions,
    )

    with pytest.raises(ResearchExpertServiceError) as exc_info:
        await service.research(
            ResearchExpertInput(
                question="private-user-question",
                objective="private-user-objective",
            )
        )

    assert exc_info.value.status is ExpertStatus(expected_status)
    assert str(exc_info.value) == "Research Expert execution failed."
    assert exc_info.value.__cause__ is provider_error
    assert len(sessions.deleted) == 1
    assert "private-provider-payload" not in caplog.text
    assert "private-user-question" not in caplog.text
    assert "private-user-objective" not in caplog.text


@pytest.mark.asyncio
async def test_research_service_bounds_runtime_and_cleans_timed_out_session(
) -> None:
    from expert_contracts import ExpertStatus
    from research_expert_service import (
        ResearchExpertService,
        ResearchExpertServiceError,
    )

    sessions = RecordingSessionService()
    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=BlockingRunner(),
        session_service=sessions,
        timeout_seconds=0.001,
    )

    with pytest.raises(ResearchExpertServiceError) as exc_info:
        await service.research(
            ResearchExpertInput(question="Question?", objective="Objective")
        )

    assert exc_info.value.status is ExpertStatus.TIMED_OUT
    assert isinstance(exc_info.value.__cause__, TimeoutError)
    assert len(sessions.deleted) == 1


@pytest.mark.asyncio
async def test_research_service_propagates_cancellation_after_cleanup() -> None:
    from research_expert_service import ResearchExpertService

    sessions = RecordingSessionService()
    runner = BlockingRunner()
    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=runner,
        session_service=sessions,
    )
    task = asyncio.create_task(
        service.research(
            ResearchExpertInput(question="Question?", objective="Objective")
        )
    )
    await runner.started.wait()

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(sessions.deleted) == 1


@pytest.mark.asyncio
async def test_research_service_does_not_delete_uncreated_session() -> None:
    from expert_contracts import ExpertStatus
    from research_expert_service import (
        ResearchExpertService,
        ResearchExpertServiceError,
    )

    sessions = FailingCreateSessionService()
    service = ResearchExpertService(
        app=object(),  # type: ignore[arg-type]
        runner=RecordingRunner(()),
        session_service=sessions,
    )

    with pytest.raises(ResearchExpertServiceError) as exc_info:
        await service.research(
            ResearchExpertInput(question="Question?", objective="Objective")
        )

    assert exc_info.value.status is ExpertStatus.UNAVAILABLE
    assert len(sessions.created) == 1
    assert sessions.deleted == []


def test_research_service_rejects_nonpositive_timeout() -> None:
    from research_expert_service import ResearchExpertService

    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        ResearchExpertService(
            app=object(),  # type: ignore[arg-type]
            runner=RecordingRunner(()),
            session_service=RecordingSessionService(),
            timeout_seconds=0,
        )
