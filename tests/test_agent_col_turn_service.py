import asyncio
from datetime import UTC, datetime

import pytest
from google.genai import types

from agent_col_responder_context_v3 import (
    AgentColResponderContextV3 as AgentColResponderContext,
)
from agent_col_routing_v3 import AgentColRoute, AgentColRoutingDirective
from memory_proposals import ProposalTurnLease
from schemas import (
    AgentActionReceipt,
    ContinuitySourceReceipt,
    MemoryClarificationChoice,
    MemoryClarificationReceipt,
    MemoryProposalReceipt,
)
from supervisor_runtime import (
    SupervisorTextDelta,
    SupervisorTurnCompleted,
    SupervisorTurnResult,
)


class RecordingRoutingRequest:
    def __init__(
        self,
        directive: AgentColRoutingDirective | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.directive = directive
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def __call__(
        self,
        client: object,
        routing_input: object,
        *,
        timeout_seconds: float,
    ) -> AgentColRoutingDirective:
        self.calls.append(
            {
                "client": client,
                "routing_input": routing_input,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        assert self.directive is not None
        return self.directive


class RecordingExecutor:
    def __init__(
        self,
        responder_context: AgentColResponderContext | None = None,
    ) -> None:
        self.available_capabilities = ("source", "research")
        self.responder_context = responder_context
        self.calls: list[tuple[object, object]] = []

    async def execute(
        self,
        directive: AgentColRoutingDirective,
        routing_input: object,
    ) -> AgentColResponderContext:
        self.calls.append((directive, routing_input))
        if self.responder_context is not None:
            return self.responder_context
        return AgentColResponderContext(routing_directive=directive)


class RecordingResponder:
    def __init__(
        self,
        result: SupervisorTurnResult | None = None,
        *,
        error: Exception | None = None,
        deltas: tuple[str, ...] = ("Agent_Col ", "response."),
    ) -> None:
        self.result = result or SupervisorTurnResult(
            response="Agent_Col response."
        )
        self.error = error
        self.deltas = deltas
        self.contexts: list[object] = []

    async def run_turn(self, context: object) -> SupervisorTurnResult:
        self.contexts.append(context)
        if self.error is not None:
            raise self.error
        return self.result

    async def stream_turn(self, context: object):
        self.contexts.append(context)
        if self.error is not None:
            raise self.error
        for text in self.deltas:
            yield SupervisorTextDelta(text=text)
        yield SupervisorTurnCompleted(result=self.result)


def memory_clarification_receipt() -> MemoryClarificationReceipt:
    return MemoryClarificationReceipt(
        clarification_id="memory-clarification--clarification-1",
        choices=[
            MemoryClarificationChoice(
                candidate_index=0,
                category_label="Response length",
                value_label="detailed",
            ),
            MemoryClarificationChoice(
                candidate_index=1,
                category_label="Explanation structure",
                value_label="step by step",
            ),
        ],
        expires_at=datetime(2026, 8, 25, 12, 15, tzinfo=UTC),
    )


def continuity_receipt() -> ContinuitySourceReceipt:
    return ContinuitySourceReceipt(
        receipt_id="continuity--note-export--rev-2",
        source_kind="collaborative_note",
        source_id="note-export",
        display_label="Used note: Export workflow",
        match_reason="exact_title",
        source_updated_at=datetime(2026, 8, 25, 12, 15, tzinfo=UTC),
    )


class RecordingArtifactExecutor:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def execute(self, command: object) -> object:
        from agent_col_artifact_executor import (
            AgentColArtifactExecutionResult,
            AgentColArtifactResponderProjection,
        )
        from schemas import ArtifactReference

        self.calls.append(command)
        artifact = ArtifactReference(
            artifact_type="synthesis_blueprint",
            project_id=command.claim.request.project_id,
            artifact_id="artifact-1",
            schema_version="2.0",
            display_label="Simple Pomodoro Timer",
        )
        return AgentColArtifactExecutionResult(
            claim=command.claim,
            actions=(),
            artifacts=(artifact,),
            adaptations=(),
            projection=AgentColArtifactResponderProjection(
                artifact=artifact,
                project_name="Simple Pomodoro Timer",
                core_value_proposition="A minimal timer workflow.",
                socratic_questions=(),
            ),
        )


class SequenceClock:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)
        self._last = values[-1]

    def __call__(self) -> float:
        try:
            self._last = next(self._values)
        except StopIteration:
            pass
        return self._last


class DelayedRoutingRequest(RecordingRoutingRequest):
    def __init__(
        self,
        directive: AgentColRoutingDirective,
        *,
        delay: float,
    ) -> None:
        super().__init__(directive)
        self.delay = delay
        self.cleaned = False

    async def __call__(
        self,
        client: object,
        routing_input: object,
        *,
        timeout_seconds: float,
    ) -> AgentColRoutingDirective:
        self.calls.append(
            {
                "client": client,
                "routing_input": routing_input,
                "timeout_seconds": timeout_seconds,
            }
        )
        try:
            await asyncio.sleep(self.delay)
            assert self.directive is not None
            return self.directive
        finally:
            self.cleaned = True


class DelayedExecutor(RecordingExecutor):
    def __init__(
        self,
        responder_context: AgentColResponderContext,
        *,
        delay: float,
    ) -> None:
        super().__init__(responder_context)
        self.delay = delay
        self.cleaned = False

    async def execute(
        self,
        directive: AgentColRoutingDirective,
        routing_input: object,
    ) -> AgentColResponderContext:
        self.calls.append((directive, routing_input))
        try:
            await asyncio.sleep(self.delay)
            assert self.responder_context is not None
            return self.responder_context
        finally:
            self.cleaned = True


class BudgetBlockingExecutor(RecordingExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.available_capabilities = (
            "source",
            "research",
            "computation",
            "requirements_verification",
        )
        self.cleaned = False

    async def execute(
        self,
        directive: AgentColRoutingDirective,
        routing_input: object,
    ) -> AgentColResponderContext:
        self.calls.append((directive, routing_input))
        try:
            await asyncio.sleep(30.0)
            raise AssertionError("expert budget failed to cancel execution")
        finally:
            self.cleaned = True


class DelayedResponder(RecordingResponder):
    def __init__(self, *, delay: float) -> None:
        super().__init__()
        self.delay = delay
        self.cleaned = False

    async def run_turn(self, context: object) -> SupervisorTurnResult:
        self.contexts.append(context)
        try:
            await asyncio.sleep(self.delay)
            return self.result
        finally:
            self.cleaned = True


def command_with_precompleted_effects() -> object:
    from agent_col_turn_service import AgentColTurnCommand

    return AgentColTurnCommand(
        project_id="secret-project",
        session_id="secret-session",
        user_id="secret-user",
        message="secret-message-content",
        precompleted_actions=(
            AgentActionReceipt(
                action_name="propose_memory_signal",
                status="completed",
            ),
        ),
        precompleted_memory_proposals=(
            MemoryProposalReceipt(
                proposal_id="response_length--proposal-2",
                category="response_length",
                proposed_value="concise",
                expires_at=datetime(2026, 8, 23, tzinfo=UTC),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_turn_service_streams_only_the_responder_after_existing_routing(
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    routing_request = RecordingRoutingRequest(
        AgentColRoutingDirective(route="direct")
    )
    executor = RecordingExecutor()
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=routing_request,
    )

    streamed = [
        event
        async for event in service.stream_turn(
            AgentColTurnCommand(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Help with this design.",
            )
        )
    ]

    assert [event.text for event in streamed[:-1]] == [
        "Agent_Col ",
        "response.",
    ]
    assert streamed[-1].result.response == "Agent_Col response."
    assert len(routing_request.calls) == 1
    assert len(executor.calls) == 1
    assert len(responder.contexts) == 1


@pytest.mark.asyncio
async def test_turn_service_streams_after_artifact_routing_and_execution(
) -> None:
    from agent_col_routing_v4 import (
        AgentColRoutingDirective as AgentColRoutingDirectiveV4,
    )
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService
    from chat_turns import ChatTurnClaim, ChatTurnRequest, derive_chat_turn_ids

    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Create a timer artifact.",
        ),
        ids=derive_chat_turn_ids("artifact-stream-key"),
        owner_token="owner-token",
        lease_expires_at=datetime(2026, 8, 24, tzinfo=UTC),
        resumed=False,
    )
    artifact_routing = RecordingRoutingRequest(
        AgentColRoutingDirectiveV4.model_validate(
            {
                "schema_version": "4.0",
                "route": "artifact",
                "artifact_intent": {
                    "operation": "create_blueprint",
                    "objective": "Create the requested artifact.",
                },
            }
        )
    )
    artifact_executor = RecordingArtifactExecutor()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=RecordingResponder(),
        routing_request=RecordingRoutingRequest(
            AgentColRoutingDirective(route="direct")
        ),
        artifact_executor=artifact_executor,
        artifact_routing_request=artifact_routing,
    )

    streamed = [
        event
        async for event in service.stream_turn(
            AgentColTurnCommand(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Create a timer artifact.",
                chat_turn_claim=claim,
            )
        )
    ]

    assert [event.text for event in streamed[:-1]] == [
        "Agent_Col ",
        "response.",
    ]
    assert streamed[-1].result.artifacts[0].artifact_id == "artifact-1"
    assert len(artifact_routing.calls) == 1
    assert len(artifact_executor.calls) == 1


@pytest.mark.asyncio
async def test_turn_service_closing_stream_cancels_in_flight_responder() -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    class BlockingResponder(RecordingResponder):
        def __init__(self) -> None:
            super().__init__(deltas=())
            self.cancelled = False

        async def stream_turn(self, context: object):
            self.contexts.append(context)
            yield SupervisorTextDelta(text="Provisional")
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    responder = BlockingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(
            AgentColRoutingDirective(route="direct")
        ),
    )
    stream = service.stream_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Help with this design.",
        )
    )

    first = await anext(stream)
    await stream.aclose()

    assert first.text == "Provisional"
    assert responder.cancelled is True


