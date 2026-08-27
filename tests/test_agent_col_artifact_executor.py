from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest
from google.genai import types

from agent_col_routing_v4 import AgentColRoutingDirective
from chat_turns import ChatTurnClaim, ChatTurnRequest, derive_chat_turn_ids
from database import ChatTurnArtifactEffectResult
from schemas import (
    AdaptationReceipt,
    AdaptationReceiptV2,
    AgentActionReceipt,
    ArtifactFeedbackDecisionRequest,
    ArtifactFeedbackCounts,
    ArtifactReference,
    BlueprintArtifactDetailResponse,
    BlueprintArtifactMetadata,
    MemoryDecisionRequest,
    SingleFileArtifact,
    SingleFileArtifactDetailResponse,
    SingleFileArtifactMetadata,
    SynthesisBlueprint,
)


NOW = datetime(2026, 8, 23, 15, 0, tzinfo=UTC)
SOURCE_TEXT = (
    "Create a structured blueprint for a collaborative study partner with "
    "explicit approval, bounded memory, and verifiable milestones."
)


def test_artifact_projection_accepts_v2_adaptation_receipt() -> None:
    from agent_col_artifact_executor import AgentColArtifactResponderProjection

    receipt = AdaptationReceiptV2(
        signal_id="development_environments--signal-v2",
        category="development_environments",
        value=["linux", "macos"],
        source_event_id=(
            "development_environments--signal-v2--approved"
        ),
        status="provided_to_model",
    )
    artifact = ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id="project-1",
        artifact_id="blueprint-v2",
        schema_version="2.0",
        display_label="Versioned Blueprint",
    )

    projection = AgentColArtifactResponderProjection(
        artifact=artifact,
        socratic_questions=(),
        adaptations=(receipt,),
    )

    assert projection.adaptations == (receipt,)


def blueprint() -> SynthesisBlueprint:
    return SynthesisBlueprint.model_validate(
        {
            "synthesized_conceptual_model": {
                "project_name": "Collaborative Study Partner",
                "core_value_proposition": (
                    "Turns learning goals into approved, verifiable plans."
                ),
                "in_scope": ["Collaborative planning"],
            },
            "personalization_trace": {},
            "architectural_decisions": [
                {
                    "component_name": "Approval boundary",
                    "proposed_solution": "Explicit structured decisions",
                    "rationale": "Keeps durable changes user-controlled.",
                    "alternatives": [
                        {
                            "option_name": "Inferred approval",
                            "tradeoff": "Lower friction but weaker control.",
                            "reason_not_selected": "Cannot prove consent.",
                        }
                    ],
                }
            ],
            "socratic_clarifying_questions": [
                {
                    "question_text": "Which learning goal comes first?",
                    "why_this_matters": "It determines the first milestone.",
                    "suggested_options": [
                        {"label": "Theory", "impact": "Start conceptually."},
                        {"label": "Practice", "impact": "Start hands-on."},
                    ],
                }
            ],
            "step_by_step_execution_roadmap": [
                {
                    "phase_name": "Foundation",
                    "objective": "Define the first learning goal.",
                    "expected_deliverable": "An approved milestone.",
                    "micro_tasks": [
                        {
                            "task_description": "Choose the first goal.",
                            "complexity_level": "Low",
                            "verification_steps": ["Record explicit approval."],
                        }
                    ],
                }
            ],
        }
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


def single_file_artifact_directive() -> AgentColRoutingDirective:
    return AgentColRoutingDirective.model_validate(
        {
            "schema_version": "4.0",
            "route": "artifact",
            "artifact_intent": {
                "operation": "create_single_file_artifact",
                "objective": "Create the requested password generator code artifact.",
                "artifact_family": "code",
                "format": "python",
                "filename": "password_generator.py",
            },
        }
    )


def initial_claim() -> ChatTurnClaim:
    return ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            message=SOURCE_TEXT,
        ),
        ids=derive_chat_turn_ids("artifact-turn-1"),
        owner_token="owner-token",
        lease_expires_at=NOW + timedelta(seconds=120),
        resumed=False,
    )


