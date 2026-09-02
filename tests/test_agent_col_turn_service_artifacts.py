from dataclasses import replace
from datetime import UTC, datetime, timedelta
import logging

import pytest
from pydantic import BaseModel, ValidationError

from agent_col_artifact_executor import (
    AgentColArtifactExecutionResult,
    AgentColArtifactResponderProjection,
)
from agent_col_responder_context_v3 import AgentColResponderContextV3
from agent_col_routing_v4 import AgentColRoutingDirective
from chat_turns import ChatTurnClaim, ChatTurnRequest, derive_chat_turn_ids
from schemas import (
    AdaptationReceipt,
    AgentActionReceipt,
    ArtifactReference,
    QueuedActionReceipt,
)
from supervisor_runtime import (
    SupervisorRuntimeError,
    SupervisorTextDelta,
    SupervisorTurnCompleted,
    SupervisorTurnResult,
)


NOW = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
SOURCE_TEXT = (
    "Create a structured blueprint for a collaborative study workflow with "
    "explicit approval and verifiable milestones."
)


def artifact_directive() -> AgentColRoutingDirective:
    return AgentColRoutingDirective.model_validate(
        {
            "schema_version": "4.0",
            "route": "artifact",
            "artifact_intent": {
                "operation": "create_blueprint",
                "objective": "Create the requested structured blueprint.",
            },
        }
    )


def initial_claim() -> ChatTurnClaim:
    return ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="artifact-session",
            user_id="artifact-user",
            message=SOURCE_TEXT,
        ),
        ids=derive_chat_turn_ids("m8-col-4b-artifact-turn"),
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=120),
        resumed=False,
    )


def artifact_receipts(
    claim: ChatTurnClaim,
) -> tuple[
    ChatTurnClaim,
    AgentActionReceipt,
    ArtifactReference,
    AdaptationReceipt,
]:
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    artifact = ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id=claim.request.project_id,
        artifact_id=f"blueprint--{claim.ids.turn_id}",
        schema_version="2.0",
        display_label="Collaborative Study Workflow",
    )
    adaptation = AdaptationReceipt(
        signal_id="example_usage--signal-1",
        category="example_usage",
        value="always_practical",
        source_event_id="example_usage--signal-1--approved",
        status="provided_to_model",
    )
    return (
        replace(
            claim,
            precompleted_actions=(action,),
            precompleted_artifacts=(artifact,),
        ),
        action,
        artifact,
        adaptation,
    )


class RecordingV4RoutingRequest:
    def __init__(self, directive: AgentColRoutingDirective) -> None:
        self.directive = directive
        self.calls: list[tuple[object, object, float]] = []

    async def __call__(
        self,
        client: object,
        routing_input: object,
        *,
        timeout_seconds: float,
    ) -> AgentColRoutingDirective:
        self.calls.append((client, routing_input, timeout_seconds))
        return self.directive


class RecordingExpertExecutor:
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
        return AgentColResponderContextV3(routing_directive=directive)


class RecordingArtifactExecutor:
    def __init__(self, result: AgentColArtifactExecutionResult) -> None:
        self.result = result
        self.commands: list[object] = []
        self.execute_commands: list[object] = []

    async def queue(self, command):
        from agent_col_artifact_executor import AgentColArtifactQueueResult

        self.commands.append(command)
        return AgentColArtifactQueueResult(
            claim=command.claim,
            queued_actions=(
                QueuedActionReceipt(
                    job_id="artifact-job-1",
                    action_kind="create_artifact",
                    status="queued",
                    display_label="Artifact: structured blueprint",
                    created_at=NOW,
                    agent_label="Artifact Builder",
                ),
            ),
        )

    async def execute(self, command):
        self.execute_commands.append(command)
        return self.result


class QueueOnlyArtifactExecutor:
    def __init__(self, queued_action: QueuedActionReceipt) -> None:
        self.queued_action = queued_action
        self.queue_commands: list[object] = []
        self.execute_commands: list[object] = []

    async def queue(self, command):
        from agent_col_artifact_executor import AgentColArtifactQueueResult

        self.queue_commands.append(command)
        return AgentColArtifactQueueResult(
            claim=command.claim,
            queued_actions=(self.queued_action,),
        )

    async def execute(self, command):
        self.execute_commands.append(command)
        raise AssertionError("artifact generation must not run in chat path")


class ValidationFailingArtifactModel(BaseModel):
    required_value: int


class ValidationFailingArtifactExecutor:
    def __init__(self, error: ValidationError) -> None:
        self.error = error
        self.commands: list[object] = []

    async def queue(self, command):
        self.commands.append(command)
        raise self.error

    async def execute(self, command):
        self.commands.append(command)
        raise self.error