@pytest.mark.asyncio
async def test_turn_service_projects_only_minimal_routing_input() -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    routing_client = object()
    routing_request = RecordingRoutingRequest(
        AgentColRoutingDirective(route="direct")
    )
    executor = RecordingExecutor()
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=routing_client,
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=routing_request,
    )
    command = AgentColTurnCommand(
        project_id="private-project",
        session_id="private-session",
        user_id="private-user",
        message=(
            "Compare https://example.com/current and answer concisely."
        ),
        recent_user_messages=(
            "Old context with https://example.com/old and private-history.",
            "New context with https://example.com/new and private-recent.",
        ),
        model_input_context=(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text="private-profile-value")],
            ),
        ),
        source_message_id="private-message-id",
        memory_decision_present=True,
        turn_lease=ProposalTurnLease(
            turn_id="a" * 64,
            owner_token="private-owner-token",
        ),
        precompleted_actions=(
            AgentActionReceipt(
                action_name="approve_memory_signal",
                status="completed",
            ),
        ),
        precompleted_memory_proposals=(
            MemoryProposalReceipt(
                proposal_id="response_length--proposal-1",
                category="response_length",
                proposed_value="concise",
                expires_at=datetime(2026, 8, 23, tzinfo=UTC),
            ),
        ),
    )

    result = await service.run_turn(command)

    assert result.response == "Agent_Col response."
    assert len(routing_request.calls) == 1
    call = routing_request.calls[0]
    assert call["client"] is routing_client
    assert call["timeout_seconds"] == 15.0
    routing_input = call["routing_input"]
    assert routing_input.current_message == command.message
    assert tuple(
        (
            candidate.candidate_id,
            str(candidate.url),
            candidate.source,
        )
        for candidate in routing_input.candidate_urls
    ) == (
        ("url-1", "https://example.com/current", "current_message"),
        ("url-2", "https://example.com/new", "recent_user_history"),
        ("url-3", "https://example.com/old", "recent_user_history"),
    )
    assert routing_input.available_capabilities == ("source", "research")
    serialized = routing_input.model_dump_json()
    for forbidden in (
        "private-project",
        "private-session",
        "private-user",
        "private-history",
        "private-recent",
        "private-profile-value",
        "private-message-id",
        "a" * 64,
        "private-owner-token",
        "approve_memory_signal",
        "response_length--proposal-1",
    ):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_turn_service_bounds_recent_user_messages_for_v4_routing(
) -> None:
    from agent_col_routing_v4 import (
        AgentColRoutingDirective as AgentColRoutingDirectiveV4,
    )
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService
    from chat_turns import ChatTurnClaim, ChatTurnRequest, derive_chat_turn_ids

    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Turn this into a checklist.",
        ),
        ids=derive_chat_turn_ids("long-history-routing-key"),
        owner_token="owner-token",
        lease_expires_at=datetime(2026, 8, 24, tzinfo=UTC),
        resumed=False,
    )
    artifact_directive = AgentColRoutingDirectiveV4.model_validate(
        {
            "schema_version": "4.0",
            "route": "artifact",
            "artifact_intent": {
                "operation": "create_blueprint",
                "objective": "Create the requested checklist.",
            },
        }
    )
    artifact_routing = RecordingRoutingRequest(artifact_directive)
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=RecordingResponder(),
        artifact_executor=RecordingArtifactExecutor(),
        artifact_routing_request=artifact_routing,
    )
    recent_messages = tuple(f"Message {index}" for index in range(25))

    await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Turn this into a checklist.",
            recent_user_messages=recent_messages,
            chat_turn_claim=claim,
        )
    )

    routing_input = artifact_routing.calls[0]["routing_input"]
    assert routing_input.recent_user_messages == recent_messages[-10:]