def artifact_for_claim(claim: ChatTurnClaim) -> ArtifactReference:
    return ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id=claim.request.project_id,
        artifact_id=f"blueprint--{claim.ids.turn_id}",
        schema_version="2.0",
        display_label="Collaborative Study Partner",
    )


def single_file_reference_for_claim(claim: ChatTurnClaim) -> ArtifactReference:
    return ArtifactReference(
        artifact_type="single_file_artifact",
        project_id=claim.request.project_id,
        artifact_id=f"artifact--{claim.ids.turn_id}",
        schema_version="1.0",
        display_label="Password Generator",
    )


def single_file_artifact() -> SingleFileArtifact:
    return SingleFileArtifact(
        artifact_family="code",
        format="python",
        filename="password_generator.py",
        content="import secrets\nprint(secrets.token_urlsafe(12))\n",
        summary="Password Generator",
    )


def single_file_detail(
    claim: ChatTurnClaim,
    artifact: ArtifactReference,
    generated: SingleFileArtifact,
) -> SingleFileArtifactDetailResponse:
    return SingleFileArtifactDetailResponse(
        metadata=SingleFileArtifactMetadata(
            reference=artifact,
            created_at=NOW,
            originating_session_id=claim.request.session_id,
            originating_turn_id=claim.ids.turn_id,
            filename=generated.filename,
            artifact_family=generated.artifact_family,
            format=generated.format,
            byte_size=len(generated.content.encode("utf-8")),
        ),
        artifact=generated,
    )


def artifact_detail(
    claim: ChatTurnClaim,
    artifact: ArtifactReference,
    generated: SynthesisBlueprint,
) -> BlueprintArtifactDetailResponse:
    return BlueprintArtifactDetailResponse(
        metadata=BlueprintArtifactMetadata(
            reference=artifact,
            created_at=NOW,
            originating_session_id=claim.request.session_id,
            originating_turn_id=claim.ids.turn_id,
            feedback_counts=ArtifactFeedbackCounts(),
        ),
        blueprint=generated,
        feedback_targets=[],
    )


def test_build_artifact_source_text_uses_recent_context_for_reference_request(
) -> None:
    from agent_col_artifact_executor import build_artifact_source_text

    source_text = build_artifact_source_text(
        current_message="Turn that into a markdown artifact.",
        recent_user_messages=(
            "I need a simple Pomodoro timer with work sessions, short breaks, "
            "and a reset control.",
        ),
    )

    assert "[CURRENT_ARTIFACT_REQUEST]" in source_text
    assert "Turn that into a markdown artifact." in source_text
    assert "[RECENT_USER_CONTEXT]" in source_text
    assert "simple Pomodoro timer" in source_text


def test_build_artifact_source_text_uses_last_six_recent_context_messages(
) -> None:
    from agent_col_artifact_executor import build_artifact_source_text

    recent_messages = tuple(f"Context message {index}" for index in range(8))

    source_text = build_artifact_source_text(
        current_message="Turn that into a markdown artifact.",
        recent_user_messages=recent_messages,
    )

    assert "Context message 0" not in source_text
    assert "Context message 1" not in source_text
    for index in range(2, 8):
        assert f"Context message {index}" in source_text


def test_build_artifact_source_text_keeps_self_contained_request_single_source(
) -> None:
    from agent_col_artifact_executor import build_artifact_source_text

    source_text = build_artifact_source_text(
        current_message=(
            "Create a blueprint for a simple Pomodoro timer with a work "
            "interval, break interval, start button, pause button, and reset."
        ),
        recent_user_messages=(
            "Unrelated old request about a study tracker.",
        ),
    )

    assert source_text.startswith("Create a blueprint for a simple Pomodoro")
    assert "Unrelated old request" not in source_text


