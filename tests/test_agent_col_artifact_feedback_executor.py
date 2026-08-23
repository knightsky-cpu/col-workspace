from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from artifact_feedback_service import (
    ResolvedArtifactFeedback,
)
from chat_turns import ChatTurnClaim, ChatTurnRequest, derive_chat_turn_ids
from database import ChatTurnFeedbackEffectResult
from schemas import (
    AgentActionReceipt,
    ArtifactFeedbackDecisionRequest,
    ArtifactFeedbackReference,
    ArtifactFeedbackTarget,
    ArtifactReference,
)


NOW = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)
TARGET_ID = "target--0123456789abcdef01234567"


def feedback_request() -> ArtifactFeedbackDecisionRequest:
    return ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id=TARGET_ID,
        decision="edited",
        feedback_text="The milestone needs a measurable outcome.",
        correction_text="Require one passing verification command.",
        expected_schema_version="2.0",
    )


def initial_claim() -> ChatTurnClaim:
    return ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="feedback-session",
            user_id="user-1",
            message="Apply this correction to the selected milestone.",
            artifact_feedback_decision=feedback_request(),
        ),
        ids=derive_chat_turn_ids("artifact-feedback-executor-1"),
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=120),
        resumed=False,
    )


def artifact() -> ArtifactReference:
    return ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id="agent-col",
        artifact_id="blueprint-1",
        schema_version="2.0",
        display_label="Collaborative Study Plan",
    )


def resolved(claim: ChatTurnClaim) -> ResolvedArtifactFeedback:
    return ResolvedArtifactFeedback(
        feedback_id=f"feedback--{claim.ids.turn_id}",
        artifact=artifact(),
        target=ArtifactFeedbackTarget(
            target_id=TARGET_ID,
            target_kind="roadmap_milestone",
            display_label="Verification milestone",
        ),
    )


class FakeResolver:
    def __init__(self, result: ResolvedArtifactFeedback) -> None:
        self.result = result
        self.commands: list[object] = []

    async def resolve_feedback_target(self, command):
        self.commands.append(command)
        return self.result


class FakeLedger:
    def __init__(self, result: ChatTurnFeedbackEffectResult) -> None:
        self.result = result
        self.calls: list[tuple[object, str, datetime]] = []

    async def record_chat_turn_artifact_feedback_effect(
        self,
        claim,
        *,
        target_kind,
        observed_at,
    ):
        self.calls.append((claim, target_kind, observed_at))
        return self.result


def effect(claim: ChatTurnClaim) -> ChatTurnFeedbackEffectResult:
    action = AgentActionReceipt(
        action_name="record_blueprint_feedback",
        status="completed",
    )
    feedback = ArtifactFeedbackReference(
        feedback_id=f"feedback--{claim.ids.turn_id}",
        artifact_id="blueprint-1",
        target_id=TARGET_ID,
        target_kind="roadmap_milestone",
        decision="edited",
        schema_version="2.0",
        created_at=NOW,
    )
    return ChatTurnFeedbackEffectResult(
        claim=replace(
            claim,
            precompleted_actions=(action,),
            precompleted_artifact_feedback=(feedback,),
        ),
        action=action,
        feedback=feedback,
    )


@pytest.mark.asyncio
async def test_feedback_executor_resolves_and_records_atomic_turn_effect(
) -> None:
    from agent_col_artifact_feedback_executor import (
        AgentColArtifactFeedbackExecutionCommand,
        AgentColArtifactFeedbackExecutor,
    )

    claim = initial_claim()
    resolver = FakeResolver(resolved(claim))
    ledger = FakeLedger(effect(claim))
    executor = AgentColArtifactFeedbackExecutor(
        feedback_resolver=resolver,
        feedback_ledger=ledger,
    )

    result = await executor.execute(
        AgentColArtifactFeedbackExecutionCommand(
            claim=claim,
            observed_at=NOW,
        )
    )

    assert len(resolver.commands) == 1
    resolution_command = resolver.commands[0]
    assert resolution_command.project_id == "agent-col"
    assert resolution_command.source_message_id == claim.ids.user_message_id
    assert resolution_command.turn_id == claim.ids.turn_id
    assert resolution_command.feedback == feedback_request()
    assert ledger.calls == [(claim, "roadmap_milestone", NOW)]
    assert result.claim == effect(claim).claim
    assert result.actions == (effect(claim).action,)
    assert result.artifact_feedback == (effect(claim).feedback,)
    assert result.projection.target_label == "Verification milestone"
    assert result.projection.correction_text == (
        "Require one passing verification command."
    )