@pytest.mark.asyncio
async def test_turn_service_v3_projects_current_message_numeric_candidates(
) -> None:
    from agent_col_responder_context_v3 import AgentColResponderContextV3
    from agent_col_routing_v3 import AgentColRoutingDirective
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    class V3Executor:
        available_capabilities = ("source", "research", "computation")

        def __init__(self) -> None:
            self.calls: list[tuple[object, object]] = []

        async def execute(self, directive, routing_input):
            self.calls.append((directive, routing_input))
            return AgentColResponderContextV3(
                routing_directive=directive
            )

    routing_request = RecordingRoutingRequest(
        AgentColRoutingDirective(route="direct")
    )
    executor = V3Executor()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=RecordingResponder(),
        routing_request=routing_request,
    )
    command = AgentColTurnCommand(
        project_id="private-project",
        session_id="private-session",
        user_id="private-user",
        message="Calculate $12 plus 15% and 20.",
        recent_user_messages=("Earlier value 999 must stay private.",),
    )

    await service.run_turn(command)

    routing_input = routing_request.calls[0]["routing_input"]
    assert routing_input.model_dump(mode="json") == {
        "current_message": "Calculate $12 plus 15% and 20.",
        "candidate_urls": [],
        "numeric_candidates": [
            {
                "candidate_id": "number-1",
                "raw_text": "$12",
                "value": 12.0,
                "notation": "currency",
                "unit_symbol": "$",
                "start_index": 10,
                "end_index": 13,
            },
            {
                "candidate_id": "number-2",
                "raw_text": "15%",
                "value": 15.0,
                "notation": "percent",
                "unit_symbol": "%",
                "start_index": 19,
                "end_index": 22,
            },
            {
                "candidate_id": "number-3",
                "raw_text": "20",
                "value": 20.0,
                "notation": "plain",
                "unit_symbol": None,
                "start_index": 27,
                "end_index": 29,
            },
        ],
        "numeric_projection_incomplete": False,
        "text_block_candidates": [
            {
                "candidate_id": "block-1",
                "text": "Calculate $12 plus 15% and 20.",
                "start_index": 0,
                "end_index": 30,
                "structural_kind": "paragraph",
            }
        ],
        "text_projection_incomplete": False,
        "available_capabilities": ["source", "research", "computation"],
    }
    assert "999" not in routing_input.model_dump_json()
    assert len(executor.calls) == 1


@pytest.mark.asyncio
async def test_turn_service_projects_v3_current_message_text_blocks_only(
) -> None:
    from agent_col_responder_context_v3 import AgentColResponderContextV3
    from agent_col_routing_v3 import AgentColRoutingDirective as V3Directive
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    class V3Executor:
        available_capabilities = (
            "source",
            "research",
            "computation",
            "requirements_verification",
        )

        def __init__(self) -> None:
            self.calls: list[tuple[object, object]] = []

        async def execute(self, directive, routing_input):
            self.calls.append((directive, routing_input))
            return AgentColResponderContextV3(
                routing_directive=directive
            )

    message = (
        "Compare the draft against every requirement.\n\n"
        "Requirements:\n"
        "- Include one practical example.\n"
        "- State one material limitation.\n\n"
        "Subject:\n"
        "The draft includes one practical example but states no limitation."
    )
    routing_request = RecordingRoutingRequest(V3Directive(route="direct"))
    executor = V3Executor()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=RecordingResponder(),
        routing_request=routing_request,
    )

    await service.run_turn(
        AgentColTurnCommand(
            project_id="private-project",
            session_id="private-session",
            user_id="private-user",
            message=message,
            recent_user_messages=(
                "Private history must not become verification input.",
            ),
            model_input_context=(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="private-profile")],
                ),
            ),
        )
    )

    routing_input = routing_request.calls[0]["routing_input"]
    payload = routing_input.model_dump(mode="json")
    assert payload.get("text_projection_incomplete") is False
    assert [
        (candidate["candidate_id"], candidate["text"])
        for candidate in payload.get("text_block_candidates", [])
    ] == [
        ("block-1", "Compare the draft against every requirement."),
        ("block-2", "Requirements:"),
        ("block-3", "- Include one practical example."),
        ("block-4", "- State one material limitation."),
        ("block-5", "Subject:"),
        (
            "block-6",
            "The draft includes one practical example but states no "
            "limitation.",
        ),
    ]
    assert payload["available_capabilities"] == [
        "source",
        "research",
        "computation",
        "requirements_verification",
    ]
    serialized = routing_input.model_dump_json()
    for excluded in (
        "private-project",
        "private-session",
        "private-user",
        "Private history",
        "private-profile",
    ):
        assert excluded not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_error", "expected_error_name"),
    (
        (RuntimeError("private-provider-payload"), "routing"),
        (TimeoutError("private-timeout-payload"), "routing_timeout"),
    ),
)
async def test_turn_service_stops_after_safe_routing_failure(
    provider_error: Exception,
    expected_error_name: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from agent_col_routing_v3 import RoutingDirectiveInputError
    from agent_col_routing_provider_v3 import (
        AgentColRoutingV3InvalidOutputReason,
        AgentColRoutingV3ProviderError,
        AgentColRoutingV3ProviderOutputError,
        AgentColRoutingV3ProviderTimeoutError,
    )
    from agent_col_turn_service import (
        AgentColTurnRoutingError,
        AgentColTurnRoutingTimeoutError,
        AgentColTurnService,
    )

    if type(provider_error) is RuntimeError:
        provider_error = AgentColRoutingV3ProviderError(
            "private-provider-payload"
        )
    elif type(provider_error) is TimeoutError:
        provider_error = AgentColRoutingV3ProviderTimeoutError(
            "private-timeout-payload"
        )
    else:
        provider_error = AgentColRoutingV3ProviderOutputError(
            AgentColRoutingV3InvalidOutputReason.SCHEMA_VALIDATION_FAILED
        )
    assert not isinstance(provider_error, RoutingDirectiveInputError)
    expected_error = (
        AgentColTurnRoutingTimeoutError
        if expected_error_name == "routing_timeout"
        else AgentColTurnRoutingError
    )
    routing_request = RecordingRoutingRequest(error=provider_error)
    executor = RecordingExecutor()
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=routing_request,
    )
    command = command_with_precompleted_effects()

    with pytest.raises(expected_error) as captured:
        await service.run_turn(command)

    assert captured.value.__cause__ is provider_error
    assert captured.value.actions == command.precompleted_actions
    assert (
        captured.value.memory_proposals
        == command.precompleted_memory_proposals
    )
    assert len(routing_request.calls) == 1
    assert executor.calls == []
    assert responder.contexts == []
    for secret in (
        "private-provider-payload",
        "private-timeout-payload",
        "secret-message-content",
        "secret-project",
        "secret-session",
        "secret-user",
        "response_length--proposal-2",
    ):
        assert secret not in str(captured.value)
        assert secret not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_error",
    (
        pytest.param(
            "invalid_output",
            id="invalid-output",
        ),
        pytest.param(
            "directive_mismatch",
            id="directive-input-mismatch",
        ),
    ),
)
async def test_turn_service_classifies_invalid_routing_without_downstream_access(
    provider_error: str,
) -> None:
    from agent_col_routing_v3 import RoutingDirectiveInputError
    from agent_col_routing_provider_v3 import (
        AgentColRoutingV3InvalidOutputReason,
        AgentColRoutingV3ProviderOutputError,
    )
    from agent_col_turn_service import (
        AgentColTurnRoutingError,
        AgentColTurnService,
    )

    error = (
        AgentColRoutingV3ProviderOutputError(
            AgentColRoutingV3InvalidOutputReason.SCHEMA_VALIDATION_FAILED
        )
        if provider_error == "invalid_output"
        else RoutingDirectiveInputError("private-directive-mismatch")
    )
    executor = RecordingExecutor()
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(error=error),
    )

    with pytest.raises(AgentColTurnRoutingError) as captured:
        await service.run_turn(command_with_precompleted_effects())

    assert captured.value.__cause__ is error
    assert executor.calls == []
    assert responder.contexts == []