class RecordingResponder:
    def __init__(
        self,
        result: SupervisorTurnResult | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.result = result or SupervisorTurnResult(response="Created.")
        self.error = error
        self.contexts: list[object] = []

    async def run_turn(self, context):
        self.contexts.append(context)
        if self.error is not None:
            raise self.error
        return self.result

    async def stream_turn(self, context):
        self.contexts.append(context)
        if self.error is not None:
            raise self.error
        yield SupervisorTextDelta(text=self.result.response)
        yield SupervisorTurnCompleted(result=self.result)


def artifact_execution_result(
    claim: ChatTurnClaim,
) -> AgentColArtifactExecutionResult:
    effect_claim, action, artifact, adaptation = artifact_receipts(claim)
    projection = AgentColArtifactResponderProjection(
        artifact=artifact,
        project_name="Collaborative Study Workflow",
        core_value_proposition=(
            "Creates approved learning plans with verifiable milestones."
        ),
        socratic_questions=("Which learning goal comes first?",),
        adaptations=(adaptation,),
    )
    return AgentColArtifactExecutionResult(
        claim=effect_claim,
        actions=(action,),
        artifacts=(artifact,),
        adaptations=(adaptation,),
        projection=projection,
    )


@pytest.mark.asyncio
async def test_turn_service_routes_artifact_through_application_executor(
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    claim = initial_claim()
    execution = artifact_execution_result(claim)
    routing = RecordingV4RoutingRequest(artifact_directive())
    expert = RecordingExpertExecutor()
    artifact_executor = RecordingArtifactExecutor(execution)
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=expert,
        responder_runtime=responder,
        artifact_executor=artifact_executor,
        artifact_routing_request=routing,
        wall_clock=lambda: NOW,
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id=claim.request.project_id,
            session_id=claim.request.session_id,
            user_id=claim.request.user_id,
            message=claim.request.message,
            chat_turn_claim=claim,
        )
    )

    assert len(routing.calls) == 1
    routing_input = routing.calls[0][1]
    assert routing_input.artifact_creation_available is True
    assert routing_input.structured_decision_present is False
    assert len(artifact_executor.commands) == 1
    assert artifact_executor.execute_commands == []
    artifact_command = artifact_executor.commands[0]
    assert artifact_command.claim is claim
    assert artifact_command.routing_directive == artifact_directive()
    assert artifact_command.observed_at == NOW
    assert expert.calls == []
    assert len(responder.contexts) == 1
    responder_context = responder.contexts[0]
    assert responder_context.precompleted_actions == ()
    assert len(responder_context.prequeued_actions) == 1
    assert len(responder_context.model_input_context) == 1
    context_text = responder_context.model_input_context[0].parts[0].text
    assert context_text is not None
    assert "queued for background processing" in context_text
    assert "[SERVER_VALIDATED_ARTIFACT_RESULT]" not in context_text
    assert SOURCE_TEXT not in context_text
    assert result.actions == ()
    assert result.artifacts == ()
    assert result.adaptations == ()
    assert len(result.queued_actions) == 1
    assert result.chat_turn_claim is claim


@pytest.mark.asyncio
async def test_turn_service_queues_artifact_before_responder_without_generation(
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    claim = initial_claim()
    queued_action = QueuedActionReceipt(
        job_id="artifact-job-1",
        action_kind="create_artifact",
        status="queued",
        display_label="Artifact: structured blueprint",
        created_at=NOW,
        agent_label="Artifact Builder",
    )
    artifact_executor = QueueOnlyArtifactExecutor(queued_action)
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExpertExecutor(),
        responder_runtime=responder,
        artifact_executor=artifact_executor,
        artifact_routing_request=RecordingV4RoutingRequest(
            artifact_directive()
        ),
        wall_clock=lambda: NOW,
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id=claim.request.project_id,
            session_id=claim.request.session_id,
            user_id=claim.request.user_id,
            message=claim.request.message,
            chat_turn_claim=claim,
        )
    )

    assert len(artifact_executor.queue_commands) == 1
    assert artifact_executor.execute_commands == []
    assert result.actions == ()
    assert result.artifacts == ()
    assert result.queued_actions == (queued_action,)
    assert result.chat_turn_claim is claim
    assert len(responder.contexts) == 1
    responder_context = responder.contexts[0]
    assert responder_context.prequeued_actions == (queued_action,)
    assert responder_context.precompleted_actions == ()
    assert responder_context.precompleted_memory_proposals == ()
    context_text = responder_context.model_input_context[0].parts[0].text
    assert context_text is not None
    assert "queued for background processing" in context_text
    assert "application already created" not in context_text.lower()
    assert SOURCE_TEXT not in context_text


