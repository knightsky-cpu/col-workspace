from datetime import UTC, datetime

import pytest

from agent_col_artifact_feedback_executor import (
    AgentColArtifactFeedbackExecutionResult,
    AgentColArtifactFeedbackResponderProjection,
)
from schemas import AgentActionReceipt
from supervisor_runtime import SupervisorRuntimeError, SupervisorTurnResult
from tests.test_agent_col_artifact_feedback_executor import (
    artifact,
    effect,
    feedback_request,
    initial_claim,
    resolved,
)


NOW = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)


def execution_result():
    claim = initial_claim()
    feedback_effect = effect(claim)
    resolution = resolved(claim)
    request = feedback_request()
    return AgentColArtifactFeedbackExecutionResult(
        claim=feedback_effect.claim,
        actions=(feedback_effect.action,),
        artifact_feedback=(feedback_effect.feedback,),
        projection=AgentColArtifactFeedbackResponderProjection(
            artifact=artifact(),
            feedback=feedback_effect.feedback,
            target_kind=resolution.target.target_kind,
            target_label=resolution.target.display_label,
            decision=request.decision,
            feedback_text=request.feedback_text,
            correction_text=request.correction_text,
        ),
    )


class FailIfRouted:
    async def __call__(self, *args, **kwargs):
        raise AssertionError("Structured feedback must bypass routing.")


class FailIfExpertCalled:
    available_capabilities = (
        "source",
        "research",
        "computation",
        "requirements_verification",
    )

    async def execute(self, *args, **kwargs):
        raise AssertionError("Structured feedback must bypass experts.")


class RecordingFeedbackExecutor:
    def __init__(self, result, *, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.commands: list[object] = []

    async def execute(self, command):
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return self.result


class RecordingResponder:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.contexts: list[object] = []

    async def run_turn(self, context):
        self.contexts.append(context)
        if self.error is not None:
            raise self.error
        return SupervisorTurnResult(response="Feedback recorded.")


@pytest.mark.asyncio
async def test_structured_feedback_executes_before_responder_without_routing(
) -> None:
    from agent_col_turn_service import AgentColTurnCommand, AgentColTurnService

    claim = initial_claim()
    execution = execution_result()
    feedback_executor = RecordingFeedbackExecutor(execution)
    responder = RecordingResponder()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=FailIfExpertCalled(),
        responder_runtime=responder,
        artifact_feedback_executor=feedback_executor,
        routing_request=FailIfRouted(),
        artifact_routing_request=FailIfRouted(),
        wall_clock=lambda: NOW,
    )

    result = await service.run_turn(
        AgentColTurnCommand(
            project_id=claim.request.project_id,
            session_id=claim.request.session_id,
            user_id=claim.request.user_id,
            message=claim.request.message,
            source_message_id=claim.ids.user_message_id,
            artifact_feedback_decision_present=True,
            chat_turn_claim=claim,
        )
    )

    assert len(feedback_executor.commands) == 1
    assert feedback_executor.commands[0].claim is claim
    assert len(responder.contexts) == 1
    context = responder.contexts[0]
    assert context.artifact_feedback_decision_present is True
    assert context.precompleted_actions == execution.actions
    context_text = context.model_input_context[-1].parts[0].text
    assert "[SERVER_VALIDATED_ARTIFACT_FEEDBACK_RESULT]" in context_text
    assert result.response == "Feedback recorded."
    assert result.actions == execution.actions
    assert result.artifact_feedback == execution.artifact_feedback
    assert result.chat_turn_claim is execution.claim


@pytest.mark.asyncio
async def test_feedback_responder_failure_preserves_completed_receipts() -> None:
    from agent_col_turn_service import (
        AgentColTurnCommand,
        AgentColTurnResponderError,
        AgentColTurnService,
    )

    claim = initial_claim()
    execution = execution_result()
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=FailIfExpertCalled(),
        responder_runtime=RecordingResponder(
            error=SupervisorRuntimeError("private provider output")
        ),
        artifact_feedback_executor=RecordingFeedbackExecutor(execution),
        routing_request=FailIfRouted(),
        artifact_routing_request=FailIfRouted(),
        wall_clock=lambda: NOW,
    )

    with pytest.raises(AgentColTurnResponderError) as captured:
        await service.run_turn(
            AgentColTurnCommand(
                project_id=claim.request.project_id,
                session_id=claim.request.session_id,
                user_id=claim.request.user_id,
                message=claim.request.message,
                artifact_feedback_decision_present=True,
                chat_turn_claim=claim,
            )
        )

    assert captured.value.actions == execution.actions
    assert captured.value.artifact_feedback == execution.artifact_feedback
    assert captured.value.chat_turn_claim is execution.claim
    assert "private provider output" not in str(captured.value)


@pytest.mark.asyncio
async def test_feedback_execution_failure_is_wrapped_with_safe_cause() -> None:
    from agent_col_turn_service import (
        AgentColTurnCommand,
        AgentColTurnService,
        AgentColTurnServiceError,
    )
    from artifact_feedback_service import ArtifactFeedbackTargetNotFoundError

    claim = initial_claim()
    cause = ArtifactFeedbackTargetNotFoundError("private target locator")
    service = AgentColTurnService(
        routing_client=object(),
        expert_executor=FailIfExpertCalled(),
        responder_runtime=RecordingResponder(),
        artifact_feedback_executor=RecordingFeedbackExecutor(
            execution_result(),
            error=cause,
        ),
        routing_request=FailIfRouted(),
        artifact_routing_request=FailIfRouted(),
        wall_clock=lambda: NOW,
    )

    with pytest.raises(AgentColTurnServiceError) as captured:
        await service.run_turn(
            AgentColTurnCommand(
                project_id=claim.request.project_id,
                session_id=claim.request.session_id,
                user_id=claim.request.user_id,
                message=claim.request.message,
                artifact_feedback_decision_present=True,
                chat_turn_claim=claim,
            )
        )

    assert captured.value.__cause__ is cause
    assert str(captured.value) == "Agent_Col artifact feedback execution failed."
    assert "private target locator" not in str(captured.value)