@pytest.mark.asyncio
async def test_turn_service_logs_allowlisted_routing_input_reason_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from agent_col_routing_v3 import (
        RoutingDirectiveInputError,
        RoutingDirectiveInputReason,
    )
    from agent_col_turn_service import (
        AgentColTurnRoutingError,
        AgentColTurnService,
    )

    error = RoutingDirectiveInputError(
        RoutingDirectiveInputReason.UNKNOWN_NUMERIC_CANDIDATE
    )
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=RecordingResponder(),
        routing_request=RecordingRoutingRequest(error=error),
    )

    with pytest.raises(AgentColTurnRoutingError):
        await service.run_turn(command_with_precompleted_effects())

    assert (
        "routing_directive_input:unknown_numeric_candidate" in caplog.text
    )
    for secret in (
        "secret-message-content",
        "secret-project",
        "secret-session",
        "secret-user",
        "number-33",
    ):
        assert secret not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("directive", "responder_context"),
    (
        (
            AgentColRoutingDirective(route="direct"),
            AgentColResponderContext(
                routing_directive=AgentColRoutingDirective(route="direct")
            ),
        ),
        (
            AgentColRoutingDirective(
                route="clarify",
                clarifying_question="Which public page should I analyze?",
            ),
            AgentColResponderContext(
                routing_directive=AgentColRoutingDirective(
                    route="clarify",
                    clarifying_question=(
                        "Which public page should I analyze?"
                    ),
                )
            ),
        ),
        (
            AgentColRoutingDirective(
                route="source",
                source_intent={
                    "objective": "Analyze the selected page.",
                    "selected_url_ids": ["url-1"],
                },
            ),
            AgentColResponderContext(
                routing_directive=AgentColRoutingDirective(
                    route="source",
                    source_intent={
                        "objective": "Analyze the selected page.",
                        "selected_url_ids": ["url-1"],
                    },
                ),
                expert_result={
                    "capability": "source",
                    "status": "unavailable",
                },
            ),
        ),
        (
            AgentColRoutingDirective(
                route="research",
                research_intent={
                    "question": "What is current?",
                    "objective": "Find current public evidence.",
                },
            ),
            AgentColResponderContext(
                routing_directive=AgentColRoutingDirective(
                    route="research",
                    research_intent={
                        "question": "What is current?",
                        "objective": "Find current public evidence.",
                    },
                ),
                expert_result={
                    "capability": "research",
                    "status": "unavailable",
                },
            ),
        ),
    ),
)
async def test_turn_service_composes_each_route_into_responder_context(
    directive: AgentColRoutingDirective,
    responder_context: AgentColResponderContext,
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    original_context = types.Content(
        role="user",
        parts=[types.Part.from_text(text="existing-context")],
    )
    lease = ProposalTurnLease(
        turn_id="b" * 64,
        owner_token="owner-token",
    )
    command = AgentColTurnCommand(
        project_id="project-1",
        session_id="session-1",
        user_id="user-1",
        message=(
            "Current user request https://example.com/current-page"
        ),
        model_input_context=(original_context,),
        source_message_id="message-1",
        memory_decision_present=True,
        turn_lease=lease,
    )
    routing_request = RecordingRoutingRequest(directive)
    executor = RecordingExecutor(responder_context)
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=routing_request,
    )

    result = await service.run_turn(command)

    assert result.response == "Agent_Col response."
    assert len(executor.calls) == 1
    routed_directive, routed_input = executor.calls[0]
    assert routed_directive is directive
    assert routed_input is routing_request.calls[0]["routing_input"]
    assert len(responder.contexts) == 1
    runtime_context = responder.contexts[0]
    assert runtime_context.project_id == command.project_id
    assert runtime_context.session_id == command.session_id
    assert runtime_context.user_id == command.user_id
    assert runtime_context.message == command.message
    assert runtime_context.source_message_id == command.source_message_id
    assert runtime_context.memory_decision_present is True
    assert runtime_context.turn_lease is lease
    assert runtime_context.model_input_context[0] is original_context
    assert len(runtime_context.model_input_context) == 2
    routed_context = runtime_context.model_input_context[1]
    routed_text = routed_context.parts[0].text
    assert routed_text is not None
    assert command.message not in routed_text
    assert responder_context.model_dump_json() in routed_text


@pytest.mark.asyncio
async def test_turn_service_injects_hidden_working_state_for_responder(
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    directive = AgentColRoutingDirective(route="direct")
    original_context = types.Content(
        role="user",
        parts=[types.Part.from_text(text="existing-context")],
    )
    working_state_context = (
        "[SERVER_VALIDATED_WORKING_STATE]\n"
        "hidden internal working state\n"
        "{\"current_goal\":\"Choose deployment plan\"}\n"
        "[/SERVER_VALIDATED_WORKING_STATE]"
    )
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(directive),
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Actually, artifact generation only takes ten seconds.",
            model_input_context=(original_context,),
            working_state_context=working_state_context,
        )
    )

    assert result.response == "Agent_Col response."
    assert result.actions == ()
    assert result.artifacts == ()
    assert result.memory_proposals == ()
    assert result.collaborative_note_proposals == ()
    assert result.continuity_receipts == ()
    runtime_context = responder.contexts[0]
    assert runtime_context.model_input_context[0] is original_context
    assert runtime_context.model_input_context[1].parts[0].text == (
        working_state_context
    )
    routed_context_text = runtime_context.model_input_context[2].parts[0].text
    assert routed_context_text is not None
    assert "[SERVER_VALIDATED_ROUTING_AND_EXPERT_RESULT]" in routed_context_text