@pytest.mark.asyncio
async def test_turn_service_logs_artifact_pipeline_without_private_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService
    import agent_col_turn_service

    claim = initial_claim()
    claim = replace(
        claim,
        request=replace(
            claim.request,
            message="private artifact prompt marker",
        ),
    )
    execution = artifact_execution_result(claim)
    routing = RecordingV4RoutingRequest(artifact_directive())
    artifact_executor = RecordingArtifactExecutor(execution)
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExpertExecutor(),
        responder_runtime=responder,
        artifact_executor=artifact_executor,
        artifact_routing_request=routing,
        wall_clock=lambda: NOW,
    )
    caplog.set_level(logging.INFO, logger=agent_col_turn_service.logger.name)

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id=claim.request.project_id,
            session_id=claim.request.session_id,
            user_id=claim.request.user_id,
            message=claim.request.message,
            chat_turn_claim=claim,
        )
    )

    assert result.artifacts == ()
    assert len(result.queued_actions) == 1
    assert "Agent_Col turn pipeline" in caplog.text
    assert "stage=routing_finish" in caplog.text
    assert "route=artifact" in caplog.text
    assert "stage=artifact_queued" in caplog.text
    assert "artifacts=0" in caplog.text
    assert "queued_actions=1" in caplog.text
    assert "stage=responder_finish" in caplog.text
    assert "private artifact prompt marker" not in caplog.text
    assert "Collaborative Study Workflow" not in caplog.text


@pytest.mark.asyncio
async def test_streamed_artifact_routing_projects_long_recent_user_messages(
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    claim = initial_claim()
    routing = RecordingV4RoutingRequest(artifact_directive())
    artifact_executor = RecordingArtifactExecutor(
        artifact_execution_result(claim)
    )
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExpertExecutor(),
        responder_runtime=responder,
        artifact_executor=artifact_executor,
        artifact_routing_request=routing,
        wall_clock=lambda: NOW,
    )
    recent_messages = (
        "old ignored 0",
        "old ignored 1",
        "old ignored 2",
        "   ",
        *(f"kept recent {index}" for index in range(9)),
        f"  {'x' * 1_200}  ",
    )

    events = [
        event
        async for event in service.stream_turn(
            AgentColTurnCommand(
                project_id=claim.request.project_id,
                session_id=claim.request.session_id,
                user_id=claim.request.user_id,
                message=claim.request.message,
                recent_user_messages=recent_messages,
                chat_turn_claim=claim,
            )
        )
    ]

    assert len(routing.calls) == 1
    routing_input = routing.calls[0][1]
    assert routing_input.recent_user_messages == (
        *(f"kept recent {index}" for index in range(9)),
        "x" * 1_000,
    )
    assert all(
        0 < len(message) <= 1_000
        for message in routing_input.recent_user_messages
    )
    assert events[-1].result.response == "Created."
    assert events[-1].result.artifacts == ()
    assert len(events[-1].result.queued_actions) == 1


@pytest.mark.asyncio
async def test_streamed_artifact_validation_failure_is_wrapped_safely(
) -> None:
    from agent_col_turn_service import (
        AgentColTurnCommand,
        AgentColTurnService,
        AgentColTurnServiceError,
    )

    claim = initial_claim()
    try:
        ValidationFailingArtifactModel.model_validate({})
    except ValidationError as exc:
        validation_error = exc
    artifact_executor = ValidationFailingArtifactExecutor(validation_error)
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExpertExecutor(),
        responder_runtime=responder,
        artifact_executor=artifact_executor,
        artifact_routing_request=RecordingV4RoutingRequest(
            artifact_directive()
        ),
        wall_clock=lambda: NOW,
    )

    with pytest.raises(AgentColTurnServiceError) as captured:
        _ = [
            event
            async for event in service.stream_turn(
                AgentColTurnCommand(
                    project_id=claim.request.project_id,
                    session_id=claim.request.session_id,
                    user_id=claim.request.user_id,
                    message=claim.request.message,
                    chat_turn_claim=claim,
                )
            )
        ]

    assert captured.value.__cause__ is validation_error
    assert captured.value.chat_turn_claim is claim
    assert len(artifact_executor.commands) == 1
    assert responder.contexts == []
    assert "required_value" not in str(captured.value)


@pytest.mark.asyncio
async def test_turn_service_forwards_resumed_claim_to_artifact_executor(
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    initial = initial_claim()
    execution = artifact_execution_result(initial)
    resumed = replace(execution.claim, resumed=True)
    resumed_execution = replace(execution, claim=resumed)
    artifact_executor = RecordingArtifactExecutor(resumed_execution)
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExpertExecutor(),
        responder_runtime=RecordingResponder(),
        artifact_executor=artifact_executor,
        artifact_routing_request=RecordingV4RoutingRequest(
            artifact_directive()
        ),
        wall_clock=lambda: NOW,
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id=resumed.request.project_id,
            session_id=resumed.request.session_id,
            user_id=resumed.request.user_id,
            message=resumed.request.message,
            precompleted_actions=resumed.precompleted_actions,
            chat_turn_claim=resumed,
        )
    )

    assert artifact_executor.commands[0].claim is resumed
    assert artifact_executor.execute_commands == []
    assert result.chat_turn_claim is resumed
    assert result.artifacts == ()
    assert len(result.queued_actions) == 1