@dataclass
class FakeSynthesisService:
    generated: SynthesisBlueprint
    adaptations: tuple[AdaptationReceipt, ...] = ()
    commands: list[object] = field(default_factory=list)

    async def generate_governed_blueprint(self, command: object) -> object:
        from synthesis_service import GovernedSynthesisGenerationResult

        self.commands.append(command)
        return GovernedSynthesisGenerationResult(
            blueprint=self.generated,
            adaptations=self.adaptations,
        )


@dataclass
class FakeGenericArtifactGenerator:
    generated: SingleFileArtifact
    calls: list[tuple[object, object]] = field(default_factory=list)

    async def __call__(
        self,
        client: object,
        request: object,
    ) -> SingleFileArtifact:
        self.calls.append((client, request))
        return self.generated


@dataclass
class FakeArtifactLedger:
    result: ChatTurnArtifactEffectResult
    calls: list[tuple[object, dict[str, object]]] = field(default_factory=list)

    async def record_chat_turn_blueprint_effect(
        self,
        claim: ChatTurnClaim,
        **kwargs: object,
    ) -> ChatTurnArtifactEffectResult:
        self.calls.append((claim, kwargs))
        return self.result

    async def record_chat_turn_single_file_artifact_effect(
        self,
        claim: ChatTurnClaim,
        **kwargs: object,
    ) -> ChatTurnArtifactEffectResult:
        self.calls.append((claim, kwargs))
        return self.result


@dataclass
class FakeArtifactReader:
    detail: BlueprintArtifactDetailResponse
    commands: list[object] = field(default_factory=list)

    async def get_blueprint(
        self,
        command: object,
    ) -> BlueprintArtifactDetailResponse:
        self.commands.append(command)
        return self.detail


@dataclass
class FakeGenericArtifactReader:
    detail: SingleFileArtifactDetailResponse
    commands: list[object] = field(default_factory=list)

    async def get_artifact(
        self,
        command: object,
    ) -> SingleFileArtifactDetailResponse:
        self.commands.append(command)
        return self.detail