def test_responder_instruction_defines_hidden_working_state_policy() -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    instruction = " ".join(RESPONDER_INSTRUCTION.split())

    assert "SERVER_VALIDATED_WORKING_STATE" in instruction
    assert "same-session" in instruction
    assert "non-authoritative" in instruction
    assert "current user" in instruction
    assert "approved memory" in instruction
    assert "workspace notes" in instruction
    assert "persisted artifacts" in instruction
    assert "routing" in instruction
    assert "blocking" in instruction
    assert "clarifying question" in instruction
    assert "assumptions" in instruction
    assert "options" in instruction
    assert "incomplete instructions" in instruction
    assert "Continue from the current" in instruction
    assert "Never expose" in instruction


def test_responder_instruction_treats_unresolved_working_state_questions_as_unsettled() -> None:
    from agent_col_responder import RESPONDER_INSTRUCTION

    instruction = " ".join(RESPONDER_INSTRUCTION.split())

    assert "Unresolved working-state questions are not facts" in instruction
    assert "facts, assumptions, and open decisions" in instruction
    assert "challenge missing details" in instruction
    assert "guide the user toward a decision" in instruction
    assert "Do not turn unresolved questions into examples" in instruction
    assert "settled platform" in instruction
    assert "source-backed" in instruction
    assert "validated routing" in instruction
    assert "assumption" in instruction
    assert "option" in instruction
    assert "open decision" in instruction


def completed_source_context() -> AgentColResponderContext:
    from source_expert import SourceExpertResult, build_source_receipts

    directive = AgentColRoutingDirective(
        route="source",
        source_intent={
            "objective": "Explain the selected page.",
            "selected_url_ids": ["url-1"],
        },
    )
    result = SourceExpertResult.model_validate(
        {
            "status": "completed",
            "summary": "The page provides grounded documentation evidence.",
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


def completed_requirements_verification_context():
    from agent_col_responder_context_v3 import AgentColResponderContextV3
    from agent_col_routing_v3 import AgentColRoutingDirective as V3Directive
    from requirements_verification import (
        RequirementAssessment,
        RequirementStatusCounts,
        RequirementsVerificationEvidence,
        RequirementsVerificationPayload,
        RequirementsVerificationResult,
        SubjectEvidence,
        build_requirements_verification_receipts,
    )

    directive = V3Directive(
        route="requirements_verification",
        requirements_verification_intent={
            "objective": "Assess every requirement against the draft.",
            "requirement_block_ids": ["block-3", "block-4"],
            "subject_block_ids": ["block-6"],
        },
    )
    result = RequirementsVerificationResult(
        status="completed",
        summary="Requirements verification completed for 2 requirements.",
        payload=RequirementsVerificationPayload(
            assessments=(
                RequirementAssessment(
                    requirement_id="REQ-001",
                    requirement_text="Include one practical example.",
                    status="covered",
                    evidence=(
                        SubjectEvidence(
                            subject_block_id="SUBJECT-001",
                            excerpt="includes one practical example",
                            explanation="The subject addresses the requirement.",
                        ),
                    ),
                ),
                RequirementAssessment(
                    requirement_id="REQ-002",
                    requirement_text="State one material limitation.",
                    status="contradictory",
                    evidence=(
                        SubjectEvidence(
                            subject_block_id="SUBJECT-001",
                            excerpt="states no limitation",
                            explanation="The subject contradicts the requirement.",
                        ),
                    ),
                    gap="The required limitation is absent.",
                    recommended_action="State one material limitation.",
                ),
            ),
            counts=RequirementStatusCounts(
                covered=1,
                partial=0,
                missing=0,
                contradictory=1,
                unsupported=0,
            ),
        ),
        evidence=RequirementsVerificationEvidence(
            requirement_count=2,
            assessed_requirement_count=2,
            validated_evidence_count=2,
            referenced_subject_block_ids=("SUBJECT-001",),
        ),
    )
    receipts = build_requirements_verification_receipts(result)
    return AgentColResponderContextV3(
        routing_directive=directive,
        expert_result=result,
        actions=receipts.actions,
        citations=receipts.citations,
    )


@pytest.mark.asyncio
async def test_turn_service_projects_completed_verification_to_responder(
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    context = completed_requirements_verification_context()

    class VerificationExecutor(RecordingExecutor):
        available_capabilities = ("requirements_verification",)

    executor = VerificationExecutor(context)
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(context.routing_directive),
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message=(
                "Compare the draft against every requirement.\n\n"
                "Requirements:\n"
                "- Include one practical example.\n"
                "- State one material limitation.\n\n"
                "Subject:\n"
                "The draft includes one practical example but states no "
                "limitation."
            ),
        )
    )

    assert len(executor.calls) == 1
    assert result.actions == context.actions
    assert result.actions[0].action_name == "verify_requirements"
    assert result.citations == ()
    responder_text = responder.contexts[0].model_input_context[-1].parts[0].text
    assert responder_text is not None
    assert '"requirement_id":"REQ-001"' in responder_text
    assert "evidence-backed assessment, not a certification" in responder_text


@pytest.mark.asyncio
async def test_turn_service_stably_merges_authoritative_receipts() -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService
    from schemas import ArtifactReference, CitationReference

    expert_context = completed_source_context()
    precompleted_action = AgentActionReceipt(
        action_name="approve_memory_signal",
        status="completed",
    )
    proposal_action = AgentActionReceipt(
        action_name="propose_memory_signal",
        status="completed",
    )
    proposal = MemoryProposalReceipt(
        proposal_id="response_length--proposal-3",
        category="response_length",
        proposed_value="concise",
        expires_at=datetime(2026, 8, 23, tzinfo=UTC),
    )
    artifact = ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id="project-1",
        artifact_id="artifact-1",
        schema_version="2.0",
        display_label="Project blueprint",
    )
    responder_citation = CitationReference(
        uri="https://example.org/",
        label="Responder application citation",
    )
    responder_result = SupervisorTurnResult(
        response="Integrated final response.",
        actions=(
            precompleted_action,
            proposal_action,
            *expert_context.actions,
        ),
        artifacts=(artifact,),
        citations=(*expert_context.citations, responder_citation),
        memory_proposals=(proposal,),
    )
    executor = RecordingExecutor(expert_context)
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=RecordingResponder(responder_result),
        routing_request=RecordingRoutingRequest(
            expert_context.routing_directive
        ),
    )
    command = AgentColTurnCommand(
        project_id="project-1",
        session_id="session-1",
        user_id="user-1",
        message="Explain https://example.com/ using the supplied page.",
        precompleted_actions=(precompleted_action,),
        precompleted_memory_proposals=(proposal,),
    )

    result = await service.run_turn(command)

    assert result.response == "Integrated final response."
    assert result.actions == (
        precompleted_action,
        *expert_context.actions,
        proposal_action,
    )
    assert result.artifacts == (artifact,)
    assert result.citations == (
        *expert_context.citations,
        responder_citation,
    )
    assert result.memory_proposals == (proposal,)