@pytest.mark.asyncio
async def test_artifact_responder_failure_preserves_authoritative_effects(
) -> None:
    from agent_col_turn_service import (
        AgentColTurnCommand,
        AgentColTurnResponderError,
        AgentColTurnService,
    )

    claim = initial_claim()
    execution = artifact_execution_result(claim)
    runtime_error = SupervisorRuntimeError("private-responder-output")
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExpertExecutor(),
        responder_runtime=RecordingResponder(error=runtime_error),
        artifact_executor=RecordingArtifactExecutor(execution),
        artifact_routing_request=RecordingV4RoutingRequest(
            artifact_directive()
        ),
        wall_clock=lambda: NOW,
    )

    with pytest.raises(AgentColTurnResponderError) as captured:
        await service.run_turn(
            AgentColTurnCommand(
                project_id=claim.request.project_id,
                session_id=claim.request.session_id,
                user_id=claim.request.user_id,
                message=claim.request.message,
                chat_turn_claim=claim,
            )
        )

    assert captured.value.__cause__ is runtime_error
    assert captured.value.actions == ()
    assert captured.value.artifacts == ()
    assert captured.value.adaptations == ()
    assert len(captured.value.queued_actions) == 1
    assert captured.value.chat_turn_claim is claim
    assert "private-responder-output" not in str(captured.value)


@pytest.mark.asyncio
async def test_v4_nonartifact_route_uses_existing_v3_executor_path() -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    claim = initial_claim()
    routing = RecordingV4RoutingRequest(
        AgentColRoutingDirective(schema_version="4.0", route="direct")
    )
    expert = RecordingExpertExecutor()
    artifact_executor = RecordingArtifactExecutor(
        artifact_execution_result(claim)
    )
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=expert,
        responder_runtime=RecordingResponder(),
        artifact_executor=artifact_executor,
        artifact_routing_request=routing,
        wall_clock=lambda: NOW,
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id=claim.request.project_id,
            session_id=claim.request.session_id,
            user_id=claim.request.user_id,
            message="Explain why artifact receipts matter.",
            chat_turn_claim=replace(
                claim,
                request=replace(
                    claim.request,
                    message="Explain why artifact receipts matter.",
                ),
            ),
        )
    )

    assert result.response == "Created."
    assert artifact_executor.commands == []
    assert len(expert.calls) == 1
    directive, routing_input = expert.calls[0]
    assert directive.schema_version == "3.0"
    assert directive.route == "direct"
    assert not hasattr(routing_input, "artifact_creation_available")


@pytest.mark.asyncio
async def test_existing_v3_service_path_does_not_require_artifact_authority(
) -> None:
    from agent_col_routing_v3 import AgentColRoutingDirective as V3Directive
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    routing = RecordingV4RoutingRequest(V3Directive(route="direct"))
    expert = RecordingExpertExecutor()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=expert,
        responder_runtime=RecordingResponder(),
        routing_request=routing,
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id="agent-col",
            session_id="legacy-v3-session",
            user_id="legacy-v3-user",
            message="Explain one stable concept.",
        )
    )

    assert result.response == "Created."
    assert len(expert.calls) == 1


@pytest.mark.asyncio
async def test_artifact_path_rejects_claim_that_does_not_match_command(
) -> None:
    from agent_col_turn_service import (
        AgentColTurnCommand,
        AgentColTurnService,
        AgentColTurnServiceError,
    )

    claim = initial_claim()
    routing = RecordingV4RoutingRequest(artifact_directive())
    artifact_executor = RecordingArtifactExecutor(
        artifact_execution_result(claim)
    )
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=RecordingExpertExecutor(),
        responder_runtime=responder,
        artifact_executor=artifact_executor,
        artifact_routing_request=routing,
        wall_clock=lambda: NOW,
    )

    with pytest.raises(
        AgentColTurnServiceError,
        match="artifact claim is inconsistent",
    ):
        await service.run_turn(
            AgentColTurnCommand(
                project_id=claim.request.project_id,
                session_id=claim.request.session_id,
                user_id=claim.request.user_id,
                message="Different message content.",
                chat_turn_claim=claim,
            )
        )

    assert routing.calls == []
    assert artifact_executor.commands == []
    assert responder.contexts == []