@pytest.mark.asyncio
async def test_artifact_executor_generates_once_and_projects_canonical_receipts(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactExecutionCommand,
        AgentColArtifactExecutor,
    )
    from artifact_read_service import GetBlueprintArtifactCommand
    from synthesis_service import SynthesisCommand

    claim = initial_claim()
    generated = blueprint()
    artifact = artifact_for_claim(claim)
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    effect_claim = replace(
        claim,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    adaptation = AdaptationReceipt(
        signal_id="planning_granularity--signal-1",
        category="planning_granularity",
        value="micro_steps",
        source_event_id="planning_granularity--signal-1--approved",
        status="provided_to_model",
    )
    synthesis_service = FakeSynthesisService(generated, (adaptation,))
    ledger = FakeArtifactLedger(
        ChatTurnArtifactEffectResult(
            claim=effect_claim,
            artifact=artifact,
        )
    )
    detail = artifact_detail(
        effect_claim,
        artifact,
        generated,
    ).model_copy(update={"adaptations": [adaptation]})
    reader = FakeArtifactReader(detail)
    executor = AgentColArtifactExecutor(
        synthesis_service=synthesis_service,
        artifact_ledger=ledger,
        artifact_reader=reader,
    )

    result = await executor.execute(
        AgentColArtifactExecutionCommand(
            claim=claim,
            routing_directive=artifact_directive(),
            observed_at=NOW,
        )
    )

    assert synthesis_service.commands == [
        SynthesisCommand(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            source_text=SOURCE_TEXT,
        )
    ]
    assert len(ledger.calls) == 1
    ledger_claim, ledger_arguments = ledger.calls[0]
    assert ledger_claim is claim
    assert ledger_arguments == {
        "model_name": "gemini-3.6-flash",
        "schema_version": "2.0",
        "blueprint": generated.model_dump(mode="json"),
        "display_label": "Collaborative Study Partner",
        "observed_at": NOW,
        "adaptations": (adaptation,),
    }
    assert reader.commands == [
        GetBlueprintArtifactCommand(
            project_id="agent-col",
            blueprint_id=artifact.artifact_id,
        )
    ]
    assert result.claim is effect_claim
    assert result.actions == (action,)
    assert result.artifacts == (artifact,)
    assert result.projection.artifact == artifact
    assert result.projection.project_name == "Collaborative Study Partner"
    assert result.projection.core_value_proposition == (
        "Turns learning goals into approved, verifiable plans."
    )
    assert result.projection.socratic_questions == (
        "Which learning goal comes first?",
    )
    assert result.adaptations == (adaptation,)
    assert result.projection.adaptations == (adaptation,)
    assert result.projection.limitations == ()


@pytest.mark.asyncio
async def test_artifact_executor_uses_server_projected_source_text(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactExecutionCommand,
        AgentColArtifactExecutor,
    )
    from synthesis_service import SynthesisCommand

    claim = initial_claim()
    generated = blueprint()
    artifact = artifact_for_claim(claim)
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    effect_claim = replace(
        claim,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    synthesis_service = FakeSynthesisService(generated)
    ledger = FakeArtifactLedger(
        ChatTurnArtifactEffectResult(
            claim=effect_claim,
            artifact=artifact,
        )
    )
    reader = FakeArtifactReader(
        artifact_detail(effect_claim, artifact, generated)
    )
    executor = AgentColArtifactExecutor(
        synthesis_service=synthesis_service,
        artifact_ledger=ledger,
        artifact_reader=reader,
    )

    await executor.execute(
        AgentColArtifactExecutionCommand(
            claim=claim,
            routing_directive=artifact_directive(),
            observed_at=NOW,
            source_text="Server-owned source projection.",
        )
    )

    assert synthesis_service.commands == [
        SynthesisCommand(
            project_id="agent-col",
            session_id="session-1",
            user_id="user-1",
            source_text="Server-owned source projection.",
        )
    ]


@pytest.mark.asyncio
async def test_artifact_executor_generates_single_file_artifact_without_blueprint(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactExecutionCommand,
        AgentColArtifactExecutor,
    )
    from generic_artifact_generation import GenericArtifactGenerationRequest
    from generic_artifact_service import GetGenericArtifactCommand

    claim = initial_claim()
    generated = single_file_artifact()
    artifact = single_file_reference_for_claim(claim)
    action = AgentActionReceipt(
        action_name="create_artifact",
        status="completed",
    )
    effect_claim = replace(
        claim,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    synthesis_service = FakeSynthesisService(blueprint())
    generic_generator = FakeGenericArtifactGenerator(generated)
    ledger = FakeArtifactLedger(
        ChatTurnArtifactEffectResult(
            claim=effect_claim,
            artifact=artifact,
        )
    )
    reader = FakeArtifactReader(
        artifact_detail(effect_claim, artifact_for_claim(claim), blueprint())
    )
    generic_reader = FakeGenericArtifactReader(
        single_file_detail(effect_claim, artifact, generated)
    )
    genai_client = object()
    executor = AgentColArtifactExecutor(
        synthesis_service=synthesis_service,
        artifact_ledger=ledger,
        artifact_reader=reader,
        generic_artifact_generator=generic_generator,
        generic_artifact_reader=generic_reader,
        genai_client=genai_client,
    )

    result = await executor.execute(
        AgentColArtifactExecutionCommand(
            claim=claim,
            routing_directive=single_file_artifact_directive(),
            observed_at=NOW,
            source_text="Create a Python password generator.",
        )
    )

    assert synthesis_service.commands == []
    assert generic_generator.calls == [
        (
            genai_client,
            GenericArtifactGenerationRequest(
                artifact_family="code",
                artifact_format="python",
                filename="password_generator.py",
                source_text="Create a Python password generator.",
                context_messages=(),
            ),
        )
    ]
    assert len(ledger.calls) == 1
    ledger_claim, ledger_arguments = ledger.calls[0]
    assert ledger_claim is claim
    assert ledger_arguments == {
        "model_name": "gemini-3.6-flash",
        "artifact": generated.model_dump(mode="json"),
        "display_label": "Password Generator",
        "observed_at": NOW,
    }
    assert generic_reader.commands == [
        GetGenericArtifactCommand(
            project_id="agent-col",
            artifact_id=artifact.artifact_id,
        )
    ]
    assert reader.commands == []
    assert result.claim is effect_claim
    assert result.actions == (action,)
    assert result.artifacts == (artifact,)
    assert result.projection.operation == "create_single_file_artifact"
    assert result.projection.artifact == artifact
    assert result.projection.filename == "password_generator.py"
    assert result.projection.format == "python"
    assert result.projection.artifact_family == "code"
    assert result.projection.summary == "Password Generator"


@pytest.mark.asyncio
async def test_artifact_executor_bounds_summary_derived_artifact_receipt_label(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactExecutionCommand,
        AgentColArtifactExecutor,
    )

    claim = initial_claim()
    long_summary = "A" * 300
    generated = SingleFileArtifact(
        artifact_family="document",
        format="text",
        filename="algebra-rules.txt",
        content="Fundamental algebraic rules.\n",
        summary=long_summary,
    )
    artifact = single_file_reference_for_claim(claim).model_copy(
        update={"display_label": long_summary[:160]}
    )
    action = AgentActionReceipt(
        action_name="create_artifact",
        status="completed",
    )
    effect_claim = replace(
        claim,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    generic_generator = FakeGenericArtifactGenerator(generated)
    ledger = FakeArtifactLedger(
        ChatTurnArtifactEffectResult(
            claim=effect_claim,
            artifact=artifact,
        )
    )
    generic_reader = FakeGenericArtifactReader(
        single_file_detail(effect_claim, artifact, generated)
    )
    executor = AgentColArtifactExecutor(
        synthesis_service=FakeSynthesisService(blueprint()),
        artifact_ledger=ledger,
        artifact_reader=FakeArtifactReader(
            artifact_detail(effect_claim, artifact_for_claim(claim), blueprint())
        ),
        generic_artifact_generator=generic_generator,
        generic_artifact_reader=generic_reader,
        genai_client=object(),
    )

    result = await executor.execute(
        AgentColArtifactExecutionCommand(
            claim=claim,
            routing_directive=AgentColRoutingDirective.model_validate(
                {
                    "schema_version": "4.0",
                    "route": "artifact",
                    "artifact_intent": {
                        "operation": "create_single_file_artifact",
                        "objective": "Create the requested algebra rules artifact.",
                        "artifact_family": "document",
                        "format": "text",
                        "filename": "algebra-rules.txt",
                    },
                }
            ),
            observed_at=NOW,
            source_text="Create a text document containing algebraic rules.",
        )
    )

    assert ledger.calls[0][1]["display_label"] == long_summary[:160]
    assert ledger.calls[0][1]["artifact"]["summary"] == long_summary
    assert result.projection.summary == long_summary


@pytest.mark.asyncio
async def test_artifact_executor_reuses_precompleted_effect_before_generation(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactExecutionCommand,
        AgentColArtifactExecutor,
    )

    claim = initial_claim()
    generated = blueprint()
    artifact = artifact_for_claim(claim)
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    resumed_claim = replace(
        claim,
        resumed=True,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    synthesis_service = FakeSynthesisService(generated)
    ledger = FakeArtifactLedger(
        ChatTurnArtifactEffectResult(
            claim=resumed_claim,
            artifact=artifact,
        )
    )
    reader = FakeArtifactReader(
        artifact_detail(resumed_claim, artifact, generated)
    )
    executor = AgentColArtifactExecutor(
        synthesis_service=synthesis_service,
        artifact_ledger=ledger,
        artifact_reader=reader,
    )

    result = await executor.execute(
        AgentColArtifactExecutionCommand(
            claim=resumed_claim,
            routing_directive=artifact_directive(),
            observed_at=NOW,
        )
    )

    assert synthesis_service.commands == []
    assert ledger.calls == []
    assert result.claim is resumed_claim
    assert result.actions == (action,)
    assert result.artifacts == (artifact,)
    assert result.projection.artifact == artifact


def test_artifact_responder_projection_excludes_source_and_full_blueprint(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactResponderProjection,
        build_agent_col_artifact_model_context,
    )

    claim = initial_claim()
    projection = AgentColArtifactResponderProjection(
        artifact=artifact_for_claim(claim),
        project_name="Collaborative Study Partner",
        core_value_proposition=(
            "Turns learning goals into approved, verifiable plans."
        ),
        socratic_questions=("Which learning goal comes first?",),
    )

    content = build_agent_col_artifact_model_context(projection)

    assert isinstance(content, types.Content)
    assert content.role == "user"
    assert len(content.parts) == 1
    text = content.parts[0].text
    assert text is not None
    assert "[SERVER_VALIDATED_ARTIFACT_RESULT]" in text
    assert "[/SERVER_VALIDATED_ARTIFACT_RESULT]" in text
    assert '"artifact_id":"blueprint--' in text
    assert '"project_name":"Collaborative Study Partner"' in text
    assert "Do not reroute" in text
    assert "do not" in text.lower()
    assert SOURCE_TEXT not in text
    assert "Explicit structured decisions" not in text
    assert "Choose the first goal" not in text


@pytest.mark.asyncio
async def test_artifact_executor_rejects_canonical_artifact_owned_by_other_turn(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactExecutionCommand,
        AgentColArtifactExecutor,
        AgentColArtifactExecutorConfigurationError,
    )

    claim = initial_claim()
    generated = blueprint()
    artifact = artifact_for_claim(claim)
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    resumed_claim = replace(
        claim,
        resumed=True,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    mismatched_detail = artifact_detail(
        resumed_claim,
        artifact,
        generated,
    ).model_copy(
        update={
            "metadata": artifact_detail(
                resumed_claim,
                artifact,
                generated,
            ).metadata.model_copy(
                update={"originating_turn_id": "different-turn"}
            )
        }
    )
    executor = AgentColArtifactExecutor(
        synthesis_service=FakeSynthesisService(generated),
        artifact_ledger=FakeArtifactLedger(
            ChatTurnArtifactEffectResult(
                claim=resumed_claim,
                artifact=artifact,
            )
        ),
        artifact_reader=FakeArtifactReader(mismatched_detail),
    )

    with pytest.raises(
        AgentColArtifactExecutorConfigurationError,
        match="Canonical artifact",
    ):
        await executor.execute(
            AgentColArtifactExecutionCommand(
                claim=resumed_claim,
                routing_directive=artifact_directive(),
                observed_at=NOW,
            )
        )


@pytest.mark.parametrize(
    "conflict",
    ("non_artifact_route", "memory_decision", "artifact_feedback_decision"),
)
@pytest.mark.asyncio
async def test_artifact_executor_rejects_conflicting_authority_before_generation(
    conflict: str,
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactExecutionCommand,
        AgentColArtifactExecutor,
        AgentColArtifactExecutorConfigurationError,
    )

    claim = initial_claim()
    directive = artifact_directive()
    if conflict == "non_artifact_route":
        directive = AgentColRoutingDirective(route="direct")
    elif conflict == "memory_decision":
        claim = replace(
            claim,
            request=replace(
                claim.request,
                memory_decision=MemoryDecisionRequest(
                    proposal_id="response_length--proposal-1",
                    decision="approve",
                ),
            ),
        )
    else:
        claim = replace(
            claim,
            request=replace(
                claim.request,
                artifact_feedback_decision=ArtifactFeedbackDecisionRequest(
                    artifact_id="blueprint-1",
                    target_id="target--0123456789abcdef01234567",
                    decision="accepted",
                    feedback_text="This boundary is correct.",
                    expected_schema_version="2.0",
                ),
            ),
        )
    generated = blueprint()
    artifact = artifact_for_claim(claim)
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    effect_claim = replace(
        claim,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    synthesis_service = FakeSynthesisService(generated)
    executor = AgentColArtifactExecutor(
        synthesis_service=synthesis_service,
        artifact_ledger=FakeArtifactLedger(
            ChatTurnArtifactEffectResult(
                claim=effect_claim,
                artifact=artifact,
            )
        ),
        artifact_reader=FakeArtifactReader(
            artifact_detail(effect_claim, artifact, generated)
        ),
    )

    with pytest.raises(AgentColArtifactExecutorConfigurationError):
        await executor.execute(
            AgentColArtifactExecutionCommand(
                claim=claim,
                routing_directive=directive,
                observed_at=NOW,
            )
        )

    assert synthesis_service.commands == []


@pytest.mark.asyncio
async def test_artifact_executor_rejects_orphaned_precompleted_action(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactExecutionCommand,
        AgentColArtifactExecutor,
        AgentColArtifactExecutorConfigurationError,
    )

    claim = replace(
        initial_claim(),
        precompleted_actions=(
            AgentActionReceipt(
                action_name="synthesize_project",
                status="completed",
            ),
        ),
    )
    synthesis_service = FakeSynthesisService(blueprint())
    executor = AgentColArtifactExecutor(
        synthesis_service=synthesis_service,
        artifact_ledger=FakeArtifactLedger(
            ChatTurnArtifactEffectResult(
                claim=claim,
                artifact=artifact_for_claim(claim),
            )
        ),
        artifact_reader=FakeArtifactReader(
            artifact_detail(claim, artifact_for_claim(claim), blueprint())
        ),
    )

    with pytest.raises(AgentColArtifactExecutorConfigurationError):
        await executor.execute(
            AgentColArtifactExecutionCommand(
                claim=claim,
                routing_directive=artifact_directive(),
                observed_at=NOW,
            )
        )

    assert synthesis_service.commands == []


@pytest.mark.asyncio
async def test_artifact_executor_projects_only_canonical_adaptation_receipts(
) -> None:
    from agent_col_artifact_executor import (
        AgentColArtifactExecutionCommand,
        AgentColArtifactExecutor,
    )

    claim = initial_claim()
    generated = blueprint()
    artifact = artifact_for_claim(claim)
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    resumed_claim = replace(
        claim,
        resumed=True,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    adaptation = AdaptationReceipt(
        signal_id="planning_granularity--signal-1",
        category="planning_granularity",
        value="micro_steps",
        source_event_id="planning_granularity--signal-1--approved",
        status="provided_to_model",
    )
    detail = artifact_detail(
        resumed_claim,
        artifact,
        generated,
    ).model_copy(update={"adaptations": [adaptation]})
    executor = AgentColArtifactExecutor(
        synthesis_service=FakeSynthesisService(generated),
        artifact_ledger=FakeArtifactLedger(
            ChatTurnArtifactEffectResult(
                claim=resumed_claim,
                artifact=artifact,
            )
        ),
        artifact_reader=FakeArtifactReader(detail),
    )

    result = await executor.execute(
        AgentColArtifactExecutionCommand(
            claim=resumed_claim,
            routing_directive=artifact_directive(),
            observed_at=NOW,
        )
    )

    assert result.adaptations == (adaptation,)
    assert result.projection.adaptations == (adaptation,)