@pytest.mark.asyncio
async def test_turn_service_preserves_continuity_receipts_on_success() -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    receipt = continuity_receipt()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=RecordingResponder(),
        routing_request=RecordingRoutingRequest(
            AgentColRoutingDirective(route="direct")
        ),
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Use the saved note.",
            continuity_receipts=(receipt,),
        )
    )

    assert result.continuity_receipts == (receipt,)


@pytest.mark.asyncio
async def test_turn_service_resolved_continuity_overrides_clarify_route(
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    receipt = continuity_receipt()
    continuity_context = types.Content(
        role="user",
        parts=[
            types.Part.from_text(
                text=(
                    "[SERVER_VALIDATED_CONTINUITY_CONTEXT]\n"
                    "Title: Project Language: TypeScript\n"
                    "Body: The project will be written in TypeScript.\n"
                    "[/SERVER_VALIDATED_CONTINUITY_CONTEXT]"
                )
            )
        ],
    )
    clarify_directive = AgentColRoutingDirective(
        route="clarify",
        clarifying_question=(
            "Which project or context are you referring to?"
        ),
    )
    routing_request = RecordingRoutingRequest(clarify_directive)
    executor = RecordingExecutor()
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=routing_request,
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message=(
                "hey col what language was that project we are working on "
                "written in"
            ),
            model_input_context=(continuity_context,),
            continuity_receipts=(receipt,),
        )
    )

    assert result.continuity_receipts == (receipt,)
    routed_directive, _ = executor.calls[0]
    assert routed_directive.route is AgentColRoute.DIRECT
    responder_context = responder.contexts[0]
    routed_context_text = responder_context.model_input_context[-1].parts[
        0
    ].text
    assert routed_context_text is not None
    assert '"route":"direct"' in routed_context_text
    assert '"route":"clarify"' not in routed_context_text
    assert "Which project or context are you referring to?" not in (
        routed_context_text
    )


@pytest.mark.asyncio
async def test_turn_service_preserves_memory_clarification_receipt() -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    clarification = memory_clarification_receipt()
    responder = RecordingResponder(
        SupervisorTurnResult(
            response="Please choose which preference you meant.",
            memory_clarifications=(clarification,),
        )
    )
    directive = AgentColRoutingDirective(route="direct")
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(directive),
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Please remember that I prefer detailed guidance.",
        )
    )

    assert result.memory_clarifications == (clarification,)


@pytest.mark.asyncio
async def test_failed_expert_context_adds_no_cognitive_receipt() -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    directive = AgentColRoutingDirective(
        route="research",
        research_intent={
            "question": "What is current?",
            "objective": "Find current public evidence.",
        },
    )
    failed_context = AgentColResponderContext(
        routing_directive=directive,
        expert_result={
            "capability": "research",
            "status": "unavailable",
        },
    )
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(failed_context),
        responder_runtime=RecordingResponder(),
        routing_request=RecordingRoutingRequest(directive),
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Find current public evidence.",
        )
    )

    assert result.actions == ()
    assert result.citations == ()


@pytest.mark.asyncio
async def test_executor_configuration_failure_is_content_safe_and_stops_responder(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from agent_col_expert_executor_v3 import (
        AgentColExpertExecutorV3ConfigurationError,
    )
    from agent_col_turn_service import (
        AgentColTurnCommand,
        AgentColTurnService,
        AgentColTurnServiceError,
    )

    executor_error = AgentColExpertExecutorV3ConfigurationError(
        "private-executor-configuration"
    )

    class ConfigurationFailingExecutor(RecordingExecutor):
        async def execute(
            self,
            directive: AgentColRoutingDirective,
            routing_input: object,
        ) -> AgentColResponderContext:
            self.calls.append((directive, routing_input))
            raise executor_error

    executor = ConfigurationFailingExecutor()
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(
            AgentColRoutingDirective(route="direct")
        ),
    )
    command = AgentColTurnCommand(
        project_id="private-project-executor",
        session_id="private-session-executor",
        user_id="private-user-executor",
        message="private-message-executor",
    )

    with pytest.raises(AgentColTurnServiceError) as captured:
        await service.run_turn(command)

    assert captured.value.__cause__ is executor_error
    assert len(executor.calls) == 1
    assert responder.contexts == []
    for secret in (
        "private-executor-configuration",
        "private-project-executor",
        "private-session-executor",
        "private-user-executor",
        "private-message-executor",
    ):
        assert secret not in str(captured.value)
        assert secret not in caplog.text


@pytest.mark.asyncio
async def test_stream_turn_stops_before_responder_on_specialist_failure() -> None:
    from agent_col_expert_executor_v3 import (
        AgentColExpertExecutorV3ConfigurationError,
    )
    from agent_col_turn_service import (
        AgentColTurnCommand,
        AgentColTurnService,
        AgentColTurnServiceError,
    )

    executor_error = AgentColExpertExecutorV3ConfigurationError(
        "private-specialist-configuration"
    )

    class ConfigurationFailingExecutor(RecordingExecutor):
        async def execute(
            self,
            directive: AgentColRoutingDirective,
            routing_input: object,
        ) -> AgentColResponderContext:
            self.calls.append((directive, routing_input))
            raise executor_error

    executor = ConfigurationFailingExecutor()
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(
            AgentColRoutingDirective(route="direct")
        ),
    )

    with pytest.raises(AgentColTurnServiceError) as captured:
        _ = [
            event
            async for event in service.stream_turn(
                AgentColTurnCommand(
                    project_id="private-project",
                    session_id="private-session",
                    user_id="private-user",
                    message="private-message",
                )
            )
        ]

    assert captured.value.__cause__ is executor_error
    assert len(executor.calls) == 1
    assert responder.contexts == []
    assert "private-specialist-configuration" not in str(captured.value)


@pytest.mark.asyncio
async def test_stream_turn_limits_recent_user_messages_for_url_projection(
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    routing = RecordingRoutingRequest(AgentColRoutingDirective(route="direct"))
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=RecordingResponder(),
        routing_request=routing,
    )
    recent_messages = (
        "Older URL https://old.example.com/reference",
        "Another older URL https://older.example.com/reference",
        *(f"recent message {index} without a URL" for index in range(10)),
    )

    events = [
        event
        async for event in service.stream_turn(
            AgentColTurnCommand(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Summarize the current request.",
                recent_user_messages=recent_messages,
            )
        )
    ]

    assert len(routing.calls) == 1
    routing_input = routing.calls[0]["routing_input"]
    assert routing_input.candidate_urls == ()
    assert events[-1].result.response == "Agent_Col response."


@pytest.mark.asyncio
async def test_responder_failure_preserves_only_trusted_partial_effects(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from agent_col_turn_service import (
        AgentColTurnCommand,
        AgentColTurnResponderError,
        AgentColTurnService,
    )
    from supervisor_runtime import SupervisorRuntimeError

    expert_context = completed_source_context()
    precompleted_action = AgentActionReceipt(
        action_name="approve_memory_signal",
        status="completed",
    )
    proposal_action = AgentActionReceipt(
        action_name="propose_memory_signal",
        status="completed",
    )
    proposal = MemoryProposalReceipt(
        proposal_id="response_length--proposal-4",
        category="response_length",
        proposed_value="concise",
        expires_at=datetime(2026, 8, 23, tzinfo=UTC),
    )
    runtime_error = SupervisorRuntimeError(
        "private-responder-output",
        actions=(precompleted_action, proposal_action),
        memory_proposals=(proposal,),
    )
    executor = RecordingExecutor(expert_context)
    responder = RecordingResponder(error=runtime_error)
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(
            expert_context.routing_directive
        ),
    )
    command = AgentColTurnCommand(
        project_id="private-project-r5",
        session_id="private-session-r5",
        user_id="private-user-r5",
        message="private-message-r5 https://example.com/",
        precompleted_actions=(precompleted_action,),
        precompleted_memory_proposals=(proposal,),
    )

    with pytest.raises(AgentColTurnResponderError) as captured:
        await service.run_turn(command)

    assert captured.value.__cause__ is runtime_error
    assert captured.value.actions == (
        precompleted_action,
        *expert_context.actions,
        proposal_action,
    )
    assert captured.value.memory_proposals == (proposal,)
    assert len(executor.calls) == 1
    assert len(responder.contexts) == 1
    for secret in (
        "private-responder-output",
        "private-project-r5",
        "private-session-r5",
        "private-user-r5",
        "private-message-r5",
        "response_length--proposal-4",
    ):
        assert secret not in str(captured.value)
        assert secret not in caplog.text


@pytest.mark.asyncio
async def test_responder_failure_preserves_memory_clarification_receipt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from agent_col_turn_service import (
        AgentColTurnCommand,
        AgentColTurnResponderError,
        AgentColTurnService,
    )
    from supervisor_runtime import SupervisorRuntimeError

    clarification = memory_clarification_receipt()
    runtime_error = SupervisorRuntimeError(
        "private-responder-output",
        memory_clarifications=(clarification,),
    )
    responder = RecordingResponder(error=runtime_error)
    directive = AgentColRoutingDirective(route="direct")
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(directive),
    )

    with pytest.raises(AgentColTurnResponderError) as captured:
        await service.run_turn(
            AgentColTurnCommand(
                project_id="private-project",
                session_id="private-session",
                user_id="private-user",
                message="private-message",
            )
        )

    assert captured.value.memory_clarifications == (clarification,)
    assert "private-responder-output" not in str(captured.value)
    assert "private-responder-output" not in caplog.text


@pytest.mark.asyncio
async def test_responder_reserve_prevents_expert_start_without_budget() -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    directive = AgentColRoutingDirective(
        route="source",
        source_intent={
            "objective": "Analyze the selected page.",
            "selected_url_ids": ["url-1"],
        },
    )
    executor = RecordingExecutor(completed_source_context())
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(directive),
        clock=SequenceClock(0.0, 0.0, 70.0, 70.0),
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Analyze https://example.com/ before time expires.",
        )
    )

    assert executor.calls == []
    assert result.actions == ()
    assert result.citations == ()
    assert len(responder.contexts) == 1
    runtime_context = responder.contexts[0]
    routed_text = runtime_context.model_input_context[-1].parts[0].text
    assert routed_text is not None
    assert '"capability":"source"' in routed_text
    assert '"status":"timed_out"' in routed_text
    assert '"actions":[]' in routed_text
    assert '"citations":[]' in routed_text


@pytest.mark.asyncio
async def test_expert_starts_when_time_exceeds_responder_reserve() -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    expert_context = completed_source_context()
    directive = expert_context.routing_directive
    executor = RecordingExecutor(expert_context)
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=RecordingResponder(),
        routing_request=RecordingRoutingRequest(directive),
        clock=SequenceClock(0.0, 0.0, 69.0, 69.0),
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Analyze https://example.com/ with one second available.",
        )
    )

    assert len(executor.calls) == 1
    assert result.actions == expert_context.actions
    assert result.citations == expert_context.citations


@pytest.mark.asyncio
async def test_artifact_turn_projects_recent_user_context_into_source_text(
) -> None:
    from agent_col_routing_v4 import (
        AgentColRoutingDirective as AgentColRoutingDirectiveV4,
    )
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService
    from chat_turns import ChatTurnClaim, ChatTurnRequest, derive_chat_turn_ids

    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Turn that into a markdown artifact.",
        ),
        ids=derive_chat_turn_ids("artifact-context-key"),
        owner_token="owner-token",
        lease_expires_at=datetime(2026, 8, 24, tzinfo=UTC),
        resumed=False,
    )
    artifact_directive = AgentColRoutingDirectiveV4.model_validate(
        {
            "schema_version": "4.0",
            "route": "artifact",
            "artifact_intent": {
                "operation": "create_blueprint",
                "objective": "Create the requested artifact.",
            },
        }
    )
    artifact_routing = RecordingRoutingRequest(artifact_directive)
    artifact_executor = RecordingArtifactExecutor()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=RecordingResponder(),
        artifact_executor=artifact_executor,
        artifact_routing_request=artifact_routing,
    )

    await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Turn that into a markdown artifact.",
            recent_user_messages=(
                "I need a simple Pomodoro timer with start, pause, reset, "
                "work sessions, and short breaks.",
            ),
            chat_turn_claim=claim,
        )
    )

    routing_input = artifact_routing.calls[0]["routing_input"]
    assert routing_input.recent_user_messages == (
        "I need a simple Pomodoro timer with start, pause, reset, "
        "work sessions, and short breaks.",
    )
    artifact_command = artifact_executor.calls[0]
    assert "[CURRENT_ARTIFACT_REQUEST]" in artifact_command.source_text
    assert "Turn that into a markdown artifact." in artifact_command.source_text
    assert "simple Pomodoro timer" in artifact_command.source_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("directive", "message", "expected_capability"),
    (
        (
            AgentColRoutingDirective(
                route="source",
                source_intent={
                    "objective": "Analyze the supplied page.",
                    "selected_url_ids": ["url-1"],
                },
            ),
            "Analyze https://example.com/.",
            "source",
        ),
        (
            AgentColRoutingDirective(
                route="research",
                research_intent={
                    "question": "What is current?",
                    "objective": "Verify with current evidence.",
                },
            ),
            "Verify the current stable Python release.",
            "research",
        ),
        (
            AgentColRoutingDirective(
                route="computation",
                computation_intent={
                    "objective": "Calculate the mean.",
                    "series_inputs": [
                        {
                            "name": "values",
                            "numeric_ids": ["number-1", "number-2"],
                        }
                    ],
                },
            ),
            "Calculate the mean of 12 and 15.",
            "computation",
        ),
        (
            AgentColRoutingDirective(
                route="requirements_verification",
                requirements_verification_intent={
                    "objective": "Assess every requirement.",
                    "requirement_block_ids": ["block-3"],
                    "subject_block_ids": ["block-5"],
                },
            ),
            (
                "Compare the draft.\n\nRequirements:\n- Include one "
                "example.\n\nSubject:\nThe draft includes one example."
            ),
            "requirements_verification",
        ),
    ),
)
async def test_expert_budget_cancels_with_typed_receipt_free_timeout(
    directive: AgentColRoutingDirective,
    message: str,
    expected_capability: str,
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    executor = BudgetBlockingExecutor()
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(directive),
        turn_timeout_seconds=0.1,
        routing_timeout_seconds=0.02,
        expert_budget_seconds=0.005,
        responder_reserve_seconds=0.02,
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message=message,
        )
    )

    assert len(executor.calls) == 1
    assert executor.cleaned is True
    assert result.actions == ()
    assert result.citations == ()
    assert len(responder.contexts) == 1
    routed_text = responder.contexts[0].model_input_context[-1].parts[0].text
    assert routed_text is not None
    assert f'"capability":"{expected_capability}"' in routed_text
    assert '"status":"timed_out"' in routed_text
    assert '"actions":[]' in routed_text
    assert '"citations":[]' in routed_text


def short_deadline_command(message: str) -> object:
    from agent_col_turn_service import AgentColTurnCommand

    return AgentColTurnCommand(
        project_id="project-1",
        session_id="session-1",
        user_id="user-1",
        message=message,
    )


@pytest.mark.asyncio
async def test_outer_deadline_contains_routing_phase() -> None:
    from agent_col_turn_service import (
        AgentColTurnService,
        AgentColTurnTimeoutError,
    )

    routing = DelayedRoutingRequest(
        AgentColRoutingDirective(route="direct"),
        delay=0.03,
    )
    executor = RecordingExecutor()
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=routing,
        turn_timeout_seconds=0.005,
        expert_budget_seconds=0.001,
        responder_reserve_seconds=0.001,
    )

    with pytest.raises(AgentColTurnTimeoutError):
        await service.run_turn(short_deadline_command("Direct request."))

    assert len(routing.calls) == 1
    assert routing.cleaned is True
    assert executor.calls == []
    assert responder.contexts == []


@pytest.mark.asyncio
async def test_expert_budget_preserves_time_for_responder_phase() -> None:
    from agent_col_turn_service import AgentColTurnService

    expert_context = completed_source_context()
    executor = DelayedExecutor(expert_context, delay=0.03)
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(
            expert_context.routing_directive
        ),
        turn_timeout_seconds=0.01,
        routing_timeout_seconds=0.005,
        expert_budget_seconds=0.001,
        responder_reserve_seconds=0.001,
    )

    result = await service.run_turn(
        short_deadline_command(
            "Analyze https://example.com/ within this turn."
        )
    )

    assert len(executor.calls) == 1
    assert executor.cleaned is True
    assert len(responder.contexts) == 1
    assert result.actions == ()
    assert result.citations == ()
    routed_text = responder.contexts[0].model_input_context[-1].parts[0].text
    assert routed_text is not None
    assert '"capability":"source"' in routed_text
    assert '"status":"timed_out"' in routed_text


@pytest.mark.asyncio
async def test_outer_deadline_contains_responder_phase() -> None:
    from agent_col_turn_service import (
        AgentColTurnService,
        AgentColTurnTimeoutError,
    )

    executor = RecordingExecutor()
    responder = DelayedResponder(delay=0.03)
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=executor,
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(
            AgentColRoutingDirective(route="direct")
        ),
        turn_timeout_seconds=0.005,
        expert_budget_seconds=0.001,
        responder_reserve_seconds=0.001,
    )

    with pytest.raises(AgentColTurnTimeoutError):
        await service.run_turn(short_deadline_command("Direct request."))

    assert len(executor.calls) == 1
    assert len(responder.contexts) == 1
    assert responder.cleaned is True


@pytest.mark.asyncio
async def test_responder_runtime_timeout_uses_turn_timeout_classification() -> None:
    from agent_col_turn_service import (
        AgentColTurnCommand,
        AgentColTurnService,
        AgentColTurnTimeoutError,
    )
    from supervisor_runtime import SupervisorTimeoutError

    runtime_error = SupervisorTimeoutError("private-runtime-timeout")
    receipt = continuity_receipt()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=RecordingResponder(error=runtime_error),
        routing_request=RecordingRoutingRequest(
            AgentColRoutingDirective(route="direct")
        ),
    )

    with pytest.raises(AgentColTurnTimeoutError) as captured:
        await service.run_turn(
            AgentColTurnCommand(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="Direct request.",
                continuity_receipts=(receipt,),
            )
        )

    assert captured.value.__cause__ is runtime_error
    assert captured.value.continuity_receipts == (receipt,)


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_after_responder_cleanup() -> None:
    from agent_col_turn_service import AgentColTurnService

    responder = DelayedResponder(delay=30.0)
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=responder,
        routing_request=RecordingRoutingRequest(
            AgentColRoutingDirective(route="direct")
        ),
    )
    task = asyncio.create_task(
        service.run_turn(short_deadline_command("Direct request."))
    )
    while not responder.contexts:
        await asyncio.sleep(0)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert responder.cleaned is True
    assert len(responder.contexts) == 1


@pytest.mark.parametrize(
    "invalid_setting",
    (
        "turn_timeout_seconds",
        "routing_timeout_seconds",
        "expert_budget_seconds",
        "responder_reserve_seconds",
    ),
)
def test_turn_service_rejects_nonpositive_deadline_settings(
    invalid_setting: str,
) -> None:
    from agent_col_turn_service import AgentColTurnService

    kwargs = {invalid_setting: 0.0}

    with pytest.raises(
        ValueError,
        match=rf"^{invalid_setting} must be positive\.$",
    ):
        AgentColTurnService(
            routing_client=object(),
            expert_executor=RecordingExecutor(),
            responder_runtime=RecordingResponder(),
            **kwargs,
        )


@pytest.mark.asyncio
async def test_routing_timeout_never_exceeds_outer_remainder() -> None:
    from agent_col_turn_service import AgentColTurnService

    routing = RecordingRoutingRequest(
        AgentColRoutingDirective(route="direct")
    )
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExecutor(),
        responder_runtime=RecordingResponder(),
        routing_request=routing,
        turn_timeout_seconds=10.0,
        routing_timeout_seconds=15.0,
        expert_budget_seconds=1.0,
        responder_reserve_seconds=1.0,
        clock=SequenceClock(0.0, 1.0, 1.0, 1.0),
    )

    await service.run_turn(short_deadline_command("Direct request."))

    assert routing.calls[0]["timeout_seconds"] == 9.0
